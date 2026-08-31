# -*- coding: utf-8 -*-
"""FlyThings UI 自动化测试生成器（纯代码，不依赖 AI）。

核心思路：
  ui/*.json 布局本身已包含全部控件坐标（position left/top/width/height）与
  可交互信息（touchable/visible）——直接解析 json 生成测试**数据脚本**，
  配合预编译的通用触摸注入工具（bin_tools/{platform}/ui_test ELF）执行。

  架构（沛哥 2026-08-31 确认）：
    - 通用工具（触摸注入 ui_test、将来 busybox 等）在电脑端预编译成各平台 ELF，
      放 MCP 独立目录 bin_tools/{platform}/，一次编译处处复用
    - 测试项目只生成数据文件（script.txt：tap/swipe/delay 指令），不再现场编译
    - 好处：tools 不膨胀、生成秒级、部署 = adb push ELF + 脚本

  test_type:
    traverse - 遍历控件验收：所有可交互控件逐个点击+滑动（生成脚本）+ 资源缺失检查
    monkey   - 压测 MonkeyTest：随机 tap/swipe 指定次数（直接用 ui_test monkey 命令）
    custom   - 自定义验收：按用户输入要求生成（差异化逻辑可走 AI）
    ask      - 询问用户三种验收方式（默认）
"""
import json, os, re, subprocess, shutil

_BASE = os.path.dirname(os.path.abspath(__file__))
BIN_TOOLS_DIR = os.path.join(_BASE, 'bin_tools')
SUPPORTED_PLATFORMS = ('z21', 'z20', 't113', 'f133', 'v85x')

# 可交互控件类型（touchable=true 时生成点击）
INTERACTIVE_TYPES = ('button', 'checkbox', 'radiogroup', 'edittext', 'seekbar',
                     'slidewindow', 'scrollwindow', 'pagewindow', 'videoview',
                     'qrcode', 'cameraview', 'imageanim')
# 滑动类控件（生成 swipe 而非 tap）
SWIPE_TYPES = ('seekbar', 'slidewindow', 'scrollwindow', 'pagewindow')


def _platform_elf(platform):
    """返回预编译 ui_test ELF 路径（bin_tools/{platform}/ui_test）。"""
    p = platform.lower()
    if p not in SUPPORTED_PLATFORMS:
        return None
    elf = os.path.join(BIN_TOOLS_DIR, p, 'ui_test')
    return elf if os.path.isfile(elf) else None


def _parse_ui_jsons(project_root):
    """解析 project_root/ui/*.json → 页面+控件列表。

    返回: {pages: [{file, res_w, res_h, controls: [...]}]}
    控件: {key, type, caption, id, left, top, w, h, touchable, visible,
           cx, cy(中心点), is_swipe}
    """
    ui_dir = os.path.join(project_root, 'ui')
    if not os.path.isdir(ui_dir):
        return None, 'ui 目录不存在: %s' % ui_dir
    jsons = sorted(f for f in os.listdir(ui_dir)
                   if f.endswith('.json') and not f.endswith('.preview.html'))
    if not jsons:
        return None, 'ui/ 下无 .json 布局（%s）' % ui_dir
    pages = []
    for fn in jsons:
        try:
            with open(os.path.join(ui_dir, fn), encoding='utf-8') as fh:
                d = json.load(fh)
        except Exception as e:
            pages.append({'file': fn, 'error': 'json 解析失败: %s' % e})
            continue
        res = d.get('resolution') or {}
        res_w, res_h = res.get('width', 0), res.get('height', 0)
        controls = []
        for key, v in d.items():
            if not isinstance(v, dict) or 'position' not in v:
                continue
            pos = v['position']
            left, top = pos.get('left', 0), pos.get('top', 0)
            w, h = pos.get('width', 0), pos.get('height', 0)
            if w <= 0 or h <= 0:
                continue
            ctype = key.split('__')[0]
            touchable = bool(v.get('touchable', False))
            visible = bool(v.get('visible', True))
            # 可交互：touchable 或交互类型控件
            interactive = touchable or ctype in INTERACTIVE_TYPES
            if not interactive:
                continue
            ctrl = {
                'key': key, 'type': ctype,
                'caption': v.get('caption', ''),
                'id': v.get('id', 0),
                'left': left, 'top': top, 'w': w, 'h': h,
                'cx': left + w // 2, 'cy': top + h // 2,
                'touchable': touchable, 'visible': visible,
                'is_swipe': ctype in SWIPE_TYPES,
                'picTab': v.get('picTab') or {},
            }
            controls.append(ctrl)
        pages.append({'file': fn, 'res_w': res_w, 'res_h': res_h,
                      'controls': controls})
    return pages, None


def _check_resources(project_root, pages):
    """遍历验收附带：检查控件引用的图片资源是否缺失。"""
    res_dir = os.path.join(project_root, 'resources')
    missing = []
    for pg in pages:
        for c in pg.get('controls', []):
            for pic in (c.get('picTab') or {}).values():
                if not pic:
                    continue
                candidates = [
                    os.path.join(res_dir, 'images', pic),
                    os.path.join(res_dir, pic),
                    os.path.join(res_dir, 'image', pic),
                ]
                if not any(os.path.isfile(p) for p in candidates):
                    missing.append({'page': pg['file'], 'control': c['key'],
                                    'caption': c['caption'], 'pic': pic})
    return missing


def _gen_traverse_script(pages):
    """生成遍历验收数据脚本（ui_test run 格式）。

    每行: tap x y / swipe x1 y1 x2 y2 / long x y ms / delay ms
    注释行: # 页名/控件名 说明（便于 logcat 对应）
    """
    lines = ['# FlyThings UI 遍历控件验收脚本（自动生成，ui_test run 执行）']
    for pg in pages:
        lines.append('# ==== page: %s ====' % pg['file'])
        for c in pg.get('controls', []):
            label = (c['caption'] or c['key']).replace('"', '\\"')
            if c['is_swipe']:
                if c['h'] >= c['w']:
                    sx, sy, ex, ey = c['cx'], c['top'] + 2, c['cx'], c['top'] + c['h'] - 2
                else:
                    sx, sy, ex, ey = c['left'] + 2, c['cy'], c['left'] + c['w'] - 2, c['cy']
                lines.append('# swipe %s' % label)
                lines.append('swipe %d %d %d %d' % (sx, sy, ex, ey))
            else:
                lines.append('# tap %s' % label)
                lines.append('tap %d %d' % (c['cx'], c['cy']))
            lines.append('delay 500')
    return '\n'.join(lines) + '\n'


def _write_script(out_dir, script_text, script_name='ui_test_script.txt'):
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, script_name)
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write(script_text)
    return path


def flythings_gen_ui_test(project_root, test_type='ask', output_dir='',
                          platform='z21', with_build=True, monkey_count=500):
    """根据 UI json 布局生成自动化测试数据脚本（纯代码，不依赖 AI）。

    test_type:
      ask      - 询问用户三种验收方式（默认，返回选项说明）
      traverse - 遍历控件验收：生成 tap/swipe 脚本 + 资源缺失检查
      monkey   - 压测 MonkeyTest：随机 tap/swipe（ui_test monkey 命令直接跑）
      custom   - 自定义验收：按用户提供的要求生成（差异化逻辑可走 AI）

    执行依赖预编译工具 bin_tools/{platform}/ui_test（ELF，电脑端已编好），
    部署 = adb push ELF + 脚本，不再现场编译。
    """
    if test_type not in ('ask', 'traverse', 'monkey', 'custom'):
        return {'success': False,
                'error': "test_type 必须是 ask/traverse/monkey/custom 之一",
                'testTypes': _ask_options()}

    if test_type == 'ask':
        return {'success': True, 'needUserChoice': True, 'options': _ask_options()}

    root = os.path.abspath(project_root)
    if not os.path.isdir(root):
        return {'success': False, 'error': '项目目录不存在: %s' % root}

    # 预编译工具检查
    elf = _platform_elf(platform)
    if not elf:
        return {'success': False,
                'error': '平台 %s 未预编译 ui_test（可用: %s）' % (platform, '/'.join(SUPPORTED_PLATFORMS))}

    pages, err = _parse_ui_jsons(root)
    if err:
        return {'success': False, 'error': err}

    res_w = next((p['res_w'] for p in pages if p.get('res_w')), 1024)
    res_h = next((p['res_h'] for p in pages if p.get('res_h')), 600)

    name = os.path.basename(root).strip() or 'UiTest'
    out = os.path.abspath(output_dir) if output_dir else os.path.join(
        os.path.dirname(root), 'UiTest_%s' % name)
    if os.path.isdir(out) and os.listdir(out):
        return {'success': False,
                'error': '输出目录非空: %s（请换 output_dir 或清空）' % out}
    os.makedirs(out, exist_ok=True)

    if test_type == 'traverse':
        total = sum(len(p.get('controls', [])) for p in pages)
        if total == 0:
            return {'success': False,
                    'error': '未找到可交互控件（touchable=true 或交互类型）'}
        script = _gen_traverse_script(pages)
        script_path = _write_script(out, script)
        missing = _check_resources(root, pages)
        desc = '遍历控件验收: %d 页 %d 个可交互控件' % (len(pages), total)
        run_cmd = 'run %s' % os.path.basename(script_path)
        result = {
            'success': True, 'testType': test_type, 'description': desc,
            'projectRoot': out, 'pages': len(pages),
            'resolution': '%dx%d' % (res_w, res_h),
            'controlCount': total,
            'toolElf': elf,
            'scriptFile': script_path,
            'resourceCheck': {'missingCount': len(missing), 'missing': missing[:20]},
        }
    elif test_type == 'monkey':
        desc = 'Monkey 压测: %dx%d 随机 %d 次输入' % (res_w, res_h, monkey_count)
        run_cmd = 'monkey %d %d %d' % (res_w, res_h, monkey_count)
        result = {
            'success': True, 'testType': test_type, 'description': desc,
            'projectRoot': out, 'pages': len(pages),
            'resolution': '%dx%d' % (res_w, res_h),
            'monkeyCount': monkey_count,
            'toolElf': elf,
        }
    else:  # custom
        return {'success': True, 'needUserInput': True,
                'hint': '请提供自定义验收要求（如：循环点击 A 按钮 100 次后截图校验），'
                        '差异化测试逻辑将由 AI 生成，普通遍历/压测建议用 traverse/monkey 免 AI。'}

    # 部署提示：push ELF + 脚本，直接跑
    elf_name = os.path.basename(elf)
    push_elf = 'adb push %s /data/%s && adb shell chmod +x /data/%s' % (elf, elf_name, elf_name)
    if test_type == 'traverse':
        script_name = os.path.basename(result['scriptFile'])
        push_script = 'adb push %s /data/%s' % (result['scriptFile'], script_name)
        cmd = 'adb shell /data/%s /dev/input/event1 %s' % (elf_name, run_cmd)
        result['deployHint'] = ('%s && %s && %s\n（设备节点按实际 getevent 确认；'
                                '运行同时 adb logcat 观察 [UITEST] 与业务日志）'
                                % (push_elf, push_script, cmd))
    else:
        cmd = 'adb shell /data/%s /dev/input/event1 %s' % (elf_name, run_cmd)
        result['deployHint'] = ('%s && %s\n（设备节点按实际 getevent 确认；'
                                '运行同时 adb logcat 观察 [MONKEY] 与业务日志）'
                                % (push_elf, cmd))
    return result


def _ask_options():
    return [
        {'type': 'traverse', 'label': '遍历控件验收',
         'desc': '解析 UI json 所有可交互控件（按钮/输入框/滑动条等），逐个点击+滑动，'
                 '并检查控件引用的图片资源是否缺失、配合 logcat 确认代码响应是否正常。'
                 '适合：图标缺失检查、功能按钮可用性验收。'},
        {'type': 'monkey', 'label': '压测 MonkeyTest 验收',
         'desc': '在屏幕范围内随机 tap/swipe（可设次数），发现潜在隐患'
                 '（崩溃/卡死/异常日志）。适合：稳定性压测、长时间老化。'},
        {'type': 'custom', 'label': '自定义验收',
         'desc': '按你输入的具体要求生成测试（如"循环点 A 按钮 100 次"、"进入设置页截图"等），'
                 '差异化测试逻辑由 AI 生成。'},
    ]
