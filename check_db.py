import asyncio
import asyncpg
import traceback

async def run():
    passwords = ["postgres", "password", "admin", "root", "123456", ""]
    for p in passwords:
        try:
            conn = await asyncpg.connect(f'postgresql://postgres:{p}@localhost:5432/expenses')
            print(f"SUCCESS with password: '{p}'")
            await conn.close()
            return
        except asyncpg.exceptions.InvalidPasswordError:
            print(f"Failed with '{p}'")
        except Exception as e:
            print(f"Other error with '{p}': {type(e)}")

asyncio.run(run())
