import asyncio, aiosqlite, traceback
async def test():
    try:
        async with aiosqlite.connect('data/expenses.db') as c:
            await c.execute("INSERT INTO expenses(user_id, date, amount, category, subcategory, note) VALUES ('t', '2026-09-01', 10, 'food', '', '')")
            await c.commit()
            print('Success')
    except Exception as e:
        traceback.print_exc()
asyncio.run(test())
