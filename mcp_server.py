# -*- coding: utf-8 -*-
"""MCP server (stdio, fastmcp): FlyThings knowledge base full toolset.
OpenClaw 注册入口。工具定义见 kb_tools.py。
"""
import os, sys, json, inspect

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mcp.server.fastmcp import FastMCP
import kb_tools

mcp = FastMCP("flythings-kb")
kb_tools.register_all(mcp)


def _tool_map():
    """已注册工具 name -> Tool 对象。"""
    tm = getattr(mcp, "_tool_manager", None)
    tools = getattr(tm, "_tools", None) if tm is not None else None
    return tools if isinstance(tools, dict) else {}


def _catalog() -> str:
    ops = []
    for name in sorted(_tool_map()):
        if name == "flythings_kb":
            continue
        t = _tool_map()[name]
        first = (getattr(t, "description", "") or "").strip().splitlines()
        brief = (first[0] if first else "")[:90]
        try:
            args = [
                p.name
                for p in inspect.signature(t.fn).parameters.values()
                if p.name not in ("ctx", "self")
            ]
        except Exception:
            args = []
        ops.append({"op": name, "brief": brief, "args": args})
    return json.dumps({"count": len(ops), "ops": ops}, ensure_ascii=False)


@mcp.tool()
async def flythings_kb(op: str = "list", args: str = "{}") -> str:
    """FlyThings 开发能力统一入口（36 个能力合一的单入口）。

    ⚠️ 仅在用户意图属于「FlyThings 软件开发」时调用：UI 布局/控件/json/ftu、
    工程创建与编译部署、依赖包/Manifest、多语言 i18n、知识库检索、UI 预览与像素验收、
    真机截图、资源生成、自动化测试。其他话题（闲聊、文档、其他产品）不要调用。

    用法：先传 op="list" 取全部可用操作及其参数名，再用 op=<操作名> + args='{"参数": 值}'。
    """
    if op in ("", "list", "help", "?"):
        return _catalog()
    tool = _tool_map().get(op)
    if tool is None:
        return json.dumps(
            {"ok": False, "error": "unknown op: %s" % op, "hint": "call op='list'"},
            ensure_ascii=False,
        )
    try:
        kwargs = json.loads(args) if args and args.strip() else {}
        if not isinstance(kwargs, dict):
            raise ValueError("args must be a JSON object")
    except Exception as e:
        return json.dumps({"ok": False, "error": "bad args: %s" % e}, ensure_ascii=False)
    try:
        res = tool.fn(**kwargs)
        if inspect.isawaitable(res):
            res = await res
        return res if isinstance(res, str) else json.dumps(res, ensure_ascii=False, default=str)
    except Exception as e:
        return json.dumps(
            {"ok": False, "op": op, "error": "%s: %s" % (type(e).__name__, e)},
            ensure_ascii=False,
        )

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
