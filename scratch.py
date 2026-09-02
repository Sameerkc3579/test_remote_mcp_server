import asyncio
import asyncpg

async def run():
    conn = await asyncpg.connect('postgresql://postgres:postgres@localhost:5432/expenses')
    rows = await conn.fetch('SELECT * FROM expenses')
    for r in rows:
        print(dict(r))
    await conn.close()

if __name__ == "__main__":
    asyncio.run(run())
