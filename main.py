from fastmcp import FastMCP
from fastmcp.server.dependencies import get_access_token
import os
import aiosqlite
import subprocess
import json
from datetime import datetime

# Use a data directory within the project
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, "expenses.db")
CATEGORIES_PATH = os.path.join(os.path.dirname(__file__), "categories.json")

print(f"Database path: {DB_PATH}")

mcp = FastMCP("ExpenseTracker")

def get_current_user_id() -> str:
    token = get_access_token()
    if token and token.subject:
        return token.subject
    return "local_test_user"

def init_db():
    try:
        print("Running database migrations...")
        subprocess.run(["alembic", "upgrade", "head"], check=True, cwd=os.path.dirname(__file__))
        print("Database initialized successfully")
    except Exception as e:
        print(f"Database initialization error: {e}")
        # Note: Do not raise here so the MCP server can still start if alembic fails
        
# Initialize database synchronously at module load
init_db()

def get_categories():
    try:
        with open(CATEGORIES_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {
            "categories": [
                "Food & Dining",
                "Transportation",
                "Shopping",
                "Entertainment",
                "Bills & Utilities",
                "Healthcare",
                "Travel",
                "Education",
                "Business",
                "Other"
            ]
        }

def validate_date(date_str: str):
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        raise ValueError(f"Invalid date format: {date_str}. Expected YYYY-MM-DD")

def validate_category(category: str):
    cats = get_categories()
    valid_categories = list(cats.keys())
    if "categories" in valid_categories and isinstance(cats["categories"], list):
        valid_categories = cats["categories"]
    if category not in valid_categories:
        raise ValueError(f"Invalid category: {category}. Valid options: {', '.join(valid_categories)}")

@mcp.tool()
async def add_expense(date, amount, category, subcategory="", note=""):  # Changed: added async
    '''Add a new expense entry to the database.'''
    user_id = get_current_user_id()
    try:
        validate_date(date)
        validate_category(category)
        async with aiosqlite.connect(DB_PATH) as c:  # Changed: added async
            cur = await c.execute(  # Changed: added await
                "INSERT INTO expenses(user_id, date, amount, category, subcategory, note) VALUES (?,?,?,?,?,?)",
                (user_id, date, amount, category, subcategory, note)
            )
            expense_id = cur.lastrowid
            await c.commit()  # Changed: added await
            return {"status": "success", "id": expense_id, "message": "Expense added successfully"}
    except Exception as e:  # Changed: simplified exception handling
        if "readonly" in str(e).lower():
            return {"status": "error", "message": "Database is in read-only mode. Check file permissions."}
        return {"status": "error", "message": f"Database error: {str(e)}"}
    
@mcp.tool()
async def list_expenses(start_date, end_date, limit: int = 50, offset: int = 0):
    '''List expense entries within an inclusive date range. Use limit and offset for pagination.'''
    user_id = get_current_user_id()
    try:
        validate_date(start_date)
        validate_date(end_date)
        async with aiosqlite.connect(DB_PATH) as c:  # Changed: added async
            cur = await c.execute(  # Changed: added await
                """
                SELECT id, date, amount, category, subcategory, note
                FROM expenses
                WHERE user_id = ? AND date BETWEEN ? AND ?
                ORDER BY date DESC, id DESC
                LIMIT ? OFFSET ?
                """,
                (user_id, start_date, end_date, limit, offset)
            )
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r)) for r in await cur.fetchall()]  # Changed: added await
    except Exception as e:
        return {"status": "error", "message": f"Error listing expenses: {str(e)}"}

@mcp.tool()
async def summarize(start_date, end_date, category=None):  # Changed: added async
    '''Summarize expenses by category within an inclusive date range.'''
    user_id = get_current_user_id()
    try:
        validate_date(start_date)
        validate_date(end_date)
        if category:
            validate_category(category)
        async with aiosqlite.connect(DB_PATH) as c:  # Changed: added async
            query = """
                SELECT category, SUM(amount) AS total_amount, COUNT(*) as count
                FROM expenses
                WHERE user_id = ? AND date BETWEEN ? AND ?
            """
            params = [user_id, start_date, end_date]

            if category:
                query += " AND category = ?"
                params.append(category)

            query += " GROUP BY category ORDER BY total_amount DESC"

            cur = await c.execute(query, params)  # Changed: added await
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r)) for r in await cur.fetchall()]  # Changed: added await
    except Exception as e:
        return {"status": "error", "message": f"Error summarizing expenses: {str(e)}"}

@mcp.tool()
async def update_expense(expense_id: int, amount: float = None, category: str = None, subcategory: str = None, note: str = None, date: str = None):
    '''Update an existing expense entry.'''
    user_id = get_current_user_id()
    
    updates = []
    params = []
    
    if date is not None:
        validate_date(date)
        updates.append("date = ?")
        params.append(date)
    if amount is not None:
        updates.append("amount = ?")
        params.append(amount)
    if category is not None:
        validate_category(category)
        updates.append("category = ?")
        params.append(category)
    if subcategory is not None:
        updates.append("subcategory = ?")
        params.append(subcategory)
    if note is not None:
        updates.append("note = ?")
        params.append(note)
        
    if not updates:
        return {"status": "error", "message": "No fields provided to update."}
        
    query = f"UPDATE expenses SET {', '.join(updates)} WHERE id = ? AND user_id = ?"
    params.extend([expense_id, user_id])
    
    try:
        async with aiosqlite.connect(DB_PATH) as c:
            cur = await c.execute(query, tuple(params))
            if cur.rowcount == 0:
                return {"status": "error", "message": "Expense not found or you do not have permission to update it."}
            await c.commit()
            return {"status": "success", "message": "Expense updated successfully"}
    except Exception as e:
        return {"status": "error", "message": f"Database error: {str(e)}"}

@mcp.tool()
async def delete_expense(expense_id: int):
    '''Delete an existing expense entry.'''
    user_id = get_current_user_id()
    try:
        async with aiosqlite.connect(DB_PATH) as c:
            cur = await c.execute("DELETE FROM expenses WHERE id = ? AND user_id = ?", (expense_id, user_id))
            if cur.rowcount == 0:
                return {"status": "error", "message": "Expense not found or you do not have permission to delete it."}
            await c.commit()
            return {"status": "success", "message": "Expense deleted successfully"}
    except Exception as e:
        return {"status": "error", "message": f"Database error: {str(e)}"}

@mcp.resource("expense:///categories", mime_type="application/json")  # Changed: expense:// → expense:///
def categories():
    try:
        return json.dumps(get_categories(), indent=2)
    except Exception as e:
        return f'{{"error": "Could not load categories: {str(e)}"}}'

# Start the server
if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=8000)
    # mcp.run()
