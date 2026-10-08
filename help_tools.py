# -*- coding: utf-8 -*-
"""技术支持入口（flythings_help）：口语/症状问法归一 → 多路检索合并 → 可执行指引。

为什么单立一个 op（2026-10-07 需求方拍板「按建议处理」）
--------------------------------------------------------
实测 30 条真实客户问法走单路 `flythings_knowledge_search`：ok 23 / low_confidence 6 / no_hit 1，
**7 条被误记进「知识缺口」**（明明有答案）。根因不是知识库缺内容，是**问法错位**：
用户说症状语言（「按键长按怎么写」），文档写机制语言（`longClickTimeOut`）——
口语与术语之间没有桥，覆盖率算出来低，于是被当成「未收录」。

本 op 做三件事：
  ① **归一**：口语/同义词/症状原话 → 机制词 + 权威文档词（本文件的 `ALIAS_RULES` +
     症状注册表 `symptom_spec.json` 的「用户原话 → 机制」映射）；
  ② **多路检索 + 按 path 合并（RRF）**：原问 + 每条归一串各检索一次，同一篇文档只出现一次，
     并标注它由哪几条问法命中。**不另造检索引擎** —— 复用 `rag_search.search` 与 kb_tools 的
     `_annotate_kb_hits` / `_best_coverage` / 本地层优先与过期降权，口径与 knowledge_search 同源；
  ③ **缺口记账只在「多重归一后仍 no_hit」时才写** —— 归一后命中/低置信一律不写，
     误记必须是 0（这是本 op 存在的第一判据）。

派生物只做**摘录**：`steps` / `code` 逐字取自命中片段，不生成新句子（禁编造）。

为什么不做成 skill（需求方口径 2026-10-07）：skill 只在装了它的 agent 生效，op 全员可用。
"""
import json
import re

import kb_local                       # 归一化口径（normalize_symptom）与缺口日志（log_no_hit）
import rag_search as rs               # 检索唯一实现（向量 + BM25 + RRF + 专名重排）

# 合并深度：每路只拿前 N 名参与合并。为什么不用 40：向量路对**任何** query 都会回 40 条，
# 深列表里第 20 名以后的"沾边"文档在 RRF 里仍能积到分，实测会把 components/*/platforms.md
# 这类泛文档挤进 top-3（问「开机自启」返回 BLE 文档）。取前 10 = 只让"强命中"参与合并。
MERGE_DEPTH = 10
_RRF_K = 60                           # RRF 平滑常数（同 rag_search._K）

# `question` 为空时的错误码（登记在 error_codes.json；错误路径的语义由那张表负责）
_ERR_EMPTY = {
    'code': 'BAD_QUESTION',
    'msg': 'question 不能为空',
    'hint': "把用户原话放进 question，例：{\"question\": \"按键长按怎么写\"}",
    'retryable': False,
}

# 用户原话里的**口语/同义词 → 机制词 + 权威文档词**。
#
# 为什么手写这张表而不是全靠症状注册表：注册表收的是「踩过坑的症状原话族」（23 条），
# 而客户问法里还有大量**没踩过坑但同样错位**的用法问题（「按键长按怎么写」「输入框只能输数字」）
# —— 那些是"用法语言"，不是"症状语言"。表里每条都来自实测问法，不许凭空造。
#
# 匹配口径：两边都过 `kb_local.normalize_symptom`（去标点/空格/大小写）后做子串匹配；
# 纯 ASCII 的**短片段**（≤3 字符，如 `qt`/`ml`）要求词边界 —— 否则 `qt` 会命中 `mqtt`，
# 那是"该命中的被吃掉"方向，比多给一串危险。与 op_spec_loader.exclude_hit 同一套口径。
ALIAS_RULES = (
    # ---- A 控件用法 ----
    ('button-long-press', ('长按', '长摁', '按住不放', 'longclick'),
     '按钮 Button 长按 longClickTimeOut longClickIntervalTime 循环重复 长按事件 触发时间'),
    ('edittext-number-only', ('只能输数字', '只能输入数字', '只输数字', '数字键盘', '只允许数字', 'texttype'),
     'edittext 输入框 只能输入数字 数字键盘 textType 输入类型 限制输入'),
    ('button-round-image', ('圆角', '切图', '九宫格', '.9.png', '拉伸区', '九宫图'),
     '圆角 nine-patch .9.png 切图 拉伸区 内容区 按钮背景 生成本规则 倒角'),
    ('button-callback-name', ('回调函数叫什么', '回调叫什么', '点击回调', '回调函数名', '事件函数名'),
     '回调 callback 事件 函数名 onButtonClick 控件回调 命名'),
    ('list-row-data', ('行数据', '列表怎么做', '列表怎么填', '列表数据怎么', 'listview'),
     'listview 列表 行数据 适配器 回调 三个回调 列表控件'),
    ('media-preview', ('摄像头', '相机', 'camera', '视频预览', '播放视频', '视频怎么播'),
     '摄像头 camera 预览 视频 播放 MediaCapability 媒体能力'),
    ('qrcode', ('二维码', 'qrcode', '扫码'),
     '二维码 qrcode 生成 控件'),
    # ---- B 现场症状 ----
    ('list-scroll-jank', ('卡顿', '掉帧', '不流畅', '滚动不', '滑动不'),
     '列表 滚动 卡顿 高频回调 刷新频率 性能 high-frequency-callback-perf'),
    ('refresh-cpu', ('cpu 高', 'cpu占用', '刷新太频繁', '刷新频繁', '主线程卡'),
     '刷新 太频繁 高频回调 CPU 占用 性能 主线程'),
    ('pushed-no-effect', ('推上去没效果', '改了没生效', '还是旧的', '没生效', '不生效', '没变化'),
     '推上去没效果 设备上还是旧的 部署 pack ftu 未生效 device-deploy'),
    ('cannot-drag-no-response', ('拖不动', '点了没反应', '不跟手', '点不动', '按了没反应', '摸不动'),
     '拖不动 点了没反应 触摸 touch touchable 事件 坐标 不响应'),
    ('refresh-after-return', ('切一下才显示', '切页回来', '返回上一页', '第二次进', '再进页面', '切回来才'),
     '切一下才显示 切页返回 刷新 activity 重绘 返回上一页'),
    ('image-blurry', ('发糊', '锯齿', '模糊', '毛边', '变形', '被拉长'),
     '图标发糊 锯齿 nine-patch 图片尺寸 控件盒 拉伸 失真 ui-layout-verify'),
    ('font-not-effective', ('中文不显示', '字体不生效', '字体没生效', '乱码', '字库'),
     '字体 中文 不显示 字库 fonts 打包 生效 font'),
    ('self-exit-killed', ('无缘无故退出', '无故退出', '莫名退出', '自己退出', '自动退出', '闪退', '被杀', '崩溃'),
     '程序退出 被杀 OOM 内存 zkgui 崩溃 重启 logcat device-deploy-budget'),
    ('screensaver', ('屏保', '屏幕自己黑', '黑屏'),
     '屏保 触发 关闭 屏幕黑 system-windows'),
    # ---- C 部署 / 环境 ----
    ('fun-not-found', ('找不到 fun', 'fsc.exe 找不到', '没有 fun', 'fun 命令', '工具链', '命令找不到'),
     'fsc.exe fui.exe 命令行工具链 cli-fun 前置条件 环境变量 FLYTHINGS_FSC_DIR 注册表 找不到'),
    ('resolution-scaling', ('分辨率', '换屏', '换面板', '缩放适配', '界面适配'),
     '分辨率 适配 resolution scaling 设计稿 面板 双分辨率 分层 platform-translate'),
    ('boot-autostart', ('开机自启', '开机启动', '自启动', '自动启动', '开机就跑', '上电启动'),
     '开机 自启动 开机启动 init.rc service zkswe 托管 setprop ctl.restart '
     'deploy-scene-map 应用由 init 拉起'),
    ('adb-connect', ('adb', '设备连不上', '连不上设备', '设备离线'),
     'adb 设备连接 离线 device-selection 排查 and-device-selection'),
    ('upgrade-image', ('升级包', 'update.img', '刷机', '固件升级'),
     '升级包 update.img pack 固化 分区 upgrade-pack-image'),
    # ---- D 边界 / 跨框架 ----
    ('cross-framework', ('qt', 'android', 'qml', 'seekbar', '小程序', 'lvgl', 'emwin', 'awtk'),
     '跨框架 控件映射 Qt Android LVGL 迁移 control-mapping 对应控件'),
    ('decompile', ('反编译', '反解 so', 'so 拿接口', '解密 so'),
     '反编译 so 接口 retrieval-boundary 边界 禁止'),
    # ---- E 业务能力 ----
    ('mqtt', ('mqtt',),
     'MQTT 接入 包 mqtt-cxx 协议 open-source-stack-integration'),
    ('bluetooth', ('蓝牙', 'bluetooth', 'ble'),
     '蓝牙 BLE 串口通信 包 component-ble'),
    ('video-wall', ('多屏', '拼接', '拼屏', '视频墙', '多屏同步'),
     '多屏拼接 视频墙 同步 video-wall-sync'),
    ('chart-widget', ('图表', '曲线图', '柱状图', '折线图', '柱图'),
     '图表 控件 能力 自绘 custom-widget 缺口'),
)

# 症状注册表匹配的阈值：查询与其"症状原话族"的词元重合度（占查询词元的比例）。
# 为什么 0.6：低于它就会把「只是同一类话题」的问法也展开（多路检索无谓变慢、还可能挤掉正解）。
_SYMPTOM_MIN = 0.6

_ASCII_SHORT = re.compile(r'[a-z0-9_.]{1,3}\Z')
_STEP_LINE = re.compile(r'^[ \t]*(?:[-*+]|[0-9]{1,2}[.)、])[ \t]+(?P<t>\S.*)$', re.M)
_CODE_FENCE = re.compile(r'```[^\n]*\n(.*?)```', re.S)

_SYMPTOM_INDEX = {}


def _kb():
    """惰性拿 kb_tools（**不能在模块顶部 import**：kb_tools 顶部要 import 本模块，成环）。"""
    import kb_tools
    return kb_tools


def _hit(phrase, question):
    """短语是否命中用户原话（口径见 ALIAS_RULES 注释）。"""
    p = kb_local.normalize_symptom(phrase)
    qn = kb_local.normalize_symptom(question)
    if not p or not qn:
        return False
    if _ASCII_SHORT.fullmatch(p):        # 短 ASCII 要整词，别让 `qt` 命中 `mqtt`
        return re.search(r'(?<![a-z0-9_.])%s(?![a-z0-9_.])' % re.escape(p), qn) is not None
    return p in qn


def _symptom_index():
    """读症状注册表（`symptom_spec.json`）→ [{id, symptoms, expand}]；读不了返回 [] 并留痕。

    expand = 「症状原话族 + 机制 + 权威文档名」——这是**症状语言 → 机制语言**的桥：
    文档写的是机制（「资源超预算被内核 OOM 杀」），用户说的是症状（「程序无缘无故退出了」）。
    """
    if 'ents' in _SYMPTOM_INDEX:
        return _SYMPTOM_INDEX['ents']
    ents, err = [], ''
    try:
        import symptom_loader
        for e in symptom_loader.load()['entries']:
            syms = [str(s) for s in (e.get('symptom') or []) if str(s).strip()]
            if not syms:
                continue
            doc = str(e.get('doc') or '')
            tail = ' '.join(x for x in (doc.replace('knowledge/', '').replace('.md', '')
                                        .replace('/', ' '), str(e.get('mechanism') or '')) if x)
            ents.append({'id': str(e.get('id') or ''), 'symptoms': syms,
                         'expand': ' '.join(syms) + ' ' + tail})
    except Exception as e:               # 注册表读不了不该把入口打挂，但要显式带出去（不静默）
        err = '%s: %s' % (type(e).__name__, e)
    _SYMPTOM_INDEX['ents'] = ents
    _SYMPTOM_INDEX['err'] = err
    return ents


def normalize(question, platform=''):
    """用户原话 → 归一化检索串列表（**不含原问**，原问由调用方放在第 0 位）。

    返回 [{'label': 来源标签, 'exp': 检索串}]；同一串只保留一次（先到先得）。
    """
    out, seen = [], set()

    def _add(label, exp):
        exp = ' '.join(str(exp or '').split())
        key = kb_local.normalize_symptom(exp)
        if len(key) < 2 or key in seen:
            return
        seen.add(key)
        out.append({'label': label, 'exp': exp})

    for name, phrases, exp in ALIAS_RULES:
        if any(_hit(p, question) for p in phrases):
            _add('alias:' + name, exp)

    qn = kb_local.normalize_symptom(question)
    qtoks = rs.query_tokens(qn)
    for ent in _symptom_index():
        best = 0.0
        for s in ent['symptoms']:
            sn = kb_local.normalize_symptom(s)
            if not sn:
                continue
            if sn in qn:                 # 原话里逐字带了某条症状原话 → 直接算命中
                best = 1.0
                break
            st = rs.query_tokens(sn)
            if st:
                best = max(best, len(qtoks & st) / float(len(qtoks) or 1))
        if best >= _SYMPTOM_MIN:
            _add('symptom:' + ent['id'], ent['expand'])

    plat = str(platform or '').strip()
    if plat:                             # 平台限定：同一段机制词在不同平台上的文档不同
        out.append({'label': 'platform', 'exp': '%s %s' % (plat, question)})
    return out


def _steps_and_code(texts, paths):
    """从命中片段里**摘录**可执行指引与代码块（逐字，不生成）。

口径：steps/code 取自「该 path 被检索到的片段」（不只展示的那一段）——
头部片段通常是文档标题/检索导引，列表与代码块在后面的片段里。
    """
    steps, codes = [], []
    for path in paths:
        for txt in texts.get(path, []):
            for m in _STEP_LINE.finditer(txt):
                t = m.group('t').strip()
                if len(t) < 6 or t in steps:
                    continue
                steps.append(t)
                if len(steps) >= 6:
                    break
            for m in _CODE_FENCE.finditer(txt):
                c = m.group(1).strip('\n')
                if c and c not in codes and len(codes) < 3:
                    codes.append(c)
    return steps[:6], codes[:3]


_NEXT_OPS = (
    (('knowledge/uicontrols/', 'control-map'), ('flythings_ui_schema', 'flythings_map_control')),
    (('json-layer', 'layout', 'touch-events'), ('flythings_layout_audit', 'flythings_ui_schema')),
    (('device-deploy', 'device-screenshot', 'device-preflight', 'adb'),
     ('flythings_device_preflight', 'flythings_device_screenshot')),
    (('upgrade',), ('flythings_pack_upgrade',)),
    (('cli-fun', 'build', 'compile'), ('flythings_build_ui_flow', 'flythings_check_project_deps')),
    (('i18n',), ('flythings_i18n',)),
    (('package', 'dependenc'), ('flythings_list_packages', 'flythings_manifest')),
)


def next_ops(hit_paths):
    """命中文档 → 建议接着调的 op（按「这条知识下一步要动手做什么」取，不是猜）。"""
    out = []
    for path in hit_paths:
        p = str(path or '').lower()
        for keys, ops in _NEXT_OPS:
            if any(k in p for k in keys):
                out.extend(ops)
    if not out:
        out = ['flythings_knowledge_search']
    uniq = []
    for o in out:
        if o not in uniq:
            uniq.append(o)
    return uniq[:4]


def run(question, k=3, platform='', project_root=''):
    """技术支持入口主体：归一 → 多路检索 → 合并 → 质量判定 → （仅 no_hit）记缺口。

    `quality` 口径与 `flythings_knowledge_search` 一致（no_hit < 0.1 / low_confidence < 0.4 / ok），
    差别只在**覆盖率取两路的最大值**：
      · coverRaw  = 原问对「原问检索回来的片段」的覆盖率（就是 knowledge_search 的口径）；
      · coverNorm = max(各归一串对**它自己检索回来的片段**的覆盖率) —— 归一的意义就在这条：
                    原话命不中的机制词由归一串代偿，但它必须**在自己的命中里**成立，
                    不许拿别的串的命中来凑（否则就成了自证）。
    """
    q = str(question or '').strip()
    kb = _kb()
    if not q:
        out = {'ok': False, 'op': 'flythings_help', 'question': q, 'normalized': [],
               'hits': [], 'refs': [], 'steps': [], 'code': [], 'nextOps': [],
               'quality': 'no_hit', 'coverage': 0.0, 'warnings': []}
        out['error'] = dict(_ERR_EMPTY)
        return out

    kk = max(1, min(int(k or 3), 8))
    warnings = []
    try:
        degraded = rs._get_embedder() is None
    except Exception as e:               # 探测失败按降级处理，但如实写进 warnings
        degraded = True
        warnings.append('向量模型可用性探测失败（%s），按降级处理' % type(e).__name__)
    if degraded:
        warnings.append('本地向量模型不可用，已降级 BM25 关键词检索（召回可能变差）')

    norm = normalize(q, platform)
    if _SYMPTOM_INDEX.get('err'):
        warnings.append('症状注册表不可用（%s）；本次只走别名表展开' % _SYMPTOM_INDEX['err'])
    queries = [q] + [n['exp'] for n in norm]

    per_query, failed = [], 0
    for i, qs in enumerate(queries):
        try:
            per_query.append(rs.search(qs, max(MERGE_DEPTH, kk * 3)))
        except Exception as e:
            per_query.append([])
            failed += 1
            warnings.append('第 %d 条检索串失败（%s）：%s' % (i, type(e).__name__, e))
    if failed == len(queries):
        out = {'ok': False, 'op': 'flythings_help', 'question': q,
               'normalized': norm, 'warnings': warnings}
        out['error'] = {'code': 'SEARCH_FAILED', 'msg': '全部检索路都失败',
                        'hint': '重试一次；仍失败检查 rag_index.json 与本地向量模型是否完整',
                        'retryable': True}
        return out

    # 多路合并：同一 path 只留一次，分数 = Σ 1/(K+rank+1)（RRF，与 rag_search 内部融合同式），
    # 再乘本地层优先 / 过期降权（复用 kb_tools 的同一对系数，不另立口径）。
    km, _ierr = kb._kb_index_map()
    merged = {}
    for i, top in enumerate(per_query):
        for rank, (s, c) in enumerate(top):
            path = c.get('path') or ''
            if not path:
                continue
            e = merged.setdefault(path, {'rrf': 0.0, 'chunk': c, 'best': -1.0,
                                         'chunks': [], 'from': []})
            e['rrf'] += 1.0 / (_RRF_K + rank + 1)
            if i not in e['from']:
                e['from'].append(i)
            if c.get('text') and c['text'] not in e['chunks']:
                e['chunks'].append(c['text'])
            if float(s) > e['best']:            # 展示哪一段：取该 path 得分最高的片段
                e['best'], e['chunk'] = float(s), c

    def _weighted(item):
        d = km.get(item[0]) or {}
        f = 1.0
        if d.get('origin') == 'local':
            f *= kb._LOCAL_BOOST
        if d.get('stale'):
            f *= kb._STALE_PENALTY
        return item[1]['rrf'] * f

    ordered = sorted(merged.items(), key=_weighted, reverse=True)[:kk]
    hits = kb._annotate_kb_hits([
        {'path': p, 'score': round(e['rrf'], 4), 'text': (e['chunk'].get('text') or ''),
         'source': kb._kb_source_label(p),
         'matchedBy': (['question'] if 0 in e['from'] else [])
                      + [norm[j - 1]['label'] for j in e['from'] if j > 0][:3]}
        for p, e in ordered])
    texts = {p: list(e['chunks']) for p, e in ordered}
    refs = [h['path'] for h in hits]

    # 覆盖率两路（口径见 docstring）：原问 vs 原问命中；归一串 vs **它自己的**命中。
    cover_raw = kb._best_coverage(q, [c.get('text') or '' for _s, c in per_query[0]])
    cover_norm, norm_best = 0.0, ''
    for i, n in enumerate(norm, start=1):
        cv = kb._best_coverage(n['exp'], [c.get('text') or '' for _s, c in per_query[i]])
        if cv > cover_norm:
            cover_norm, norm_best = cv, n['label']
    cover = max(cover_raw, cover_norm)
    if not hits or cover < 0.1:
        quality = 'no_hit'
    elif cover < 0.4:
        quality = 'low_confidence'
    else:
        quality = 'ok'

    steps, codes = _steps_and_code(texts, refs)
    out = {'ok': True, 'op': 'flythings_help', 'question': q, 'count': len(hits),
           'normalized': norm, 'hits': hits, 'refs': refs, 'steps': steps, 'code': codes,
           'nextOps': next_ops(refs), 'quality': quality, 'coverage': round(cover, 3),
           'coverageRaw': round(cover_raw, 3), 'coverageNorm': round(cover_norm, 3),
           'retrieval': 'bm25' if degraded else 'vector+bm25(RRF)', 'degraded': bool(degraded),
           'warnings': warnings}
    if norm_best:
        out['coveredBy'] = norm_best
    if platform:
        out['platform'] = str(platform)
    if project_root:
        # 项目层知识（<项目>/docs/kb/）也在检索索引里；回显路径便于把结论回填到项目知识层
        out['projectRoot'] = str(project_root)

    if quality == 'no_hit':
        out['notice'] = kb.NO_HIT_NOTICE
        out['positioning'] = kb._positioning_field()
        # **只有多重归一后仍 no_hit 才记账**（2026-10-07 口径）：归一后命中/低置信一律不写，
        # 否则「明明有答案」的问法会持续污染知识缺口清单。
        try:
            logr = kb_local.log_no_hit(q, 'no_hit', refs, kk)
        except Exception as e:           # 日志失败不影响检索本身，但必须让调用方看见
            logr = {'logged': False, 'error': repr(e)}
            warnings.append('未命中日志写入失败（不影响检索）：%s' % e)
        out['gapLogged'] = bool(logr.get('logged'))
        out['gapLog'] = logr.get('file', '')
        out['gapHint'] = ('本条已记入知识缺口清单（scripts/kb_gaps.py 生成 kb_gaps.md）；'
                          '要补这条知识：flythings_knowledge_capture(...) → 补 evidence → '
                          'scripts/kb_verify.py 复验 → 人工签字后才入库')
    elif quality == 'low_confidence':
        out['notice'] = ('低置信命中（归一后最高覆盖率 %.2f）：片段可能只是话题相近；'
                         '结论前请打开 path 对应文档核对，或换更具体的问法。'
                         '若确认未收录：禁止用 Qt/Android/LVGL/emWin/AWTK 等其它 GUI 框架类推，'
                         '请查官方文档 developer.flythings.cn 或转人工确认。' % cover)
        out['positioning'] = kb._positioning_field()
    else:
        if norm_best:
            out['notice'] = ('原话覆盖率 %.2f 偏低，但按「%s」归一后命中（%.2f）——'
                             '结论以命中片段为准，动手前核对 path 原文。'
                             % (cover_raw, norm_best, cover_norm))
    return out


def run_json(question, k=3, platform='', project_root=''):
    """op 出口：json 字符串（kb_tools.flythings_help 只做这一步转发）。"""
    return json.dumps(run(question, k, platform, project_root), ensure_ascii=False)
