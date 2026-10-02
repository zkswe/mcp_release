# -*- coding: utf-8 -*-
"""硬件型号库（平台 → 型号 → 规格 + 平台/型号差异化）。

为什么需要（2026-09-12）：客户/开发者手上是一台具体硬件，但 AI 只认平台名，
型号里的分辨率/按键值/接口差异全靠人肉回忆 → 建工程分辨率选错、按键值靠试。
本模块把「选硬件」变成一次查询：说型号（或只说平台）就能拿到分辨率、按键值、
接口配置、平台差异化与待确认项。

单一事实来源：**hardware_catalog.json**（人工维护；本模块只读，不写）
派生文档：knowledge/hardware/hardware-models.md（由 scripts/gen_hardware_doc.py 生成，勿手改）
改完 json 必须重跑生成器 + rebuild_index_local.py，否则检索到的还是旧型号表。

设计要点：
  - 型号匹配宽松：忽略大小写/空格/连字符/下划线（SW80480070D_C == sw80480070dc），别名可配
  - 查不到不编造：返回 not_found + 近似候选 + 平台可用型号清单（禁止 AI 猜规格）
  - missing[] 明确列出待补字段，让 AI 照实转述而不是脑补
  - 平台名过 platforms.py 校验（单一来源，不在这里另写平台表）
"""
import io
import json
import os

BASE = os.path.dirname(os.path.abspath(__file__))
CATALOG_PATH = os.path.join(BASE, 'hardware_catalog.json')

_CACHE = {}

# 查不到型号时最多给几个候选
_MAX_SUGGEST = 5


def _norm(s):
    """型号/平台归一：小写 + 去掉空格、连字符、下划线、点。"""
    return ''.join(ch for ch in str(s or '').lower()
                   if ch.isalnum())


def load(force=False):
    """读硬件库（带缓存）。返回 (catalog_dict, warnings[])。读不到不抛，回空库 + warning。"""
    if not force and 'cat' in _CACHE:
        return _CACHE['cat'], _CACHE['warn']
    warn = []
    cat = {'schema': 1, 'note': '', 'platforms': {}}
    if not os.path.isfile(CATALOG_PATH):
        warn.append('hardware_catalog.json 不存在（%s）——硬件库为空；'
                    '请检查安装包完整性' % CATALOG_PATH)
    else:
        try:
            cat = json.loads(io.open(CATALOG_PATH, encoding='utf-8').read())
        except (OSError, ValueError) as e:
            warn.append('hardware_catalog.json 解析失败（%s: %s）——硬件库按空处理'
                        % (type(e).__name__, e))
            cat = {'schema': 1, 'note': '', 'platforms': {}}
    plats = cat.get('platforms')
    if not isinstance(plats, dict):
        warn.append('hardware_catalog.json 缺 platforms 对象')
        cat['platforms'] = {}
    else:
        bad = [k for k in plats if _known_platform(k) is False]
        if bad:
            warn.append('hardware_catalog.json 里出现未知平台名 %s——'
                        '平台名必须取 platforms.py 的规范名（%s）'
                        % (','.join(sorted(bad)), ','.join(_platform_names())))
        warn.extend(_VALIDATOR_WARN)     # 校验器坏掉时如实报，不当成「校验通过」
    _CACHE['cat'] = cat
    _CACHE['warn'] = warn
    return cat, warn


_VALIDATOR_WARN = []          # 平台校验器不可用时的如实记录（不静默、不假装通过）


def _platform_names():
    try:
        import platforms as pl
        return pl.supported()
    except Exception as e:               # 平台模块异常不吞：照实标未校验
        _VALIDATOR_WARN.append(
            'platforms.py 不可用（%s: %s）——平台名未校验，按原样放行'
            % (type(e).__name__, e))
        return ['<platforms.py 不可用: %s>' % e]


def _known_platform(name):
    """平台名是否符合 platforms.py 规范。

    True = 已知；False = 确定是未知名字；**None = 校验器不可用（未校验）**。
旧实现这里是 `except Exception: return True`——把「没校验」说成「通过」，
属于静默瞒报：平台模块一旦坏掉，脏平台名会被当成合法数据放行。
    """
    try:
        import platforms as pl
        return bool(pl.normalize(name))
    except Exception:
        return None


def normalize_platform(name):
    """把用户给的平台名归一（z21 → Z21；**V851S/V853S 等芯片名 → V85X**）；空 = 全部平台；
无法识别返回 None。

    ⚠️ v0.27.87：原先只走 `platforms.normalize`（只认规范名+少数历史别名）→ `hardware_info(platform='V851S')`
回 BAD_PLATFORM「未知平台」，而同一串拿去查包却是认的（V85x 芯片名 → v85x 包键）——
这正是 v0.27.41 检讨过的「同一个平台名，包查询认、另一个工具不认」。现在补一道
    `platforms.resolve`（认包生态变体 + 芯片名）作兑底。
仅包生态的平台（z6s/z261/h500s/a33nor）**仍回 None**：交给调用方的
    PLATFORM_NOT_IN_HARDWARE_LIB 专用错误码说明「真平台、硬件库未登记」，不当未知平台。
    """
    if name is None or str(name).strip() == '':
        return ''
    try:
        import platforms as pl
        got = pl.normalize(name)
        if got:
            return got
        r = pl.resolve(name)
        if r and r.get('canonical') in pl.PLATFORMS:
            return r['canonical']
        return None
    except Exception:
        return None


def _iter_models(cat, platform=''):
    """按 (平台, 型号名, 条目) 遍历；platform 为空则全部。"""
    plats = cat.get('platforms', {})
    for pname in sorted(plats):
        if platform and pname.upper() != str(platform).upper():
            continue
        models = plats[pname].get('models') or {}
        for mname in sorted(models):
            yield pname, mname, models[mname] or {}


def _match_keys(entry, name):
    """条目可用于匹配的字符串集合（型号名 + 别名 + 平台前缀组合）。"""
    keys = {name}
    for a in (entry.get('aliases') or []):
        keys.add(a)
    return {_norm(k) for k in keys if k}


def _screen_line(entry):
    sc = entry.get('screen') or {}
    res = sc.get('resolution') or ''
    if not res and sc.get('width') and sc.get('height'):
        res = '%sx%s' % (sc['width'], sc['height'])
    parts = []
    if sc.get('inch'):
        parts.append('%s 寸' % sc['inch'])
    if res:
        parts.append(res)
    if sc.get('orientation') == 'portrait':
        parts.append('竖屏')
    elif sc.get('orientation') == 'landscape':
        parts.append('横屏')
    return ' '.join(parts) or (sc.get('note') or '')


def _key_line(entry):
    k = entry.get('keys') or {}
    vals = k.get('values') or []
    if not vals:
        return ''
    codes = k.get('linuxKeyCodes') or []
    pair = ', '.join('%s%s' % (v, ('(%s)' % codes[i]) if i < len(codes) else '')
                     for i, v in enumerate(vals))
    return '%d 键：%s' % (k.get('count') or len(vals), pair)


def _brief(entry):
    """列表里每型号一行摘要。"""
    out = [_screen_line(entry)]
    kl = _key_line(entry)
    if kl:
        out.append(kl)
    if entry.get('kind'):
        out.append(entry['kind'])
    return '；'.join(p for p in out if p)


def _pack_entry(platform, name, entry, plat_meta=None):
    """条目 → 对外返回结构（原样带出，另加可读摘要字段，不丢原始字段）。"""
    out = dict(entry)
    out['platform'] = platform
    out['model'] = name
    out['summary'] = _brief(entry)
    out['defaults'] = _merged_defaults(entry, plat_meta)
    res = (entry.get('screen') or {}).get('resolution') or ''
    if not res:
        w, h = (entry.get('screen') or {}).get('width'), (entry.get('screen') or {}).get('height')
        res = '%sx%s' % (w, h) if w and h else ''
    out['resolution'] = res
    return out


def _suggest(cat, model):
    """近似候选：型号串互为子串（如 pd4 → PocketDisplay4）。"""
    want = _norm(model)
    if not want:
        return []
    hits = []
    for pname, mname, entry in _iter_models(cat):
        for k in _match_keys(entry, mname):
            if want in k or k in want:
                hits.append({'platform': pname, 'model': mname, 'summary': _brief(entry)})
                break
    return hits[:_MAX_SUGGEST]


# AI 需要的命名规则键（v0.27.178）：只留「用户报型号时要用」的。
# 维护者口径（platformLetter / lettersNote / legacyLabelWarning）**不随每次调用返回**——
# 它是给人看的（哪个字母是哪个平台、旧文档哪里写错过），只进知识页。
AI_NAMING_KEYS = ('structure', 'example', 'decode', 'limit')


def _ai_naming_rules(cat):
    """命名规则里 AI 真正要用的那部分（结构/示例/命名段解码/使用边界）。"""
    nr = cat.get('namingRules') or {}
    return {k: nr[k] for k in AI_NAMING_KEYS if nr.get(k)}


def _platform_overview(cat, platform=''):
    """按平台汇总（含平台级差异化与待补项）。"""
    out = []
    plats = cat.get('platforms', {})
    for pname in sorted(plats):
        if platform and pname.upper() != str(platform).upper():
            continue
        meta = plats[pname] or {}
        models = []
        for mname, entry in sorted((meta.get('models') or {}).items()):
            models.append({'model': mname, 'summary': _brief(entry),
                           'dataStatus': entry.get('dataStatus', ''),
                           'aliases': entry.get('aliases') or []})
        out.append({
            'platform': pname,
            'summary': meta.get('summary', ''),
            'chips': meta.get('chips') or [],
            # v0.27.87：芯片级登记（"哪个芯片实测过/哪些只能待确认" + 平台与包键的绑定说明）
            'chipsNote': meta.get('chipsNote', ''),
            'chipEntries': meta.get('chipEntries') or {},
            'defaults': meta.get('defaults') or {},
            'differences': meta.get('differences') or [],
            'platformOptional': meta.get('optional') or [],
            'modelCount': len(models),
            'models': models,
        })
    return out


def _next_steps(entry, platform):
    """拿到硬件后的落地建议（预设参数可直接用，不用再问再查）。"""
    steps = []
    sc = entry.get('screen') or {}
    res = sc.get('resolution') or ''
    if not res and sc.get('width') and sc.get('height'):
        res = '%sx%s' % (sc['width'], sc['height'])
    if res:
        steps.append('建工程按此分辨率：flythings_create_project(platform="%s", resolution="%s")'
                     % (platform or '<平台>', res))
    if entry.get('keys'):
        k = entry['keys']
        steps.append('按键值 %s 直接用（/dev/input 事件 code），不用试'
                     % ', '.join(str(v) for v in (k.get('values') or [])))
    if (entry.get('dataStatus') or '') != 'complete':
        steps.append('其余参数未入库不影响开工（有平台 + 分辨率即可）；'
                     '真要用到具体接口/差异时再补库，不必为它停下来核对')
    return steps


def _merged_defaults(entry, plat_meta=None):
    """合并默认参数：平台级 defaults 打底，型号级覆盖（现场反馈：「平台差异」= 型号默认参数，开箱可照抄）。"""
    d = {}
    for src in ((plat_meta or {}).get('defaults') or {}, entry.get('defaults') or {}):
        if isinstance(src, dict):
            d.update(src)
    return d


def _preset(entry, platform, plat_meta=None):
    """预设参数：开工直接照抄的一组值（平台级 + 型号级默认参数，开发不用猜）。"""
    pre = _merged_defaults(entry, plat_meta)
    sc = entry.get('screen') or {}
    res = sc.get('resolution') or ''
    if not res and sc.get('width') and sc.get('height'):
        res = '%sx%s' % (sc['width'], sc['height'])
    if platform:
        pre['platform'] = platform
    if res:
        pre['resolution'] = res
    if sc.get('orientation'):
        pre['orientation'] = sc['orientation']
    if sc.get('interface'):
        pre['display'] = sc['interface']
    if entry.get('keys'):
        pre['keys'] = entry['keys'].get('values') or []
    pre['note'] = ('有具体型号就按这组默认参数开工（分辨率/方向/按键等不用再猜）；'
                   '没有具体型号时，确认平台 + 分辨率即可，其余按需再问')
    return pre


# 没有具体型号（或型号未收录）时的一句话准则：平台 + 分辨率就够开工。
WHEN_UNKNOWN = ('没有具体型号时不必卡在这里：确认**平台 + 分辨率**就能建工程/写 UI，'
                '其余参数按需再问/再补库（预设知识只为省掉反复核对，不是开工前置条件）。')


def query(model='', platform=''):
    """硬件库查询入口。

    model 为空 → 列平台与型号（platform 可过滤）；model 给了 → 返回该型号完整条目。
返回 dict（由调用方 json.dumps）：
      {ok, mode: overview|model|not_found, platforms/model/hardware/..., warnings}
    """
    cat, warn = load()
    plat = normalize_platform(platform)
    if plat is None:
        # 区分「真实平台但硬件库没登记」与「完全不认识」：
        # 一律回「未知平台」等于把 z6s/z261 这类真平台判成不存在（AI 会去瞎猜）。
        pkg_only = None
        try:
            import platforms as pl
            _info = pl.resolve(platform)
            pkg_only = _info if (_info and _info.get('packageOnly')) else None
        except Exception:
            pkg_only = None
        if pkg_only:
            return {'ok': False, 'mode': 'bad_platform',
                    'error': {'code': 'PLATFORM_NOT_IN_HARDWARE_LIB',
                              'msg': '平台 %s 是真实平台（%s），但硬件库还没登记它的型号'
                                     % (pkg_only['canonical'],
                                        pkg_only.get('note') or '仅依赖包生态'),
                              'hint': '硬件库已登记的平台：%s（不编造未登记平台的规格）'
                                      % ', '.join(sorted(cat.get('platforms', {}))),
                              'retryable': True},
                    'warnings': warn}
        return {'ok': False, 'mode': 'bad_platform',
                'error': {'code': 'BAD_PLATFORM',
                          'msg': '未知平台 %r' % platform,
                          'hint': '可用平台：%s（也可用别名，如 V85XEMMC）'
                                  % ', '.join(_platform_names()),
                          'retryable': True},
                'warnings': warn}

    if not str(model or '').strip():
        plats = _platform_overview(cat, plat)
        if not plats:
            return {'ok': False, 'mode': 'overview',
                    'error': {'code': 'NO_PLATFORM',
                              'msg': '硬件库中无此平台：%r' % (platform or ''),
                              'hint': '已登记平台：%s'
                                      % ', '.join(sorted(cat.get('platforms', {}))) or '（空库）',
                              'retryable': True},
                    'warnings': warn}
        return {'ok': True, 'mode': 'overview',
                'platformCount': len(plats),
                'modelCount': sum(p['modelCount'] for p in plats),
                'platforms': plats,
                'fields': ('每个型号：model/summary/dataStatus/aliases；'
                           '取单型号规格传 model=<型号>'),
                'whenNoModel': WHEN_UNKNOWN,
                'namingRules': _ai_naming_rules(cat),
                'note': ('平台差异化与可选补充分别在 platforms[].differences / optional[]；'
                         '型号详情含 screen/keys/specs/differences/optional/source，'
                         '并自带 preset（开工直接照抄的平台+分辨率(+按键)）'),
                'warnings': warn}

    want = _norm(model)
    exact, loose = [], []
    for pname, mname, entry in _iter_models(cat, plat):
        keys = _match_keys(entry, mname)
        if _norm(mname) == want or want in keys:
            exact.append((pname, mname, entry))
        elif any(want in k for k in keys):
            loose.append((pname, mname, entry))
    hits = exact or loose
    if len(hits) == 1:
        pname, mname, entry = hits[0]
        meta = (cat.get('platforms', {}).get(pname) or {})
        hw = _pack_entry(pname, mname, entry, meta)
        return {'ok': True, 'mode': 'model',
                'platform': pname,
                'model': mname,
                'preset': _preset(entry, pname, meta),
                'hardware': hw,
                'platformSummary': meta.get('summary', ''),
                'platformDefaults': meta.get('defaults') or {},
                'platformDifferences': meta.get('differences') or [],
                'platformOptional': meta.get('optional') or [],
                'nextSteps': _next_steps(entry, pname),
                'warnings': warn}
    if len(hits) > 1:
        return {'ok': True, 'mode': 'ambiguous',
                'query': str(model),
                'candidates': [{'platform': p, 'model': m, 'summary': _brief(e)}
                               for p, m, e in hits],
                'hint': '型号不唯一，请带 platform 或写全型号名再查',
                'warnings': warn}

    sug = _suggest(cat, model)
    avail = {}
    for pname in sorted(cat.get('platforms', {})):
        if plat and pname.upper() != plat.upper():
            continue
        avail[pname] = [m for _, m, _ in _iter_models(cat, pname)]
    return {'ok': False, 'mode': 'not_found',
            'query': str(model),
            'error': {'code': 'MODEL_NOT_FOUND',
                      'msg': '硬件库未收录型号 %r（不挡开发）' % model,
                      'hint': WHEN_UNKNOWN + ' 型号名可能有出入，先看 suggestions；'
                              '确认要补这个型号时告诉需求方加进 hardware_catalog.json',
                      'retryable': True},
            'fallback': {'platform': plat or '',
                         'need': ['平台', '分辨率'],
                         'advice': '按平台 + 分辨率开工即可；不猜规格（避免同系列外推出错）'},
            'namingRules': _ai_naming_rules(cat),
            'suggestions': sug,
            'available': avail,
            'warnings': warn}


# ---------------- 文档生成（单一来源 → 可检索 markdown）----------------

def build_markdown(cat=None):
    """由硬件库生成 knowledge/hardware/hardware-models.md 全文（单一事实来源的派生）。"""
    if cat is None:
        cat, _ = load()
    L = ['# 硬件型号库（平台 → 型号 → 规格 / 预设参数）', '',
         '> 检索导引：问「这块板什么分辨率/按键值/接口 / SW 型号怎么读（SW80480070D1 等）/ '
         'SV50PD·86 盒·价签规格 / 没给型号能不能开工」→ 本文（机读查询用 `flythings_hardware_info`；'
         '本页由生成器产出勿手改）。',
         '> 检索关键词：型号 / 硬件 / 平台型号 / 屏幕分辨率 / 按键值 / PocketDisplay4 / '
         'SW80480070D / SV50PD / 86盒 / 串口屏 / 价签 / 选型',
         '> 用法：**有具体型号**→ 按该型号的预设参数开工（平台/分辨率/按键直接照抄）；'
         '**没有具体型号**→ 确认平台 + 分辨率即可建工程，其余按需再问。',
         '> 本文档由 `scripts/gen_hardware_doc.py` 从 `hardware_catalog.json` 生成，**勿手改**'
         '（改 json 后重跑生成器 + `rebuild_index_local.py`）。',
         '> 查询用工具：`flythings_hardware_info(model, platform)`；'
         '未收录型号会返回候选与「平台 + 分辨率即可」的开工建议，不猜规格。', '' ]
    plats = cat.get('platforms', {})
    nr = cat.get('namingRules') or {}
    if nr:
        L.append('## 型号命名规则（看型号名时参考）')
        L.append('')
        if nr.get('structure'):
            L.append('- 结构：%s' % nr['structure'])
        if nr.get('example'):
            L.append('- 示例：%s' % nr['example'])
        for k, v in (nr.get('platformLetter') or {}).items():
            L.append('- 平台/版本字母 %s：%s' % (k, v))
        if nr.get('lettersNote'):
            L.append('- ⚠️ 适用范围：%s' % nr['lettersNote'])
        for _dim, _m in (nr.get('decode') or {}).items():
            L.append('- 命名段解码·%s：%s'
                     % (_dim, '；'.join('%s=%s' % (a, b_) for a, b_ in _m.items())))
        if nr.get('limit'):
            L.append('- 使用边界：%s' % nr['limit'])
        if nr.get('legacyLabelWarning'):
            L.append('- ⚠️ 旧文档坑：%s' % nr['legacyLabelWarning'])
        L.append('')
    L.append('## 平台总览')
    L.append('')
    L.append('| 平台 | 型号数 | 已登记型号 | 平台定位 |')
    L.append('|------|-------|-----------|---------|')
    for pname in sorted(plats):
        meta = plats[pname] or {}
        models = sorted((meta.get('models') or {}).keys())
        L.append('| %s | %d | %s | %s |' % (pname, len(models),
                                            ' / '.join(models) or '（暂未登记）',
                                            meta.get('summary', '')))
    L.append('')
    for pname in sorted(plats):
        meta = plats[pname] or {}
        L.append('## %s' % pname)
        L.append('')
        if meta.get('summary'):
            L.append('- 平台定位：%s' % meta['summary'])
        if meta.get('chips'):
            L.append('- 常见主控：%s' % ' / '.join(meta['chips']))
        if meta.get('chipsNote'):
            L.append('- 主控→平台/包键（写死口径）：%s' % meta['chipsNote'])
        for cname in sorted(meta.get('chipEntries') or {}):
            ce = (meta['chipEntries'] or {}).get(cname) or {}
            bits = []
            if ce.get('kind'):
                bits.append(ce['kind'])
            if ce.get('aliases'):
                bits.append('别名 %s' % ' / '.join(ce['aliases']))
            if ce.get('dataStatus'):
                bits.append('数据状态=%s' % ce['dataStatus'])
            L.append('- 主控 %s：%s%s'
                     % (cname, '；'.join(bits) + '。' if bits else '', ce.get('note', '')))
            if ce.get('source'):
                L.append('  - 依据：%s' % ce['source'])
        pdef = meta.get('defaults') or {}
        if pdef:
            L.append('- 平台默认参数：%s'
                     % '；'.join('%s=%s' % (k, v) for k, v in pdef.items()))
        for d in (meta.get('differences') or []):
            L.append('- 平台差异·%s：%s' % (d.get('topic', ''), d.get('detail', '')))
        for m in (meta.get('optional') or []):
            L.append('- 可选补充（非阻塞）：%s' % m)
        L.append('')
        for mname in sorted(meta.get('models') or {}):
            e = meta['models'][mname] or {}
            L.append('### %s（%s）' % (mname, pname))
            L.append('')
            if e.get('kind'):
                L.append('- 形态：%s' % e['kind'])
            if e.get('aliases'):
                L.append('- 别名：%s' % ' / '.join(e['aliases']))
            nm = e.get('naming') or {}
            if nm:
                L.append('- 型号命名：字母 %s = %s'
                         % (nm.get('letter', ''), nm.get('meaning', '')))
            if _brief(e):
                L.append('- 摘要：%s' % _brief(e))
            sc = e.get('screen') or {}
            if sc:
                bits = []
                for k, label in (('inch', '尺寸(寸)'), ('width', '宽'), ('height', '高'),
                                 ('resolution', '分辨率'), ('orientation', '方向'),
                                 ('interface', '接口'), ('touch', '触摸'), ('note', '说明')):
                    if sc.get(k) not in (None, '', []):
                        bits.append('%s=%s' % (label, sc[k]))
                if bits:
                    L.append('- 屏幕：%s' % '，'.join(str(b) for b in bits))
            if e.get('screenNote'):
                L.append('- 屏幕判定依据：%s' % e['screenNote'])
            if e.get('labelNote'):
                L.append('- %s' % e['labelNote'])
            k = e.get('keys') or {}
            if k:
                codes = k.get('linuxKeyCodes') or []
                pairs = ['%s%s' % (v, ('(%s)' % codes[i]) if i < len(codes) else '')
                         for i, v in enumerate(k.get('values') or [])]
                L.append('- 按键：%d 个，按键值 %s' % (k.get('count') or len(pairs),
                                                      ', '.join(pairs)))
                if k.get('note'):
                    L.append('  - %s' % k['note'])
            for sk, sv in (e.get('specs') or {}).items():
                L.append('- %s：%s' % (sk, sv))
            mdef = _merged_defaults(e, meta)
            if mdef:
                L.append('- **默认参数（开发直接照抄）**：%s'
                         % '；'.join('%s=%s' % (k, v) for k, v in mdef.items()))
            for rf in (e.get('docRefs') or []):
                L.append('- 资料：`%s`' % rf)
            for g in (e.get('pinGroups') or []):
                pins = g.get('pins') or []
                if not pins:
                    continue
                cols = ('pin', 'name', 'default', 'io', 'alt', 'note')
                head = {'pin': 'PIN', 'name': '名称', 'default': '默认功能',
                        'io': 'IO', 'alt': '复用', 'note': '备注'}
                use = [k for k in cols if any(p.get(k) for p in pins)]
                L.append('')
                L.append('#### 管脚定义 · %s' % g.get('name', ''))
                L.append('')
                L.append('| ' + ' | '.join(head[k] for k in use) + ' |')
                L.append('|' + '---|' * len(use))
                for pin in pins:
                    cells = []
                    for k in use:
                        v = pin.get(k)
                        if isinstance(v, list):
                            v = ' / '.join(str(x) for x in v)
                        cells.append(str(v if v is not None else ''))
                    L.append('| ' + ' | '.join(cells) + ' |')
                L.append('')
            for d in (e.get('differences') or []):
                L.append('- 差异·%s：%s' % (d.get('topic', ''), d.get('detail', '')))
            for m in (e.get('optional') or []):
                L.append('- 可选补充（非阻塞，按需补）：%s' % m)
            if e.get('source'):
                L.append('- 数据来源：%s' % e['source'])
            L.append('- 数据状态：%s' % e.get('dataStatus', ''))
            L.append('')
    return '\n'.join(L).rstrip() + '\n'
