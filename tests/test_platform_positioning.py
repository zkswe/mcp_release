# -*- coding: utf-8 -*-
"""平台定位契约（v0.27.196）：FlyThings OS = Linux 基座 + 自研框架；FlyThings UI( EasyUI ) ≠ LVGL。

为什么要有这组用例（2026-10-05，需求方反馈的真实事故）：
其他用户调本 MCP 时，AI 写出了这样的「关键约束」——
    「V85X 跑的是 FlyThings（zkgui/LVGL），不是 ESP32 也不是 Linux 用户空间，所以不能直接套 SDK 固件。」
两处错：① 把 GUI 当成 LVGL（FlyThings UI / EasyUI 与 LVGL 是对标竞争的两套库）；② 把 FlyThings 排除在
Linux 之外（它本就是 Linux 基座的操作系统）。这两个错会**直接改变能力判定**：AI 会砍掉整层 Linux 能力
（POSIX/socket/dlopen/现成开源库），并把 LVGL 的 API 往 FlyThings 上套（违反检索边界）。

本组钉四件事（缺一条，错误定位就会重新长回来）：
  ① 权威页存在且写清了四条核心断言（定位真源 = knowledge/devflow/flythings-os-positioning.md）；
  ② 入口面带得动它：MCP instructions / 分发器 docstring / get_version.positioning /
     flythings://tools / flythings://version；
  ③ 判平台能力的 op（建工程、编译部署、包清单、工程规范）常驻面必须有定位规则；
  ④ 冻结的错误说法不许在仓库正文里复活（只允许出现在「反面教材」上下文里）。
"""
import io
import json
import os
import re
import unittest

import _util as U
import kb_tools
import platforms as pl

POSITIONING_DOC = 'knowledge/devflow/flythings-os-positioning.md'

# 判平台能力的 op：它们的常驻面（tool description）必须带定位规则
POSITIONING_OPS = ('flythings_create_project',
                   'flythings_build_ui_flow', 'flythings_list_packages',
                   'flythings_get_project_spec')


def _read(path):
    return io.open(os.path.join(U.BASE, path), encoding='utf-8').read()


class TestPositioningAuthority(unittest.TestCase):
    """① 权威页的内容断言（定位真源）。"""

    def setUp(self):
        self.doc = _read(POSITIONING_DOC)

    def test_doc_exists_and_is_declared(self):
        self.assertTrue(os.path.isfile(os.path.join(U.BASE, POSITIONING_DOC)))
        self.assertIn('platforms.py', self.doc,
                      '定位页要写明「OS 身份在 platforms.py、arch 字段不是 OS 名」')

    def test_four_core_claims(self):
        """四条核心断言：Linux 基座 / buildroot-openwrt 基线 / 不是 MCU-SDK / GUI 是自研≠LVGL。"""
        for token in ('Linux', 'buildroot', 'openwrt', 'EasyUI', 'FlyThings UI', 'LVGL',
                      'ESP32', 'RTOS'):
            self.assertIn(token, self.doc, '定位页缺关键词: %s' % token)
        # 「不是...」的否定式必须成对出现（否则读者会把 ESP32 读成"也是"）
        self.assertRegex(self.doc, r'不是\**\s*(单片机|MCU)')
        self.assertRegex(self.doc, r'(对标|竞争)')

    def test_lists_the_actual_misjudgments(self):
        """起因段必须原样收录用户报的那句错话（否则后人不知道在防什么）。"""
        self.assertIn('不是 Linux 用户空间', self.doc)
        self.assertIn('不能直接套 SDK 固件', self.doc)
        self.assertIn('zkgui', self.doc)

    def test_doc_indexable_and_registered(self):
        """定位页必须进检索面（knowledge/ 根 = kb_index_roots 的索引根之一）。"""
        roots = {r['id'] for r in __import__('kb_index_roots').ROOTS}
        self.assertIn('knowledge', roots)
        import kb_index_roots as bir
        docs = {rel for rel, _abs, _spec in bir.iter_repo_docs(U.BASE)}
        self.assertIn(POSITIONING_DOC, docs)


class TestPositioningSurfaces(unittest.TestCase):
    """② 入口面：会话起始 / 版本 / 工具资源 / 版本资源都得带定位。"""

    def setUp(self):
        self.p = kb_tools._positioning_field()

    def test_field_shape(self):
        for key in ('oneLine', 'baseline', 'mustNotSay', 'doc'):
            self.assertTrue(str(self.p.get(key) or '').strip(), 'PLATFORM_POSITIONING 缺 %s' % key)
        self.assertEqual(self.p['doc'], POSITIONING_DOC)
        self.assertIn('EasyUI', self.p['oneLine'])
        self.assertIn('LVGL', self.p['oneLine'])
        self.assertIn('buildroot', self.p['baseline'])
        self.assertIn('不是 Linux 用户空间', self.p['mustNotSay'])

    def test_instructions_text_single_source(self):
        txt = kb_tools.positioning_instructions()
        for token in ('EasyUI', 'LVGL', 'buildroot', POSITIONING_DOC):
            self.assertIn(token, txt)

    def test_mcp_instructions_registered_both_servers(self):
        import mcp_server
        import mcp_server_flat
        for name, srv in (('mcp_server', mcp_server), ('mcp_server_flat', mcp_server_flat)):
            ins = getattr(srv.mcp, 'instructions', None) or ''
            self.assertIn('EasyUI', ins, '%s 没把定位下发给会话（instructions 空）' % name)
            self.assertIn(POSITIONING_DOC, ins, '%s instructions 缺定位页指针' % name)

    def test_get_version_carries_positioning_within_budget(self):
        r = U.jcall('flythings_get_version')
        self.assertTrue(r['positioning'], 'get_version 缺 positioning 字段')
        self.assertIn('EasyUI', r['positioning']['oneLine'])
        # compact 默认形态是「问一句版本号」的返回，**不许**因为加了定位而变成 token 炸弹
        n = len(json.dumps(r, ensure_ascii=False))
        self.assertLess(n, 6000, 'compact get_version 已被撑到 %d 字符（上限 6000）' % n)

    def test_tools_and_version_resources_carry_positioning(self):
        import mcp_extras
        for label, txt in (('flythings://tools', mcp_extras._tools_doc()),
                           ('flythings://version', mcp_extras._version_doc())):
            self.assertIn('## 平台定位', txt, '%s 缺「平台定位」一节' % label)
            self.assertIn('EasyUI', txt)
            self.assertIn(POSITIONING_DOC, txt)

    def test_low_confidence_search_carries_positioning(self):
        """低置信/未命中时附定位指针：这类回答最容易让 AI 顺着沾边片段把定位写歪。"""
        out = json.loads(kb_tools.flythings_knowledge_search('这个话题知识库里肯定没有的东西xyzzy', k=3))
        if out.get('quality') in ('no_hit', 'low_confidence'):
            self.assertIn('positioning', out, '低置信返回体没带定位兜底')


class TestPositioningInToolSurface(unittest.TestCase):
    """③ 判平台能力的 op：常驻 description 必须带定位规则（不是只在知识页里）。"""

    def test_platform_ops_carry_positioning_rule(self):
        import op_spec_loader as osl
        for op in POSITIONING_OPS:
            text = osl.render(op)                       # 常驻面（tool description）
            self.assertIn('平台定位', text, '%s 常驻面缺平台定位规则' % op)
            self.assertIn(POSITIONING_DOC.split('/')[-1], text,
                          '%s 的定位规则要指到权威页' % op)

    def test_dispatcher_docstring_carries_positioning(self):
        import mcp_server
        doc = mcp_server.flythings_kb.__doc__ or ''
        for token in ('EasyUI', 'LVGL', 'buildroot', POSITIONING_DOC):
            self.assertIn(token, doc, '分发器 docstring 缺 %s' % token)


class TestPlatformIdentityOsField(unittest.TestCase):
    """④ 平台身份的 OS 层：arch 是 CPU 架构，不是 OS 名。"""

    def test_top_os_declared(self):
        self.assertIn('FlyThings OS', pl.TOP_OS)
        self.assertIn('Linux', pl.TOP_OS)
        self.assertEqual(pl.POSITIONING_DOC, POSITIONING_DOC)

    def test_describe_rows_carry_os(self):
        rows = pl.describe()
        self.assertTrue(rows)
        for r in rows:
            self.assertEqual(r.get('os'), pl.TOP_OS,
                             '%s 行缺 os（AI 会把 arch 读成 OS 名）' % r.get('platform'))

    def test_v85x_note_carries_os_and_baseline(self):
        note = pl.meta('V85X')['note']
        self.assertIn('FlyThings OS', note)
        self.assertIn('Linux', note)


class TestMisconceptionFrozen(unittest.TestCase):
    """④ 冻结：判错的原话不许在仓库正文里复活（只有「纠正语境的引用」才允许）。

    为什么要按行 + 语境豁免，而不是全仓 blacklist：
      · 定位页与 `mustNotSay` 文案**必须引用**这句错话（不引就没人知道在防什么）；
      · 修法本身也是「反面教材」——「❌ 不要写『FlyThings 用的是 LVGL』」是正确的，而
        「FlyThings 用的是 LVGL」（无纠正语境）就是事故。
    所以判据 = 出现即错，**除非同一行带纠正语境标记**（❌/错/禁/不要/mustNotSay/误判/反面/≠ 等）。
    这样后人若把纠正句删掉、只留断言，用例立刻红。
    """

    BAD = (
        (re.compile(r'zkgui\s*/\s*LVGL'), '把 GUI 写成「zkgui/LVGL」'),
        (re.compile(r'FlyThings 用(的)?是\s*LVGL'), '把 GUI 库说成 LVGL'),
        (re.compile(r'不是\s*Linux\s*用户空间'), '把 FlyThings 排除在 Linux 之外'),
    )
    # 纠正语境标记：命中行**前后 4 行窗口**内有任一个，就认为这是「引用错话并纠正」，不算复活。
    # 为什么用窗口而不是只看本行：纠正句常被行宽折断（`kb_tools.py` 的 mustNotSay / 注释就是），
    # 只看本行会把正确的反面教材误判成事故（实测踩到，故按窗口）。
    CONTEXT_OK = ('❌', '≠', '不对', '错的', '错话', '误判', '判错', '写错', '写歪', '给出错误',
                  '错误定位', '错误理解', '禁止', '不要', '不许', '别当', 'mustNotSay',
                  '反面', '纠正', '冻结', '事故', '防', 'BAD', '不是因为它')
    CONTEXT_WINDOW = 4
    # 允许出现这些说法的文件（定位页要引原话当反面教材；历史归档不改）
    ALLOW_FILES = (POSITIONING_DOC, 'CHANGELOG.md', 'VERSION_HISTORY.md', 'features_recent.json')
    SCAN_DIRS = ('knowledge', 'components', 'packages', 'wiki')
    SCAN_FILES = ('README.md', 'mcp_server.py', 'mcp_server_flat.py', 'kb_tools.py',
                  'mcp_extras.py', 'platforms.py', 'op_spec.json', 'platform_capabilities.json')
    _EXT = ('.md', '.py', '.json', '.yaml', '.txt')

    def _targets(self):
        out = []
        for d in self.SCAN_DIRS:
            for root, dirs, files in os.walk(os.path.join(U.BASE, d)):
                dirs[:] = [x for x in dirs if x not in ('__pycache__', '.git')]
                for f in files:
                    if f.endswith(self._EXT):
                        out.append(os.path.relpath(os.path.join(root, f), U.BASE))
        out += [f for f in self.SCAN_FILES if os.path.isfile(os.path.join(U.BASE, f))]
        return out

    def test_no_frozen_misconception_in_repo(self):
        bad, unreadable = [], []
        for rel in self._targets():
            rel_n = rel.replace('\\', '/')
            if rel_n in self.ALLOW_FILES:
                continue
            try:
                text = _read(rel_n)
            except OSError as e:                      # 读不了必须**报出来**（不许静默跳过：
                unreadable.append('%s (%s)' % (rel_n, e))   # 否则"扫不到"会被读成"没违规"）
                continue
            lines = text.splitlines()
            for i, line in enumerate(lines):
                for rx, why in self.BAD:
                    m = rx.search(line)
                    if not m:
                        continue
                    lo = max(0, i - self.CONTEXT_WINDOW)
                    hi = min(len(lines), i + self.CONTEXT_WINDOW + 1)
                    ctx = '\n'.join(lines[lo:hi])
                    if any(c in ctx for c in self.CONTEXT_OK):
                        continue                      # 引用并纠正 → 允许
                    bad.append('%s:%d: %s（%r）' % (rel_n, i + 1, why, m.group(0)))
        self.assertEqual(unreadable, [], '这些文件读不了，本轮扫描不完整（别当"没违规"）：\n  '
                         + '\n  '.join(unreadable))
        self.assertEqual(bad, [], '仓库里出现了已冻结的平台定位错误说法（无纠正语境）：\n  '
                         + '\n  '.join(bad))

    def test_allowlist_is_not_empty_and_points_to_real_files(self):
        """豁免名单本身要可核（防止「豁免一个不存在的文件」把门禁架空）。"""
        if not os.path.isfile(os.path.join(U.BASE, 'PUBLISH.md')):
            self.skipTest('裁剪发布版（PUBLISH.md 不随包）：该内部件/私有包按发布边界剔除')
        for rel in self.ALLOW_FILES:
            self.assertTrue(os.path.isfile(os.path.join(U.BASE, rel)), '豁免文件不存在: %s' % rel)


if __name__ == '__main__':
    unittest.main(verbosity=2)
