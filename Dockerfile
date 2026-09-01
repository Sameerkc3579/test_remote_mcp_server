FROM python:3.11-slim

WORKDIR /app

# Install uv for fast dependency resolution
RUN pip install uv

# Copy project files
COPY pyproject.toml .
COPY categories.json .
COPY main.py .
COPY alembic.ini .
COPY alembic ./alembic

# Install dependencies using uv
RUN uv pip install --system aiosqlite alembic asyncpg fastmcp redis sqlalchemy

# Expose port
EXPOSE 8000

# Start server
CMD ["python", "main.py"]
