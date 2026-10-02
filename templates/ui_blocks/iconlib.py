# -*- coding: utf-8 -*-
"""块库图标解析层：语义图标名 → `components/icons` 图标资产库（**唯一图标源**）。

背景（2026-10-01）：「这些网络/设备的 icon 来源？效果差异和实际差异太大」——
块库原先的 `glyph()` 走 `ui_tools/gen_res.glyph_icon()` 的兜底（默认 style=emoji → 查
`_GLYPH_EMOJI` + 本地 emoji 字体，缺字体退简笔线框），与**真机/产品用的那套图标**不是同一套图形。
本模块把块库图标接到 `components/icons`：

  · **唯一来源**= `components/icons`（v0.3.1 = Tabler Icons 3.46.0 单色烘焙 PNG；
矢量源 `vendor/tabler/**`，生成器 `components/icons/scripts/gen_icons.py`）。
块库**不自绘图标、不用 emoji 字体**（真机没有那套字体）。
  · **产物图 == 控件盒**（工程铁律 #11/#17：引擎对「图 ≠ 盒」是**拉伸填充**）——
本模块按盒尺寸取档/出图，绝不拉伸。
  · **档位（按目标盒尺寸选）**：盒 ≥ 44px → **56 档**；≥ 26px → **24 档**；否则 **22 档**
    （与 `blocks/_tokens.json` 的 `glyph_min_px = 24` 对齐）。盒尺寸**正好等于**档位
    ——直接取库里 `out/<档>/` 那张现成 PNG（白底烘焙，故只在要求白色时命中）；
    **缺档**（如极小屏空态 16px、基准屏空态 36px）→ 用库自带生成器按**盒尺寸**现出
    （缺档补齐，**不为凑档放大控件盒**）。
  · **颜色**：FlyThings 无 tint API，颜色必须生成时烘焙（见 `components/icons/README.md` 的
    `palette.note`）——所以按调用方给的颜色现出；库预置产物是白的。
  · **回退**：库里查不到该语义名 → 返回 None，由调用方（`compose.py`）回退 `gen_res` 线框，
并在 compose 输出里**明说「回退线框」**（不静默）。

对外 API：
    available()                      → 资产库可用？（catalog + 生成器都在）
    lookup(token)                    → 语义名 → 库条目 dict（查不到返回 None）
    tier_of(box)                     → 盒尺寸 → 档位（56 / 24 / 22）
    produce(token, box, rgb, state)  → (PIL.Image, meta)；图尺寸严格 == box
    allowed_names()                  → 库里的语义名清单（供文档/blocks 的「允许值」）
    is_tier_size(n)                  → n 是否 == 22/24/56（预置档）

缓存：
    FLYTHINGS_ICONS_CACHE 指到 <workspace>/temp/ui_blocks_icons/（解包出来的 Tabler SVG +
本模块渲染的 PNG 缓存）——**不往 `components/icons/out/` 里写任何新档位**（不动他人产物）。
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))                    # tools/FlyThings_mcp_open
LIB = os.path.join(REPO, 'components', 'icons')                  # 图标资产库根
LIB_SCRIPTS = os.path.join(LIB, 'scripts')
LIB_CATALOG = os.path.join(LIB, 'catalog.json')

# 档位规则（盒 ≥ 阈值 → 档位）；与 _tokens.json 的 glyph_min_px 对齐
TIER_LADDER = ((44, 56), (26, 24), (0, 22))
TIER_SIZES = (22, 24, 56)

# 块库语义名 → 库里语义名（只登记 catalog 的 name/icon/aliases 都查不到的补充/歧义消解；
# 其余一律交给库自带生成器 gen_icons.resolve_target 解析——**不另建一份名字表**，避免与库漂移）
ALIASES = {
    'toggle': 'control.toggle-right',        # 库里叫 toggle-left / toggle-right
    'toggle-on': 'control.toggle-right',
    'switch': 'control.switch-3',            # 拨动开关
    'forward': 'control.chevron-right',      # 旧名兜底（行尾箭头另走本库的 chevron 口径，见 README §8-3）
}


def _cache_root():
    """SVG/PNG 缓存根：env 覆盖 → <workspace>/temp/ui_blocks_icons → 系统临时目录。"""
    env = os.environ.get('FLYTHINGS_ICONS_CACHE')
    if env:
        return env
    ws = os.path.dirname(os.path.dirname(REPO))                  # tools 的上一层 = workspace
    if os.path.isdir(os.path.join(ws, 'temp')):
        return os.path.join(ws, 'temp', 'ui_blocks_icons')
    return os.path.join(tempfile.gettempdir(), 'flythings_uiblocks_icons')


PNG_CACHE = os.path.join(_cache_root(), 'png')                    # 本模块渲染结果缓存

_gen = None
_cat = None
_lookup_cache = {}
_mem = {}


# ─────────────────────────── 资产库加载（惰性、失败即回退） ───────────────────────────


def _load():
    """惰性导入库自带生成器。返回 True = 资产库可用；False = 调用方走回退（不抛异常）。"""
    global _gen, _cat
    if _gen is not None:
        return True
    if not os.path.isfile(LIB_CATALOG):
        return False
    os.environ.setdefault('FLYTHINGS_ICONS_CACHE', _cache_root())
    if LIB_SCRIPTS not in sys.path:
        sys.path.insert(0, LIB_SCRIPTS)
    try:
        import gen_icons                                          # noqa: E402库自带唯一入口
    except Exception:                                             # noqa: BLE001
        return False
    try:
        _cat = gen_icons.load_catalog()                            # components/icons/catalog.json
    except Exception:                                             # noqa: BLE001
        return False
    _gen = gen_icons
    return True


def available():
    return _load()


def lookup(token):
    """语义名 → 库条目 dict；查不到 / 库不可用 → None。

支持：语义名（wifi）/ 语义全名（system.wifi）/ 别名（bell-off / x / dots）/
    Tabler 原生名（cloud-rain）/ 旧产物名（ic_system_wifi.png）。
    """
    key = str(token or '').strip().lower()
    if not key:
        return None
    if key in _lookup_cache:
        return _lookup_cache[key]
    if not _load():
        _lookup_cache[key] = None
        return None
    probe = ALIASES.get(key, key)
    try:
        it, style = _gen.resolve_target(_cat, probe)
    except SystemExit:                                            # 库里没有这个名字
        _lookup_cache[key] = None
        return None
    style = style or (it['styles'][0] if it.get('styles') else 'tabler')
    v = it['variants'][style]
    info = {
        'token': str(token).strip(),
        'name': it['name'],                                       # 语义全名（system.wifi）
        'icon': it['icon'],                                       # 短名（wifi）
        'category': it['category'],
        'source': it.get('source', ''),
        'style': style,
        'states': list(v['states'] or ['']),
        'variant': v,
        'defaultColor': list(it.get('defaultColor') or [255, 255, 255]),
        'aliased': probe != key,
    }
    _lookup_cache[key] = info
    return info


# ─────────────────────────── 档位 / 尺寸 ───────────────────────────


def tier_of(box):
    """目标盒尺寸 → 档位（盒 ≥ 44 → 56；≥ 26 → 24；否则 22；**盒 == 预置档尺寸时取该档**）。

最后一条是 2026-10-01 实测补的：24px 盒按「≥26」阈值会落到 22 档，但库里 24 档明明有
现成产物，且「盒 == 档」才能直接取库里那张（产物图仍严格 == 盒）。
    """
    box = int(box)
    if box in TIER_SIZES:
        return box
    for lo, tier in TIER_LADDER:
        if box >= lo:
            return tier
    return TIER_SIZES[0]


def is_tier_size(n):
    return int(n) in TIER_SIZES


def prebuilt_png(info, tier, state):
    """库里 `out/<档>/` 的现成产物（白底烘焙）——存在才返回路径。"""
    files = info['variant']['files']
    if state not in files:
        if not files:
            return None
        state = list(files)[0]
    p = os.path.join(LIB, 'out', str(tier), files[state])
    return p if os.path.isfile(p) else None


# ─────────────────────────── 出图 ───────────────────────────


def produce(token, box, rgb, state=None):
    """按**盒尺寸**出图 → (PIL.Image, meta dict)；图尺寸严格 == box。

优先级（都不改盒尺寸）：
      ① 盒尺寸 == 档位（22/24/56）且库里有该状态产物 → 取库里 `out/<档>/` 那张：要求白色 → 原图直用；其它颜色 → 按 alpha 换色（库 PNG 就是「RGB 恒等于 --color，
         alpha = 覆盖率」，换色与重新渲染**像素等价**；见交付报告里的 maxdiff=0 实证）；
      ② 其余（缺档：16 / 36 / …）→ 用库自带生成器 `gen_icons.py` 按盒尺寸 + 指定颜色现出。
查不到该语义名 → 抛 LookupError（调用方回退线框并**明说**）。
    """
    info = lookup(token)
    if info is None:
        raise LookupError('components/icons 里没有语义名 %r' % (token,))
    box = int(box)
    rgb = tuple(int(c) for c in rgb[:3])
    states = info['states']
    st = state if (state in states) else states[0]
    tier = tier_of(box)
    from PIL import Image

    mem_key = (info['name'], st, box, rgb, info['style'])
    if mem_key in _mem:
        img, render = _mem[mem_key]
        return img, _meta(info, box, tier, st, render)

    # ① 预置档命中（尺寸 == 档 + 库里有该状态产物）→ 直接用库产物（需要时换色）
    p = prebuilt_png(info, box, st) if is_tier_size(box) else None
    if p:
        img = Image.open(p).convert('RGBA')
        if rgb == (255, 255, 255):
            _mem[mem_key] = (img, 'prebuilt')
            return img, _meta(info, box, tier, st, 'prebuilt')
        img = _recolor(img, rgb)
        _mem[mem_key] = (img, 'prebuilt+recolor')
        return img, _meta(info, box, tier, st, 'prebuilt+recolor')

    # ② 按盒尺寸现出（缺档补齐 / 非白颜色必须烘焙）
    fname = '%s%s_%s_%s_%d_%d-%d-%d.png' % (info['category'], '_' + info['icon'].replace('-', ''),
                                            info['style'], st or 'single', box,
                                            rgb[0], rgb[1], rgb[2])
    cp = os.path.join(PNG_CACHE, fname)
    if os.path.isfile(cp):
        img = Image.open(cp).convert('RGBA')
    else:
        job = dict(icon=info['name'], iconShort=info['icon'], category=info['category'],
                   style=info['style'], state=st, variant=info['variant'],
                   png=fname, source=info['source'])
        img = _gen.render_one(job, box, rgb, ss=8)                # 8× 超采样 + BOX 面积平均
        os.makedirs(PNG_CACHE, exist_ok=True)
        img.save(cp)
    _mem[mem_key] = (img, 'generated')
    return img, _meta(info, box, tier, st, 'generated')


def _recolor(img, rgb):
    """库 PNG 的 alpha 换色（库口径：RGB 恒等于 --color、alpha = 覆盖率）。"""
    import numpy as np
    from PIL import Image
    a = np.asarray(img.convert('RGBA'))[..., 3]
    arr = np.zeros(a.shape + (4,), dtype=np.uint8)
    arr[..., 0], arr[..., 1], arr[..., 2] = rgb[0], rgb[1], rgb[2]
    arr[..., 3] = a
    return Image.fromarray(arr, 'RGBA')


def _meta(info, box, tier, state, source):
    return {'token': info['token'], 'name': info['name'], 'icon': info['icon'],
            'category': info['category'], 'style': info['style'],
            'state': state, 'box': int(box), 'tier': tier, 'render': source,
            'svg': info['variant'].get('svg', {}).get(state) or
                   (list(info['variant'].get('svg', {}).values())[:1] or [''])[0],
            'aliased': info['aliased']}


# ─────────────────────────── 文档用清单 ───────────────────────────


def allowed_names():
    """库里全部语义名 → [(tooltip 用短名, 语义全名, 分类, 状态)]（按分类 + 名排序）。"""
    if not _load():
        return []
    rows = []
    for it in _cat['icons']:
        style = it['styles'][0] if it.get('styles') else 'tabler'
        v = it['variants'][style]
        rows.append((it['icon'], it['name'], it['category'], list(v['states'] or [''])))
    rows.sort(key=lambda r: (r[2], r[0]))
    return rows


def short_names_by_category():
    """{分类: [短名, ...]}——blocks/*.json 的「允许的图标名」清单就从这里摘。"""
    out = {}
    for icon, name, cat, _st in allowed_names():
        out.setdefault(cat, []).append(icon)
    return out
