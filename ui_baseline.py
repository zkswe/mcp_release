# -*- coding: utf-8 -*-
"""像素基线库（0 token）：给 UI 验收建**版本化基线**。

为什么单独做一层
----------------
`ui_visual(action="diff")` 只能比「两张临时图」——比完就散，谁也不知道
"上一次验收通过的那张"长什么样。于是回归验收变成「每次拿新图跟手边另一张图比」，
基线漂移/比错对象没人发现。本模块把基线**落盘版本化**：

    <项目>/ui_baseline/
        baseline.json          # 索引：每个 key 的尺寸/sha256/容差档案/来源/时间
        <key>.png              # 基线图（真源）
        _diff/<key>.diff.png   # 最近一次 compare 的标注图

判据口径与 `ui_diff` 完全同源（±2 容差 + ±1px 抖动补偿 + 模糊 + 噪声块归并），
容差档案**随基线一起存**（不同页/不同渲染器的噪声水平不一样，别用一套阈值套所有图）。

对外 API（供 kb_tools 的 ui_visual action=baseline 与 test_tools 的测试跑批共用）
------------------------------------------------------------------------------------
    save(project_root, image, key='', name='', note='', profile=None, allow_regions=0,
         replace=True)                      # 建/更新基线
    compare(project_root, image, key='', out_png='', allow_regions=None, profile=None)
    listing(project_root)
    key_of(image_path, key='')

约定
----
- key 缺省取图文件名（去扩展名）；**同一页面同一状态必须用同一个 key**，
  否则等于绕过基线（比不到就报 no-baseline，不静默放行）。
- 尺寸不一致（resolution 改了）→ 明确报 `size-mismatch`，不硬比。
- 比不到基线 → `no-baseline`（调用方决定当告警还是失败，绝不静默当通过）。
"""
import datetime
import hashlib
import json
import os
import shutil
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
UI_TOOLS = os.path.join(BASE, 'ui_tools')
if UI_TOOLS not in sys.path:
    sys.path.insert(0, UI_TOOLS)
try:
    import ui_diff as _udf
except Exception as _e:                      # 缺 numpy/Pillow 时降级（compare/save 会明确报错）
    _udf = None
    _UD_ERR = repr(_e)
else:
    _UD_ERR = ''

STORE_NAME = 'ui_baseline'
INDEX_NAME = 'baseline.json'
DIFF_DIR = '_diff'
INDEX_VERSION = 1

# 默认容差档案：与 ui_visual(action='diff') 的默认参数一致（沛哥 2026-09-10 定：±2 起步）
DEFAULT_PROFILE = {'tolerance': 2, 'shift': 1, 'minArea': 4, 'blur': 0.7, 'noiseBbox': 10}
_PROFILE_KEYS = tuple(DEFAULT_PROFILE)


def store_dir(project_root):
    return os.path.join(os.path.abspath(project_root), STORE_NAME)


def index_path(project_root):
    return os.path.join(store_dir(project_root), INDEX_NAME)


def key_of(image_path, key=''):
    """key 缺省 = 图文件名（去扩展名）。"""
    k = str(key or '').strip()
    if k:
        return _safe_key(k)
    return _safe_key(os.path.splitext(os.path.basename(image_path or ''))[0])


def _safe_key(s):
    out = ''.join(c if (c.isalnum() or c in '._-') else '_' for c in str(s)).strip('._')
    return out or 'baseline'


def normalize_profile(profile=None):
    """把外部传入的容差覆盖合并到默认档案上（只认已知键，未知键丢弃）。"""
    p = dict(DEFAULT_PROFILE)
    if isinstance(profile, dict):
        for k in _PROFILE_KEYS:
            if profile.get(k) is not None:
                p[k] = profile[k]
    p['tolerance'] = int(p['tolerance'])
    p['shift'] = int(p['shift'])
    p['minArea'] = int(p['minArea'])
    p['noiseBbox'] = int(p['noiseBbox'])
    p['blur'] = float(p['blur'])
    return p


def load_index(project_root):
    p = index_path(project_root)
    if not os.path.isfile(p):
        return {'version': INDEX_VERSION, 'profile': dict(DEFAULT_PROFILE), 'entries': {}}
    try:
        with open(p, encoding='utf-8') as f:
            d = json.load(f)
    except Exception as e:
        return {'version': INDEX_VERSION, 'profile': dict(DEFAULT_PROFILE), 'entries': {},
                'indexError': '索引解析失败: %s' % e}
    if not isinstance(d, dict):
        return {'version': INDEX_VERSION, 'profile': dict(DEFAULT_PROFILE), 'entries': {},
                'indexError': '索引不是对象（被手改坏了？）'}
    d.setdefault('version', INDEX_VERSION)
    d.setdefault('profile', dict(DEFAULT_PROFILE))
    if not isinstance(d.get('entries'), dict):
        d['entries'] = {}
    return d


def save_index(project_root, idx):
    d = store_dir(project_root)
    os.makedirs(d, exist_ok=True)
    with open(index_path(project_root), 'w', encoding='utf-8') as f:
        json.dump(idx, f, ensure_ascii=False, indent=1)
    return index_path(project_root)


def _sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()


def _size_of(path):
    try:
        from PIL import Image
        with Image.open(path) as im:
            return [int(im.size[0]), int(im.size[1])]
    except Exception:
        return []


def _now():
    return datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def save(project_root, image, key='', name='', note='', profile=None,
         allow_regions=0, replace=True, source=''):
    """建/更新基线（把 image 复制进基线库并登记）。

    replace=False 且 key 已存在 → 报 `exists`（不覆盖，防误把"当前有问题的图"刷成基线）。
    """
    res = {'success': False, 'op': 'ui_baseline.save'}
    if not project_root:
        res.update(error='缺 project_root', hint='基线库落在 <项目>/ui_baseline/')
        return res
    if not image or not os.path.isfile(image):
        res.update(error='图片不存在: %s' % (image or '(空)'))
        return res
    if _udf is None:
        res.update(error='像素对比依赖不可用（缺 numpy/Pillow）', detail=_UD_ERR)
        return res
    k = key_of(image, key)
    idx = load_index(project_root)
    if k in idx['entries'] and not replace:
        e = idx['entries'][k]
        res.update(key=k, error='基线已存在（replace=False）', exists=True,
                   baseline=e.get('file'), updatedAt=e.get('updatedAt'),
                   hint='要覆盖请传 replace=True（或走 action=baseline mode=update）')
        return res
    d = store_dir(project_root)
    os.makedirs(d, exist_ok=True)
    dst = os.path.join(d, k + os.path.splitext(image)[1].lower() if
                       os.path.splitext(image)[1] else k + '.png')
    prof = normalize_profile(profile)
    try:
        shutil.copyfile(image, dst)
    except Exception as e:
        res.update(key=k, error='写入基线失败: %s' % e)
        return res
    size = _size_of(dst)
    old = idx['entries'].get(k)
    idx['entries'][k] = {
        'key': k, 'name': name or k, 'file': os.path.basename(dst),
        'sha256': _sha256(dst), 'width': size[0] if size else 0,
        'height': size[1] if size else 0,
        'profile': prof, 'allowRegions': int(allow_regions or 0),
        'updatedAt': _now(), 'source': source or os.path.basename(image),
        'note': note, 'revision': (int(old.get('revision', 0)) + 1) if old else 1,
    }
    save_index(project_root, idx)
    res.update(success=True, key=k, baseline=os.path.basename(dst), store=d,
               size='%dx%d' % (size[0], size[1]) if size else '',
               profile=prof, allowRegions=int(allow_regions or 0),
               revision=idx['entries'][k]['revision'], updated=True if old else False,
               index=index_path(project_root))
    return res


def update(project_root, image, key='', name='', note='', profile=None, allow_regions=0):
    """显式把当前图刷成新基线（= save(replace=True)，语义更醒目，供 CLI/测试跑批调用）。"""
    return save(project_root, image, key=key, name=name, note=note, profile=profile,
                allow_regions=allow_regions, replace=True, source='update')


def compare(project_root, image, key='', out_png='', allow_regions=None, profile=None):
    """当前图 vs 基线图。

    返回 status: pass | fail | no-baseline | size-mismatch | error。
    allow_regions 缺省用基线登记值；显式传入则覆盖（不改基线）。
    """
    res = {'success': False, 'op': 'ui_baseline.compare', 'status': 'error'}
    if not project_root:
        res.update(error='缺 project_root')
        return res
    if not image or not os.path.isfile(image):
        res.update(error='图片不存在: %s' % (image or '(空)'))
        return res
    if _udf is None:
        res.update(error='像素对比依赖不可用（缺 numpy/Pillow）', detail=_UD_ERR)
        return res
    k = key_of(image, key)
    res['key'] = k
    idx = load_index(project_root)
    if idx.get('indexError'):
        res.update(status='error', error=idx['indexError'])
        return res
    e = idx['entries'].get(k)
    if not e:
        res.update(status='no-baseline', baseline='',
                   hint=('基线库里没有 key=%s。先建基线：action=baseline mode=save；'
                         '可用 key 见 mode=list' % k),
                   knownKeys=sorted(idx['entries'])[:20])
        return res
    ref = os.path.join(store_dir(project_root), e['file'])
    if not os.path.isfile(ref):
        res.update(status='error', baseline=e['file'],
                   error='索引里有 key=%s，但基线图文件丢了: %s' % (k, ref),
                   hint='删掉该条目重存，或从版本库恢复基线图')
        return res
    prof = normalize_profile(profile or e.get('profile'))
    allow = int(e.get('allowRegions', 0) if allow_regions is None else allow_regions)
    if not out_png:
        out_png = os.path.join(store_dir(project_root), DIFF_DIR, k + '.diff.png')
    try:
        os.makedirs(os.path.dirname(out_png), exist_ok=True)
    except Exception:
        out_png = ''
    try:
        r = _udf.diff_images(ref, image, tol=prof['tolerance'], shift=prof['shift'],
                             min_area=prof['minArea'], blur=prof['blur'],
                             noise_bbox=prof['noiseBbox'], out_png=out_png)
    except Exception as ex:
        res.update(status='error', error='对比失败: %s' % ex)
        return res
    n = int(r.get('regionCount', 0))
    status = 'pass' if n <= allow else 'fail'
    if r.get('sizeMismatch'):
        status = 'size-mismatch'
    res.update(success=(status == 'pass'), status=status, baseline=e['file'],
               baselineUpdatedAt=e.get('updatedAt'), baselineSize='%sx%s' % (e.get('width'),
                                                                             e.get('height')),
               currentSize=r.get('sizeB'), allowRegions=allow,
               regionCount=n, diffPixelsInRegions=r.get('diffPixelsInRegions'),
               noiseCount=r.get('noiseCount'), profile=prof,
               regions=(r.get('regions') or [])[:10], diffPng=out_png if os.path.isfile(out_png or '') else '')
    if status == 'size-mismatch':
        res['error'] = ('基线与当前图尺寸不一致（%sx%s vs %s）：分辨率改过就别拿旧基线硬比，'
                        '确认新尺寸后重新存基线'
                        % (e.get('width'), e.get('height'), r.get('sizeB')))
    elif status == 'fail':
        res['error'] = '与基线有 %d 处差异（容差允许 %d）：%s' % (
            n, allow, '；'.join('x=%s y=%s %sx%s 面积%s 最大色差%s' % (
                g['x'], g['y'], g['w'], g['h'], g['area'], g['maxDelta'])
                for g in (r.get('regions') or [])[:3]))
    return res


def listing(project_root):
    """列出基线库全部条目（不读图内容，0 token）。"""
    idx = load_index(project_root)
    ents = []
    for k in sorted(idx['entries']):
        e = idx['entries'][k]
        f = os.path.join(store_dir(project_root), e.get('file', ''))
        ents.append({'key': k, 'name': e.get('name', k), 'file': e.get('file'),
                     'size': '%sx%s' % (e.get('width'), e.get('height')),
                     'profile': e.get('profile'), 'allowRegions': e.get('allowRegions', 0),
                     'updatedAt': e.get('updatedAt'), 'revision': e.get('revision', 1),
                     'note': e.get('note', ''),
                     'missing': (not os.path.isfile(f))})
    return {'success': True, 'op': 'ui_baseline.list', 'store': store_dir(project_root),
            'count': len(ents), 'entries': ents,
            'missingCount': sum(1 for x in ents if x['missing']),
            'indexError': idx.get('indexError', '')}


# ---------------- CLI（人/脚本用；MCP 侧走 kb_tools） ----------------
def _main(argv):
    import argparse
    ap = argparse.ArgumentParser(description='像素基线库（save/compare/update/list）')
    ap.add_argument('mode', choices=['save', 'compare', 'update', 'list'])
    ap.add_argument('--project', required=True)
    ap.add_argument('--image', default='')
    ap.add_argument('--key', default='')
    ap.add_argument('--name', default='')
    ap.add_argument('--note', default='')
    ap.add_argument('--out-png', default='')
    ap.add_argument('--allow-regions', type=int, default=None)
    ap.add_argument('--tolerance', type=int, default=None)
    ap.add_argument('--shift', type=int, default=None)
    a = ap.parse_args(argv[1:])
    prof = {}
    for k in ('tolerance', 'shift'):
        v = getattr(a, k)
        if v is not None:
            prof[k] = v
    if a.mode == 'list':
        r = listing(a.project)
    elif a.mode == 'compare':
        kw = {'allow_regions': a.allow_regions}
        if a.out_png:
            kw['out_png'] = a.out_png
        if prof:
            kw['profile'] = prof
        r = compare(a.project, a.image, key=a.key, **kw)
    elif a.mode == 'update':
        r = update(a.project, a.image, key=a.key, name=a.name, note=a.note,
                   profile=prof or None, allow_regions=int(a.allow_regions or 0))
    else:
        r = save(a.project, a.image, key=a.key, name=a.name, note=a.note,
                 profile=prof or None, allow_regions=int(a.allow_regions or 0))
    print(json.dumps(r, ensure_ascii=False, indent=1))
    if a.mode in ('save', 'update'):
        return 0 if r.get('success') else 1
    if a.mode == 'compare':
        return 0 if r.get('status') == 'pass' else 1
    return 0


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.exit(_main(sys.argv))
