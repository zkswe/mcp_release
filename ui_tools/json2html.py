#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""JSON 布局 → HTML 预览页（通用工具 v1，不随项目复制）

用途：把 ui/*.json（或单个 json）渲染成浏览器可看的 HTML 交互预览稿，
供客户确认 UI 交互。与 fui pack 生成的 ftu 同源于 json 布局。

用法：
    python json2html.py <项目根目录或 json 文件路径> [输出目录]

示例：
    python tools/ui_tools/json2html.py projects/MyApp
    python tools/ui_tools/json2html.py ui/main.json out_preview/
"""
import base64, json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


# ---------- 工具 ----------
def _color(intval, default='#888888'):
    try:
        v = int(intval)
        if v < 0 or v > 0xFFFFFF:
            return default
        return '#%06X' % v
    except Exception:
        return default


# 图片引用 → 真实文件（FlyThings 引用相对 resources 目录，可带子目录，如 audio/horn.png）
_MIME = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
         '.gif': 'image/gif', '.bmp': 'image/bmp', '.webp': 'image/webp'}


def find_asset(pic, base_dir=''):
    """定位图片资源真实路径。按顺序找：<项目>/resources/<引用>、<项目>/resources/<basename>、
    <json同目录>[/images]/…、<项目>/<引用>；再退一步试 .9.png 九宫格变体。
    （2026-09-10 修：旧实现只按 basename 找 resources/images/，带子目录的引用
      如 audio/horn.png、dvr/record.png 全部找不到 → 预览丢图、尺寸预检漏报）"""
    if not pic or str(pic).startswith(('http://', 'https://', 'data:')):
        return None
    rel = str(pic).replace('\\', '/').lstrip('/')
    base = os.path.basename(rel)
    roots = []
    if base_dir:
        proj = os.path.dirname(os.path.abspath(base_dir))
        roots = [os.path.join(proj, 'resources'),
                 os.path.join(proj, 'resources', 'images'),
                 base_dir,
                 os.path.join(base_dir, 'images'),
                 proj]
    cands = []
    for r in roots:
        cands += [os.path.join(r, rel), os.path.join(r, base)]
        if rel.startswith('images/'):
            cands.append(os.path.join(r, rel[len('images/'):]))
    for c in cands:
        if os.path.isfile(c):
            return os.path.abspath(c)
    for c in cands:
        stem, ext = os.path.splitext(c)
        for alt in (stem + '.9' + ext, c + '.9.png'):
            if os.path.isfile(alt):
                return os.path.abspath(alt)
    return None


def pic_size(pic, base_dir=''):
    """图片真实像素尺寸（定位不到 / 不是图片 → None）。"""
    p = find_asset(pic, base_dir)
    if not p:
        return None
    try:
        from PIL import Image
        return Image.open(p).size
    except Exception:
        return None


def _inline_image(pic, base_dir='', max_kb=600):
    """图片引用 → data URI 内联（预览稿单文件独立显示）。找不到/过大 → None（保留原相对引用）。"""
    p = find_asset(pic, base_dir)
    if not p:
        return None
    try:
        if os.path.getsize(p) > max_kb * 1024:
            return None
        mime = _MIME.get(os.path.splitext(p)[1].lower(), 'image/png')
        import base64 as _b64
        with open(p, 'rb') as f:
            b = _b64.b64encode(f.read()).decode('ascii')
        return f'data:{mime};base64,' + b
    except Exception:
        return None


def _align_class(alignment):
    a = int(alignment or 0)
    cls = []
    if a & 16:
        cls.append('al-hc')
    if a & 32:
        cls.append('al-vc')
    if a & 1:
        cls.append('al-l')
    if a & 2:
        cls.append('al-r')
    return ' '.join(cls)


def _esc(s):
    return (s or '').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def _pos_style(pos):
    return (f"left:{pos.get('left', 0)}px;top:{pos.get('top', 0)}px;"
            f"width:{pos.get('width', 0)}px;height:{pos.get('height', 0)}px;")


def _text_of(ctrl):
    return ctrl.get('text') or ctrl.get('caption') or ''


def _bg_image(ctrl, field='backgroundPic', base_dir=''):
    pic = ctrl.get(field)
    if not pic:
        return ''
    uri = _inline_image(pic, base_dir)
    if uri:
        return (f"background-image:url('{uri}');"
                f"background-size:100% 100%;background-repeat:no-repeat;")
    return (f"background-image:url('{_esc(pic)}');"
            f"background-size:100% 100%;background-repeat:no-repeat;")


# ---------- 控件渲染 ----------
def _da(key, ctrl, ctype, edit=False):
    """data-* 标记（调试/可视化编辑器用）：data-key 便于定位控件、data-type 控件类型。"""
    cap = _esc(ctrl.get('caption', ''))
    cls = ' editable' if edit else ''
    vis = 'false' if ctrl.get('visible') is False else 'true'
    return (f'data-key="{key}" data-type="{ctype}" data-cap="{cap}" '
            f'data-visible="{vis}" data-edit="{cls.strip()}"')


# 属性面板可改字段（json 里 position 的四个分量）
POS_FIELDS = ('left', 'top', 'width', 'height')


def _render_control(key, ctrl, depth=0, base_dir='', edit=False):
    ctype = key.split('__')[0]
    pos = ctrl.get('position', {})
    style = _pos_style(pos)
    bg = _bg_image(ctrl, 'backgroundPic', base_dir)
    color = _color(ctrl.get('colorTab', {}).get('color0') if isinstance(ctrl.get('colorTab'), dict) else None)
    align = _align_class(ctrl.get('alignment'))
    visible = ctrl.get('visible', True)
    if not visible:
        style += 'display:none;'
    touchable = 'touchable' if ctrl.get('touchable') else ''
    cap = _esc(ctrl.get('caption', ''))

    if ctype == 'window':
        inner = []
        for k2, v2 in ctrl.items():
            if isinstance(v2, dict) and '__' in k2 and k2 != key:
                inner.append(_render_control(k2, v2, depth + 1, base_dir, edit))
        bgcolor = _color(ctrl.get('backgroundColor'))
        return (f'<div class="ctrl window {align}" data-caption="{cap}" '
                f'{_da(key, ctrl, ctype, edit)} '
                f'style="{style}background-color:{bgcolor};{bg}">' + ''.join(inner) + '</div>')

    if ctype == 'textview':
        txt = ctrl.get('text')
        label = _esc(txt) if txt else ''  # 空文本不显示 caption（图标 textview 不叠字）
        return (f'<div class="ctrl textview {align} {touchable}" data-caption="{cap}" '
                f'{_da(key, ctrl, ctype, edit)} '
                f'style="{style}color:{color};font-size:{ctrl.get("fontSize", 16)}px;{bg}">'
                f'{label}</div>')

    if ctype == 'button':
        pbg = ''
        ptab = ctrl.get('picTab') if isinstance(ctrl.get('picTab'), dict) else None
        if ptab:
            # 部分控件只填了非 0 状态图（如只给 pic2）→ 预览取第一个有值的状态，别显示空白
            p0 = ''
            for _k in ('pic0', 'pic1', 'pic2', 'pic3', 'pic4'):
                if ptab.get(_k):
                    p0 = ptab[_k]
                    break
            if p0:
                uri = _inline_image(p0, base_dir)
                ref = uri if uri else _esc(p0)
                pbg = (f"background-image:url('{ref}');"
                       f"background-size:100% 100%;background-repeat:no-repeat;")
        else:
            bct = ctrl.get('bgColorTab') if isinstance(ctrl.get('bgColorTab'), dict) else None
            if bct:
                pbg = f'background-color:{_color(bct.get("color0"))};'
        txt = ctrl.get('text')
        label = _esc(txt) if txt else ''  # 无文字不显示 caption；图片/热区按钮不叠字
        if not pbg:
            pbg = 'background-color:transparent;'  # 透明热区按钮：去掉 CSS 默认灰底，露出下层
        return (f'<div class="ctrl button {align} {touchable}" data-caption="{cap}" '
                f'{_da(key, ctrl, ctype, edit)} '
                f'style="{style}color:{color};font-size:{ctrl.get("fontSize", 18)}px;{pbg}">'
                f'{label}</div>')

    if ctype == 'seekbar':
        prog = ctrl.get('defProgress', 0)
        mx = ctrl.get('max', 100) or 1
        pct = min(100, max(0, int(prog) * 100 // mx))
        fill = _bg_image(ctrl, 'progressPic', base_dir)
        track = _bg_image(ctrl, 'backgroundPic', base_dir)
        return (f'<div class="ctrl seekbar" data-caption="{cap}" {_da(key, ctrl, ctype, edit)} '
                f'style="{style}{track}" '
                f'data-progress="{pct}"><div class="seekbar-fill" style="width:{pct}%;{fill}"></div></div>')

    if ctype == 'listview':
        cols = int(ctrl.get('cols', 1) or 1)
        rows = int(ctrl.get('rows', 1) or 1)
        item = ctrl.get('item', {})
        ipos = item.get('position', {})
        iw, ih = ipos.get('width', 100), ipos.get('height', 50)
        sub = []
        for si in item.get('subItem', []):
            si_style = (f"left:{si.get('position', {}).get('left', 0)}px;"
                        f"top:{si.get('position', {}).get('top', 0)}px;"
                        f"width:{si.get('position', {}).get('width', 40)}px;"
                        f"height:{si.get('position', {}).get('height', 20)}px;")
            sub.append(f'<div class="lv-sub" style="{si_style}">{_esc(si.get("text", ""))}</div>')
        cells = []
        for _r in range(min(rows, 8)):
            for _c in range(cols):
                cells.append(f'<div class="lv-cell" style="width:{iw}px;height:{ih}px;">{"".join(sub)}</div>')
        return (f'<div class="ctrl listview" data-caption="{cap}" {_da(key, ctrl, ctype, edit)} style="{style}">'
                f'<div class="lv-grid" style="grid-template-columns:repeat({cols}, {iw}px);'
                f'gap:{ctrl.get("colSpacing", 0)}px {ctrl.get("rowSpacing", 0)}px;">{"".join(cells)}</div></div>')

    if ctype == 'checkbox':
        checked = '☑' if ctrl.get('checked') else '☐'
        return (f'<div class="ctrl checkbox {align}" data-caption="{cap}" {_da(key, ctrl, ctype, edit)} '
                f'style="{style}color:{color};font-size:{ctrl.get("fontSize", 16)}px;">'
                f'{checked} {_esc(_text_of(ctrl))}</div>')

    if ctype == 'radiogroup':
        inner = []
        for rb in ctrl.get('radiobuttons', []):
            rp = rb.get('position', {})
            rstyle = (f"left:{rp.get('left', 0)}px;top:{rp.get('top', 0)}px;"
                      f"width:{rp.get('width', 60)}px;height:{rp.get('height', 24)}px;")
            rmark = '●' if rb.get('checked') else '○'
            inner.append(f'<div class="radio-item" style="{rstyle}">{rmark} {_esc(rb.get("text", ""))}</div>')
        return (f'<div class="ctrl radiogroup" data-caption="{cap}" {_da(key, ctrl, ctype, edit)} '
                f'style="{style}">{"".join(inner)}</div>')

    # 未知控件：兜底盒子
    return (f'<div class="ctrl {ctype}" data-caption="{cap}" {_da(key, ctrl, ctype, edit)} '
            f'style="{style}{bg}">{_esc(_text_of(ctrl))}</div>')


# ---------- 主转换 ----------
def _json_to_html(json_path, html_path, edit=False, extra_css='', extra_js='',
                  wrapper_open='', wrapper_close=''):
    with open(json_path, encoding='utf-8-sig') as f:
        data = json.load(f)
    res = data.get('resolution', {})
    W, H = res.get('width', 800), res.get('height', 480)
    bgcolor = _color(data.get('backgroundColor'), '#202020')

    body = []
    base_dir = os.path.dirname(os.path.abspath(json_path))
    for k, v in data.items():
        if isinstance(v, dict) and '__' in k:
            body.append(_render_control(k, v, base_dir=base_dir, edit=edit))

    html = f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<title>UI 预览 - {os.path.basename(json_path)}</title>
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ background:#2a2a2a; font-family:'Microsoft YaHei',sans-serif; padding:20px; }}
  .device {{ width:{W}px; height:{H}px; background:{bgcolor}; position:relative;
            margin:0 auto; border:2px solid #555; border-radius:6px; overflow:hidden;
            box-shadow:0 8px 30px rgba(0,0,0,.6); }}
  .ctrl {{ position:absolute; overflow:hidden; }}
  .textview {{ display:flex; align-items:center; }}
  .button {{ display:flex; align-items:center; justify-content:center; cursor:pointer;
            border-radius:4px; background:#3a3f4b; }}
  .button:hover {{ filter:brightness(1.3); }}
  .window {{ border:1px dashed rgba(255,255,255,.25); }}
  .al-hc {{ justify-content:center; text-align:center; }}
  .al-vc {{ align-items:center; }}
  .al-l {{ justify-content:flex-start; }}
  .al-r {{ justify-content:flex-end; }}
  .seekbar {{ background:#333; border-radius:3px; }}
  .seekbar-fill {{ height:100%; background:#4a90d9; border-radius:3px; }}
  .listview {{ border:1px dashed rgba(255,255,255,.2); overflow:auto; }}
  .lv-grid {{ display:grid; }}
  .lv-cell {{ border:1px solid rgba(255,255,255,.08); display:flex; }}
  .lv-sub {{ position:relative; }}
  .checkbox {{ display:flex; align-items:center; }}
  .radiogroup {{ position:absolute; }}
  .radio-item {{ position:absolute; color:#ddd; }}
  .toolbar {{ max-width:{W}px; margin:0 auto 12px; color:#ccc; font-size:13px;
             display:flex; justify-content:space-between; }}
  .toolbar span {{ color:#8f8; }}
{extra_css}
</style>
</head>
<body>
  <div class="toolbar">
    <div>🖥 UI 预览（客户确认稿）· <span>{os.path.basename(json_path)}</span></div>
    <div>分辨率 {W} x {H} · 与设备端 ftu 同源</div>
  </div>
  {wrapper_open}<div class="device">
{chr(10).join(body)}
  </div>{wrapper_close}
{extra_js}
</body>
</html>"""
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html)
    return W, H


# ---------- 对外工具 ----------
def json2html(target, output_dir=''):
    """target 为项目根目录或单个 json 文件路径。返回 {"success", "files": [...]}。"""
    if os.path.isdir(target):
        ui_dir = os.path.join(target, 'ui')
        if not os.path.isdir(ui_dir):
            return {"success": False, "error": f"ui 目录不存在: {ui_dir}"}
        out_dir = output_dir or ui_dir
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
        files = sorted(os.listdir(ui_dir))
        results = []
        for fn in files:
            if not fn.endswith('.json'):
                continue
            jp = os.path.join(ui_dir, fn)
            hp = os.path.join(out_dir, fn[:-5] + '.preview.html')
            try:
                W, H = _json_to_html(jp, hp)
                results.append({"json": fn, "html": hp, "resolution": f"{W}x{H}"})
            except Exception as e:
                results.append({"json": fn, "html": None, "error": str(e)})
        return {"success": all(r.get('html') for r in results), "files": results}
    elif os.path.isfile(target):
        out_dir = output_dir or os.path.dirname(os.path.abspath(target))
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
        hp = os.path.join(out_dir, os.path.splitext(os.path.basename(target))[0] + '.preview.html')
        try:
            W, H = _json_to_html(target, hp)
            return {"success": True, "files": [{"json": os.path.basename(target),
                                                "html": hp, "resolution": f"{W}x{H}"}]}
        except Exception as e:
            return {"success": False, "error": str(e)}
    return {"success": False, "error": f"路径不存在: {target}"}


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    if len(sys.argv) < 2:
        print('用法: python json2html.py <项目根目录或 json 文件> [输出目录]')
        sys.exit(1)
    out = sys.argv[2] if len(sys.argv) > 2 else ''
    r = json2html(sys.argv[1], out)
    print(json.dumps(r, ensure_ascii=False, indent=1))
    sys.exit(0 if r.get('success') else 1)
