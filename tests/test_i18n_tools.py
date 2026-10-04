# -*- coding: utf-8 -*-
"""多语言（i18n）契约：`.tr` → 设备 json 的**换行还原**与**字节格式**。

为什么要有（2026-10-03）：i18n 的 6 个 op 此前**只有路由测试**（`test_op_routing` 认触发词），
**没有一条用例碰过 `i18n_tools` 的实现**。而这里恰有两处「静默坏」风险 —— 都不会报错，
只会"看起来就是不对"：

  · `.tr` 里的 `\\n` 若没还原成**真实换行** → 设备**原样显示「\n」两个字**不换行
    （反汇编依据：`LanguageManager::getValue` 不做反斜杠还原，分行在 `zk_gdi_draw_text`
    按字节 `0x0A` 切 —— 见 `knowledge/devflow/i18n-multilang.md` §6）；
  · 生成的 json 若不是「**tab 缩进 + 冒号后无空格 + 末尾无换行**」→ 与设备端加载格式
    不再逐字节一致（`i18n_to_json` 的字节一致性契约就靠它）。

离线（零设备）：`i18n_to_json` 一律用 `push=False`；`tests/_util.py` 默认拦掉真 adb。
"""
import io
import json
import os
import unittest

import _util as U


def _p(op, args):
    """调 op 并**拆掉分发器信封**（`{ok, op, data(JSON 字符串), warnings}`）→ op 自己的返回体。"""
    return U.payload(U.jcall(op, args))


class TestTrEscaping(unittest.TestCase):
    """`.tr`（人写）与 json（设备读）之间的换行/制表/反斜杠转义。"""

    def test_backslash_n_becomes_real_newline(self):
        import i18n_tools as it
        self.assertEqual(it._unescape_tr('第一行\\n第二行'), '第一行\n第二行')
        self.assertIn('\n', it._unescape_tr('a\\nb'))
        self.assertEqual(it._unescape_tr('a\\tb'), 'a\tb')
        self.assertEqual(it._unescape_tr('反斜杠\\\\'), '反斜杠\\')
        self.assertEqual(it._unescape_tr('未知\\x 原样保留'), '未知\\x 原样保留')
        self.assertEqual(it._unescape_tr('没有转义'), '没有转义')

    def test_escape_unescape_roundtrip(self):
        import i18n_tools as it
        for s in ('普通文案', '两行\n文本', '带\tTAB', '反斜杠\\与引号"', ''):
            self.assertEqual(it._unescape_tr(it._escape_tr(s)), s, repr(s))

    def test_official_xml_char_reference_form(self):
        """**官方写法** `&#x000A;` 也必须落到 json 里的真换行（对编译器与 MCP 都安全的那条路）。

        官方 i18n 文档：`<string name="new_line_test">第一行&#x000A;第二行</string>`。
        它与「字面 `\\n`」是**两条不同来源**：XML 字符引用由 XML 解析器解开，
        字面 `\\n` 靠 `_unescape_tr`；两条都必须变成 json 里的真实 `0x0A`（设备按它切行）。
        """
        import i18n_tools as it
        tmp = U.project()
        try:
            U.write(os.path.join(tmp, 'i18n', 'zh_CN.tr'),
                    '<?xml version="1.0" encoding="utf-8"?>\n<resources>\n'
                    '  <string name="nl">第一行&#x000A;第二行</string>\n'
                    '</resources>\n')
            r = _p('flythings_i18n_to_json',
                   {'project_root': tmp, 'langs': 'zh_CN', 'push': False})
            self.assertTrue(r['ok'], r)
            with io.open(os.path.join(tmp, 'i18n', 'zh_CN.json'),
                         encoding='utf-8', newline='') as f:
                raw = f.read()
            self.assertEqual(json.loads(raw)['nl'], '第一行\n第二行',
                             '官方 &#x000A; 形式没还原成真换行（设备会不换行）')
        finally:
            U.cleanup(tmp)


class TestDeviceJsonFormat(unittest.TestCase):
    """生成的 json 必须与设备端加载格式逐字节一致（tab/冒号/无尾换行）。"""

    def test_dump_json_is_device_byte_format(self):
        import i18n_tools as it
        out = it._dump_json({'about_me': '关于我们', 'two': 'a\nb'})
        self.assertEqual(out, '{\n\t"about_me":"关于我们",\n\t"two":"a\\nb"\n}')
        self.assertFalse(out.endswith('\n'), '末尾不能有换行（要与设备端逐字节一致）')
        self.assertNotIn(': ', out, '冒号后不能有空格')
        # JSON 文本里是真换行的转义写法；设备 json 解析后拿到的是 0x0A（切行靠它）
        self.assertEqual(json.loads(out)['two'], 'a\nb')


class TestLayoutKeyCollection(unittest.TestCase):
    """`@key` 收集：布局引用检查（scan 的 `layoutRefMissingInTr`）靠它。"""

    def test_collects_at_keys_only(self):
        import i18n_tools as it
        tmp = U.project()
        try:
            U.write(os.path.join(tmp, 'ui', 'main.json'),
                    json.dumps({'textview__1': {'text': '@about_me'},
                                'textview__2': {'text': '写死的文案（不带 @）'},
                                'button__1': {'text': '@ok'}}, ensure_ascii=False))
            self.assertEqual(it._collect_layout_keys(tmp), {'about_me', 'ok'})
        finally:
            U.cleanup(tmp)

    def test_display_name_three_part_filename(self):
        import i18n_tools as it
        self.assertEqual(it._tr_display_name('fr_FR-法语'), '法语')
        self.assertEqual(it._tr_display_name('zh_CN'), 'zh_CN')


class TestScanAndToJson(unittest.TestCase):
    """端到端：两种语言的 .tr + 布局 @key → scan 报对齐/缺引用；to_json 出设备格式。"""

    def setUp(self):
        self.tmp = U.project()
        U.write(os.path.join(self.tmp, 'i18n', 'zh_CN.tr'),
                '<?xml version="1.0" encoding="utf-8"?>\n<resources>\n'
                '  <string name="about_me">关于我们</string>\n'
                '  <string name="two_line">第一行\\n第二行</string>\n'
                '</resources>\n')
        U.write(os.path.join(self.tmp, 'i18n', 'en_US.tr'),
                '<?xml version="1.0" encoding="utf-8"?>\n<resources>\n'
                '  <string name="about_me">About us</string>\n'
                '</resources>\n')
        U.write(os.path.join(self.tmp, 'ui', 'main.json'),
                json.dumps({'textview__1': {'text': '@about_me'},
                            'textview__2': {'text': '@missing_key'}}, ensure_ascii=False))

    def tearDown(self):
        U.cleanup(self.tmp)

    def test_scan_reports_alignment_and_layout_refs(self):
        r = _p('flythings_i18n_scan', {'project_root': self.tmp})
        self.assertTrue(r['ok'], r)
        self.assertTrue(r['hasI18n'])
        self.assertEqual(sorted(r['languages']), ['en_US', 'zh_CN'])
        self.assertEqual(r['languageDisplayNames']['zh_CN'], 'zh_CN')
        self.assertFalse(r['keyAligned'], '两种语言 key 不一致时 keyAligned 必须为 false')
        self.assertIn('two_line', r['missingKeysPerLanguage']['en_US'])
        self.assertIn('missing_key', r['layoutRefMissingInTr'],
                      '布局引用了但 .tr 里没有的 key 必须被报出来')
        self.assertEqual(r['keysPerLanguage']['zh_CN'], 2)
        self.assertEqual(r['keysPerLanguage']['en_US'], 1)

    def test_normal_project_reports_no_i18n_honestly(self):
        """没有 i18n/ 时不许假装有：回 hasI18n=false + 指路 export。"""
        plain = U.project()
        try:
            r = _p('flythings_i18n_scan', {'project_root': plain})
            self.assertTrue(r['ok'], r)
            self.assertFalse(r['hasI18n'])
            self.assertEqual(r['languages'], [])
            self.assertIn('i18n_export', json.dumps(r, ensure_ascii=False))
        finally:
            U.cleanup(plain)

    def test_to_json_writes_device_format_with_real_newline(self):
        r = _p('flythings_i18n_to_json',
                    {'project_root': self.tmp, 'langs': 'zh_CN', 'push': False})
        self.assertTrue(r['ok'], r)
        self.assertEqual([c['lang'] for c in r['converted']], ['zh_CN'])
        jp = os.path.join(self.tmp, 'i18n', 'zh_CN.json')
        self.assertTrue(os.path.isfile(jp), '必须生成 i18n/zh_CN.json（设备实际加载这个）')
        with io.open(jp, encoding='utf-8', newline='') as f:
            raw = f.read()
        self.assertFalse(raw.endswith('\n'), '末尾不能有换行')
        self.assertNotIn(': ', raw, '冒号后不能有空格')
        self.assertEqual(json.loads(raw)['two_line'], '第一行\n第二行',
                         '换行必须是真换行（设备按 0x0A 切行）')

    def test_to_json_unknown_lang_reports_not_silent(self):
        r = _p('flythings_i18n_to_json',
                    {'project_root': self.tmp, 'langs': 'de_DE', 'push': False})
        self.assertFalse(r['ok'], '指定了不存在的语言必须明确报错，不能静默成功')
        self.assertIn('de_DE', json.dumps(r, ensure_ascii=False))


if __name__ == '__main__':
    unittest.main(verbosity=2)
