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

多页面（整屏 window + showWnd() 架构，v0.27.35）：
    json 里多个整屏 window、部分 visible=false 时，预览页顶部自动生成「页面切换条」：
      · 点页签 = 显示该整屏窗口、隐藏其余整屏窗口（默认页 = json 里首个 visible!=false 的整屏窗口）
      · 链接支持 hash 直达：xxx.preview.html#window__29（也认 #29 简写）
      · 「显示隐藏」勾选框：visible=false 的控件/窗口以 35% 透明 + 橙色虚线幽灵框叠显
        （与 flythings_ui_visual(action="editor") 的 ghost 行为对齐）
      · 左右方向键翻页；同一项目多个 json 时另有「项目页面」跳转行
"""
import base64, json, os, re, sys, time

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
    """FlyThings alignment(int) → CSS 对齐类（水平和垂直都显式给，不靠 CSS 缺省）。

位定义（设备实测校准：references/kb/controls.md 2026-08-29 + 2026-09-12 复核）：
      bit0-1 = 水平 0=左 1=中 2=右；bit2-3 = 垂直 0=顶 1=中 2=底；
      bit4/5（16/32）是引擎附加标志位，不影响对齐语义。
于是：36=左中 / 37=中中 / 38=右中 / 33=中顶 / 41=中底 / 40=左底 / 0=左顶。
    ⚠️ 旧实现把 bit0 当“靠左”、又忽略 bit2，导致 37（居中）被画成靠左、33/41 垂直方向丢失
    ——2026-09-12 需求方报的「edit.html 文字对齐显示不对」即此。
    """
    a = int(alignment or 0)
    h = {0: 'al-hl', 1: 'al-hc', 2: 'al-hr'}.get(a & 3, 'al-hl')
    v = {0: 'al-vt', 1: 'al-vc', 2: 'al-vb'}.get((a >> 2) & 3, 'al-vt')
    return h + ' ' + v


def _esc(s):
    return (s or '').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def _pos_style(pos):
    return (f"left:{pos.get('left', 0)}px;top:{pos.get('top', 0)}px;"
            f"width:{pos.get('width', 0)}px;height:{pos.get('height', 0)}px;")


def _text_of(ctrl):
    return ctrl.get('text') or ctrl.get('caption') or ''


# ---------- 多整屏窗口预览支持（v0.27.35）----------
# 背景：官方推荐的「整屏 window + showWnd() 切页」架构下，旧预览把所有 visible=false
# 的窗口都 display:none，客户确认稿只能看到首页 → 等于失效。
_SCREEN_TOL = 4          # 整屏判定容差（px）


def _screen_windows(data, W, H):
    """顶层整屏 window 列表 → [(key, caption, visible)]，用于生成页面切换条。
非数值 width/height 直接跳过（不抛错也不静默吞异常，无 except 站点）。"""
    out = []
    for k, v in data.items():
        if not (isinstance(v, dict) and '__' in k and k.split('__')[0] == 'window'):
            continue
        pos = v.get('position') or {}
        w, h = pos.get('width', 0), pos.get('height', 0)
        if isinstance(w, bool) or isinstance(h, bool):
            continue
        if not isinstance(w, (int, float)) or not isinstance(h, (int, float)):
            continue
        if w >= W - _SCREEN_TOL and h >= H - _SCREEN_TOL:
            out.append((k, v.get('caption') or '', v.get('visible', True) is not False))
    return out


def _hidden_count(data):
    """递归统计 visible=false 的控件数（决定是否给幽灵框开关）。"""
    n = 0

    def walk(o):
        nonlocal n
        if isinstance(o, dict):
            for k, v in o.items():
                if isinstance(v, dict) and '__' in k:
                    if v.get('visible') is False:
                        n += 1
                    walk(v)
    walk(data)
    return n


def _page_bar(pages, default_key, siblings, hidden_n, self_html='', json_name=''):
    """页面切换条 HTML（页签 + 幽灵框开关 + 项目内其它 json 跳转）。"""
    rows = []
    if len(pages) >= 2:
        btns, default_label = [], ''
        for key, cap, vis in pages:
            label = _esc(cap) or _esc(key)
            if key == default_key:
                default_label = label
            cls = 'pg-btn on' if key == default_key else 'pg-btn'
            if not vis:
                cls += ' off'
            btns.append(f'<a class="{cls}" href="#{key}" data-win="{key}" '
                        f'title="{_esc(key)}">{label}</a>')
        tip = '点页签切页 · 链接加 #window__N 可直达 · 左右方向键翻页'
        rows.append('<div class="pgnav" id="pg-nav">'
                    f'<span class="pg-label">页面 {len(pages)}</span>' + ''.join(btns) +
                    f'<span class="pg-tip">{tip}（默认页：{default_label}）</span>'
                    + (_ghost_toggle(hidden_n, inline=True) if hidden_n else '') +
                    '</div>')
    elif hidden_n:
        rows.append('<div class="pgnav" id="pg-nav">' + _ghost_toggle(hidden_n) + '</div>')
    if siblings and len(siblings) > 1:
        links = []
        for jn, hn in siblings:
            cls = 'pg-btn sib on' if hn == self_html else 'pg-btn sib'
            links.append(f'<a class="{cls}" href="{_esc(hn)}" title="{_esc(jn)}">'
                         f'{_esc(os.path.splitext(jn)[0])}</a>')
        rows.append('<div class="pgnav pgnav-sib"><span class="pg-label">项目页面</span>'
                    + ''.join(links) + '</div>')
    if not rows:
        return ''
    return '\n  '.join(rows)


def _ghost_toggle(hidden_n, inline=False):
    """幽灵框开关（visible=false 的控件 / 整屏窗口以 35% 虚线框叠显）。"""
    style = ' style="margin-left:auto;"' if inline else ''
    return (f'<label class="pg-ghost-toggle"{style}>'
            f'<input type="checkbox" id="pg-ghost"> 显示隐藏'
            f'<span class="pg-tip">（本 json 有 {hidden_n} 个 visible=false 控件）</span>'
            f'</label>')


# 多窗口预览所需 CSS（.pg-ghost 视觉与 ui_editor 的 .ed-ghost 对齐）
PREVIEW_CSS = """
  .pgnav { max-width:__W__px; margin:0 auto 8px; display:flex; flex-wrap:wrap; gap:6px;
           align-items:center; font-size:13px; color:#aaa; }
  .pgnav .pg-label { color:#8ab4f8; margin-right:2px; }
  .pgnav .pg-tip { color:#777; font-size:12px; }
  .pgnav a.pg-btn { color:#cfd6e4; text-decoration:none; background:#3a3f4b;
                    border:1px solid #555e70; border-radius:14px; padding:3px 12px; }
  .pgnav a.pg-btn:hover { filter:brightness(1.3); }
  .pgnav a.pg-btn.on { background:#4a90d9; border-color:#7ab6f0; color:#fff; }
  .pgnav a.pg-btn.off { opacity:.5; }
  .pgnav .pg-ghost-toggle { display:flex; align-items:center; gap:4px; cursor:pointer; }
  .ctrl.pg-ghost { opacity:.35 !important; outline:1px dashed #ff9f43 !important; }
"""


# 页面切换 / hash 直达 / 幽灵框逻辑（纯原生 JS，无依赖；默认页由 py 侧注入）
# 注：自带 <script> 标签，与 ui_editor 的 EDIT_JS 一致（模板直接拼 {extra_js}{pages_js}）
PREVIEW_JS = """
<script>
(function(){
  var dev=document.querySelector('.device');
  if(!dev) return;
  var all=Array.prototype.slice.call(dev.querySelectorAll('.ctrl[data-key]'));
  var W=dev.offsetWidth, H=dev.offsetHeight;
  var wins=all.filter(function(el){
    if(el.dataset.topwin!=='1') return false;
    var w=parseFloat(el.dataset.w||0), h=parseFloat(el.dataset.h||0);
    return w>=W-4 && h>=H-4;                 // 整屏窗口 = 页面
  });
  var nav=document.getElementById('pg-nav');
  var links=nav?Array.prototype.slice.call(nav.querySelectorAll('a[data-win]')):[];
  var box=document.getElementById('pg-ghost');
  var ghostOn=false, active='';
  function findWin(k){ for(var i=0;i<wins.length;i++){ if(wins[i].dataset.key===k) return wins[i]; } return null; }
  function pageOf(el){                        // 控件所属的整屏窗口
    var n=el;
    while(n && n!==dev){
      if(n.dataset && n.dataset.topwin==='1' && wins.indexOf(n)>=0) return n.dataset.key;
      n=n.parentElement;
    }
    return '';
  }
  function fromHash(){
    var h=location.hash.replace(/^#/,'');
    try{ h=decodeURIComponent(h); }catch(e){}
    if(!h) return '';
    if(findWin(h)) return h;
    if(/^[0-9]+$/.test(h) && findWin('window__'+h)) return 'window__'+h;
    return '';
  }
  function apply(){
    all.forEach(function(el){
      var hid=el.dataset.visible==='false';
      var isTopWin=el.dataset.topwin==='1' && wins.indexOf(el)>=0;
      var pg=pageOf(el), off;
      if(isTopWin){ off=(el.dataset.key!==active) && !ghostOn; }
      else if(pg && pg!==active){ off=!ghostOn; }
      else { off=hid && !ghostOn; }
      el.style.display=off?'none':'';
      if(ghostOn && (hid || (isTopWin && el.dataset.key!==active))){
        el.classList.add('pg-ghost');
      } else { el.classList.remove('pg-ghost'); }
    });
    links.forEach(function(a){ a.classList.toggle('on', a.dataset.win===active); });
  }
  function setActive(k, fromHash){
    if(!k && wins.length) return;
    active=k;
    apply();
    if(!fromHash && location.hash.replace(/^#/,'')!==k){ location.hash=k; }
  }
  active=fromHash() || __DEFAULT_WIN__;   // 默认页（py 侧注入 JS 字面量）
  apply();
  links.forEach(function(a){
    a.addEventListener('click', function(e){ e.preventDefault(); setActive(a.dataset.win,false); });
  });
  window.addEventListener('hashchange', function(){ var k=fromHash(); if(k) setActive(k,true); });
  if(box){ box.addEventListener('change', function(){ ghostOn=box.checked; apply(); }); }
  document.addEventListener('keydown', function(e){
    if(!wins.length || (e.key!=='ArrowLeft' && e.key!=='ArrowRight')) return;
    var keys=wins.map(function(w){ return w.dataset.key; });
    var i=keys.indexOf(active), n=keys.length;
    var j=(e.key==='ArrowRight')?(i+1+n)%n:(i-1+n)%n;
    setActive(keys[j],false);
  });
})();
</script>
"""


# ---------- 客户确认稿模式（for_customer，2026-09-30）----------
# 与工程预览的区别：**给需求方/客户看**，不是给工程师拖。
#   ① 单文件、图片已 base64 内联，手机可直接打开/转发；
#   ② 默认隐藏 window 虚线框等"工程感"装饰；
#   ③ 「标注」开关：每个控件叠一个编号框 + `key · 宽x高 @(left,top)`（客户能指到具体控件）；
#   ④ 窄屏（手机）自动等比缩放适配；
#   ⑤ 顶部带项目名/分辨率/页数/控件数/生成时间，便于留档比对。
CUSTOMER_CSS = """
  body.customer { background:#1b1b1b; }
  body.customer .window { border:none; }
  .cbar { max-width:__W__px; margin:0 auto 10px; color:#ddd; font-size:13px;
          display:flex; flex-wrap:wrap; gap:8px; align-items:center; }
  .cbar button { background:#3a3f4b; color:#eee; border:1px solid #555;
                 border-radius:4px; padding:4px 10px; cursor:pointer; font-size:12px; }
  .cbar button.on { background:#2f6d3a; border-color:#3f8f4d; }
  .cbar .meta { color:#9aa; }
  #annotate-layer { position:absolute; left:0; top:0; right:0; bottom:0;
                    pointer-events:none; display:none; z-index:60; }
  body.annotate #annotate-layer { display:block; }
  #annotate-layer .abox { position:absolute; border:1px dashed #ffd24a;
                          background:rgba(255,210,74,.06); }
  #annotate-layer .atag { position:absolute; font:11px/1.35 'Microsoft YaHei',sans-serif;
                          color:#1b1b1b; background:#ffd24a; padding:1px 4px;
                          border-radius:3px; white-space:nowrap; }
"""

CUSTOMER_JS = """
<script>
(function(){
  document.body.classList.add('customer');
  var dev = document.querySelector('.device');
  if (!dev) { return; }
  var bar = document.createElement('div');
  bar.className = 'cbar';
  bar.innerHTML = '<button id="btn-an">标注 控件名/尺寸</button>'
                + '<button id="btn-fit">适应屏幕</button>'
                + '<span class="meta">__META__</span>';
  dev.parentNode.insertBefore(bar, dev.parentNode.firstChild);
  var layer = document.createElement('div');
  layer.id = 'annotate-layer';
  dev.appendChild(layer);
  var nodes = dev.querySelectorAll('.ctrl[data-key]');
  for (var i = 0; i < nodes.length; i++) {
    var el = nodes[i];
    if (el.dataset.visible === 'false' || el.offsetParent === null) { continue; }
    var box = document.createElement('div');
    box.className = 'abox';
    box.style.left = el.offsetLeft + 'px';  box.style.top = el.offsetTop + 'px';
    box.style.width = el.offsetWidth + 'px'; box.style.height = el.offsetHeight + 'px';
    var tag = document.createElement('div');
    tag.className = 'atag';
    tag.textContent = (i + 1) + '. ' + el.dataset.key + '  ' + el.offsetWidth + 'x'
                    + el.offsetHeight + ' @(' + el.offsetLeft + ',' + el.offsetTop + ')';
    tag.style.left = el.offsetLeft + 'px';
    tag.style.top = Math.max(el.offsetTop - 15, 0) + 'px';
    layer.appendChild(box); layer.appendChild(tag);
  }
  document.getElementById('btn-an').onclick = function(){
    document.body.classList.toggle('annotate');
    this.classList.toggle('on');
  };
  document.getElementById('btn-fit').onclick = function(){
    var w = dev.offsetWidth || 1, vw = document.documentElement.clientWidth - 40;
    var s = vw < w ? (vw / w) : 1;
    dev.style.transform = s < 1 ? 'scale(' + s.toFixed(3) + ')' : 'none';
    dev.style.transformOrigin = 'top left';
  };
})();
</script>
"""


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
    align = _align_class(ctrl.get('alignment')) if 'alignment' in ctrl else ''
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
        # 顶层窗口（depth==0）标记为页面候选，多整屏 window 架构下预览页靠它切页
        top = (f'data-topwin="1" data-w="{pos.get("width", 0)}" '
               f'data-h="{pos.get("height", 0)}" ') if depth == 0 else ''
        return (f'<div class="ctrl window {align}" data-caption="{cap}" '
                f'{top}{_da(key, ctrl, ctype, edit)} '
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

    if ctype in ('scrollwindow', 'pagewindow'):
        # 只装 window（层级铁律）；**必须递归渲染子控件**，否则确认稿只剩容器壳、看不到滑动区内容
        inner = []
        for k2, v2 in ctrl.items():
            if isinstance(v2, dict) and '__' in k2 and k2 != key:
                inner.append(_render_control(k2, v2, depth + 1, base_dir, edit))
        # 视口裁剪由 .ctrl 的 overflow:hidden 提供（与引擎一致：内层 window 可高于视口，多出的部分被裁掉）
        return (f'<div class="ctrl {ctype} {align}" data-caption="{cap}" '
                f'{_da(key, ctrl, ctype, edit)} '
                f'style="{style}">' + ''.join(inner) + '</div>')

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
                  wrapper_open='', wrapper_close='', siblings=None, customer=False):
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

    # ---- 多整屏窗口：页面切换条 + hash 直达 + 幽灵框开关（v0.27.35）----
    pages_bar, pages_css, pages_js = '', '', ''
    if not edit:
        pages = _screen_windows(data, W, H)
        hidden_n = _hidden_count(data)
        default_key = next((k for k, _c, vis in pages if vis),
                           pages[0][0] if pages else '')
        if len(pages) >= 2 or hidden_n or (siblings and len(siblings) > 1):
            pages_bar = _page_bar(pages, default_key, siblings, hidden_n,
                                  self_html=os.path.basename(html_path),
                                  json_name=os.path.basename(json_path))
            pages_js = PREVIEW_JS.replace('__DEFAULT_WIN__', json.dumps(default_key))
        if pages_bar:
            pages_css = PREVIEW_CSS.replace('__W__', str(W))

    # ---- 客户确认稿（for_customer）：窄屏适配 + 标注层 + 留档抬头 ----
    viewport, bar = '', ''
    if customer:
        meta = ('%s · 分辨率 %d x %d · 控件 %d 个 · 生成 %s'
                % (os.path.basename(json_path), W, H, len(body),
                   time.strftime('%Y-%m-%d %H:%M')))
        extra_css += CUSTOMER_CSS.replace('__W__', str(W))
        extra_js = CUSTOMER_JS.replace('__META__', _esc(meta)) + extra_js
        viewport = '<meta name="viewport" content="width=device-width,initial-scale=1">\n'

    html = f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">{viewport}
<title>{'UI 确认稿' if customer else 'UI 预览'} - {os.path.basename(json_path)}</title>
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ background:#2a2a2a; font-family:'Microsoft YaHei',sans-serif; padding:20px; }}
  .device {{ width:{W}px; height:{H}px; background:{bgcolor}; position:relative;
            margin:0 auto; border:2px solid #555; border-radius:6px; overflow:hidden;
            box-shadow:0 8px 30px rgba(0,0,0,.6); }}
  .ctrl {{ position:absolute; overflow:hidden; }}
  .textview {{ display:flex; align-items:flex-start; }}
  .button {{ display:flex; align-items:center; justify-content:center; cursor:pointer;
            border-radius:4px; background:#3a3f4b; }}
  .button:hover {{ filter:brightness(1.3); }}
  .window {{ border:1px dashed rgba(255,255,255,.25); }}
  /* alignment 十进制位 → 对齐类：bit0-1 水平(0左1中2右) / bit2-3 垂直(0顶1中2底)；
写全 H+V 两类，避免 .button 的默认居中把 36/33/41 之类画错 */
  .al-hl {{ justify-content:flex-start; text-align:left; }}
  .al-hc {{ justify-content:center; text-align:center; }}
  .al-hr {{ justify-content:flex-end; text-align:right; }}
  .al-vt {{ align-items:flex-start; }}
  .al-vc {{ align-items:center; }}
  .al-vb {{ align-items:flex-end; }}
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
{extra_css}{pages_css}
</style>
</head>
<body>
  <div class="toolbar">
    <div>🖥 {'UI 确认稿（给需求方看，单文件可转发）' if customer else 'UI 预览（客户确认稿）'} · <span>{os.path.basename(json_path)}</span></div>
    <div>分辨率 {W} x {H} · 与设备端 ftu 同源</div>
  </div>
  {pages_bar}
  {wrapper_open}<div class="device">
{chr(10).join(body)}
  </div>{wrapper_close}
{extra_js}{pages_js}
</body>
</html>"""
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html)
    return W, H


# ---------- 对外工具 ----------
def _siblings_of(ui_dir, out_dir, files):
    """同目录其它 json → 预览页跳转用 [(json 名, html 名)]（同项目多 json 分页架构）。"""
    out = []
    for fn in files:
        if fn.endswith('.json'):
            out.append((fn, fn[:-5] + '.preview.html'))
    return out


def _ui_json_pages(ui_dir):
    """ui 布局 json 清单：同时支持 ui/*.json 与 ui/<分辨率>/*.json（工程布局不一致）。

原实现只 listdir(ui) 顶层 → 分层工程（如基准 SampleUI-New 的 ui/1024x600/*.json）
会得到 0 页，预览静默出空列表（v0.27.36 修，与 check_all._ui_pages 同一口径）。
返回 [(相对路径, 绝对路径)]，按相对路径排序。
    """
    out = []
    for name in sorted(os.listdir(ui_dir)):
        p = os.path.join(ui_dir, name)
        if name.endswith('.json') and os.path.isfile(p):
            out.append((name, p))
        elif os.path.isdir(p):
            for sub in sorted(os.listdir(p)):
                sp = os.path.join(p, sub)
                if sub.endswith('.json') and os.path.isfile(sp):
                    out.append((name + '/' + sub, sp))
    return out


def json2html(target, output_dir='', for_customer=False):
    """target 为项目根目录或单个 json 文件路径；for_customer=True 出「客户确认稿」（.confirm.html）。
返回 {"success", "files": [...]}。"""
    suffix = '.confirm.html' if for_customer else '.preview.html'
    if os.path.isdir(target):
        ui_dir = os.path.join(target, 'ui')
        if not os.path.isdir(ui_dir):
            return {"success": False, "error": f"ui 目录不存在: {ui_dir}"}
        out_dir = output_dir or ui_dir
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
        results = []
        for rel, jp in _ui_json_pages(ui_dir):
            sub = os.path.dirname(rel)                     # '' 或 '1024x600'
            odir = os.path.join(out_dir, sub) if sub else out_dir
            os.makedirs(odir, exist_ok=True)
            base = os.path.basename(rel)
            # 兄弟页只在同一个目录内互链（不同分辨率的 json 不串页）
            siblings = [os.path.basename(x) for x, _ in _ui_json_pages(os.path.dirname(jp))]
            sibs = _siblings_of(os.path.dirname(jp), odir, siblings)
            hp = os.path.join(odir, base[:-5] + suffix)
            try:
                W, H = _json_to_html(jp, hp, siblings=sibs, customer=for_customer)
                results.append({"json": rel, "html": hp, "resolution": f"{W}x{H}"})
            except Exception as e:
                results.append({"json": rel, "html": None, "error": str(e)})
        return {"success": bool(results) and all(r.get('html') for r in results),
                "files": results}
    elif os.path.isfile(target):
        out_dir = output_dir or os.path.dirname(os.path.abspath(target))
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
        hp = os.path.join(out_dir, os.path.splitext(os.path.basename(target))[0] + suffix)
    # 单文件模式：只链同目录已有同名 .preview.html 的邻居，避免死链接
        sibs = []
        jdir = os.path.dirname(os.path.abspath(target))
        if os.path.isdir(jdir):
            for fn in sorted(os.listdir(jdir)):
                if not fn.endswith('.json'):
                    continue
                cand = os.path.join(out_dir, fn[:-5] + '.preview.html')
                if fn == os.path.basename(target) or os.path.isfile(cand):
                    sibs.append((fn, fn[:-5] + '.preview.html'))
        try:
            W, H = _json_to_html(target, hp, siblings=sibs, customer=for_customer)
            return {"success": True, "files": [{"json": os.path.basename(target),
                                                "html": hp, "resolution": f"{W}x{H}"}]}
        except Exception as e:
            return {"success": False, "error": str(e)}
    return {"success": False, "error": f"路径不存在: {target}"}


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    if len(sys.argv) < 2:
        print('用法: python json2html.py <项目根目录或 json 文件> [输出目录] [--customer]')
        sys.exit(1)
    argv = [a for a in sys.argv[1:] if a != '--customer']
    cust = '--customer' in sys.argv
    out = argv[1] if len(argv) > 1 else ''
    r = json2html(argv[0], out, for_customer=cust)
    print(json.dumps(r, ensure_ascii=False, indent=1))
    sys.exit(0 if r.get('success') else 1)
