# Willow MCP Server

Exposes Willow's capabilities to Claude Desktop and Claude Code (Ganesha) via the Model Context Protocol.

## Tools

| Tool | Description |
|------|-------------|
| `willow_status` | Check Willow skill-layer health |
| `willow_query` | Search knowledge base (quick) |
| `willow_journal` | Add a continuity ring journal entry |
| `willow_persona` | Invoke a Willow persona (PA, Analyst, etc.) |
| `willow_speak` | TTS via Willow router |
| `willow_route` | Route a file through Willow for LLM analysis |
| `willow_agents` | List registered agents + trust levels |
| `willow_chat` | Chat with a specific agent (kart, shiva, etc.) |
| `willow_knowledge_search` | Full knowledge search with metadata |
| `willow_knowledge_ingest` | Add document/text to knowledge base |
| `willow_system_status` | Full system status (DB, daemons, tunnel, workers) |
| `willow_governance` | View pending governance proposals |

## Configuration

Set `WILLOW_URL` env var to override the default base URL (`http://127.0.0.1:8420`).

---

## Claude Code (WSL / Ganesha)

Added at user scope via:
```bash
claude mcp add --scope user willow -- /home/sean/.willow-venv/bin/python \
  /mnt/c/Users/Sean/Documents/GitHub/Willow/mcp/willow_server.py
```

Verify with:
```bash
claude mcp list
```

---

## Claude Desktop (Windows)

Add to `%APPDATA%\Claude\claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "willow": {
      "command": "C:\\Python314\\python.exe",
      "args": ["C:\\Users\\Sean\\Documents\\GitHub\\Willow\\mcp\\willow_server.py"]
    }
  }
}
```

Or via WSL Python (if Claude Desktop supports WSL invocation):

```json
{
  "mcpServers": {
    "willow": {
      "command": "wsl",
      "args": ["/home/sean/.willow-venv/bin/python", "/mnt/c/Users/Sean/Documents/GitHub/Willow/mcp/willow_server.py"]
    }
  }
}
```

Restart Claude Desktop after editing.

---

## Verification

After restarting Claude Code:

```
/mcp                    # Show MCP server status
willow_status           # Returns Willow skill-layer health
willow_system_status    # Full system health (DB, daemons, workers)
willow_agents           # Lists Ganesha, Kart, Shiva, etc.
willow_knowledge_search # query="what is Willow?"
willow_chat             # agent=kart, message="hello"
```
