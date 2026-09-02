import asyncio
import asyncpg
import getpass

async def test_conn():
    user = getpass.getuser()
    urls = [
        'postgresql://localhost:5432/expenses',
        'postgresql://postgres@localhost:5432/expenses',
        f'postgresql://{user}@localhost:5432/expenses',
        f'postgresql://{user}:password@localhost:5432/expenses'
    ]
    for url in urls:
        try:
            conn = await asyncpg.connect(url)
            print(f"SUCCESS with {url}")
            await conn.close()
            return
        except Exception as e:
            print(f"Failed {url}: {e}")

asyncio.run(test_conn())
