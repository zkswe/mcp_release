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

    def test_uninstalled_platform_reports_explicitly(self):
        """头文件不在本机时必须**显式报错 + 给 fix 命令**，不许返回空的类表。

        为什么钉（2026-10-05 实测缺口）：`~/.fsc/registry/public/` 下**只有跑过 `fun install`
        的平台**（本机实测只有 v85x / z20）。原实现在目录不存在时返回 `success: True` +
        `headers: []` + `classes: []` —— 调用方分不清「这个平台没装包」（要装）与
        「这个包没有可解析的类」（要换手段看 API），前者会导致"查不到就以为没有这个能力"。

        判据用**真实未安装平台**而不是造目录：跑过 install 的平台集合随机器变，所以先探测
        哪个平台已安装，若都装了则跳过（避免把"本机恰好都装了"变成假红）。
        """
        installed = [p for p in ('V85X', 'Z20', 'T113', 'F133', 'Z21')
                     if os.path.isdir(pt._pkg_dir('easyui', p))]
        not_installed = [p for p in ('V85X', 'Z20', 'T113', 'F133', 'Z21')
                         if p not in installed]
        if not not_installed:
            self.skipTest('本机各平台都装过 easyui，无未安装平台可验')
        plat = not_installed[0]
        r = pt.flythings_get_package_api('easyui', plat)
        self.assertFalse(r.get('success'), '%s 未装包却报 success' % plat)
        self.assertIn('fun install', str(r.get('hint') or ''),
                      '报错必须给出可执行的 fix 命令（fun install）')
        self.assertIn('registry', str(r.get('error') or ''),
                      '报错要说清"本机 registry 里没有"而不是"包不存在"')

    def test_uninstalled_platform_still_serves_offline_api(self):
        """未装平台时**除了报错，还要把包卡里的离线 API 面直接给出**（2026-10-05 需求方口径）。

        为什么钉：需求方问「远端提供的这些库是否有对应材料让 AI 正确处理」——
        `packages/<包>/package.yaml` 就是为 AI 写的（头文件实读、含真机实测坑），
        它**离线、可复现**；而本机 registry 只覆盖跑过 `fun install` 的平台。
        若未装时只回 `success: False` + "去装"，调用方会止步，手里明明有一份能用的 API 资料。

        契约：`success` 仍为 False（"平台级精确签名没拿到"这个事实不许掩盖），
        但 `offlineApi` / `offlineNote` 必须在，且 API 签名要有实质内容。
        """
        installed = [p for p in ('V85X', 'Z20', 'T113', 'F133', 'Z21')
                     if os.path.isdir(pt._pkg_dir('zknet', p))]
        not_installed = [p for p in ('V85X', 'Z20', 'T113', 'F133', 'Z21')
                         if p not in installed]
        if not not_installed:
            self.skipTest('本机各平台都装过 zknet，无未安装平台可验')
        r = pt.flythings_get_package_api('zknet', not_installed[0])
        self.assertFalse(r.get('success'), '平台级签名没拿到时不许报 success')
        off = r.get('offlineApi')
        self.assertIsNotNone(off, '未装平台必须同时给出包卡离线面（否则调用方无法继续）')
        self.assertEqual(off.get('source'), 'packages/zknet/package.yaml')
        self.assertTrue(off.get('api'), 'offlineApi.api 应有签名清单')
        self.assertTrue(off.get('usage'), 'offlineApi.usage 应给可直接粘的代码')
        self.assertTrue(off.get('gotchas'), 'offlineApi.gotchas 应带真机实测的坑')
        self.assertTrue(off.get('verified'), 'offlineApi.verified 应带真机验证块')
        self.assertIn('offline', str(r.get('offlineNote') or '').lower()
                      + str(r.get('hint') or '').lower(),
                      '要明说"不装也能看 API"（否则调用方不会往下读）')

    def test_offline_api_survives_callers_without_local_registry(self):
        """包卡是**仓内文件**，与本地 registry 无关 —— 这是"可复现"的根据。"""
        for pkg in ('zknet', 'zkhardware', 'mqtt-cxx', 'nanovg'):
            card = pt.package_card(pkg)
            self.assertIsNotNone(card, '%s 包卡读不到' % pkg)
            self.assertTrue(card.get('api'), '%s 包卡没有 api 段' % pkg)

    def test_all_cards_parse(self):
        bad = []
        for name in CARDS:
            c = pt.package_card(name)
            if c is None:
                bad.append(name)
        self.assertEqual(bad, [], '这些包卡解析失败（YAML 语法？）: %s' % bad)


if __name__ == '__main__':
    unittest.main()
