# -*- coding: utf-8 -*-
"""MCP server (stdio, fastmcp): FlyThings knowledge base full toolset.

OpenClaw 注册入口。工具定义见 kb_tools.py。

⚠️ 分发器走**自建 OPS 注册表**（kb_tools.OP_NAMES），不反射 FastMCP 私有属性
（`mcp._tool_manager._tools` 是内部结构，SDK 一升级就炸）。

工具面模式（v0.27.34，环境变量 FLYTHINGS_MCP_MODE，默认 dispatcher）：
  - `dispatcher`（默认）：**只暴露 1 个工具** flythings_kb（op="list" 取目录）——schema 开销最小，
    推荐所有客户端用（外部工具目录由意图闸门/README 提供）；
  - `all`：1 个分发器 + 46 个独立工具（老配置兼容，客户端可直接调 `flythings_knowledge_search` 这类名字）；
  - `flat`：只注册 46 个独立工具（等价 mcp_server_flat.py，给需要独立 schema 的客户端）。
⚠️ 默认值从“全注册”改为“只分发器”是**行为变更**（v0.27.34）：如你的客户端/提示词直接调用
flat 工具名，设 FLYTHINGS_MCP_MODE=all 即可恢复原行为。
"""
import os, sys, json, inspect

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mcp.server.fastmcp import FastMCP
import kb_tools
import mcp_extras

MODE = (os.environ.get('FLYTHINGS_MCP_MODE') or 'dispatcher').strip().lower()
if MODE not in ('dispatcher', 'all', 'flat'):
    MODE = 'dispatcher'

mcp = FastMCP("flythings-kb")
# 'dispatcher'：不注册独立工具（只有下面的 flythings_kb）；'all' / 'flat'：注册 46 个独立工具
if MODE in ('all', 'flat'):
    kb_tools.register_all(mcp)
# resources + prompts（与工具面模式无关，两种 server 共用同一实现 mcp_extras）
mcp_extras.register(mcp)

# {op 名 -> 已统一 envelope 包装的函数}；与注册清单同源，无私有属性反射
OPS = {}
for _name in kb_tools.OP_NAMES:
    _fn = getattr(kb_tools, _name, None)
    if callable(_fn):
        OPS[_name] = _fn


def _brief(fn) -> str:
    doc = (getattr(fn, '__doc__', '') or '').strip()
    return (doc.splitlines()[0] if doc else '')[:90]


def _args_of(fn) -> list:
    try:
        return [p.name for p in inspect.signature(fn).parameters.values()
                if p.name not in ('ctx', 'self')]
    except (TypeError, ValueError):
        return []


def _catalog() -> str:
    ops = [{"op": n, "brief": _brief(f), "args": _args_of(f)}
           for n, f in sorted(OPS.items())]
    return json.dumps({"count": len(ops), "ops": ops}, ensure_ascii=False)


def _suggest(op: str, limit: int = 5) -> list:
    """未知名 op 的可机读候选：①合并/改名的旧名 → 直接给新名 ②按名字片段打分排序。"""
    key = (op or '').lower()
    out = []
    try:
        import kb_tools as _kb
        if key in getattr(_kb, 'RENAMED', {}):
            out.append(_kb.RENAMED[key])
    except Exception:
        pass
    toks = [t for t in key.replace('-', '_').split('_') if len(t) > 2 and t != 'flythings']
    scored = []
    for n in sorted(OPS):
        score = 0
        if key and (key in n or n in key):
            score += 3
        score += sum(2 for t in toks if t in n)
        if score:
            scored.append((-score, len(n), n))
    scored.sort()
    for _, _, n in scored:
        if n not in out:
            out.append(n)
        if len(out) >= limit:
            break
    return out[:limit]


def _env_err(code, msg, hint='', retryable=False) -> str:
    return json.dumps({"ok": False,
                       "error": {"code": code, "msg": msg, "hint": hint,
                                 "retryable": bool(retryable)}},
                      ensure_ascii=False)


async def flythings_kb(op: str = "list", args: str = "{}") -> str:
    """FlyThings 开发能力统一入口（46 个能力合一的单入口）。

    ⚠️ 仅在用户意图属于「FlyThings 软件开发」时调用：UI 布局/控件/json/ftu、
    工程创建与编译部署、依赖包/Manifest、多语言 i18n、知识库检索、UI 预览与像素验收、
    真机截图、资源生成、自动化测试。其他话题（闲聊、文档、其他产品）不要调用。

    用法：先传 op="list" 取全部可用操作及其参数名，再用 op=<操作名> + args='{"参数": 值}'
    （args 传 JSON 字符串；部分客户端只支持对象，也可直接传 dict）。

    ⚠️ 能力不止这 46 个 op：设备端预编译工具（touch 触摸注入 / busybox / ui_test /
    zkshot）在 `<MCP 安装目录>/bin_tools/<平台>/` 下，**不是 op、不占 op 名额**——
    只数 op 会漏掉触摸注入这类能力；看 flythings_get_version 的 binTools 字段或
    flythings://tools 资源的「设备端预编译工具」一节。
    """
    if op in ("", "list", "help", "?"):
        return _catalog()
    fn = OPS.get(op)
    if fn is None:
        try:
            import kb_tools as _kb
            renamed = _kb.RENAMED.get(op)
        except Exception:
            renamed = None
        if renamed:
            try:
                extra = kb_tools.RENAMED_HINT.get(renamed, '')
            except Exception:
                extra = ''
            hint = '直接改用 %s（旧名不再提供）' % renamed
            if extra:
                hint += '；' + extra
            return json.dumps({"ok": False,
                               "error": {"code": "OP_RENAMED",
                                         "msg": "op %s 已合并/改名为 %s" % (op, renamed),
                                         "hint": hint,
                                         "retryable": False}},
                              ensure_ascii=False)
        return json.dumps({"ok": False,
                           "error": {"code": "UNKNOWN_OP",
                                     "msg": "unknown op: %s" % op,
                                     "hint": "调 op='list' 取全部 op 与参数名；或见 candidates",
                                     "retryable": False},
                           "candidates": _suggest(op)}, ensure_ascii=False)
    if isinstance(args, dict):
        kwargs = dict(args)
    else:
        try:
            kwargs = json.loads(args) if args and str(args).strip() else {}
        except Exception as e:
            return _env_err("BAD_ARGS", "args 不是合法 JSON: %s" % e,
                            "args 传 JSON 对象字符串，如 '{\"project_root\": \"...\"}'；"
                            "也可直接传对象。参数名见 op='list'", True)
        if not isinstance(kwargs, dict):
            return _env_err("BAD_ARGS",
                            "args 必须是 JSON 对象（当前是 %s）" % type(kwargs).__name__,
                            "参数名见 op='list'", True)
    try:
        res = fn(**kwargs)
        if inspect.isawaitable(res):
            res = await res
        return res if isinstance(res, str) else json.dumps(res, ensure_ascii=False, default=str)
    except TypeError as e:
        # 参数名/个数不对 → 回正确签名，AI 可直接改
        return _env_err("BAD_PARAMS", "%s: %s" % (type(e).__name__, e),
                        "本 op 正确签名: %s(%s)" % (op, ', '.join(_args_of(fn))), True)
    except Exception as e:
        return _env_err(type(e).__name__, str(e))


def main():
    """console_scripts 入口（pyproject.toml: flythings-mcp = mcp_server:main）。"""
    mcp.run()


# 注册分发器（MODE=flat 时不注册：那种模式语义 =「只要 46 个独立工具」，见 mcp_server_flat.py）
if MODE != 'flat':
    mcp.tool()(flythings_kb)


# 预热本地 embedding 模型（2026-09-07 实测修复）
# ⚠️ run() 事件循环内首次加载 onnxruntime session 实测耗时 30s+，
# 超过客户端工具超时 → 首次检索调用必失败（表现为 search 卡死/超时）。
# 启动前预热仅 ~0.2s，session 就绪后检索全程 <0.1s。
# 模型缺失/加载失败时跳过，检索自动降级 BM25，不影响启动。
try:
    import embed_local
    if embed_local.available():
        embed_local.embed('__prewarm__')
except Exception:
    pass

if __name__ == '__main__':
    main()
