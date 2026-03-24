"""
willow_store_mcp.py — MCP bridge for WillowStore (portless)
No ports. No server. stdin/stdout protocol only.
This IS the portless server — MCP talks to folders.
"""

import asyncio
import json
import sys
from pathlib import Path

# MCP SDK
try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    import mcp.types as types
except ImportError:
    print("MCP SDK not installed. Run: pip install mcp", file=sys.stderr)
    sys.exit(1)

# WillowStore
sys.path.insert(0, str(Path(__file__).parent))
from willow_store import WillowStore

# Default store location — override with WILLOW_STORE_ROOT env var
import os
STORE_ROOT = os.environ.get("WILLOW_STORE_ROOT", str(Path(__file__).parent / "merged_test"))

store = WillowStore(STORE_ROOT)
server = Server("willow-store")


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="store_put",
            description="Write a record to a collection. Append-only. Returns (id, action) where action is work_quiet/flag/stop from angular deviation rubric.",
            inputSchema={
                "type": "object",
                "properties": {
                    "collection": {"type": "string", "description": "e.g. knowledge/atoms, agents/shiva, feedback"},
                    "record": {"type": "object", "description": "The record data (JSON)"},
                    "record_id": {"type": "string", "description": "Optional. Auto-generated if omitted."},
                    "deviation": {"type": "number", "description": "Angular deviation (radians). 0=routine, pi/4=significant, pi/2=major, pi=reversal.", "default": 0.0},
                },
                "required": ["collection", "record"],
            },
        ),
        types.Tool(
            name="store_get",
            description="Read a single record by ID from a collection.",
            inputSchema={
                "type": "object",
                "properties": {
                    "collection": {"type": "string"},
                    "record_id": {"type": "string"},
                },
                "required": ["collection", "record_id"],
            },
        ),
        types.Tool(
            name="store_search",
            description="Text search within a collection.",
            inputSchema={
                "type": "object",
                "properties": {
                    "collection": {"type": "string"},
                    "query": {"type": "string"},
                },
                "required": ["collection", "query"],
            },
        ),
        types.Tool(
            name="store_search_all",
            description="Search across ALL collections. The 'go ask Willow' pattern.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                },
                "required": ["query"],
            },
        ),
        types.Tool(
            name="store_list",
            description="List all records in a collection.",
            inputSchema={
                "type": "object",
                "properties": {
                    "collection": {"type": "string"},
                },
                "required": ["collection"],
            },
        ),
        types.Tool(
            name="store_update",
            description="Update an existing record. Audit-trailed.",
            inputSchema={
                "type": "object",
                "properties": {
                    "collection": {"type": "string"},
                    "record_id": {"type": "string"},
                    "record": {"type": "object"},
                    "deviation": {"type": "number", "default": 0.0},
                },
                "required": ["collection", "record_id", "record"],
            },
        ),
        types.Tool(
            name="store_delete",
            description="Soft-delete a record. Invisible to search/get but audit-trailed.",
            inputSchema={
                "type": "object",
                "properties": {
                    "collection": {"type": "string"},
                    "record_id": {"type": "string"},
                },
                "required": ["collection", "record_id"],
            },
        ),
        types.Tool(
            name="store_add_edge",
            description="Add an edge to the knowledge graph.",
            inputSchema={
                "type": "object",
                "properties": {
                    "from_id": {"type": "string"},
                    "to_id": {"type": "string"},
                    "relation": {"type": "string"},
                    "context": {"type": "string", "default": ""},
                },
                "required": ["from_id", "to_id", "relation"],
            },
        ),
        types.Tool(
            name="store_edges_for",
            description="Get all edges involving a record.",
            inputSchema={
                "type": "object",
                "properties": {
                    "record_id": {"type": "string"},
                },
                "required": ["record_id"],
            },
        ),
        types.Tool(
            name="store_stats",
            description="Collection counts and trajectory scores.",
            inputSchema={"type": "object", "properties": {}},
        ),
        types.Tool(
            name="store_audit",
            description="Read recent audit log for a collection.",
            inputSchema={
                "type": "object",
                "properties": {
                    "collection": {"type": "string"},
                    "limit": {"type": "integer", "default": 20},
                },
                "required": ["collection"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    try:
        if name == "store_put":
            rid, action = store.put(
                arguments["collection"],
                arguments["record"],
                record_id=arguments.get("record_id"),
                deviation=arguments.get("deviation", 0.0),
            )
            result = {"id": rid, "action": action}

        elif name == "store_get":
            result = store.get(arguments["collection"], arguments["record_id"])
            if result is None:
                result = {"error": "not_found"}

        elif name == "store_search":
            result = store.search(arguments["collection"], arguments["query"])

        elif name == "store_search_all":
            result = store.search_all(arguments["query"])

        elif name == "store_list":
            result = store.all(arguments["collection"])

        elif name == "store_update":
            rid, action = store.update(
                arguments["collection"],
                arguments["record_id"],
                arguments["record"],
                deviation=arguments.get("deviation", 0.0),
            )
            result = {"id": rid, "action": action}

        elif name == "store_delete":
            ok = store.delete(arguments["collection"], arguments["record_id"])
            result = {"deleted": ok}

        elif name == "store_add_edge":
            rid, action = store.add_edge(
                arguments["from_id"],
                arguments["to_id"],
                arguments["relation"],
                context=arguments.get("context", ""),
            )
            result = {"id": rid, "action": action}

        elif name == "store_edges_for":
            result = store.edges_for(arguments["record_id"])

        elif name == "store_stats":
            result = store.stats()

        elif name == "store_audit":
            result = store.audit_log(
                arguments["collection"],
                limit=arguments.get("limit", 20),
            )

        else:
            result = {"error": f"Unknown tool: {name}"}

        return [types.TextContent(type="text", text=json.dumps(result, indent=2, default=str))]

    except Exception as e:
        return [types.TextContent(type="text", text=json.dumps({"error": str(e)}))]


async def main():
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
