# -*- coding: utf-8 -*-
"""build_example.py —— 最小接入示例（端到端，可重复跑）

做三件事：
  1) 调 `../scripts/gen_icons.py` 按**语义名**把示例用到的图标生成到
     `app/resources/images/`（生成器保证"图片像素尺寸 == 请求尺寸"）；
  2) 写一份真的 FlyThings 布局 json（`app/ui/main.json`），每个图标控件的
     `position` 都与对应图片的像素尺寸一致；
  3) 校验 + 出预览图（把图标按控件位置拼到背景上）。

图标名走 catalog.json（`--name` 语义名 + 可选 `--state off|on`），所以示例代码里
**看不到 tabler 文件名**——换图标只改语义名。

用法：
    python example/build_example.py            # 生成 + 写 json + 校验 + 预览图
    python example/build_example.py --check    # 只校验图片尺寸与控件盒是否一致
"""

import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MODULE = os.path.dirname(HERE)
APP = os.path.join(HERE, 'app')
IMAGES = os.path.join(APP, 'resources', 'images')
UI = os.path.join(APP, 'ui')

# (控件类型, caption, id, left, top, size, 语义图标名, 状态, 说明)
LAYOUT = [
    ('textview', 'ImgWeatherBig', 50001, 40, 26, 56, 'weather.partly-cloudy', 'on', '天气大图标'),
    ('textview', 'ImgWeatherRain', 50002, 112, 44, 22, 'weather.rain', '', '天气小图标'),
    ('textview', 'ImgWeatherSnow', 50003, 142, 44, 22, 'weather.snow', '', '天气小图标'),
    ('textview', 'ImgWeatherWind', 50004, 172, 44, 22, 'weather.wind', '', '天气小图标'),
    ('textview', 'ImgWifi', 50005, 640, 30, 22, 'system.wifi', '', '状态栏 wifi'),
    ('textview', 'ImgBattery', 50006, 672, 30, 22, 'system.battery-3', 'on', '状态栏电量'),
    ('textview', 'ImgSignal', 50007, 704, 30, 22, 'system.signal', '', '状态栏信号'),
    ('textview', 'ImgBack', 50008, 24, 130, 22, 'control.arrow-left', '', '返回箭头'),
    ('textview', 'ImgLight', 50009, 60, 200, 32, 'device.bulb', 'on', '设备：灯（on）'),
    ('textview', 'ImgFan', 50010, 108, 200, 32, 'device.windmill', 'on', '设备：风扇'),
    ('textview', 'ImgAc', 50011, 156, 200, 32, 'device.air-conditioning', '', '设备：空调'),
    ('textview', 'ImgTv', 50012, 204, 200, 32, 'device.tv', 'on', '设备：电视'),
    ('button', 'BtnToggleOff', 20001, 480, 196, 44, 'control.toggle-left', 'off', '开关（关）'),
    ('button', 'BtnToggleOn', 20002, 560, 196, 44, 'control.toggle-right', 'on', '开关（开）'),
    ('button', 'BtnCheck', 20003, 480, 264, 22, 'control.checkbox', '', '复选框（未选）'),
    ('button', 'BtnCheckOn', 20004, 520, 264, 22, 'control.square-check', 'on', '复选框（已选）'),
    ('button', 'BtnStar', 20005, 560, 250, 44, 'system.star', 'on', '收藏（已选）'),
    ('button', 'BtnMore', 20006, 660, 130, 22, 'system.more', 'on', '更多'),
]

RES = (800, 480)
BG = (0x12 << 16) | (0x16 << 8) | 0x1E


def _catalog():
    with open(os.path.join(MODULE, 'catalog.json'), encoding='utf-8') as f:
        return json.load(f)


def png_of(cat, icon, state):
    """语义名 + 状态 → 产物文件名（单态图标自动不带状态后缀）。"""
    for it in cat['icons']:
        if it['name'] == icon:
            style = it['styles'][0]
            v = it['variants'][style]
            if state and state in v['files']:
                return v['files'][state]
            if not state:
                return v['files'][list(v['files'])[0]]
            return v['files'][list(v['files'])[0]]
    raise SystemExit('catalog 里没有图标 %r' % icon)


def gen_images():
    cat = _catalog()
    py = sys.executable
    gen = os.path.join(MODULE, 'scripts', 'gen_icons.py')
    for it in LAYOUT:
        name, state = it[6], it[7]
        cmd = [py, gen, '--name', name, '--size', str(it[5]), '--color', '255,255,255',
               '--out', IMAGES]
        if state:
            cmd += ['--state', state]
        r = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8',
                           env=dict(os.environ, PYTHONIOENCODING='utf-8'))
        if r.returncode != 0:
            print(r.stdout, r.stderr)
            raise SystemExit('生成 %s(%s) 失败' % (name, state))
        print('  + %-34s %s  %dpx' % (png_of(cat, name, state), state or '-', it[5]))


def build_json():
    cat = _catalog()
    doc = {
        'beepEnable': True, 'id': 0,
        'resolution': {'width': RES[0], 'height': RES[1]},
        'topmost': False, 'backgroundColor': BG,
        'position': {'left': 0, 'top': 0, 'width': RES[0], 'height': RES[1]},
    }
    for i, (kind, caption, cid, left, top, size, icon, state, _d) in enumerate(LAYOUT):
        image = png_of(cat, icon, state)
        item = {'caption': caption, 'id': cid,
                'position': {'left': left, 'top': top, 'width': size, 'height': size},
                'colorTab': {'color0': 16777215}, 'fontSize': 16, 'alignment': 36}
        if kind == 'button':
            item.update(touchable=True, alignment=37, text='',
                        picTab={'pic0': 'images/%s' % image})
        else:
            item.update(touchable=False, backgroundPic='images/%s' % image)
        doc['%s__%d' % (kind, i + 1)] = item
    os.makedirs(UI, exist_ok=True)
    p = os.path.join(UI, 'main.json')
    with open(p, 'w', encoding='utf-8') as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
        f.write('\n')
    return p


def check():
    """校验：每张图片存在、像素尺寸 == json 里控件 position 的宽高。"""
    from PIL import Image
    with open(os.path.join(UI, 'main.json'), encoding='utf-8') as f:
        doc = json.load(f)
    bad = 0
    for k, v in doc.items():
        if '__' not in k or not isinstance(v, dict):
            continue
        img = v.get('backgroundPic') or (v.get('picTab') or {}).get('pic0')
        if not img:
            continue
        path = os.path.join(APP, 'resources', img.replace('/', os.sep))
        if not os.path.isfile(path):
            print('  × 缺图：%s' % img)
            bad += 1
            continue
        w, h = Image.open(path).size
        pos = v['position']
        tag = 'OK ' if (w, h) == (pos['width'], pos['height']) else 'BAD'
        if tag == 'BAD':
            bad += 1
        print('  %s %-44s 图 %dx%d  控件 %dx%d' % (tag, img, w, h, pos['width'], pos['height']))
    print('--- %s：%d 处不一致' % ('PASS' if not bad else 'FAIL', bad))
    return bad


def render_preview():
    """把布局里的图标按控件位置拼到背景上 → example/preview.png（审阅用）。"""
    from PIL import Image
    canvas = Image.new('RGBA', RES, (0x12, 0x16, 0x1E, 255))
    for it in LAYOUT:
        p = os.path.join(IMAGES, png_of(_catalog(), it[6], it[7]))
        if os.path.isfile(p):
            canvas.alpha_composite(Image.open(p).convert('RGBA'), (it[3], it[4]))
    out = os.path.join(HERE, 'preview.png')
    canvas.convert('RGB').save(out)
    return out


def main(argv):
    if '--check' in argv:
        return 1 if check() else 0
    print('[1/3] 生成图标 → app/resources/images/')
    gen_images()
    print('[2/3] 写布局 → app/ui/main.json')
    print('      %s' % build_json())
    print('校验图片尺寸与控件盒：')
    check()
    print('[3/3] 预览图 → example/preview.png')
    print('      %s' % render_preview())
    print('\n下一步（在工程里）：')
    print('  fui pack app/ui/main.json        # 或 flythings_fui_pack，设备实际加载 ftu')
    print('  fsc build -p <平台> && fsc launch -p <平台>   # 或 flythings_build_ui_flow')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
