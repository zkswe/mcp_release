#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""JSON 布局可视化编辑器（拖控件 / 改大小 → 导出变更 JSON → 打回 json → pack ftu）

为什么是它：手写 HTML 预览是「第二份真相」，跟设备必然漂移；本工具在 json 渲染出的
预览页上直接拖拽，改完导出的是**坐标变更**，写回 ui/*.json 后 pack 成 ftu，
预览与设备同源，沟通成本 = 0（不用描述"往左一点"，直接拖）。

生成的是单文件 HTML（图片 base64 内联），双击即可用，无需搭环境：
    python tools/ui_tools/ui_editor.py <项目根或 json 文件> [输出 HTML]

页面操作：
    · 单击控件选中，拖动移动，8 个手柄改大小
    · 方向键微调 1px（Shift 加速 10px，网格可切 1/2/5/10）
    · Ctrl+Z 撤销 / Ctrl+Y 重做
    · 右侧面板列出所有改动（前值→新值）
    · 「复制变更 JSON」→ 粘到对话里即可，或「下载变更 JSON」存文件
写回：
    python tools/ui_tools/ui_edit_apply.py <变更JSON> --project <项目根> [--pack]

内置校验（省得来回沟通）：
    · 图片尺寸 ≠ 控件尺寸 → 红标（FlyThings 普通 PNG 不缩放，这是"切图不对"的根因）
    · 文本超出控件估算尺寸 → 黄标（设备端会裁字/换行）
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import json2html as J2H  # noqa: E402


# ---------- 图片资源收集（预览显图 + "切图不对"预检）----------
_PIC_KEY_RE = re.compile(r'pic|image', re.I)


def _collect_pics(data, base_dir):
    """递归收集 json 里所有图片引用 → {引用字符串: (w,h) 或 None}。
    用 J2H.find_asset 定位（支持 audio/horn.png 这类带子目录的相对 resources 路径）。"""
    found = {}

    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if isinstance(v, str) and _PIC_KEY_RE.search(str(k)) and v.strip():
                    if v not in found:
                        found[v] = J2H.pic_size(v, base_dir)
                elif isinstance(v, (dict, list)):
                    walk(v)
        elif isinstance(o, list):
            for x in o:
                walk(x)

    walk(data)
    return found


def _iter_controls(data, base_dir, parent=''):
    """递归遍历控件，yield (path, key, ctrl)。"""
    for k, v in data.items():
        if not (isinstance(v, dict) and '__' in k):
            continue
        path = f'{parent}/{k}' if parent else k
        yield path, k, v
        yield from _iter_controls(v, base_dir, path)


def _is_transparent(path):
    """全透明占位图（transparency.png 类）会被故意拉伸，不算尺寸不匹配。"""
    try:
        from PIL import Image
        im = Image.open(path).convert('RGBA')
        return im.getchannel('A').getextrema()[1] == 0
    except Exception:
        return False


def _preflight(data, base_dir, pics=None):
    """图片尺寸/文本溢出预检 → [(path, caption, level, msg)]；pics = {引用: (w,h)}。
    只校验「按控件尺寸画」的图（backgroundPic / picTab.picN）；thumb/progressPic/
    charsetTab 等自有尺寸的图不参与（避开假警报）。"""
    pics = pics or _collect_pics(data, base_dir)
    out = []
    for path, key, ctrl in _iter_controls(data, base_dir):
        pos = ctrl.get('position') or {}
        w, h = pos.get('width'), pos.get('height')
        ctype = key.split('__')[0]
        refs = []
        if isinstance(ctrl.get('backgroundPic'), str) and ctrl['backgroundPic'].strip():
            refs.append(('backgroundPic', ctrl['backgroundPic']))
        pt = ctrl.get('picTab')
        if isinstance(pt, dict):
            for k2 in ('pic0', 'pic1', 'pic2', 'pic3', 'pic4'):
                if isinstance(pt.get(k2), str) and pt[k2].strip():
                    refs.append((f'picTab.{k2}', pt[k2]))
        for field, pic in refs:
            sz = pics.get(pic)
            if sz is None:
                continue
            real = J2H.find_asset(pic, base_dir) or ''
            if real.endswith('.9.png') or not w or not h:
                continue                      # 九宫格图本来就要拉伸
            if sz[0] == w and sz[1] == h:
                continue
            if sz[0] > w or sz[1] > h:
                out.append((path, ctrl.get('caption', ''), 'error',
                            f'{field} 图 {sz[0]}x{sz[1]} > 控件 {w}x{h}'
                            '（设备不缩放普通 PNG，会裁切/错位）'))
            elif w > 100 and h > 100 and not _is_transparent(real):
                out.append((path, ctrl.get('caption', ''), 'warn',
                            f'{field} 图 {sz[0]}x{sz[1]} < 控件 {w}x{h}（大控件配小图，会留边/拉糊）'))
        # 文本溢出：粗估（CJK 1.0em / ASCII 0.55em）。阈值放宽到 1.35 倍，
        # 宁可漏报不误报——SampleUI-New 基准工程零告警是校准目标（2026-09-10）。
        if ctype in ('textview', 'button') and not ctrl.get('rollEnable'):
            txt = ctrl.get('text') or ''
            fs = int(ctrl.get('fontSize') or 16)
            if txt and w:
                est_w = sum(1.0 if ord(c) > 0x2000 else 0.55 for c in txt) * fs
                if est_w > w * 1.35:
                    out.append((path, ctrl.get('caption', ''), 'warn',
                                f'文本估算 {int(est_w)}px 宽，明显超控件 {w}px（设备端可能裁字，建议核对）'))
                if fs > (h or 0):
                    out.append((path, ctrl.get('caption', ''), 'warn',
                                f'字号 {fs} > 控件高 {h}px（设备端会裁字）'))
    return out


# ---------- 编辑器前端 ----------
EDIT_CSS = """
  /* ===== 可视化编辑器（ui_editor）===== */
  body.ed { padding: 12px 12px 20px; }
  .ed-wrap { display:flex; gap:14px; justify-content:center; align-items:flex-start; }
  .ed-stage { position:relative; }
  .ed-overlay { position:absolute; inset:0; pointer-events:none; z-index:9999; }
  .ed-sel { position:absolute; border:1px dashed #2ee6a8; pointer-events:none;
            box-sizing:border-box; }
  .ed-tag { position:absolute; left:-1px; top:-18px; background:#2ee6a8; color:#062;
            font:11px/16px monospace; padding:0 4px; white-space:nowrap; border-radius:2px; }
  .ed-h { position:absolute; width:9px; height:9px; margin:-5px 0 0 -5px; background:#2ee6a8;
          border:1px solid #053; pointer-events:auto; }
  .ed-h.nw{left:0;top:0;cursor:nwse-resize} .ed-h.n {left:50%;top:0;cursor:ns-resize}
  .ed-h.ne{left:100%;top:0;cursor:nesw-resize} .ed-h.e{left:100%;top:50%;cursor:ew-resize}
  .ed-h.se{left:100%;top:100%;cursor:nwse-resize} .ed-h.s{left:50%;top:100%;cursor:ns-resize}
  .ed-h.sw{left:0;top:100%;cursor:nesw-resize} .ed-h.w{left:0;top:50%;cursor:ew-resize}
  .ed-bad { position:absolute; z-index:10000; pointer-events:none; font:11px/15px monospace;
            padding:0 3px; color:#fff; }
  .ed-bad.error { background:rgba(220,40,40,.92); }
  .ed-bad.warn { background:rgba(220,150,0,.92); color:#221; }
  .ed-panel { width:340px; color:#ddd; font-size:13px; }
  .ed-panel h3 { font-size:14px; margin:0 0 8px; color:#2ee6a8; }
  .ed-bar { display:flex; flex-wrap:wrap; gap:6px; align-items:center; margin-bottom:8px; }
  .ed-bar button { background:#3a3f4b; color:#eee; border:1px solid #555; border-radius:4px;
                   padding:4px 9px; cursor:pointer; font-size:12px; }
  .ed-bar button:hover { background:#4a5162; }
  .ed-bar button.pri { background:#1b7f5f; border-color:#2ee6a8; }
  .ed-bar label { font-size:12px; color:#aaa; }
  .ed-list { max-height:300px; overflow:auto; background:#21242b; border:1px solid #383c46;
             border-radius:4px; padding:6px; font:12px/1.6 monospace; }
  .ed-list .row { border-bottom:1px dashed #333; padding:2px 0; }
  .ed-list .k { color:#7fd7ff; }
  .ed-list .v { color:#f0c674; }
  .ed-issues { max-height:220px; overflow:auto; background:#21242b; border:1px solid #383c46;
               border-radius:4px; padding:6px; font:12px/1.6 monospace; margin-top:8px; }
  .ed-issues .error { color:#ff7b7b; }
  .ed-issues .warn { color:#ffc46b; }
  textarea.ed-out { width:100%; height:150px; background:#191c22; color:#9fe8c8; border:1px solid #383c46;
                    border-radius:4px; font:11px/1.45 monospace; margin-top:8px; }
  .ed-hint { color:#8a8f9a; font-size:11px; margin-top:6px; line-height:1.6; }
  .ed-toggles { display:flex; gap:10px; font-size:12px; color:#aaa; margin-top:6px; flex-wrap:wrap; }
  /* ===== 指哪打哪：悬停高亮 / 遮罩穿透 / 属性输入 / 控件列表 ===== */
  .ctrl.ed-hover { outline:1px solid #4ac1ff; outline-offset:0; }
  .ctrl.ed-ghost { opacity:.35 !important; outline:1px dashed #ff9f43 !important; }
  .ed-move { position:absolute; left:0; top:0; width:15px; height:15px; z-index:10001;
             pointer-events:auto; cursor:move; background:#2ee6a8; border:1px solid #053;
             border-radius:2px; color:#053; font:bold 11px/13px monospace; text-align:center;
             user-select:none; }
  .ed-prop { display:grid; grid-template-columns:34px 1fr 44px 1fr; gap:5px 6px;
             align-items:center; font:12px monospace; color:#aaa; }
  .ed-prop input { width:100%; background:#191c22; color:#9fe8c8; border:1px solid #383c46;
                   border-radius:3px; padding:3px 5px; font:12px monospace; }
  .ed-tree { background:#21242b; border:1px solid #383c46; border-radius:4px; padding:4px;
             max-height:200px; overflow:auto; }
  .ed-tree input.search { width:100%; margin-bottom:4px; background:#191c22; color:#9fe8c8;
                          border:1px solid #383c46; border-radius:3px; padding:3px 5px; font:12px monospace; }
  .ed-tree .n { cursor:pointer; padding:1px 4px; border-radius:2px; white-space:nowrap;
                overflow:hidden; text-overflow:ellipsis; font:11px/1.55 monospace; color:#c8ccd4; }
  .ed-tree .n:hover { background:#2e3440; }
  .ed-tree .n.sel { background:#1b7f5f; color:#fff; }
  .ed-tree .n.hid { color:#8a8f9a; }
  .ed-tree .n .z { color:#6b7280; }
  /* ===== 属性编辑（文字/颜色/图片/可见…全部可改）===== */
  .ed-fields { background:#21242b; border:1px solid #383c46; border-radius:4px; padding:5px;
               max-height:280px; overflow:auto; font:12px monospace; color:#8a8f9a; }
  .ed-frow { display:grid; grid-template-columns:104px 1fr; gap:4px 6px; align-items:center;
             padding:1px 0; }
  .ed-frow label { color:#9aa3b2; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .ed-frow input[type=text], .ed-frow input[type=number], .ed-frow textarea {
    width:100%; background:#191c22; color:#9fe8c8; border:1px solid #383c46; border-radius:3px;
    padding:2px 4px; font:12px monospace; }
  .ed-frow textarea { height:48px; resize:vertical; }
  .ed-frow input[type=color] { width:100%; height:20px; padding:0; border:1px solid #383c46;
                               background:#191c22; }
  .ed-frow.grp { color:#7fd7ff; border-top:1px dashed #333; margin-top:4px; padding-top:3px; }
  .ed-fsub { padding-left:8px; }
  .ed-list .p { color:#9aa3b2; }
"""

EDIT_JS = r"""
<script>
(function(){
  var META = __META__;
  var device = document.querySelector('.device');
  if(!device) return;
  document.body.classList.add('ed');
  var ASSETS = META.assets || {};

  // ---------- 覆盖层：选中框 + 手柄 + 移动块 ----------
  var ov = document.createElement('div'); ov.className='ed-overlay'; device.appendChild(ov);
  var selBox = document.createElement('div'); selBox.className='ed-sel'; selBox.style.display='none';
  var selTag = document.createElement('div'); selTag.className='ed-tag'; selBox.appendChild(selTag);
  var moveH = document.createElement('div'); moveH.className='ed-move';
  moveH.title='拖动移动（遮罩下层也能拖）'; moveH.textContent='✥'; selBox.appendChild(moveH);
  ['nw','n','ne','e','se','s','sw','w'].forEach(function(d){
    var h=document.createElement('div'); h.className='ed-h '+d; h.dataset.d=d; selBox.appendChild(h);
  });
  ov.appendChild(selBox);

  // ---------- 右侧面板 ----------
  var panel = document.createElement('div'); panel.className='ed-panel';
  panel.innerHTML = '<h3>布局调整（指哪打哪）</h3>' +
    '<div class="ed-bar">' +
      '<button data-a="undo">撤销</button><button data-a="redo">重做</button>' +
      '<label>网格 <select data-a="grid"><option>1</option><option>2</option>' +
      '<option>5</option><option>10</option></select>px</label>' +
      '<label><input type="checkbox" data-a="boxes" checked> 框线</label>' +
      '<label><input type="checkbox" data-a="dims"> 尺寸</label>' +
      '<label><input type="checkbox" data-a="ghost"> 显示隐藏</label>' +
      '<label><input type="checkbox" data-a="issues" checked> 问题</label>' +
    '</div>' +
    '<h3>几何 <span id="ed-cap" style="color:#f0c674;font-size:12px"></span></h3>' +
    '<div class="ed-prop" id="ed-prop"></div>' +
    '<div class="ed-hint" id="ed-info">未选中控件（点画布里的控件，或用下面列表选）</div>' +
    '<h3>属性 <span id="ed-fc" style="color:#8a8f9a;font-size:12px"></span></h3>' +
    '<div class="ed-fields" id="ed-fields">（选中控件后显示）</div>' +
    '<h3>控件列表 <span id="ed-tc" style="color:#8a8f9a;font-size:12px"></span></h3>' +
    '<div class="ed-tree"><input class="search" id="ed-search" placeholder="搜 key / caption，点一行即选中">' +
    '<div id="ed-tree-body"></div></div>' +
    '<h3>改动清单 <span id="ed-cnt">0</span> 处</h3><div class="ed-list" id="ed-list">（未改动）</div>' +
    '<div class="ed-bar" style="margin-top:8px">' +
      '<button class="pri" data-a="copy">复制变更 JSON</button>' +
      '<button data-a="dl">下载变更 JSON</button>' +
      '<button data-a="dlfull">下载完整 json</button>' +
      '<button data-a="reset">还原</button>' +
    '</div>' +
    '<h3>预检问题 <span id="ed-ic">0</span> 条</h3><div class="ed-issues" id="ed-issues"></div>' +
    '<textarea class="ed-out" id="ed-out" readonly placeholder="点「复制变更 JSON」，或直接粘到聊天里"></textarea>' +
    '<div class="ed-hint">点控件=选中 · 拖动=移动 · 拖左上绿块=移动（被遮罩压住也能拖）· ' +
    'Alt+点=穿透选中下层 · 几何/属性都能直接改（改文字即时生效）· 方向键 1px · Ctrl+Z 撤销</div>';
  document.querySelector('.ed-wrap').appendChild(panel);

  var grid=1, sel=null, changes={}, props={}, undoStack=[], redoStack=[], originals={}, ghostOn=false;
  var all = Array.prototype.slice.call(device.querySelectorAll('.ctrl[data-key]'));
  var issues = META.issues || [];
  var CTRL = META.controls || {};

  function pathOf(el){
    var parts=[], n=el;
    while(n && n!==device){ if(n.dataset && n.dataset.key) parts.unshift(n.dataset.key); n=n.parentElement; }
    return parts.join('/');
  }
  function byPath(p){ var r=null; all.forEach(function(c){ if(c.dataset.path===p) r=c; }); return r; }
  all.forEach(function(el){
    var p=pathOf(el), s=el.style;
    el.dataset.path=p;
    originals[p]={left:parseInt(s.left)||0, top:parseInt(s.top)||0,
                  width:parseInt(s.width)||0, height:parseInt(s.height)||0};
  });
  function geom(el){ var s=el.style;
    return {left:parseInt(s.left)||0, top:parseInt(s.top)||0,
            width:parseInt(s.width)||0, height:parseInt(s.height)||0}; }
  function setGeom(el,g){ var s=el.style;
    s.left=g.left+'px'; s.top=g.top+'px'; s.width=g.width+'px'; s.height=g.height+'px'; }
  function relPos(el){ var x=0,y=0,n=el;
    while(n && n!==device){ x+=n.offsetLeft; y+=n.offsetTop; n=n.offsetParent; }
    return {x:x,y:y}; }
  function parentBox(el){ var p=el.offsetParent||device;
    return {w:p.clientWidth||p.offsetWidth, h:p.clientHeight||p.offsetHeight}; }
  function clamp(g,el){ var pb=parentBox(el);
    g.width=Math.max(1,g.width); g.height=Math.max(1,g.height);
    g.left=Math.max(0,Math.min(pb.w-g.width,g.left));
    g.top =Math.max(0,Math.min(pb.h-g.height,g.top)); return g; }
  function snapv(v, noSnap){ return noSnap? Math.round(v) : Math.round(v/grid)*grid; }
  function int2hex(v){ v=(v===null||v===undefined)?0:v; if(v<0) v=0x1000000+v;
    return '#'+('000000'+(v>>>0).toString(16)).slice(-6); }
  function hex2int(h){ return parseInt(h.replace('#',''),16); }

  // ---------- 深路径工具（属性改动按 key 路径记录） ----------
  function getDeep(o, keys){ var v=o; for(var i=0;i<keys.length;i++){ if(v===null||v===undefined) return undefined; v=v[keys[i]]; } return v; }
  function setDeep(o, keys, val){ var v=o;
    for(var i=0;i<keys.length-1;i++){ var k=keys[i];
      if(typeof v[k]!=='object'||v[k]===null) v[k]={}; v=v[k]; }
    v[keys[keys.length-1]]=val; }
  function clone(o){ return JSON.parse(JSON.stringify(o)); }
  function merge(base, patch){
    var out=clone(base||{});
    function rec(t, p){ Object.keys(p).forEach(function(k){
      if(p[k] && typeof p[k]==='object' && !Array.isArray(p[k])){ rec(t[k]||(t[k]={}), p[k]); }
      else { t[k]=p[k]; } }); }
    rec(out, patch||{}); return out;
  }
  function mergedCtrl(p){ return merge(CTRL[p]||{}, props[p]||{}); }

  // ---------- 几何输入 ----------
  var propEl=document.getElementById('ed-prop'), propIn={};
  propEl.innerHTML = ['left','top','width','height'].map(function(f){
    return '<label>'+f+'</label><input type="number" step="1" data-p="'+f+'">';
  }).join('');
  Array.prototype.forEach.call(propEl.querySelectorAll('input'), function(inp){
    propIn[inp.dataset.p]=inp;
    inp.addEventListener('focus', function(){ if(sel) pushUndo(); });
    inp.addEventListener('change', applyProp);
    inp.addEventListener('keydown', function(e){
      if(e.key==='Enter'){ applyProp(); inp.blur(); e.preventDefault(); }
      if(e.key==='Escape'){ if(sel) fillProps(sel); inp.blur(); }
    });
  });
  function applyProp(){
    if(!sel) return;
    var g=geom(sel);
    ['left','top','width','height'].forEach(function(f){
      var v=parseInt(propIn[f].value,10); if(!isNaN(v)) g[f]=v;
    });
    setGeom(sel, clamp(g, sel)); select(sel); record(sel);
  }
  function fillProps(el){ var g=geom(el);
    ['left','top','width','height'].forEach(function(f){ propIn[f].value=g[f]; }); }

  // ---------- 属性字段（text/字号/颜色/图片/可见…全部可改） ----------
  var fieldsBox=document.getElementById('ed-fields');
  var COLOR_KEYS=/^(color\d|backgroundColor|hintTextColor|textColor|penColor|clockColor)$/;
  var PIC_KEYS=/^(backgroundPic|progressPic|pic0|pic1|pic2|pic3|pic4|pic|normalPic|pressedPic)$/;
  function isChildKey(k){ return /__\d+$/.test(k); }
  // 只读字段（由 IDE 生成 / 改了会错）：id
  var READONLY_KEYS={id:'控件 ID 由 IDE 生成，不支持修改'};
  // picTab 四个状态图（知识库 button-fields.md：pic0 正常 / pic1 按下 / pic2 选中 /
  // pic3 选中按下 / pic4 无效）
  var PIC_TAB_CN={pic0:'正常', pic1:'按下', pic2:'选中', pic3:'选中按下', pic4:'无效'};
  function fieldLabel(keys){
    var k=keys[keys.length-1];
    if(k==='picTab') return 'picTab（按钮各状态图）';
    if(k==='picTab'||keys.indexOf('picTab')>=0){
      if(PIC_TAB_CN[k]) return k+'（'+PIC_TAB_CN[k]+'）';
    }
    return k;
  }

  function renderFields(el){
    fieldsBox.innerHTML='';
    document.getElementById('ed-fc').textContent = el? '': '';
    if(!el){ fieldsBox.textContent='（选中控件后显示）'; return; }
    var data=CTRL[el.dataset.path];
    if(!data){ fieldsBox.textContent='（无原始数据）'; return; }
    var cur=mergedCtrl(el.dataset.path);
    Object.keys(data).forEach(function(k){
      if(k==='position'||k==='resolution'||isChildKey(k)) return;
      addField(fieldsBox, el.dataset.path, [k], cur[k], 0, k);
    });
    document.getElementById('ed-fc').textContent =
      Object.keys(data).filter(function(k){ return k!=='position'&&k!=='resolution'&&!isChildKey(k); }).length+' 项';
    /* 注：id 只读（IDE 生成，改了会与 mainActivity 生成代码不一致） */
  }

  function addField(box, p, keys, val, depth, label){
    var k=keys[keys.length-1];
    var disp=fieldLabel(keys)||label;
    if(val && typeof val==='object' && !Array.isArray(val)){
      var grp=document.createElement('div'); grp.className='ed-frow grp';
      grp.innerHTML='<label title="'+keys.join('.')+'">'+disp+'</label>'+
        '<span style="color:#6b7280">▾</span>';
      box.appendChild(grp);
      var sub=document.createElement('div'); sub.className='ed-fsub'; box.appendChild(sub);
      Object.keys(val).forEach(function(k2){ if(isChildKey(k2)) return;
        addField(sub, p, keys.concat([k2]), val[k2], depth+1, k2); });
      return;
    }
    var row=document.createElement('div'); row.className='ed-frow'+(depth?(' d'+depth):'');
    var lab=document.createElement('label'); lab.textContent=disp; lab.title=keys.join('.'); row.appendChild(lab);
    var cell=document.createElement('div'); row.appendChild(cell);

    // 只读字段：id（IDE 生成，改了会错）
    if(READONLY_KEYS[k] && keys.length===1){
      var ro=document.createElement('input'); ro.type='text'; ro.value=val;
      ro.readOnly=true; ro.title=READONLY_KEYS[k];
      ro.style.cssText='opacity:.55;cursor:not-allowed;';
      cell.appendChild(ro);
      var tip=document.createElement('span'); tip.textContent='（只读）';
      tip.style.cssText='color:#6b7280;font-size:11px;margin-left:4px;';
      cell.appendChild(tip);
      box.appendChild(row);
      return;
    }

    if(typeof val==='boolean'){
      var cb=document.createElement('input'); cb.type='checkbox'; cb.checked=!!val;
      cb.addEventListener('change', function(){ onField(p, keys, cb.checked); });
      cell.appendChild(cb);
    } else if(typeof val==='number'){
      if(COLOR_KEYS.test(k)){
        var cp=document.createElement('input'); cp.type='color'; cp.value=int2hex(val);
        var ni=document.createElement('input'); ni.type='number'; ni.value=val; ni.style.width='82px';
        cp.addEventListener('input', function(){ ni.value=hex2int(cp.value); onField(p, keys, hex2int(cp.value)); });
        ni.addEventListener('change', function(){ cp.value=int2hex(parseInt(ni.value,10)||0);
          onField(p, keys, parseInt(ni.value,10)||0); });
        cell.appendChild(cp); cell.appendChild(ni);
      } else {
        var ni2=document.createElement('input'); ni2.type='number'; ni2.value=val;
        ni2.addEventListener('change', function(){ onField(p, keys, parseFloat(ni2.value)); });
        cell.appendChild(ni2);
      }
    } else if(typeof val==='string'){
      var isLong=(k==='text'||val.length>48);
      var ti=document.createElement(isLong?'textarea':'input');
      if(!isLong) ti.type='text';
      ti.value=val;
      if(PIC_KEYS.test(k)) ti.placeholder='images/xxx.png（相对 resources）';
      ti.addEventListener('change', function(){ onField(p, keys, ti.value); });
      if(isLong){ ti.addEventListener('keydown', function(e){
        if(e.key==='Enter'&&(e.ctrlKey||e.metaKey)){ onField(p, keys, ti.value); } }); }
      cell.appendChild(ti);
    } else if(Array.isArray(val)){
      var ta=document.createElement('textarea'); ta.value=JSON.stringify(val,null,1);
      ta.title='复杂结构：改 JSON 后失焦生效';
      ta.addEventListener('change', function(){
        try{ onField(p, keys, JSON.parse(ta.value)); }
        catch(err){ ta.style.borderColor='#ff7b7b'; }
      });
      cell.appendChild(ta);
    } else {
      cell.textContent=String(val);
    }
    box.appendChild(row);
  }

  function onField(p, keys, val){
    pushUndo();
    var orig=getDeep(CTRL[p]||{}, keys);
    var same=(val && typeof val==='object')? JSON.stringify(val)===JSON.stringify(orig)
                                          : String(val)===String(orig);
    if(!props[p]) props[p]={};
    if(same){ // 改回原值 → 从改动集里摘掉
      var t=props[p];
      for(var i=0;i<keys.length-1;i++){ if(!t[keys[i]]) { t=null; break; } t=t[keys[i]]; }
      if(t) delete t[keys[keys.length-1]];
      var empty=function(o){ return Object.keys(o).length===0; };
      function prune(o, orig2){
        Object.keys(o).forEach(function(k2){
          if(o[k2] && typeof o[k2]==='object' && !Array.isArray(o[k2])){ prune(o[k2], (orig2||{})[k2]||{});
            if(empty(o[k2])) delete o[k2]; }
        });
      }
      prune(props[p], CTRL[p]||{});
      if(empty(props[p])) delete props[p];
    } else {
      setDeep(props[p], keys, val);
    }
    if(sel) { liveSync(sel, keys, val); renderFields(sel); }
    renderList();
  }

  // 对齐类：与 py 端 _align_class 同一套位定义（bit0-1 水平 0左1中2右 / bit2-3 垂直 0顶1中2底）
  function alignCls(val){
    var a=parseInt(val,10)||0;
    var h={0:'al-hl',1:'al-hc',2:'al-hr'}[a&3]||'al-hl';
    var v={0:'al-vt',1:'al-vc',2:'al-vb'}[(a>>2)&3]||'al-vt';
    return h+' '+v;
  }
  function applyAlign(el, val){
    ALIGN_CLS.forEach(function(c){ el.classList.remove(c); });
    alignCls(val).split(' ').forEach(function(c){ if(c) el.classList.add(c); });
    if(el.dataset.type==='button'){   // 文字按钮的默认居中会被对齐类盖掉，按类重算
      var c2=el.classList;
      el.style.justifyContent = c2.contains('al-hc')?'center':(c2.contains('al-hr')?'flex-end':'flex-start');
      el.style.alignItems = c2.contains('al-vc')?'center':(c2.contains('al-vb')?'flex-end':'flex-start');
    }
  }
  var ALIGN_CLS=['al-hl','al-hc','al-hr','al-vt','al-vc','al-vb','al-l','al-r'];

  // 画布即时生效（改文字/颜色/字号/图片/可见/对齐，立刻看到）
  function liveSync(el, keys, val){
    var k=keys[keys.length-1], t=el.dataset.type||'';
    if(k==='text' && (t==='textview'||t==='button'||t==='checkbox')){ el.textContent=(val===undefined?'':val); }
    else if(k==='fontSize'){ el.style.fontSize=(val||0)+'px'; }
    else if(k==='alignment'){ applyAlign(el, val); }
    else if(k==='backgroundColor'){ el.style.backgroundColor=int2hex(val); }
    else if(keys[0]==='colorTab' && k==='color0'){ el.style.color=int2hex(val); }
    else if(k==='bold'){ el.style.fontWeight=val?'bold':''; }
    else if(k==='italic'){ el.style.fontStyle=val?'italic':''; }
    else if(k==='backgroundPic' || (PIC_KEYS.test(k) && keys[0]==='picTab')){
      var uri=ASSETS[val];
      if(uri){ el.style.backgroundImage='url('+uri+')';
        el.style.backgroundSize='100% 100%'; el.style.backgroundRepeat='no-repeat'; }
      else if(!val){ el.style.backgroundImage=''; }
    }
    else if(k==='visible'){ applyVisible(el, val); }
    else return;
    refresh();
  }
  function applyVisible(el, vis){
    var hid=el.dataset.visible==='false';
    if(vis===false||hid){ if(!ghostOn){ el.style.display='none'; return; } }
    el.style.display='';
  }
  // 用「原始 + 改动」重建全部可视属性（撤销/还原后调用）
  function applyLiveAll(){
    all.forEach(function(el){
      var cur=mergedCtrl(el.dataset.path), t=el.dataset.type||'';
      if(cur.backgroundPic!==undefined){
        var uri=ASSETS[cur.backgroundPic];
        el.style.backgroundImage = uri? ('url('+uri+')') : (cur.backgroundPic? "url('"+cur.backgroundPic+"')" : '');
      }
      if(cur.colorTab && cur.colorTab.color0!==undefined) el.style.color=int2hex(cur.colorTab.color0);
      if(cur.fontSize!==undefined) el.style.fontSize=(cur.fontSize||0)+'px';
      if(cur.bold!==undefined) el.style.fontWeight=cur.bold?'bold':'';
      if(cur.italic!==undefined) el.style.fontStyle=cur.italic?'italic':'';
      if(cur.text!==undefined && (t==='textview'||t==='button'||t==='checkbox')) el.textContent=cur.text;
      if(cur.alignment!==undefined) applyAlign(el, cur.alignment);
      if(cur.backgroundColor!==undefined) el.style.backgroundColor=int2hex(cur.backgroundColor);
      el.style.display='';   // 再按 visible / ghost 规则收一遍
      if(cur.visible===false || el.dataset.visible==='false'){
        if(ghostOn) el.classList.add('ed-ghost'); else el.style.display='none';
      } else { el.classList.remove('ed-ghost'); }
    });
  }

  // ---------- 选中 ----------
  function select(el){
    sel=el;
    Array.prototype.forEach.call(document.querySelectorAll('.ed-tree .n.sel'),
      function(n){ n.classList.remove('sel'); });
    if(!el){
      selBox.style.display='none';
      document.getElementById('ed-cap').textContent='';
      document.getElementById('ed-info').textContent='未选中控件（点画布里的控件，或用下面列表选）';
      ['left','top','width','height'].forEach(function(f){ propIn[f].value=''; });
      renderFields(null); return;
    }
    var r=relPos(el), g=geom(el), p=el.dataset.path;
    selBox.style.display='block';
    selBox.style.left=r.x+'px'; selBox.style.top=r.y+'px';
    selBox.style.width=g.width+'px'; selBox.style.height=g.height+'px';
    selTag.textContent = p+(el.dataset.cap?('  '+el.dataset.cap):'')+
      '  '+g.left+','+g.top+'  '+g.width+'x'+g.height;
    fillProps(el);
    document.getElementById('ed-cap').textContent=(el.dataset.type||'')+'  '+(el.dataset.cap||'');
    var mine=issues.filter(function(i){ return i.path===p; });
    document.getElementById('ed-info').innerHTML = mine.length
      ? mine.map(function(i){ return '<span style="color:'+
          (i.level==='error'?'#ff7b7b':'#ffc46b')+'">'+i.msg+'</span>'; }).join('<br>')
      : ('key: '+p+(el.dataset.visible==='false'?'　（原布局 visible:false，默认隐藏）':''));
    var n=document.querySelector('.ed-tree .n[data-path="'+p+'"]');
    if(n) n.classList.add('sel');
    renderFields(el);
  }
  function refresh(){ if(sel) select2(sel); }
  function select2(el){   // 只刷框与标签，不重建属性面板（避免输入时被顶掉）
    var r=relPos(el), g=geom(el);
    selBox.style.left=r.x+'px'; selBox.style.top=r.y+'px';
    selBox.style.width=g.width+'px'; selBox.style.height=g.height+'px';
    selTag.textContent = el.dataset.path+(el.dataset.cap?('  '+el.dataset.cap):'')+
      '  '+g.left+','+g.top+'  '+g.width+'x'+g.height;
    fillProps(el);
  }

  // ---------- 控件列表 ----------
  var treeBody=document.getElementById('ed-tree-body');
  function renderTree(){
    var q=(document.getElementById('ed-search').value||'').toLowerCase(), out=[];
    all.forEach(function(el){
      var g=geom(el), cap=el.dataset.cap||'', hid=el.dataset.visible==='false';
      var label=el.dataset.path+(cap?(' · '+cap):'');
      var hay=(label+' '+g.left+','+g.top+','+g.width+','+g.height).toLowerCase();
      if(q && hay.indexOf(q)<0) return;
      out.push('<div class="n'+(hid?' hid':'')+(el===sel?' sel':'')+'" data-path="'+el.dataset.path+'">'+
        (hid?'⊘ ':'')+label+' <span class="z">'+g.width+'×'+g.height+'</span></div>');
    });
    treeBody.innerHTML = out.join('') || '<div class="n">（无匹配）</div>';
    document.getElementById('ed-tc').textContent='共 '+all.length+' 个';
  }
  treeBody.addEventListener('click', function(e){
    var n=e.target.closest? e.target.closest('.n[data-path]'):null; if(!n) return;
    var el=byPath(n.getAttribute('data-path'));
    if(el){ select(el); try{ el.scrollIntoView({block:'center', inline:'nearest'}); }catch(err){} }
  });
  treeBody.addEventListener('mouseover', function(e){
    var n=e.target.closest? e.target.closest('.n[data-path]'):null; if(!n) return;
    var p=n.getAttribute('data-path');
    all.forEach(function(c){ c.classList.toggle('ed-hover', c.dataset.path===p); });
  });
  treeBody.addEventListener('mouseleave', function(){
    all.forEach(function(c){ c.classList.remove('ed-hover'); }); });
  document.getElementById('ed-search').addEventListener('input', renderTree);

  // ---------- 改动记录 ----------
  function pushUndo(){ undoStack.push(JSON.stringify({c:changes,p:props})); redoStack.length=0; }
  function record(el){
    var p=el.dataset.path, g=geom(el), o=originals[p];
    if(g.left===o.left&&g.top===o.top&&g.width===o.width&&g.height===o.height) delete changes[p];
    else changes[p]=g;
    renderList(); renderTree(); refresh();
  }
  function flatPatch(patch, orig){
    var out={};
    (function rec(o, base, pre){
      Object.keys(o).forEach(function(k){
        var v=o[k];
        if(v && typeof v==='object' && !Array.isArray(v)) rec(v, (base||{})[k]||{}, pre+k+'.');
        else out[pre+k]={from:(base||{})[k], to:v};
      });
    })(patch, orig||{}, '');
    return out;
  }
  function renderList(){
    var box=document.getElementById('ed-list');
    var ks={}; Object.keys(changes).forEach(function(k){ ks[k]=1; });
    Object.keys(props).forEach(function(k){ ks[k]=1; });
    ks=Object.keys(ks);
    document.getElementById('ed-cnt').textContent=ks.length;
    if(!ks.length){ box.innerHTML='（未改动）'; sync(); return; }
    box.innerHTML=ks.map(function(k){
      var parts=[];
      var o=originals[k]||{}, c=changes[k];
      if(c){ ['left','top','width','height'].forEach(function(f){
        if(o[f]!==c[f]) parts.push('<span class="p">'+f+'</span>:<span class="v">'+o[f]+'→'+c[f]+'</span>'); }); }
      if(props[k]){
        var f2=flatPatch(props[k], CTRL[k]||{});
        Object.keys(f2).forEach(function(kk){
          var a=f2[kk].from, b=f2[kk].to;
          if(typeof a==='string'&&a.length>18) a=a.slice(0,18)+'…';
          if(typeof b==='string'&&b.length>24) b=b.slice(0,24)+'…';
          parts.push('<span class="p">'+kk+'</span>:<span class="v">'+
            (a===undefined?'(空)':a)+'→'+(b===undefined?'(空)':b)+'</span>');
        });
      }
      return '<div class="row"><span class="k">'+k+'</span><br>'+parts.join(' ')+'</div>';
    }).join('');
    sync();
  }
  function sync(){ document.getElementById('ed-out').value=JSON.stringify(payload(),null,2); }
  function payload(){
    var o={file:META.json, resolution:META.res};
    if(Object.keys(changes).length) o.changes=changes;
    if(Object.keys(props).length) o.props=props;
    o.note='由 ui_editor 导出；ui_edit_apply.py 写回 position/props 后 pack ftu';
    return o;
  }

  // ---------- 命中/拖动 ----------
  function candidatesAt(x,y){
    var hits=[];
    all.forEach(function(el){
      if(el.style.display==='none') return;
      var r=el.getBoundingClientRect();
      if(x>=r.left && x<=r.right && y>=r.top && y<=r.bottom) hits.push(el);
    });
    return hits.reverse();
  }
  var drag=null;
  device.addEventListener('mousedown', function(e){
    if(e.button!==0) return;
    var h=e.target.closest? e.target.closest('.ed-h'):null;
    if(h && sel){ startResize(e,h.dataset.d); return; }
    var mv=e.target.closest? e.target.closest('.ed-move'):null;
    if(mv && sel){ startDrag(e,sel); return; }
    var cand=candidatesAt(e.clientX,e.clientY);
    if(!cand.length){ select(null); return; }
    var el;
    if(e.altKey && sel){
      var i=cand.indexOf(sel);
      el=(i>=0)? cand[(i+1)%cand.length] : cand[0];
    } else { el=cand[0]; }
    select(el); startDrag(e,el);
  });
  function startDrag(e, el){ drag={el:el, sx:e.clientX, sy:e.clientY, g:geom(el), mode:'move'};
    pushUndo(); e.preventDefault(); }
  function startResize(e,d){ drag={el:sel, sx:e.clientX, sy:e.clientY, g:geom(sel), mode:'resize', d:d};
    pushUndo(); e.preventDefault(); e.stopPropagation(); }
  window.addEventListener('mousemove', function(e){
    if(!drag) return;
    var dx=e.clientX-drag.sx, dy=e.clientY-drag.sy, ns=e.altKey;
    var g=JSON.parse(JSON.stringify(drag.g));
    if(drag.mode==='move'){
      g.left=snapv(drag.g.left+dx, ns); g.top=snapv(drag.g.top+dy, ns);
      clamp(g, drag.el);
    } else {
      var d=drag.d, MIN=2;
      if(d.indexOf('e')>=0) g.width =Math.max(MIN, drag.g.width +snapv(dx,ns));
      if(d.indexOf('s')>=0) g.height=Math.max(MIN, drag.g.height+snapv(dy,ns));
      if(d.indexOf('w')>=0){ var nw=Math.max(MIN, drag.g.width -snapv(dx,ns));
        g.left=drag.g.left+(drag.g.width-nw); g.width=nw; }
      if(d.indexOf('n')>=0){ var nh=Math.max(MIN, drag.g.height-snapv(dy,ns));
        g.top=drag.g.top+(drag.g.height-nh); g.height=nh; }
    }
    setGeom(drag.el,g); select2(drag.el);
  });
  window.addEventListener('mouseup', function(){ if(drag){ record(drag.el); drag=null; } });
  device.addEventListener('mousemove', function(e){
    if(drag) return;
    var el=e.target.closest? e.target.closest('.ctrl'):null;
    all.forEach(function(c){ c.classList.toggle('ed-hover', c===el); });
  });

  // ---------- 键盘 ----------
  window.addEventListener('keydown', function(e){
    var t=e.target.tagName;
    if(t==='TEXTAREA'||t==='INPUT'||t==='SELECT') return;
    if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='z'){ undo(); e.preventDefault(); return; }
    if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='y'){ redo(); e.preventDefault(); return; }
    if(!sel) return;
    var step=(e.shiftKey?10:(e.altKey?1:(grid>1?grid:1))), g=geom(sel), hit=false;
    if(e.key==='ArrowLeft'){ g.left-=step; hit=true; }
    if(e.key==='ArrowRight'){ g.left+=step; hit=true; }
    if(e.key==='ArrowUp'){ g.top-=step; hit=true; }
    if(e.key==='ArrowDown'){ g.top+=step; hit=true; }
    if(!hit) return;
    setGeom(sel, clamp(g, sel)); select2(sel); record(sel); e.preventDefault();
  }, true);
  function undo(){ if(!undoStack.length) return;
    redoStack.push(JSON.stringify({c:changes,p:props}));
    var s=JSON.parse(undoStack.pop()); changes=s.c||{}; props=s.p||{}; applyAll(); }
  function redo(){ if(!redoStack.length) return;
    undoStack.push(JSON.stringify({c:changes,p:props}));
    var s=JSON.parse(redoStack.pop()); changes=s.c||{}; props=s.p||{}; applyAll(); }
  function applyAll(){
    changes={};
    all.forEach(function(el){ setGeom(el, changes[el.dataset.path]||originals[el.dataset.path]); });
    applyLiveAll(); renderList(); renderTree();
    if(sel) select(sel);
  }
  function applyGeomOnly(){
    all.forEach(function(el){ setGeom(el, changes[el.dataset.path]||originals[el.dataset.path]); });
  }

  // ---------- 预检问题标记 ----------
  document.getElementById('ed-ic').textContent=issues.length;
  function renderIssues(){
    var show=document.querySelector('[data-a="issues"]').checked;
    var box=document.getElementById('ed-issues');
    box.style.display=show?'block':'none';
    box.innerHTML = issues.length? issues.map(function(i){
      return '<div class="'+i.level+'">['+i.level.toUpperCase()+'] '+i.path+
        (i.cap?(' ('+i.cap+')'):'')+'<br>　'+i.msg+'</div>';
    }).join('') : '（无）';
    Array.prototype.forEach.call(document.querySelectorAll('.ed-bad'), function(n){ n.remove(); });
    if(!show) return;
    issues.forEach(function(i){
      var el=byPath(i.path); if(!el) return;
      var r=relPos(el);
      var b=document.createElement('div'); b.className='ed-bad '+i.level;
      b.textContent=(i.level==='error'?'图不对':'!');
      b.style.left=Math.max(0,r.x)+'px'; b.style.top=Math.max(14,r.y-16)+'px';
      ov.appendChild(b);
    });
  }
  renderIssues();

  // ---------- 工具条 ----------
  panel.addEventListener('click', function(e){
    var a=e.target.dataset? e.target.dataset.a:null; if(!a) return;
    if(a==='undo') undo();
    if(a==='redo') redo();
    if(a==='reset'){ changes={}; props={}; undoStack.length=0; redoStack.length=0;
      applyGeomOnly(); applyLiveAll(); renderList(); renderTree(); if(sel) select(sel); }
    if(a==='copy'){
      var t=document.getElementById('ed-out'); t.removeAttribute('readonly');
      t.select(); var ok=false;
      try{ ok=document.execCommand('copy'); }catch(err){}
      t.setAttribute('readonly','readonly');
      var btn=e.target, old=btn.textContent;
      btn.textContent = ok? '已复制 ✓' : '请手动 Ctrl+C';
      setTimeout(function(){ btn.textContent=old; },1200);
    }
    if(a==='dl'){ download(META.json.replace(/\.json$/,'')+'.changes.json',
      JSON.stringify(payload(),null,2)); }
    if(a==='dlfull'){
      var out=clone(META.full);
      (function rec(o){ Object.keys(o).forEach(function(k){
        if(o[k] && typeof o[k]==='object' && !Array.isArray(o[k])) rec(o[k]); }); })(out);
      applyPatchToJson(out, changes, props);
      download(META.json, JSON.stringify(out,null,2));
    }
  });
  function applyPatchToJson(root, ch, pr){
    function findNode(o, path){
      var parts=path.split('/'), node=o;
      for(var i=0;i<parts.length;i++){
        if(node && node[parts[i]]) node=node[parts[i]];
        else { // 单段全局搜
          var hit=null;
          (function walk(x){ Object.keys(x).forEach(function(k){
            if(k===parts[parts.length-1] && x[k] && typeof x[k]==='object') hit=x[k];
            if(x[k] && typeof x[k]==='object') walk(x[k]); }); })(o);
          return hit;
        }
      }
      return node;
    }
    Object.keys(ch||{}).forEach(function(p){
      var n=findNode(root,p); if(n && n.position) Object.keys(ch[p]).forEach(function(f){ n.position[f]=ch[p][f]; });
    });
    Object.keys(pr||{}).forEach(function(p){
      var n=findNode(root,p); if(!n) return;
      (function rec(patch){
        Object.keys(patch).forEach(function(k){
          if(patch[k] && typeof patch[k]==='object' && !Array.isArray(patch[k])){
            if(!n[k] || typeof n[k]!=='object') n[k]={};
            var sub=n[k]; (function rec2(patch2, target){
              Object.keys(patch2).forEach(function(k2){
                if(patch2[k2] && typeof patch2[k2]==='object' && !Array.isArray(patch2[k2])){
                  if(!target[k2]||typeof target[k2]!=='object') target[k2]={};
                  rec2(patch2[k2], target[k2]);
                } else { target[k2]=patch2[k2]; }
              }); })(patch[k], sub);
          } else { n[k]=patch[k]; }
        });
      })(pr[p]);
    });
  }
  panel.addEventListener('change', function(e){
    var a=e.target.dataset? e.target.dataset.a:null;
    if(a==='grid') grid=parseInt(e.target.value)||1;
    if(a==='boxes'){ selBox.style.visibility=e.target.checked?'visible':'hidden'; }
    if(a==='ghost'){
      ghostOn=e.target.checked;
      all.forEach(function(el){
        if(el.dataset.visible!=='false') return;
        if(ghostOn){ el.style.display='block'; el.classList.add('ed-ghost'); }
        else { el.style.display='none'; el.classList.remove('ed-ghost'); }
      });
      renderTree(); refresh();
    }
    if(a==='dims'){
      all.forEach(function(el){
        var t=el.querySelector('.ed-dim');
        if(e.target.checked){ if(t) return;
          t=document.createElement('div'); t.className='ed-dim';
          var g=geom(el); t.textContent=g.width+'x'+g.height;
          t.style.cssText='position:absolute;left:0;bottom:0;font:10px/12px monospace;'+
            'color:#ffd479;background:rgba(0,0,0,.55);pointer-events:none;z-index:10000;';
          el.appendChild(t);
        } else if(t){ t.remove(); } });
    }
    if(a==='issues') renderIssues();
  });
  function download(name, text){
    var blob=new Blob([text],{type:'application/json'});
    var a=document.createElement('a'); a.href=URL.createObjectURL(blob); a.download=name;
    document.body.appendChild(a); a.click(); a.remove();
  }
  document.addEventListener('mousedown', function(e){
    if(e.target.closest && (e.target.closest('.ed-panel')||e.target.closest('.ctrl')||
       e.target.closest('.ed-h')||e.target.closest('.ed-move'))) return;
    select(null);
  });
  renderTree(); renderList();
  if(location.hash.length>1){
    var want=decodeURIComponent(location.hash.slice(1));
    var el0=byPath(want);
    if(el0){ select(el0); try{ el0.scrollIntoView({block:'center'}); }catch(err){} }
  }
})();
</script>
"""


def make_editor(target, out_html=''):
    """target: 项目根目录 或 单个 json 文件。返回 {"success", "files":[{json, html, ...}]}"""
    if os.path.isdir(target) and os.path.isdir(os.path.join(target, 'ui')):
        ui_root = os.path.join(target, 'ui')
        jsons = []
        for root, dirs, files in os.walk(ui_root):
            dirs[:] = [d for d in dirs if d not in ('.git', '__pycache__')]
            jsons += [os.path.join(root, f) for f in sorted(files) if f.endswith('.json')]
        jsons.sort()
        # 默认输出到 <ui>/_edit/，不把生成物混进 ui/ 目录（单个 json 则同目录生成）
        out_html = out_html or os.path.join(ui_root, '_edit')
        out_dir = out_html
    elif os.path.isfile(target):
        jsons = [target]
        out_dir = out_html or os.path.dirname(os.path.abspath(target))
    else:
        return {'success': False, 'error': f'路径不存在或项目无 ui/ 目录: {target}'}

    if out_html:
        os.makedirs(out_html, exist_ok=True)

    res = []
    for jp in jsons:
        try:
            with open(jp, encoding='utf-8-sig') as f:
                data = json.load(f)
            r = data.get('resolution', {})
            jdir = os.path.dirname(os.path.abspath(jp))
            pics = _collect_pics(data, jdir)
            issues = _preflight(data, jdir, pics)
            # 图片资源内联进页面：预览能直接看到真图，属性栏换图也即时生效
            assets, bytes_used = {}, 0
            for ref in pics:
                if bytes_used > 14 * 1024 * 1024:
                    break
                uri = J2H._inline_image(ref, jdir, max_kb=600)
                if uri:
                    assets[ref] = uri
                    bytes_used += len(uri)
            controls = {p: c for p, _k, ctrl in _iter_controls(data, jdir)
                        for c in [ctrl] if isinstance(ctrl, dict)}
            meta = {
                'json': os.path.basename(jp),
                'res': f"{r.get('width', 0)}x{r.get('height', 0)}",
                'issues': [{'path': p, 'cap': c, 'level': l, 'msg': m} for p, c, l, m in issues],
                'full': data,
                'controls': controls,
                'assets': assets,
                'picCount': len(pics),
                'picMissing': sum(1 for v in pics.values() if not v),
            }
            js = EDIT_JS.replace('__META__', json.dumps(meta, ensure_ascii=False))
            hp = os.path.join(out_dir or os.path.dirname(jp),
                              os.path.splitext(os.path.basename(jp))[0] + '.edit.html')
            W, H = J2H._json_to_html(jp, hp, edit=True, extra_css=EDIT_CSS, extra_js=js,
                                     wrapper_open='<div class="ed-wrap"><div class="ed-stage">',
                                     wrapper_close='</div></div>')
            res.append({'json': os.path.basename(jp), 'html': hp, 'resolution': f'{W}x{H}',
                        'issues': len(issues), 'pics': len(pics), 'picsInlined': len(assets),
                        'picsMissing': sum(1 for v in pics.values() if not v)})
        except Exception as e:
            res.append({'json': os.path.basename(jp), 'html': None, 'error': str(e)})
    return {'success': all(r.get('html') for r in res), 'files': res}


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    out = sys.argv[2] if len(sys.argv) > 2 else ''
    r = make_editor(sys.argv[1], out)
    print(json.dumps(r, ensure_ascii=False, indent=1))
    sys.exit(0 if r.get('success') else 1)
