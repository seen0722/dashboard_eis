"""把所有 tool / resource 模組註冊到 MCPServer。新模組在這裡加一行。"""
from __future__ import annotations
from mcp.server.mcpserver import MCPServer
from ..state import ServerState
from . import admin, overview, project


def register_all(mcp: MCPServer, state: ServerState) -> None:
    admin.register(mcp, state)
    project.register(mcp, state)
    overview.register(mcp, state)
