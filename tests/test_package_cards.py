# -*- coding: utf-8 -*-
"""契约用例：仓库包卡（packages/<包>/package.yaml）可解析 + 已接进工具返回。

对应 2026-09-29 审查报告 P0①：`package_tools` 必须把包卡挂到
`flythings_get_package_api` / `list_packages` / `query_package` 的返回体里。
"""
import io
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import package_tools as pt  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG_DIR = os.path.join(REPO, 'packages')
CARDS = sorted(d for d in os.listdir(PKG_DIR)
               if os.path.isfile(os.path.join(PKG_DIR, d, 'package.yaml'))) if os.path.isdir(PKG_DIR) else []


class TestPackageCards(unittest.TestCase):
    def test_cards_exist(self):
        self.assertTrue(CARDS, 'packages/<包>/package.yaml 一张都没有')
        self.assertIn('zknet', CARDS)
        self.assertIn('zkhardware', CARDS)

    def test_card_fields(self):
        card = pt.package_card('zknet')
        self.assertIsNotNone(card, 'zknet 包卡读不到（pyyaml 缺失？）')
        self.assertEqual(card['id'], 'zknet')
        self.assertTrue(card['summary'])
        self.assertTrue(card['usage_cpp'], 'usage_cpp 应给可直接粘的示例')
        self.assertTrue(card['gotchas'], 'gotchas 应有真坑清单')
        self.assertTrue(card['api'], 'api 应有签名清单')
        self.assertIn('cardPath', card)
        self.assertTrue(card['verified'], 'verified_* 块应被带出')

    def test_missing_card_is_none(self):
        self.assertIsNone(pt.package_card('no-such-package-xyz'))
        self.assertFalse(pt._has_card('no-such-package-xyz'))

    def test_get_package_api_attaches_card(self):
        r = pt.flythings_get_package_api('zknet', 'Z20')
        self.assertIn('card', r)
        self.assertIsNotNone(r['card'], 'get_package_api 必须把包卡带上（审查报告 P0①）')
        self.assertEqual(r['card']['id'], 'zknet')

    def test_list_packages_marks_has_card(self):
        r = pt.flythings_list_packages('Z20')
        items = r['platforms'].get('Z20', [])
        self.assertTrue(items)
        by = {i['name']: i for i in items}
        if 'zknet' in by:
            self.assertTrue(by['zknet'].get('hasCard'), 'list_packages 应标 hasCard')

    def test_query_package_has_card_summary(self):
        r = pt.flythings_query_package('zknet', 'Z20')
        self.assertTrue(r.get('hasCard') or r.get('cardSummary'))


class TestPackageApiSignatures(unittest.TestCase):
    """`flythings_get_package_api` 的类/方法签名解析（2026-10-05 重写，钉住三条性质）。

    背景：原实现是"粗解析"，会让 AI **拿到错的 API**（这正是"painter 方法名不对"的机制）：
      · `re.findall(r'class\\s+(\\w+)')` 取文件里前 3 个 class 字面量 → 选中
        `class ZKPainterPrivate`（内部 Pimpl），而真正导出的 `class ZKPainter : public ZKBase` 不出现；
      · 方法行是**全文件**扫的，再原样挂到每个类名下 → Private 拿到了公共类的方法表；
      · `max_classes=8` 一满就 break，且按目录顺序 → `ZKPainter` 这类真正要用的头永远排不进来。

    判据：**签名唯一真源 = 本地 registry 头文件**（换平台/换版本自动跟随），
    所以这里直接拿头文件原文对账，而不是对着一份手抄的期望值断言。
    """

    def _inc(self):
        v = pt._pkg_versions('easyui', 'V85X')
        if not v:
            self.skipTest('本机 registry 无 easyui/V85X（该判据依赖本地包）')
        return os.path.join(pt._pkg_dir('easyui', 'V85X'), v[0], 'include')

    def test_no_internal_classes_in_api_surface(self):
        """给 AI 的 API 面里**不许有内部实现类**（`*Private` / `*Impl`）—— 那是 Pimpl 细节。"""
        inc = self._inc()
        names = [c['name'] for c in pt._parse_header_classes(inc, max_classes=30)]
        bad = [n for n in names if n.endswith(('Private', 'Impl'))]
        self.assertEqual(bad, [], '内部类混进了 API 面：%s' % bad)
        self.assertTrue(names, '一个类都没解析出来（判据空转了）')

    def test_focus_returns_exactly_that_class(self):
        """`focus=<类名>` 必须**只**返回该类，且不问数量上限（问一个类是最高频用法）。"""
        r = pt._parse_header_classes(self._inc(), focus='ZKPainter')
        self.assertEqual([c['name'] for c in r], ['ZKPainter'])
        self.assertTrue(r[0]['methods'], 'focus 命中却没方法')
        r2 = pt._parse_header_classes(self._inc(), focus='no-such-class-xyz')
        self.assertEqual(r2, [], '未知类名应返回空，而不是退回"给 8 个无关类"')

    def test_methods_match_the_header_verbatim(self):
        """方法签名必须**逐字来自头文件**（含参数名与默认值）—— AI 照抄就能编译。

        默认值是重点：`drawRect(..., int radius = 0)` 少了 `= 0`，AI 会以为必须传满 5 个参数；
        参数名同样是重点（`centerX/radiusX` vs 页面上写的 `cx/rx`）。
        """
        inc = self._inc()
        header = io.open(os.path.join(inc, 'control', 'ZKPainter.h'),
                         encoding='utf-8', errors='replace').read()
        cls = pt._parse_header_classes(inc, focus='ZKPainter')[0]
        self.assertTrue(cls['header'].endswith('control/ZKPainter.h'))
        for want in ('void setLineWidth(uint32_t width);',
                     'void drawRect(int left, int top, int width, int height, int radius = 0);',
                     'void drawArc(int centerX, int centerY, int radiusX, int radiusY = 0,'
                     ' int startAngle = 0, int sweepAngle = 360);',
                     'void drawLines(const SZKPoint *pPoints, int count);',
                     'void erase(int x, int y, int w, int h);'):
            self.assertIn(want, cls['methods'], '签名与头文件不一致（或漏了默认值）：%s' % want)
            self.assertIn(want.rstrip(';'), header, '头文件本身已变，对账基准要更新')
        # 内部类的方法不许出现在公共类名下
        self.assertNotIn('ZKPainterPrivate', [c['name'] for c in pt._parse_header_classes(inc)])

    def test_all_cards_parse(self):
        bad = []
        for name in CARDS:
            c = pt.package_card(name)
            if c is None:
                bad.append(name)
        self.assertEqual(bad, [], '这些包卡解析失败（YAML 语法？）: %s' % bad)


if __name__ == '__main__':
    unittest.main()
