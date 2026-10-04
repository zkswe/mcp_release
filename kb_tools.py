# -*- coding: utf-8 -*-
"""FlyThings_mcp_open: 全套 MCP 工具定义（stdio 本地部署，完全开放）。

每个工具都是普通函数，返回 str/JSON 字符串；由 mcp_server.py（stdio）注册。
✅ 开源版：检索完全本地化（内置 bge-small-zh 向量模型，免 API Key，
不可用时自动降级 BM25），不依赖任何远程 MCP 服务。
"""
import html.parser  # PyInstaller 打包需要（html2json 运行时导入，静态分析漏收）
import inspect
import io
import json, math, os, re, shutil, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import platforms as _platforms   # 平台唯一来源：默认值/平台清单/包生态键都从这里取
import error_codes_loader as errcodes   # 错误码语义（域⑫）：normalize_result 补 action
import rag_search as rs
import project_tools as pt
import package_tools as pkgtools
import hardware_tools as hw
UI_TOOLS = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ui_tools')
if getattr(sys, 'frozen', False):  # PyInstaller 打包：ui_tools 随包进 _MEIPASS
    UI_TOOLS = os.path.join(sys._MEIPASS, 'ui_tools')
if UI_TOOLS not in sys.path:
    sys.path.insert(0, UI_TOOLS)
import html2json as h2j
import json2html as j2h
import gen_res as h2j_genres
import i18n_tools as itx
import test_tools as tt
import logic_tools as lt
import translate_tools as trt
# 整机自检 + 缺陷单（2026-09-29）：实现层单列（采集/渲染长逻辑不在本文件），kb_tools 只做工具面封装
try:
    import selfcheck_tools as sc
except Exception as _e:
    sc = None
    _SC_ERR = repr(_e)
else:
    _SC_ERR = ''
# UI 可视化编辑 / 像素验收（2026-09-10 起）：缺依赖时降级为对应工具报错，不影响其它工具
try:
    import ui_editor as uied
except Exception:
    uied = None
try:
    import ui_edit_apply as uia
except Exception:
    uia = None
try:
    import ui_diff as udf
except Exception:
    udf = None
try:
    import check_all as chk_all
    from check_all import verify_assets as _verify_assets
    if not callable(_verify_assets):
        raise ImportError('verify_assets missing')
except Exception:
    chk_all = None

try:
    import device_screenshot as dss
except Exception:
    dss = None

try:
    import ui_schema_loader as _uischema     # UI json 布局规范注册表（ui_schema.json 唯一真源）
except Exception as _e:
    _uischema = None
    _USC_ERR = repr(_e)
else:
    _USC_ERR = ''

_KB_ROOT_LABELS = None      # 仓库内文档路径 → 源标签（进程内缓存，按索引根真源派生）
_KB_ROOT_LABELS_ERR = []    # 真源不可用时的原因（不静默：检索返回体里带出来）


def _kb_root_labels():
    """仓库内文档路径 → 源标签（**按 kb_index_roots 的真源派生**，不是只判 `knowledge/` 前缀）。

    修前的口径是二选一：
        'knowledge（实践）' if path.startswith('knowledge/') else 'wiki（官方镜像）'
    于是**仓库内**的 `components/**/platforms.md`（16 篇，2026-10-02 收编）与
    `packages/**`（25 篇，2026-10-03 收编）全被标成「wiki（官方镜像）」——
    等于告诉 AI「这是外部镜像、不是本仓实践知识」：**可信度判错、出处指错**，
    而这正是它读检索结果时最先看到的字段之一。
    """
    global _KB_ROOT_LABELS
    if _KB_ROOT_LABELS is not None:
        return _KB_ROOT_LABELS
    labels = {'knowledge': 'knowledge（实践）',
              'components-platforms': 'components（组件平台页）',
              'packages': 'packages（包用法）'}
    out = {}
    try:
        import kb_index_roots as _bir
        base = os.path.dirname(os.path.abspath(__file__))
        for rel, _abs, spec in _bir.iter_repo_docs(base):
            out[rel.replace('\\', '/')] = labels.get(spec['id'], spec['id'])
    except Exception as e:                      # 真源不可用不静默：退回"全部按 wiki"并记原因
        out = {}
        del _KB_ROOT_LABELS_ERR[:]
        _KB_ROOT_LABELS_ERR.append('%s: %s' % (type(e).__name__, e))
    _KB_ROOT_LABELS = out
    return out


def _kb_source_label(path):
    """命中的来源标签（消费侧据此判断"这是本仓实践知识 / 配套页 / 本地层 / 外部镜像"）。"""
    p = str(path or '').replace('\\', '/')
    if p.startswith('kb_local/'):
        return 'kb_local（用户本地层）'
    lab = _kb_root_labels().get(p)
    return lab if lab else 'wiki（官方镜像）'


# ========== MCP 版本号（每次发布递增，AI/用户可查询确认是否最新）==========
MCP_VERSION = '0.27.195-open'
MCP_BUILD = '2026-10-03'
# compact 模式下每条特性截断长度（v0.27.87）：条目越写越长，不截断就会把默认返回体撑成 token 炸弹
# （契约用例 test_compact_default 盯 6000 字上限）；完整条目仍能通过 compact=False 拿到。
COMPACT_FEATURE_CHARS = 700


def _clip_feature(text, limit=None):
    """compact 用：把长特性条目截断到 limit 字（尾巴标「…」+ 指路 compact=False）。"""
    limit = COMPACT_FEATURE_CHARS if limit is None else limit
    s = str(text or '')
    if len(s) <= limit:
        return s
    return s[:limit] + '…（完整见 compact=False）'
# ========== 近期特性史（数据外置，2026-10-01）==========
# 条目本体在仓库根 features_recent.json（JSON 字符串数组，最新一条在顶部）；
# 这里只留惰性加载器：首次访问才读文件并缓存，import 时不吞这份百 KB 数据。
# 更早的版本史（< v0.27.121-open）归档在仓库根 VERSION_HISTORY.md（不随 get_version 返回）。
MCP_FEATURES_FILE = 'features_recent.json'
MCP_FEATURES_ARCHIVE = 'VERSION_HISTORY.md'
MCP_FEATURES_ARCHIVE_MAX = 'v0.27.121-open'
_FEATURES_CACHE = None   # None = 未加载；加载后为 list[str]（读取失败时为空 list，原因见 _FEATURES_ERR）
_FEATURES_ERR = ''


def _features_path():
    """features_recent.json 位置：源码态 = 本文件旁；PyInstaller 打包 = _MEIPASS（随包数据）。"""
    if getattr(sys, 'frozen', False):
        return os.path.join(sys._MEIPASS, MCP_FEATURES_FILE)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), MCP_FEATURES_FILE)


def _load_features():
    """惰性读 features_recent.json（带缓存）。文件缺失/损坏不静默：记 _FEATURES_ERR 并回空列表，
    get_version 仍回版本号与工具数（featuresError 字段给出原因）。"""
    global _FEATURES_CACHE, _FEATURES_ERR
    if _FEATURES_CACHE is not None:
        return _FEATURES_CACHE
    try:
        with io.open(_features_path(), encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        _FEATURES_ERR = '%s 读取失败：%s' % (MCP_FEATURES_FILE, e)
        _FEATURES_CACHE = []
        return _FEATURES_CACHE
    if not isinstance(data, list) or not all(isinstance(x, str) for x in data):
        _FEATURES_ERR = '%s 格式错误：顶层必须是字符串数组' % MCP_FEATURES_FILE
        _FEATURES_CACHE = []
        return _FEATURES_CACHE
    _FEATURES_ERR = ''
    _FEATURES_CACHE = data
    return _FEATURES_CACHE


def __getattr__(name):
    """PEP 562 模块级惰性属性：MCP_FEATURES 保持「模块属性」形态不变
    （tests / scripts/smoke / mcp_extras 均按 kb_tools.MCP_FEATURES 引用），但首次访问才真正读文件。"""
    if name == 'MCP_FEATURES':
        return _load_features()
    raise AttributeError('module %r has no attribute %r' % (__name__, name))



def _tool_names() -> list:
    """本模块内已注册的工具函数名（单一来源，禁止手写数量）。"""
    import inspect as _i
    return sorted(n for n, _ in _i.getmembers(sys.modules[__name__], _i.isfunction)
                  if n.startswith('flythings_') and n != 'flythings_kb')


# ========== 设备端预编译工具（bin_tools/，**不是 op**，不占 op 名额）==========
# 2026-09-14（经需求方反馈）：外部 AI 数完 34 个 op 就断言「MCP 这版没有触摸注入」——
# 实际 touch 自 v0.27.40 起一直在 bin_tools/<平台>/ 下，只是不占 op 名额、工具面没有任何出口。
# 修法：把 bin_tools 暴露成 flythings_get_version 的 binTools 字段 + flythings://tools 资源一节。
BIN_TOOLS = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'bin_tools')
if getattr(sys, 'frozen', False):          # PyInstaller 打包：随包进 _MEIPASS
    BIN_TOOLS = os.path.join(sys._MEIPASS, 'bin_tools')

BIN_TOOL_BRIEF = {
    'touch': '统一触摸注入：自动扫 /dev/input 节点 + 自动判协议（单点/MT-A/MT-B）；'
             'tap/swipe/long/monkey/run/record/play + list/info；部署不带 /dev/input/eventN',
    'busybox': '设备调试工具箱（网络/系统/Shell applet 全开，静态链接）',
    'ui_test': '触摸注入 / 自动化测试（单点协议，兼容保留，需人工传节点）',
    'zkshot': 'SigmaStar（z20/z21）视频层抓帧，配合 flythings_device_screenshot(layer="video")',
}


def _bin_tools() -> dict:
    """扫 bin_tools/<平台>/ 下的设备端 ELF → {平台: [工具名,...]}（缺失时返回空 dict，不报错）。"""
    out = {}
    if not os.path.isdir(BIN_TOOLS):
        return out
    for plat in sorted(os.listdir(BIN_TOOLS)):
        d = os.path.join(BIN_TOOLS, plat)
        if not os.path.isdir(d):
            continue
        # 说明文件（README.md）不算设备端工具——bin_tools/z235x 目前只有占位说明
        files = sorted(f for f in os.listdir(d)
                       if os.path.isfile(os.path.join(d, f)) and not f.startswith('.')
                       and not f.lower().endswith('.md'))
        if files:
            out[plat] = files
    return out


def _bin_tools_field() -> dict:
    """binTools 字段（工具面唯一出口：让「数 op」的 AI 也能发现设备端工具）。"""
    by_plat = _bin_tools()
    if not by_plat:
        return {}
    used = {f for fs in by_plat.values() for f in fs}
    return {
        'note': '设备端预编译 ELF（随 MCP 发布，adb push 即用）——**它们不是 op、不占 op 名额**，'
                '所以只数 op 清单会漏掉；触摸注入/自动化测试先看 touch，不要自己造轮子',
        'dir': BIN_TOOLS.replace('\\', '/'),
        'byPlatform': by_plat,
        'brief': {k: v for k, v in sorted(BIN_TOOL_BRIEF.items()) if k in used},
        'usage': '触摸：adb push bin_tools/<平台>/touch /data/touch && chmod 777；再 '
                 '`adb shell /data/touch list` 看节点+协议，tap/swipe/long/monkey/run/play 同工具；'
                 '知识库：knowledge/devflow/touch-inject-autotest.md',
    }


def flythings_get_version(compact: bool = True) -> str:
    """返回 MCP 版本号、工具数量与近期关键特性。用户问「MCP 版本是多少 / 是不是最新的」时调用。

    触发：MCP 版本 / 是不是最新版 / 装了哪个版本
    """
    tools = _tool_names()
    out = {
        'mcpName': 'flythings-kb-open',
        'version': MCP_VERSION,
        'build': MCP_BUILD,
        'toolCount': len(tools),
        'tools': tools,
        'checkHint': 'version 即当前安装版本；与官方最新发布号 vX.Y.Z-open 比对即可确认是否最新',
    }
    bt = _bin_tools_field()
    if bt:
        out['binTools'] = bt
    out['historyFile'] = MCP_FEATURES_ARCHIVE          # 更早版本史归档位置（仓库根）
    out['historyMax'] = MCP_FEATURES_ARCHIVE_MAX        # 近期史保留到哪个版本
    out['featuresFile'] = MCP_FEATURES_FILE             # 近期条目本体（惰性加载，数据外置）
    feats = _load_features()
    if _FEATURES_ERR:
        # 数据文件缺失/损坏：版本号与工具数仍可用，显式给出原因（不静默）
        out['featuresError'] = _FEATURES_ERR
    if compact:
        out['recent'] = [_clip_feature(f) for f in feats[:3]]
        out['note'] = ('默认只回近期 3 条、每条 ≤ %d 字以省 token；近期全量传 compact=False；'
                       '更早版本史（< %s）见 %s'
                       % (COMPACT_FEATURE_CHARS, MCP_FEATURES_ARCHIVE_MAX, MCP_FEATURES_ARCHIVE))
    else:
        out['features'] = feats
    return json.dumps(out, ensure_ascii=False)


# 检索边界（对应 knowledge/uicontrols/retrieval-boundary.md）：未命中时必须明确告知，
# 否则 AI 会转身用通用 web 搜索 / 其它 GUI 框架类推，导致 FlyThings 知识错乱。
NO_HIT_NOTICE = (
    '知识库未收录该主题。禁止用其它 GUI 框架（Qt/Android/Flutter/emWin/AWTK/LVGL 等）'
    '的控件用法类推 FlyThings；请查官方文档 developer.flythings.cn，或转人工/需求方确认后入库。'
)


def _query_tokens(q):
    """查询词元：英文/数字词（≥2）+ 中文二元组（BM25 的整串切词对中文几乎不命中）。"""
    q = (q or '').lower()
    return rs.query_tokens(q)      # 单一实现：切词口径与 BM25 完全一致（v0.27.34）


def _best_coverage(q, texts):
    """命中片段对查询词元的最大覆盖率（**IDF 加权**，0 = 完全没沾边）。

为什么要它：rag_search 的向量路总是返回 top-40 再融合，任何 query（包括
完全不相关）都会有“命中”——仅靠空列表判不出未命中，必须看词覆盖度。

为什么 IDF 加权（v0.27.34）：中文改用字级 bigram 后，「不存在」「主题」这类常见
二字组合在语料里到处都是，不加权会让任何 query 都显得“高覆盖”，把「知识库未收录」
误判成命中（→ AI 转身去 web 猜，正是检索边界规则要防的）。
口径：df ≥ 30% 语料的过泛词元权重记 0；分母 = 词元 IDF 和，分子 = 命中词元 IDF 和。
    """
    toks = _query_tokens(q)
    if not toks:
        return 1.0
    n = len(rs.CHUNKS) or 1
    weights = {}
    total = 0.0
    for t in toks:
        df = rs._df_of(t)
        w = 0.0 if df >= 0.3 * n else math.log(1.0 + (n - df + 0.5) / (df + 0.5))
        weights[t] = w
        total += w
    if total <= 0:
        return 1.0        # query 全是过泛词元（无判别力）→ 无从判定，不误报「未收录」
    best = 0.0
    for t2 in texts:
        tl = (t2 or '').lower()
        best = max(best, sum(w for t, w in weights.items() if w > 0 and t in tl))
    return best / total


_KB_INDEX_CACHE = {}


def _kb_index_map():
    """path → 元数据（status/evidenceLevel/origin），总账索引 + **本地层索引**合并，进程内缓存。

    P0-2：本地层（用户 capture 出来的）必须也能被标注到 origin=local，检索侧才能“本地优先”。
    """
    if 'map' not in _KB_INDEX_CACHE:
        m, err = {}, ''
        try:
            import kb_local as _kbl
            for path, org in ((os.path.join(_kbl.TOTAL_KB, 'kb_index.json'), 'total'),
                              (_kbl.local_index_path(_kbl.kb_dir()), 'local')):
                idx = _kbl.load_json(path)
                for d in (idx.get('docs') or []):
                    if d.get('path'):
                        d.setdefault('origin', org)
                        m[d['path']] = d
                err = err or idx.get('_error', '')
        except Exception as e:                      # 索引读不了不影响检索，只丢标注
            err = repr(e)
        _KB_INDEX_CACHE.update({'map': m, 'err': err})
    return _KB_INDEX_CACHE['map'], _KB_INDEX_CACHE.get('err', '')


_LOCAL_BOOST = 1.15        # 本地层同主题优先（更贴近现场）：仅改排序，不改写分数
_STALE_PENALTY = 0.85     # 过期知识降权（P2 时效）：仅改排序


def _kb_index_entry(path):
    km, _err = _kb_index_map()
    return km.get(path) or {}


def flythings_knowledge_gaps(limit: int = 20, out: str = '', project_root: str = '') -> str:
    """查「知识缺口清单」：用户/AI 反复问但**检索不到**的主题（生长引擎的输入端）。

    触发：知识库缺什么 / 哪些问题搜不到 / 知识缺口
    """
    import kb_local as _kbl
    g = _kbl.gaps(int(limit or 20), kb_override='')
    if out:
        md = _kbl.gaps_markdown(g)
        try:
            os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
            with open(out, 'w', encoding='utf-8', newline='\n') as f:
                f.write(md)
            g['markdown'] = out
        except OSError as e:
            g['warnings'] = g.get('warnings', []) + ['kb_gaps.md 写不了: %s' % e]
    g['logFile'] = g.get('logFile')
    g['nextActions'] = [
        '挑一条缺口 → flythings_knowledge_capture(...)（落本地层候选）',
        '补 evidence（cmd 或 artifact）→ python scripts/kb_verify.py --apply',
        '登记 ≥5 条问法到 scripts/check_retrieval.py 的 GROUPS，跑 --report 取实测阈值',
        '人工签字（reviewed_by）或机器复验（machine_verified_at）后才 status=verified',
    ]
    return json.dumps(g, ensure_ascii=False)


def _annotate_kb_hits(hits):
    """给命中补 `status / evidenceLevel / verifiedAt`（消费侧要看得出「这条验没验过」）。

背景（2026-09-29 提报发现 ②）：首轮迁移把 80/85 篇迁成 `verified + needs_evidence`，
光看 `verified` 会被当成"已验"。`evidenceLevel`: has-evidence（有可执行判据）/ manual-only
    （人工沉淀、无判据）/ none（未验证）。非 verified 或 none 的额外给 `advisory`。
    """
    km, _err = _kb_index_map()
    for h in hits:
        d = km.get(h.get('path'))
        if not d:
            continue
        h['status'] = d.get('status')
        h['evidenceLevel'] = d.get('evidenceLevel')
        h['origin'] = d.get('origin')
        h['verifiedAt'] = d.get('verified_at')
        h['freshness'] = d.get('freshness')
        h['ageDays'] = d.get('ageDays')
        lvl = d.get('evidenceLevel') or ''
        if (d.get('status') or '') != 'verified' or lvl != 'has-evidence':
            h['advisory'] = ('本条状态=%s / 证据等级=%s：可当线索，结论前请核对原文'
                             '或按 evidence 复验（法见 knowledge/devflow/kb-growth.md）'
                             % (d.get('status') or '?', lvl or 'none'))
        if d.get('stale'):
            h['stale'] = True
            h['advisory'] = ('⚠️ 本条已过期（%s 天前验，阈值 %s 天）：结论可能已被版本迭代推翻，'
                             '请先按 evidence 复验' % (d.get('ageDays'), d.get('staleDays') or 180))
        elif d.get('freshness') == 'aging' and not h.get('advisory'):
            h['advisory'] = '本条已接近复验期（%s 天前验），大改前建议复验' % d.get('ageDays')
    return hits


def flythings_knowledge_search(query: str, k: int = 3) -> str:
    """在知识库（wiki 官方镜像 + knowledge 实践文档）检索片段（完全本地，零 Key）。

    触发：查知识库 / 搜一下资料 / 这个怎么做 / 有没有相关文档
    """
    kk = max(1, min(int(k), 8))
    warnings = []
    try:
        degraded = rs._get_embedder() is None
    except Exception:
        degraded = True
    if degraded:
        warnings.append('本地向量模型不可用，已降级 BM25 关键词检索（召回可能变差）')
    try:
        top = rs.search(query, kk)
    except Exception as e:
        return json.dumps({'ok': False, 'op': 'flythings_knowledge_search', 'query': query,
                           'error': {'code': 'SEARCH_FAILED', 'msg': str(e),
                                     'hint': '重试一次；仍失败检查 rag_index.json 与模型文件是否完整',
                                     'retryable': True},
                           'warnings': warnings}, ensure_ascii=False)
    # P0-2：本地层同主题优先（更贴近现场）；P2：**过期降权**（只改排序，不改分数字段）
    _km0, _e0 = _kb_index_map()
    if any(((_km0.get(c.get('path')) or {}).get('origin') == 'local')
           or ((_km0.get(c.get('path')) or {}).get('stale')) for _s, c in top):
        def _w(sc):
            d = _km0.get(sc[1].get('path')) or {}
            f = 1.0
            if d.get('origin') == 'local':
                f *= _LOCAL_BOOST
            if d.get('stale'):
                f *= _STALE_PENALTY
            return float(sc[0]) * f
        top = sorted(top, key=_w, reverse=True)
    hits = _annotate_kb_hits([
        {'path': c['path'], 'score': round(float(s), 4), 'text': c['text'],
         'source': _kb_source_label(c.get('path'))}      # 按索引根真源派生（见 _kb_source_label）
        for s, c in top])
    cover = _best_coverage(query, [c['text'] for _, c in top])
    out = {'ok': True, 'op': 'flythings_knowledge_search', 'query': query, 'count': len(hits),
           'hits': hits, 'coverage': round(cover, 3), 'warnings': warnings,
           'retrieval': 'bm25' if degraded else 'vector+bm25(RRF)',
           'degraded': bool(degraded)}
    # 权威口径提示（v0.27.177）：一条铁律常被十几到三十篇文档各自复述，措辞不同、没有逐字重复，
    # 于是「哪一篇才算权威」不明确。命中已登记概念的别名时附上权威文档，AI 一步知道该信谁去哪核对。
    try:
        import kb_authority as _au
        _auth = _au.for_query(query)
        if _auth:
            out['authority'] = _auth
    except Exception as _e:            # 注册表缺失不该把检索打挂，但要显式带出去（不静默）
        warnings.append('权威口径表不可用（%s: %s）；已按普通检索返回' % (type(_e).__name__, _e))
    if not hits or cover < 0.1:
        # 空命中，或查询词元（IDF 加权后）几乎没沾到 → 按「知识库未收录」处理
        out['quality'] = 'no_hit'
        out['notice'] = NO_HIT_NOTICE
    elif cover < 0.4:
        # 低置信：向量路对任何 query 都会返回 top-N，必须标出来，并同样带上检索边界提醒
        # （否则 AI 会拿着「沾边但不对」的片段当依据，或转身去 web 猜其他框架用法）
        out['quality'] = 'low_confidence'
        out['notice'] = ('低置信命中（查询词元加权覆盖率 %.2f）：片段可能只是话题相近；'
                         '结论前请打开 path 对应文档核对，或换更具体的问法。'
                         '若确认未收录：禁止用 Qt/Android/LVGL/emWin/AWTK 等其它 GUI 框架类推，'
                         '请查官方文档 developer.flythings.cn 或转人工确认。' % cover)
    else:
        out['quality'] = 'ok'
    # 知识生长燃料（P1）：未命中/低置信落**用户本地层**日志（绝不写安装目录），
    # scripts/kb_gaps.py 聚合出「用户真的问不到什么」→ 驱动下一批写作。
    if out['quality'] in ('no_hit', 'low_confidence'):
        try:
            import kb_local as _kbl
            logr = _kbl.log_no_hit(query, out['quality'], [h['path'] for h in hits], kk)
        except Exception as _e:                      # 日志失败不能影响检索本身
            logr = {'logged': False, 'error': repr(_e)}
            warnings.append('未命中日志写入失败（不影响检索）：%s' % _e)
        out['gapLogged'] = bool(logr.get('logged'))
        out['gapLog'] = logr.get('file', '')
        out['gapHint'] = ('本条已记入知识缺口清单（scripts/kb_gaps.py 生成 kb_gaps.md）；'
                          '要补这条知识：flythings_knowledge_capture(...) → 补 evidence → '
                          'scripts/kb_verify.py 复验 → 人工签字后才入库')
    return json.dumps(out, ensure_ascii=False)


def flythings_knowledge_capture(title: str, body: str = '', category: str = 'devflow',
                                platforms: str = '', tags: str = '', evidence: str = '',
                                source: str = '', severity: str = 'normal',
                                project_root: str = '', layer: str = 'local') -> str:
    """把一条现场结论落成知识候选（写**用户本地层/项目层**，绝不写 MCP 安装目录）。

    触发：记条知识 / 这个坑记下来 / 沉淀一条经验 / 存进知识库
    """
    import kb_local as _kbl
    ev = []
    if str(evidence or '').strip():
        try:
            ev = json.loads(evidence)
            if not isinstance(ev, list):
                ev = [ev]
        except ValueError:
            ev = [{'kind': 'manual', 'cmd': str(evidence)}]
    r = _kbl.capture(title, body, category,
                     [x for x in str(platforms or '').split(',') if x.strip()],
                     [x for x in str(tags or '').split(',') if x.strip()], ev,
                     source=source, layer=layer, project_root=project_root,
                     severity=severity)
    return json.dumps(r, ensure_ascii=False)


def flythings_knowledge_export(out: str = '', scope: str = 'inbox', layer: str = 'local',
                               project_root: str = '', internal: bool = False) -> str:
    """导出**脱敏知识补丁包**（回流总账通道 A：kb-contrib-<时间>.json）。

    触发：导出知识包 / 回流知识 / 分享经验
    ⚠️⚠️ **强制脱敏**（IP/本机路径/凭据/主机名 → 占位符）；未脱敏必须显式 internal=True（仅总账维护者自用）。
    """
    import kb_local as _kbl
    return json.dumps(_kbl.export_pack(out, scope, layer=layer, project_root=project_root,
                                       internal=internal), ensure_ascii=False)


def flythings_hardware_info(model: str = '', platform: str = '') -> str:
    """查硬件型号库：按平台/型号拿到分辨率、按键值、接口规格与平台差异化。

    触发：这块屏什么参数 / 板子规格 / 型号是多少 / 按键值 / 硬件差异
    ⚠️⚠️ 平台/分辨率以**用户或型号库**为准；只说型号系列时不要外推（猜错 = 整份工程返工）。
    """
    return json.dumps(hw.query(model, platform), ensure_ascii=False)


# ========== 跨框架控件映射能力（2026-09-16，需求方口径：有一一映射的控件走「映射能力」，不写散文）==========
# 数据唯一来源：mcp_control_map.json（人工维护；来源 = components/ui_v1/control-map.md + gap-list.md
# + knowledge/devflow/gui-controls-gap.md + knowledge/uicontrols/*-fields.md，**冲突以 KB 为准**）。
# 分工：**有平台对应控件 → 本 op（机读索引 + 可粘贴 json 片段）；平台真缺的能力 → components/ui_v1/<包>**。
_CONTROL_MAP_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'mcp_control_map.json')
if getattr(sys, 'frozen', False):          # PyInstaller 打包：随包进 _MEIPASS
    _CONTROL_MAP_PATH = os.path.join(sys._MEIPASS, 'mcp_control_map.json')
_CM_CACHE = {}


def _control_map():
    """读 mcp_control_map.json（带缓存）。文件缺失/坏掉时回 (None, 原因)，不静默。"""
    if 'err' in _CM_CACHE:
        return None, _CM_CACHE['err']
    if 'data' in _CM_CACHE:
        return _CM_CACHE['data'], ''
    try:
        data = json.loads(io.open(_CONTROL_MAP_PATH, encoding='utf-8').read())
    except Exception as e:
        _CM_CACHE['err'] = 'mcp_control_map.json 读取失败（%s: %s）' % (type(e).__name__, e)
        return None, _CM_CACHE['err']
    _CM_CACHE['data'] = data
    return data, ''


# ========== op → 知识文档「去哪找」（2026-09-30；不占 docstring 预算的另一种「指路」）==========
# 数据唯一来源：op_seealso.json（人工维护）。返回体统一加 seeAlso 字段（list[str]），
# 让 AI 拿到工具结果后**直接知道去哪看细节**，不必再自己检索一遍（docstring 预算仅 12000 已顶格）。
# 覆盖度进闸门：scripts/gen_seealso.py --check（每个 op 要么有 seeAlso、要么登记 none + 理由）。
_SEEALSO_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'op_seealso.json')
if getattr(sys, 'frozen', False):          # PyInstaller 打包：随包进 _MEIPASS
    _SEEALSO_PATH = os.path.join(sys._MEIPASS, 'op_seealso.json')
_SA_CACHE = {}


def _seealso_table():
    """读 op_seealso.json（带缓存）。缺失/坏掉 → ({}, 原因)，不静默。"""
    if 'err' in _SA_CACHE:
        return {}, _SA_CACHE['err']
    if 'data' in _SA_CACHE:
        return _SA_CACHE['data'], ''
    try:
        data = json.loads(io.open(_SEEALSO_PATH, encoding='utf-8').read())
    except Exception as e:
        _SA_CACHE['err'] = 'op_seealso.json 读取失败（%s: %s）' % (type(e).__name__, e)
        return {}, _SA_CACHE['err']
    _SA_CACHE['data'] = data.get('ops') or {}
    return _SA_CACHE['data'], ''


def _seealso_for(op):
    """该 op 的「去哪找」列表；未登记或登记为 none 时回 None。"""
    ops, _err = _seealso_table()
    ent = ops.get(op) or {}
    refs = ent.get('seeAlso')
    if isinstance(refs, list) and refs:
        out = [str(x) for x in refs]
        out += ['wiki:' + str(w) for w in (ent.get('wiki') or [])]
        return out
    return None


def _cm_norm(s):
    """控件名归一：小写 + 去下划线/连字符/点/空格/括号（模糊匹配口径，与用户写法无关）。"""
    s = (s or '').lower()
    for ch in '_-./\\ ()[]（）·':
        s = s.replace(ch, '')
    return s


def _cm_score(q, name, aliases):
    """打分：精确 100 / 前缀 80 / 子串 60 / 词元包含 40；别名按同名列一起算（取最高）。"""
    if not q:
        return 0
    best = 0
    for cand in [name] + list(aliases or []):
        n = _cm_norm(cand)
        if not n:
            continue
        if q == n:
            best = max(best, 100)
        elif n.startswith(q) or q.startswith(n):
            best = max(best, 80)
        elif q in n:
            best = max(best, 60 + min(10, len(q)))
        elif len(q) >= 4 and any(t and t in n for t in [q[:4]]):
            best = max(best, 40)
    return best


def flythings_map_control(query: str, source: str = '') -> str:
    """跨框架控件映射：输入源框架控件名 → 一次对上我们的控件（等价级别 + 可直接粘的 json 片段）。

    触发：这个控件对应哪个 / LVGL 的按钮是什么 / 跨框架控件对照
    """
    data, err = _control_map()
    if data is None:
        return json.dumps({'ok': False, 'op': 'flythings_map_control',
                           'error': _err_obj('DATA_MISSING', err, '确认 mcp_control_map.json 随包分发', False),
                           'warnings': [err]}, ensure_ascii=False)
    sources = data.get('sources') or {}
    targets = data.get('targets') or {}
    labels = data.get('sourceLabels') or {}
    src = (source or '').strip().lower()
    if src and src not in sources:
        cands = sorted(sources.keys())
        return json.dumps({'ok': False, 'op': 'flythings_map_control',
                           'error': _err_obj('BAD_SOURCE', '未知 source: %s' % source,
                                             'source 取 ' + ' / '.join(cands) + '（留空 = 全框架搜）', True),
                           'sources': cands, 'warnings': []}, ensure_ascii=False)
    q = _cm_norm(query)
    if not q:
        return json.dumps({'ok': False, 'op': 'flythings_map_control',
                           'error': _err_obj('BAD_PARAMS', 'query 为空',
                                             '传源框架控件名，如 query="lv_slider"（可带 source="lvgl"）', True),
                           'warnings': []}, ensure_ascii=False)
    hits = []
    for sname, arr in sources.items():
        if src and sname != src:
            continue
        for e in arr or []:
            sc = _cm_score(q, e.get('name', ''), e.get('aliases'))
            if sc > 0:
                hits.append((sc, sname, e))
    if not hits:
        names = sorted({e.get('name', '') for a in sources.values() for e in (a or [])})
        near = [n for n in names if q[:3] and q[:3] in _cm_norm(n)][:5] if len(q) >= 3 else []
        msg = '映射表里没有「%s」%s' % (query, ('（限定 %s）' % src) if src else '')
        hint = ('先判是不是「平台真缺的能力」：去 components/ui_v1/components.md 看计划/已实现的自定义控件包'
                '（Chart/Calendar/RadButton 已实现；RichText/TableGrid/BadgeToast/Pseudo3D 计划中；'
                '**滚轮/时间/时钟盘族（WheelPicker·TimePicker 含时钟盘·NumberPicker）已改判 L2 → 不建包，'
                '走 `listview` 组合**，见 knowledge/uicontrols/listview-wheel-picker.md），'
                '再按「缺口五级」处置：L1 等价 / L2 组合 / L3 自绘（须在 ui_v1/gap-list.md 登记编号）/ '
                'L4 降级（写明降级点）/ L5 不支持（明说 + 给替代），**不要临场发明**')
        return json.dumps({'ok': False, 'op': 'flythings_map_control', 'query': query,
                           'error': _err_obj('NO_HIT', msg, hint, False),
                           'candidates': near,
                           'gapPolicy': {'levels': data.get('levels') or {},
                                         'mapForExisting': 'platform 有对应控件 → 用本 op（flythings_map_control）',
                                         'packForMissing': 'platform 真缺 → components/ui_v1/<源控件名>/（四件套 + example + 真机证据）',
                                         'docs': 'components/ui_v1/control-map.md（权威表）/ gap-list.md（G-01~G-36 + T1~T12）/ '
                                                 'components.md（状态表）/ knowledge/uicontrols/control-mapping-capability.md'},
                           'warnings': []}, ensure_ascii=False)
    hits.sort(key=lambda x: (-x[0], len(x[2].get('name', '')), x[1]))
    sc, sname, e = hits[0]
    tgt = e.get('target', '')
    meta = targets.get(tgt) or {}
    out = {'ok': True, 'op': 'flythings_map_control', 'query': query, 'score': sc,
           'source': sname, 'sourceLabel': labels.get(sname, sname),
           'name': e.get('name', ''), 'target': tgt, 'level': e.get('level', ''),
           'levelName': (data.get('levels') or {}).get(e.get('level', ''), ''),
           'notes': e.get('notes', ''), 'json': e.get('json', ''), 'ref': e.get('ref', ''),
           'control': {'caption': meta.get('caption', ''), 'ptr': meta.get('ptr', ''),
                       'note': meta.get('note', '')},
           'warnings': []}
    if sc < 100:
        out['warnings'].append('模糊命中（score=%d）——确认是否你要的控件；要精确匹配请用源控件原名' % sc)
    if len(hits) > 1:
        out['alsoMatched'] = [{'source': s, 'name': x.get('name', ''), 'target': x.get('target', ''),
                               'level': x.get('level', '')} for _, s, x in hits[1:5]]
    if e.get('level') in ('L3', 'L4', 'L5'):
        out['gapHint'] = '该控件不是等价映射：先看 components/ui_v1/gap-list.md 的处置与编号，别现场发明'
    return json.dumps(out, ensure_ascii=False)


def flythings_ui_schema(control_type: str = '', include: str = 'all') -> str:
    """UI 布局 json 规范查询（唯一真源 = ui_schema.json 注册表）：控件字段表/必填键/默认值/类型。

    触发：字段什么意思 / json 有哪些字段 / 控件必填什么 / 布局规范查询
    """
    if _uischema is None:
        return json.dumps({'ok': False, 'op': 'flythings_ui_schema',
                           'error': _err_obj('MODULE_MISSING',
                                             'ui_schema_loader 不可用: %s' % _USC_ERR,
                                             '确认 ui_tools/ui_schema_loader.py 与 ui_schema.json 随包分发', False),
                           'warnings': []}, ensure_ascii=False)
    try:
        reg = _uischema.load()
    except _uischema.SchemaRegistryError as e:
        return json.dumps({'ok': False, 'op': 'flythings_ui_schema',
                           'error': _err_obj('DATA_MISSING', str(e),
                                             '注册表真源 = ui_tools/ui_schema.json（与 loader 同目录）', False),
                           'warnings': []}, ensure_ascii=False)
    ct = (control_type or '').strip().lower()
    if not ct:
        return json.dumps({
            'ok': True, 'op': 'flythings_ui_schema',
            'schemaVersion': reg.get('schemaVersion'), 'updated': reg.get('updated'),
            'controlTypes': [{'type': t, 'interactive': bool(m.get('interactive')),
                              'container': bool(m.get('container'))}
                             for t, m in sorted((reg.get('controls') or {}).items())],
            'subStructures': sorted(reg.get('subStructures') or {}),
            'sharedTypes': sorted(reg.get('sharedTypes') or {}),
            # **视觉保真契约**跟着清单一起来（DESIGN_SPEC 第 1.1 条）：它必须是"设计前就能拿到"的规格，
            # 否则 AI 只能等真机暴露再事后补特例 —— 那正是锯齿/白边这类问题复发 8 次的机制。
            # 这里只带 id/rule/consequence（`scope` 留给按控件查询时带全，避免清单响应过大）。
            'renderContract': [{'id': r.get('id'), 'rule': r.get('rule'),
                                'consequence': r.get('consequence')}
                               for r in (reg.get('renderContract') or {}).get('rows') or []],
            'hint': '指定 control_type 取完整 schema（如 control_type="seekbar"）；'
                    '视觉保真契约（renderContract）是**设计前必读**，判错会出什么缺陷见其 consequence',
            'warnings': []}, ensure_ascii=False)
    entry = (reg.get('controls') or {}).get(ct) or (reg.get('subStructures') or {}).get(ct)
    if entry is None:
        cands = sorted(reg.get('controls') or {})
        return json.dumps({'ok': False, 'op': 'flythings_ui_schema',
                           'error': _err_obj('NO_HIT', '未知控件类型: %s' % control_type,
                                             'control_type 取 ' + ' / '.join(cands)
                                             + '（留空 = 全部类型清单）', True),
                           'controlTypes': cands, 'warnings': []}, ensure_ascii=False)
    used_shared = sorted({spec.get('type') for spec in (entry.get('fields') or {}).values()
                          if spec.get('type') in (reg.get('sharedTypes') or {})})
    out = {'ok': True, 'op': 'flythings_ui_schema', 'controlType': ct,
           'interactive': bool(entry.get('interactive')),
           'container': bool(entry.get('container')),
           'note': entry.get('note', ''),
           'fields': entry.get('fields') or {},
           'requiredFields': _uischema.required_fields(ct),
           'defaults': _uischema.defaults(ct),
           'sharedTypes': {k: reg['sharedTypes'][k] for k in used_shared},
           'valueRules': reg.get('valueRules') or {},
           # 按控件查询时带**全字段**（含 scope）：设计某个控件前要看的就是"哪几条管它"
           'renderContract': (reg.get('renderContract') or {}).get('rows') or [],
           'warnings': []}
    inc = (include or 'all').strip().lower()
    if inc in ('fields', 'schema'):
        keep = ('ok', 'op', 'controlType', 'interactive', 'container', 'note',
                'fields', 'requiredFields', 'defaults', 'warnings')
        out = {k: v for k, v in out.items() if k in keep}
    elif inc in ('sharedtypes', 'types'):
        out = {k: out[k] for k in ('ok', 'op', 'controlType', 'sharedTypes', 'warnings')}
    elif inc in ('valuerules', 'rules'):
        out = {k: out[k] for k in ('ok', 'op', 'controlType', 'valueRules', 'warnings')}
    return json.dumps(out, ensure_ascii=False)


def flythings_translate_ui(source: str, out: str = '', res: str = '',
                           dry_run: bool = None, gen_placeholders: bool = False) -> str:
    """LVGL(v8/v9) C 源码 → FlyThings ui json 迁移翻译（v1，确定性；给 out 就落盘）。

    触发：LVGL 工程迁过来 / 代码转界面 / 迁移翻译 / 换个框架
    """
    return json.dumps(trt.translate(source, out, res, dry_run, gen_placeholders),
                      ensure_ascii=False)


def flythings_read_json(json_path: str) -> str:
    """解析 .json 布局文件为 JSON（分辨率、控件列表、caption→id 映射）。传入 json 完整路径。

    触发：界面结构 / 有哪些控件 / 读一下 json / 控件列表
    """
    return json.dumps(pt.flythings_read_json(json_path), ensure_ascii=False)


def flythings_get_project_spec() -> str:
    """返回 FlyThings 项目结构化规范（目录规则、生成规则、注意事项）。编写/修改项目代码前调用。新需求先出设计稿/原型并确认。

    触发：工程规范 / 目录怎么放 / 写代码前看什么 / 项目结构 / 注意事项
    ⚠️⚠️ **没读过规范不许开始写** `ui/*.json` 或业务代码 —— 目录规则/生成规则/注意事项都在这里。
    """
    return json.dumps(pt.flythings_get_project_spec(), ensure_ascii=False)


def flythings_validate_project(project_root: str) -> str:
    """检查项目是否符合 FlyThings 规范，返回 errors/warnings。生成代码后调用。

    触发：检查工程 / 项目有没有问题 / 规范体检 / 体检一下项目
    """
    return json.dumps(pt.flythings_validate_project(project_root), ensure_ascii=False)


def _with_files(obj, *paths):
    """给写操作返回体补 affectedFiles（去重、去空、绝对路径）。"""
    if not isinstance(obj, dict):
        return obj
    files = []
    for p in list(obj.get('affectedFiles') or []) + list(paths):
        if not p:
            continue
        ap = os.path.abspath(p)
        if ap not in files:
            files.append(ap)
    if files:
        obj['affectedFiles'] = files
    return obj

def flythings_layout_audit(project_root: str, page: str = '') -> str:
    """静态审计 UI 布局的层叠/遮挡/触摸穿透（**纯几何，0 token，先看 json 再截图**）。

    触发：布局有没有问题 / 控件被遮住 / 点不动 / 触摸穿透 / 越界
    """
    return json.dumps(pt.flythings_layout_audit(project_root, page), ensure_ascii=False)


def flythings_fui_pack(json_path: str) -> str:
    """将 json 布局打包为 ftu（设备实际加载的是 ftu）。返回 ftu 路径、控件数、分辨率。

    触发：打包界面 / json 打成 ftu / 改了 json 要生效
    ⚠️⚠️ ftu 是 json 布局的**编译产物**：改布局一律改 json 后 pack，**不要手写/手改 ftu**（json 才是源）。
    """
    r = pt.flythings_fui_pack(json_path)
    if isinstance(r, dict):
        r.update(_confirm_gate(_project_root_of(json_path), json_path))
    return json.dumps(_with_files(r, r.get('ftuPath')), ensure_ascii=False)


def flythings_fui_unpack(ftu_path: str, output_json: str = '', overwrite: bool = True) -> str:
    """ftu → json 反解析（fui unpack；随包 fui 自 v0.27.91 起支持）。

    触发：反解析 / ftu 转 json / 看看 ftu 里有什么
    """
    r = pt.flythings_fui_unpack(ftu_path, output_json, overwrite)
    return json.dumps(_with_files(r, r.get('jsonPath')), ensure_ascii=False)




def flythings_edit_ftu(ftu_path: str, operations: str, output_ftu: str = '',
                       overwrite: bool = False) -> str:
    """编辑 ftu 布局：自动应用编辑到 json 后 pack 回 ftu（json 是源，ftu 是编译产物）。

    触发：改布局 / 按钮往右移 / 改个文字 / 换个颜色 / 删掉这个控件 / 复制控件
    """
    r = pt.flythings_edit_ftu(ftu_path, operations, output_ftu, overwrite)
    return json.dumps(_with_files(r, r.get('ftuPath'), r.get('jsonPath'), r.get('backup')),
                      ensure_ascii=False)


def flythings_device_preflight(project_root: str, device: str = '', adapt: str = 'ask',
                               font_check: str = 'auto', font_tier: str = '',
                               font_apply: bool = True) -> str:
    """上机前体检：设备发现→型号/平台确认→分辨率/字库/体积三项判据（launch 前自动跑同一套）。

    触发：上机前检查 / 接上设备先看什么 / 这板子能不能跑 / 屏幕对不对 / 字库够不够 / 打包会不会超 / 屏比设计小 / 屏幕比设计小 / 分辨率不一样
    """
    r = pt.flythings_device_preflight(project_root, device, adapt, font_check, font_tier,
                                      font_apply)
    files = [os.path.join(project_root, f)
             for f in ((r.get('adapted') or {}).get('files') or [])]
    return json.dumps(_with_files(r, *files), ensure_ascii=False)


def flythings_build_ui_flow(project_root: str, with_launch: bool = True, device: str = '',
                            font_check: str = 'auto', font_tier: str = '') -> str:
    """FlyThings UI 构建与部署全流程（pack → install → build → 设备探测 → launch）。

    触发：编译 / 构建 / 调试 / 部署 / 推送到设备 / 跑一下 / 上机 / 传到设备 / 烧上去
    """
    return json.dumps(_with_design_warning(
        pt.flythings_build_ui_flow(project_root, with_launch, device,
                                   font_check, font_tier), project_root),
        ensure_ascii=False)


def flythings_pack_upgrade(project_root: str, out_path: str = '', release_version: str = '',
                           ab: bool = False, with_build: bool = False,
                           dry_run: bool = False) -> str:
    """固化升级包（update.img）——交付/发布/量产走本条；与「调试推送到设备」不同（那是 build_ui_flow，掉电即失）。

    触发：打包升级包 / 出升级包 / 固化 / 刷进设备 / 出货版本 / TF卡升级包 / 刷机
    """
    return json.dumps(pt.flythings_pack_upgrade(project_root, out_path, release_version,
                                                ab, with_build, dry_run),
                      ensure_ascii=False)



def _project_root_of(json_path):
    """从 ui/*.json 反推项目根（找包含 ui/ 或 Manifest.xml 的最近上级）。"""
    p = os.path.abspath(json_path or '')
    d = os.path.dirname(p)
    for _ in range(4):
        if os.path.isdir(os.path.join(d, 'ui')) or os.path.isfile(os.path.join(d, 'Manifest.xml')):
            return d
        nd = os.path.dirname(d)
        if nd == d:
            break
        d = nd
    return os.path.dirname(p)


def _newest(paths, errs=None):
    """[(mtime, path)] → (最大 mtime, 对应 path)；空列表 → (0.0, '')。

    errs 传 list 时，把「读 mtime 失败」的文件名记进去（上层回给调用方，不静默吞）。
    """
    mt, who = 0.0, ''
    for p in paths:
        try:
            m = os.path.getmtime(p)
        except OSError as e:
            if errs is not None:
                errs.append('%s (%s)' % (os.path.basename(p), type(e).__name__))
            continue
        if m > mt:
            mt, who = m, p
    return mt, who


def _confirm_gate(project_root, json_path=''):
    """确认闸门（2026-09-30 SmartPanel 检讨）：布局改完 → 项目里有没有**更新**的确认稿？

只提醒、不阻塞（与「写操作默认安全」同一纪律）：回 confirmNeeded + confirmHint。
确认稿 = flythings_ui_preview(for_customer=True) 的 `.confirm.html`（或 .preview.html / _edit/*.edit.html）。
    """
    out = {'confirmNeeded': None, 'confirmDraft': '', 'confirmHint': ''}
    try:
        root = os.path.abspath(project_root or '') or _project_root_of(json_path)
        uroot = os.path.join(root, 'ui')
        if not os.path.isdir(uroot):
            return out
        drafts, jsons, skipped = [], [], []
        for dp, _dn, fn in os.walk(uroot):
            for f in fn:
                p = os.path.join(dp, f)
                if f.endswith(('.confirm.html', '.preview.html', '.edit.html')):
                    drafts.append(p)
                elif f.endswith('.json'):
                    jsons.append(p)
        if json_path and os.path.isfile(json_path):
            jsons.append(os.path.abspath(json_path))
        t_json, jm = _newest(jsons, skipped)
        t_draft, dm = _newest(drafts, skipped)
        out['confirmDraft'] = dm
        out['confirmNeeded'] = bool(t_json and (not dm or t_draft < t_json))
        if out['confirmNeeded']:
            out['confirmHint'] = (
                '布局已改（%s）但没有**更新**的确认稿 → 先出确认稿给需求方确认，再 pack / 推真机：'
                'flythings_ui_preview(target="%s", for_customer=True)（单文件 .confirm.html，'
                '手机可打开、带控件标注）；口径见 knowledge/devflow/ui-layout-verify.md §0'
                % (os.path.basename(jm or ''), root))
        else:
            out['confirmHint'] = ('已有确认稿 %s，可直接 pack/推真机（再改布局记得重出确认稿）'
                                  % os.path.basename(dm or ''))
        if skipped:
            out['confirmWarnings'] = skipped
    except Exception as e:                                # noqa: BLE001
        out['confirmHint'] = '确认闸门未跑成：%s' % e
    return out


def _asset_audit(project_root):
    """出图后自动跑资产审计（抗锯齿 / 弧线过渡 / 倒角 / 透明底）；缺工具如实回报，不静默。"""
    out = {'ran': False, 'status': 'skip', 'hint': '', 'checks': []}
    if chk_all is None:
        out['hint'] = ('ui_tools/check_all.py 不可用，审计没跑；手跑 tools/qa/{aa_audit,corner_audit}.py')
        return out
    jobs = (('aa', lambda: chk_all.check_aa_assets(project_root)),
            ('arc', lambda: chk_all.check_arc_quality(project_root)),
            ('corner', lambda: chk_all.check_shape_audit(project_root, 'corner')),
            ('alphaBg', lambda: chk_all.check_shape_audit(project_root, 'alpha')))
    for name, fn in jobs:
        try:
            r = fn() or {}
        except Exception as e:                            # noqa: BLE001
            out['checks'].append({'check': name, 'status': 'error', 'reason': str(e)})
            continue
        item = {'check': name, 'status': r.get('status') or 'skip',
                'defect': len(r.get('defect') or []), 'warn': len(r.get('warn') or [])}
        if item['status'] == 'skip':
            item['reason'] = r.get('reason', '')
        out['checks'].append(item)
    ran = [c for c in out['checks'] if c['status'] not in ('skip', 'error')]
    out['ran'] = bool(ran)
    if any(c.get('defect') or c['status'] == 'fail' for c in out['checks']):
        out['status'] = 'fail'
        out['hint'] = ('有 DEFECT（逐条看 checks 的 defect 数）→ 按 knowledge/devflow/ui-asset-rules.md '
                       '#11~#13 修图后重出；⚠️ 纯二值资产（二维码/条形码那种只有两种颜色的图）会被抗锯齿'
                       '审计判 hard_diag，属预期，需在审计规则里登记豁免而不是改图')
    elif ran:
        out['status'] = 'ok'
        out['hint'] = '抗锯齿/弧线过渡/倒角/透明底审计通过（WARN 逐条列在 checks，不阻塞但别忽略）'
    else:
        out['hint'] = ('审计脚本没找到（tools/qa/*.py 不在搜索路径）→ 手跑 '
                       'python tools/qa/aa_audit.py <项目>/resources/images --fail')
    return out


def _with_confirm_gate(r, json_path='', project_root=''):
    """把确认闸门结果合进返回体（解析不了/不是 dict 就原样回）。"""
    if not isinstance(r, dict):
        return r
    if not project_root:
        p = os.path.abspath(json_path) if json_path else ''
        if p and os.path.isdir(p):                    # 传的是项目根/目录
            project_root = p
        elif p and os.path.isdir(os.path.join(os.path.dirname(p), 'ui')):
            project_root = os.path.dirname(p)
    r.update(_confirm_gate(project_root, json_path))
    return r


def flythings_ui_preview(target: str, output_dir: str = '', for_customer: bool = False) -> str:
    """json 布局 / 整个项目 → HTML 预览稿（客户确认 UI 用；只交 html，不产图片/截图）。

    触发：出预览稿 / 给客户看效果 / 客户确认 / 预览页面 / 出个预览稿 / 客户确认稿
    """
    is_dir = os.path.isdir(target)
    r = j2h.json2html(target, output_dir, for_customer=bool(for_customer))
    if is_dir and isinstance(r, dict) and r.get('success'):
        for f in r.get('files', []):
            jp = os.path.join(target, 'ui', f.get('json', ''))
            if os.path.isfile(jp):
                try:
                    with open(jp, encoding='utf-8-sig') as fh:
                        data = json.load(fh)
                    # A7 修（2026-09-27）：递归计数（旧版只数根层 → 50 控件页面报 controls:1）
                    def _count_list(dd, acc):
                        for k, v in dd.items():
                            if k.startswith('__'):
                                continue
                            if isinstance(v, dict) and '__' in k:
                                acc[0] += 1
                                _count_list(v, acc)
                            if isinstance(v, list):
                                for x in v:
                                    if isinstance(x, dict):
                                        _count_list(x, acc)
                        return acc[0]

                    top = sum(1 for k, v in data.items()
                              if isinstance(v, dict) and not k.startswith('__') and '__' in k)
                    total = _count_list(data, [0])
                    f['controls'] = total
                    f['controlsTopLevel'] = top
                    f['controlsNested'] = max(total - top, 0)
                except Exception:
                    pass
        r['projectRoot'] = target
        r['outputDir'] = output_dir or os.path.join(target, 'ui')
        r['forCustomer'] = bool(for_customer)
        r['note'] = ('html 为客户预览稿；设备端仍用 fui pack 生成的 ftu，两者同源于 json' +
                     ('；**客户确认稿**：单文件可发微信/手机打开，点「标注」看控件名与尺寸'
                      if for_customer else ''))
    return json.dumps(_with_confirm_gate(r, target), ensure_ascii=False)


def flythings_html_to_json(input_html: str, output_json: str = '', res: str = '',
                           merge_windows: bool = False) -> str:
    """受限 HTML 交互原型 -> ui/*.json（CSS 效果自动转图；产物尺寸 == 控件盒）。

    触发：原型变界面 / HTML 转 json / 设计稿落地 / 网页稿转界面 / 把原型变成界面 / 设计稿转界面
    """
    out = h2j.html2json(input_html, output_json or None, res or None,
                        merge_windows=bool(merge_windows))
    hint = _render_path_hint(input_html)
    if hint and isinstance(out, dict):
        out['pathHint'] = hint
    return json.dumps(out, ensure_ascii=False)


def flythings_list_packages(platform: str = '') -> str:
    """列出依赖包生态（platform 如 F133/Z20，留空列全部），含功能描述与版本。写代码前调用。

    触发：有哪些包 / 内置包清单 / 能用什么库
    """
    r = pkgtools.flythings_list_packages(platform or None)
    if platform and isinstance(r, dict):
        info = _platforms.resolve(platform) or {}
        if info and not info.get('buildable'):
            # 「仅依赖包生态」平台：只能查包/取包，**不能建工程与编译**
            r['packageOnly'] = True
            r['notice'] = ('%s 属「仅依赖包生态」平台：只能查/取依赖包，'
                           '**不支持 create_project / build_ui_flow**（别在这些平台上试建工程）'
                           % (info.get('name') or platform))
    return json.dumps(r, ensure_ascii=False)


def flythings_query_package(package: str, platform: str = _platforms.DEFAULT_PLATFORM) -> str:
    """查询依赖包在指定平台的可用版本。传入包名（如 mqtt-cxx）与平台。

    触发：这个包什么版本 / 平台支不支持 / 版本号多少
    """
    return json.dumps(pkgtools.flythings_query_package(package, platform), ensure_ascii=False)


def flythings_manifest(features: str, platform: str = _platforms.DEFAULT_PLATFORM, project_root: str = '',
                       dry_run: bool = True) -> str:
    """按功能需求准备 Manifest.xml 依赖配置（**默认只推荐、不写盘**）。

    触发：依赖清单 / Manifest 怎么写 / 要哪些包
    """
    flist = [f.strip() for f in str(features).split(',') if f.strip()]
    if dry_run:
        r = pkgtools.flythings_generate_manifest(flist, platform)
        if isinstance(r, dict):
            r['dryRun'] = True
            r['hint'] = ('dry_run=True 只推荐不写盘；确认后用 dry_run=False + project_root 写入 Manifest.xml，'
                         '或逐个用 flythings_add_package 追加并 fun install')
        return json.dumps(r, ensure_ascii=False)
    if not project_root:
        return json.dumps({'ok': False, 'op': 'flythings_manifest',
                           'error': {'code': 'BAD_PARAMS',
                                     'msg': 'dry_run=False 时必须提供 project_root',
                                     'hint': '先 dry_run=True 看推荐，确认后传 project_root 写入',
                                     'retryable': True}, 'warnings': []}, ensure_ascii=False)
    gen = pkgtools.flythings_generate_manifest(flist, platform)
    if not (isinstance(gen, dict) and gen.get('success') and gen.get('manifest')):
        return json.dumps({'ok': False, 'op': 'flythings_manifest',
                           'error': {'code': 'GENERATE_FAILED',
                                     'msg': '生成 Manifest 失败: %s' % (gen.get('error') if isinstance(gen, dict) else gen),
                                     'hint': '', 'retryable': False}, 'warnings': []}, ensure_ascii=False)
    root = os.path.abspath(project_root)
    if not os.path.isdir(root):
        return json.dumps({'ok': False, 'op': 'flythings_manifest',
                           'error': {'code': 'NO_PROJECT', 'msg': '项目目录不存在: %s' % root,
                                     'hint': '', 'retryable': False}, 'warnings': []}, ensure_ascii=False)
    target = os.path.join(root, 'Manifest.xml')
    backup = ''
    if os.path.isfile(target):
        backup = target + '.bak'
        shutil.copy2(target, backup)      # 写前必备份（破坏性默认值收口）
    io.open(target, 'w', encoding='utf-8', newline='\n').write(gen['manifest'])
    out = dict(gen)
    out.update({'dryRun': False, 'manifestPath': target, 'backup': backup,
                'affectedFiles': [target] + ([backup] if backup else []),
                'hint': 'Manifest 已写盘；依赖拉取请接着调 flythings_add_package（with_install=True）'
                        '或项目内 fun install'})
    return json.dumps(out, ensure_ascii=False)
def flythings_add_package(project_root: str, package: str, version: str = '',
                          platform: str = '', with_install: bool = True) -> str:
    """把 package 添加进项目 Manifest.xml 并执行 fun install 拉取依赖（添加包闭环流程）。

    触发：加包 / 装个包 / 引入依赖 / 这个包怎么加进工程 / 加个包 / 加个 mqtt 包
    """
    return json.dumps(pkgtools.flythings_add_package(project_root, package,
                                                     version or None,
                                                     platform or None,
                                                     with_install), ensure_ascii=False)




def flythings_package_search(keyword: str, platform: str = _platforms.DEFAULT_PLATFORM) -> str:
    """按功能关键词搜索可用 package（mqtt/json/http/ssl/ble/ota/audio 等）。

    触发：有没有现成的包 / 找库 / 支持 mqtt 的包 / 有没有 http 库 / 找个库
    """
    return json.dumps(pkgtools.flythings_search_package(keyword, platform), ensure_ascii=False)


def flythings_get_package_api(package_id: str, platform: str = _platforms.DEFAULT_PLATFORM,
                              version: str = '', focus: str = '') -> str:
    """获取 package 的头文件路径、类方法签名、使用示例。传入包名与可选版本。

    触发：这个包怎么用 / 包的 API / 有哪些方法 / 看头文件
    ⚠️⚠️ **注册表没有 ≠ 平台没有**：设备 /lib 自带 nanovg / libpng12 / freetype / jpeg / mad / zlib，可 dlopen 免编译（先 `adb shell ls /lib` 核一遍）。
    """
    return json.dumps(pkgtools.flythings_get_package_api(package_id, platform,
                                                         version or None, focus or ''),
                      ensure_ascii=False)


def flythings_resolve_dependencies(packages: str, platform: str = _platforms.DEFAULT_PLATFORM) -> str:
    """递归解析 package 依赖树并检测冲突。packages 为 JSON 数组字符串，如 '[{"id":"mqtt-cxx","version":"3.2.0"}]'。返回依赖树、解析结果与冲突建议。

    触发：依赖冲突 / 依赖树 / 循环依赖
    """
    return json.dumps(pkgtools.flythings_resolve_dependencies(packages, platform), ensure_ascii=False)


def flythings_create_bin_project(project_root: str, project_name: str = '', platform: str = _platforms.DEFAULT_BIN_PLATFORM,
                                 app_version: str = '1.0.0', description: str = '',
                                 with_build: bool = True) -> str:
    """创建「可执行程序」项目（fun create --type bin）并编译为直接可运行的 ELF 二进制。

    触发：做个小工具 / 命令行程序 / 不要界面 / 可执行文件 / bin 工程
    """
    return json.dumps(pt.flythings_create_bin_project(
        project_root, project_name, platform, app_version, description, with_build),
        ensure_ascii=False)


def flythings_gen_logic_stub(project_root: str, page: str = '', dry_run: bool = False) -> str:
    """按 ui/*.json 的控件表补齐 logic 回调桩（只补不改，不写业务）。

    触发：补回调函数 / 按钮点击事件 / 写业务之前 / 生成骨架 / 回调桩 / 补上按钮点击回调 / 回调怎么补 / 补回调桩 / 缺回调怎么办 / 那个回调没生成
    """
    return json.dumps(lt.gen_logic_stub(project_root, page, dry_run), ensure_ascii=False)


def flythings_gen_ui_test(project_root: str, test_type: str = 'ask', output_dir: str = '',
                          platform: str = _platforms.DEFAULT_BIN_PLATFORM, with_build: bool = True,
                          monkey_count: int = 500) -> str:
    """根据 UI json 布局生成自动化测试项目（纯代码，不依赖 AI，省 token）。

    触发：生成测试用例 / 自动测界面 / UI 回归脚本 / 触摸测试
    """
    return json.dumps(tt.flythings_gen_ui_test(
        project_root, test_type, output_dir, platform, with_build, monkey_count),
        ensure_ascii=False)


def flythings_test_run(plan: str = '', devices: str = 'auto', project_root: str = '',
                       out: str = '', platform: str = '', parallel: int = 4,
                       baseline: str = 'auto', allow_regions: int = 0,
                       per_device_keys: str = 'auto') -> str:
    """多设备**并行**跑一份 UI 用例（触摸注入+日志断言+像素基线），出 JSON + JUnit 报告。

    触发：跑测试 / 自动化回归 / 并行测多台 / UI 测试
    ⚠️⚠️ **比不到基线记 no-baseline，不算通过** —— 不许把 no-baseline 步骤报成「通过」。
    """
    return json.dumps(tt.flythings_test_run(plan, devices, project_root, out, platform,
                                            parallel, baseline, allow_regions,
                                            per_device_keys),
                      ensure_ascii=False)


def flythings_attach_cli_tools(project_root: str) -> str:
    """复制 fui.exe（→项目 ui/）与 fun.exe（→项目根目录）到项目，随项目交付。

    触发：装工具链 / 项目里没有 fun.exe / 缺 fui.exe / 交付要带编译工具
    ⚠️⚠️ src/activity/ 目录（mainActivity.cpp/h）由 IDE 编译时自动生成，禁止创建/修改；业务代码只写 src/logic/*.cc。
    """
    return json.dumps(pt.flythings_attach_cli_tools(project_root), ensure_ascii=False)


# ===== 设计先行软闸门（v0.27.101）=====
# 背景（2026-09-21 口径 A）：用户没给设计流程/界面时，AI 必须先走「原型设计 -> 界面设计 ->
# 用户确认」再建工程；意图闸门负责在 prompt 侧拦，这里负责在**开干类工具**侧留痕。
# 口径：**只读检测 + 只加 warnings，不改 success 语义、不阻断**（避免破坏既有调用与用例）。
_DESIGN_HINT = (
    '未检测到设计确认稿：若是新需求，请先走原型设计/界面设计流程'
    '（prototype-flow：功能拆解 -> 页面树 -> 线框图 -> 确认稿 -> 确认后再建工程）'
)
# 设计产物识别：design/ 等目录、任意 *.html（线框图/美化稿/确认稿）、*.preview.html 等
_DESIGN_DIRS = ('design', 'designs', 'prototype', 'wireframe', 'mockup')
# ⚠️ 构建产物目录**两代都要跳**：09-28 版 fun 起产物由 `<项目>/.fun/` 改名 `.fsc/`
# （唯一真源 = project_tools.BUILD_DIR_NAMES，这里用字面量是因为本判断要能在不 import
#  project_tools 的前提下用）。只写 `.fun` = 对新工具链工程**等于完全没跳** ——
#  `.fsc/**` 里任何 `.html`/preview 文件都会被当成设计产物，从而**静默抑制**设计先行提示
# （2026-10-03 与 preflight 体积口径同一漏改一起修正）。
_DESIGN_WALK_SKIP = {'.git', '.fsc', '.fun', 'Release', '__pycache__', 'node_modules', '.settings'}


def _has_design_artifacts(root):
    """项目目录内是否已有设计产物（design/ 目录 / *.html / *.preview.html / 设计稿类文件）。

只读、只扫一层浅目录树（跳过构建产物）。任何异常一律当作「有设计」（不提示），
保证这个提示永远不会变成新的失败点。
    """
    try:
        root = str(root or '').strip()
        if not root or not os.path.isdir(root):
            return True          # 目录还不存在（工具自己会报错）-> 不提示
        for d in _DESIGN_DIRS:
            if os.path.isdir(os.path.join(root, d)):
                return True
        for base, dirs, files in os.walk(root):
            dirs[:] = [x for x in dirs if x not in _DESIGN_WALK_SKIP]
            for f in files:
                low = f.lower()
                if low.endswith(('.html', '.htm', '.wireframe')) or 'preview' in low:
                    return True
        return False
    except Exception:
        return True


def _with_design_warning(res, root):
    """给「开干类」返回值追加设计先行软提示（只 push warnings，不动其它键）。

失败路径（success/ok 显式为 False）不加：失败原因本身才是要看的，别塞噪音。
    """
    try:
        if (isinstance(res, dict) and res.get('success') is not False
                and res.get('ok') is not False and not _has_design_artifacts(root)):
            w = list(res.get('warnings') or [])
            w.append(_DESIGN_HINT)
            res['warnings'] = w
    except Exception:
        return res
    return res


def flythings_create_project(project_root: str, platform: str, resolution: str,
                             app_name: str = '', with_cli: bool = True, force: bool = False) -> str:
    """从 HelloWord 模板创建 FlyThings 项目，自动替换工程名/分辨率/平台。

    触发：新建工程 / 建个项目 / 从零开始 / 起个新项目 / 建 FlyThings 工程 / 从头做
    ⚠️⚠️ src/activity/ 由 IDE 按 ftu 生成，禁止创建/修改/覆盖；业务只写 src/logic/*.cc
    ⚠️⚠️ 新需求必须先出设计稿/原型并让用户确认（见 prototype-flow）再建工程 —— 跳过确认 = 返工
    """
    return json.dumps(_with_design_warning(
        pt.flythings_create_project(project_root, platform, resolution,
                                    app_name, with_cli, force), project_root),
        ensure_ascii=False)


def flythings_check_project_deps(project_root: str, platform: str = _platforms.DEFAULT_PLATFORM,
                                device: str = '', font_check: str = 'auto', font_tier: str = '',
                                font_apply: bool = False) -> str:
    """扫描项目 include 的三方库与 Manifest 声明对比，返回缺失依赖。

    触发：依赖对不对 / 缺哪些库 / include 找不到 / 查依赖
    """
    return json.dumps(pkgtools.flythings_check_project_deps(
        project_root, platform, device, font_check, font_tier, font_apply), ensure_ascii=False)


def flythings_generate_ui_assets(project_root: str, assets: str) -> str:
    """生成 UI 图片资源（图标/牌面/按钮背景等）→ <项目>/resources/images/（json 引用写 images/xxx.png）。

    触发：生成图标 / 出图 / 做个按钮背景图 / 要一套图标
    """
    res = h2j_genres.gen_ui_assets(project_root, assets)
    if isinstance(res, dict):
        res['assetAudit'] = _asset_audit(project_root)
    return json.dumps(res, ensure_ascii=False)


def flythings_i18n_scan(project_root: str) -> str:
    """诊断项目多语言（i18n）现状：i18n/*.tr 语言文件、key 对齐、布局 @key 引用完整性。

    触发：多语言有没有问题 / 检查翻译 / key 对不齐
    """
    return json.dumps(itx.flythings_i18n_scan(project_root), ensure_ascii=False)


def flythings_i18n_add_language(project_root: str, lang: str, lang_name: str, base_lang: str = 'zh_CN', context: str = '') -> str:
    """添加新语言：从基础语言（缺省 zh_CN）复制 key 骨架，生成 i18n/<lang>-<lang_name>.tr 待翻译文件。

    触发：加个语言 / 支持英文 / 多语言加一种 / 加英文 / 加一门语言 / 加个语种 / 要英文
    """
    return json.dumps(itx.flythings_i18n_add_language(project_root, lang, lang_name, base_lang, context), ensure_ascii=False)


def flythings_i18n_export(project_root: str, lang: str = 'zh_CN', keys: str = '', context: str = '') -> str:
    """导出指定语言（缺省 zh_CN）的 key→文本清单（JSON），供翻译后 import 写回。

    触发：导出翻译 / 把文案给翻译 / 导出语言包 / 导出给翻译 / 文案导出 / 导出文案
    """
    return json.dumps(itx.flythings_i18n_export(project_root, lang, keys, context), ensure_ascii=False)


def flythings_i18n_import(project_root: str, lang: str, translations: str, merge: bool = True) -> str:
    """将翻译结果写回项目 i18n/<lang>.tr（生成新语言文件或更新已有）。

    触发：翻译好了 / 导入翻译 / 把译文写回去
    """
    r = itx.flythings_i18n_import(project_root, lang, translations, merge)
    try:
        r2 = json.loads(r) if isinstance(r, str) else r
    except Exception:
        return r if isinstance(r, str) else json.dumps(r, ensure_ascii=False)
    if isinstance(r2, dict):
        _with_files(r2, r2.get('path'), r2.get('trPath'))
    return json.dumps(r2, ensure_ascii=False)


def flythings_i18n_refactor(project_root: str, lang: str = 'zh_CN', dry_run: bool = True) -> str:
    """把布局 json 里写死的非空文本控件替换为 @key 引用（多语言改造辅助）。

    触发：多语言改造 / 写死的文字改成 key / 文案抽出来
    """
    return json.dumps(itx.flythings_i18n_refactor(project_root, lang, dry_run), ensure_ascii=False)


def flythings_i18n_to_json(project_root: str, langs: str = '', push: bool = True, device: str = '') -> str:
    """把 i18n/*.tr 转为 i18n/*.json（设备 zkgui 实际加载格式），并可推送到设备 /tmp/tr/。

    触发：推翻译 / tr 转 json / 翻译不生效 / 界面还是旧文案
    """
    return json.dumps(itx.flythings_i18n_to_json(project_root, langs, push, device), ensure_ascii=False)


# ── UI 可视化三合一（v0.27.37：ui-visual 组做成一个带 action 的入口）──────────────
# 旧 op flythings_ui_editor / flythings_ui_edit_apply / flythings_ui_diff 已并入
# flythings_ui_visual(action=...)（见 RENAMED）；下面是三个动作的内层实现，不再单独注册。
def _ui_editor(project_root: str, output_dir: str = '') -> str:
    """把 ui/*.json 生成「可视化编辑器」网页：拖控件就改布局（输出 <项目>/ui/_edit/<name>.edit.html）。

闭环第二步：AI 出/改 json → 本工具出编辑器给用户拖 → 用户点「复制 AI 指令」
    （自带工程路径 + 目标 json + 变更 JSON 的一段话）直接粘给 AI，或「复制变更 JSON」拿纯 json →
    flythings_ui_visual(action="edit_apply") 写回 json + pack ftu。页面是本地静态文件、无回传通道，只能复制粘贴。
预览与设备同源（都来自 json），改完即所得。

页面能力（点选/拖动/8 手柄缩放、方向键微调、网格吸附、Alt+点穿透选中下层、被遮罩控件也能拖、
控件列表搜索、visible:false 幽灵框、属性栏列出全部字段、图片尺寸预检红黄标、深链接 #button__2）
见知识库「UI 可视化编辑器 用法与能力」，检索：可视化编辑器 / Alt 点穿透 / 属性栏 / 拖完怎么回 json。
    output_dir 缺省 <项目>/ui/_edit。
    """
    if uied is None:
        return json.dumps({'success': False, 'error': 'ui_editor 不可用（缺 ui_tools/ui_editor.py 或 Pillow）'},
                          ensure_ascii=False)
    try:
        r = uied.make_editor(project_root, output_dir)
    except Exception as e:
        return json.dumps({'success': False, 'error': str(e)}, ensure_ascii=False)
    if isinstance(r, dict) and r.get('success'):
        r['projectRoot'] = project_root
        r['note'] = ('在浏览器打开 *.edit.html 拖动/改属性；改完点「复制 AI 指令」，把指令（自带工程路径 + '
                     '目标 json + 变更 JSON）直接粘给 AI，AI 用 flythings_ui_visual(action="edit_apply") 写回 json'
                     '（默认不动 ftu，要 ftu 就说 pack）；只想要纯 json 就点「复制变更 JSON」/「下载变更 JSON」。'
                     '⚠️ 页面是本地静态文件、没有回传通道，必须复制粘贴给 AI')
        for f in r.get('files', []):
            if f.get('html'):
                f['open'] = f['html']
    return json.dumps(r, ensure_ascii=False)


def _ui_edit_apply(project_root: str, changes: str, pack: bool = False,
                   dry_run: bool = False) -> str:
    """把 ui_editor 导出的「变更 JSON」写回 ui/*.json（**默认不 pack、可先 dry_run 预览**）。

    changes：可直接传 JSON 文本（用户从编辑器复制过来的），也可传文件路径。
结构：
        {"file": "main.json", "resolution": "1600x600",
         "changes": {"button__1": {"left": 130, "top": 60, "width": 150, "height": 54}},
         "props":   {"textview__4": {"text": "新文字", "fontSize": 22,
                                     "colorTab": {"color0": 16711680}}}}
控件路径：顶层 "button__1"；嵌套 window 内 "window__2/button__3"。
    changes = 几何（position 四项）；props = 其它属性（深合并写回）；两者都可省。
    ⚠️ 破坏性默认值收口（v0.27.32）：pack 默认 False（确认布局无误后再显式传 pack=True）；
    dry_run=True 只回「将要改什么」的预览（不写盘、不 pack）。

安全：① 写回前自动备份 <name>.json.bak；② 格式一致性自检（原文件必须能被
    json.dumps(indent=2, ensure_ascii=False) 无损还原，否则拒绝写入以免整文件重排）；
    ③ 坐标取整 + 不越出屏幕；④ 返回 affectedFiles 与 .bak 路径，便于回滚/审计。
    """
    if uia is None:
        return json.dumps({'success': False, 'error': 'ui_edit_apply 不可用'}, ensure_ascii=False)
    text = (changes or '').strip()
    tmp = ''
    try:
        if not text:
            return json.dumps({'success': False, 'error': 'changes 为空'}, ensure_ascii=False)
        if not text.startswith('{'):
            if not os.path.isfile(text):
                return json.dumps({'success': False, 'error': 'changes 既不是 JSON 文本也不是文件路径'},
                                  ensure_ascii=False)
            with open(text, encoding='utf-8-sig') as f:
                ch = json.load(f)
        else:
            ch = json.loads(text)
        r = uia.apply_changes(ch, project=project_root, dry_run=bool(dry_run))
        if r.get('success') and pack and not dry_run:
            r['pack'] = uia.pack(r['json'], project_root)
        if r.get('success') and not dry_run:
            r.update(_confirm_gate(project_root, r.get('json') or ''))
        if dry_run:
            r['note'] = ('dry_run：仅预览，未写盘；确认后传 dry_run=False 写回' +
                         '（要接着 pack 再传 pack=True）')
        else:
            r['note'] = '变更已写回 json' + ('（含 ftu 重新打包）' if r.get('pack') else
                                             '（未 pack：布局确认后传 pack=True）') + \
                        '；备份在同目录 <name>.json.bak；布局改完先出确认稿给需求方确认' \
                        '（flythings_ui_preview for_customer=True）再 pack/推真机（见 confirmHint）'
        return json.dumps(_with_files(r, r.get('json'), r.get('backup')), ensure_ascii=False)
    except Exception as e:
        return json.dumps({'success': False, 'error': str(e)}, ensure_ascii=False)
    finally:
        if tmp and os.path.isfile(tmp):
            try:
                os.remove(tmp)
            except Exception:
                pass


def _ui_diff(image_a: str, image_b: str, tolerance: int = 2, shift: int = 1,
             min_area: int = 4, blur: float = 0.7, noise_bbox: int = 10,
             out_png: str = '', out_json: str = '', show_noise: bool = False) -> str:
    """两张同尺寸截图的像素级对比（0 token，纯本地算法）——UI 验收 / 回归对比。

输出的**是差异清单（数字）不是图**，所以不吃 token：区域坐标 / 尺寸 / 面积 / 最大色差。
典型用法：改布局前截一张、改后截一张，两张丢进来 → 只有预期差异才算过；
    「改 A 碰坏 B」会被逐块列出来。跨渲染器（HTML 预览 vs 设备截图）只当骨架参考，
字体磨边噪声靠下面的阈值压。

抑制假报警的默认参数（2026-09-10 定）：
    - tolerance=2：单通道 |Δ|<=2 视为相同
    - shift=1：±1px 抖动补偿（每像素在邻域找最优匹配，"看着像差异其实只是抖动"不算）
    - blur=0.7：对比前高斯模糊，抹掉字体抗锯齿噪声
    - min_area=4 + noise_bbox=10：小于 4px 的斑点和 bbox<=10x10 的小碎块归入 noise 不计入主清单
      （要连小碎块一起看，传 show_noise=True）
    out_png 给出标注图路径（红框=主差异，黄框=噪声）；out_json 存差异清单；缺省只返回清单。
    """
    if udf is None:
        return json.dumps({'success': False, 'error': 'ui_diff 不可用（缺 numpy/Pillow）'},
                          ensure_ascii=False)
    try:
        for p in (image_a, image_b):
            if not os.path.isfile(p):
                return json.dumps({'success': False, 'error': f'图片不存在: {p}'}, ensure_ascii=False)
        r = udf.diff_images(image_a, image_b, tol=int(tolerance), shift=int(shift),
                            min_area=int(min_area), open_k=3, out_png=out_png,
                            out_json=out_json, blur=float(blur),
                            noise_bbox=int(noise_bbox), show_noise=bool(show_noise))
        r['note'] = ('identical=true 表示无差异；regions 为真实差异块（坐标/面积/最大色差），'
                     'noise 为已忽略的抗锯齿/文字磨边小碎块')
        return json.dumps(r, ensure_ascii=False)
    except Exception as e:
        return json.dumps({'success': False, 'error': str(e)}, ensure_ascii=False)


def _render_report_dir(project_root='', json_path=''):
    """清单目录：<项目>/temp/render/ —— **绝不能放 ui/ 下**（json2img 会把 ui/*/*.json 当页面 json）。

没给工程根时从页面 json 反推；两者都取不到→临时目录（不污染工程）。
    """
    root = str(project_root or '').strip()
    jp = str(json_path or '').strip()
    if not root and jp:
        cand = os.path.dirname(os.path.dirname(os.path.abspath(jp)))
        if os.path.isdir(os.path.join(cand, 'ui')):
            root = cand
    if root:
        return os.path.join(root, 'temp', 'render')
    import tempfile
    return os.path.join(tempfile.gettempdir(), 'ft_render')


def _ui_render(project_root, page='', scale=1, out='', all_pages=False):
    """离线「所见即所得」：ui/*.json → 引擎等价 PNG（子进程调 ui_tools/json2img.py）。

清单走 --json-report 读回，unsupported（未支持/待校准降级）**原样透出、绝不静默吞**。
渲染语义（树序 / 拉伸填充 / 对齐位模型 / 裁剪）见 knowledge/devflow/wysiwyg-render-spec.md。
    """
    import subprocess
    script = os.path.join(UI_TOOLS, 'json2img.py')
    if not os.path.isfile(script):
        return json.dumps({'success': False, 'error': 'json2img.py 不可用: %s' % script},
                          ensure_ascii=False)
    root = str(project_root or '').strip()
    if not os.path.isdir(os.path.join(root, 'ui')):
        return json.dumps({'success': False, 'error': 'project_root 下没有 ui/ 目录: %r' % root},
                          ensure_ascii=False)
    pg = str(page or 'main').strip() or 'main'
    try:
        sc = max(1, int(scale or 1))
    except (TypeError, ValueError):
        return json.dumps({'success': False, 'error': 'scale 必须是整数: %r' % scale},
                          ensure_ascii=False)
    rd = os.path.join(root, 'ui', '_render')
    rjd = _render_report_dir(root)            # 清单不进 ui/（否则被当页面 json 扫到）
    outp = str(out or '').strip()
    if all_pages:                       # --all：out 视作输出目录
        dst = outp or rd
        rj = os.path.join(rjd, '_all.report.json')
    else:
        dst = outp or os.path.join(rd, pg + '.png')
        rj = os.path.join(rjd, pg + '.report.json')
    try:                                # json2img 只自建清单目录，产物目录这里保证
        os.makedirs(dst if all_pages else os.path.dirname(os.path.abspath(dst)), exist_ok=True)
        os.makedirs(os.path.dirname(os.path.abspath(rj)), exist_ok=True)
    except OSError as e:
        return json.dumps({'success': False, 'error': '创建输出目录失败: %s' % e},
                          ensure_ascii=False)
    cmd = [sys.executable, script, root, '--scale', str(sc), '--json-report', rj]
    cmd += ['--all', '--out', dst] if all_pages else ['--page', pg, '--out', dst]
    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=900)
    except Exception as e:                      # 解释器/脚本异常也不静默
        return json.dumps({'success': False, 'error': 'json2img 执行失败: %r' % e},
                          ensure_ascii=False)
    log = (proc.stdout or b'').decode('utf-8', 'replace')
    rep = {}
    if os.path.isfile(rj):
        try:
            with open(rj, encoding='utf-8') as f:
                rep = json.load(f)
        except (ValueError, OSError) as e:
            return json.dumps({'success': False, 'error': '清单读取失败: %r' % e,
                               'stdout': log[-1200:]}, ensure_ascii=False)
    pages = rep.get('renders') or []
    if proc.returncode != 0 or not pages:
        return json.dumps({'success': False,
                           'error': 'json2img 失败 rc=%s（页面名/项目路径是否正确？）'
                                    % proc.returncode,
                           'stdout': log[-1500:]}, ensure_ascii=False)
    return json.dumps({'success': True,
                       'pages': [{'page': r.get('page'), 'png': r.get('out'),
                                  'size': r.get('size')} for r in pages],
                       'unsupported': rep.get('unsupported') or [],
                       'missingAssets': rep.get('missing_assets') or [],
                       'stretched': rep.get('stretched') or [],
                       'report': rj}, ensure_ascii=False)


def _ui_render_check(render='', device='', page_json='', tol=2, max_ratio=1.0,
                     project_root='', page='', scale=1):
    """渲染图 vs 真机截图 → 一致性判据（子进程调 ui_tools/wysiwyg_diff.py）。

    render 不给就用 project_root+page 自渲染。pass=false ⇒ 返回体 ok=false +
    error.code=WYSIWYG_MISMATCH（不一致明说，不静默）；判据口径见 wysiwyg-render-spec.md §5。
    """
    import subprocess
    script = os.path.join(UI_TOOLS, 'wysiwyg_diff.py')
    if not os.path.isfile(script):
        return json.dumps({'success': False, 'error': 'wysiwyg_diff.py 不可用: %s' % script},
                          ensure_ascii=False)
    dev = str(device or '').strip()
    pj = str(page_json or '').strip()
    for p in (dev, pj):
        if not p or not os.path.isfile(p):
            return json.dumps({'success': False, 'error': 'device/json 文件不存在: %r' % p},
                              ensure_ascii=False)
    rimg = str(render or '').strip()
    if not rimg:                                # 没给渲染图 → 自己渲染（同 op 内复用）
        root0 = str(project_root or '').strip()
        if not root0:
            return json.dumps({'success': False,
                               'error': 'render 与 project_root 至少要给一个'},
                              ensure_ascii=False)
        r0 = json.loads(_ui_render(root0, page, scale, '', False))
        if not r0.get('success'):
            return json.dumps(r0, ensure_ascii=False)
        pg = str(page or 'main').strip() or 'main'
        hit = [p for p in r0['pages'] if len(r0['pages']) == 1 or p.get('page') == pg]
        rimg = hit[0].get('png', '') if hit else ''
    if not rimg or not os.path.isfile(rimg):
        return json.dumps({'success': False, 'error': '没有可用的渲染图: %r' % rimg},
                          ensure_ascii=False)
    try:
        t, mr = int(tol), float(max_ratio)
    except (TypeError, ValueError):
        return json.dumps({'success': False, 'error': 'tol 需整数 / max_ratio 需数字'},
                          ensure_ascii=False)
    rj = os.path.join(_render_report_dir(project_root, pj),
                      os.path.splitext(os.path.basename(rimg))[0] + '.wysiwyg.json')
    cmd = [sys.executable, script, rimg, dev, pj, '--tol', str(t), '--max-ratio', str(mr),
           '--json', rj]
    root = str(project_root or '').strip()
    if root:
        cmd += ['--project', root]              # 显式给工程根（运行期文字盒识别用）
    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=900)
    except Exception as e:
        return json.dumps({'success': False, 'error': 'wysiwyg_diff 执行失败: %r' % e},
                          ensure_ascii=False)
    log = (proc.stdout or b'').decode('utf-8', 'replace')
    if proc.returncode not in (0, 1) or not os.path.isfile(rj):
        return json.dumps({'success': False,
                           'error': 'wysiwyg_diff 失败 rc=%s（尺寸不一致？看 stdout）'
                                    % proc.returncode,
                           'stdout': log[-1500:]}, ensure_ascii=False)
    with open(rj, encoding='utf-8') as f:
        d = json.load(f)
    pct = d.get('nonTextConsistencyPct')
    mb = d.get('maxBlock') or {}
    ok = bool(d.get('pass'))
    res = {'success': True, 'ok': ok, 'pass': ok, 'render': rimg, 'device': dev,
           'pageJson': pj, 'nonTextConsistencyPct': pct,
           'runtimeTextRatioPct': d.get('runtimeTextRatioPct'),
           'runtimeTextControls': d.get('runtimeTextControls'),
           'maxBlock': d.get('maxBlock'), 'attribution': d.get('attribution') or [],
           'tol': t, 'maxRatio': mr, 'report': rj}
    base = ('非文字区超容差 %.2f%%（判据 ≤ %.2f%%），运行期文字区 %.2f%%，最大差异块 %sx%s'
            % (100.0 - float(pct or 0.0), mr, float(d.get('runtimeTextRatioPct') or 0.0),
               mb.get('w', 0), mb.get('h', 0)))
    if ok:
        res['message'] = '一致（PASS）：' + base
    else:
        res['code'] = 'WYSIWYG_MISMATCH'
        res['message'] = ('渲染图与真机截图不一致（FAIL）：' + base
                          + '；逐控件归因见 attribution，口径见 '
                            'knowledge/devflow/wysiwyg-render-spec.md §5')
    return json.dumps(res, ensure_ascii=False)


# ── 合并后的唯一入口（v0.27.37）──────────────────────────────────────────
# 三动作合一：editor（原 ui_editor）/ edit_apply（原 ui_edit_apply）/ diff（原 ui_diff）。
# 每个 action 只接受自己的参数；传了别家的参数会回 visualNote 提醒（不静默忽略）。
UI_VISUAL_ACTIONS = ('editor', 'edit_apply', 'diff', 'baseline', 'render', 'render_check')
UI_VISUAL_ARGS = {
    'editor': ('project_root', 'output_dir'),
    'edit_apply': ('project_root', 'changes', 'pack', 'dry_run'),
    'diff': ('image_a', 'image_b', 'tolerance', 'shift', 'min_area', 'blur',
             'noise_bbox', 'out_png', 'out_json', 'show_noise'),
    # baseline（2026-09-29）：像素基线库 —— 把「上一次验收通过的那张图」版本化存下来
    'baseline': ('project_root', 'image_a', 'mode', 'baseline_key', 'name', 'allow_regions',
                 'tolerance', 'shift', 'min_area', 'blur', 'noise_bbox', 'out_png'),
    # render / render_check（2026-10-01：设计流要像写 HTML，离线所见即所得要闭环）
    'render': ('project_root', 'page', 'scale', 'out', 'all'),
    'render_check': ('render', 'device', 'json', 'tol', 'max_ratio', 'project_root',
                     'page', 'scale'),
}
UI_VISUAL_REQUIRED = {'editor': ('project_root',),
                      'edit_apply': ('project_root', 'changes'),
                      'diff': ('image_a', 'image_b'),
                      'baseline': ('project_root',),
                      'render': ('project_root',),
                      'render_check': ('device', 'json')}
_UI_VISUAL_DEFAULTS = {'project_root': '', 'output_dir': '', 'changes': '', 'pack': False,
                       'dry_run': False, 'image_a': '', 'image_b': '', 'tolerance': 2,
                       'shift': 1, 'min_area': 4, 'blur': 0.7, 'noise_bbox': 10,
                       'out_png': '', 'out_json': '', 'show_noise': False,
                       'mode': '', 'baseline_key': '', 'name': '', 'allow_regions': 0,
                       'page': '', 'scale': 1, 'out': '', 'all': False, 'render': '',
                       'device': '', 'json': '', 'tol': 2, 'max_ratio': 1.0}


def _ui_baseline(project_root, image, mode='', key='', name='', allow_regions=0,
                 out_png='', profile=None):
    """像素基线库（ui_baseline.py）：mode=list/save/compare/update（缺省 compare）。"""
    import ui_baseline as ubl
    m = str(mode or 'compare').strip().lower()
    ar = None if int(allow_regions or 0) <= 0 else int(allow_regions)
    if m in ('', 'compare', 'check', 'verify'):
        return json.dumps(ubl.compare(project_root, image, key=key, out_png=out_png,
                                      allow_regions=ar, profile=profile),
                          ensure_ascii=False)
    if m == 'save':
        return json.dumps(ubl.save(project_root, image, key=key, name=name,
                                   profile=profile, allow_regions=ar or 0),
                          ensure_ascii=False)
    if m == 'update':
        return json.dumps(ubl.update(project_root, image, key=key, name=name,
                                     profile=profile, allow_regions=ar or 0),
                          ensure_ascii=False)
    if m in ('list', 'ls'):
        return json.dumps(ubl.listing(project_root), ensure_ascii=False)
    return json.dumps({'ok': False, 'op': 'flythings_ui_visual',
                       'error': _err_obj('BAD_PARAMS', 'baseline mode=%s 不认识' % mode,
                                         'mode 取 list / save / compare / update', True),
                       'warnings': []}, ensure_ascii=False)


def _ui_visual_bad(msg, hint):
    """三合一入口的参数错误：给可机读 BAD_PARAMS + 本 action 的正确参数清单。"""
    return json.dumps({'ok': False, 'op': 'flythings_ui_visual',
                       'error': _err_obj('BAD_PARAMS', msg, hint, True),
                       'warnings': []}, ensure_ascii=False)


def _render_path_hint(text):
    """按关键词给一行「走哪条路」（返回体提示，不占 docstring 预算）。"""
    s = str(text or '').lower()
    keys = ('旋转', '矢量', '半透明', 'alpha', '3d', '模糊', '仪表', '图表', '粒子')
    if not any(k in s for k in keys):
        return ''
    return ('检测到可能涉及矢量/旋转/透明/差异化绘制 → 先答三问（静态还是逐帧？面积多大？'
            '有无硬件层？），再查 knowledge/uicontrols/extension-surface.md 选扩展点；'
            '任意角度旋转位图平台没有（先例 components/vinyl）')


def _ui_visual_hint(raw, hint):
    """把 pathHint 塞进返回体（解析不了就原样回）。"""
    if not hint:
        return raw
    try:
        d = __import__('json').loads(raw)
    except ValueError:
        return raw
    if isinstance(d, dict):
        d['pathHint'] = hint
        return __import__('json').dumps(d, ensure_ascii=False)
    return raw


def _ui_visual_note(raw, note):
    """给内层结果补一条 visualNote（不改内层语义；解析不了就原样回）。"""
    if not note:
        return raw
    try:
        d = json.loads(raw)
    except ValueError:
        return raw
    if isinstance(d, dict):
        d['visualNote'] = note
        return json.dumps(d, ensure_ascii=False)
    return raw


def _jvis(o):
    """json.dumps 的本地别名：flythings_ui_visual 有名为 json 的参数，会遮蔽模块名。"""
    return json.dumps(o, ensure_ascii=False)


def flythings_ui_visual(action: str = 'list', project_root: str = '', output_dir: str = '',
                        changes: str = '', pack: bool = False, dry_run: bool = False,
                        image_a: str = '', image_b: str = '', tolerance: int = 2,
                        shift: int = 1, min_area: int = 4, blur: float = 0.7,
                        noise_bbox: int = 10, out_png: str = '', out_json: str = '',
                        show_noise: bool = False, mode: str = '', baseline_key: str = '',
                        name: str = '', allow_regions: int = 0,
                        page: str = '', scale: int = 1, out: str = '', all: bool = False,
                        render: str = '', device: str = '', json: str = '',
                        tol: int = 2, max_ratio: float = 1.0) -> str:
    """UI 可视化/像素验收入口（action 选动作；旧编辑器三 op 已并入，action=list 看参数）。

    触发：对比设计稿 / 还原度 / 像素验收 / 渲染出来看看 / 和截图像不像 / 和设计稿不像 / 跟设计稿不像 / 还原度多少
    """
    act = str(action or '').strip().lower().replace('-', '_')
    if act in ('', 'list', 'help', '?'):
        return _jvis({'success': True, 'op': 'flythings_ui_visual',
                      'actions': {k: {'args': list(v),
                                      'required': list(UI_VISUAL_REQUIRED[k])}
                                  for k, v in UI_VISUAL_ARGS.items()},
                      'hint': ('action 取 editor / edit_apply / diff / baseline / render / '
                               'render_check；旧 ui_editor / ui_edit_apply / ui_diff 已并入本 op')})
    if act not in UI_VISUAL_ACTIONS:
        return _ui_visual_bad('unknown action: %s' % action,
                              'action 取 editor / edit_apply / diff / baseline / render / '
                              'render_check（传 action="list" 看参数）')
    given = {'project_root': project_root, 'output_dir': output_dir, 'changes': changes,
             'pack': pack, 'dry_run': dry_run, 'image_a': image_a, 'image_b': image_b,
             'tolerance': tolerance, 'shift': shift, 'min_area': min_area, 'blur': blur,
             'noise_bbox': noise_bbox, 'out_png': out_png, 'out_json': out_json,
             'show_noise': show_noise, 'mode': mode, 'baseline_key': baseline_key,
             'name': name, 'allow_regions': allow_regions,
             'page': page, 'scale': scale, 'out': out, 'all': all, 'render': render,
             'device': device, 'json': json, 'tol': tol, 'max_ratio': max_ratio}
    miss = [k for k in UI_VISUAL_REQUIRED[act] if not str(given[k] or '').strip()]
    if miss:
        return _ui_visual_bad('action=%s 缺必填参数: %s' % (act, ', '.join(miss)),
                              '本 action 参数: %s(%s)' % (act, ', '.join(UI_VISUAL_ARGS[act])))
    ignored = [k for k in given
               if k not in UI_VISUAL_ARGS[act] and given[k] != _UI_VISUAL_DEFAULTS[k]]
    note = ('action=%s 用不到这些参数，已忽略: %s（各 action 参数见 action="list"）'
            % (act, ', '.join(ignored))) if ignored else ''
    if act == 'editor':
        return _ui_visual_hint(_ui_visual_note(_ui_editor(project_root, output_dir), note),
                              _render_path_hint(changes))
    if act == 'edit_apply':
        return _ui_visual_hint(_ui_visual_note(_ui_edit_apply(project_root, changes, pack, dry_run), note),
                              _render_path_hint(changes))
    if act == 'baseline':
        prof = {'tolerance': tolerance, 'shift': shift, 'minArea': min_area, 'blur': blur,
                'noiseBbox': noise_bbox}
        return _ui_visual_note(_ui_baseline(project_root, image_a, mode, baseline_key,
                                            name, allow_regions, out_png, prof), note)
    if act == 'render':
        return _ui_visual_note(_ui_render(project_root, page, scale, out, all), note)
    if act == 'render_check':
        return _ui_visual_note(_ui_render_check(render, device, json, tol, max_ratio,
                                               project_root, page, scale), note)
    return _ui_visual_note(_ui_diff(image_a, image_b, tolerance, shift, min_area, blur,
                                    noise_bbox, out_png, out_json, show_noise), note)


def flythings_verify_assets(project_root: str) -> str:
    """核对「json 声明 vs 磁盘产物」：图片引用是否存在 + PNG 尺寸是否 == 盒子。

    触发：图片对不上 / 尺寸不符 / 图丢了 / 资源核对 / 图比控件盒大 / 图片比盒子大 / 图比盒子大
    """
    if chk_all is None:
        return json.dumps({'ok': False, 'error': 'check_all 模块不可用（缺 ui_tools/check_all.py）'},
                          ensure_ascii=False)
    try:
        r = chk_all.verify_assets(project_root)
    except Exception as e:
        return json.dumps({'ok': False, 'error': 'verify_assets 失败: %s' % e}, ensure_ascii=False)
    r['hint'] = ('missing → 补图或改 json 引用（自动生成图片放 resources/images/，引用写 images/xxx.png）；'
                 'mismatch → 重新出图，使 PNG 尺寸严格 == 盒子（position 或 thumb.size）；'
                 'stretched 一般无需处理（手绘图由引擎拉伸到控件盒）')
    return json.dumps(r, ensure_ascii=False)


# device_screenshot 的进阶参数默认值（v0.27.34：这些键也可统一走 advanced JSON，
# 已显式传的同名参数优先 —— 参数分层的判定基准）
_DSS_ADV_DEFAULTS = {'fb': '/dev/fb0', 'pixel': 'auto', 'width': 0, 'height': 0, 'offset_y': -1,
                     'flip': '', 'rotate': 'auto', 'crop': '', 'layer': 'ui', 'vdec_chn': 0,
                     'name': '', 'timeout': 180}


def flythings_device_screenshot(device: str = '', out: str = '', fmt: str = 'png', scale: float = 1.0,                               quality: int = 90, fb: str = '/dev/fb0', pixel: str = 'auto',
                               width: int = 0, height: int = 0, offset_y: int = -1,
                               flip: str = '', rotate: str = 'auto', crop: str = '', name: str = '',
                               timeout: int = 180, advanced: str = '', layer: str = 'ui',
                               vdec_chn: int = 0) -> str:
    """从**设备真机**抓当前屏幕 → PNG / JPG / BMP（给视觉模型看，或给 ui_visual(action="diff") 验收）。

    触发：抓屏 / 截图 / 看看现在屏幕什么样 / 抓个图
    """
    if dss is None:
        return json.dumps({'success': False, 'error': 'device_screenshot 不可用（缺 ui_tools/device_screenshot.py 或 Pillow）'},
                          ensure_ascii=False)
    # 参数分层（v0.27.34）：fb/pixel/width/height/offset_y/flip/rotate/crop/name/timeout 可统一走 advanced
    # （JSON 对象字符串）；**已显式传的同名参数优先**（旧客户端不受影响）。
    params = {'fb': fb, 'pixel': pixel, 'width': width, 'height': height, 'offset_y': offset_y,
              'flip': flip, 'rotate': rotate, 'crop': crop, 'layer': layer, 'name': name,
              'timeout': timeout, 'vdec_chn': vdec_chn}
    if advanced and str(advanced).strip():
        try:
            adv = json.loads(advanced)
        except Exception as e:
            return json.dumps({'ok': False, 'op': 'flythings_device_screenshot',
                               'error': {'code': 'BAD_ARGS', 'msg': 'advanced 不是合法 JSON: %s' % e,
                                         'hint': 'advanced 传 JSON 对象字符串（如 {"crop": "auto"}）',
                                         'retryable': True}, 'warnings': []}, ensure_ascii=False)
        if not isinstance(adv, dict):
            return json.dumps({'ok': False, 'op': 'flythings_device_screenshot',
                               'error': {'code': 'BAD_ARGS', 'msg': 'advanced 必须是 JSON 对象',
                                         'hint': '可选键: %s' % ', '.join(sorted(params)),
                                         'retryable': True}, 'warnings': []}, ensure_ascii=False)
        unknown = sorted(k for k in adv if k not in params)
        if unknown:
            return json.dumps({'ok': False, 'op': 'flythings_device_screenshot',
                               'error': {'code': 'BAD_ARGS',
                                         'msg': 'advanced 含未知键: %s' % ', '.join(unknown),
                                         'hint': '可选键: %s' % ', '.join(sorted(params)),
                                         'retryable': True}, 'warnings': []}, ensure_ascii=False)
        for k, v in adv.items():
            if params[k] == _DSS_ADV_DEFAULTS[k]:     # 未显式指定 → advanced 生效
                params[k] = v
    try:
        r = dss.capture(device=device, out=out, fmt=fmt, scale=scale, quality=quality, **params)
    except Exception as e:
        return json.dumps({'success': False, 'error': str(e)}, ensure_ascii=False)
    return json.dumps(r, ensure_ascii=False)

def flythings_selfcheck(device: str = '', diff_against: str = '', out: str = '') -> str:
    """整机快照（十一个分区），每分区给 {ok, hint, data}；`ok=false` **不是错误而是结论**。

    触发：整机体检 / 板子什么状态 / 网络通不通 / 分区挂载 / 把设备状态抓一遍
    """
    if sc is None:
        return json.dumps({'ok': False, 'op': 'flythings_selfcheck',
                           'error': {'code': 'MODULE_MISSING',
                                     'msg': 'selfcheck_tools 不可用: %s' % _SC_ERR,
                                     'hint': '恢复仓库里的 selfcheck_tools.py 后重试',
                                     'retryable': False},
                           'warnings': []}, ensure_ascii=False)
    return json.dumps(sc.run_selfcheck(device, diff_against, out), ensure_ascii=False)


def flythings_bugreport(title: str = '', project_root: str = '', device: str = '',
                        symptom: str = '', steps: str = '', expected: str = '',
                        actual: str = '', evidence: str = '', severity: str = '',
                        out: str = '') -> str:
    """缺陷单生成器：缺陷清单 + 真机判据 → 可提交 markdown（格式对齐 html2json A1~A8 那批）。

    触发：提 bug / 缺陷单 / 报个问题 / 写缺陷报告
    """
    if sc is None:
        return json.dumps({'ok': False, 'op': 'flythings_bugreport',
                           'error': {'code': 'MODULE_MISSING',
                                     'msg': 'selfcheck_tools 不可用: %s' % _SC_ERR,
                                     'hint': '恢复仓库里的 selfcheck_tools.py 后重试',
                                     'retryable': False},
                           'warnings': []}, ensure_ascii=False)
    r = sc.build_bugreport(title, project_root, device, symptom, steps, expected, actual,
                           evidence, severity, out, MCP_VERSION)
    return json.dumps(_with_files(r, r.get('path')), ensure_ascii=False)



def flythings_project_state(project_root: str = "", action: str = "show",
                            slot: str = "", note: str = "") -> str:
    """工程进度（跨会话「做到哪了」）：已过/未过的闸门 + 下一步做什么。

    触发：做到哪了 / 上次做到哪 / 继续上次 / 下一步做什么 / 工程进度 / 做到哪一步了
    """
    import project_state as _ps
    act = (action or "show").strip().lower()
    known = "、".join(sorted(_ps.slots()))
    try:
        if act == "show":
            data = _ps.show(project_root)
        elif act == "mark":
            if not slot:
                raise _ps.ProjectStateError("mark 必须给 slot（可选：%s）" % known)
            root = _ps.resolve(project_root)
            if not root:
                raise _ps.ProjectStateError("没有活动工程：请传 project_root")
            _ps.mark(root, slot, note=note, source="flythings_project_state")
            data = _ps.show(root)
        elif act == "reset":
            if not project_root:            # 清空必须显式给路径（不给「最近工程」兜底）
                raise _ps.ProjectStateError("reset 必须显式传 project_root")
            if not _ps.reset(project_root):
                raise _ps.ProjectStateError("清空失败：%s" % project_root)
            data = _ps.show(project_root)
        else:
            raise _ps.ProjectStateError("未知 action=%r（可选 show / mark / reset）" % action)
    except _ps.ProjectStateError as e:
        return json.dumps({"success": False, "code": "BAD_PARAMS", "msg": str(e),
                           "hint": "状态位口径见 flow_spec.json 的 stateSlots（可选：%s）；"
                                   "show 不需要额外参数" % known}, ensure_ascii=False)
    return json.dumps({"success": True, "op": "flythings_project_state",
                       "action": act, **data}, ensure_ascii=False, default=str)


# ===== 统一返回契约（v0.27.31）=====
# 所有工具返回值统一为 {ok, op, warnings[], error{code,msg,hint,retryable}}；
# 保留原有键（success / error 文本 / 业务字段）向后兼容，非 JSON 纯文本收进 data.text。
# 目的：宿主 AI 能机读判定「成功/失败/是否可重试」，不再出现有的回 success、有的回 ok、
# 错误只有一句字符串（MCP isError 永为 false）的情况。

def _err_obj(code, msg, hint='', retryable=None):
    """统一错误对象。

    `retryable=None` = **未表态**，留给错误码表（域⑫）按 code 的默认值填；
    显式传 True/False 表示调用点有更强判断，码表不覆盖。
    最终 `normalize_result` 会把 None 收敛成 False —— 对外契约里它必是布尔。
    """
    return {'code': code or 'ERROR', 'msg': str(msg), 'hint': hint,
            'retryable': None if retryable is None else bool(retryable)}


def normalize_result(op, raw):
    """把任意工具返回值归一化为统一 envelope（幂等，重复归一不再变）。"""
    if not isinstance(raw, str):
        try:
            raw = json.dumps(raw, ensure_ascii=False, default=str)
        except Exception:
            raw = json.dumps({'data': str(raw)}, ensure_ascii=False)
    try:
        obj = json.loads(raw)
    except Exception:
        return json.dumps({'ok': True, 'op': op, 'data': {'text': raw}, 'warnings': []},
                          ensure_ascii=False)
    if not isinstance(obj, dict):
        return json.dumps({'ok': True, 'op': op, 'data': obj, 'warnings': []}, ensure_ascii=False)
    out = dict(obj)
    ok = out.get('ok')
    if not isinstance(ok, bool):
        if 'success' in out:
            ok = bool(out['success'])
        else:
            ok = not any(k in out for k in ('error', 'errors', 'fail'))
        out['ok'] = ok
    err = out.get('error')
    if not ok:
        if isinstance(err, dict):
            out['error'] = _err_obj(err.get('code'), err.get('msg') or err.get('message') or err,
                                    err.get('hint', ''), err.get('retryable'))
        elif isinstance(err, str):
            out['error'] = _err_obj(out.get('code'), err, out.get('hint', ''),
                                    out.get('retryable'))
        elif err is None:
            out['error'] = _err_obj(out.get('code'),
                                    out.get('message') or out.get('msg') or 'unknown error',
                                    out.get('hint', ''), out.get('retryable'))
        # 码表补语义（域⑫ error_codes.json）：调用点只写 code+msg，`action`（下一步该做什么）
        # 与默认 `retryable` 在这里统一注入 —— 于是 48 个 op 的失败返回都自带处置建议。
        # 显式写过的 retryable 优先；查不到的码原样放过（漏登记由门禁抓，不在运行时炸）。
        errcodes.enrich(out['error'])
        if out['error'].get('retryable') is None:   # 未表态 → 收敛成 False（契约里必是布尔）
            out['error']['retryable'] = False
    elif isinstance(err, str):
        out.pop('error', None)  # ok=True 时的残留错误字符串清掉，避免误判
    out.setdefault('warnings', [])
    out.setdefault('op', op)
    sa = _seealso_for(op)          # 「去哪找」：不占 docstring 预算（见 op_seealso.json）
    if sa:
        out.setdefault('seeAlso', sa)
    return json.dumps(out, ensure_ascii=False)


def _sig_args(fn) -> list:
    """函数签名参数名（给 BAD_PARAMS 回显用）。"""
    import inspect as _i
    try:
        return [p.name for p in _i.signature(fn).parameters.values()
                if p.name not in ('ctx', 'self')]
    except (TypeError, ValueError):
        return []


def _state_auto_mark(op_name, kwargs, raw):
    """op 成功后按**流程真源反查**的状态位就地回写（域⑪）。

    为什么放在 `_envwrap`：这样 dispatcher / all / flat **三种模式都覆盖**；
    放在分发器里只能覆盖 dispatcher 模式。
    为什么能反查：`flow_spec.json` 的 steps 里写着「哪一步 setsState 哪些位」，
    `project_state.slots_of_op()` 从它推出来 —— 所以**不需要另维护一张 op→状态位 映射表**。

    失败不许影响主流程，但要**如实回报**（写进返回体的 warnings）。
    """
    try:
        obj = json.loads(raw) if isinstance(raw, str) else raw
    except ValueError:
        return raw
    if not isinstance(obj, dict) or not obj.get('ok'):
        return raw                              # 只认成功：失败回写会把「跑过」当成「做成了」
    try:
        import project_state as _ps
        marked, err = _ps.auto_mark(op_name, kwargs, obj)
    except Exception as e:
        marked, err = [], '%s: %s' % (type(e).__name__, e)
    if not marked and not err:
        return raw
    if marked:
        obj.setdefault('stateMarked', marked)
    if err:
        obj.setdefault('warnings', []).append('工程状态回写失败（不阻断本次调用）：%s' % err)
    return json.dumps(obj, ensure_ascii=False)


def _envwrap(name, fn):
    """工具级包装：统一 envelope + 内部异常不再静默（转为可机读 error 返回）。

参数绑定错误（少传/写错参数名）单独识别为 **BAD_PARAMS**并附正确签名：否则会被下面的 except 归成 TOOL_RAISED，AI 拿不到签名就得猜参数（v0.27.33 修）。
    """
    import functools

    @functools.wraps(fn)
    def wrapper(*a, **kw):
        try:
            inspect.signature(fn).bind(*a, **kw)      # 只做绑定校验，不执行
        except TypeError as e:
            return json.dumps(
                {'ok': False, 'op': name,
                 'error': _err_obj('BAD_PARAMS', '%s: %s' % (type(e).__name__, e),
                                   '本 op 正确签名: %s(%s)'
                                   % (name, ', '.join(_sig_args(fn))), True),
                 'warnings': []}, ensure_ascii=False)
        try:
            return _state_auto_mark(name, kw, normalize_result(name, fn(*a, **kw)))
        except Exception as e:
            return json.dumps(
                {'ok': False, 'op': name,
                 'error': _err_obj('TOOL_RAISED', '%s: %s' % (type(e).__name__, e),
                                   'v0.27.31 起工具内部异常不再静默；请把本消息连同 op 反馈给官方',
                                   False),
                 'warnings': []}, ensure_ascii=False)
    return wrapper


# 注册前统一包装（两条路径——flythings_kb 分发器与独立工具——返回同一契约）
for _n in _tool_names():
    globals()[_n] = _envwrap(_n, globals()[_n])


# ── op 注册清单（唯一来源）──────────────────────────────────────────────
# register_all 与 mcp_server 的分发器共用本清单；新增 op 只需：
#   ① 在 kb_tools 里定义 flythings_xxx 函数  ② 把名字加进 OP_NAMES
#   ③ 跑 scripts/check_consistency.py（校验 OP_NAMES == 模块内全部 flythings_* 函数）
OP_NAMES = (
    'flythings_get_version',
    'flythings_knowledge_search',
    'flythings_knowledge_capture',
    'flythings_knowledge_export',
    'flythings_knowledge_gaps',
    'flythings_hardware_info',
    'flythings_map_control',
    'flythings_ui_schema',
    'flythings_translate_ui',
    'flythings_read_json',
    'flythings_layout_audit',
    'flythings_get_project_spec',
    'flythings_validate_project',
    'flythings_fui_pack',
    'flythings_fui_unpack',
    'flythings_edit_ftu',
    'flythings_build_ui_flow',
    'flythings_device_preflight',
    'flythings_pack_upgrade',
    'flythings_ui_preview',
    'flythings_html_to_json',
    'flythings_ui_visual',
    'flythings_verify_assets',
    'flythings_device_screenshot',
    'flythings_selfcheck',
    'flythings_bugreport',
    'flythings_attach_cli_tools',
    'flythings_create_project',
    'flythings_create_bin_project',
    'flythings_gen_logic_stub',
    'flythings_gen_ui_test',
    'flythings_test_run',
    'flythings_check_project_deps',
    'flythings_generate_ui_assets',
    'flythings_i18n_scan',
    'flythings_i18n_add_language',
    'flythings_i18n_export',
    'flythings_i18n_import',
    'flythings_i18n_refactor',
    'flythings_i18n_to_json',
    'flythings_list_packages',
    'flythings_project_state',
    'flythings_query_package',
    'flythings_manifest',
    'flythings_add_package',
    'flythings_package_search',
    'flythings_get_package_api',
    'flythings_resolve_dependencies',
)

# 已合并/改名的 op（v0.27.36 起：工具直接合并，不留别名）——
# 分发器遇到它们时回 OP_RENAMED + 新名字（**只是错误提示，不执行**，不会变成隐性别名）。
RENAMED = {
    'flythings_search': 'flythings_knowledge_search',
    'flythings_generate_ui_preview': 'flythings_ui_preview',
    'flythings_json_to_html': 'flythings_ui_preview',
    'flythings_recommend_manifest': 'flythings_manifest',
    'flythings_generate_manifest': 'flythings_manifest',
    'flythings_search_package': 'flythings_package_search',
    'flythings_ui_editor': 'flythings_ui_visual',
    'flythings_ui_edit_apply': 'flythings_ui_visual',
    'flythings_ui_diff': 'flythings_ui_visual',
}

# 合并后带 action 的入口：旧名 → 该用哪个 action（分发器把它拼进 OP_RENAMED 的 hint）。
RENAMED_HINT = {
    'flythings_ui_visual': ('action 取 editor（原 ui_editor）/ edit_apply（原 ui_edit_apply）'
                            '/ diff（原 ui_diff）'),
}


def register_all(mcp):
    """把全部 op 注册到 MCP server；返回已注册函数列表（smoke / 一致性检查用）。"""
    fns = []
    for name in OP_NAMES:
        fn = globals().get(name)
        if callable(fn) is False:
            raise RuntimeError('OP_NAMES 里的 op 未定义: ' + name)
        mcp.tool()(fn)
        fns.append(fn)
    return fns
