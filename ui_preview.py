# -*- coding: utf-8 -*-
"""UI 布局 JSON → HTML 预览转换器。

将 ui/*.json 布局转换成自包含 HTML 预览页（客户确认 UI 交互用），
与 fui pack 生成的 ftu 互补：json 是中间文件，ftu 给设备执行，html 给客户预览。
"""
import base64, json, os, re

# ---------- 工具 ----------
def _color(intval, default='#888888'):
    """FlyThings colorTab.color0 int → #RRGGBB。"""
    try:
        v = int(intval)
        if v < 0 or v > 0xFFFFFF:
            return default
        return '#%06X' % v
    except Exception:
        return default


def _align_class(alignment):
    """alignment 位标志 → CSS 类。FlyThings: 1=左 2=右 4=上 8=下 16=水平居中 32=垂直居中。"""
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


# ---------- 控件渲染 ----------
def _render_control(key, ctrl, base_dir):
    ctype = key.split('__')[0]
    pos = ctrl.get('position', {})
    style = _pos_style(pos)
    bg = _bg_image(ctrl, base_dir)
    color = _color(ctrl.get('colorTab', {}).get('color0') if isinstance(ctrl.get('colorTab'), dict) else None)
    align = _align_class(ctrl.get('alignment'))
    visible = ctrl.get('visible', True)
    if not visible:
        style += 'display:none;'
    touchable = 'touchable' if ctrl.get('touchable') else ''

    if ctype == 'window':
        # 子窗口：容器，递归渲染内部控件
        inner = []
        for k2, v2 in ctrl.items():
            if isinstance(v2, dict) and '__' in k2 and k2 != key:
                inner.append(_render_control(k2, v2, base_dir))
        bgcolor = _color(ctrl.get('backgroundColor'))
        return (f'<div class="ctrl window {align}" data-caption="{_esc(ctrl.get("caption", ""))}" '
                f'style="{style}background-color:{bgcolor};{bg}">' + ''.join(inner) + '</div>')

    if ctype == 'textview':
        return (f'<div class="ctrl textview {align} {touchable}" data-caption="{_esc(ctrl.get("caption", ""))}" '
                f'style="{style}color:{color};font-size:{ctrl.get("fontSize", 16)}px;{bg}">'
                f'{_esc(_text_of(ctrl))}</div>')

    if ctype == 'button':
        # picTab 图片背景（pic0=normal, pic1=pressed）；无图时用默认灰底
        pbg = ''
        ptab = ctrl.get('picTab') if isinstance(ctrl.get('picTab'), dict) else None
        if ptab:
            p0 = ptab.get('pic0', '')
            if p0:
                pbg = f"background-image:url('{_esc(p0)}');background-size:100% 100%;background-repeat:no-repeat;"
        else:
            bct = ctrl.get('bgColorTab') if isinstance(ctrl.get('bgColorTab'), dict) else None
            if bct:
                pbg = f'background-color:{_color(bct.get("color0"))};'
        return (f'<div class="ctrl button {align} {touchable}" data-caption="{_esc(ctrl.get("caption", ""))}" '
                f'style="{style}color:{color};font-size:{ctrl.get("fontSize", 18)}px;{pbg}">'
                f'{_esc(_text_of(ctrl))}</div>')

    if ctype == 'seekbar':
        prog = ctrl.get('defProgress', 0)
        mx = ctrl.get('max', 100) or 1
        pct = min(100, max(0, int(prog) * 100 // mx))
        fill = _bg_image(ctrl, base_dir, 'progressPic')
        return (f'<div class="ctrl seekbar" data-caption="{_esc(ctrl.get("caption", ""))}" '
                f'style="{style}{_bg_image(ctrl, base_dir)}" data-progress="{pct}">'
                f'<div class="seekbar-fill" style="width:{pct}%;{fill}"></div></div>')

    if ctype == 'listview':
        # 网格：按 cols/rows 渲染 item 模板若干格
        cols = int(ctrl.get('cols', 1) or 1)
        rows = int(ctrl.get('rows', 1) or 1)
        item = ctrl.get('item', {})
        ipos = item.get('position', {})
        iw, ih = ipos.get('width', 100), ipos.get('height', 50)
        sub = []
        for k2, v2 in item.items():
            if isinstance(v2, dict) and 'subItem' in v2:
                for si in v2['subItem']:
                    sub.append(_render_control(f"sub_{si.get('caption','')}", si, base_dir))
        cells = []
        for r in range(min(rows, 8)):
            for c in range(cols):
                cells.append(f'<div class="lv-cell" style="width:{iw}px;height:{ih}px;">{"".join(sub)}</div>')
        return (f'<div class="ctrl listview" data-caption="{_esc(ctrl.get("caption", ""))}" '
                f'style="{style}"><div class="lv-grid" style="grid-template-columns:repeat({cols}, {iw}px);'
                f'gap:{ctrl.get("colSpacing", 0)}px {ctrl.get("rowSpacing", 0)}px;">{"".join(cells)}</div></div>')

    # 未知控件：兜底盒子
    return (f'<div class="ctrl {ctype}" data-caption="{_esc(ctrl.get("caption", ""))}" '
            f'style="{style}{bg}">{_esc(_text_of(ctrl))}</div>')


def _bg_image(ctrl, base_dir, field='backgroundPic'):
    """backgroundPic → 内联 CSS background。图片存在则引用相对路径，否则跳过。"""
    pic = ctrl.get(field)
    if not pic:
        return ''
    # 相对 ui 目录（html 也生成在 ui/ 下，路径直接可用）
    return f"background-image:url('{_esc(pic)}');background-size:100% 100%;background-repeat:no-repeat;"


# ---------- 主转换 ----------
def _json_to_html(json_path, html_path):
    with open(json_path, encoding='utf-8-sig') as f:
        data = json.load(f)
    res = data.get('resolution', {})
    W, H = res.get('width', 800), res.get('height', 480)
    base_dir = os.path.dirname(os.path.abspath(json_path))
    bgcolor = _color(data.get('backgroundColor'), '#202020')

    body = []
    for k, v in data.items():
        if isinstance(v, dict) and '__' in k:
            body.append(_render_control(k, v, base_dir))

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
  .lv-cell {{ border:1px solid rgba(255,255,255,.08); display:flex; flex-direction:column; }}
  .lv-cell .ctrl {{ position:relative; }}
  .toolbar {{ max-width:{W}px; margin:0 auto 12px; color:#ccc; font-size:13px;
             display:flex; justify-content:space-between; }}
  .toolbar span {{ color:#8f8; }}
</style>
</head>
<body>
  <div class="toolbar">
    <div>🖥 UI 预览（客户确认稿）· <span>{os.path.basename(json_path)}</span></div>
    <div>分辨率 {W} x {H} · 与设备端 ftu 同源</div>
  </div>
  <div class="device">
{chr(10).join(body)}
  </div>
</body>
</html>"""
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html)
    return W, H


# ---------- 对外工具 ----------
def flythings_generate_ui_preview(project_root, output_dir=''):
    """将项目 ui/*.json 布局生成 HTML 预览页（客户确认 UI 交互用）。

    用途：json 是中间文件 → fui pack 生成 ftu 给设备执行；本工具生成 html 给客户预览。
    每个 ui/*.json 生成同名 .preview.html（默认放 ui/ 目录，output_dir 可指定其他目录）。
    返回每个 json 对应的 html 路径、分辨率、控件数。
    """
    if not os.path.isdir(project_root):
        return {"success": False, "error": f"项目目录不存在: {project_root}"}
    ui_dir = os.path.join(project_root, 'ui')
    if not os.path.isdir(ui_dir):
        return {"success": False, "error": f"ui 目录不存在: {ui_dir}（先创建 ui/*.json 布局）"}
    if output_dir and not os.path.isdir(output_dir):
        try:
            os.makedirs(output_dir, exist_ok=True)
        except Exception as e:
            return {"success": False, "error": f"输出目录创建失败: {e}"}
    out_dir = output_dir or ui_dir

    results = []
    for fn in sorted(os.listdir(ui_dir)):
        if not fn.endswith('.json'):
            continue
        json_path = os.path.join(ui_dir, fn)
        html_path = os.path.join(out_dir, fn[:-5] + '.preview.html')
        try:
            W, H = _json_to_html(json_path, html_path)
            with open(json_path, encoding='utf-8-sig') as f:
                data = json.load(f)
            count = sum(1 for k, v in data.items() if isinstance(v, dict) and '__' in k)
            results.append({"json": fn, "html": html_path, "resolution": f"{W}x{H}",
                            "controls": count})
        except Exception as e:
            results.append({"json": fn, "html": None, "error": str(e)})
    ok = all(r.get('html') for r in results)
    return {"success": ok, "projectRoot": project_root, "outputDir": out_dir,
            "files": results, "note": "html 为客户预览稿；设备端仍用 fui pack 生成的 ftu，两者同源于 json"}


if __name__ == '__main__':
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    root = sys.argv[1] if len(sys.argv) > 1 else r'C:\Users\zkswe\.openclaw\workspace\projects\ElevatorDisplay'
    print(json.dumps(flythings_generate_ui_preview(root), ensure_ascii=False, indent=1))
