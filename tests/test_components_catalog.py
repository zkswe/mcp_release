# -*- coding: utf-8 -*-
"""域⑦ 可复用组件目录的契约（components_catalog.py + gen_components_catalog.py）。

本目录的价值是两条：
① 让「有没有现成的组件 / 怎么用 / 依赖什么 / 示例在哪」一次可查（原来散在 15 篇 README 里）；
② 把 `components/README.md` 那条「**四件套缺一不收**」从人自觉变成可执行校验。

钉住八件事：
  ① 扫描可用；三种形态（源码型/二进制型/资产工具型）都能识别
  ② 四件套按形态核对通过（缺件会被抓）
  ③ **示例工程不被当成组件**（它们有 README + src，按形状会误判 —— 这是修过的回归点）
  ④ 分组与索引页的判定（ui_v1 是分组；根目录不是分组）
  ⑤ 未知 id 抛错并给相近提示
  ⑥ 依赖取自组件自己的 Manifest（不是抄来的第二份）
  ⑦ 平台可用性来自 platform_capabilities（本模块不重写）
  ⑧ 派生页与树一致；已登记缺口**必须**写原因与日期（不许静默放行）
"""
import os
import subprocess
import sys
import unittest

import _util as U

BASE = U.BASE
if BASE not in sys.path:
    sys.path.insert(0, BASE)
import components_catalog as cc                   # noqa: E402


class TestComponentsCatalog(unittest.TestCase):

    def test_01_扫描与形态(self):
        """① 三形态都能识别，且组件数量在合理区间。"""
        ms = cc.modules()
        self.assertGreaterEqual(len(ms), 10, '组件数异常：%d' % len(ms))
        forms = {m['form'] for m in ms}
        self.assertEqual(forms, {'source', 'binary', 'asset'},
                         '三种形态都应至少有一个实例：%s' % forms)
        for m in ms:
            with self.subTest(c=m['id']):
                self.assertIn(m['formName'], ('源码型', '二进制型', '资产/工具型'))

    def test_02_四件套核对通过(self):
        """② 现状应当齐备（不齐的必须走登记缺口）。"""
        self.assertEqual(cc.validate(), [], '四件套核对未过')

    def test_03_示例工程不被当组件(self):
        """③ 回归点：example/ 有 README + src，按形状会被误判成源码型组件。"""
        ids = [m['id'] for m in cc.modules()]
        bad = [i for i in ids if i.endswith('/example') or i.startswith('example')]
        self.assertEqual(bad, [], '示例工程被当成了组件：%s' % bad)
        for m in cc.modules():
            self.assertNotIn('/example/', m['dir'], m['dir'])

    def test_04_分组与索引页(self):
        """④ ui_v1 是分组、examples 是索引页；根目录不列成分组。"""
        gs = {g['id']: g for g in cc.groups()}
        self.assertIn('ui_v1', gs)
        self.assertIn('ui_v1/Chart', gs['ui_v1']['children'])
        self.assertIn('examples', gs)
        self.assertEqual(gs['examples']['children'], [], 'examples 是索引页，不该有子模块')
        self.assertNotIn('components', gs, '根目录不该被当成分组')

    def test_05_未知id抛错(self):
        """⑤ 查不到要报错并给相近提示。"""
        with self.assertRaises(cc.CatalogError):
            cc.get('不存在的组件')
        with self.assertRaises(cc.CatalogError):
            cc.get('chart')                       # id 是 ui_v1/Chart，不是 chart

    def test_06_依赖取自Manifest(self):
        """⑥ 依赖是机器可读的（来自各组件 Manifest.xml），不是手抄的第二份。"""
        self.assertIn('base-utility', cc.get('mp_transfer')['deps'])
        self.assertEqual(cc.get('blur')['deps'], [], 'blur 自述无第三方包')
        for m in cc.modules():
            with self.subTest(c=m['id']):
                if m['pieces'].get('Manifest.xml'):
                    self.assertIsInstance(m['deps'], list)

    def test_07_平台可用性来自注册表(self):
        """⑦ 平台可用性真源是 platform_capabilities.json（联接派生）。"""
        v85x = [m['id'] for m in cc.by_platform('V85X')]
        self.assertIn('ui_v1/Chart', v85x, 'V85X 上应有 ui_v1/Chart（已真机验收）')
        self.assertIn('ble', v85x)
        self.assertTrue(cc.get('ble')['platforms'])

    def test_08_派生页一致与缺口登记(self):
        """⑧ 派生页一致；缺口登记每条必须有 why + date（不许静默放行）。"""
        r = subprocess.run([sys.executable,
                            os.path.join(BASE, 'scripts', 'gen_components_catalog.py'), '--check'],
                           capture_output=True, cwd=BASE)
        self.assertEqual(r.returncode, 0, (r.stdout + r.stderr).decode('utf-8', 'replace')[:200])
        gaps = cc.declared_gaps()
        self.assertTrue(gaps, '应至少有一条登记缺口（mp_transfer 的形态变体）')
        for g in gaps:
            self.assertTrue(g.get('why'), '%s 的缺口没写原因' % g['id'])
            self.assertTrue(g.get('date'), '%s 的缺口没写日期' % g['id'])
        # 登记缺口必须精确：mp_transfer 只放行 include，别的缺件照旧要报
        mp = cc.get('mp_transfer')
        self.assertIn('include', mp['missing'])
        self.assertNotIn('Manifest.xml', mp['missing'], 'Manifest.xml 已补齐，不该再缺')


if __name__ == '__main__':
    unittest.main()
