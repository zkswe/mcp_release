# -*- coding: utf-8 -*-
"""硬件型号库（平台 → 型号 → 规格 + 平台/型号差异化）。

为什么需要（沛哥 2026-09-12）：客户/开发者手上是一台具体硬件，但 AI 只认平台名，
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
        bad = [k for k in plats if not _known_platform(k)]
        if bad:
            warn.append('hardware_catalog.json 里出现未知平台名 %s——'
                        '平台名必须取 platforms.py 的规范名（%s）'
                        % (','.join(sorted(bad)), ','.join(_platform_names())))
    _CACHE['cat'] = cat
    _CACHE['warn'] = warn
    return cat, warn


def _platform_names():
    try:
        import platforms as pl
        return pl.supported()
    except Exception as e:               # 平台模块异常不吞：照实标未校验
        return ['<platforms.py 不可用: %s>' % e]


def _known_platform(name):
    try:
        import platforms as pl
        return bool(pl.normalize(name))
    except Exception:
        return True                      # 校验器不可用时不做平台名拦截


def normalize_platform(name):
    """把用户给的平台名归一（z21 → Z21）；空 = 全部平台；无法识别返回 None。"""
    if name is None or str(name).strip() == '':
        return ''
    try:
        import platforms as pl
        return pl.normalize(name)
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


def _pack_entry(platform, name, entry):
    """条目 → 对外返回结构（原样带出，另加可读摘要字段，不丢原始字段）。"""
    out = dict(entry)
    out['platform'] = platform
    out['model'] = name
    out['summary'] = _brief(entry)
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


def _preset(entry, platform):
    """预设参数：开工直接照抄的一组值（平台/分辨率/方向/按键），省掉后续逐个确认。"""
    sc = entry.get('screen') or {}
    res = sc.get('resolution') or ''
    if not res and sc.get('width') and sc.get('height'):
        res = '%sx%s' % (sc['width'], sc['height'])
    pre = {'platform': platform or '', 'resolution': res}
    if sc.get('orientation'):
        pre['orientation'] = sc['orientation']
    if sc.get('interface'):
        pre['display'] = sc['interface']
    if entry.get('keys'):
        pre['keys'] = entry['keys'].get('values') or []
    pre['note'] = ('有具体型号就按这组预设参数开工（不用再问分辨率/按键）；'
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
        hw = _pack_entry(pname, mname, entry)
        meta = (cat.get('platforms', {}).get(pname) or {})
        return {'ok': True, 'mode': 'model',
                'platform': pname,
                'model': mname,
                'preset': _preset(entry, pname),
                'hardware': hw,
                'platformSummary': meta.get('summary', ''),
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
                              '确认要补这个型号时告诉沛哥加进 hardware_catalog.json',
                      'retryable': True},
            'fallback': {'platform': plat or '',
                         'need': ['平台', '分辨率'],
                         'advice': '按平台 + 分辨率开工即可；不猜规格（避免同系列外推出错）'},
            'suggestions': sug,
            'available': avail,
            'warnings': warn}


# ---------------- 文档生成（单一来源 → 可检索 markdown）----------------

def build_markdown(cat=None):
    """由硬件库生成 knowledge/hardware/hardware-models.md 全文（单一事实来源的派生）。"""
    if cat is None:
        cat, _ = load()
    L = ['# 硬件型号库（平台 → 型号 → 规格 / 预设参数）', '',
         '> 检索关键词：型号 / 硬件 / 平台型号 / 屏幕分辨率 / 按键值 / PocketDisplay4 / '
         'SW80480070D / SV50PD / 86盒 / 串口屏 / 价签 / 选型',
         '> 用法：**有具体型号** → 按该型号的预设参数开工（平台/分辨率/按键直接照抄）；'
         '**没有具体型号** → 确认平台 + 分辨率即可建工程，其余按需再问。',
         '> 本文档由 `scripts/gen_hardware_doc.py` 从 `hardware_catalog.json` 生成，**勿手改**'
         '（改 json 后重跑生成器 + `rebuild_index_local.py`）。',
         '> 查询用工具：`flythings_hardware_info(model, platform)`；'
         '未收录型号会返回候选与「平台 + 分辨率即可」的开工建议，不猜规格。', '' ]
    plats = cat.get('platforms', {})
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
            for d in (e.get('differences') or []):
                L.append('- 差异·%s：%s' % (d.get('topic', ''), d.get('detail', '')))
            for m in (e.get('optional') or []):
                L.append('- 可选补充（非阻塞，按需补）：%s' % m)
            if e.get('source'):
                L.append('- 数据来源：%s' % e['source'])
            L.append('- 数据状态：%s' % e.get('dataStatus', ''))
            L.append('')
    return '\n'.join(L).rstrip() + '\n'
