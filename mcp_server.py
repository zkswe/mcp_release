# -*- coding: utf-8 -*-
"""MCP server (stdio, fastmcp): FlyThings knowledge base full toolset.
OpenClaw 注册入口。工具定义见 kb_tools.py。
"""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mcp.server.fastmcp import FastMCP
import kb_tools

mcp = FastMCP("flythings-kb")
kb_tools.register_all(mcp)

if __name__ == '__main__':
    mcp.run()
