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
    """工具清单（来自 manifest；文件缺失/损坏时回退代码清单，并在文档里说明原因——不静默降级）。"""
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
                     '', '风险分级：read=只读 / write=写本地文件 / device=会连真机', '']
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


# ---------------- prompts 模板 ----------------

_SAFETY = ('安全默认：改布局先出预览稿给用户确认；`flythings_ui_visual(action="edit_apply")` 先 dry_run；'
           '`flythings_fui_pack` / `flythings_build_ui_flow` 默认不 pack、不推真机，'
           '要 pack / 要上设备必须显式确认后传参。')

PROMPTS = {
    'flythings-new-project': {
        'title': '新建 FlyThings 工程',
        'description': '从零建工程：确认平台/分辨率 → 建骨架 → 布局 → 预览 → 编译',
        'args': ['platform', 'resolution', 'requirement'],
        'body': ('用 FlyThings 新建工程：平台 {platform}、分辨率 {resolution}。需求：{requirement}\n\n'
                 '步骤：\n'
                 '1. `flythings_create_project`（platform/resolution 必须由用户明确给出，不要猜；'
                 'with_cli=True 带上 fui/fun）\n'
                 '2. 先看知识库 `flythings://knowledge/devflow/html-subset-quickref.md` 与'
                 ' `knowledge/devflow/prototype-flow.md`（检索词：原型流程 / HTML_SUBSET），'
                 '按受限 HTML 写原型稿（图标优先、禁 emoji 文本）\n'
                 '3. `flythings_html_to_json` 转布局 → `flythings_ui_preview` 出预览稿给用户确认'
                 '（未确认不要 pack、不要写逻辑）\n'
                 '4. 确认后 `flythings_build_ui_flow` 编译（默认不推真机）\n\n' + _SAFETY),
    },
    'flythings-ui-from-prototype': {
        'title': 'HTML 原型 → UI 布局',
        'description': '原型稿转 json：效果转图、预览确认、产物核对',
        'args': ['requirement'],
        'body': ('按需求做 UI 原型转布局。需求：{requirement}\n\n'
                 '1. 先检索「HTML_SUBSET 原型规范 / 控件映射 / data-icon 图标」'
                 '（`flythings_knowledge_search`），必要时读 '
                 '`flythings://knowledge/devflow/html-subset-quickref.md`\n'
                 '2. 写受限 HTML（效果由转换器自动转图：渐变/阴影圆角/emoji/loading；'
                 '禁自绘 1x png）\n'
                 '3. `flythings_html_to_json` → `flythings_ui_preview` 出预览稿，'
                 '**只把预览稿交给用户确认**\n'
                 '4. 确认后 `flythings_verify_assets` 核对产物（图尺寸必须 == 控件盒）→ '
                 '再 pack / 写 logic.cc\n\n' + _SAFETY),
    },
    'flythings-ui-verify': {
        'title': 'UI 验收（预览 → 真机 → 像素）',
        'description': '三段式验收 + 产物核对，改前改后对比',
        'args': ['project_root'],
        'body': ('验收工程 {project_root} 的界面。\n\n'
                 '1. 静态：`flythings_validate_project` + `flythings_verify_assets`'
                 '（引用存在 + 自动生成图尺寸 == 控件盒）\n'
                 '2. 预览：`flythings_ui_preview`（零 token 看结构与相对关系；'
                 '多整屏 window 工程自带页面切换条 + `#window__N` 直达）\n'
                 '3. 真机像素真相：`flythings_device_screenshot`（方向 rotate=\'auto\'，'
                 '按项目工程 rotateScreen；改前先抓一张）\n'
                 '4. 对比：`flythings_ui_visual(action="diff")`（0 token 差异清单；只看差异区小图给视觉模型）\n'
                 '5. 结论：给用户「改了什么/像素差异/是否可交付」，别把整屏原图丢给模型\n\n' + _SAFETY),
    },
    'flythings-deploy-debug': {
        'title': '编译部署到真机调试',
        'description': '编译 → 按需推真机 → 抓屏/日志排查',
        'args': ['project_root', 'device'],
        'body': ('把工程 {project_root} 编译并部署调试（设备：{device}）。\n\n'
                 '1. `flythings_build_ui_flow`（默认**只编译不推真机**；用户明确要上设备才传 '
                 'with_launch=True；fun launch 网络推送失败会自动重试 5 次，仍失败必须问用户接入方式，'
                 '不要自写 push 脚本）\n'
                 '2. 画面确认：`flythings_device_screenshot`（不要用 admin/其他设备的老截图）\n'
                 '3. 无画面/黑屏排查顺序：先日志（事件到没到控件 / 回调进没进）再像素（抓帧要按 pan 取当前页）；'
                 '设备缺命令就 push busybox（见 `flythings://knowledge/devflow/busybox-debug-library.md`）\n'
                 '4. i18n 改动：`fun launch` 不推翻译，必须 `flythings_i18n_to_json` 补推\n\n' + _SAFETY),
    },
    'flythings-package-deps': {
        'title': '依赖包与 Manifest',
        'description': '检索现有 package、生成 Manifest、递归解析依赖',
        'args': ['requirement', 'platform'],
        'body': ('为功能「{requirement}」在平台 {platform} 上准备依赖。\n\n'
                 '1. `flythings_package_search` 检索包生态（**有包用包，禁止手写协议栈/库**）\n'
                 '2. `flythings_get_package_api` 看该包头文件级 API（只认头文件，禁猜、禁反编译）\n'
                 '3. `flythings_manifest`（dry_run 先看推荐，确认后写 Manifest.xml）\n'
                 '4. `flythings_resolve_dependencies` 递归解析 + 冲突检查\n'
                 '5. `flythings_check_project_deps` 核对代码 include 与 Manifest 声明一致\n\n' + _SAFETY),
    },
}


def _render(name, **kwargs):
    """渲染 prompt 模板：未提供的参数留提示语（让 AI 先问用户而不是瞎猜）。"""
    spec = PROMPTS[name]
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

    @mcp.resource('flythings://version', name='version',
                  title='FlyThings MCP 版本', mime_type='text/markdown')
    def version_doc() -> str:
        """版本 / 构建日 / 工具数 / 近期特性。"""
        return _version_doc()

    # prompts：每个都必须有**显式参数名**（FastMCP 靠签名生成参数 schema，**kwargs 会变成无参）
    @mcp.prompt(name='flythings-new-project', title=PROMPTS['flythings-new-project']['title'],
                description=PROMPTS['flythings-new-project']['description'])
    def new_project(platform: str = '', resolution: str = '', requirement: str = '') -> str:
        """新建工程流程（平台/分辨率/需求）。"""
        return _render('flythings-new-project', platform=platform, resolution=resolution,
                       requirement=requirement)

    @mcp.prompt(name='flythings-ui-from-prototype',
                title=PROMPTS['flythings-ui-from-prototype']['title'],
                description=PROMPTS['flythings-ui-from-prototype']['description'])
    def ui_from_prototype(requirement: str = '') -> str:
        """HTML 原型 → json 布局流程。"""
        return _render('flythings-ui-from-prototype', requirement=requirement)

    @mcp.prompt(name='flythings-ui-verify', title=PROMPTS['flythings-ui-verify']['title'],
                description=PROMPTS['flythings-ui-verify']['description'])
    def ui_verify(project_root: str = '') -> str:
        """三段式 UI 验收 + 产物核对。"""
        return _render('flythings-ui-verify', project_root=project_root)

    @mcp.prompt(name='flythings-deploy-debug', title=PROMPTS['flythings-deploy-debug']['title'],
                description=PROMPTS['flythings-deploy-debug']['description'])
    def deploy_debug(project_root: str = '', device: str = '') -> str:
        """编译部署到真机调试（默认不推真机）。"""
        return _render('flythings-deploy-debug', project_root=project_root, device=device)

    @mcp.prompt(name='flythings-package-deps', title=PROMPTS['flythings-package-deps']['title'],
                description=PROMPTS['flythings-package-deps']['description'])
    def package_deps(requirement: str = '', platform: str = '') -> str:
        """依赖包检索 + Manifest 生成。"""
        return _render('flythings-package-deps', requirement=requirement, platform=platform)

    return mcp
