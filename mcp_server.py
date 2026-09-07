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

# 预热本地 embedding 模型（2026-09-07 实测修复）
# ⚠️ run() 事件循环内首次加载 onnxruntime session 实测耗时 30s+，
# 超过客户端工具超时 → flythings_search 首次调用必失败（表现为 search 卡死/超时）。
# 启动前预热仅 ~0.2s，session 就绪后检索全程 <0.1s。
# 模型缺失/加载失败时静默跳过，检索自动降级 BM25，不影响启动。
try:
    import embed_local
    if embed_local.available():
        embed_local.embed('__prewarm__')
except Exception:
    pass

if __name__ == '__main__':
    mcp.run()
