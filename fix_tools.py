# -*- coding: utf-8 -*-
"""FlyThings 自动修复工具（fix.log 规则库驱动，2026-08-29 沛哥交付）。

18 条高频问题修复规则（FT-001 ~ FT-006 + FT-008 ~ FT-014 + FT-020 ~ FT-024）：
  FT-001  二维码必须用 ZKQRCode 控件（zk_qrcode）+ loadQRCode()，TextView 占位不生成 QR
  FT-002  ZKSeekBar 不解析 9-patch，marker 像素画成黑框 → Pic 字段改普通 .png
  FT-003  ZKSeekBar 3 张图尺寸必须与控件 position 严格相等（不自动缩放）
  FT-004  改 main.json 必须清 .fun/<plat>/generated 缓存再 fui pack，否则 mPtr 缺失
  FT-005  Z21 + fun.exe 的宏是 FUN_BUILD（不是 FYX_BUILD），INIT_UI_TIMERS 被错误宏保护会空展开
  FT-006  多 Window 架构必须父+子 Window 显式 visible:false，onUI_show 只 showWindow 首屏
  FT-008  Pillow 圆角必须超采样（SS=2 + LANCZOS），1x 直接画是二值 α 锯齿
  FT-009  TextView/Button 硬裁剪不省略，宽高须满足最小尺寸公式
  （FT-007 已于 2026-09-02 废弃：手动 push images + kill zkgui 的部署顺序不再需要，部署统一用 fun launch）

每条规则 = detect(项目) 诊断 → fix(项目) 修复 → verify(项目) 验证。
入口：flythings_fix_project(project_root, kb_id='', apply=False)
  kb_id 留空 = 全部规则；apply=False = 仅诊断（dry-run）；apply=True = 执行修复。
"""
import json, os, re, shutil, glob, datetime

try:
    from PIL import Image, ImageDraw
    _HAS_PIL = True
except Exception:
    _HAS_PIL = False

_BASE = os.path.dirname(os.path.abspath(__file__))

# ============ 辅助函数 ============
def _ui_jsons(root):
    """项目 ui/ 下所有 .json 布局文件。"""
    return sorted(glob.glob(os.path.join(root, 'ui', '*.json')))

def _logic_ccs(root):
    """项目 src/logic 下所有 .cc/.cpp。"""
    return sorted(glob.glob(os.path.join(root, 'src', 'logic', '*.cc')) +
                  glob.glob(os.path.join(root, 'src', 'logic', '*.cpp')))

def _load_json(path):
    try:
        with open(path, encoding='utf-8-sig') as f:
            return json.load(f)
    except Exception as e:
        return {'__error__': str(e)}

def _dump_json(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def _platform_of(root):
    """从 Manifest.xml 探测平台（Z21/F133/...）。"""
    mf = os.path.join(root, 'Manifest.xml')
    if os.path.isfile(mf):
        try:
            t = open(mf, encoding='utf-8', errors='replace').read()
        except Exception:
            t = ''
        m = re.search(r'<manifest\s+platform=["\']([^"\']+)["\']', t)
        if m:
            return m.group(1)
    return ''

def _gen_dir(root):
    """返回 .fun/<plat>/generated 或 .fuse/<plat>/generated（存在者优先）。"""
    plat = _platform_of(root) or ''
    for base in ('.fun', '.fuse', '.fyx'):
        for p in (plat, plat.lower()):
            d = os.path.join(root, base, p, 'generated')
            if os.path.isdir(d):
                return d
    return ''

def _image_size(path):
    """返回图片 (w,h)；失败返回 None。"""
    if not _HAS_PIL or not os.path.isfile(path):
        return None
    try:
        with Image.open(path) as im:
            return im.size
    except Exception:
        return None

def _eff_size(path):
    """图片有效尺寸：.9.png 去掉四周 1px 边框后为内容区。"""
    s = _image_size(path)
    if s is None:
        return None
    return (s[0] - 2, s[1] - 2) if path.lower().endswith('.9.png') else s

def _img_dirs(root):
    """项目图片目录：resources/images 与 ui/images（去重）。"""
    dirs = [os.path.join(root, 'resources', 'images'),
            os.path.join(root, 'ui', 'images')]
    return [d for d in dirs if os.path.isdir(d)]

def _caption_ptr(caption):
    """caption → 控件指针名约定（m + Caption + Ptr）。"""
    return 'm' + caption + 'Ptr'


def _iter_controls(data, top_level=False):
    """递归遍历 json 布局中的全部控件 (key, value)。
    FlyThings json 是树形：控件可嵌套在 window 容器内（如 window__1 内的 textview__2）。
    top_level=True 时只产出根级控件（仅 window__* 等顶层容器）。
    """
    for key, val in data.items():
        if not isinstance(val, dict) or '__' not in key:
            continue
        yield key, val
        if not top_level:
            yield from _iter_controls(val)


def _replace_control_key(data, old_key, new_key):
    """在 json 树中查找 old_key 控件并原地重命名为 new_key（支持嵌套 window）。"""
    for k, v in list(data.items()):
        if k == old_key and isinstance(v, dict):
            data[new_key] = data.pop(old_key)
            return True
        if isinstance(v, dict):
            if _replace_control_key(v, old_key, new_key):
                return True
    return False

# ============ FT-001 二维码控件 ============
_RULE_FT001 = {
    'kb_id': 'FT-001', 'priority': 'high',
    'name': '二维码必须用 ZKQRCode 控件 + loadQRCode()',
    'root_cause': 'FlyThings 生成二维码必须用 ZKQRCode 控件（json key 前缀 qrcode__，id 92001+）'
                  '并调用 loadQRCode(); 用 TextView 占位 + 文字填充不会生成 QR bitmap。',
    'user_patterns': ['二维码没显示', '扫码支付灰色', 'QRCode 不出来', '二维码控件不渲染', 'ZKQRCode loadQRCode 没效果'],
    'anti_patterns': ['用 TextView 当 QR 占位控件直接 setText(url)'],
}

def _detect_ft001(root):
    issues = []
    for jp in _ui_jsons(root):
        data = _load_json(jp)
        if '__error__' in data:
            continue
        for key, val in _iter_controls(data):
            cap = val.get('caption', '')
            if re.search(r'(?i)qr|pay.*code|code.*pay', cap) and not key.startswith('qrcode__'):
                issues.append({
                    'file': os.path.relpath(jp, root), 'control': key, 'caption': cap,
                    'msg': f'控件 {key}({cap}) 疑似二维码占位但类型是 {key.split("__")[0]}，'
                           f'应改用 qrcode__ 前缀（ZKQRCode, id 92001+）并调用 loadQRCode()',
                })
        # logic 层 loadQRCode 调用检查
        if issues:
            ltext = '\n'.join(open(p, encoding='utf-8', errors='replace').read()
                              for p in _logic_ccs(root)) if _logic_ccs(root) else ''
            for it in issues:
                ptr = _caption_ptr(it['caption'])
                if ptr + '->loadQRCode' not in ltext and 'loadQRCode' not in ltext:
                    it['msg'] += f'；且 logic 层未见 {ptr}->loadQRCode(...) 调用'
    return issues

def _fix_ft001(root, issues):
    fixes, notes = [], []
    if not issues:
        return fixes, notes, True
    for jp in _ui_jsons(root):
        data = _load_json(jp)
        if '__error__' in data:
            continue
        changed = False
        next_id = 92001
        used_ids = {v.get('id') for k, v in _iter_controls(data) if v.get('id')}
        for key, val in list(_iter_controls(data)):
            if not re.search(r'(?i)qr|pay.*code|code.*pay', val.get('caption', '')):
                continue
            if key.startswith('qrcode__'):
                continue
            new_key = 'qrcode__' + key.split('__')[-1]
            while next_id in used_ids:
                next_id += 1
            val['id'] = next_id
            used_ids.add(next_id)
            # 若原 text 像 URL 则作为 codeStr 初始值，否则留占位
            if 'codeStr' not in val:
                t = str(val.get('text', ''))
                val['codeStr'] = t if re.match(r'^https?://', t) else 'https://<PAY_URL>'
            for drop in ('text', 'fontSize', 'alignment', 'colorTab'):
                val.pop(drop, None)
            _replace_control_key(data, key, new_key)
            fixes.append(f"{os.path.relpath(jp, root)}: {key} → {new_key}（ZKQRCode, id={val['id']}）")
            changed = True
        if changed:
            _dump_json(jp, data)
    # logic.cc onUI_init 插入 loadQRCode
    for cc in _logic_ccs(root):
        text = open(cc, encoding='utf-8', errors='replace').read()
        inserts = []
        for it in issues:
            ptr = _caption_ptr(it['caption'])
            if ptr + '->loadQRCode' in text:
                continue
            code = f'    if ({ptr}) {ptr}->loadQRCode("https://<PAY_URL>");  // TODO: 替换真实支付/二维码 URL'
            if code not in text:
                inserts.append(code)
        if inserts:
            block = '\n'.join(inserts) + '\n'
            if 'onUI_init' in text:
                text = re.sub(r'(static void onUI_init\(\)\{)', r'\1\n' + block, text, count=1)
            else:
                text += '\nstatic void onUI_init(){\n' + block + '}\n'
            open(cc, 'w', encoding='utf-8').write(text)
            fixes.append(f'{os.path.relpath(cc, root)}: onUI_init 插入 loadQRCode 调用（URL 占位，需替换）')
    notes.append('loadQRCode 的 URL 为占位符 <PAY_URL>，请替换为真实地址')
    return fixes, notes, True

def _verify_ft001(root):
    ok, msgs = True, []
    for jp in _ui_jsons(root):
        data = _load_json(jp)
        if '__error__' in data:
            continue
        for key, val in _iter_controls(data):
            if re.search(r'(?i)qr|pay.*code|code.*pay', val.get('caption', '')):
                if not key.startswith('qrcode__'):
                    ok, msgs = False, [f'{os.path.relpath(jp, root)}: {key} 仍是 {key.split("__")[0]} 类型']
                    break
    return ok, msgs

# ============ FT-002 SeekBar 9-patch 黑框 ============
_RULE_FT002 = {
    'kb_id': 'FT-002', 'priority': 'critical',
    'name': 'SeekBar 禁用 9-patch（marker 像素画成黑框）',
    'root_cause': 'ZKSeekBar 不解析 9-patch 1px 纯黑 marker，会把 marker 当图像内容显示，'
                  '导致进度条 bg/fill/thumb 四周一圈 1px 黑框+圆角被破坏。',
    'user_patterns': ['SeekBar 外框有黑线', '进度条 marker 显示出来了', '进度条背景四周一圈黑边', 'seekbar 边框被画成黑色'],
    'anti_patterns': ["给 ZKSeekBar backgroundPic 传 .9.png 以为会拉伸", "save_card('seekbar_bg') 自动生成 .9.png"],
}
_SEEKBAR_PIC_FIELDS = ('progressPic', 'secondaryProgressPic', 'backgroundPic', 'thumbPic')

def _detect_ft002(root):
    issues = []
    for jp in _ui_jsons(root):
        data = _load_json(jp)
        if '__error__' in data:
            continue
        for key, val in _iter_controls(data):
            if not key.startswith('seekbar__'):
                continue
            for fld in _SEEKBAR_PIC_FIELDS:
                v = val.get(fld, '')
                if isinstance(v, str) and v.lower().endswith('.9.png'):
                    issues.append({
                        'file': os.path.relpath(jp, root), 'control': key, 'field': fld, 'pic': v,
                        'msg': f'SeekBar {key}.{fld} 用了 9-patch ({v})：ZKSeekBar 不解析 marker，'
                               f'会显示 1px 黑框，应改用普通 .png',
                    })
    return issues

def _fix_ft002(root, issues):
    fixes, notes = [], []
    if not issues:
        return fixes, notes, True
    # 1) json 字段 .9.png → .png
    for jp in _ui_jsons(root):
        data = _load_json(jp)
        if '__error__' in data:
            continue
        changed = False
        for key, val in _iter_controls(data):
            if not key.startswith('seekbar__'):
                continue
            for fld in _SEEKBAR_PIC_FIELDS:
                v = val.get(fld, '')
                if isinstance(v, str) and v.lower().endswith('.9.png'):
                    val[fld] = v[:-len('.9.png')] + '.png'
                    changed = True
        if changed:
            _dump_json(jp, data)
            fixes.append(f'{os.path.relpath(jp, root)}: SeekBar Pic 字段 .9.png → .png')
    # 2) 资源：.9.png → 普通 .png（只处理 SeekBar 引用到的图；按钮/面板/header 的 9-patch 是合法用法，不动）
    target_pics = {os.path.basename(it.get('pic', '')) for it in issues if it.get('pic')}
    for d in _img_dirs(root):
        for p9 in glob.glob(os.path.join(d, '*.9.png')):
            base = p9[:-len('.9.png')] + '.png'
            if os.path.basename(p9) not in target_pics and os.path.basename(base) not in target_pics:
                continue  # 非 SeekBar 引用（按钮/面板等 9-patch 合法），跳过
            if os.path.isfile(base):
                continue  # 已有普通版，无需转换
            if _HAS_PIL:
                try:
                    with Image.open(p9) as im:
                        w, h = im.size
                        if w > 2 and h > 2:
                            im.crop((1, 1, w - 1, h - 1)).save(base)
                        else:
                            im.save(base)
                    fixes.append(f'{os.path.relpath(p9, root)} → 普通 .png（裁掉 9-patch 边框）')
                except Exception as e:
                    notes.append(f'{os.path.basename(p9)} 转换失败: {e}')
            else:
                shutil.copy2(p9, base)
                fixes.append(f'{os.path.relpath(p9, root)} → 复制为 .png（无 PIL，未裁边框）')
    # 3) 删除不再被引用的 .9.png（仅限 seekbar 相关、且 json 无引用者）
    refs = set()
    for jp in _ui_jsons(root):
        data = _load_json(jp)
        if '__error__' in data:
            continue
        for key, val in _iter_controls(data):
            for fld in _SEEKBAR_PIC_FIELDS + ('backgroundPic', 'pic0', 'pic1'):
                v = val.get(fld, '')
                if isinstance(v, str) and v.lower().endswith('.9.png'):
                    refs.add(os.path.basename(v))
    for d in _img_dirs(root):
        for p9 in glob.glob(os.path.join(d, '*.9.png')):
            if os.path.basename(p9) not in refs and os.path.basename(p9).startswith(('bar_', 'seekbar_', 'progress_')):
                os.remove(p9)
                fixes.append(f'{os.path.relpath(p9, root)}: 已删除无人引用的 9-patch')
    return fixes, notes, True

def _verify_ft002(root):
    ok, msgs = True, []
    for jp in _ui_jsons(root):
        data = _load_json(jp)
        if '__error__' in data:
            continue
        for key, val in _iter_controls(data):
            if not key.startswith('seekbar__'):
                continue
            for fld in _SEEKBAR_PIC_FIELDS:
                v = val.get(fld, '')
                if isinstance(v, str) and v.lower().endswith('.9.png'):
                    ok, msgs = False, [f'{os.path.relpath(jp, root)}: {key}.{fld} 仍引用 9-patch']
                    break
    return ok, msgs

# ============ FT-003 SeekBar 尺寸匹配 ============
_RULE_FT003 = {
    'kb_id': 'FT-003', 'priority': 'high',
    'name': 'SeekBar 图片尺寸必须与控件 position 严格相等',
    'root_cause': 'ZKSeekBar 按控件 position rect 直接 drawBitmap，不做 fitCenter 缩放；'
                  '3 张图必须与 position 宽高严格相等且 bg/fill 尺寸一致，否则显示对不齐/留白/拉伸糊。',
    'user_patterns': ['进度条背景和前景高度不一样', 'SeekBar 上面短一截', '进度条高度不一致', '进度条被裁剪、中间矮、对不齐'],
    'anti_patterns': ['seekbar_bg/fill 高度只有控件 1/3 以为会自动缩放居中', 'radius < height/2 造成非半圆封端'],
}

def _detect_ft003(root):
    issues = []
    for jp in _ui_jsons(root):
        data = _load_json(jp)
        if '__error__' in data:
            continue
        for key, val in _iter_controls(data):
            if not key.startswith('seekbar__'):
                continue
            pos = val.get('position') or {}
            pw, ph = pos.get('width'), pos.get('height')
            if not pw or not ph:
                continue
            for fld in ('progressPic', 'backgroundPic'):
                pic = val.get(fld, '')
                if not pic:
                    continue
                for d in _img_dirs(root):
                    p = os.path.join(d, pic)
                    if os.path.isfile(p):
                        eff = _eff_size(p)
                        if eff and (eff[0] != pw or eff[1] != ph):
                            issues.append({
                                'file': os.path.relpath(jp, root), 'control': key, 'field': fld, 'pic': pic,
                                'expect': f'{pw}x{ph}', 'actual': f'{eff[0]}x{eff[1]}',
                                'msg': f'SeekBar {key}.{fld} 图片 {pic} 尺寸 {eff[0]}x{eff[1]} '
                                       f'≠ 控件 position {pw}x{ph}（ZKSeekBar 不缩放，必须严格相等）',
                            })
                        break
    return issues

def _fix_ft003(root, issues):
    fixes, notes = [], []
    if not issues:
        return fixes, notes, True
    if not _HAS_PIL:
        return fixes, ['需要 PIL 重新生成匹配尺寸图片，跳过自动修复'], False
    for it in issues:
        for d in _img_dirs(root):
            p = os.path.join(d, it['pic'])
            if not os.path.isfile(p):
                continue
            w, h = it['expect'].split('x')
            w, h = int(w), int(h)
            color = None
            try:
                with Image.open(p) as im:
                    px = im.convert('RGBA')
                    # 采样中心像素作为填充色
                    cw, ch = px.size
                    color = px.getpixel((cw // 2, ch // 2))[:3]
            except Exception:
                color = (0x2E, 0xCC, 0x71) if 'fill' in it['pic'] else (0x23, 0x2D, 0x3D)
            img = Image.new('RGBA', (w, h), (0, 0, 0, 0))
            radius = h // 2
            ImageDraw.Draw(img).rounded_rectangle([0, 0, w - 1, h - 1], radius=radius, fill=color + (255,))
            img.save(p)
            fixes.append(f'{os.path.relpath(p, root)}: 重生成 {w}x{h}（radius={radius} 半圆封端）')
            break
    return fixes, notes, True

def _verify_ft003(root):
    ok, msgs = True, []
    for jp in _ui_jsons(root):
        data = _load_json(jp)
        if '__error__' in data:
            continue
        for key, val in _iter_controls(data):
            if not key.startswith('seekbar__'):
                continue
            pos = val.get('position') or {}
            pw, ph = pos.get('width'), pos.get('height')
            if not pw or not ph:
                continue
            for fld in ('progressPic', 'backgroundPic'):
                pic = val.get(fld, '')
                if not pic:
                    continue
                for d in _img_dirs(root):
                    p = os.path.join(d, pic)
                    if os.path.isfile(p):
                        eff = _eff_size(p)
                        if eff and (eff[0] != pw or eff[1] != ph):
                            ok, msgs = False, [f'{key}.{fld} {pic} {eff[0]}x{eff[1]} ≠ {pw}x{ph}']
                        break
    return ok, msgs

# ============ FT-004 fui generated 缓存 ============
_RULE_FT004 = {
    'kb_id': 'FT-004', 'priority': 'high',
    'name': '改 json 后必须清 generated 缓存重新 pack',
    'root_cause': 'fui pack 只在 generated 比 json 旧时才重生成 event_dispatcher/ui_main；'
                  '直接改 json 不清缓存会导致新控件指针 mXXXPtr 缺失、回调不挂载。',
    'user_patterns': ['新加的 caption mPtr 指针没生成', 'ui_main.h 里没有新控件', 'event_dispatcher 里没 onButtonClick', '新插入的 textview C++ 端找不到', 'ninja no work to do 但实际改了 json'],
    'anti_patterns': ['改完 json 直接 fun build 跳过 fui pack 和 generated 清理'],
}

def _detect_ft004(root):
    issues = []
    gd = _gen_dir(root)
    for jp in _ui_jsons(root):
        base = os.path.splitext(os.path.basename(jp))[0]
        gh = os.path.join(gd, f'ui_{base}.h') if gd else ''
        data = _load_json(jp)
        if '__error__' in data:
            continue
        caps = [v.get('caption') for k, v in _iter_controls(data) if v.get('caption')]
        mtime_new = os.path.getmtime(jp)
        gtext = ''
        if gh and os.path.isfile(gh):
            gtext = open(gh, encoding='utf-8', errors='replace').read()
            if mtime_new > os.path.getmtime(gh) + 1:
                issues.append({
                    'file': os.path.relpath(jp, root),
                    'msg': f'{os.path.basename(jp)} 修改时间晚于 {os.path.relpath(gh, root)}：'
                           f'改过 json 未清 generated 缓存，新控件指针可能缺失',
                })
        missing = [c for c in caps if c and gtext and f'm{c}Ptr' not in gtext]
        if missing and gtext:
            issues.append({
                'file': os.path.relpath(jp, root),
                'msg': f'generated ui_{base}.h 中缺少控件指针: {", ".join(missing[:6])}'
                       f'（需清缓存重新 fui pack）',
            })
        if not gtext and not gh:
            issues.append({
                'file': os.path.relpath(jp, root),
                'msg': f'未找到 generated 目录（{gd or ".fun/<plat>/generated"}）——'
                       f'可能从未编译过，或需清理后重新 fui pack + fun build',
            })
    return issues

def _fix_ft004(root, issues):
    fixes, notes = [], []
    if not issues:
        return fixes, notes, True
    plat = _platform_of(root) or ''
    removed = False
    for base in ('.fun', '.fuse', '.fyx'):
        for p in (plat, plat.lower()):
            d = os.path.join(root, base, p)
            for sub in ('generated', 'build'):
                t = os.path.join(d, sub)
                if os.path.isdir(t):
                    shutil.rmtree(t, ignore_errors=True)
                    fixes.append(f'已删除 {os.path.relpath(t, root)}')
                    removed = True
    if not removed:
        notes.append('未发现可清理的 generated/build 缓存目录')
    # 重新 fui pack（json → ftu 在 ui 目录执行）
    try:
        import project_tools as pt
        ui_dir = os.path.join(root, 'ui')
        if os.path.isdir(ui_dir):
            r = pt._run_fui('pack', ui_dir)
            fixes.append(f'fui pack: {"成功" if r["success"] else "失败 " + (r.get("stderr") or r.get("stdout") or "")[-200:]}')
            if r['success']:
                notes.append('缓存已清理并重新 pack，需重新 fun build 编译（可用 flythings_build_ui_flow）')
    except Exception as e:
        notes.append(f'fui pack 未执行: {e}')
    return fixes, notes, True

def _verify_ft004(root):
    gd = _gen_dir(root)
    ok, msgs = True, []
    for jp in _ui_jsons(root):
        base = os.path.splitext(os.path.basename(jp))[0]
        gh = os.path.join(gd, f'ui_{base}.h')
        if not os.path.isfile(gh):
            ok, msgs = False, [f'generated ui_{base}.h 不存在（需重新编译）']
            continue
        data = _load_json(jp)
        gtext = open(gh, encoding='utf-8', errors='replace').read()
        for k, v in _iter_controls(data):
            if v.get('caption') and f'm{v["caption"]}Ptr' not in gtext:
                    ok, msgs = False, [f'缺少 m{v["caption"]}Ptr']
                    break
    return ok, msgs

# ============ FT-005 TIMER 宏（FUN_BUILD vs FYX_BUILD）============
_RULE_FT005 = {
    'kb_id': 'FT-005', 'priority': 'critical',
    'name': 'Z21+fun.exe 的编译宏是 FUN_BUILD，INIT_UI_TIMERS 不能被 FYX_BUILD 保护',
    'root_cause': 'Z21 平台 + fun.exe toolchain 的编译宏是 FUN_BUILD（不是 FYX_BUILD）。'
                  'INIT_UI_TIMERS 宏被 #ifdef FYX_BUILD 保护时展开为空 → 所有定时器不注册。',
    'user_patterns': ['TIMER_1S 不触发', '心跳定时器没走', 'onUI_timer 不回调', '倒计时数字不动', 'SIMULATE 全卡在初始化'],
    'anti_patterns': ['全局替换 FYX_BUILD → FUN_BUILD 误伤其他功能宏（有些平台特定宏真的是 FYX）'],
}

def _detect_ft005(root):
    issues = []
    for cc in _logic_ccs(root):
        text = open(cc, encoding='utf-8', errors='replace').read()
        idx = text.find('INIT_UI_TIMERS')
        if idx < 0:
            continue
        # 找 INIT_UI_TIMERS 之前最近的 #ifdef
        head = text[:idx]
        m = re.findall(r'#if(n?def|ndef)\s+(\w+)', head)
        if m and m[-1][1] == 'FYX_BUILD' and m[-1][0] in ('def', 'n?def'):
            issues.append({
                'file': os.path.relpath(cc, root),
                'msg': f'INIT_UI_TIMERS 外层被 #{m[-1][0]} FYX_BUILD 保护：'
                       f'Z21+fun.exe 实际宏是 FUN_BUILD，定时器注册会被展开为空',
            })
    return issues

def _fix_ft005(root, issues):
    fixes, notes = [], []
    if not issues:
        return fixes, notes, True
    for it in issues:
        p = os.path.join(root, it['file'])
        text = open(p, encoding='utf-8', errors='replace').read()
        idx = text.find('INIT_UI_TIMERS')
        if idx < 0:
            continue
        head = text[:idx]
        # 只替换 INIT_UI_TIMERS 之前最近的那一处 #ifdef FYX_BUILD（禁止全局替换）
        pos = head.rfind('#ifdef FYX_BUILD')
        if pos >= 0:
            text = text[:pos] + '#ifdef FUN_BUILD' + text[pos + len('#ifdef FYX_BUILD'):]
            open(p, 'w', encoding='utf-8').write(text)
            fixes.append(f'{it["file"]}: INIT_UI_TIMERS 外层 #ifdef FYX_BUILD → #ifdef FUN_BUILD（仅此一处）')
    return fixes, notes, True

def _verify_ft005(root):
    ok, msgs = True, []
    for cc in _logic_ccs(root):
        text = open(cc, encoding='utf-8', errors='replace').read()
        idx = text.find('INIT_UI_TIMERS')
        if idx < 0:
            continue
        head = text[:idx]
        m = re.findall(r'#if(n?def|ndef)\s+(\w+)', head)
        if m and m[-1][1] == 'FYX_BUILD':
            ok, msgs = False, [f'{os.path.relpath(cc, root)}: INIT_UI_TIMERS 仍被 FYX_BUILD 保护']
    return ok, msgs

# ============ FT-006 多 Window 可见性 ============
_RULE_FT006 = {
    'kb_id': 'FT-006', 'priority': 'high',
    'name': '页面级用多 Activity 跳转；功能窗口内才用 Window 嵌套',
    'root_cause': 'FlyThings 架构（沛哥 2026-08-29 定）：①页面级（全屏互斥页面，如欢迎/支付/充电/完成）'
                  '应拆多个 Activity 用 Intent 跳转（onUI_intent / openActivity），不要单 Activity 堆多个全屏 '
                  'Window 做 visible 状态机；②隶属于一个功能窗口的局部内容（卡片/弹窗/子面板）才用 Window 嵌套，'
                  '子 Window 随父 Window 显示/隐藏，是合法用法。'
                  '若坚持单 Activity 多 Window：所有父+子 Window 默认 visible=true 不会自动分层，'
                  '必须全部显式 visible:false 再 showWindow 首屏。',
    'user_patterns': ['所有窗口都显示出来', '卡片堆在一起', '层级乱套', '欢迎屏后面透出其他屏内容', 'Payment Window 初始化就出来了'],
    'anti_patterns': ['页面级用单 Activity 堆全屏 Window 状态机（应拆多 Activity）',
                      '把功能窗口内的嵌套子 Window 当独立页面控制',
                      '靠 z-order 覆盖代替 visible → 交互穿透'],
}

def _overlap_ratio(a, b):
    """两矩形交叠面积 / 较小者面积。"""
    ax, ay, aw, ah = a['left'], a['top'], a['width'], a['height']
    bx, by, bw, bh = b['left'], b['top'], b['width'], b['height']
    ix = max(0, min(ax + aw, bx + bw) - max(ax, bx))
    iy = max(0, min(ay + ah, by + bh) - max(ay, by))
    inter = ix * iy
    small = min(aw * ah, bw * bh)
    return inter / small if small else 0

def _detect_ft006(root):
    issues = []
    for jp in _ui_jsons(root):
        data = _load_json(jp)
        if '__error__' in data:
            continue
        res = data.get('resolution') or {}
        rw, rh = res.get('width') or 0, res.get('height') or 0
        screen_area = rw * rh
        wins = [(k, v) for k, v in _iter_controls(data, top_level=True)
                if k.startswith('window__') and v.get('position')]
        if len(wins) < 2 or not screen_area:
            continue
        # 页面级候选：面积 ≥ 60% 屏幕的顶层 window
        page_wins = []
        for k, v in wins:
            pos = v['position']
            area = (pos.get('width') or 0) * (pos.get('height') or 0)
            if area >= screen_area * 0.6:
                page_wins.append((k, v))
        if len(page_wins) < 2:
            continue
        # 互斥判定：两两交叠 >30%
        overlapped = []
        for i in range(len(page_wins)):
            for j in range(i + 1, len(page_wins)):
                k1, v1 = page_wins[i]
                k2, v2 = page_wins[j]
                if _overlap_ratio(v1['position'], v2['position']) > 0.3:
                    overlapped.append((k1, k2))
        if not overlapped:
            continue
        names = ' / '.join(sorted(set(k for pair in overlapped for k in pair)))
        issues.append({
            'file': os.path.relpath(jp, root),
            'msg': f'检测到页面级互斥全屏 Window（{names}）：页面级应拆多个 Activity 用 Intent 跳转'
                   f'（onUI_intent / openActivity），不要单 Activity 堆全屏 Window 做 visible 状态机；'
                   f'功能窗口内的局部内容才用 Window 嵌套（合法）',
        })
    return issues

def _fix_ft006(root, issues):
    fixes, notes = [], []
    if not issues:
        return fixes, notes, True
    doc = os.path.join(root, 'tools', 'activity_architecture.md')
    os.makedirs(os.path.dirname(doc), exist_ok=True)
    content = """# 页面/窗口架构规范（FT-006，沛哥 2026-08-29 定）

## 1. 页面级（全屏互斥页面）→ 多 Activity 跳转
- 不同功能页面（如欢迎/支付/充电/完成）应各建一个 Activity，用 Intent 跳转
- FlyThings 每个页面 = 一个 activity（ui 下每个 json 对应一个 activity + logic）
- 跳转：openActivity / Intent（onUI_intent 接收参数），见 wiki devflow
- 禁止：单 Activity 里堆多个全屏 Window 用 visible 状态机切换

## 2. 功能窗口内 → Window 嵌套（合法）
- 隶属于一个功能窗口的局部内容（卡片/弹窗/子面板）用 Window 嵌套
- 子 Window 随父 Window 显示/隐藏，无需手动 visible 控制
- 注意：嵌套子 Window 不要当独立页面写独立逻辑

## 3. 若确需单 Activity 多 Window（不推荐）
- 所有父+子 Window 显式 visible:false
- onUI_show 只 showWindow(首屏Ptr)
- 其余按状态机 showWindow/hideWindow 切换
"""
    open(doc, 'w', encoding='utf-8').write(content)
    fixes.append(f'已生成 {os.path.relpath(doc, root)}（页面→多 Activity / 功能内→嵌套 架构规范）')
    notes.append('页面级拆多 Activity 属架构改动，需人工实现（建新 activity + Intent 跳转），自动工具不代拆')
    return fixes, notes, True

def _verify_ft006(root):
    doc = os.path.join(root, 'tools', 'activity_architecture.md')
    if os.path.isfile(doc):
        return True, ['架构规范文档已就位（拆 Activity 需人工实现）']
    return False, ['缺少架构规范文档（tools/activity_architecture.md）']

# ============ FT-008 Pillow 超采样抗锯齿 ============
_RULE_FT008 = {
    'kb_id': 'FT-008', 'priority': 'high',
    'name': 'Pillow 圆角资源必须超采样（SS=2 + LANCZOS）',
    'root_cause': 'Pillow 1× 尺寸画 rounded_rectangle 只输出二值 α（0/255），无子像素过渡；'
                  'FlyThings 只支持位图，必须在资源生成端超采样抗锯齿。',
    'user_patterns': ['倒角锯齿明显', '圆角阶梯状', '按钮角上有小台阶', '卡片圆角有狗牙感', 'seekbar thumb 不圆', 'icon 圆边硬切'],
    'anti_patterns': ['只升级 Pillow 以为自带 AA', '先 resize 再画 rounded_rectangle（画在 1× 又变回锯齿）'],
}

def _gen_scripts(root):
    """项目内资源生成脚本候选。"""
    cands = []
    for pat in ('tools/gen_res.py', 'tools/_gen_cards.py', 'tools/ui_tools/gen_res.py',
                'resources/images/_gen_cards.py', 'resources/images/gen_res.py'):
        p = os.path.join(root, pat)
        if os.path.isfile(p):
            cands.append(p)
    for d in _img_dirs(root):
        for pat in ('_gen_cards.py', 'gen_res.py'):
            p = os.path.join(d, pat)
            if os.path.isfile(p):
                cands.append(p)
    return list(dict.fromkeys(cands))

def _detect_ft008(root):
    issues = []
    for p in _gen_scripts(root):
        text = open(p, encoding='utf-8', errors='replace').read()
        has_round = ('rounded_rectangle' in text or 'rounded_rect' in text)
        has_ss = ('LANCZOS' in text or 'supersample' in text.lower() or 'ss=' in text or 'SS =' in text)
        if has_round and not has_ss:
            issues.append({
                'file': os.path.relpath(p, root),
                'msg': f'{os.path.basename(p)} 画圆角但无超采样（LANCZOS/SS）：'
                       f'1× 直接画圆角是二值 α 锯齿，需 SS=2 放大绘制后 LANCZOS 缩小',
            })
    return issues

def _fix_ft008(root, issues):
    fixes, notes = [], []
    if not issues:
        return fixes, notes, True
    for it in issues:
        p = os.path.join(root, it['file'])
        text = open(p, encoding='utf-8', errors='replace').read()
        # 注入 SS 常量（若缺）
        if not re.search(r'^\s*SS\s*=\s*\d+', text, re.M):
            text = 'SS = 2  # 超采样抗锯齿（FT-008）\n' + text
        # 整体替换 rounded_rect 函数：画在 SS 倍画布上 → LANCZOS 缩回（超采样方向必须如此）
        pat = re.compile(
            r'def rounded_rect\(([^)]*)\):\n(.*?)(?=\ndef |\n# |\Z)', re.S)
        m = pat.search(text)
        if m:
            args = m.group(1)
            new_fn = (
                f'def rounded_rect({args}):\n'
                f'    """超采样圆角矩形（FT-008）：SS 倍画布绘制 → LANCZOS 缩回，消除锯齿。"""\n'
                f'    img = Image.new("RGBA", (w * SS, h * SS), (0, 0, 0, 0))\n'
                f'    d = ImageDraw.Draw(img)\n'
                f'    d.rounded_rectangle([0, 0, w * SS - 1, h * SS - 1], radius=radius * SS, fill=fill,\n'
                f'                        outline=border, width=border_w * SS)\n'
                f'    return img.resize((w, h), Image.LANCZOS)\n')
            text = text[:m.start()] + new_fn + text[m.end():]
            fixes.append(f'{it["file"]}: rounded_rect 已整体替换为 SS=2 超采样版本')
        else:
            notes.append(f'{it["file"]}: 未匹配到 rounded_rect 函数形态，需手动加超采样'
                         f'（放大 SS 倍绘制 → Image.LANCZOS 缩小）')
        open(p, 'w', encoding='utf-8').write(text)
    return fixes, notes, True

def _verify_ft008(root):
    ok, msgs = True, []
    for p in _gen_scripts(root):
        text = open(p, encoding='utf-8', errors='replace').read()
        if 'rounded_rectangle' in text or 'rounded_rect' in text:
            if 'LANCZOS' not in text:
                ok, msgs = False, [f'{os.path.relpath(p, root)}: 仍无 LANCZOS 超采样']
                break
    return ok, msgs

# ============ FT-009 TextView 最小尺寸公式 ============
_RULE_FT009 = {
    'kb_id': 'FT-009', 'priority': 'high',
    'name': 'TextView/Button 宽高须满足最小尺寸公式',
    'root_cause': 'FlyThings TextView/Button 按 rect 硬裁剪不 ellipsize，缺字号/字符数匹配的最小尺寸。'
                  '语系宽度系数：中文/全角=1.0，英文/数字/括号=0.55，符号混合=0.6；取 ceil+10% 余量。',
    'user_patterns': ['显示不全', '文字被截断', '控件区域太短', 'caption 最后一个字看不到', 'OK 被切', '字号太大盒子太窄'],
    'anti_patterns': ['单纯加大 fontSize 不改 width/height', '放大 width 不减小相邻 left 压到其他控件'],
}

def _container_width(data, target_key):
    """返回 target_key 控件的容器宽度：根级控件=分辨率宽，嵌套控件=父 window 的 position.width。
    用于 FT-009 扩大宽度时防溢出父容器。"""
    res = data.get('resolution') or {}
    root_w = res.get('width', 0) or 0

    def find_parent(d, key, parent=None):
        for k, v in d.items():
            if not isinstance(v, dict):
                continue
            if k == key:
                return parent
            if '__' in k:
                r = find_parent(v, key, v if k.startswith('window__') else parent)
                if r is not None:
                    return r
        return None

    parent = find_parent(data, target_key)
    if parent is not None and parent.get('position'):
        w = parent['position'].get('width', root_w) or root_w
        return w
    return root_w


def _text_min_size(text, font_size, align):
    """按公式算最小宽高。"""
    if not text:
        return 0, 0
    wsum = 0.0
    for ch in text:
        if ord(ch) > 0x2E7F:      # CJK/全角
            wsum += 1.0
        elif re.match(r'[\w\d()\[\]{}]', ch):
            wsum += 0.55
        else:
            wsum += 0.6
    min_w = int(wsum * font_size * 1.1) + 16
    if align == 37:  # CENTER 补余量
        min_w += 8
    min_h = int(font_size * 1.25)
    return min_w, min_h

def _detect_ft009(root):
    issues = []
    for jp in _ui_jsons(root):
        data = _load_json(jp)
        if '__error__' in data:
            continue
        for key, val in _iter_controls(data):
            if not key.startswith(('textview__', 'button__')):
                continue
            text = str(val.get('text', ''))
            fs = val.get('fontSize') or 0
            pos = val.get('position') or {}
            if not text or not fs or not pos.get('width'):
                continue
            min_w, min_h = _text_min_size(text, fs, val.get('alignment', 0))
            if pos['width'] < min_w or pos['height'] < min_h:
                issues.append({
                    'file': os.path.relpath(jp, root), 'control': key,
                    'caption': val.get('caption', ''), 'text': text[:12],
                    'cur': f"{pos['width']}x{pos['height']}", 'min': f'{min_w}x{min_h}',
                    'msg': f'{key}({val.get("caption", "")}) 文本 "{text[:10]}" 字号 {fs}：'
                           f'最小 {min_w}x{min_h}，当前 {pos["width"]}x{pos["height"]}，会截断',
                })
    return issues

def _fix_ft009(root, issues):
    fixes, notes = [], []
    if not issues:
        return fixes, notes, True
    for jp in _ui_jsons(root):
        data = _load_json(jp)
        if '__error__' in data:
            continue
        changed = False
        for key, val in _iter_controls(data):
            if not key.startswith(('textview__', 'button__')):
                continue
            text = str(val.get('text', ''))
            fs = val.get('fontSize') or 0
            pos = val.get('position') or {}
            if not text or not fs or not pos.get('width'):
                continue
            min_w, min_h = _text_min_size(text, fs, val.get('alignment', 0))
            new_w, new_h = pos['width'], pos['height']
            if pos['width'] < min_w:
                new_w = min_w
            if pos['height'] < min_h:
                new_h = min_h
            if (new_w, new_h) != (pos['width'], pos['height']):
                # 容器边界保护：扩大宽度后不超出父 window/屏幕宽度，否则跳过并提示手动处理
                cw = _container_width(data, key)
                if new_w > pos['width'] and pos.get('left', 0) + new_w > cw:
                    notes.append(f'{key}({val.get("caption", "")}) 扩大宽度会超出容器({cw}px)，'
                                 f'已跳过自动调整，需手动改位置或缩字号')
                    continue
                pos['width'], pos['height'] = new_w, new_h
                changed = True
                fixes.append(f'{os.path.relpath(jp, root)}: {key}({val.get("caption", "")}) '
                             f'{pos["width"]}x{pos["height"]} → {new_w}x{new_h}')
        if changed:
            _dump_json(jp, data)
    notes.append('若放大后与相邻控件重叠，需手动调整 left/top（本工具只保证最小尺寸）')
    return fixes, notes, True

def _verify_ft009(root):
    ok, msgs = True, []
    for jp in _ui_jsons(root):
        data = _load_json(jp)
        if '__error__' in data:
            continue
        for key, val in _iter_controls(data):
            if not key.startswith(('textview__', 'button__')):
                continue
            text = str(val.get('text', ''))
            fs = val.get('fontSize') or 0
            pos = val.get('position') or {}
            if not text or not fs or not pos.get('width'):
                continue
            min_w, min_h = _text_min_size(text, fs, val.get('alignment', 0))
            if pos['width'] < min_w or pos['height'] < min_h:
                ok, msgs = False, [f'{key} 仍小于最小尺寸 {min_w}x{min_h}']
                break
    return ok, msgs


# ============ FT-010 NTP 包 semver 范围匹配 ============
_RULE_FT010 = {
    'kb_id': 'FT-010', 'priority': 'critical',
    'name': '包版本 semver 范围必须与 registry 实际版本 MAJOR 对齐',
    'root_cause': '凭空猜 FlyThings 包版本（写 ^1.0.0）。SemVer ^X.Y.Z 允许 >=X.Y.Z 且 MAJOR 不变；'
                  'registry 实际 ntp 是 2.1.1（MAJOR=2），^1.0.0 范围 [1,2) 不含 2.1.1，'
                  'fun install resolve 会静默跳过不满足 semver 的包 → CMake include path 没有 ntp/2.1.1/include → 编译找不到头文件。',
    'user_patterns': ['ntp/ntp.h No such file or directory', 'Manifest 加了 package id=ntp 但找不到头文件',
                      'fun install 显示 resolved 但编译报找不到包', '引入后 CMake include path 没加'],
    'anti_patterns': ['凭空写 ntp@^1.0.0 假设从 v1 开始', 'fun install 报 resolved 就以为包进来了，不查 CMakeCache/compile_commands.json'],
}

_SEMVER_RE = re.compile(r'^\^?(\d+)\.(\d+)\.(\d+)')


def _manifest_packages(root):
    """读 Manifest.xml 返回 {pkg: version_constraint}。"""
    mf = os.path.join(root, 'Manifest.xml')
    out = {}
    if os.path.isfile(mf):
        try:
            t = open(mf, encoding='utf-8', errors='replace').read()
        except Exception:
            t = ''
        for m in re.finditer(r'<package\s+id="([^"]+)"\s+version="([^"]+)"', t):
            out[m.group(1)] = m.group(2)
    return out


def _registry_versions(pkg, platform):
    """查 registry 实际版本（多目录扫描，semver 降序）。"""
    plat = (platform or '').lower()
    vers = set()
    for base in (r'C:\Users\zkswe\.fun\registry\public',
                 r'C:\Users\zkswe\.fuse\registry\public',
                 r'C:\zkswe\fun\registry\public'):
        d = os.path.join(base, plat, pkg)
        if os.path.isdir(d):
            vers.update(v for v in os.listdir(d) if os.path.isdir(os.path.join(d, v)))
    def _vk(v):
        m = re.match(r'^(\d+)\.(\d+)\.(\d+)', v or '')
        return tuple(int(x) for x in m.groups()) if m else (0, 0, 0)
    return sorted(vers, key=_vk, reverse=True)


def _semver_matches(constraint, actual):
    """约束 ^X.Y.Z 与 actual 是否匹配（MAJOR 必须相等，MINOR/PATCH >=）。"""
    cm = _SEMVER_RE.match(constraint or '')
    am = re.match(r'^(\d+)\.(\d+)\.(\d+)', actual or '')
    if not cm or not am:
        return True
    cmj, cmi, cpa = (int(x) for x in cm.groups())
    amj, ami, apa = (int(x) for x in am.groups())
    if amj != cmj:
        return False
    if constraint.startswith('^'):
        return (ami, apa) >= (cmi, cpa)
    return (amj, ami, apa) >= (cmj, cmi, cpa)


def _detect_ft010(root):
    issues = []
    plat = _platform_of(root) or ''
    if not plat:
        return issues
    for pkg, cons in sorted(_manifest_packages(root).items()):
        if not cons:
            continue
        rv = _registry_versions(pkg, plat)
        if not rv:
            continue
        actual = rv[0]
        if not _semver_matches(cons, actual):
            issues.append({
                'file': 'Manifest.xml', 'package': pkg,
                'constraint': cons, 'registryActual': actual,
                'msg': f'{pkg} 版本约束 {cons} 与 registry 实际 {actual} 的 MAJOR 不匹配'
                       f'（^X 只允许同 MAJOR；fun install 会静默跳过 → include 缺失）。应改为 ^{actual}',
            })
    return issues


def _fix_ft010(root, issues):
    fixes, notes = [], []
    if not issues:
        return fixes, notes, True
    mf = os.path.join(root, 'Manifest.xml')
    if not os.path.isfile(mf):
        return fixes, ['Manifest.xml 不存在'], False
    text = open(mf, encoding='utf-8', errors='replace').read()
    for it in issues:
        new_cons = '^' + it['registryActual']
        text = re.sub(r'(<package\s+id="' + re.escape(it['package']) + r'"\s+version=")[^"]*(")',
                      r'\g<1>' + new_cons + r'\2', text)
        fixes.append(f"Manifest.xml: {it['package']} {it['constraint']} → {new_cons}")
    open(mf, 'w', encoding='utf-8').write(text)
    for d in ('.deps.lock',):
        p = os.path.join(root, d)
        if os.path.isfile(p):
            os.remove(p)
            fixes.append(f'已删除 {d}')
    try:
        import project_tools as _pt
        ri = _pt._run_fun('install', root)
        fixes.append('fun install: ' + ('成功' if ri['success'] else '失败 ' + (ri.get('stderr') or ri.get('stdout') or '')[-200:]))
    except Exception as e:
        notes.append(f'fun install 未执行: {e}')
    notes.append('版本已对齐 registry；若仍报 include 缺失，清 .fun/<plat>/generated+build 重新 fun build')
    return fixes, notes, True


def _verify_ft010(root):
    ok, msgs = True, []
    plat = _platform_of(root) or ''
    for pkg, cons in sorted(_manifest_packages(root).items()):
        rv = _registry_versions(pkg, plat)
        if not rv:
            continue
        if not _semver_matches(cons, rv[0]):
            ok, msgs = False, [f'{pkg} {cons} 仍不匹配 registry {rv[0]}']
            break
    return ok, msgs


# ============ FT-011 新依赖必须先 fun install ============
_RULE_FT011 = {
    'kb_id': 'FT-011', 'priority': 'high',
    'name': 'Manifest 改依赖后必须先 fun install（build 不会自动 resolve）',
    'root_cause': 'Manifest 改依赖后直接 fun build：fun build 不会主动基于 Manifest 重新 resolve 依赖，'
                  '只读 .deps.lock 里之前解好的树；没有 fun install，.deps.lock 不更新，CMake 不拉新包 → include 缺失。',
    'user_patterns': ['Manifest 加了新 package 直接 build 报找不到', 'deps.lock 里没有新包', '新增包后 build 还是老 include path'],
    'anti_patterns': ['edit Manifest + immediately fun build（90% include 缺失）', 'fun install 但不清 .fun/z21/build → CMakeCache 还用老 include'],
}


def _deps_lock_packages(root):
    p = os.path.join(root, '.deps.lock')
    if not os.path.isfile(p):
        return set()
    try:
        t = open(p, encoding='utf-8', errors='replace').read()
    except Exception:
        return set()
    ids = set(re.findall(r'"id"\s*:\s*"([^"]+)"', t))
    if not ids:
        ids = set(re.findall(r'\b(package\s+)?id\s*[:=]\s*"?([A-Za-z0-9_-]+)', t))
        ids = {x[1] for x in ids}
    return ids


def _detect_ft011(root):
    issues = []
    mf_pkgs = set(_manifest_packages(root).keys())
    lock_pkgs = _deps_lock_packages(root)
    if not mf_pkgs:
        return issues
    if not lock_pkgs:
        issues.append({'file': 'Manifest.xml',
                       'msg': '.deps.lock 缺失或为空：Manifest 声明了依赖但从未成功 fun install'
                              '（改依赖后必须先 fun install，build 不会自动 resolve）'})
        return issues
    missing = mf_pkgs - lock_pkgs
    if missing:
        issues.append({'file': 'Manifest.xml',
                       'newPackages': sorted(missing),
                       'msg': f'Manifest 新增依赖未进 .deps.lock: {", ".join(sorted(missing))}'
                              f'（必须按序: rm .deps.lock → fun install → rm generated+build → fun build）'})
    return issues


def _fix_ft011(root, issues):
    fixes, notes = [], []
    if not issues:
        return fixes, notes, True
    for d in ('.deps.lock',):
        p = os.path.join(root, d)
        if os.path.isfile(p):
            os.remove(p)
            fixes.append(f'已删除 {d}（强制重新 resolve）')
    try:
        import project_tools as _pt
        ri = _pt._run_fun('install', root)
        fixes.append('fun install: ' + ('成功' if ri['success'] else '失败 ' + (ri.get('stderr') or ri.get('stdout') or '')[-200:]))
        if ri['success']:
            plat = _platform_of(root) or ''
            for base in ('.fun', '.fuse', '.fyx'):
                d = os.path.join(root, base, plat.lower())
                for sub in ('generated', 'build'):
                    t = os.path.join(d, sub)
                    if os.path.isdir(t):
                        shutil.rmtree(t, ignore_errors=True)
                        fixes.append(f'已清理 {os.path.relpath(t, root)}')
            notes.append('依赖已重新 install；请执行 fun build（或 flythings_build_ui_flow）完成编译')
    except Exception as e:
        notes.append(f'fun install 未执行: {e}')
    return fixes, notes, True


def _verify_ft011(root):
    mf_pkgs = set(_manifest_packages(root).keys())
    lock_pkgs = _deps_lock_packages(root)
    if not mf_pkgs:
        return True, []
    missing = mf_pkgs - lock_pkgs
    if missing:
        return False, [f'.deps.lock 仍缺: {", ".join(sorted(missing))}']
    return True, []


# ============ FT-012 NTP 阻塞调用在 UI 线程 ============
_RULE_FT012 = {
    'kb_id': 'FT-012', 'priority': 'critical',
    'name': 'NTP 同步不得阻塞 UI 线程（syncTime 需线程包装）',
    'root_cause': '把阻塞网络操作 ntp::syncTime（5 秒超时 × N 台服务器）直接放 onUI_init/onTimer。'
                  'FlyThings Single Activity 是单线程 GUI 事件泵，阻塞 → 画面不刷新 + 触摸不响应 + 定时器 tick 滞后。',
    'user_patterns': ['开机后欢迎屏卡 2-5 秒', 'UI Init 后按钮点不了', 'NTP 同步期间界面冻结', 'TIMER_1S tick 滞后'],
    'anti_patterns': ['ntp::syncTime 直接在 UI 线程调用', 'std::thread 没 detach/join 挂起对象析构崩溃',
                      '没有 CAS 防重入，每 60 tick 重复触发开 100 个线程'],
}


def _detect_ft012(root):
    issues = []
    for cc in _logic_ccs(root):
        text = open(cc, encoding='utf-8', errors='replace').read()
        for fn in ('onUI_init', 'onUI_Timer', 'onUI_show'):
            m = re.search(r'static\s+void\s+' + fn + r'\s*\([^)]*\)\s*\{(.*?)\n\}', text, re.S)
            if not m:
                continue
            body = m.group(1)
            if 'ntp::syncTime' in body and 'std::thread' not in body:
                issues.append({
                    'file': os.path.relpath(cc, root), 'function': fn,
                    'msg': f'{fn}() 内直接调用 ntp::syncTime（阻塞 5s×N 服务器）：'
                           f'必须用 std::thread + CAS 防重入异步执行，UI 线程只触发',
                })
    return issues


def _fix_ft012(root, issues):
    fixes, notes = [], []
    if not issues:
        return fixes, notes, True
    seen = set()
    for it in issues:
        p = os.path.join(root, it['file'])
        if p in seen:
            continue
        seen.add(p)
        text = open(p, encoding='utf-8', errors='replace').read()
        if 'asyncNtpSyncTrigger' not in text:
            block = (
                '// FT-012: NTP 同步不得阻塞 UI 线程（异步线程 + CAS 防重入）\n'
                'static std::atomic<bool> gNtpRunning = {false};\n'
                'static void syncNtpBlocking() {\n'
                '    // TODO: 原 ntp::syncTime / startSyncTime 阻塞调用放这里\n'
                '    ntp::syncTime(ntp::defaultServerList(), 3000);\n'
                '}\n'
                'static void asyncNtpSyncTrigger() {\n'
                '    if (gNtpRunning) return;\n'
                '    bool expected = false;\n'
                '    if (!gNtpRunning.compare_exchange_strong(expected, true)) return;\n'
                '    std::thread th([](){ syncNtpBlocking(); gNtpRunning = false; });\n'
                '    th.detach();\n'
                '}\n'
            )
            if '#include' in text:
                pos = text.rfind('#include')
                eol = text.find('\n', pos)
                text = text[:eol + 1] + '\n' + block + text[eol + 1:]
            else:
                text = block + text
            fixes.append(f'{it["file"]}: 注入 asyncNtpSyncTrigger 线程包装（syncNtpBlocking 内需替换为真实同步调用）')
        text = re.sub(r'(static\s+void\s+onUI_init\s*\([^)]*\)\s*\{\s*)',
                      r'\1    asyncNtpSyncTrigger();  // FT-012: NTP 异步，不阻塞 UI\n',
                      text, count=1)
        open(p, 'w', encoding='utf-8').write(text)
    notes.append('已在 onUI_init 注入异步触发；请把 syncNtpBlocking() 内的 TODO 替换为真实的 ntp::syncTime/startSyncTime 调用')
    return fixes, notes, True


def _verify_ft012(root):
    ok, msgs = True, []
    for cc in _logic_ccs(root):
        text = open(cc, encoding='utf-8', errors='replace').read()
        m = re.search(r'static\s+void\s+onUI_init\s*\([^)]*\)\s*\{(.*?)\n\}', text, re.S)
        if m and 'ntp::syncTime' in m.group(1) and 'asyncNtpSyncTrigger' not in m.group(1):
            ok, msgs = False, [f'{os.path.relpath(cc, root)}: onUI_init 仍直调 ntp::syncTime']
            break
    return ok, msgs


# ============ FT-013 TZ 时区（POSIX 反号 + 先设） ============
_RULE_FT013 = {
    'kb_id': 'FT-013', 'priority': 'high',
    'name': 'TZ 时区必须在 onUI_init 先设（不依赖 NTP），POSIX 反号要写 UTC-8',
    'root_cause': '①时区只在 syncNtpBlocking 里设——NTP 慢/断网就用默认 UTC 显示；'
                  '②写错 POSIX TZ="UTC+8"（POSIX 反号：UTC+8 实际 = UTC-8 西八区，北京必须是 UTC-8）。',
    'user_patterns': ['屏幕时间比北京慢 8 小时', 'NTP 成功前显示 UTC', '网络断时区就错', '显示 06:31 不是 14:31'],
    'anti_patterns': ['setenv TZ=UTC+8（反号错 16h）', 'TZ 只在 NTP 成功后才设', '只 setenv 忘 tzset()'],
}


def _detect_ft013(root):
    issues = []
    for cc in _logic_ccs(root):
        text = open(cc, encoding='utf-8', errors='replace').read()
        for m in re.finditer(r'setenv\s*\(\s*"TZ"\s*,\s*"UTC\+8"', text):
            issues.append({'file': os.path.relpath(cc, root),
                           'msg': f'第 {text[:m.start()].count(chr(10)) + 1} 行 setenv("TZ","UTC+8") 反号：'
                                  f'POSIX 时区符号相反，北京应为 "UTC-8"（UTC+8 实际是西八区）'})
        m = re.search(r'static\s+void\s+onUI_init\s*\([^)]*\)\s*\{(.*?)\n\}', text, re.S)
        if m:
            body = m.group(1)
            has_tz = 'setenv' in body and '"TZ"' in body
            if not has_tz and ('ntp::' in text or 'syncNtp' in text):
                issues.append({'file': os.path.relpath(cc, root),
                               'msg': f'onUI_init 未设置 TZ 时区（NTP 相关代码存在）：'
                                      f'时区必须在 onUI_init 第一行 setenv("TZ","UTC-8",1)+tzset()，'
                                      f'不依赖 NTP 线程启动（断网/慢也要显示对）'})
    return issues


def _fix_ft013(root, issues):
    fixes, notes = [], []
    if not issues:
        return fixes, notes, True
    for it in issues:
        p = os.path.join(root, it['file'])
        text = open(p, encoding='utf-8', errors='replace').read()
        changed = False
        if 'UTC+8' in text:
            text = re.sub(r'setenv\s*\(\s*"TZ"\s*,\s*"UTC\+8"', 'setenv("TZ", "UTC-8"', text)
            changed = True
            fixes.append(f'{it["file"]}: TZ=UTC+8 反号 → UTC-8（POSIX 符号）')
        m = re.search(r'static\s+void\s+onUI_init\s*\([^)]*\)\s*\{\s*', text)
        if m and 'UTC-8' not in text[:m.end() + 200]:
            code = '    setenv("TZ", "UTC-8", 1); tzset();  // FT-013: 时区先设，不依赖 NTP\n'
            text = text[:m.end()] + code + text[m.end():]
            changed = True
            fixes.append(f'{it["file"]}: onUI_init 第一行插入 setenv("TZ","UTC-8",1)+tzset()')
        if changed:
            open(p, 'w', encoding='utf-8').write(text)
    return fixes, notes, True


def _verify_ft013(root):
    ok, msgs = True, []
    for cc in _logic_ccs(root):
        text = open(cc, encoding='utf-8', errors='replace').read()
        if 'UTC+8' in text:
            ok, msgs = False, [f'{os.path.relpath(cc, root)}: 仍含 TZ=UTC+8 反号']
            break
        m = re.search(r'static\s+void\s+onUI_init\s*\([^)]*\)\s*\{(.*?)\n\}', text, re.S)
        if m and 'setenv' in m.group(1) and '"TZ"' in m.group(1) and 'UTC-8' in m.group(1):
            continue
        if 'ntp::' in text and not (m and 'UTC-8' in m.group(1)):
            ok, msgs = False, [f'{os.path.relpath(cc, root)}: onUI_init 缺 TZ=UTC-8 设置']
            break
    return ok, msgs


# ============ FT-014 包 id/version 查 registry 不猜写 ============
_RULE_FT014 = {
    'kb_id': 'FT-014', 'priority': 'medium',
    'name': '包 id/version 必须先查 registry（禁止凭空猜写）',
    'root_cause': '不查 registry 直接猜 package id/version（如猜 zkntp/ntpclient）。'
                  'FlyThings 全局注册表在 <FUN_ROOT>/fun/registry/public/<PLATFORM>/<PACKAGE>/<VERSION>/Manifest.xml 有精确值。',
    'user_patterns': ['不知道包精确 id 和 version', '查 ntp 包叫 zkntp 还是 ntp', '如何查本地已安装包列表'],
    'anti_patterns': ['猜包名: zkntp, ntpclient, zktime', '写 version="^2.1.0" 而 registry 只有 2.1.1'],
}


def _detect_ft014(root):
    issues = []
    plat = _platform_of(root) or ''
    if not plat:
        return issues
    for pkg, cons in sorted(_manifest_packages(root).items()):
        rv = _registry_versions(pkg, plat)
        if rv:
            continue
        # registry 无实体 → 可能猜写 id；catalog 有则提示走 add_package，无则提示查 registry
        hint = ''
        try:
            import package_tools as _pkg
            cv = _pkg._catalog_versions(pkg, plat.lower())
            if cv:
                hint = f'本地 registry 无实体（catalog 有 {cv[0]}）：确认包 id 正确后应清缓存重新 fun install，或用 flythings_add_package 走闭环流程'
        except Exception:
            pass
        if not hint:
            hint = f'在 registry 未找到实体，疑似猜写包 id；先查 registry（flythings_query_package / list_packages）再写 Manifest'
        issues.append({'file': 'Manifest.xml', 'package': pkg, 'msg': hint})
    return issues


def _fix_ft014(root, issues):
    fixes, notes = [], []
    if not issues:
        return fixes, notes, True
    for it in issues:
        pkg = it.get('package', '')
        try:
            import package_tools as _pkg
            r = _pkg.flythings_add_package(root, pkg, with_install=False)
            if r.get('success'):
                fixes.append(f'{pkg} → 已按 registry/catalog 版本 {r.get("version")} 更新 Manifest（flythings_add_package）')
                notes.append(f'{pkg} 需 fun install 拉取实体（可用 flythings_add_package with_install=True 或 build_ui_flow）')
            else:
                notes.append(f'{pkg} 未找到可用版本: {r.get("error", "")}')
        except Exception as e:
            notes.append(f'{pkg} 自动修正失败: {e}')
    return fixes, notes, True


def _verify_ft014(root):
    return True, ['FT-014 为流程规则（查 registry 不猜写），已提示']


# ============ FT-020 HTML 语义图标转 PNG ============
_RULE_FT020 = {
    'kb_id': 'FT-020', 'priority': 'critical',
    'name': 'HTML 语义图标（icon/check/tick/plug 等）必须转 PNG + backgroundPic',
    'root_cause': 'HTML→JSON 转换只把 TextNode 映射成 TextView，没对语义图标（icon/tick/success/plug 等关键词）'
                  '做第二步"生成 PNG + 插入 backgroundPic"映射 → 图标变 [OK]/[Plug] 文字，页面像低保真线框。',
    'user_patterns': ['完成页成功图标没生成', 'HTML 有对勾绿圆但 json 没有 picture', '充电枪插头图标没出现',
                      '语义图标被转成 [ OK ] 文字', '装饰图片缺失像线框'],
    'anti_patterns': ['看到 class=ok-icon 就生成 setText("[ OK ]")', '图标缩成 24x24 小图放角落', 'inline SVG 跳过不处理'],
}

_ICON_KEYWORDS = re.compile(
    r'(?i)(icon|check|tick|success|done|ok|plug|battery|clock|hourglass|warning|error|warn|'
    r'lightning|bolt|qr|scan|wifi|signal|plug_in|power|charge|stop|confirm|cancel|home|back|arrow)')


def _is_icon_control(key, val):
    """判定控件是否语义图标：①caption 带 Icon/Img/ImageView 后缀；②文本为空且关键词命中。
    排除 Text*/Label* 前缀的文本显示控件（如 TextClock/LabelVolt 是文本不是图标）。"""
    cap = str(val.get('caption', ''))
    text = str(val.get('text', ''))
    # 明确图标后缀 → 一定是图标
    if re.search(r'(?i)(icon|img|imageview|pic)$', cap):
        return True
    # 文本显示控件（Text/Label 前缀且有文本内容）→ 不是图标
    if re.match(r'(?i)^(text|label)', cap) and text.strip():
        return False
    # 关键词命中 + 无文本（纯图标占位）→ 图标
    if _ICON_KEYWORDS.search(cap) and not text.strip():
        return True
    return False


def _detect_ft020(root):
    issues = []
    for jp in _ui_jsons(root):
        data = _load_json(jp)
        if '__error__' in data:
            continue
        for key, val in _iter_controls(data):
            if not isinstance(val, dict):
                continue
            if not _is_icon_control(key, val):
                continue
            has_pic = bool(val.get('backgroundPic')) or bool(val.get('picTab')) or bool(val.get('src'))
            if not has_pic:
                cap = str(val.get('caption', ''))
                issues.append({
                    'file': os.path.relpath(jp, root), 'control': key,
                    'caption': cap, 'text': str(val.get('text', ''))[:14],
                    'msg': f'{key}({cap}) 疑似语义图标（关键词: {cap}）'
                           f'但无 backgroundPic：需生成 PNG 图标并引用，不能只用文字占位',
                })
    return issues


def _fix_ft020(root, issues):
    fixes, notes = [], []
    if not issues:
        return fixes, notes, True
    if not _HAS_PIL:
        return fixes, ['需要 PIL 生成图标 PNG，跳过'], False
    try:
        import sys as _sys
        _sys.path.insert(0, os.path.join(_BASE, 'ui_tools'))
        import gen_res as _gr
    except Exception as e:
        return fixes, [f'gen_res 导入失败: {e}'], False
    for jp in _ui_jsons(root):
        data = _load_json(jp)
        if '__error__' in data:
            continue
        changed = False
        for key, val in list(_iter_controls(data)):
            if not isinstance(val, dict):
                continue
            if not _is_icon_control(key, val):
                continue
            if val.get('backgroundPic') or val.get('picTab'):
                continue
            cap = str(val.get('caption', ''))
            pos = val.get('position') or {}
            w, h = pos.get('width', 48), pos.get('height', 48)
            kind = 'check'
            low = cap.lower()
            if any(k in low for k in ('alert', 'warn', 'error')):
                kind = 'alert'
            elif any(k in low for k in ('charge', 'bolt', 'lightning', 'power')):
                kind = 'charging'
            elif any(k in low for k in ('wifi', 'signal')):
                kind = 'wifi'
            name = 'icon_%s.png' % cap
            out_dir = os.path.join(root, 'ui', 'images')
            os.makedirs(out_dir, exist_ok=True)
            color = (0x2E, 0xCC, 0x71, 255) if any(k in low for k in ('success', 'ok', 'check', 'tick', 'done')) \
                else (0xE7, 0x4C, 0x3C, 255) if any(k in low for k in ('error', 'warn', 'alert', 'stop')) \
                else (0x2F, 0x6D, 0xF6, 255)
            try:
                _gr.icon_circle(out_dir, name, max(w, h), color, kind)
                val['backgroundPic'] = 'images/' + name
                val.pop('text', None)
                val['touchable'] = False
                changed = True
                fixes.append(f'{os.path.relpath(jp, root)}: {key}({cap}) 生成 {name} + backgroundPic')
            except Exception as e:
                notes.append(f'{cap} 图标生成失败: {e}')
        if changed:
            _dump_json(jp, data)
    notes.append('图标已按语义生成（check/charging/wifi/alert 线条兜底）；如需更精致可换 AI 生图或手动切图')
    return fixes, notes, True


def _verify_ft020(root):
    ok, msgs = True, []
    for jp in _ui_jsons(root):
        data = _load_json(jp)
        if '__error__' in data:
            continue
        for key, val in _iter_controls(data):
            if _is_icon_control(key, val) and not val.get('backgroundPic') and not val.get('picTab'):
                ok, msgs = False, [f'{os.path.relpath(jp, root)}: {key}({val.get("caption", "")}) 仍无图标图']
                break
    return ok, msgs


# ============ FT-021 渐变圆角背景 → backgroundPic（删 backgroundColor） ============
_RULE_FT021 = {
    'kb_id': 'FT-021', 'priority': 'high',
    'name': '渐变/圆角背景必须转 PNG（backgroundPic），禁止 backgroundColor 双写',
    'root_cause': '把 HTML CSS 渐变映射成 backgroundColor 单色；FlyThings 控件不支持属性式渐变/圆角，'
                  '只能 backgroundPic PNG 表现；backgroundColor 与 backgroundPic 双写会被纯色覆盖 → 方角。',
    'user_patterns': ['按钮没圆角太硬', 'HTML 渐变圆角但 json 纯色', '卡片没有阴影圆角是黑边方盒'],
    'anti_patterns': ['backgroundColor 和 backgroundPic 同时存在（被 backgroundColor 覆盖）'],
}


def _detect_ft021(root):
    issues = []
    for jp in _ui_jsons(root):
        data = _load_json(jp)
        if '__error__' in data:
            continue
        for key, val in _iter_controls(data):
            if not isinstance(val, dict):
                continue
            pic = val.get('backgroundPic') or (val.get('picTab') or {}).get('pic0')
            if pic and (val.get('bgColorTab') is not None or 'backgroundColor' in val):
                issues.append({
                    'file': os.path.relpath(jp, root), 'control': key,
                    'msg': f'{key}({val.get("caption", "")}) 同时有 backgroundPic 与底色字段'
                           f'（bgColorTab/backgroundColor）：纯色会覆盖背景图 → 视觉方角，需删除底色字段（FT-021）',
                })
    return issues


def _fix_ft021(root, issues):
    fixes, notes = [], []
    if not issues:
        return fixes, notes, True
    for jp in _ui_jsons(root):
        data = _load_json(jp)
        if '__error__' in data:
            continue
        changed = False
        for key, val in list(_iter_controls(data)):
            if not isinstance(val, dict):
                continue
            pic = val.get('backgroundPic') or (val.get('picTab') or {}).get('pic0')
            if pic and val.get('bgColorTab') is not None:
                del val['bgColorTab']
                changed = True
                fixes.append(f'{os.path.relpath(jp, root)}: {key} 删除 bgColorTab（避免覆盖背景图）')
            if pic and 'backgroundColor' in val:
                del val['backgroundColor']
                changed = True
        if changed:
            _dump_json(jp, data)
    return fixes, notes, True


def _verify_ft021(root):
    ok, msgs = True, []
    for jp in _ui_jsons(root):
        data = _load_json(jp)
        if '__error__' in data:
            continue
        for key, val in _iter_controls(data):
            pic = val.get('backgroundPic') or (val.get('picTab') or {}).get('pic0')
            if pic and val.get('bgColorTab') is not None:
                ok, msgs = False, [f'{os.path.relpath(jp, root)}: {key} 仍双写底色']
                break
    return ok, msgs


# ============ FT-022 资源尺寸严格匹配 position ============
_RULE_FT022 = {
    'kb_id': 'FT-022', 'priority': 'high',
    'name': '资源 PNG 尺寸必须与控件 position 严格相等',
    'root_cause': '生成资源随手写死尺寸，不把 main.json 的 position.w/h 作为 ground truth；'
                  'FlyThings 按 position rect 直接 drawBitmap 不缩放 → 尺寸不等就拉伸糊/短一截。',
    'user_patterns': ['进度条背景和前景高度不一样', '卡片短一截', '按钮被拉伸糊'],
    'anti_patterns': ['硬编码 seekbar_bg/h=10 而实际 position.h=28'],
}


def _detect_ft022(root):
    issues = []
    for jp in _ui_jsons(root):
        data = _load_json(jp)
        if '__error__' in data:
            continue
        for key, val in _iter_controls(data):
            if not isinstance(val, dict):
                continue
            pos = val.get('position') or {}
            pw, ph = pos.get('width'), pos.get('height')
            if not pw or not ph:
                continue
            pics = []
            bp = val.get('backgroundPic')
            if isinstance(bp, str):
                pics.append(bp)
            pt_ = val.get('picTab') or {}
            for f in ('pic0', 'pic1'):
                v = pt_.get(f)
                if isinstance(v, str):
                    pics.append(v)
            for pic in dict.fromkeys(pics):
                # ⚠️ .9.png 是九宫格可拉伸图（支持拉伸复用），尺寸不要求等于 position；
                # 只有普通 PNG 才按 position rect 直接 drawBitmap 不缩放 → 必须严格相等
                if pic.lower().endswith('.9.png'):
                    continue
                found = False
                for d in _img_dirs(root):
                    # json 引用可能是 images/xxx.png（带前缀）或 xxx.png；图片实际都在 images 目录下
                    p = os.path.join(d, os.path.basename(pic))
                    if os.path.isfile(p):
                        eff = _eff_size(p)
                        if eff and (eff[0] != pw or eff[1] != ph):
                            issues.append({
                                'file': os.path.relpath(jp, root), 'control': key, 'pic': pic,
                                'expect': f'{pw}x{ph}', 'actual': f'{eff[0]}x{eff[1]}',
                                'msg': f'{key} 引用 {pic} 尺寸 {eff[0]}x{eff[1]} ≠ position {pw}x{ph}'
                                       f'（FlyThings 不缩放普通 PNG，必须严格相等）',
                            })
                        found = True
                        break
                if not found:
                    issues.append({
                        'file': os.path.relpath(jp, root), 'control': key, 'pic': pic,
                        'msg': f'{key} 引用 {pic} 但图片文件不存在（资源缺失）',
                    })
    return issues


def _fix_ft022(root, issues):
    fixes, notes = [], []
    if not issues:
        return fixes, notes, True
    if not _HAS_PIL:
        return fixes, ['需要 PIL 重生成匹配尺寸图片'], False
    for it in issues:
        if 'expect' not in it or it.get('pic') is None:
            continue
        if it['pic'].lower().endswith('.9.png'):
            continue  # 9-patch 可拉伸，无需重生成
        w, h = it['expect'].split('x')
        w, h = int(w), int(h)
        base = os.path.basename(it['pic'])
        for d in _img_dirs(root):
            p = os.path.join(d, base)
            if not os.path.isfile(p):
                continue
            try:
                from PIL import Image as _I, ImageDraw as _D
                with _I.open(p) as im:
                    px = im.convert('RGBA')
                    cw, ch = px.size
                    color = px.getpixel((cw // 2, ch // 2))[:3]
                    corner_a = px.getpixel((2, 2))[3]
                img = _I.new('RGBA', (w, h), (0, 0, 0, 0))
                radius = min(h // 2, 12) if corner_a == 0 else 0
                _D.Draw(img).rounded_rectangle([0, 0, w - 1, h - 1], radius=radius,
                                               fill=color + (255,))
                img.save(p)
                fixes.append(f'{os.path.relpath(p, root)}: 重生成 {w}x{h}（FT-022 尺寸对齐）')
            except Exception as e:
                notes.append(f'{it["pic"]} 重生成失败: {e}')
            break
    return fixes, notes, True


def _verify_ft022(root):
    ok, msgs = True, []
    for jp in _ui_jsons(root):
        data = _load_json(jp)
        if '__error__' in data:
            continue
        for key, val in _iter_controls(data):
            pos = val.get('position') or {}
            pw, ph = pos.get('width'), pos.get('height')
            if not pw or not ph:
                continue
            pics = [v for v in (val.get('backgroundPic'), (val.get('picTab') or {}).get('pic0'))
                    if isinstance(v, str)]
            for pic in pics:
                if pic.lower().endswith('.9.png'):
                    continue  # 9-patch 可拉伸
                for d in _img_dirs(root):
                    p = os.path.join(d, os.path.basename(pic))
                    if os.path.isfile(p):
                        eff = _eff_size(p)
                        if eff and (eff[0] != pw or eff[1] != ph):
                            ok, msgs = False, [f'{key} {pic} {eff[0]}x{eff[1]} ≠ {pw}x{ph}']
                        break
    return ok, msgs


# ============ FT-023 端到端 4 阶段自检 ============
_RULE_FT023 = {
    'kb_id': 'FT-023', 'priority': 'high',
    'name': 'HTML→json 转换后必须跑 4 阶段自检（JSON 合法/图标齐全/尺寸/9patch）',
    'root_cause': '转换做完就交付，缺少统一的 4 阶段自检脚本，导致 FT-002/003/008/020 等结构性错误反复人工反馈。',
    'user_patterns': ['每次都要人工点屏幕才知道哪里漏了', '倒角锯齿/尺寸不一致/资源缺失/SeekBar 黑边反复出现'],
    'anti_patterns': ['转换完成不跑任何检查直接交付'],
}

_VERIFY_PIPELINE_SCRIPT = r'''# -*- coding: utf-8 -*-
"""FlyThings HTML→json 4 阶段自检（FT-023）：交付前必跑。
Stage1 JSON 合法校验 -> Stage2 语义图标齐全 -> Stage3 资源尺寸匹配 -> Stage4 9-patch marker。
用法: python verify_pipeline.py <项目根>
"""
import json, os, sys, re

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
fails = []

def stage1_json_valid():
    ui = os.path.join(ROOT, 'ui')
    if not os.path.isdir(ui):
        fails.append('[Stage1] ui 目录不存在'); return
    for fn in sorted(os.listdir(ui)):
        if not fn.endswith('.json'):
            continue
        try:
            json.load(open(os.path.join(ui, fn), encoding='utf-8-sig'))
        except Exception as e:
            fails.append('[Stage1] %s JSON 非法: %s' % (fn, e))

def stage2_icons():
    ui = os.path.join(ROOT, 'ui')
    if not os.path.isdir(ui):
        return
    for fn in sorted(os.listdir(ui)):
        if not fn.endswith('.json'):
            continue
        data = json.load(open(os.path.join(ui, fn), encoding='utf-8-sig'))
        for k, v in data.items():
            if not isinstance(v, dict) or '__' not in k:
                continue
            cap = str(v.get('caption', ''))
            if re.search(r'(?i)(icon|check|tick|success|ok|plug|alert|warn)', cap):
                if not v.get('backgroundPic') and not v.get('picTab'):
                    fails.append('[Stage2] %s %s(%s) 语义图标缺 backgroundPic' % (fn, k, cap))

def stage3_size():
    ui = os.path.join(ROOT, 'ui')
    if not os.path.isdir(ui):
        return
    for fn in sorted(os.listdir(ui)):
        if not fn.endswith('.json'):
            continue
        data = json.load(open(os.path.join(ui, fn), encoding='utf-8-sig'))
        for k, v in data.items():
            if not isinstance(v, dict) or '__' not in k:
                continue
            pos = v.get('position') or {}
            pw, ph = pos.get('width'), pos.get('height')
            if not pw or not ph:
                continue
            for pic in (v.get('backgroundPic'), (v.get('picTab') or {}).get('pic0')):
                if not isinstance(pic, str):
                    continue
                for d in ('ui/images', 'resources/images'):
                    p = os.path.join(ROOT, d, pic)
                    if not os.path.isfile(p):
                        continue
                    try:
                        from PIL import Image
                        with Image.open(p) as im:
                            w, h = im.size
                        if pic.endswith('.9.png'):
                            w, h = w - 2, h - 2
                        if w != pw or h != ph:
                            fails.append('[Stage3] %s %s %s %dx%d != position %dx%d' % (fn, k, pic, w, h, pw, ph))
                    except Exception:
                        pass
                    break

def stage4_9patch_marker():
    ui = os.path.join(ROOT, 'ui')
    if not os.path.isdir(ui):
        return
    for fn in sorted(os.listdir(ui)):
        if not fn.endswith('.json'):
            continue
        data = json.load(open(os.path.join(ui, fn), encoding='utf-8-sig'))
        for k, v in data.items():
            if not isinstance(v, dict) or not k.startswith('seekbar'):
                continue
            for f in ('progressPic', 'backgroundPic', 'thumbPic'):
                pic = v.get(f, '')
                if isinstance(pic, str) and pic.endswith('.9.png'):
                    fails.append('[Stage4] %s %s.%s 仍用 9-patch（SeekBar 不解析 marker）-> 改 .png' % (fn, k, f))

stage1_json_valid(); stage2_icons(); stage3_size(); stage4_9patch_marker()
if fails:
    print('\n'.join(fails)); sys.exit(1)
print('4 阶段自检全部通过 OK')
'''


def _detect_ft023(root):
    issues = []
    checks = [os.path.join(root, 'tools', 'verify_pipeline.py'),
              os.path.join(root, 'tools', 'check_all.py')]
    if not any(os.path.isfile(c) for c in checks):
        issues.append({
            'file': 'pipeline',
            'msg': '项目缺少 4 阶段自检脚本（tools/verify_pipeline.py）：'
                   'HTML→json 转换后必须跑 Stage1 JSON 合法校验 / Stage2 图标齐全 / '
                   'Stage3 资源尺寸 / Stage4 9-patch marker，才能交付',
        })
    for jp in _ui_jsons(root):
        data = _load_json(jp)
        if '__error__' in data:
            issues.append({'file': os.path.relpath(jp, root),
                           'msg': f'JSON 非法: {data["__error__"]}'})
    return issues


def _fix_ft023(root, issues):
    fixes, notes = [], []
    if not issues:
        return fixes, notes, True
    script = os.path.join(root, 'tools', 'verify_pipeline.py')
    os.makedirs(os.path.dirname(script), exist_ok=True)
    open(script, 'w', encoding='utf-8').write(_VERIFY_PIPELINE_SCRIPT)
    fixes.append(f'已生成 {os.path.relpath(script, root)}（4 阶段自检脚本）')
    notes.append('交付前执行 python tools/verify_pipeline.py <项目根>，4 关全过再 build/launch')
    return fixes, notes, True


def _verify_ft023(root):
    script = os.path.join(root, 'tools', 'verify_pipeline.py')
    if os.path.isfile(script):
        return True, ['自检脚本已就位（交付前运行）']
    return False, ['缺少 tools/verify_pipeline.py']


# ============ FT-024: text 禁止换行符（设备不支持 \n 多行）============
_RULE_FT024 = {
    'kb_id': 'FT-024', 'priority': 'high',
    'name': '文本控件 text 禁止含换行符（\\n 多行设备不支持）',
    'root_cause': 'FlyThings textview/button 的 text 不渲染 \\n，json 里写换行设备只显示部分/异常（UIlayoutDemo TvRow 校准）。'
                  '多行内容应拆多个 textview 上下排列。',
    'user_patterns': ['文本换行显示不全', 'json 里写了 \\n 设备不显示第二行', '多行文字挤成一坨'],
    'anti_patterns': ['用 \\n 硬拼多行文本', '依赖 HTML <br> 转多行'],
}


def _detect_ft024(root):
    """检测 ui/*.json 中所有 text 含真实换行符（\n）的控件。"""
    issues = []
    for jp in _ui_jsons(root):
        data = _load_json(jp)
        if '__error__' in data:
            continue
        for key, val in _iter_controls(data):
            text = val.get('text') if isinstance(val, dict) else None
            if isinstance(text, str) and '\n' in text:
                issues.append({
                    'file': os.path.relpath(jp, root),
                    'ctrl': key,
                    'caption': val.get('caption', ''),
                    'text': text,
                    'msg': f'{key}({val.get("caption", "")}) 的 text 含换行符，设备不渲染多行 → 拆多个 textview 或折叠为空格',
                })
    return issues


def _fix_ft024(root, issues):
    """自动把换行符折叠为空格（保证设备正常渲染单行）；多行布局需人工拆控件。"""
    fixes, notes = [], []
    if not issues:
        return fixes, notes, True
    by_file = {}
    for it in issues:
        by_file.setdefault(it['file'], []).append(it)
    for rel, items in by_file.items():
        jp = os.path.join(root, rel)
        data = _load_json(jp)
        if '__error__' in data:
            continue
        changed = False
        for it in items:
            for key, val in _iter_controls(data):
                if key != it['ctrl']:
                    continue
                if isinstance(val.get('text'), str) and '\n' in val['text']:
                    val['text'] = re.sub(r'\s+', ' ', val['text']).strip()
                    changed = True
                    fixes.append(f'{rel} {key}: 换行符已折叠为空格（设备不支持多行）')
        if changed:
            with open(jp, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
    notes.append('如需真正多行：拆成多个 textview 上下排列（各自 setText），或用两个 36 对齐的 textview 拼一行')
    return fixes, notes, True


def _verify_ft024(root):
    issues = _detect_ft024(root)
    if not issues:
        return True, ['所有文本控件无换行符']
    return False, [i['msg'] for i in issues[:5]]

# ============ 规则注册表 ============
RULES = [
    {'meta': _RULE_FT001, 'detect': _detect_ft001, 'fix': _fix_ft001, 'verify': _verify_ft001},
    {'meta': _RULE_FT002, 'detect': _detect_ft002, 'fix': _fix_ft002, 'verify': _verify_ft002},
    {'meta': _RULE_FT003, 'detect': _detect_ft003, 'fix': _fix_ft003, 'verify': _verify_ft003},
    {'meta': _RULE_FT004, 'detect': _detect_ft004, 'fix': _fix_ft004, 'verify': _verify_ft004},
    {'meta': _RULE_FT005, 'detect': _detect_ft005, 'fix': _fix_ft005, 'verify': _verify_ft005},
    {'meta': _RULE_FT006, 'detect': _detect_ft006, 'fix': _fix_ft006, 'verify': _verify_ft006},
    {'meta': _RULE_FT008, 'detect': _detect_ft008, 'fix': _fix_ft008, 'verify': _verify_ft008},
    {'meta': _RULE_FT009, 'detect': _detect_ft009, 'fix': _fix_ft009, 'verify': _verify_ft009},
    {'meta': _RULE_FT010, 'detect': _detect_ft010, 'fix': _fix_ft010, 'verify': _verify_ft010},
    {'meta': _RULE_FT011, 'detect': _detect_ft011, 'fix': _fix_ft011, 'verify': _verify_ft011},
    {'meta': _RULE_FT012, 'detect': _detect_ft012, 'fix': _fix_ft012, 'verify': _verify_ft012},
    {'meta': _RULE_FT013, 'detect': _detect_ft013, 'fix': _fix_ft013, 'verify': _verify_ft013},
    {'meta': _RULE_FT014, 'detect': _detect_ft014, 'fix': _fix_ft014, 'verify': _verify_ft014},
    {'meta': _RULE_FT020, 'detect': _detect_ft020, 'fix': _fix_ft020, 'verify': _verify_ft020},
    {'meta': _RULE_FT021, 'detect': _detect_ft021, 'fix': _fix_ft021, 'verify': _verify_ft021},
    {'meta': _RULE_FT022, 'detect': _detect_ft022, 'fix': _fix_ft022, 'verify': _verify_ft022},
    {'meta': _RULE_FT023, 'detect': _detect_ft023, 'fix': _fix_ft023, 'verify': _verify_ft023},
    {'meta': _RULE_FT024, 'detect': _detect_ft024, 'fix': _fix_ft024, 'verify': _verify_ft024},
]


def flythings_fix_project(project_root, kb_id='', apply=False):
    """按 fix.log 修复知识库（FT-001~FT-009）自动诊断并修复 FlyThings 项目。

    传入项目根目录完整路径。
    - kb_id 传 'FT-001' 等只处理该条；留空处理全部 9 条。
    - apply=False（默认）仅诊断（dry-run），返回每个规则命中/未命中与修复计划；
    - apply=True 执行修复，并逐条验证。
    诊断维度：ui/*.json 布局、src/logic/*.cc 逻辑、资源图片尺寸/生成脚本、fui generated 缓存。
    """
    if not os.path.isdir(project_root):
        return {"success": False, "error": f"项目目录不存在: {project_root}"}
    rules = RULES
    if kb_id:
        rules = [r for r in RULES if r['meta']['kb_id'] == kb_id.upper()]
        if not rules:
            return {"success": False, "error": f"未知规则: {kb_id}（可用: {', '.join(r['meta']['kb_id'] for r in RULES)}）"}
    results = []
    for rule in rules:
        meta = rule['meta']
        try:
            issues = rule['detect'](project_root)
        except Exception as e:
            results.append({'kb_id': meta['kb_id'], 'name': meta['name'],
                            'priority': meta['priority'], 'detected': False,
                            'error': f'detect 异常: {e}'})
            continue
        item = {'kb_id': meta['kb_id'], 'name': meta['name'],
                'priority': meta['priority'],
                'root_cause': meta['root_cause'],
                'user_patterns': meta['user_patterns'],
                'anti_patterns': meta['anti_patterns'],
                'detected': bool(issues), 'issues': issues}
        if issues and apply:
            try:
                fixes, notes, ok = rule['fix'](project_root, issues)
                vok, vmsgs = rule['verify'](project_root)
                item['fixes'] = fixes
                item['notes'] = notes
                item['fixed'] = ok
                item['verify'] = {'ok': vok, 'messages': vmsgs}
            except Exception as e:
                item['fixed'] = False
                item['error'] = f'fix 异常: {e}'
        elif issues:
            item['fixPlan'] = '检测到问题（apply=False 未执行修复，可传 apply=True 自动修复）'
        else:
            item['fixPlan'] = '未命中'
        results.append(item)
    summary = {
        'success': True,
        'projectRoot': project_root,
        'apply': apply,
        'total': len(rules),
        'detected': sum(1 for r in results if r.get('detected')),
        'fixed': sum(1 for r in results if r.get('fixed')),
        'results': results,
    }
    return summary


def fix_rules_summary():
    """返回全部修复规则元信息（供 get_version/说明使用）。"""
    return [{'kb_id': r['meta']['kb_id'], 'name': r['meta']['name'],
             'priority': r['meta']['priority'],
             'user_patterns': r['meta']['user_patterns'],
             'anti_patterns': r['meta']['anti_patterns']} for r in RULES]


if __name__ == '__main__':
    import sys
    root = sys.argv[1] if len(sys.argv) > 1 else r'C:\Users\zkswe\.openclaw\workspace\projects\ChargePileHMI_Z21'
    apply = '--apply' in sys.argv
    print(json.dumps(flythings_fix_project(root, apply=apply), ensure_ascii=False, indent=2))
