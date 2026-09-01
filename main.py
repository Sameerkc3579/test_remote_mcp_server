import os
import json
import logging
import time
from datetime import datetime
from fastmcp import FastMCP
from fastmcp.server.dependencies import get_access_token
import asyncpg
import redis.asyncio as redis

# --- Observability: Structured Logging ---
logger = logging.getLogger("expense_tracker")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
class JsonFormatter(logging.Formatter):
    def format(self, record):
        log_obj = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "message": record.getMessage(),
        }
        if hasattr(record, "user_id"): log_obj["user_id"] = record.user_id
        if hasattr(record, "tool"): log_obj["tool"] = record.tool
        if hasattr(record, "status"): log_obj["status"] = record.status
        if hasattr(record, "error_type"): log_obj["error_type"] = record.error_type
        return json.dumps(log_obj)

handler.setFormatter(JsonFormatter())
logger.addHandler(handler)

# --- Configuration ---
CATEGORIES_PATH = os.path.join(os.path.dirname(__file__), "categories.json")
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/expenses")
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

mcp = FastMCP("ExpenseTracker")

# --- Globals & Pools ---
db_pool = None
redis_client = None
_categories_cache = None

async def get_pool():
    global db_pool
    if db_pool is None:
        db_pool = await asyncpg.create_pool(DATABASE_URL, min_size=5, max_size=10)
    return db_pool

async def get_redis():
    global redis_client
    if redis_client is None:
        redis_client = redis.from_url(REDIS_URL)
    return redis_client

def get_current_user_id() -> str:
    token = get_access_token()
    if token and token.subject:
        return token.subject
    raise Exception("Authentication required: No valid OAuth token found. Please sign in.")

# --- Rate Limiting ---
async def check_rate_limit(user_id: str, tool_name: str):
    r = await get_redis()
    key = f"rate_limit:{user_id}"
    try:
        current = await r.incr(key)
        if current == 1:
            await r.expire(key, 60)
        if current > 30:
            raise Exception("Rate limit exceeded. Try again later.")
    except redis.ConnectionError:
        # Bypass rate limit gracefully if Redis goes down, but log the failure
        logger.warning("Redis connection failed, bypassing rate limit", extra={"user_id": user_id, "tool": tool_name})

# --- Validation ---
def get_categories():
    global _categories_cache
    if _categories_cache is None:
        try:
            with open(CATEGORIES_PATH, "r", encoding="utf-8") as f:
                _categories_cache = json.load(f)
        except FileNotFoundError:
            _categories_cache = {
                "categories": [
                    "Food & Dining", "Transportation", "Shopping", "Entertainment",
                    "Bills & Utilities", "Healthcare", "Travel", "Education",
                    "Business", "Other"
                ]
            }
    return _categories_cache

def validate_date(date_str: str):
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d")
        now = datetime.now()
        if (now.year - d.year) > 10:
            raise ValueError(f"Date {date_str} is too far in the past.")
        if (d.year - now.year) > 1:
            raise ValueError(f"Date {date_str} is too far in the future.")
    except ValueError as e:
        if "does not match format" in str(e):
            raise ValueError(f"Invalid date format: {date_str}. Expected YYYY-MM-DD")
        raise e

def validate_category(category: str):
    cats = get_categories()
    valid_categories = list(cats.keys())
    if "categories" in valid_categories and isinstance(cats["categories"], list):
        valid_categories = cats["categories"]
    if category not in valid_categories:
        raise ValueError(f"Invalid category: {category}. Valid options: {', '.join(valid_categories)}")

def validate_amount(amount: float):
    if amount <= 0:
        raise ValueError("Amount must be greater than 0.")
    if amount > 100_000_000:
        raise ValueError("Amount exceeds maximum allowed value.")

# --- Tools ---

def log_attempt(user_id, tool_name):
    logger.info(f"Executing {tool_name}", extra={"user_id": user_id, "tool": tool_name, "status": "started"})

def log_success(user_id, tool_name):
    logger.info(f"Successfully executed {tool_name}", extra={"user_id": user_id, "tool": tool_name, "status": "success"})

def log_error(user_id, tool_name, e):
    error_type = "database_error"
    if isinstance(e, ValueError):
        error_type = "validation_error"
    elif "Authentication required" in str(e):
        error_type = "auth_error"
    elif "Rate limit exceeded" in str(e):
        error_type = "rate_limit_error"
    
    logger.error(f"Error in {tool_name}: {str(e)}", extra={"user_id": user_id, "tool": tool_name, "status": "failed", "error_type": error_type})
    return {"status": "error", "message": str(e), "error_type": error_type}

@mcp.tool()
async def add_expense(date: str, amount: float, category: str, subcategory: str = "", note: str = ""):
    '''Add a new expense entry to the database.'''
    try:
        user_id = get_current_user_id()
        log_attempt(user_id, "add_expense")
        await check_rate_limit(user_id, "add_expense")
        
        validate_date(date)
        validate_category(category)
        validate_amount(amount)
        
        pool = await get_pool()
        async with pool.acquire() as conn:
            expense_id = await conn.fetchval(
                """
                INSERT INTO expenses(user_id, date, amount, category, subcategory, note) 
                VALUES ($1, $2, $3, $4, $5, $6)
                RETURNING id
                """,
                user_id, date, amount, category, subcategory, note
            )
            log_success(user_id, "add_expense")
            return {"status": "success", "id": expense_id, "message": "Expense added successfully"}
    except Exception as e:
        return log_error(locals().get("user_id", "unknown"), "add_expense", e)

@mcp.tool()
async def list_expenses(start_date: str, end_date: str, limit: int = 50, offset: int = 0):
    '''List expense entries within an inclusive date range. Use limit and offset for pagination.'''
    try:
        user_id = get_current_user_id()
        log_attempt(user_id, "list_expenses")
        
        validate_date(start_date)
        validate_date(end_date)
        
        pool = await get_pool()
        async with pool.acquire() as conn:
            records = await conn.fetch(
                """
                SELECT id, date, amount, category, subcategory, note
                FROM expenses
                WHERE user_id = $1 AND date BETWEEN $2 AND $3
                ORDER BY date DESC, id DESC
                LIMIT $4 OFFSET $5
                """,
                user_id, start_date, end_date, limit, offset
            )
            log_success(user_id, "list_expenses")
            return [dict(r) for r in records]
    except Exception as e:
        return log_error(locals().get("user_id", "unknown"), "list_expenses", e)

@mcp.tool()
async def summarize(start_date: str, end_date: str, category: str = None):
    '''Summarize expenses by category within an inclusive date range.'''
    try:
        user_id = get_current_user_id()
        log_attempt(user_id, "summarize")
        
        validate_date(start_date)
        validate_date(end_date)
        if category:
            validate_category(category)
            
        pool = await get_pool()
        async with pool.acquire() as conn:
            if category:
                query = """
                    SELECT category, SUM(amount) AS total_amount, COUNT(*) as count
                    FROM expenses
                    WHERE user_id = $1 AND date BETWEEN $2 AND $3 AND category = $4
                    GROUP BY category ORDER BY total_amount DESC
                """
                records = await conn.fetch(query, user_id, start_date, end_date, category)
            else:
                query = """
                    SELECT category, SUM(amount) AS total_amount, COUNT(*) as count
                    FROM expenses
                    WHERE user_id = $1 AND date BETWEEN $2 AND $3
                    GROUP BY category ORDER BY total_amount DESC
                """
                records = await conn.fetch(query, user_id, start_date, end_date)
                
            log_success(user_id, "summarize")
            return [dict(r) for r in records]
    except Exception as e:
        return log_error(locals().get("user_id", "unknown"), "summarize", e)

@mcp.tool()
async def update_expense(expense_id: int, amount: float = None, category: str = None, subcategory: str = None, note: str = None, date: str = None):
    '''Update an existing expense entry.'''
    try:
        user_id = get_current_user_id()
        log_attempt(user_id, "update_expense")
        await check_rate_limit(user_id, "update_expense")
        
        updates = []
        params = []
        param_idx = 1
        
        if date is not None:
            validate_date(date)
            updates.append(f"date = ${param_idx}")
            params.append(date)
            param_idx += 1
        if amount is not None:
            validate_amount(amount)
            updates.append(f"amount = ${param_idx}")
            params.append(amount)
            param_idx += 1
        if category is not None:
            validate_category(category)
            updates.append(f"category = ${param_idx}")
            params.append(category)
            param_idx += 1
        if subcategory is not None:
            updates.append(f"subcategory = ${param_idx}")
            params.append(subcategory)
            param_idx += 1
        if note is not None:
            updates.append(f"note = ${param_idx}")
            params.append(note)
            param_idx += 1
            
        if not updates:
            raise ValueError("No fields provided to update.")
            
        updates.append(f"updated_at = NOW()")
            
        query = f"UPDATE expenses SET {', '.join(updates)} WHERE id = ${param_idx} AND user_id = ${param_idx + 1}"
        params.extend([expense_id, user_id])
        
        pool = await get_pool()
        async with pool.acquire() as conn:
            status = await conn.execute(query, *params)
            updated_count = int(status.split()[-1])
            if updated_count == 0:
                raise Exception("Expense not found or you do not have permission to update it.")
            
            log_success(user_id, "update_expense")
            return {"status": "success", "message": "Expense updated successfully"}
    except Exception as e:
        return log_error(locals().get("user_id", "unknown"), "update_expense", e)

@mcp.tool()
async def delete_expense(expense_id: int):
    '''Delete an existing expense entry.'''
    try:
        user_id = get_current_user_id()
        log_attempt(user_id, "delete_expense")
        await check_rate_limit(user_id, "delete_expense")
        
        pool = await get_pool()
        async with pool.acquire() as conn:
            status = await conn.execute("DELETE FROM expenses WHERE id = $1 AND user_id = $2", expense_id, user_id)
            deleted_count = int(status.split()[-1])
            if deleted_count == 0:
                raise Exception("Expense not found or you do not have permission to delete it.")
            
            log_success(user_id, "delete_expense")
            return {"status": "success", "message": "Expense deleted successfully"}
    except Exception as e:
        return log_error(locals().get("user_id", "unknown"), "delete_expense", e)

@mcp.resource("expense:///categories", mime_type="application/json")
def categories():
    try:
        return json.dumps(get_categories(), indent=2)
    except Exception as e:
        return f'{{"error": "Could not load categories: {str(e)}"}}'

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    mcp.run(transport="sse", host="0.0.0.0", port=port)
