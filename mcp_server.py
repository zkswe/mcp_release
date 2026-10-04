# -*- coding: utf-8 -*-
"""MCP server (stdio, fastmcp): FlyThings knowledge base full toolset.

OpenClaw 注册入口。工具定义见 kb_tools.py。

⚠️ 分发器走**自建 OPS 注册表**（kb_tools.OP_NAMES），不反射 FastMCP 私有属性
（`mcp._tool_manager._tools` 是内部结构，SDK 一升级就炸）。

工具面模式（v0.27.34，环境变量 FLYTHINGS_MCP_MODE，默认 dispatcher）：
  - `dispatcher`（默认）：**只暴露 1 个工具** flythings_kb（op="list" 取目录）——schema 开销最小，
    推荐所有客户端用（外部工具目录由意图闸门/README 提供）；
  - `all`：1 个分发器 + 48 个独立工具（老配置兼容，客户端可直接调 `flythings_knowledge_search` 这类名字）；
  - `flat`：只注册 48 个独立工具（等价 mcp_server_flat.py，给需要独立 schema 的客户端）。
⚠️ 默认值从“全注册”改为“只分发器”是**行为变更**（v0.27.34）：如你的客户端/提示词直接调用
flat 工具名，设 FLYTHINGS_MCP_MODE=all 即可恢复原行为。
"""
import os, sys, json, inspect

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mcp.server.fastmcp import Context, FastMCP
import error_codes_loader as errcodes   # 错误码语义（域⑫）
import kb_tools
import mcp_extras

MODE = (os.environ.get('FLYTHINGS_MCP_MODE') or 'dispatcher').strip().lower()
if MODE not in ('dispatcher', 'all', 'flat'):
    MODE = 'dispatcher'

mcp = FastMCP("flythings-kb")
# 'dispatcher'：不注册独立工具（只有下面的 flythings_kb）；'all' / 'flat'：注册 48 个独立工具
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


def _find(need: str, limit: int = 6) -> str:
    """**分级筛选**：用户需求原话 → 候选 op + 关联知识指针（不谈参数、不拉契约）。

    为什么要有它（2026-10-03 架构）：工具面分三层，但"选哪个 op"这一步原先只能让 AI
    读 47 条 description 自己挑 —— 那是把上下文预算花在"选"上。这里按**触发词**先筛一道：

      第一级 `stage` —— 这条需求落在哪个阶段（design/build/other），先缩小到一组；
      第二级 `candidates` —— 组内按**用户会怎么说的触发词**打分排序，带命中理由；
      第三级 `knowledge` —— 候选 op 关联的知识页（`docRef`），调用中要深入时直接去检索。

    选中之后：`op="describe:<名>"` 拉完整契约（流程/铁律），再 `op=<名>` + args 调用。
    """
    q = (need or '').strip()
    out = {"ok": True, "need": q, "count": 0, "stage": '', "candidates": [],
           "hint": '选中后 op="describe:<名>" 拉完整契约；再 op=<名> + args 调用；'
                   '要深入某条判据用 op="knowledge_search"。',
           "knowledge": []}
    if not q:
        out["ok"] = False
        out["hint"] = '把用户原话放进 op="find:<需求原话>"（例：op="find:把界面推到设备上跑一下"）'
        return json.dumps(out, ensure_ascii=False)
    try:
        import op_spec_loader as osl
        ops = osl.registered()
        import kb_authority as ka          # 匹配器**唯一实现**（容忍中间插词，与知识权威归属同一份）
    except Exception as e:                       # 注册表不可用 → 明说，别给空候选让人以为"没这个能力"
        return _err_json("CONTRACT_UNAVAILABLE",
                         "op 契约注册表不可用: %s: %s" % (type(e).__name__, e))
    scored = []
    ex_hits = {}                                 # op → 出局词（命中即出局，见下 ①d）
    # ② 语义补一路：走**已有的知识检索**（本地向量 + BM25，已评测、有回归），
    #    命中文档 → 反查"哪些 op 以它为 docRef / seeAlso"（两跳，**不新造索引**）。
    #    为什么需要它：「屏比设计小怎么办」这种口语，字面触发词一条都命中不了，
    #    但知识库里就是那篇判据页（实测 top-1 = device-preflight-spec.md）。
    doc2ops = {}
    for op in ops:
        s = osl.spec(op)
        for d in ([s.get('docRef')] if s.get('docRef') else []) + list(s.get('seeAlso') or []):
            doc2ops.setdefault(d, []).append(op)
    sem_ops, sem_docs = {}, []
    try:
        import rag_search as _rs
        for rank, item in enumerate(_rs.search(q, k=3) or []):
            _sc, h = (item if isinstance(item, (list, tuple)) else (0, item))
            p = (h or {}).get('path') or ''
            if p and p not in sem_docs:
                sem_docs.append(p)
            if rank > 1:                          # 只认前两名（实测 0.027~0.033 同档，
                continue                          # 分数分不出信号/噪声，靠**名次**而不是分数）
            for op in doc2ops.get(p, []):
                sem_ops[op] = max(sem_ops.get(op, 0), 6 - 3 * rank)
    except Exception as e:                       # 检索不可用不阻断字面匹配，但如实回报
        out['semanticError'] = '%s: %s' % (type(e).__name__, e)
    for op in ops:
        s = osl.spec(op)
        score, hits = 0, []
        ex = osl.exclude_hit(op, q)              # ①d 出局词（见下）
        if ex:
            ex_hits[op] = ex
        for t in (s.get('triggers') or []):      # ① 触发词：子串/滑窗（权重最高）
            h = ka.alias_hit(t, q) if t else 0
            if h:
                score += 2 * h
                hits.append(t)
            elif t and ka.weak_chars_hit(t, q):  # 弱命中：短词够不着滑窗阈值时的兜底
                score += 1
                hits.append(t)
        for k in (s.get('keywords') or []):      # ①b 检索词：有人按术语问
            h = ka.alias_hit(k, q) if k else 0
            if h:
                score += h
                hits.append(k)
        for frag in (op.replace('flythings_', '').split('_') +      # ①c op 名片段（弱信号）
                     [w for w in (s.get('summary') or '').replace('（', ' ').split()[:6]]):
            if len(frag) >= 2 and ka.alias_hit(frag, q):
                score += 1
                hits.append(frag)
        if op in sem_ops:                        # ② 语义（知识检索命中它挂的文档）
            score += sem_ops[op]
            hits.append('语义')
        if ex:
            # ①d **出局制**（不是降权）：登记了 excludes 的 op，一旦命中就整个退出候选。
            # 为什么出局而不是减分：减分只把它往后挪，而"同名词不同动作"的判断是**确定性的**
            # ——「给客户看下效果」要的就是预览稿，此时把「建工程」留在候选里只会让 AI 犹豫
            # （实测它靠「项目」这个词拿到 6 分居首，把 ui_preview 压到第 3）。
            # 出局是**可追溯**的：命中的片段原样带出去（excluded），不静默吞掉。
            continue
        if score:
            scored.append((score, op, s, hits))
    scored.sort(key=lambda r: (-r[0], r[1]))
    from collections import Counter
    st = Counter(s.get('stage') or 'other' for _sc, _op, s, _h in scored[:limit])
    out['stage'] = (st.most_common(1)[0][0] if st else '')
    docrefs = []
    for score, op, s, hits in scored[:limit]:
        args = [p.get('name') for p in (s.get('params') or [])]
        out['candidates'].append({'op': op, 'brief': s.get('summary') or '',
                                  'risk': s.get('risk'), 'stage': s.get('stage'),
                                  'score': score, 'hit': list(dict.fromkeys(hits))[:6],
                                  'params': args})
        d = s.get('docRef')
        if d and d not in docrefs:
            docrefs.append(d)
    out['count'] = len(out['candidates'])
    # 出局明细（可追溯，不静默）：哪些 op 因为哪个词被排除。命中过的才列，避免噪声。
    if ex_hits:
        out['excluded'] = [{'op': op, 'by': ex_hits[op]} for op in sorted(ex_hits)]
    # 第三级：候选相关的知识（语义命中的文档优先，再补候选的 docRef）——
    # 这就是"调用过程中产生需要关联的知识再进知识库匹配"的入口：先给指针，要深了再 knowledge_search
    for d in docrefs:
        if d not in sem_docs:
            sem_docs.append(d)
    out['knowledge'] = sem_docs[:5]
    if not out['candidates']:
        out['hint'] = ('没有 op 命中这句需求 —— 先 op="list" 看全部能力；'
                       '若确认该能力缺失，用 op="knowledge_gaps" / "knowledge_search" 查知识缺口')
    return json.dumps(out, ensure_ascii=False)


def _describe(name: str) -> str:
    """按需拉某个 op 的**完整契约**（常驻 description 只有 L0：选不选 + 怎么调）。

    工具面分层见 `op_spec.json.tiers`：常驻面省下的是每次会话的上下文预算，
    代价是"细节要主动拉"—— 选中一个 op、准备调它之前，若摘要不够就调这里。
    """
    op = (name or '').strip()
    if op not in OPS:
        out = {"ok": False,
               "error": {"code": "UNKNOWN_OP", "msg": "unknown op: %s" % op,
                         "hint": "调 op='list' 取全部 op 与参数名",
                         "retryable": False},
               "candidates": _suggest(op)}
        return json.dumps(out, ensure_ascii=False)
    try:
        import op_spec_loader as osl
        out = {"ok": True, "op": op, "risk": osl.risk(op), "category": osl.category(op),
               "stage": osl.stage(op), "docRef": osl.doc_ref(op) or '',
               "contract": osl.render_contract(op)}
    except Exception as e:                       # 注册表不可用 → 明说（不静默给空契约）
        return json.dumps({"ok": False,
                           "error": {"code": "CONTRACT_UNAVAILABLE",
                                     "msg": "op 契约注册表不可用: %s: %s"
                                            % (type(e).__name__, e),
                                     "hint": "检查 op_spec.json / op_spec_loader.py 是否随包分发",
                                     "retryable": False}},
                          ensure_ascii=False)
    try:
        import kb_tools as _kb
        sa = _kb._seealso_for(op) or []
        if sa:
            out['seeAlso'] = sa
    except Exception as e:                       # seeAlso 是加分项（缺了不影响契约本身），但不静默
        out['seeAlsoError'] = '%s: %s' % (type(e).__name__, e)
    return json.dumps(out, ensure_ascii=False)


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


def _err_json(code, msg, hint='', retryable=None, **extra) -> str:
    """分发器侧的失败返回：统一 envelope + 错误码表补 action / who / 默认 retryable。

    `retryable=None` = 未表态（由码表定）；显式 True 表示调用点更确定可重试。
    这样分发器的错误体与工具内部的（kb_tools.normalize_result 那条路）形状一致。
    """
    err = {"code": code, "msg": msg, "hint": hint, "retryable": retryable}
    errcodes.enrich(err)
    if err.get("retryable") is None:
        err["retryable"] = False
    out = {"ok": False, "error": err, "warnings": []}
    out.update(extra)
    return json.dumps(out, ensure_ascii=False)


def _env_err(code, msg, hint='', retryable=False) -> str:
    return _err_json(code, msg, hint, retryable or None)


# ── 长任务：进度上报 + 不阻塞事件循环 ────────────────────────────────
# 为什么：构建 / 部署 / 刷机是**分钟级**；原来同步直调会把**事件循环**堵死 ——
# 客户端连「取消」都发不进来，也收不到任何进度。改法：op 丢到工作线程跑，
# 事件循环每秒轮询 `progress.current()`（阶段由 op 内部的 steps.append 打点）→ ctx.report_progress。
# 长任务清单来自 `op_spec.json` 的 `longOps`（不在这里硬编码）。
_LONG_OPS = None
_PROGRESS_NOTE = ''


def _long_ops():
    global _LONG_OPS, _PROGRESS_NOTE
    if _LONG_OPS is None:
        try:
            import op_spec_loader as _osl
            _LONG_OPS = set(_osl.long_ops())
        except Exception as e:          # 契约不可用 → 全部按普通 op 处理，但**记下原因**（不静默）
            _LONG_OPS = set()
            _PROGRESS_NOTE = '长任务清单不可用（%s: %s），本次不启用进度上报' % (type(e).__name__, e)
    return _LONG_OPS


def _progress_token_ok(ctx):
    """客户端带 progressToken 了吗（没带就别白发通知）。"""
    meta = getattr(getattr(ctx, 'request_context', None), 'meta', None)
    return bool(getattr(meta, 'progressToken', None))


async def _run_long(fn, kwargs, ctx):
    """工作线程跑长任务；期间把阶段推给客户端（无 ctx / 客户端不支持也照跑，只是不上报）。"""
    import anyio
    import progress as _pg
    _pg.begin()
    box = {}
    can_report = ctx is not None and _progress_token_ok(ctx)

    async def _beat():
        global _PROGRESS_NOTE
        last = -1
        while True:
            await anyio.sleep(1.0)
            snap = _pg.current()
            if snap['seq'] == last or not can_report:
                continue
            last = snap['seq']
            try:
                await ctx.report_progress(progress=snap['elapsed'], total=None,
                                          message=snap['stage'] or '运行中')
            except Exception as e:      # 上报通路断了：停上报，任务继续（并如实记下）
                _PROGRESS_NOTE = '进度上报中断（%s: %s），任务继续执行' % (type(e).__name__, e)
                return

    async with anyio.create_task_group() as tg:
        tg.start_soon(_beat)
        try:
            box['v'] = await anyio.to_thread.run_sync(lambda: fn(**kwargs))
        finally:
            tg.cancel_scope.cancel()    # 任务结束就停心跳，别留一个永久 sleep 的任务
    _pg.end()
    return box['v']


async def flythings_kb(op: str = "list", args: str = "{}",
                        ctx: Context = None) -> str:
    """FlyThings 开发能力统一入口（48 个能力合一的单入口）。

    ⚠️ 仅在用户意图属于「FlyThings 软件开发」时调用：UI 布局/控件/json/ftu、
    工程创建与编译部署、依赖包/Manifest、多语言 i18n、知识库检索、UI 预览与像素验收、
    真机截图、资源生成、自动化测试。其他话题（闲聊、文档、其他产品）不要调用。

    用法：先传 op="list" 取全部可用操作**及其参数名**（索引），再用 op=<操作名> + args='{"参数": 值}'
    （args 传 JSON 字符串；部分客户端只支持对象，也可直接传 dict）。
    **三步走（省上下文）**：① 需求进来先分级筛选 —— `op="find:<用户原话>"` 出候选 op
    （按触发词打分 + 关联知识指针）；② 选中后 `op="describe:<op 名>"` 拉完整契约
    （多步流程 / 踩坑铁律）；③ 调用中需要判据细节，按返回体的 seeAlso/docRef 走
    `op="knowledge_search"` 检索（按需，不预加载）。

    ⚠️ 能力不止这 48 个 op：设备端预编译工具（touch 触摸注入 / busybox / ui_test /
    zkshot）在 `<MCP 安装目录>/bin_tools/<平台>/` 下，**不是 op、不占 op 名额**——
    只数 op 会漏掉触摸注入这类能力；看 flythings_get_version 的 binTools 字段或
    flythings://tools 资源的「设备端预编译工具」一节。
    """
    if op in ("", "list", "help", "?"):
        return _catalog()
    if op.startswith('find:'):
        return _find(op.split(':', 1)[1])
    if op == 'find':                             # 也认 args={"need": "..."} 这种写法
        try:
            need = (json.loads(args) or {}).get('need', '') if isinstance(args, str) \
                else (args or {}).get('need', '')
        except ValueError:
            need = ''
        return _find(need)
    if op.startswith('describe:'):
        return _describe(op.split(':', 1)[1])
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
            return _err_json("OP_RENAMED",
                             "op %s 已合并/改名为 %s" % (op, renamed), hint)
        return _err_json("UNKNOWN_OP", "unknown op: %s" % op,
                         "调 op='list' 取全部 op 与参数名；或见 candidates",
                         candidates=_suggest(op))
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
        if op in _long_ops():               # 长任务：线程 + 进度上报（普通 op 仍直调，省一次切换）
            res = await _run_long(fn, kwargs, ctx)
        else:
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


# 注册分发器（MODE=flat 时不注册：那种模式语义 =「只要 48 个独立工具」，见 mcp_server_flat.py）
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
