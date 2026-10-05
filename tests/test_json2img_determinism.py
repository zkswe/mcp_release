# -*- coding: utf-8 -*-
"""`json2img` 的**确定性基线**（T2.3）：同一份输入 → 同一串字节；基线**绑定渲染器版本**。

为什么必须钉（2026-10-05 需求方口径）：
> 「现在离线可以用 json2img 来判定。这个可以作为判定依据，如果后期有差异我们来完善 json2img。」

"离线判定"成立的**前提**是确定性：`json2img.py` 头注释把 A/B 像素 diff 定为硬判据
（`REMEDIATION-UI-PIPELINE.md` §2 档②），而同输入同输出是它的地基 —— 渲染器只要引入
集合遍历顺序、时间戳、随机采样、字体回退漂移中的任意一条，A/B diff 就会把"渲染器的抖动"
报成"界面的差异"，判据当场失效。所以这里钉两件事：

  ① 同 json + 同资源 + 同字体 → 渲染两次的 PNG **md5 相同**（并且换个进程、换 PYTHONHASHSEED 也相同）；
  ② `EXPECTED_RENDERER_VERSION == json2img.__version__` —— **基线绑定渲染器版本**：
     改了渲染器版本就必须**同批**更新本用例里的期望值，并在提交信息里说清"基线为什么需要重算"，
     防的是"改渲染器让老基线静默失效"（老基线悄悄不再代表当前实现，却还在绿灯放行）。

反面对照也在本文件里（否则"两次 md5 相等"可能只是因为两次都渲染了同一张空图）：
输入改 1px / 改文字 → md5 必须**不同**；页面必须真的画出了轨道色与文字色。
"""
import hashlib
import io
import json
import os
import subprocess
import sys
import unittest

import _util as U

sys.path.insert(0, U.BASE)
sys.path.insert(0, os.path.join(U.BASE, 'ui_tools'))
import json2img as J  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

# ============================================================================
# ★ 基线锚点：渲染器版本。改 `json2img.__version__` 就必须**同批**改这里（见文件头 ②）。
#   为什么用等号而不是"大于等于"：基线是"这一版渲染器的像素行为"的快照，版本变了，
#   快照与实现是否还对应必须由人重新确认一次 —— 静默通过等于基线失效。
# ============================================================================
EXPECTED_RENDERER_VERSION = '0.1.1'   # 0.1.1：颜色语义修正（-1 才是不填充；负数按 0xAARRGGBB）

TRACK = (36, 47, 73, 255)          # 轨道色
FILL = (46, 139, 255, 255)         # 填充色
TEXT_LUMA = 200                    # "文字画出来了"的亮度阈值（文字色是 0xFFFFFF，见 PAGE 里的 color0）
SEEK_BOX = (16, 120, 448, 32)      # left, top, w, h
TEXT_BOX = (16, 40, 448, 40)


class DeterminismBase(unittest.TestCase):
    """最小工程夹具：一个 `textview` + 一个 `seekbar`（参考 `test_json2img_engine_model.py` 的写法）。"""

    def setUp(self):
        self.tmp = U.project()
        self.imgdir = os.path.join(self.tmp, 'resources', 'images')
        os.makedirs(self.imgdir, exist_ok=True)

    def tearDown(self):
        U.cleanup(self.tmp)

    def asset(self, name, size, color):
        Image.new('RGBA', size, color).save(os.path.join(self.imgdir, name))
        return 'images/' + name

    def doc(self, text='Hello 进度', dx=0):
        """页面 json：textview + seekbar。`dx`/`text` 用于"输入变了，字节必须变"的反面对照。"""
        track = self.asset('track.png', (SEEK_BOX[2], SEEK_BOX[3]), TRACK)
        fill = self.asset('fill.png', (SEEK_BOX[2], SEEK_BOX[3]), FILL)
        return {
            # ⚠️ 颜色写**正数**（0x101418 = 不透明深色）：本渲染器把 -1 当"不绘制"，
            # 而其它负值同样落进"不填充"分支（`color_rgba` 只认 v<0 → None），
            # 用负数会让根底色悄悄不画、还多记一条 root/backgroundColor 记账（不是本用例要测的东西）。
            'resolution': {'width': 480, 'height': 800},
            'position': {'left': 0, 'top': 0, 'width': 480, 'height': 800},
            'backgroundColor': 0x101418,
            'textview__1': {
                'text': text, 'fontSize': 24, 'alignment': 36,       # 36 = 靠左 + 垂直居中（实测值）
                'colorTab': {'color0': 0xFFFFFF},
                'position': {'left': TEXT_BOX[0] + dx, 'top': TEXT_BOX[1],
                             'width': TEXT_BOX[2], 'height': TEXT_BOX[3]},
            },
            'seekbar__1': {
                'backgroundPic': track, 'progressPic': fill,
                'defProgress': 60, 'max': 100,
                'thumb': {'size': {'width': 0, 'height': 0}, 'normalPic': '', 'pressedPic': ''},
                'position': {'left': SEEK_BOX[0] + dx, 'top': SEEK_BOX[1],
                             'width': SEEK_BOX[2], 'height': SEEK_BOX[3]},
            },
        }

    def write_page(self, doc, name='main'):
        jp = os.path.join(self.tmp, 'ui', '%s.json' % name)
        os.makedirs(os.path.dirname(jp), exist_ok=True)
        with io.open(jp, 'w', encoding='utf-8') as f:
            json.dump(doc, f, ensure_ascii=False)
        return jp

    def render_twice(self, doc):
        """同一份 json 渲染两次（不同输出文件）→ (md5, md5, info1, info2)。"""
        jp = self.write_page(doc)
        md5s, infos = [], []
        for i in (1, 2):
            out = os.path.join(self.tmp, 'ui', 'r%d.png' % i)
            info = J.render_one(self.tmp, jp, out, report=J.Report(), verbose=False)
            with io.open(out, 'rb') as f:
                md5s.append(hashlib.md5(f.read()).hexdigest())
            infos.append(info)
        return md5s[0], md5s[1], infos[0], infos[1]

    def md5_of(self, path):
        with io.open(path, 'rb') as f:
            return hashlib.md5(f.read()).hexdigest()


class TestBaselineIsPinned(DeterminismBase):
    """② 基线绑定渲染器版本。"""

    def test_expected_version_matches_the_renderer(self):
        self.assertTrue(EXPECTED_RENDERER_VERSION,
                        '本用例必须显式登记基线对应的渲染器版本（不许留空）')
        self.assertEqual(
            EXPECTED_RENDERER_VERSION, J.__version__,
            '渲染器版本已变（基线登记 %s，实现是 %s）：改了渲染器就要**同批**更新本用例里的'
            'EXPECTED_RENDERER_VERSION，并说明"基线为什么需要重算"（旧基线不再代表当前实现，'
            '静默通过 = 基线失效）' % (EXPECTED_RENDERER_VERSION, J.__version__))

    def test_baseline_constant_is_documented_in_this_file(self):
        """锚点必须住在**本用例文件**里（换个人接手要一眼看见"改版本要同批改这里"）。"""
        src = io.open(os.path.abspath(__file__), encoding='utf-8').read()
        self.assertIn('EXPECTED_RENDERER_VERSION', src)
        self.assertIn('同批', src, '要写明"版本变了必须同批更新基线"')


class TestSameInputSameBytes(DeterminismBase):
    """① 同 json + 同资源 + 同字体 → 两次渲染字节相同。"""

    def test_two_renders_are_byte_identical(self):
        md5a, md5b, a, b = self.render_twice(self.doc())
        self.assertEqual(md5a, md5b, '同一份输入渲染两次得到不同字节 —— A/B 像素 diff 判据不成立')
        self.assertEqual(a['size'], b['size'])
        self.assertEqual(a['font'], b['font'], '两次渲染必须用同一个字体（否则比的是字体差异）')
        if a['font']:
            self.assertTrue(os.path.isfile(a['font']), '用到的字体必须是真实文件：%s' % a['font'])

    def test_two_processes_are_byte_identical(self):
        """跨进程也相同（不同 PYTHONHASHSEED）：防"渲染顺序依赖 set/dict 的哈希顺序"。"""
        jp = self.write_page(self.doc())
        cli = os.path.join(U.BASE, 'ui_tools', 'json2img.py')
        md5s = []
        for seed in ('0', '12345'):
            out = os.path.join(self.tmp, 'ui', 'seed%s.png' % seed)
            env = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONHASHSEED=seed)
            p = subprocess.run([sys.executable, cli, jp, '--out', out],
                               capture_output=True, text=True, encoding='utf-8',
                               errors='replace', env=env)
            self.assertEqual(p.returncode, 0, 'CLI 渲染失败：%s%s'
                             % (p.stdout[-400:], p.stderr[-400:]))
            md5s.append(self.md5_of(out))
        self.assertEqual(md5s[0], md5s[1],
                         '换 PYTHONHASHSEED 后字节不同 → 渲染顺序依赖哈希顺序（跨机/跨版本会漂）')

    def test_rendered_page_actually_has_content(self):
        """正面判据：两次相等的**不是空图** —— 轨道色、填充色、文字色都得真画出来。

        为什么单列：只比"两次 md5 相等"时，一个"什么都不画"的渲染器也能通过；
        确定性的前提是"确实画了东西且每次一样"。
        """
        jp = self.write_page(self.doc())
        out = os.path.join(self.tmp, 'ui', 'r.png')
        J.render_one(self.tmp, jp, out, report=J.Report(), verbose=False)
        with Image.open(out) as im:
            im = im.convert('RGBA')
        l, t, w, h = SEEK_BOX
        y = t + h // 2
        self.assertEqual(im.getpixel((l + 10, y))[:3], FILL[:3], '进度条填充没画出来')
        self.assertEqual(im.getpixel((l + w - 10, y))[:3], TRACK[:3], '进度条轨道没画出来')
        tl, tt, tw, th = TEXT_BOX
        # 判"文字画出来了"用**亮度阈值**而不是精确等色：不同机器的兜底字体不同，
        # 抗锯齿边缘不保证有纯 255 像素（钉死等色会让这条判据在别的机器上假红）。
        lit = [1 for yy in range(tt, tt + th) for x in range(tl, tl + tw)
               if min(im.getpixel((x, yy))[:3]) > TEXT_LUMA]
        self.assertTrue(lit, '文字没画出来（渲染成空图时"字节相等"毫无意义）')

    def test_different_input_gives_different_bytes(self):
        """反面对照：输入改 1px / 改文字 → 字节必须变（证明本用例的比较**抓得住**差异）。"""
        md5a, _, _, _ = self.render_twice(self.doc())
        md5b, _, _, _ = self.render_twice(self.doc(dx=1))
        self.assertNotEqual(md5a, md5b, '控件挪 1px 后字节竟然相同 —— 本用例的比较是假的')
        md5c, _, _, _ = self.render_twice(self.doc(text='Hello 进度 2'))
        self.assertNotEqual(md5b, md5c, '文字变了字节却相同 —— 本用例的比较是假的')


if __name__ == '__main__':
    unittest.main()
