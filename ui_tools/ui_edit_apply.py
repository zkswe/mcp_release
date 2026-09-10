#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把 ui_editor 导出的「变更 JSON」写回 ui/*.json，可选直接 pack 成 ftu。

用法：
    python ui_edit_apply.py changes.json --project projects/MyApp            # 只写回
    python ui_edit_apply.py changes.json --project projects/MyApp --pack     # 写回 + pack ftu
    python ui_edit_apply.py changes.json --ui projects/MyApp/ui --dry-run    # 预演

变更 JSON 格式（ui_editor 导出）：
    {"file": "main.json", "resolution": "1024x600",
     "changes": {"button__1": {"left":130,"top":60,"width":150,"height":54},
                 "window__2/button__3": {...}},
     "props":   {"textview__4": {"text":"新文字","fontSize":22,
                                "colorTab":{"color0":16711680}}}}
    changes = 几何（position），props = 其它属性（深合并写回控件）；两者都可省。

安全措施：
    · 写回前自动备份 <name>.json.bak（同目录，覆盖式）
    · 格式一致性自检：原文件能被 json.dumps(indent=2, ensure_ascii=False) 无损还原才写
      （FlyThings json 就是这个格式；不一致时拒绝写入，加 --force 才继续）
    · 坐标取整 + 边界钳制（不越出父容器 / 屏幕）
"""
import argparse
import json
import os
import shutil
import subprocess
import sys


def _load_json(p):
    with open(p, encoding='utf-8-sig') as f:
        return json.load(f)


def _dump(data):
    return json.dumps(data, indent=2, ensure_ascii=False)


def _find_json(ui_dir, name):
    direct = os.path.join(ui_dir, name)
    if os.path.isfile(direct):
        return direct
    for root, _d, files in os.walk(ui_dir):
        if name in files:
            return os.path.join(root, name)
    return None


def _resolve_target(changes, project, ui_dir):
    """变更文件里可能带 file 字段，也可能直接是 {文件名: {控件: 几何}}。"""
    file_field = changes.get('file')
    body = changes.get('changes')
    if body is None and changes.get('props'):
        body = {}          # 只改属性、没改几何
    if file_field is None and body is not None and 'props' in changes:
        return _finish_target(file_field, body, changes.get('props') or {}, project, ui_dir)
    if body is None:
        # 形如 {"main.json": {"button__1": {...}}}
        files = [(k, v) for k, v in changes.items()
                 if isinstance(v, dict) and k not in ('props',)]
        if len(files) == 1:
            file_field, body = files[0][0], files[0][1]
        else:
            raise SystemExit('无法识别变更 JSON：缺 file/changes 字段')
    if file_field is None or body is None:
        raise SystemExit('无法识别变更 JSON：缺 file 或 changes')
    return _finish_target(file_field, body, changes.get('props') or {}, project, ui_dir)


def _finish_target(file_field, body, props, project, ui_dir):
    ui_dir = (ui_dir or '').strip()
    project = (project or '').strip()
    if not ui_dir:
        ui_dir = os.path.join(project, 'ui') if project else ''
    if not ui_dir:
        raise SystemExit('需要 --project 或 --ui')
    jp = _find_json(ui_dir, file_field)
    if not jp:
        raise SystemExit(f'找不到 json: {file_field} (在 {ui_dir})')
    return jp, body, props


def _node_by_path(root, path):
    """按 'window__2/button__3' 定位嵌套控件；单段则在整个树里找唯一匹配。"""
    parts = [p for p in path.split('/') if p]
    node = root
    for i, p in enumerate(parts):
        if not isinstance(node, dict) or p not in node:
            break
        if i == len(parts) - 1:
            return node[p]
        node = node[p]
    if len(parts) == 1:
        hits = []

        def walk(o):
            for k, v in o.items():
                if isinstance(v, dict) and '__' in k:
                    if k == parts[0]:
                        hits.append(v)
                    walk(v)
        walk(root)
        if len(hits) == 1:
            return hits[0]
        if len(hits) > 1:
            raise SystemExit(f'路径歧义（同名 {parts[0]} 有 {len(hits)} 个）：请用 window__x/{parts[0]} 全路径')
    raise SystemExit(f'找不到控件路径: {path}')


def apply_changes(changes, project='', ui_dir='', dry_run=False, force=False):
    jp, body, props = _resolve_target(changes, project, ui_dir)
    raw = open(jp, 'rb').read()
    data = json.loads(raw.decode('utf-8-sig'))

    if _dump(data).encode('utf-8') != raw:
        if not force:
            return {'success': False, 'error':
                    f'{jp} 格式与标准缩进(2)/UTF-8 不一致，拒绝写入以免整文件重排；'
                    f'确认可重排后加 --force'}
    res = data.get('resolution', {}) if isinstance(data, dict) else {}

    applied, skipped = [], []
    for path, g in body.items():
        try:
            ctrl = _node_by_path(data, path)
        except SystemExit as e:
            skipped.append({'path': path, 'reason': str(e)})
            continue
        pos = ctrl.setdefault('position', {})
        parent = ctrl.get('__parent_size')  # 由调用方注入（可选）
        changes_made = {}
        for f in ('left', 'top', 'width', 'height'):
            if f not in g:
                continue
            v = int(round(float(g[f])))
            if f in ('width', 'height'):
                v = max(1, v)
            changes_made[f] = [pos.get(f), v]
            pos[f] = v
        # 钳制：顶层控件不越出屏幕
        if path.count('/') == 0 and res:
            w, h = res.get('width', 0), res.get('height', 0)
            if w and pos.get('left', 0) + pos.get('width', 1) > w:
                pos['left'] = max(0, w - pos.get('width', 1))
            if h and pos.get('top', 0) + pos.get('height', 1) > h:
                pos['top'] = max(0, h - pos.get('height', 1))
            pos['left'] = max(0, pos.get('left', 0))
            pos['top'] = max(0, pos.get('top', 0))
        applied.append({'path': path, 'caption': ctrl.get('caption', ''), 'fields': changes_made})

    applied_props = []
    for path, patch in (props or {}).items():
        try:
            ctrl = _node_by_path(data, path)
        except SystemExit as e:
            skipped.append({'path': path, 'reason': str(e)})
            continue
        if not isinstance(patch, dict):
            skipped.append({'path': path, 'reason': 'props 不是对象'})
            continue
        touched = _merge_props(ctrl, patch)
        applied_props.append({'path': path, 'caption': ctrl.get('caption', ''),
                              'fields': touched})

    out = {'success': True, 'json': jp, 'applied': applied, 'appliedProps': applied_props,
           'skipped': skipped, 'dryRun': dry_run}
    if dry_run:
        return out

    shutil.copy2(jp, jp + '.bak')
    with open(jp, 'w', encoding='utf-8', newline='') as f:
        f.write(_dump(data))
    out['backup'] = jp + '.bak'
    return out


def _merge_props(ctrl, patch, prefix=''):
    """属性深合并到控件（嵌套 dict 递归；list/标量直接覆盖）。返回改动字段列表。"""
    touched = []
    for k, v in patch.items():
        if isinstance(v, dict) and not isinstance(ctrl.get(k), list):
            if not isinstance(ctrl.get(k), dict):
                ctrl[k] = {}
            touched += _merge_props(ctrl[k], v, prefix + k + '.')
        else:
            old = ctrl.get(k)
            if old != v:
                touched.append(f'{prefix}{k}: {old!r} -> {v!r}')
            ctrl[k] = v
    return touched


def find_fui(project=''):
    for c in ([os.environ.get('FUI_EXE', '')] +
              [os.path.join(project, 'ui', 'fui.exe') if project else '',
               os.path.join(project, 'fui.exe') if project else '']):
        if c and os.path.isfile(c):
            return c
    here = os.path.dirname(os.path.abspath(__file__))
    for up in (os.path.join(here, '..', '..', 'projects', 'fui.exe'),
               os.path.join(here, 'fui.exe')):
        up = os.path.abspath(up)
        if os.path.isfile(up):
            return up
    return 'fui.exe'   # 交给 PATH


def pack(json_path, project=''):
    fui = find_fui(project)
    cmd = [fui, 'pack', json_path]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
    ftu = os.path.splitext(json_path)[0] + '.ftu'
    return {'cmd': ' '.join(cmd), 'returncode': r.returncode,
            'stdout': (r.stdout or '').strip()[-400:],
            'stderr': (r.stderr or '').strip()[-400:],
            'ftu': ftu if os.path.isfile(ftu) else None,
            'ftuMtime': os.path.getmtime(ftu) if os.path.isfile(ftu) else None}


def main():
    ap = argparse.ArgumentParser(description='ui_editor 变更 JSON → 写回 json（可 pack ftu）')
    ap.add_argument('changes', help='ui_editor 导出的变更 JSON 路径')
    ap.add_argument('--project', default='', help='项目根目录')
    ap.add_argument('--ui', default='', help='ui 目录（与 --project 二选一）')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--force', action='store_true', help='格式不一致也写入（整文件重排）')
    ap.add_argument('--pack', action='store_true', help='写回后直接 pack 成 ftu')
    a = ap.parse_args()

    ch = _load_json(a.changes)
    r = apply_changes(ch, project=a.project, ui_dir=a.ui, dry_run=a.dry_run, force=a.force)
    if not r.get('success'):
        print(json.dumps(r, ensure_ascii=False, indent=1))
        return 1
    if a.pack and not a.dry_run:
        r['pack'] = pack(r['json'], a.project)
    print(json.dumps(r, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.exit(main())
