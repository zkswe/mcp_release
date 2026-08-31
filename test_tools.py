# -*- coding: utf-8 -*-
"""FlyThings UI 自动化测试生成器（纯代码，不依赖 AI）。

核心思路：
  ui/*.json 布局本身已包含全部控件坐标（position left/top/width/height）与
  可交互信息（touchable/visible）——直接解析 json 生成可编译的 bin 测试项目：
    - traverse 遍历控件验收：逐个点击所有可交互控件中心点 + 资源缺失检查 + logcat 校验
    - monkey 压测：随机 tap/swipe 循环
    - custom 自定义：返回提示，由用户提供要求（差异化逻辑可再走 AI）

产物形态：bin 项目（fun.json + src/main.cpp，触摸注入代码基于 event.c 方法），
可选 fun build 编译成 ELF，adb push 到设备直接跑。
"""
import json, os, re, subprocess, shutil

_BASE = os.path.dirname(os.path.abspath(__file__))

# 可交互控件类型（touchable=true 时生成点击）
INTERACTIVE_TYPES = ('button', 'checkbox', 'radiogroup', 'edittext', 'seekbar',
                     'slidewindow', 'scrollwindow', 'pagewindow', 'videoview',
                     'qrcode', 'cameraview', 'imageanim')
# 滑动类控件（生成 swipe 而非 tap）
SWIPE_TYPES = ('seekbar', 'slidewindow', 'scrollwindow', 'pagewindow')

# 触摸注入 C 代码模板（基于 LearningProject/input event.c 方法）
TOUCH_C = r'''
#include <stdio.h>
#include <unistd.h>
#include <fcntl.h>
#include <string.h>
#include <stdlib.h>
#include <time.h>
#include <errno.h>
#include <stdint.h>
#include <linux/input.h>
#include <sys/time.h>

/* ---- 触摸注入（event.c 方法） ---- */
static int reportkey(int fd, uint16_t type, uint16_t code, int32_t value) {
    struct input_event event;
    event.type = type; event.code = code; event.value = value;
    gettimeofday(&event.time, 0);
    if (write(fd, &event, sizeof(struct input_event)) < 0) {
        fprintf(stderr, "report key error %s!\n", strerror(errno));
        return -1;
    }
    return 0;
}

/* 按下 */
static int touch_down(int fd, int x, int y) {
    reportkey(fd, EV_ABS, ABS_X, x);
    reportkey(fd, EV_ABS, ABS_Y, y);
    reportkey(fd, EV_ABS, ABS_PRESSURE, 100);
    reportkey(fd, EV_KEY, BTN_TOUCH, 1);
    reportkey(fd, EV_SYN, EV_SYN, EV_SYN);
    return 0;
}

/* 抬起 */
static int touch_up(int fd) {
    reportkey(fd, EV_ABS, ABS_PRESSURE, 0);
    reportkey(fd, EV_KEY, BTN_TOUCH, 0);
    reportkey(fd, EV_SYN, EV_SYN, EV_SYN);
    return 0;
}

/* 移动一步 */
static int touch_move(int fd, int x, int y) {
    reportkey(fd, EV_ABS, ABS_X, x);
    reportkey(fd, EV_ABS, ABS_Y, y);
    reportkey(fd, EV_SYN, EV_SYN, EV_SYN);
    return 0;
}

/* 点击 */
static void tap(int fd, int x, int y) {
    touch_down(fd, x, y);
    usleep(60 * 1000);
    touch_up(fd);
}

/* 滑动（中点插值） */
static void swipe(int fd, int x1, int y1, int x2, int y2) {
    touch_down(fd, x1, y1);
    int dx = x2 - x1, dy = y2 - y1;
    int steps = (abs(dx) > abs(dy) ? abs(dx) : abs(dy)) / 8;
    if (steps < 4) steps = 4;
    for (int i = 1; i <= steps; i++) {
        touch_move(fd, x1 + dx * i / steps, y1 + dy * i / steps);
        usleep(8 * 1000);
    }
    usleep(40 * 1000);
    touch_up(fd);
}

/* 长按 */
static void long_press(int fd, int x, int y, int ms) {
    touch_down(fd, x, y);
    usleep(ms * 1000);
    touch_up(fd);
}

/* ---- 被测控件表（由 ui json 自动生成） ---- */
typedef struct {
    const char *name;   /* caption */
    const char *page;   /* 所在页面 json */
    int x, y;           /* 中心点 */
    int is_swipe;       /* 1=滑动类控件 */
    int sx, sy, ex, ey; /* 滑动起终点（is_swipe=1 时有效） */
} Ctrl;

static const Ctrl kCtrls[] = {
__CONTROLS__
};

static const int kCtrlCount = __CTRL_COUNT__;
static const char *kInputDev = "/dev/input/event1";

int main(int argc, char **argv) {
    if (argc > 1) kInputDev = argv[1];
    int fd = open(kInputDev, O_WRONLY);
    if (fd < 0) {
        fprintf(stderr, "open %s failed: %s\n", kInputDev, strerror(errno));
        return 1;
    }
    printf("[UITEST] device=%s controls=%d start\n", kInputDev, kCtrlCount);
    for (int i = 0; i < kCtrlCount; i++) {
        const Ctrl *c = &kCtrls[i];
        if (c->is_swipe) {
            printf("[UITEST] swipe %s(%s) (%d,%d)->(%d,%d)\n",
                   c->name, c->page, c->sx, c->sy, c->ex, c->ey);
            swipe(fd, c->sx, c->sy, c->ex, c->ey);
        } else {
            printf("[UITEST] tap %s(%s) (%d,%d)\n", c->name, c->page, c->x, c->y);
            tap(fd, c->x, c->y);
        }
        usleep(500 * 1000);  /* 每控件间隔 500ms，便于 logcat 对应 */
    }
    printf("[UITEST] done\n");
    close(fd);
    return 0;
}
'''

MONKEY_C = r'''
#include <stdio.h>
#include <unistd.h>
#include <fcntl.h>
#include <string.h>
#include <stdlib.h>
#include <time.h>
#include <errno.h>
#include <stdint.h>
#include <linux/input.h>
#include <sys/time.h>

/* ---- 触摸注入（event.c 方法） ---- */
static int reportkey(int fd, uint16_t type, uint16_t code, int32_t value) {
    struct input_event event;
    event.type = type; event.code = code; event.value = value;
    gettimeofday(&event.time, 0);
    if (write(fd, &event, sizeof(struct input_event)) < 0) return -1;
    return 0;
}
static int touch_down(int fd, int x, int y) {
    reportkey(fd, EV_ABS, ABS_X, x); reportkey(fd, EV_ABS, ABS_Y, y);
    reportkey(fd, EV_ABS, ABS_PRESSURE, 100); reportkey(fd, EV_KEY, BTN_TOUCH, 1);
    reportkey(fd, EV_SYN, EV_SYN, EV_SYN); return 0;
}
static int touch_up(int fd) {
    reportkey(fd, EV_ABS, ABS_PRESSURE, 0); reportkey(fd, EV_KEY, BTN_TOUCH, 0);
    reportkey(fd, EV_SYN, EV_SYN, EV_SYN); return 0;
}
static int touch_move(int fd, int x, int y) {
    reportkey(fd, EV_ABS, ABS_X, x); reportkey(fd, EV_ABS, ABS_Y, y);
    reportkey(fd, EV_SYN, EV_SYN, EV_SYN); return 0;
}
static void tap(int fd, int x, int y) {
    touch_down(fd, x, y); usleep(60 * 1000); touch_up(fd);
}
static void swipe(int fd, int x1, int y1, int x2, int y2) {
    touch_down(fd, x1, y1);
    int dx = x2 - x1, dy = y2 - y1;
    int steps = (abs(dx) > abs(dy) ? abs(dx) : abs(dy)) / 8;
    if (steps < 4) steps = 4;
    for (int i = 1; i <= steps; i++) {
        touch_move(fd, x1 + dx * i / steps, y1 + dy * i / steps);
        usleep(8 * 1000);
    }
    usleep(40 * 1000);
    touch_up(fd);
}

static int g_w, g_h, g_count, g_seed;

int main(int argc, char **argv) {
    if (argc > 1) { const char *dev = argv[1]; }
    g_w = __SCREEN_W__; g_h = __SCREEN_H__;
    g_count = argc > 3 ? atoi(argv[3]) : __MONKEY_COUNT__;
    g_seed = argc > 4 ? atoi(argv[4]) : (int)time(NULL);
    srand(g_seed);

    const char *dev = argc > 1 ? argv[1] : "/dev/input/event1";
    int fd = open(dev, O_WRONLY);
    if (fd < 0) { fprintf(stderr, "open %s failed: %s\n", dev, strerror(errno)); return 1; }

    printf("[MONKEY] seed=%d screen=%dx%d count=%d start\n", g_seed, g_w, g_h, g_count);
    for (int i = 0; i < g_count; i++) {
        int r = rand() % 100;
        if (r < 65) {  /* 65% 点击 */
            int x = rand() % g_w, y = rand() % g_h;
            printf("[MONKEY] %d/%d tap (%d,%d)\n", i + 1, g_count, x, y);
            tap(fd, x, y);
        } else {       /* 35% 滑动 */
            int x1 = rand() % g_w, y1 = rand() % g_h;
            int x2 = rand() % g_w, y2 = rand() % g_h;
            printf("[MONKEY] %d/%d swipe (%d,%d)->(%d,%d)\n", i + 1, g_count, x1, y1, x2, y2);
            swipe(fd, x1, y1, x2, y2);
        }
        usleep(150 * 1000);
    }
    printf("[MONKEY] done\n");
    close(fd);
    return 0;
}
'''


def _find_fun_exe():
    """定位 fun.exe（复用 project_tools 探测逻辑的简化版）。"""
    cands = [
        os.environ.get('FLYTHINGS_FUN_DIR', ''),
        os.path.join(_BASE, 'toolchain'),
        os.path.join(os.path.dirname(_BASE), 'toolchain'),
        r'D:\zkswe\fun',
        r'C:\zkswe\fun',
    ]
    for d in cands:
        if d and os.path.isfile(os.path.join(d, 'fun.exe')):
            return os.path.join(d, 'fun.exe')
    return 'fun.exe'


FUN_EXE = _find_fun_exe()


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
                # 常见引用方式：resources/images/xxx.png 或相对路径
                candidates = [
                    os.path.join(res_dir, 'images', pic),
                    os.path.join(res_dir, pic),
                    os.path.join(res_dir, 'image', pic),
                ]
                if not any(os.path.isfile(p) for p in candidates):
                    missing.append({'page': pg['file'], 'control': c['key'],
                                    'caption': c['caption'], 'pic': pic})
    return missing


def _gen_traverse_c(pages):
    """生成遍历验收 C 代码。"""
    lines = []
    for pg in pages:
        for c in pg.get('controls', []):
            if c['is_swipe']:
                # 滑动类：从左/上边缘滑到右/下边缘（依控件形状）
                if c['h'] >= c['w']:
                    sx, sy, ex, ey = c['cx'], c['top'] + 2, c['cx'], c['top'] + c['h'] - 2
                else:
                    sx, sy, ex, ey = c['left'] + 2, c['cy'], c['left'] + c['w'] - 2, c['cy']
                lines.append('    { "%s", "%s", %d, %d, 1, %d, %d, %d, %d },' % (
                    (c['caption'] or c['key']).replace('"', '\\"'), pg['file'],
                    c['cx'], c['cy'], sx, sy, ex, ey))
            else:
                lines.append('    { "%s", "%s", %d, %d, 0, 0, 0, 0, 0 },' % (
                    (c['caption'] or c['key']).replace('"', '\\"'), pg['file'],
                    c['cx'], c['cy']))
    return TOUCH_C.replace('__CONTROLS__', '\n'.join(lines) if lines else '    /* 无控件 */') \
                 .replace('__CTRL_COUNT__', str(len(lines)))


def _gen_monkey_c(res_w, res_h, count=500):
    """生成 Monkey 压测 C 代码。"""
    return MONKEY_C.replace('__SCREEN_W__', str(res_w or 1024)) \
                   .replace('__SCREEN_H__', str(res_h or 600)) \
                   .replace('__MONKEY_COUNT__', str(count))


def _write_bin_project(out_dir, project_name, platform, main_c):
    """写 bin 项目（fun.json + src/main.cpp）。"""
    os.makedirs(os.path.join(out_dir, 'src'), exist_ok=True)
    fun_json = {
        'name': project_name, 'version': '1.0.0',
        'platform': platform.lower(), 'description': 'UI auto test (generated)',
        'type': 'executable',
    }
    with open(os.path.join(out_dir, 'fun.json'), 'w', encoding='utf-8') as fh:
        json.dump(fun_json, fh, ensure_ascii=False, indent=2)
    with open(os.path.join(out_dir, 'src', 'main.cpp'), 'w', encoding='utf-8') as fh:
        fh.write(main_c)
    return fun_json


def flythings_gen_ui_test(project_root, test_type='ask', output_dir='',
                          platform='z21', with_build=True, monkey_count=500):
    """根据 UI json 布局生成自动化测试项目（纯代码，不依赖 AI）。

    test_type:
      ask      - 询问用户三种验收方式（默认，返回选项说明）
      traverse - 遍历控件验收：所有可交互控件逐个点击 + 滑动 + 资源缺失检查
      monkey   - 压测 MonkeyTest：随机 tap/swipe，发现潜在隐患
      custom   - 自定义验收：按用户提供的要求生成（差异化逻辑可走 AI）

    output_dir 缺省：在项目同级生成 UiTest_{工程名}/。
    生成 bin 项目（fun.json + src/main.cpp），可选 fun build 编译 ELF。
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

    pages, err = _parse_ui_jsons(root)
    if err:
        return {'success': False, 'error': err}

    # 分辨率取第一页（多页同分辨率）
    res_w = next((p['res_w'] for p in pages if p.get('res_w')), 1024)
    res_h = next((p['res_h'] for p in pages if p.get('res_h')), 600)

    if test_type == 'traverse':
        total = sum(len(p.get('controls', [])) for p in pages)
        if total == 0:
            return {'success': False,
                    'error': '未找到可交互控件（touchable=true 或交互类型）'}
        main_c = _gen_traverse_c(pages)
        missing = _check_resources(root, pages)
        desc = '遍历控件验收: %d 页 %d 个可交互控件' % (len(pages), total)
    elif test_type == 'monkey':
        main_c = _gen_monkey_c(res_w, res_h, monkey_count)
        missing = []
        desc = 'Monkey 压测: %dx%d 随机 %d 次输入' % (res_w, res_h, monkey_count)
    else:  # custom
        return {'success': True, 'needUserInput': True,
                'hint': '请提供自定义验收要求（如：循环点击 A 按钮 100 次后截图校验），'
                        '差异化测试逻辑将由 AI 生成，普通遍历/压测建议用 traverse/monkey 免 AI。'}

    name = os.path.basename(root).strip() or 'UiTest'
    out = os.path.abspath(output_dir) if output_dir else os.path.join(
        os.path.dirname(root), 'UiTest_%s' % name)
    if os.path.isdir(out) and os.listdir(out):
        return {'success': False,
                'error': '输出目录非空: %s（请换 output_dir 或清空）' % out}
    os.makedirs(out, exist_ok=True)
    fun_json = _write_bin_project(out, 'UiTest_%s' % name, platform, main_c)

    result = {
        'success': True,
        'testType': test_type,
        'description': desc,
        'projectRoot': out,
        'pages': len(pages),
        'resolution': '%dx%d' % (res_w, res_h),
        'files': ['fun.json', 'src/main.cpp'],
    }
    if test_type == 'traverse':
        result['controlCount'] = total
        result['resourceCheck'] = {
            'missingCount': len(missing),
            'missing': missing[:20],
        }
    if test_type == 'monkey':
        result['monkeyCount'] = monkey_count

    # 可选编译
    if with_build:
        try:
            rb = subprocess.run([FUN_EXE, 'build'], cwd=out, capture_output=True,
                                text=True, timeout=600, stdin=subprocess.DEVNULL,
                                encoding='utf-8', errors='replace')
            result['buildSuccess'] = rb.returncode == 0
            result['buildLog'] = ((rb.stdout or '') + (rb.stderr or ''))[-800:]
            elf = os.path.join(out, '.fun', platform.lower(), 'UiTest_%s' % name)
            result['outputPath'] = elf if os.path.isfile(elf) else None
            if not result['buildSuccess']:
                result['error'] = 'fun build 失败: %s' % result['buildLog']
        except Exception as e:
            result['buildSuccess'] = False
            result['error'] = 'fun build 异常: %s' % e

    result['deployHint'] = (
        'adb push %s /data/ && adb shell chmod +x /data/UiTest_%s && '
        'adb shell /data/UiTest_%s /dev/input/event1\n'
        '（设备节点按实际 getevent 确认；运行同时 adb logcat 观察 [UITEST]/[MONKEY] 与业务日志）'
        % (os.path.join(out, '.fun', platform.lower(), 'UiTest_%s' % name) if with_build else '<ELF>',
           name, name))
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
