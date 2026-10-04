# -*- coding: utf-8 -*-
"""MCP 原生原语：resources（可挂载的上下文）+ prompts（常用流程模板）。

为什么需要（检讨报告 §3.6）：只用 tools 时，知识只能靠 `flythings_knowledge_search` 拿 3 条片段、
常用流程只能靠提示词口头描述——客户端**无法把整篇知识文档当上下文挂载**。
本模块把关键文档暴露成 resources、把常见流程做成 prompts，两种 server（默认入口 / flat）共用。

resources：
  flythings://catalog/knowledge知识库目录（分类 → 文档清单 + 检索关键词提示）
  flythings://knowledge/<分类>/<文件>.md分类目录下的文档（如 devflow/device-screenshot.md）
  flythings://knowledge/<文件>.md          knowledge/ 根目录的文档（如 README.md）
  flythings://tools工具清单（op / 风险分级 / 一句话简介；来自 tools_manifest.json）
                                    + 「设备端预编译工具」一节：bin_tools/<平台>/ 下的 touch / busybox /
                                    ui_test / zkshot（**不是 op**，数 op 看不到）
  flythings://version版本 / 构建日 / 工具数 / 近期特性
  flythings://errors错误码表（code → 什么意思 / 该谁动手 / 可否重试 / 下一步）—— 多数情况
                                     **不用挂**：action 已自动补进每次失败的返回体
  flythings://state最近工程的进度（跨会话「上次做到哪」）—— 新会话不用重摸工程

  ⚠️ FastMCP 的 URI 模板参数只匹配单段路径（内部把 {x} 换成 [^/]+），所以分类文档与
根目录文档用两个模板，不能写 {path} 通吃多级；读文件前过白名单校验（仅 knowledge/ 下 .md，防穿越）。

prompts（模板只给流程与安全默认，不代替工具调用）：
  flythings-new-project(平台, 分辨率, 需求)
  flythings-ui-from-prototype(需求)
  flythings-ui-verify(项目根)
  flythings-deploy-debug(项目根, 设备?)
  flythings-package-deps(功能需求, 平台)

安全默认（与 MCP 工具一致，模板里写死提醒）：写操作先 dry_run / preview，pack 与推真机必须显式。
"""
import io
import json

import flow_loader
import os

BASE = os.path.dirname(os.path.abspath(__file__))
KNOWLEDGE = os.path.join(BASE, 'knowledge')
MANIFEST = os.path.join(BASE, 'tools_manifest.json')


def _read(path):
    return io.open(path, encoding='utf-8').read()


def _knowledge_index():
    """知识库目录（分类 → 文档清单），带检索关键词提示。"""
    if not os.path.isdir(KNOWLEDGE):
        return '# 知识库目录\n\n（knowledge/ 不存在）\n'
    lines = ['# FlyThings 知识库目录', '',
             '> 用法：`flythings://knowledge/<相对路径>` 可直接挂载/读取；',
             '> 或调用工具 `flythings_knowledge_search`（检索）取片段。', '']
    total = 0
    for root, dirs, files in os.walk(KNOWLEDGE):
        dirs[:] = sorted(d for d in dirs if not d.startswith('.'))
        rel_dir = os.path.relpath(root, KNOWLEDGE).replace('\\', '/')
        if rel_dir == '.':
            rel_dir = ''
        mds = sorted(f for f in files if f.endswith('.md'))
        if not mds:
            continue
        lines.append('## %s/' % (rel_dir or ''))
        for f in mds:
            rel = (rel_dir + '/' + f) if rel_dir else f
            total += 1
            first = ''
            try:
                for ln in _read(os.path.join(root, f)).splitlines():
                    if ln.strip().startswith('#') or ln.strip():
                        first = ln.strip('# ').strip()[:80]
                        break
            except OSError:
                first = ''
            lines.append('- `%s`%s' % (rel, (' — ' + first) if first else ''))
        lines.append('')
    lines.append('共 %d 篇。' % total)
    return '\n'.join(lines)


def _safe_knowledge_path(path):
    """把 resource URI 里的 path 解析成 knowledge/ 下的真实文件（防目录穿越）。"""
    rel = (path or '').strip().replace('\\', '/').lstrip('/')
    if not rel.endswith('.md'):
        raise ValueError('只支持读取 knowledge/ 下的 .md 文档，收到: %r' % path)
    full = os.path.abspath(os.path.join(KNOWLEDGE, rel))
    root = os.path.abspath(KNOWLEDGE)
    if not (full == root or full.startswith(root + os.sep)):
        raise ValueError('路径越出 knowledge/ 目录（拒绝）: %r' % path)
    if not os.path.isfile(full):
        raise ValueError('文档不存在: %s（可用 flythings://catalog/knowledge 看清单）' % rel)
    return full


def _bin_tools_section():
    """「设备端预编译工具」一节（bin_tools/，**不是 op**）。

    2026-09-14（经需求方反馈）：外部 AI 数完 op 个数就断言「这版没有 touch 注入」——实际 touch
自 v0.27.40 起一直在 bin_tools/<平台>/ 下。工具清单只列 op，必须显式补这一节。
    """
    root = os.path.join(BASE, 'bin_tools')
    if not os.path.isdir(root):
        return ''
    try:
        import kb_tools
        brief = dict(getattr(kb_tools, 'BIN_TOOL_BRIEF', {}) or {})
    except ImportError:
        brief = {}
    lines = ['', '## 设备端预编译工具（bin_tools/，**不是 op**，不占 op 名额）', '',
             '> 路径：`<MCP 安装目录>/bin_tools/<平台>/<工具>`，`adb push` 即用（无需宿主 zkgui）；',
             '> 触摸注入 / UI 自动化测试先调 `flythings_gen_ui_test`（内部就用 `touch`）+ '
             '`flythings_knowledge_search("触摸注入")`，不要自己造轮子。', '']
    for plat in sorted(os.listdir(root)):
        d = os.path.join(root, plat)
        if not os.path.isdir(d):
            continue
        # 说明文件（README.md）不算设备端工具——bin_tools/z235x 目前只有占位说明
        files = sorted(f for f in os.listdir(d)
                       if os.path.isfile(os.path.join(d, f)) and not f.startswith('.')
                       and not f.lower().endswith('.md'))
        if not files:
            continue
        lines.append('- **%s**: %s' % (plat, '; '.join(
            '`%s`%s' % (f, (' — ' + brief[f]) if f in brief else '') for f in files)))
    lines.append('')
    return '\n'.join(lines)


def _tools_doc():
    """工具清单（来自 manifest；文件缺失/损坏时回退代码清单，并在文档里说明原因——不静默降级）。

    这份清单是**常驻面的索引**：tool description 只带「选不选 + 怎么调」（见 `op_spec.json.tiers`），
    要看某个 op 的契约（流程/铁律/检索词）挂 `flythings://ops/<op 名>` —— 那是按需面；只想要某一段时挂 `flythings://ops/<op 名>/<段名>`。
    """
    note = ''
    if os.path.isfile(MANIFEST):
        data = None
        try:
            data = json.loads(_read(MANIFEST))
        except (OSError, ValueError) as e:
            note = 'tools_manifest.json 读取失败（%s），已回退到代码清单。' % e
        ops = data.get('ops') if isinstance(data, dict) else None
        if isinstance(ops, list) and ops:
            lines = ['# FlyThings MCP 工具清单（%s，%d 个）'
                     % (data.get('version'), data.get('toolCount') or len(ops)),
                     '',
                     '风险分级：read=只读 / write=写本地文件 / device=会连真机。',
                     '这里是**索引**（一句话 + 参数名）；**契约**（流程/铁律坑）挂 '
                     '`flythings://ops/<op 名>`，或用 `flythings_kb(op="describe:<op 名>")`。',
                     '']
            for cat in sorted({o.get('category', 'other') for o in ops}):
                lines.append('## %s' % cat)
                for o in ops:
                    if o.get('category', 'other') != cat:
                        continue
                    lines.append('- `%s` [%s] (%s) — %s'
                                 % (o.get('op'), o.get('risk'),
                                    ', '.join(o.get('args') or []) or '无参数', o.get('brief', '')))
                lines.append('')
            return '\n'.join(lines) + _bin_tools_section()
        if not note:
            note = 'tools_manifest.json 结构异常（缺 ops），已回退到代码清单。'
    else:
        note = 'tools_manifest.json 不存在（先跑 scripts/gen_manifest.py），已回退到代码清单。'
    import kb_tools
    lines = ['# FlyThings MCP 工具清单（%d 个）' % len(kb_tools.OP_NAMES), '',
             '> ⚠️ %s' % note, '']
    for n in kb_tools.OP_NAMES:
        fn = getattr(kb_tools, n, None)
        brief = ((getattr(fn, '__doc__', '') or '').strip().splitlines() or [''])[0]
        lines.append('- `%s` — %s' % (n, brief[:80]))
    return '\n'.join(lines) + _bin_tools_section()


def _version_doc():
    import kb_tools
    f = (kb_tools.MCP_FEATURES or [''])[0]
    return ('# FlyThings MCP 版本\n\n'
            '- version: `%s`\n- build: `%s`\n- toolCount: %d\n\n'
            '## 近期特性\n\n%s\n\n'
            '> 近期变更史：调用 `flythings_get_version(compact=False)`；更早版本史见仓库根 `VERSION_HISTORY.md`。\n'
            % (kb_tools.MCP_VERSION, kb_tools.MCP_BUILD, len(kb_tools.OP_NAMES), f))


# ---------------- prompts（正文由 flow_spec.json 派生，本文件只留签名） ----------------
#
# FastMCP 靠**函数签名**生成参数 schema，所以每个 prompt 必须有显式参数名；
# 而标题 / 说明 / 正文 / 参数表全部来自 `flow_spec.json` 的 action 流程（域⑩ 唯一真源）——
# 改流程改注册表，不在本文件抄一份。签名与注册表 `inputs` 的一致性由 tests/test_flows.py 钉住。


def _prompt_spec(flow_id):
    """取动作流程渲染出的 prompt 规格 → {'title','description','args','body'}。"""
    return flow_loader.render_prompt(flow_id)


def _render(flow_id, **kwargs):
    """渲染动作流程 → prompt 正文；未提供的参数留提示语（让 AI 先问用户而不是瞎猜）。"""
    spec = _prompt_spec(flow_id)
    vals = {k: (kwargs.get(k) or '（未提供，先问用户）') for k in spec['args']}
    return spec['body'].format(**vals)


def register(mcp):
    """把 resources / prompts 注册到给定 FastMCP 实例（默认入口与 flat 入口共用）。"""

    @mcp.resource('flythings://catalog/knowledge', name='knowledge-catalog',
                  title='FlyThings 知识库目录', mime_type='text/markdown')
    def knowledge_catalog() -> str:
        """知识库全部文档清单（挂载后 AI 可直接挑文档读）。"""
        return _knowledge_index()

    @mcp.resource('flythings://knowledge/{folder}/{file}', name='knowledge-doc',
                  title='FlyThings 知识文档', mime_type='text/markdown')
    def knowledge_doc_sub(folder: str, file: str) -> str:
        """读取分类目录下的文档，如 devflow/device-screenshot.md。"""
        return _read(_safe_knowledge_path('%s/%s' % (folder, file)))

    # ⚠️ FastMCP 的 URI 模板参数只能匹配单段（内部把 {x} 换成 [^/]+），
    # 所以根目录文档和分类目录文档必须用两个模板（不能写 {path} 通吃多级路径）。
    @mcp.resource('flythings://knowledge/{file}', name='knowledge-doc-root',
                  title='FlyThings 知识文档（根目录）', mime_type='text/markdown')
    def knowledge_doc_root(file: str) -> str:
        """读取 knowledge/ 根目录下的文档，如 README.md。"""
        return _read(_safe_knowledge_path(file))

    @mcp.resource('flythings://tools', name='tool-catalog',
                  title='FlyThings MCP 工具清单', mime_type='text/markdown')
    def tool_catalog() -> str:
        """工具清单 + 风险分级（read/write/device）——写操作前先看这里。"""
        return _tools_doc()

    @mcp.resource('flythings://ops', name='op-contract-index',
                  title='FlyThings op 完整契约（索引）', mime_type='text/markdown')
    def op_contract_index() -> str:
        """47 个 op 的完整契约索引（一句话 + 触发词 + 参数名 + 去哪看细节）。

        工具面分层（`op_spec.json.tiers`）：tool description 只是**常驻**的「选不选 + 怎么调」；
        契约（流程/铁律/检索词）是**按需**的 —— 挂 `flythings://ops/<op 名>` 取单个（默认形态）；要单段挂 `flythings://ops/<op 名>/<段名>`（`skeleton`/`flow`/`returns`/`rules`/`refs`，`all` = 全文）。
        """
        import op_spec_loader as _osl
        L = ['# FlyThings op 完整契约 · 索引',
             '',
             '> 常驻的 tool description 只带「选不选 + 怎么调」（省每次会话的上下文预算）；',
             '> 要某个 op 的**契约**（调用流程 / 铁律 / 检索词）按需取：挂 `flythings://ops/<op 名>`，'
             '要单段挂 `flythings://ops/<op 名>/<段名>`（段名 skeleton/flow/returns/rules/refs，all=全文）'
             '或 `flythings_kb(op="describe:<op 名>")`。',
             '']
        for op in _osl.registered():
            s = _osl.spec(op)
            trig = ' / '.join(s.get('triggers') or []) or '—'
            args = '、'.join(p.get('name') for p in (s.get('params') or [])) or '（见函数签名）'
            L.append('- **`%s`**（%s / %s）%s' % (op, s.get('risk'), s.get('category'),
                                                 s.get('summary') or ''))
            L.append('  - 何时用：%s ｜ 参数：%s' % (trig, args))
            if s.get('docRef'):
                L.append('  - 细节文档：`%s`' % s['docRef'])
        return '\n'.join(L) + '\n'

    @mcp.resource('flythings://ops/{name}', name='op-contract',
                  title='FlyThings op 完整契约（单个）', mime_type='text/markdown')
    def op_contract(name: str) -> str:
        """单个 op 的契约（调用流程 / 铁律 / 检索词 / 未归类的兜底说明）—— 默认形态；要单取一段挂 `flythings://ops/<op 名>/<段名>`。

        什么时候挂：已经选中这个 op 但 description 里的摘要不够时（多步流程、踩坑铁律）。
        """
        import op_spec_loader as _osl
        op = (name or '').strip()
        try:
            s = _osl.spec(op)
        except Exception:
            L = ['# 未登记的 op：%s' % op, '', '可用 op 清单见 `flythings://ops`。']
            import difflib
            near = difflib.get_close_matches(op, _osl.registered(), n=5, cutoff=0.4)
            if near:
                L += ['', '是不是想找：' + '、'.join('`%s`' % x for x in near)]
            return '\n'.join(L) + '\n'
        L = ['# %s' % op, '',
             '风险 %s ｜ 分类 %s ｜ 阶段 %s' % (s.get('risk'), s.get('category'), s.get('stage')),
             '',
             # 默认形态：全文 ≤ 预算时就是全文（与旧行为逐字节相同）；超预算才退化成
             # skeleton + 段目录。要单取一段用 `flythings://ops/<名>/<段>`。
             '---', '', _osl.render_default(op), '']
        if s.get('docRef'):
            L += ['', '细节文档：`%s`' % s['docRef']]
        try:
            import kb_tools as _kb
            sa = _kb._seealso_for(op) or []
        except Exception:
            sa = []
        if sa:
            L += ['', '相关知识：' + '、'.join('`%s`' % x for x in sa)]
        return '\n'.join(L) + '\n'

    @mcp.resource('flythings://ops/{name}/{section}', name='op-contract-section',
                  title='FlyThings op 契约（单个 op 的某一段）', mime_type='text/markdown')
    def op_contract_section(name: str, section: str) -> str:
        """单取一个 op 的**某一段**契约（按需面分段取用）。

        段名：`skeleton`（选不选+怎么调+铁律+参数）/ `flow` / `returns` / `rules` / `refs`；
        `all` = 全文。为什么要分段：单条契约有 900 字符上限，而最长的一条已到 892 ——
        分段把计费单位从"整条 op"换成"一次取用"（实测单段最大 645）。
        """
        import op_spec_loader as _osl
        op = (name or '').strip()
        sec = (section or '').strip()
        try:
            _osl.spec(op)
        except Exception:
            return '# 未登记的 op：%s\n\n可用 op 清单见 `flythings://ops`。\n' % op
        if sec not in _osl.section_ids():
            # 未知段**不静默回落**成整条契约（与 `_describe` 同口径）
            return ('# 未登记的段：%s\n\n可用段：%s\n\n'
                    '（`all` = 全文；不分段时挂 `flythings://ops/%s` 取默认形态）\n'
                    % (sec, ' / '.join('`%s`' % x for x in _osl.section_ids()), op))
        L = ['# %s ｜ %s' % (op, sec), '', _osl.render_section(op, sec), '',
             '（段清单与全文：`flythings://ops/%s`）' % op]
        return '\n'.join(L) + '\n'

    @mcp.resource('flythings://version', name='version',
                  title='FlyThings MCP 版本', mime_type='text/markdown')
    def version_doc() -> str:
        """版本 / 构建日 / 工具数 / 近期特性。"""
        return _version_doc()

    @mcp.resource('flythings://errors', name='error-codes',
                  title='FlyThings MCP 错误码表', mime_type='text/markdown')
    def error_codes_doc() -> str:
        """全部错误码 + 含义 + 该谁动手 + 能否重试（由 error_codes.json 派生）。

        ⚠️ 多数情况**不用挂这个** —— `action` 与默认 `retryable` 已经自动补进每次失败的返回体了。
        挂它是为了「先知道有哪些码」或排查反复出现的同一类错。
        """
        import error_codes_loader as _ec
        return _ec.render_table()

    @mcp.resource('flythings://state', name='project-state',
                  title='最近工程的进度（跨会话）', mime_type='text/markdown')
    def project_state_doc() -> str:
        """最近活动过的工程 + 各自做到哪了 —— 新会话里「上次做到哪」不用重摸工程。

        状态位口径来自 `flow_spec.json` 的 `stateSlots`；实例在 `<项目>/.flythings/state.json`。
        要打点 / 清空用 op `flythings_project_state`（本资源只读）。
        """
        import project_state as _ps
        L = ['# 最近工程的进度（跨会话「做到哪了」）', '',
             '> 状态位口径来自 `flow_spec.json` 的 `stateSlots`；实例写 `<项目>/.flythings/state.json`。',
             '> 打点 / 清空用 op `flythings_project_state`。', '']
        rows = _ps.recent(5)
        if not rows:
            L.append('（还没有活动工程记录 —— 建工程或跑任意工程 op 后会自动登记。）')
            return '\n'.join(L) + '\n'
        for r in rows:
            root = r.get('root') or ''
            L.append('## %s' % (r.get('name') or root))
            L.append('')
            L.append('- 路径：`%s`' % root)
            try:
                v = _ps.show(root)
            except Exception as e:                # 读不到就如实报，不假装没这个工程
                L.append('- ⚠️ 读不到状态：%s: %s' % (type(e).__name__, e))
                L.append('')
                continue
            L.append('- 已过闸门：%s' % ('、'.join(d['slot'] for d in v['done']) or '（无）'))
            nxt = v.get('next')
            L.append('- 下一步：%s' % (('%s（`%s`）' % (nxt['stepTitle'], nxt['op'] or '人判断'))
                                    if nxt else '全部走完'))
            if nxt and nxt.get('gate'):
                L.append('- ⚠️ 该步是**%s**：%s' % (nxt['gate'], nxt.get('gateHow') or ''))
            L.append('')
        return '\n'.join(L) + '\n'

    # prompts：每个都必须有**显式参数名**（FastMCP 靠签名生成参数 schema，**kwargs 会变成无参）
    @mcp.prompt(name='flythings-new-project', title=_prompt_spec('new-project')['title'],
                description=_prompt_spec('new-project')['description'])
    def new_project(platform: str = '', resolution: str = '', requirement: str = '') -> str:
        """新建工程流程（平台/分辨率/需求）。"""
        return _render('new-project', platform=platform, resolution=resolution,
                       requirement=requirement)

    @mcp.prompt(name='flythings-ui-from-prototype',
                title=_prompt_spec('ui-from-prototype')['title'],
                description=_prompt_spec('ui-from-prototype')['description'])
    def ui_from_prototype(requirement: str = '') -> str:
        """HTML 原型 → json 布局流程。"""
        return _render('ui-from-prototype', requirement=requirement)

    @mcp.prompt(name='flythings-ui-verify', title=_prompt_spec('ui-verify')['title'],
                description=_prompt_spec('ui-verify')['description'])
    def ui_verify(project_root: str = '') -> str:
        """三段式 UI 验收 + 产物核对。"""
        return _render('ui-verify', project_root=project_root)

    @mcp.prompt(name='flythings-deploy-debug', title=_prompt_spec('deploy-debug')['title'],
                description=_prompt_spec('deploy-debug')['description'])
    def deploy_debug(project_root: str = '', device: str = '') -> str:
        """编译部署到真机调试（默认不推真机）。"""
        return _render('deploy-debug', project_root=project_root, device=device)

    @mcp.prompt(name='flythings-package-deps', title=_prompt_spec('package-deps')['title'],
                description=_prompt_spec('package-deps')['description'])
    def package_deps(requirement: str = '', platform: str = '') -> str:
        """依赖包检索 + Manifest 生成。"""
        return _render('package-deps', requirement=requirement, platform=platform)

    return mcp
