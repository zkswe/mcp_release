# -*- coding: utf-8 -*-
"""契约用例：仓库包卡（packages/<包>/package.yaml）可解析 + 已接进工具返回。

对应 2026-09-29 审查报告 P0①：`package_tools` 必须把包卡挂到
`flythings_get_package_api` / `list_packages` / `query_package` 的返回体里。
"""
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

    def test_all_cards_parse(self):
        bad = []
        for name in CARDS:
            c = pt.package_card(name)
            if c is None:
                bad.append(name)
        self.assertEqual(bad, [], '这些包卡解析失败（YAML 语法？）: %s' % bad)


if __name__ == '__main__':
    unittest.main()
