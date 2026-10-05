# -*- coding: utf-8 -*-
"""发射口径对账契约（T5.1/T5.2）。

钉住三件事：
  ① **快照与实测一致**：`scripts/gen_emit_conformance.py --check` rc=0（发射层 vs html2json 产物）；
  ② **自证**：把快照改一处（模拟"某处发射口径漂了"）→ `--check` 必须红；
  ③ **唯一发射层自身合规**：`ui_emit.DEFAULT_BY_TYPE` 每个类型的键都必须是注册表声明过的字段，
     且**覆盖该类型的全部必填键**（否则"字段全集"从发射层就漏了）。
"""
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS = os.path.dirname(os.path.abspath(__file__))
for _p in (BASE, os.path.join(BASE, 'ui_tools'), os.path.join(BASE, 'scripts'), TESTS):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import _util as U                                           # noqa: E402
import ui_emit as E                                         # noqa: E402
import ui_schema_loader as US                               # noqa: E402

GEN = os.path.join(BASE, 'scripts', 'gen_emit_conformance.py')
SNAP = os.path.join(BASE, 'ui_tools', 'emit_conformance.json')


class TestEmitConformance(unittest.TestCase):

    def test_snapshot_matches_reality(self):
        p = subprocess.run([sys.executable, GEN, '--check'], capture_output=True, text=True,
                           encoding='utf-8', errors='replace')
        self.assertEqual(p.returncode, 0, (p.stdout or '')[-800:] + (p.stderr or '')[-300:])
        self.assertIn('[PASS]', p.stdout or '')

    def test_mutated_snapshot_is_red(self):
        """自证：把快照里某一处差异改掉（= 有人悄悄改了发射口径/前端）→ 必须红。"""
        tmp = tempfile.mkdtemp(prefix='mcp_emitconf_')
        self.addCleanup(U.cleanup, tmp)
        bad = os.path.join(tmp, 'bad.json')
        shutil.copy2(SNAP, bad)
        data = json.load(io.open(bad, encoding='utf-8'))
        t = sorted(data['types'])[0]
        data['types'][t]['valueDiffs']['__injected__'] = {'html2json': 1, 'uiEmit': 2}
        with io.open(bad, 'w', encoding='utf-8', newline='\n') as f:
            f.write(json.dumps(data, ensure_ascii=False, indent=1))
        p = subprocess.run([sys.executable, GEN, '--check', '--snapshot', bad],
                           capture_output=True, text=True, encoding='utf-8', errors='replace')
        self.assertEqual(p.returncode, 1, '被改过的快照必须判红：%s' % (p.stdout or '')[-300:])
        self.assertIn('[FAIL]', p.stdout or '')

    def test_emit_layer_covers_required_keys(self):
        for tname, fill in sorted(E.DEFAULT_BY_TYPE.items()):
            declared = set(US.load()['controls'].get(tname, {}).get('fields', {}))
            self.assertTrue(declared, '发射层声明了注册表里没有的类型：%s' % tname)
            unknown = sorted(set(fill) - declared)
            self.assertEqual(unknown, [], '%s 的默认表里有注册表未声明的键：%s' % (tname, unknown))
            missing = sorted(set(US.required_fields(tname)) - set(fill))
            # caption/position 这类由调用方给的必填键不在 fill 里是正常的
            missing = [m for m in missing if m not in ('caption', 'position', 'id')]
            self.assertEqual(missing, [], '%s 的默认表漏了必填键：%s' % (tname, missing))

    def test_emit_layer_used_by_translate(self):
        """`translate_tools` 必须**引用**唯一发射层（别名），而不是自带第二份实现。"""
        src = io.open(os.path.join(BASE, 'translate_tools.py'), encoding='utf-8').read()
        self.assertIn('import ui_emit as _emit', src)
        self.assertNotIn('_SCHEMA_FILL = {', src, 'translate_tools 里不该再有第二份 fill 表')
        import translate_tools as T
        self.assertIs(T._SCHEMA_FILL, E.DEFAULT_BY_TYPE, '别名必须指向同一对象（不是复制）')


class TestHtml2JsonUsesSharedEmit(unittest.TestCase):
    """T5.5：`html2json` 的控件也过共享发射层（但只补必填键）。"""

    HTML = ('<!doctype html><html><body><div class="screen" data-res="480x272" '
            'data-bg="#101418">'
            '<div class="bar" data-caption="SkOne" data-x="10" data-y="10" data-w="200" '
            'data-h="30"></div>'
            '<button class="btn" data-caption="BtnHot" data-x="10" data-y="60" data-w="120" '
            'data-h="40">热区</button>'
            '</div></body></html>')

    def _emit(self):
        import html2json as H
        tmp = U.project()
        self.addCleanup(U.cleanup, tmp)
        src = os.path.join(tmp, 'p.html')
        U.write(src, self.HTML)
        out = os.path.join(tmp, 'p.json')
        r = H.html2json(src, out, res='480x272')
        self.assertTrue(r.get('success'), r)
        return json.load(io.open(out, encoding='utf-8'))

    def test_seekbar_gets_required_keys_from_shared_layer(self):
        page = self._emit()
        sk = [v for k, v in page.items() if k.startswith('seekbar__')]
        self.assertTrue(sk, '没生成 seekbar：%s' % list(page))
        for key in ('backgroundPic', 'progressPic'):
            self.assertIn(key, sk[0],
                          '必填键 %s 没补上（共享发射层未生效）' % key)

    def test_optional_keys_are_not_injected(self):
        """前端刻意省略的可选字段不许被补回。

        为什么单测这一层：`html2json` 自己对**普通按钮**会写 `bgColorTab`（源稿给了底色），
        但对"热区按钮"是**故意不写**的（写了会盖住下层画布——设备教训已写成用例）。
        所以判据只能钉在"补全函数不碰可选键"这一层，而不是拿某个具体页面当样本。
        """
        page = self._emit()
        sk = [v for k, v in page.items() if k.startswith('seekbar__')][0]
        self.assertNotIn('bgColorTab', sk,
                         '必填键补全把**可选**的 bgColorTab 也补进来了（seekbar 本不需要）')
        _ctl, _unfilled = E.fill_required('button', {'caption': 'B', 'id': 20001,
                                                    'position': {'left': 0, 'top': 0,
                                                                 'width': 1, 'height': 1},
                                                    'picTab': {}})
        self.assertNotIn('bgColorTab', _ctl,
                         'fill_required 补了可选键 bgColorTab（= 热区按钮会被盖底色）')
        self.assertIn('touchable', _ctl, '必填键没补（判据失效）')

    def test_html2json_calls_shared_layer(self):
        src = io.open(os.path.join(BASE, 'ui_tools', 'html2json.py'), encoding='utf-8').read()
        self.assertIn('_emit.fill_required(', src,
                      'html2json 必须走 ui_emit 的必填键补全（唯一发射层）')


class TestComposeUsesSharedEmit(unittest.TestCase):
    """T5.6：	emplates/ui_blocks/compose.py 也走共享发射层的必填键补全。"""

    def test_compose_source_calls_shared_layer(self):
        src = io.open(os.path.join(BASE, 'templates', 'ui_blocks', 'compose.py'),
                      encoding='utf-8').read()
        self.assertIn('_emit.fill_required(', src,
                      'compose 的 serialize() 必须走 ui_emit 的必填键补全（唯一发射层）')

    def test_compose_really_calls_shared_layer_at_runtime(self):
        """**运行期**判据：`serialize()` 真的调到了 `ui_emit.fill_required`。

        为什么不能只查源码子串（2026-10-05 检讨）：源码里出现 `_emit.fill_required(` 也可以是
        注释或走不到的分支；而 compose **自带字段全集表**，它一旦停止调用共享层，产物依然
        "字段齐全" → `gen_emit_conformance --check` 不会红，唯一能抓住的就是这个调用本身。
        """
        import importlib.util
        path = os.path.join(BASE, 'templates', 'ui_blocks', 'compose.py')
        here = os.path.dirname(path)
        spec = importlib.util.spec_from_file_location('_ui_blocks_compose_probe', path)
        mod = importlib.util.module_from_spec(spec)
        sys.path.insert(0, here)          # compose 以脚本形态 `import iconlib`（同目录）
        try:
            spec.loader.exec_module(mod)
        finally:
            sys.path.remove(here)
        calls = []
        orig = E.fill_required

        def spy(tname, ctl):
            calls.append(tname)
            return orig(tname, ctl)

        E.fill_required = spy
        try:
            node = mod.Node('window', 'W1', {'left': 0, 'top': 0, 'width': 10, 'height': 10})
            out = mod.serialize([node])
        finally:
            E.fill_required = orig
        self.assertEqual(calls, ['window'],
                         'compose.serialize 没经过共享发射层（调用记录=%s）' % calls)
        self.assertIn('hideTimeOut', out['window__1'], '产物不完整，判据失效')

    def test_snapshot_covers_compose_and_is_complete(self):
        data = json.load(io.open(SNAP, encoding='utf-8'))
        cmp_rep = data.get('compose') or {}
        self.assertEqual(cmp_rep.get('errors'), [], 'compose 对账没跑成：%s' % cmp_rep.get('errors'))
        types = cmp_rep.get('types') or {}
        self.assertTrue(types, 'compose 段没有任何类型被对账（扫描器坏了？）')
        total = sum(v['samples'] for v in types.values())
        self.assertGreaterEqual(total, 30, 'compose 样本太少（%d）→ 对账没有覆盖力' % total)
        for t, v in sorted(types.items()):
            self.assertEqual(v['missingRequired'], [],
                             'compose 的 %s 缺必填键：%s' % (t, v['missingRequired']))
            self.assertEqual(v['extraKeys'], [],
                             'compose 的 %s 写了注册表未声明的键：%s' % (t, v['extraKeys']))


class TestEmitStringThumbPath(unittest.TestCase):
    """`schema_complete` 的「thumb 字符串 → 子盒」路径（T5.2 搬层时漏掉的回归）。

    2026-10-05 检讨实测：搬层后 `ui_emit.py` 用了 `os.path.basename` 却**没有 `import os`**
    → 映射片段里的字符串 thumb（`schema_complete` 文档自己写明的正规输入形态，注册表
    `valueRules.subboxType` 允许旧式字符串）**一律抛 NameError**，`translate_ui` 那条路当场不可用；
    而 T5.2 的"产物逐字节一致"证据只覆盖了基本夹具，没碰到这条路。
    """

    POS = {'left': 0, 'top': 0, 'width': 448, 'height': 32}

    def test_string_thumb_becomes_subbox(self):
        c = E.schema_complete('seekbar', {'caption': 'Sk', 'id': 91001,
                                          'position': dict(self.POS),
                                          'thumb': 'images/progress_32x32.png'})
        self.assertEqual(c['thumb']['size'], {'width': 32, 'height': 32},
                         '字符串 thumb 没转成子盒（或尺寸没从文件名取到）：%s' % (c.get('thumb'),))
        self.assertEqual(c['thumb']['normalPic'], 'images/progress_32x32.png')
        self.assertEqual(c['thumb']['pressedPic'], 'images/progress_32x32.png')

    def test_string_thumb_without_size_in_name_defaults_24(self):
        c = E.schema_complete('seekbar', {'caption': 'Sk', 'id': 91002,
                                          'position': dict(self.POS),
                                          'thumb': 'images/knob.png'})
        self.assertEqual(c['thumb']['size'], {'width': 24, 'height': 24},
                         '文件名里没有 WxH 时应落 24（旧口径），实测：%s' % (c.get('thumb'),))

    def test_empty_string_thumb_means_no_pic(self):
        c = E.schema_complete('circlebar', {'caption': 'Cb', 'id': 92001,
                                            'position': {'left': 0, 'top': 0,
                                                         'width': 100, 'height': 100},
                                            'thumb': ''})
        self.assertEqual(c['thumb'], E.THUMB_EMPTY, '空串 thumb 必须是「不设图」零值子盒')


if __name__ == '__main__':
    unittest.main()
