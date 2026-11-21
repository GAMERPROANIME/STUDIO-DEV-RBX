"""OMNIBRIDGE Studio Bridge — Web AI ↔ Python ↔ official Roblox Studio MCP.

Architecture (ZeroScript-inspired, independently implemented):

    Web AI page
      │  (browser extension: provider adapter, command parser, agent loop)
      ▼  ws://127.0.0.1:17613  (extension service worker)
    Python Bridge  ← the brain: auth, validation, permissions, audit, retries
      │  MCP over stdio (official Python SDK client)
      ▼
    Official Roblox Studio MCP server  (cmd.exe /c %LOCALAPPDATA%\\Roblox\\mcp.bat …)
      │
      ▼
    Roblox Studio

The bridge never re-implements Roblox tooling: it discovers the real tools exposed by
the Studio MCP server and forwards calls. Python owns lifecycle, security and state.
"""
from __future__ import annotations

__all__ = ["__version__"]

__version__ = "1.0.0"
