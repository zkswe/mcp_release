# -*- coding: utf-8 -*-
"""域⑤ 多媒体能力注册表契约（media_capabilities.json + media_cap_loader.py）。

这套注册表的价值是：①「这块板能不能做某件事」一次可查；② **跨来源对账** ——
注册表说"用某个包"，就必须在 package_catalog 里真有；注册表说"出处是某篇文档"，
那篇就必须真实存在。所以用例钉住的是这两条对账，而不只是"能加载"。

钉住十件事：
  ① 可加载、自检通过（validate() 空）
  ② 每条能力有 hints（口语问法）—— 检索靠它命中
  ③ 必填字段 + kind 合法 + id 唯一
  ④ docRef 全部真实存在（死指针会让 AI 去搜不存在的东西）
  ⑤ packages 全部在 package_catalog 里（跨来源对账）
  ⑥ availability 联接正确，且 platforms_of 归一到 platforms.py 的规范名（f136→F135）
  ⑦ 未知 id 抛 MediaCapError（并给相近提示），不静默回空
  ⑧ 口语问法能命中（for_query）
  ⑨ layers 覆盖 UI/OSD 与视频层，且带平台与出处
  ⑩ 派生知识页与注册表一致（手改 md 会红）；免编译库能力不占包
"""
import io
import os
import subprocess
import sys
import unittest

import _util as U

BASE = U.BASE
if BASE not in sys.path:
    sys.path.insert(0, BASE)
import media_cap_loader as mc                      # noqa: E402
import derived_md                                  # noqa: E402


class TestMediaCapRegistry(unittest.TestCase):

    def test_01_加载与自检(self):
        """① 注册表可加载、声明 authority、自检零问题。"""
        d = mc.load()
        self.assertIn('authority', d)
        self.assertIn('唯一真源', d['authority'].get('role', ''))
        self.assertEqual(mc.validate(), [], '注册表自检未过')

    def test_02_每条能力有口语问法(self):
        """② hints 是检索入口；缺了等于这条能力搜不到。"""
        for c in mc.capabilities():
            with self.subTest(cap=c['id']):
                self.assertTrue(c.get('hints'), '%s 缺 hints' % c['id'])
                self.assertGreaterEqual(len(c['hints']), 1)

    def test_03_必填字段与_kind(self):
        """③ 结构自洽（kind 在 kinds 里、id 不重复、有 summary）。"""
        kinds = set(mc.kinds())
        self.assertTrue(kinds)
        ids = [c['id'] for c in mc.capabilities()]
        self.assertEqual(len(ids), len(set(ids)), 'id 有重复')
        for c in mc.capabilities():
            self.assertIn(c['kind'], kinds, c['id'])
            self.assertTrue(c['summary'].strip(), c['id'])

    def test_04_docRef_真实存在(self):
        """④ 出处必须是真文档（这条对账是本域的核心价值之一）。"""
        for c in mc.capabilities():
            p = os.path.join(BASE, c['docRef'])
            with self.subTest(cap=c['id']):
                self.assertTrue(os.path.isfile(p), '%s 的 docRef 不存在：%s' % (c['id'], c['docRef']))

    def test_05_引用的包在包目录里确有(self):
        """⑤ 跨来源对账：注册表引用的包，package_catalog 必须真收录。"""
        cat = mc._catalog()
        self.assertTrue(cat, '包目录为空？')
        for c in mc.capabilities():
            for name in (c.get('packages') or []):
                with self.subTest(cap=c['id'], pkg=name):
                    self.assertIn(name, cat,
                                  '%s 引用了包目录里没有的包 %r（这条能力落不了地）' % (c['id'], name))

    def test_06_可用性联接与平台归一(self):
        """⑥ availability 来自包目录；平台名走 platforms.py（f136/f136emmc → F135）。"""
        if not os.path.isfile(os.path.join(BASE, 'PUBLISH.md')):
            self.skipTest('裁剪发布版（PUBLISH.md 不随包）：该内部件/私有包按发布边界剔除')
        av = mc.availability('dvr-camera-preview')
        self.assertIn('V85X', av, 'DVR 预览应有 V85X')
        self.assertIn('aw-dvr', av['V85X'])
        # f136 是 F135 的别名（包键 f136/f136emmc）——不得出现 f136 这种原始键
        for cap_id in [c['id'] for c in mc.capabilities()]:
            for plat in mc.platforms_of(cap_id):
                with self.subTest(cap=cap_id, plat=plat):
                    self.assertNotIn(plat, ('f136', 'f136emmc', 't113stdcxx', 'v85xemmc'),
                                     '平台名未归一到规范名：%s' % plat)

    def test_07_未知id抛错并给提示(self):
        """⑦ 查不到要报错，不能静默回空（调用方据此判断，不是靠猜）。"""
        with self.assertRaises(mc.MediaCapError):
            mc.cap('video-layer')
        try:
            mc.cap('dvr')
        except mc.MediaCapError as e:
            self.assertIn('相近', str(e), '相近 id 提示应给出：%s' % e)
        else:
            self.fail('dvr 不是完整 id，应抛错')

    def test_08_口语问法能命中(self):
        """⑧ 用户问法（口语）要能落到对应能力上。"""
        cases = {
            '拼墙抓不到画面': 'video-layer-capture',
            '能不能不编译直接用设备上的库': 'lib-preinstalled',
            '视频播放用什么包': 'video-h264-play',
            '摄像头预览怎么做': 'dvr-camera-preview',
        }
        for q, want in cases.items():
            with self.subTest(q=q):
                ids = [c['id'] for c in mc.for_query(q)]
                self.assertIn(want, ids, '%r 应命中 %s，实际 %s' % (q, want, ids))

    def test_09_图层覆盖与出处(self):
        """⑨ 图层清单必须说清「画面在哪一层」并给出处。"""
        by_id = {ly['id']: ly for ly in mc.layers()}
        self.assertIn('ui-osd', by_id)
        self.assertIn('video', by_id)
        self.assertEqual(sorted(by_id['video'].get('platforms') or []), ['Z20', 'Z21'])
        for ly in mc.layers():
            self.assertTrue(os.path.isfile(os.path.join(BASE, ly['docRef'])), ly['id'])

    def test_10_派生页一致与免编译库不占包(self):
        """⑩ 派生页 == 注册表渲染（手改会红）；只借库的能力不写 packages。"""
        r = subprocess.run([sys.executable, os.path.join(BASE, 'scripts', 'gen_media_cap_doc.py'),
                            '--check'], capture_output=True, cwd=BASE)
        self.assertEqual(r.returncode, 0,
                         (r.stdout + r.stderr).decode('utf-8', 'replace')[:200])
        with io.open(os.path.join(BASE, mc.doc_path()), encoding='utf-8') as fh:
            cur = fh.read()
        self.assertTrue(derived_md.normalize(cur).count('# 多媒体能力索引'))
        lib_only = [c for c in mc.capabilities() if c['kind'] == 'lib']
        self.assertTrue(lib_only, '应有「设备预装可借库」这一类')
        for c in lib_only:
            self.assertFalse(c.get('packages'), '%s 是纯库能力，不该写 packages' % c['id'])
            self.assertTrue(c.get('libs'), '%s 应列出库清单' % c['id'])

    def test_11_反向索引(self):
        """⑪ 包 → 能力（换包时知道会影响哪些能力）。"""
        if not os.path.isfile(os.path.join(BASE, 'PUBLISH.md')):
            self.skipTest('裁剪发布版（PUBLISH.md 不随包）：该内部件/私有包按发布边界剔除')
        self.assertIn('dvr-camera-preview', mc.caps_for_package('aw-dvr'))
        self.assertEqual(mc.caps_for_package('不存在的包'), [])


if __name__ == '__main__':
    unittest.main()
