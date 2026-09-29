# -*- coding: utf-8 -*-
"""FlyThings UI 自动化测试生成器（纯代码，不依赖 AI）。

核心思路：
  ui/*.json 布局本身已包含全部控件坐标（position left/top/width/height）与
  可交互信息（touchable/visible）——直接解析 json 生成测试**数据脚本**，
  配合预编译的通用触摸注入工具（bin_tools/{platform}/touch ELF）执行。

  架构（沛哥 2026-08-31 确认；2026-09-12 换用统一工具 touch）：
    - 通用工具（触摸注入 touch、busybox 等）在电脑端预编译成各平台 ELF，
      放 MCP 独立目录 bin_tools/{platform}/，一次编译处处复用
    - 测试项目只生成数据文件（script.txt：tap/swipe/delay 指令），不再现场编译
    - 好处：tools 不膨胀、生成秒级、部署 = adb push ELF + 脚本

  ⚠️ 注入工具选择（2026-09-12）：
    - **首选 `touch`**（bin_tools/{平台}/touch）：自动扫描 /dev/input 找触摸节点、
      自动判协议（MT-B / MT-A / 单点），**部署命令不需要传设备节点**
    - `ui_test`（单点）/ `mt_test`（MT-A）保留兼容，但需人工指定节点且要猜协议，
      仅在 touch 缺该平台 ELF 时退回使用

  test_type:
    traverse - 遍历控件验收：所有可交互控件逐个点击+滑动（生成脚本）+ 资源缺失检查
    monkey   - 压测 MonkeyTest：随机 tap/swipe 指定次数（直接用 ui_test monkey 命令）
    custom   - 自定义验收：按用户输入要求生成（差异化逻辑可走 AI）
    ask      - 询问用户三种验收方式（默认）
"""
import json, os, re, subprocess, shutil

import platforms as _platforms  # 平台名唯一来源（别在这里再抄一份白名单）
import adb_tools as _adb

_BASE = os.path.dirname(os.path.abspath(__file__))
BIN_TOOLS_DIR = os.path.join(_BASE, 'bin_tools')
# 可跑 UI 测试的平台 = platforms.py 里可建工程的平台（小写化），单一来源。
# 以前这里手抄一份 ('z21','z20',...) 元组，与 platforms.py 漂移了也没人知道。
SUPPORTED_PLATFORMS = tuple(p.lower() for p in _platforms.supported())

# 可交互控件类型（touchable=true 时生成点击）
INTERACTIVE_TYPES = ('button', 'checkbox', 'radiogroup', 'edittext', 'seekbar',
                     'slidewindow', 'scrollwindow', 'pagewindow', 'videoview',
                     'qrcode', 'cameraview', 'imageanim')
# 滑动类控件（生成 swipe 而非 tap）
SWIPE_TYPES = ('seekbar', 'slidewindow', 'scrollwindow', 'pagewindow')


def _platform_elf(platform):
    """返回预编译触摸注入 ELF 路径（**按真实文件探测**，不是按平台名白名单）。

    解析（支持别名/大小写）→ 取 bin_tools 目录名 → 真的存在 touch 才用，
    其次退回老的 ui_test；两边都没有就回 None（调用方据此报「未预编译」，
    并把真实可用平台列出来，而不是笼统地说平台不支持）。
    """
    info = _platforms.resolve(platform)
    if not info or not info.get('buildable'):
        return None
    p = info['binTool']
    for name in ('touch', 'ui_test'):
        elf = os.path.join(BIN_TOOLS_DIR, p, name)
        if os.path.isfile(elf):
            return elf
    return None


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
        # A7 修（2026-09-27）：**递归**收集嵌套控件 —— 旧版只扫根层，交互控件全在
        #   window/card 里（弹窗页、键盘页）的工程产出的可测控件为 0，自动化遍历完全覆盖不到。
        #   嵌套控件的 position 是**父相对坐标** → 累加父偏移得到屏幕坐标（tap 才落得准）。
        def _collect(dd, ox, oy, depth, out, keys=()):
            for key, v in dd.items():
                if key.startswith('__') or not isinstance(v, dict):
                    continue
                pos = v.get('position')
                if not isinstance(pos, dict):
                    continue
                left, top = ox + pos.get('left', 0), oy + pos.get('top', 0)
                w, h = pos.get('width', 0), pos.get('height', 0)
                if w <= 0 or h <= 0:
                    continue
                ctype = key.split('__')[0]
                touchable = bool(v.get('touchable', False))
                visible = bool(v.get('visible', True))
                # 可交互：touchable 或交互类型控件
                interactive = touchable or ctype in INTERACTIVE_TYPES
                if interactive:
                    ctrl = {
                        'key': key, 'type': ctype,
                        'caption': v.get('caption', ''),
                        'id': v.get('id', 0),
                        'left': left, 'top': top, 'w': w, 'h': h,
                        'cx': left + w // 2, 'cy': top + h // 2,
                        'touchable': touchable, 'visible': visible,
                        'is_swipe': ctype in SWIPE_TYPES,
                        'picTab': v.get('picTab') or {},
                        'nested': depth > 0,
                        'path': '/'.join(keys + (key,)),
                    }
                    out.append(ctrl)
                _collect(v, left, top, depth + 1, out, keys + (key,))

        _collect(d, 0, 0, 0, controls)
        pages.append({'file': fn, 'res_w': res_w, 'res_h': res_h,
                      'controls': controls,
                      'controlsTopLevel': sum(1 for c in controls if not c['nested']),
                      'controlsNested': sum(1 for c in controls if c['nested'])})
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
      monkey   - 压测 MonkeyTest：随机 tap/swipe（touch monkey 命令直接跑）
      custom   - 自定义验收：按用户提供的要求生成（差异化逻辑可走 AI）

    执行依赖预编译工具 bin_tools/{platform}/touch（ELF，电脑端已编好），
    部署 = adb push ELF + 脚本，不再现场编译。
    **touch 自动识别触摸节点与协议，部署命令不带 /dev/input/eventN**。
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
                'error': '平台 %s 未预编译触摸注入工具（可用: %s）'
                         % (platform, '/'.join(SUPPORTED_PLATFORMS)),
                'hint': '平台名支持别名/大小写（如 F133EMMC -> F133）；'
                        '若确实是新平台，按 bin_tools/README「新增平台/工具流程」补预编译 ELF'} 

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

    # 部署提示：push ELF + 脚本，直接跑（touch 自动选节点/协议，不写 eventN）
    elf_name = os.path.basename(elf)
    push_elf = 'adb push %s /data/%s && adb shell chmod +x /data/%s' % (elf, elf_name, elf_name)
    if elf_name == 'touch':
        run_tpl = 'adb shell /data/touch '          # 节点+协议自动识别
        note = '（touch 自动扫描 /dev/input 并判协议；想先看清单跑 `adb shell /data/touch list`；' \
               '运行同时 adb logcat 观察 [TOUCH] 与业务日志）'
    else:                                            # 退回 ui_test/mt_test：需人工给节点
        run_tpl = 'adb shell /data/%s /dev/input/eventN ' % elf_name
        note = '（ui_test/mt_test 需要设备节点，先 getevent 确认；' \
               '运行同时 adb logcat 观察业务日志）'
    if test_type == 'traverse':
        script_name = os.path.basename(result['scriptFile'])
        push_script = 'adb push %s /data/%s' % (result['scriptFile'], script_name)
        cmd = run_tpl + 'run /data/' + script_name
        result['deployHint'] = ('%s && %s && %s\n%s'
                                % (push_elf, push_script, cmd, note))
    else:
        cmd = run_tpl + run_cmd
        result['deployHint'] = ('%s && %s\n%s' % (push_elf, cmd, note))
    return result


# ══════════════════════════════════════════════════════════════════════════

# ══════════════════════════════════════════════════════════════════════════
# 多设备并行测试跑批 + 机读报告（2026-09-29；钟工「自动化测试/验收」优化项）
#
# 补的三件事（此前只能靠 AI 手敲 adb + 人眼看截图）：
#   ① 同一份用例在**多台设备并行**跑（此前多设备在线时工具一律「不猜」，只能逐台串行手敲）
#   ② 每步结果**机器可判**（注入命令 rc / 日志断言 / 与像素基线逐像素对比），不是「跑完了」
#   ③ 产出**机器可读报告**（JSON + JUnit XML），能直接进 CI / 质量门
# 基线对比复用 ui_baseline.py；**比不到基线报 no-baseline，绝不静默当通过**。
# ══════════════════════════════════════════════════════════════════════════
import time
import xml.sax.saxutils as _xml
from concurrent.futures import ThreadPoolExecutor

STEP_ACTIONS = ('tap', 'swipe', 'long', 'wait', 'shot', 'log', 'monkey', 'run')
BASELINE_MODES = ('auto', 'compare', 'save', 'off')
_PLAN_DOC = ('{"name":"<用例名>","steps":['
             '{"name":"进入设置","action":"tap","x":512,"y":300,"wait":800,'
             '"shot":"home_setting","expectLog":["onClick"]},'
             '{"action":"swipe","from":[512,900],"to":[512,300],"duration":300},'
             '{"action":"log","lines":200,"expectNoLog":["FATAL","segfault"]}]}')


def _load_plan(plan):
    """plan 可以是 JSON 文本，也可以是 .json 文件路径。"""
    if not plan or not str(plan).strip():
        return None, ('缺 plan：传用例 JSON 文本或 .json 路径，形如 %s' % _PLAN_DOC)
    raw = str(plan).strip()
    txt = raw
    if os.path.isfile(raw):
        try:
            with open(raw, encoding='utf-8') as fh:
                txt = fh.read()
        except Exception as e:
            return None, 'plan 文件读不了: %s (%s)' % (raw, e)
    try:
        d = json.loads(txt)
    except Exception as e:
        return None, 'plan 不是合法 JSON: %s。形如 %s' % (e, _PLAN_DOC)
    if not isinstance(d, dict) or not isinstance(d.get('steps'), list) or not d['steps']:
        return None, 'plan 结构不对：需要 {"steps": [...]} 且非空。形如 %s' % _PLAN_DOC
    bad = []
    for i, s in enumerate(d['steps']):
        if not isinstance(s, dict):
            bad.append('#%d 不是对象' % (i + 1))
            continue
        a = str(s.get('action') or '').strip().lower()
        if a not in STEP_ACTIONS:
            bad.append('#%d action=%s 不认识（可用: %s）'
                       % (i + 1, a or '(空)', '/'.join(STEP_ACTIONS)))
        s['action'] = a
    if bad:
        return None, 'plan 步骤有问题: ' + '；'.join(bad)
    d.setdefault('name', 'ui-test')
    return d, None


def _dev_brief(d):
    return {'serial': d.get('serial'), 'model': d.get('model', ''),
            'platform': d.get('platform', ''), 'state': d.get('state')}


def _select_devices(devices, adb, platform=''):
    """挑执行设备。多台在线时**不猜**（沿用本仓口径）：auto 只在恰好 1 台时生效。"""
    want = str(devices or 'auto').strip()
    info = _adb.probe_devices(adb, with_model=True)
    if not info.get('ok'):
        return None, {'error': '设备探测失败: %s' % info.get('error', ''),
                      'hint': '先确认 adb 可用（adb_tools.resolve_adb）'}
    online = info.get('online') or []
    if not online:
        return None, {'error': '没有在线设备', 'installHint': _adb.install_hint(platform),
                      'hint': 'USB 调试授权；网络设备先 adb connect <IP>:5555'}
    if want.lower() in ('auto', 'single', 'one'):
        if len(online) > 1:
            return None, {'error': '在线 %d 台，devices="auto" 不猜' % len(online),
                          'online': [_dev_brief(d) for d in online],
                          'hint': '传 devices="all"（每台都跑）或 devices="<IP>:5555,<IP>:5555"'}
        return online, None
    if want.lower() == 'all':
        return online, None
    ser_map = {}
    for d in online:
        for k in (d.get('serial'), d.get('ip')):
            if k:
                ser_map[str(k)] = d
    picked, unknown = [], []
    for tok in [x.strip() for x in want.split(',') if x.strip()]:
        d = ser_map.get(tok)
        if d is None and ':' not in tok and (tok + ':5555') in ser_map:
            d = ser_map[tok + ':5555']
        if d is None:
            unknown.append(tok)
        else:
            picked.append(d)
    if unknown:
        return None, {'error': '这些设备不在线: %s' % ', '.join(unknown),
                      'online': [_dev_brief(d) for d in online],
                      'hint': '用在线清单里的 serial（含 :5555 端口）'}
    return picked, None


def _platform_of(dev, platform=''):
    """设备平台：显式传的优先；否则用探测结果里的型号/platform（查不到就明确报，不猜）。"""
    if platform:
        return platform, ''
    p = dev.get('platform') or ''
    if p:
        return p, ''
    model = dev.get('model') or ''
    if not model:
        return '', '设备未回 ro.product.model（无法判平台）→ 显式传 platform 参数'
    return '', '型号 %s 未登记平台（device_models.json）→ 显式传 platform 参数' % model


def _deploy_touch(serial, adb, platform, notes):
    """推 bin_tools/<平台>/touch（touch 自动扫节点+判协议，不传 eventN）。

    落点依次试 `/data` → `/tmp` → `/mnt/extsd`：Z20 那类板子 `/data` 经常写满
    （实测报 `remote No space left on device`），退到 tmpfs 一样能跑；用了哪个目录会回显。
    """
    elf = _platform_elf(platform)
    if not elf:
        return None, ('平台 %s 无可用的预编译注入工具（可用: %s）'
                      % (platform, '/'.join(SUPPORTED_PLATFORMS)))
    name = os.path.basename(elf)
    tried, last = [], ''
    for d in ('/data', '/tmp', '/mnt/extsd'):
        remote = '%s/%s' % (d, name)
        rc, out, err = _adb.push(adb, serial, elf, remote)
        if rc != 0:
            last = ((out or '') + (err or '')).strip()[-200:]
            tried.append('%s ✗ %s' % (d, last.replace('\n', ' ')[:80]))
            continue
        _adb.shell_rc(adb, serial, 'chmod 777 %s' % remote)
        rc2, out2, err2 = _adb.shell_rc(adb, serial, '%s list' % remote, timeout=40)
        if rc2 != 0:
            last = ((out2 or '') + (err2 or '')).strip()[-200:]
            tried.append('%s ✗ 起不来: %s' % (d, last.replace('\n', ' ')[:60]))
            continue
        extra = '（%s）' % '；'.join(tried) if tried else ''
        notes.append('%s: 注入工具 %s → %s%s；节点/协议: %s'
                     % (serial, name, remote, extra,
                        ' '.join((out2 or '').split())[:80]))
        return remote, ''
    return None, ('注入工具推不上去（试过 %s）：%s\nhint: 设备存储满了就先腾空间，'
                  '或手动把 bin_tools/%s/%s 推到 /tmp 再跑'
                  % ('/data, /tmp, /mnt/extsd', last, _platform_key(platform), name))


def _platform_key(platform):
    info = _platforms.resolve(platform) or {}
    return info.get('binTool') or str(platform or '').lower()


def _log_tail(adb, serial, lines=200, tag='zkgui'):
    cmd = 'logcat -d -t %d' % int(lines)
    if tag:
        cmd += ' -s %s' % tag
    rc, out, err = _adb.shell_rc(adb, serial, cmd, timeout=45)
    return (out or '') if rc == 0 else ''


def _as_list(v):
    if v is None or v == '':
        return []
    if isinstance(v, (list, tuple)):
        return [str(x) for x in v]
    return [str(v)]


def _dev_key(serial):
    """设备的短标识（用于按设备区分基线 key）：`198.51.100.108:5555` → `108`。"""
    s = str(serial or '').split(':')[0]
    parts = [p for p in s.split('.') if p]
    if len(parts) >= 2 and all(p.isdigit() for p in parts):
        return parts[-1]
    return _safe_name(s)


def _one_step(step, i, ctx):
    """执行单步 → 结果字典（status: pass | fail | error | no-baseline）。"""
    adb, serial, touch = ctx['adb'], ctx['serial'], ctx['touch']
    res, shot_dir = ctx['res'], ctx['shotDir']
    act = step['action']
    name = step.get('name') or ('%s#%d' % (act, i + 1))
    r = {'index': i + 1, 'name': name, 'action': act, 'status': 'pass', 'detail': {}}
    t0 = time.time()
    cmd = ''
    if act == 'tap':
        cmd = '%s tap %d %d' % (touch, int(step.get('x', 0)), int(step.get('y', 0)))
    elif act == 'long':
        cmd = '%s long %d %d %d' % (touch, int(step.get('x', 0)), int(step.get('y', 0)),
                                    int(step.get('ms', 1000)))
    elif act == 'swipe':
        fr = step.get('from') or [0, 0]
        to = step.get('to') or [0, 0]
        cmd = '%s swipe %d %d %d %d %d' % (touch, int(fr[0]), int(fr[1]), int(to[0]),
                                           int(to[1]), int(step.get('duration', 300)))
    elif act == 'monkey':
        cmd = '%s monkey %d %d %d' % (touch, int(step.get('width', 0) or res[0]),
                                      int(step.get('height', 0) or res[1]),
                                      int(step.get('count', 200)))
    elif act == 'run':
        if not step.get('script'):
            r.update(status='error', detail={'error': 'action=run 缺 script（设备侧脚本路径）'})
            r['ms'] = int((time.time() - t0) * 1000)
            return r
        cmd = '%s run %s' % (touch, step['script'])
    elif act == 'wait':
        time.sleep(max(0, int(step.get('ms', 500))) / 1000.0)
    if cmd:
        rc, out, err = _adb.shell_rc(adb, serial, cmd, timeout=int(step.get('timeout', 90)))
        r['detail']['cmd'] = cmd
        r['detail']['rc'] = rc
        if rc != 0:
            r['status'] = 'error'
            r['detail'].update(error='注入命令失败（rc=%s）' % rc,
                               out=(out or '')[-300:], err=(err or '')[-300:])
            r['ms'] = int((time.time() - t0) * 1000)
            return r
    # ---- 截图（+ 像素基线对比）----
    shot = step.get('shot') or ('shot_%d' % (i + 1) if act == 'shot' else '')
    if shot and ctx.get('keySuffix'):
        # 多设备同一份用例：基线 key **按设备区分**（panel@108 / panel@71）
        # —— 否则「两台机器本来就不在同一页」会被当成回归差异（真机实测踩过）
        shot = '%s@%s' % (shot, ctx['keySuffix'])
    if shot:
        os.makedirs(shot_dir, exist_ok=True)
        png = os.path.join(shot_dir, '%s.png' % _safe_name(shot))
        cap = None
        try:
            import device_screenshot as dss
            cap = dss.capture(device=serial, out=png, fmt='png')
        except Exception as e:
            cap = {'success': False, 'error': '抓屏异常: %s' % e}
        if not (isinstance(cap, dict) and cap.get('success') and os.path.isfile(png)):
            r['status'] = 'error'
            r['detail'].update(error='抓屏失败',
                               shotError=(cap or {}).get('error', ''),
                               shotHint=(cap or {}).get('hint', ''))
            r['ms'] = int((time.time() - t0) * 1000)
            return r
        r['detail']['shot'] = png
        mode = ctx['baselineMode']
        broot = ctx['baselineRoot']
        # 容差优先序：**步骤指定 > 运行级指定 > 基线登记的档案（None）**
        # （复检 #2 抓到：以前总把 0 显式传给 compare，把基线里存的容差覆盖掉了）
        if step.get('allowRegions') is not None:
            allow_val = int(step['allowRegions'])
        elif ctx.get('allowSpecified'):
            allow_val = int(ctx.get('allowRegions') or 0)
        else:
            allow_val = None
        if broot and mode != 'off':
            import ui_baseline as ubl
            if mode == 'save':
                sv = ubl.save(broot, png, key=shot, name=name, source='test_run',
                              replace=True,
                              allow_regions=(0 if allow_val is None else allow_val))
                r['detail']['baseline'] = {'mode': 'save', 'key': shot,
                                           'ok': bool(sv.get('success')),
                                           'error': sv.get('error', '')}
                if not sv.get('success'):
                    r['status'] = 'error'
                    r['detail']['error'] = '存基线失败: %s' % sv.get('error')
            else:
                cp = ubl.compare(broot, png, key=shot, allow_regions=allow_val)
                st = cp.get('status')
                r['detail']['baseline'] = {'mode': 'compare', 'key': shot, 'status': st,
                                           'regionCount': cp.get('regionCount'),
                                           'allowRegions': cp.get('allowRegions'),
                                           'toleranceFrom': ('step' if step.get('allowRegions')
                                                             is not None else
                                                             ('run' if ctx.get('allowSpecified')
                                                              else 'baseline')),
                                           'diffPng': cp.get('diffPng', ''),
                                           'error': cp.get('error', '')}
                if st == 'pass':
                    pass
                elif st == 'no-baseline':
                    # 状态永远是 no-baseline（机器可读的真相）；但 baseline=compare 是**严格模式**：
                    # 明确要求回归比对却没有基线 → 报告里按失败算（auto 才算 skipped）。
                    r['status'] = 'no-baseline'
                    if mode != 'auto':
                        r['detail']['baseline']['strict'] = True
                        r['detail']['error'] = ('基线库里没有 key=%s（baseline=%s 为严格模式，缺基线按失败算；'
                                                '首次请先用 baseline="save" 建基线）' % (shot, mode))
                else:
                    r['status'] = 'fail'
    # ---- 日志断言 ----
    exp_in = _as_list(step.get('expectLog'))
    exp_no = _as_list(step.get('expectNoLog'))
    if act == 'log' or exp_in or exp_no:
        tail = _log_tail(adb, serial, int(step.get('lines', 200)), step.get('tag', 'zkgui'))
        r['detail']['logLines'] = len(tail.splitlines())
        miss = [s for s in exp_in if s not in tail]
        hit_bad = [s for s in exp_no if s in tail]
        if miss or hit_bad:
            r['status'] = 'fail'
            parts = []
            if miss:
                parts.append('日志里没出现: %s' % miss)
            if hit_bad:
                parts.append('日志里不该出现: %s' % hit_bad)
            r['detail']['error'] = '日志断言未过 —— ' + '；'.join(parts)
            r['detail']['logTail'] = tail[-600:]
        else:
            r['detail']['logAssert'] = {'expectLog': len(exp_in),
                                        'expectNoLog': len(exp_no), 'ok': True}
    if step.get('wait') and cmd:
        time.sleep(max(0, int(step['wait'])) / 1000.0)
    r['ms'] = int((time.time() - t0) * 1000)
    return r


def _run_on_device(dev, plan, adb, out_root, platform, baseline, allow, resolution,
                   dev_count=1, per_device='auto'):
    serial = dev.get('serial')
    t0 = time.time()
    notes, errors = [], []
    res = {'serial': serial, 'model': dev.get('model', ''), 'ok': False, 'steps': [],
           'notes': notes, 'errors': errors, 'ms': 0}
    use, perr = _platform_of(dev, platform)
    res['platform'] = use
    if not use:
        errors.append(perr or '平台判定失败')
        res['ms'] = int((time.time() - t0) * 1000)
        return res
    out_dir = os.path.join(out_root, _safe_name(serial))
    shot_dir = os.path.join(out_dir, 'shots')
    os.makedirs(shot_dir, exist_ok=True)
    res['reportDir'] = out_dir
    touch, terr = _deploy_touch(serial, adb, use, notes)
    if not touch:
        errors.append(terr or '注入工具部署失败')
        res['ms'] = int((time.time() - t0) * 1000)
        return res
    res['tool'] = os.path.basename(touch)
    plan_allow = plan.get('allowRegions')
    if plan_allow is not None:
        a_spec, a_val = True, int(plan_allow)
    elif int(allow or 0) > 0:
        a_spec, a_val = True, int(allow)
    else:
        a_spec, a_val = False, 0        # 都没指定 → 用基线里登记的容差档案
    ctx = {'adb': adb, 'serial': serial, 'touch': touch, 'res': resolution,
           'shotDir': shot_dir, 'baselineRoot': plan.get('baselineRoot') or '',
           'baselineMode': (plan.get('baseline') or baseline),
           'allowRegions': a_val, 'allowSpecified': a_spec,
           'keySuffix': (_dev_key(serial) if _per_device_on(per_device, dev_count) else '')}
    if ctx['keySuffix']:
        notes.append('%s: 基线 key 带设备标识（@%s）—— 多设备同一用例必须区分，'
                     '否则会把“两台内容不同”误报成回归' % (serial, ctx['keySuffix']))
    for i, step in enumerate(plan['steps']):
        try:
            r = _one_step(step, i, ctx)
        except Exception as e:
            r = {'index': i + 1, 'name': step.get('name') or step.get('action'),
                 'action': step.get('action'), 'status': 'error',
                 'detail': {'error': '步骤执行异常: %s' % e}, 'ms': 0}
        res['steps'].append(r)
    res['ok'] = bool(res['steps']) and all(s['status'] == 'pass' for s in res['steps'])
    res['ms'] = int((time.time() - t0) * 1000)
    try:
        with open(os.path.join(out_dir, 'logcat.txt'), 'w', encoding='utf-8') as f:
            f.write(_log_tail(adb, serial, 400, 'zkgui'))
        res['logcat'] = os.path.join(out_dir, 'logcat.txt')
    except Exception as e:
        errors.append('logcat 落盘失败: %s' % e)
    return res


def _safe_name(s):
    return ''.join(c if (c.isalnum() or c in '._-') else '_' for c in str(s)) or 'x'


def _xattr(v):
    """XML 属性值转义（**必须含引号**，否则 message 里的 " 会把属性截断 → XML 非法，CI 直接解析失败）。"""
    return _xml.escape(str(v or ''), {'"': '&quot;', "'": '&apos;'})


def _junit_xml(plan_name, devices, summary):
    esc = _xattr
    cases, fails, errs, skips = [], 0, 0, 0
    for d in devices:
        devname = d.get('serial') or 'device'
        if not d.get('steps'):
            errs += 1
            cases.append('<testcase classname="%s" name="deploy"><error message="%s"/></testcase>'
                         % (esc(devname), esc('; '.join(d.get('errors') or ['部署失败']))))
            continue
        for s in d['steps']:
            nm = '%s / %s' % (s.get('action'), s.get('name'))
            st = s.get('status')
            body = ''
            if st == 'fail':
                fails += 1
                body = '<failure message="%s"/>' % esc((s.get('detail') or {}).get('error', 'fail'))
            elif st == 'error':
                errs += 1
                body = '<error message="%s"/>' % esc((s.get('detail') or {}).get('error', 'error'))
            elif st == 'no-baseline':
                det = s.get('detail') or {}
                if (det.get('baseline') or {}).get('strict'):
                    fails += 1          # 严格模式（baseline=compare）：缺基线按失败
                    body = '<failure message="%s"/>' % esc(det.get('error') or '缺基线')
                else:
                    skips += 1
                    body = '<skipped message="基线库中没有该 key，未做像素判定"/>'
            cases.append('<testcase classname="%s" name="%s" time="%.3f">%s</testcase>'
                         % (esc(devname), esc(nm), (s.get('ms', 0) or 0) / 1000.0, body))
    head = ('<?xml version="1.0" encoding="UTF-8"?>' + '\n'
            + '<testsuites name="%s" tests="%d" failures="%d" errors="%d" skipped="%d">' % (
                esc(plan_name), summary['steps'], fails, errs, skips) + '\n'
            + '<testsuite name="%s" tests="%d" failures="%d" errors="%d" skipped="%d">' % (
                esc(plan_name), summary['steps'], fails, errs, skips) + '\n')
    return head + '\n'.join(cases) + '\n</testsuite>\n</testsuites>\n'


def _per_device_on(mode, dev_count):
    """是否按设备区分基线 key：auto = 多台才开；on/off 显式。"""
    m = str(mode or 'auto').strip().lower()
    if m in ('off', 'false', '0', 'no'):
        return False
    if m in ('on', 'true', '1', 'yes'):
        return True
    return int(dev_count or 1) > 1


def flythings_test_run(plan='', devices='auto', project_root='', out='', platform='',
                       parallel=4, baseline='auto', allow_regions=0,
                       per_device_keys='auto'):
    """多设备并行跑一份用例（触摸注入 + 日志断言 + 像素基线），出 JSON + JUnit 报告。

    plan：用例 JSON（文本或 .json 路径）——steps[].action 取 tap/long/swipe/wait/monkey/run/
      shot/log；step 可带 shot=<基线 key>、expectLog/expectNoLog（日志断言）、wait(ms)。
    devices："auto"（**恰好 1 台才自动选**）|"all"|"<IP>:5555,<IP>:5555"；多台**并行**跑。
    project_root：像素基线库位置（<项目>/ui_baseline/）；baseline=auto/compare/save/off。
    out：报告目录（默认 <项目或仓库>/temp/test_runs/<时间>-<用例名>）。
    返回 summary + reportJson + reportXml；**比不到基线记 no-baseline 并进 warnings，不算通过**。
    """
    root = os.path.abspath(project_root) if project_root else ''
    p, err = _load_plan(plan)
    if err:
        return {'success': False, 'op': 'flythings_test_run', 'error': err, 'planDoc': _PLAN_DOC}
    mode = str(baseline or 'auto').lower()
    if mode not in BASELINE_MODES:
        return {'success': False, 'op': 'flythings_test_run',
                'error': 'baseline 取 %s' % '/'.join(BASELINE_MODES)}
    broot = (p.get('baselineRoot') or root)
    if mode != 'off' and not broot:
        return {'success': False, 'op': 'flythings_test_run',
                'error': 'baseline=%s 需要 project_root（或 plan.baselineRoot）' % mode,
                'hint': '不要像素判定就传 baseline="off"'}
    if broot:
        p['baselineRoot'] = broot
    adb = _adb.resolve_adb()
    if not adb:
        return {'success': False, 'op': 'flythings_test_run',
                'error': '找不到 adb', 'hint': _adb.adb_missing_hint()}
    devs, derr = _select_devices(devices, adb, platform)
    if derr:
        return {'success': False, 'op': 'flythings_test_run', 'error': derr.pop('error', ''),
                'details': derr, 'planDoc': _PLAN_DOC}
    name = _safe_name(p.get('name') or 'ui-test')
    if not out:
        out = os.path.join(root or _BASE, 'temp', 'test_runs',
                           '%s-%s' % (time.strftime('%Y%m%d-%H%M%S'), name))
    out = os.path.abspath(out)
    os.makedirs(out, exist_ok=True)
    resolution = [int(p.get('width', 0) or 0), int(p.get('height', 0) or 0)]
    workers = max(1, min(int(parallel or 4), len(devs)))
    results = []
    if workers == 1 or len(devs) == 1:
        for d in devs:
            results.append(_run_on_device(d, p, adb, out, platform, mode, allow_regions,
                                          resolution, len(devs), per_device_keys))
    else:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs = [ex.submit(_run_on_device, d, p, adb, out, platform, mode,
                              allow_regions, resolution, len(devs), per_device_keys)
                    for d in devs]
            for f in futs:
                results.append(f.result())
    cnt = {'pass': 0, 'fail': 0, 'error': 0, 'no-baseline': 0}
    for d in results:
        for s in d.get('steps', []):
            cnt[s['status']] = cnt.get(s['status'], 0) + 1
    summary = {'devices': len(results), 'devicesOk': sum(1 for d in results if d['ok']),
               'steps': sum(len(d.get('steps', [])) for d in results),
               'pass': cnt['pass'], 'fail': cnt['fail'], 'error': cnt['error'],
               'noBaseline': cnt['no-baseline'],
               'parallelWorkers': workers, 'ms': sum(d.get('ms', 0) for d in results)}
    warnings = []
    nb = sorted({s['name'] for d in results for s in d.get('steps', [])
                 if s['status'] == 'no-baseline'})
    if nb:
        warnings.append('%d 个截图步骤**没有基线可比**（记 no-baseline，不算通过）：%s'
                        % (cnt['no-baseline'], '；'.join(nb)))
    for d in results:
        for e in d.get('errors', []):
            warnings.append('%s: %s' % (d.get('serial'), e))
    rjson = os.path.join(out, 'report.json')
    rxml = os.path.join(out, 'report.xml')
    payload = {'plan': name, 'startedAt': time.strftime('%Y-%m-%d %H:%M:%S'),
               'summary': summary, 'devices': results, 'warnings': warnings}
    with open(rjson, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    with open(rxml, 'w', encoding='utf-8') as f:
        f.write(_junit_xml(name, results, summary))
    ok = bool(results) and all(d['ok'] for d in results) and not cnt['no-baseline']
    return {'success': ok, 'op': 'flythings_test_run', 'plan': name, 'baselineMode': mode,
            'perDeviceKeys': _per_device_on(per_device_keys, len(devs)),
            'summary': summary, 'devices': results, 'warnings': warnings,
            'reportJson': rjson, 'reportXml': rxml, 'out': out,
            'hint': ('success=false 常见原因：有 fail/error 步骤；或截图没有基线'
                     '（先 baseline="save" 建基线，再 baseline="compare" 卡回归）')}


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
