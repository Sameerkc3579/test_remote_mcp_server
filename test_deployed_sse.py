import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.sse import sse_client

async def test_server():
    url = "https://test-remote-mcp-server-xf2s.onrender.com/sse"
    print(f"Connecting to {url}...")
    try:
        async with sse_client(url) as streams:
            async with ClientSession(streams[0], streams[1]) as session:
                await session.initialize()
                print("Successfully initialized session!")
                tools = await session.list_tools()
                print("Available tools:")
                for tool in tools.tools:
                    print(f"- {tool.name}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_server())
