# Expense Tracker MCP Server

A FastMCP server that allows Claude Desktop to securely track, list, and summarize your personal expenses.

## How it works

This server is deployed publicly on Render and uses Server-Sent Events (SSE) to connect with MCP clients like Claude Desktop. It stores expenses in a centralized database but **strictly partitions data based on your email address**.

## How to Connect Claude Desktop

Because Claude Desktop natively expects to communicate over standard input/output (`stdio`), and this server is hosted remotely over SSE, you need to use a small bridge proxy called `mcp-remote`.

### Prerequisites
1. **Claude Desktop App**
2. **Node.js** (Required to run the proxy bridge. Download from [nodejs.org](https://nodejs.org/)).

### Configuration Setup
1. Open your Claude Desktop configuration file:
   - **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`
   - **Mac:** `~/Library/Application Support/Claude/claude_desktop_config.json`
2. Add the `sameers-expense-tracker` to the `mcpServers` list:

```json
{
  "mcpServers": {
    "sameers-expense-tracker": {
      "command": "npx",
      "args": [
        "-y",
        "mcp-remote",
        "https://test-remote-mcp-server-xf2s.onrender.com/sse"
      ]
    }
  }
}
```
3. Save the file and **completely restart Claude Desktop**.

## How to use it in Claude

When you start a new conversation with Claude, the server requires an email address for authentication and partitioning. **If you do not specify your email, Claude will fail to access your expenses.**

### 1. Register your email in the chat
At the start of your conversation, explicitly tell Claude your unique email address:
> *"Hey Claude, my email is [your-unique-email@gmail.com]. Please use this for tracking my expenses."*

### 2. Available Commands
Once Claude knows your email, you can ask it to:
- **Add expenses:** *"Add a $15 cab ride expense for today."*
- **List expenses:** *"What were my expenses for last week?"*
- **Summarize expenses:** *"Give me a summary of my food expenses for September."*
- **Update/Delete:** *"Delete that cab ride expense."*

**Security Note:** 
To prevent Claude from hallucinating and unintentionally mixing your data with others, the server strictly refuses any database operation unless a valid email is explicitly provided by the AI during the tool call. It is important to always explicitly provide your unique email to Claude.
