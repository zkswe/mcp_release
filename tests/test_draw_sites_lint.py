# -*- coding: utf-8 -*-
"""出图白名单扫描（T4.2，REMEDIATION-UI-PIPELINE §WS-4）的契约用例。

被测对象 = `scripts/lint_draw_sites.py`（唯一真源：它的 `PRODUCERS` 常量 + 六个原语）。
本文件钉住任务书点名的五条判据（**每条都要能判红**，否则闸门等于没有）：

  ① 真仓 `--check` rc=0（当前基线与实测命中数相等）；
  ② **自证**：注入一行 `img = Image.new('RGBA', (2, 2))` → `--check` rc≠0 且**指名该文件**。
     两个失败分支都测：`--update` 登记过的文件命中数**上升**、基线里**没登记**的文件出现命中。
     自证的另一半：不注入时必须是绿的 —— 只有"注入→红、不注入→绿"两半都在，
     "变红"才说明是注入引起的，而不是这道门本来就红。
  ③ 命中数下降 → `--check` PASS 且输出含「可下调基线」，并且**不许自动改基线**
     （下调是人的动作，要留 diff 给人看）；
  ④ 白名单文件：命中被豁免（rc=0）但**仍然出现在输出里**（命中数 + 理由，不静默）；
  ⑤ `--update` 在命中数上升时**拒绝**（rc≠0）且**不动基线文件**。

另外三条守"判据本身没写歪"（这类扫描器最容易的失效方式是扫错面/漏别名）：
  · 扫描范围 = `PRODUCERS` 那三个文件（钉死字面量，防静默缩小扫描面）；
  · 六个原语都算命中，而**只读取图不算**（`Image.open`/`convert`/`resize`/`crop`/`getpixel`/`save`）；
  · PIL **别名要解析**（本仓 `ui_tools/html2json.py` 就是 `from PIL import Image as _I` →
    `_I.new(...)`；不解析别名的话，改个名字就能把画图点藏起来）。

夹具一律用 `tests/_util.py` 的 `project()/cleanup()`（系统临时目录），**不碰真工程路径**；
"减少命中数"的场景是**改写临时夹具的内容**，不做删除（删除只有 `U.rm_in_temp` 通道，本文件用不到）。

跑法：`python -m unittest discover -s tests -p "test_draw_sites_lint.py" -q`
"""
import importlib.util
import io
import json
import os
import re
import subprocess
import sys
import unittest

import _util as U

BASE = U.BASE
SCRIPT = os.path.join(BASE, 'scripts', 'lint_draw_sites.py')

# 判据的"扫描范围"契约（与 lint_draw_sites.PRODUCERS 逐字对齐；改这里 = 有意改口径）。
PRODUCER_SCOPE = ('ui_tools/html2json.py', 'templates/ui_blocks/compose.py', 'translate_tools.py')

# 注入用的那一行（任务书原文）：一行 = 一个 Image.new 命中。
INJECT = "img = Image.new('RGBA', (2, 2))\n"


def _load_lint():
    """按路径加载闸门脚本（它不是包成员，也不该为了用例改成包）。"""
    spec = importlib.util.spec_from_file_location('lint_draw_sites_for_test', SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


L = _load_lint()


def run(args):
    """跑闸门脚本（**子进程**：与门禁挂载走同一条路径）→ (rc, stdout, stderr)。"""
    p = subprocess.run([sys.executable, SCRIPT] + [str(a) for a in args],
                       cwd=BASE, capture_output=True, timeout=300)
    return (p.returncode,
            p.stdout.decode('utf-8', 'replace'),
            p.stderr.decode('utf-8', 'replace'))


def read(path):
    with io.open(path, encoding='utf-8') as f:
        return f.read()


def stub(hits):
    """最小生产者文件：前 `hits` 行各一个 `Image.new(` 画图点（其余是只读导入，不计）。"""
    lines = ['# -*- coding: utf-8 -*-', 'from PIL import Image', '', '', 'def make():']
    for i in range(hits):
        lines.append("    img%d = Image.new('RGBA', (2, 2))" % i)
    lines.append('    return locals()')
    return '\n'.join(lines) + '\n'


class _Base(unittest.TestCase):
    """夹具基类：临时目录建树/改写 + 读回。"""

    def tree(self, files):
        """{相对路径: 文本} → 临时夹具树的根（自动 cleanup）。"""
        tmp = U.project()
        self.addCleanup(U.cleanup, tmp)
        for rel, text in files.items():
            U.write(os.path.join(tmp, rel.replace('/', os.sep)), text)
        return tmp

    def stub_tree(self, html2json=0, compose=0, translate=0):
        return self.tree({'ui_tools/html2json.py': stub(html2json),
                          'templates/ui_blocks/compose.py': stub(compose),
                          'translate_tools.py': stub(translate)})

    def real_producers_tree(self):
        """**真**生产者文件的副本（自证要打在真代码上，不是打在我编的样例上）。"""
        tmp = U.project()
        self.addCleanup(U.cleanup, tmp)
        for rel in L.PRODUCERS:
            with io.open(os.path.join(BASE, rel.replace('/', os.sep)), encoding='utf-8') as f:
                U.write(os.path.join(tmp, rel.replace('/', os.sep)), f.read())
        return tmp

    def rewrite(self, tmp, rel, text):
        U.write(os.path.join(tmp, rel.replace('/', os.sep)), text)

    def append_line(self, tmp, rel, line=INJECT):
        p = os.path.join(tmp, rel.replace('/', os.sep))
        self.rewrite(tmp, rel, read(p) + '\n' + line)

    def bl(self, tmp):
        return os.path.join(tmp, 'bl.txt')

    def wl(self, tmp):
        return os.path.join(tmp, 'wl.txt')


class TestScanScopeAndDetection(_Base):
    """判据本身：扫描范围 + 六个原语 + 只读不算 + 别名解析 + 注释不算。"""

    def test_producers_constant_is_the_declared_scope(self):
        """扫描范围就是任务书点名的三个生产者文件（钉死：防止静默缩小扫描面）。"""
        self.assertEqual(L.PRODUCERS, PRODUCER_SCOPE,
                         'PRODUCERS 变了：改扫描范围要同步本用例（缩面的改动必须先被看见）')

    def test_six_primitives_are_hits(self):
        tmp = self.tree({'probe.py': '\n'.join([
            '# -*- coding: utf-8 -*-', '', '', 'def draw(img):',
            '    ImageDraw.Draw(img)',
            "    Image.new('RGBA', (2, 2))",
            '    img.filter(ImageFilter.GaussianBlur(1))',
            '    ImageChops.multiply(img, img)',
            '    img.alpha_composite(img)',
            '    Image.blend(img, img, 0.5)', ''])})
        got = L.sites(os.path.join(tmp, 'probe.py'))
        self.assertEqual(sorted(p for _ln, p, _t in got), sorted(
            ['ImageDraw', 'Image.new', 'ImageFilter', 'ImageChops', 'alpha_composite', 'Image.blend']),
            '六个原语没被全部抓到：%s' % got)

    def test_read_only_pil_ops_are_not_hits(self):
        """只读取图不算：量尺寸/读像素/缩放/裁剪/存图都不许命中（否则闸门会被噪声淹没）。"""
        tmp = self.tree({'probe.py': '\n'.join([
            '# -*- coding: utf-8 -*-', 'from PIL import Image', '', '',
            'def probe(p):',
            "    img = Image.open(p).convert('RGBA')",
            '    img = img.resize((2, 2))',
            '    img = img.crop((0, 0, 1, 1))',
            '    px = img.getpixel((0, 0))',
            '    img.paste(img, (0, 0))',
            '    img.save(p)',
            '    return px', ''])})
        self.assertEqual(L.sites(os.path.join(tmp, 'probe.py')), [],
                         '只读操作被当成了画图点')

    def test_pil_alias_is_resolved(self):
        """别名藏不住画图点（真仓 html2json 的写法）。"""
        tmp = self.tree({'probe.py': '\n'.join([
            '# -*- coding: utf-8 -*-',
            'from PIL import Image as _I',
            'from PIL import ImageDraw as _D', '', '',
            'def draw():',
            "    m = _I.new('L', (2, 2), 0)",
            '    d = _D.Draw(m)',
            '    return d', ''])})
        texts = [t for _ln, _p, t in L.sites(os.path.join(tmp, 'probe.py'))]
        self.assertIn("m = _I.new('L', (2, 2), 0)", texts, '别名 `_I.new(...)` 漏了')
        self.assertIn('d = _D.Draw(m)', texts, '别名 `_D.Draw(...)` 漏了')

    def test_comment_mention_is_not_a_hit(self):
        tmp = self.tree({'probe.py': '# -*- coding: utf-8 -*-\n# 别用 Image.new(...) 自己画形状\nX = 1\n'})
        self.assertEqual(L.sites(os.path.join(tmp, 'probe.py')), [], '注释里的原语名不该判红')


class TestRealRepo(unittest.TestCase):
    """① 真仓当前基线成立（这是"闸门能挂在门禁上"的前提）。"""

    def test_check_passes_on_real_repo(self):
        rc, out, err = run(['--check'])
        self.assertEqual(rc, 0, '真仓 --check 必须 rc=0\n' + out + err)
        for rel in L.PRODUCERS:
            self.assertRegex(out, r'\[PASS\] %s\s+hits=\d+\s+baseline=' % re.escape(rel),
                             '%s 没有逐文件命中数（数字要看得见）：\n%s' % (rel, out))
        self.assertIn('fail=0  OK', out)

    def test_json_report_is_machine_readable(self):
        tmp = U.project()
        self.addCleanup(U.cleanup, tmp)
        jf = os.path.join(tmp, 'report.json')
        rc, out, err = run(['--check', '--json', jf])
        self.assertEqual(rc, 0, out + err)
        rep = json.loads(read(jf))
        self.assertEqual(rep['mode'], 'check')
        self.assertTrue(rep['ok'])
        self.assertEqual(rep['fail'], 0)
        by = {f['path']: f for f in rep['files']}
        for rel in L.PRODUCERS:
            self.assertIn(rel, by, '--json 报告缺 %s' % rel)
            self.assertIsInstance(by[rel]['hits'], int)
            self.assertIn(by[rel]['status'], ('ok', 'decreased', 'exempt'))
        self.assertTrue(rep['baseline'].endswith('draw_sites_baseline.txt'))
        self.assertTrue(rep['whitelist'].endswith('draw_sites_whitelist.txt'))


class TestSelfProof(_Base):
    """② 自证：注入画图点必须变红（两个失败分支），不注入必须绿。"""

    def test_new_draw_site_on_unbaselined_file_is_red(self):
        tmp = self.real_producers_tree()
        bl = self.bl(tmp)
        rc, out, _ = run(['--update', '--root', tmp, '--baseline', bl])
        self.assertEqual(rc, 0, '夹具树登记基线失败\n' + out)
        rc, out, _ = run(['--check', '--root', tmp, '--baseline', bl])
        self.assertEqual(rc, 0, '自证的另一半：没注入时必须绿\n' + out)
        # `translate_tools.py` 当前 0 命中 → 不在基线里 → 注入走"未登记文件"分支
        self.append_line(tmp, 'translate_tools.py')
        rc, out, _ = run(['--check', '--root', tmp, '--baseline', bl])
        self.assertNotEqual(rc, 0, '注入 Image.new 后闸门还是绿的 → 这道门是空转\n' + out)
        self.assertIn('translate_tools.py', out, '判红必须**指名文件**')
        self.assertIn('新增画图点', out)

    def test_increase_on_baselined_file_is_red(self):
        tmp = self.real_producers_tree()
        bl = self.bl(tmp)
        rc, out, _ = run(['--update', '--root', tmp, '--baseline', bl])
        self.assertEqual(rc, 0, out)
        self.append_line(tmp, 'ui_tools/html2json.py')      # 已登记文件再加一处画图点
        rc, out, _ = run(['--check', '--root', tmp, '--baseline', bl])
        self.assertNotEqual(rc, 0, '命中数超过基线必须判红\n' + out)
        self.assertIn('ui_tools/html2json.py', out)
        self.assertIn('命中数上升', out)

    def test_missing_producer_file_is_red(self):
        """PRODUCERS 里的文件不在夹具里 → FAIL（不静默漏扫）；--update 同样拒绝且不落盘。"""
        tmp = self.tree({'ui_tools/html2json.py': stub(1),
                         'templates/ui_blocks/compose.py': stub(0)})
        bl = self.bl(tmp)
        rc, out, _ = run(['--check', '--root', tmp, '--baseline', bl])
        self.assertNotEqual(rc, 0, out)
        self.assertIn('translate_tools.py', out)
        self.assertIn('不存在', out)
        rc, out, _ = run(['--update', '--root', tmp, '--baseline', bl])
        self.assertNotEqual(rc, 0, out)
        self.assertFalse(os.path.isfile(bl), '被拒绝的 --update 不该写出基线文件')


class TestDecrease(_Base):
    """③ 命中数下降：PASS + 提示「可下调基线」，但不自动改基线。"""

    def test_decrease_passes_and_hints_lowering(self):
        tmp = self.stub_tree(html2json=3)
        bl = self.bl(tmp)
        rc, out, _ = run(['--update', '--root', tmp, '--baseline', bl])
        self.assertEqual(rc, 0, out)
        before = read(bl)
        self.assertIn('hits=3', before, '基线该登记 3 个命中：\n' + before)
        self.rewrite(tmp, 'ui_tools/html2json.py', stub(2))     # 消掉一处画图点
        rc, out, _ = run(['--check', '--root', tmp, '--baseline', bl])
        self.assertEqual(rc, 0, '命中数下降必须 PASS\n' + out)
        self.assertIn('可下调基线', out, '下降了要提示可以下调基线（否则基线会一直是虚高的）')
        self.assertIn('hits=2  baseline=3', out)
        self.assertEqual(read(bl), before, '--check 不许自动改基线（下调要留 diff 给人看）')


class TestWhitelist(_Base):
    """④ 白名单：命中被豁免，但仍然出现在输出里（不静默）；缺理由即 FAIL。"""

    def test_whitelist_exempts_but_still_reports(self):
        tmp = self.stub_tree(compose=2)
        bl, wl = self.bl(tmp), self.wl(tmp)
        U.write(wl, '# 例外登记\n'
                    'templates/ui_blocks/compose.py  ::  仅出块库缩略图（人眼预览，不进 ui/*.json 图资产），'
                    '形状一律调 gen_res 的覆盖率 API\n')
        rc, out, _ = run(['--update', '--root', tmp, '--baseline', bl, '--whitelist', wl])
        self.assertEqual(rc, 0, out)
        self.assertNotIn('compose.py', read(bl), '白名单文件不该再进基线（否则两处口径打架）')
        rc, out, _ = run(['--check', '--root', tmp, '--baseline', bl, '--whitelist', wl])
        self.assertEqual(rc, 0, '白名单文件不参与计数 → 那 2 处命中不许判红\n' + out)
        self.assertIn('已豁免 1 个文件', out)
        self.assertIn('[SKIP] 已豁免：templates/ui_blocks/compose.py', out)
        self.assertIn('hits=2', out, '豁免也要把命中数打出来')
        self.assertIn('仅出块库缩略图', out, '豁免理由也要打出来（不静默）')
        # 语义钉死：豁免文件**不参与计数**（这正是白名单与基线的区别）→ 再加画图点仍放行
        self.append_line(tmp, 'templates/ui_blocks/compose.py')
        rc, out, _ = run(['--check', '--root', tmp, '--baseline', bl, '--whitelist', wl])
        self.assertEqual(rc, 0, out)
        self.assertIn('hits=3', out, '豁免文件的新命中数仍要如实显示')

    def test_whitelist_entry_without_reason_is_red(self):
        tmp = self.stub_tree(compose=2)
        bl, wl = self.bl(tmp), self.wl(tmp)
        U.write(wl, 'templates/ui_blocks/compose.py\n')       # 故意不写理由
        rc, out, _ = run(['--check', '--root', tmp, '--baseline', bl, '--whitelist', wl])
        self.assertNotEqual(rc, 0, '白名单不写理由必须判红\n' + out)
        self.assertIn('缺理由', out)


class TestUpdateRefusesIncrease(_Base):
    """⑤ `--update` 只许下调/登记新文件；命中数上升 = 新增画图点 → 拒绝且不动基线。"""

    def test_update_refuses_when_hits_increase(self):
        tmp = self.stub_tree(html2json=2)
        bl = self.bl(tmp)
        rc, out, _ = run(['--update', '--root', tmp, '--baseline', bl])
        self.assertEqual(rc, 0, out)
        before = read(bl)
        self.append_line(tmp, 'ui_tools/html2json.py')
        rc, out, _ = run(['--update', '--root', tmp, '--baseline', bl])
        self.assertNotEqual(rc, 0, '命中数上升时 --update 必须拒绝\n' + out)
        self.assertIn('命中数上升', out)
        self.assertIn('拒绝', out)
        self.assertEqual(read(bl), before, '被拒绝时基线文件必须原样（不许偷偷"顺手"登记）')
        self.assertIn('hits=2', before)


if __name__ == '__main__':
    unittest.main()
