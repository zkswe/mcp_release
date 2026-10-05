# -*- coding: utf-8 -*-
"""契约用例：仓内 skill（`.dsh/skills/<name>/SKILL.md`）。

为什么钉（2026-10-05 需求方问「远端提供的这些库是否有对应 skill/agent 文件让 AI 正确去处理」）：
仓里原先**一个 skill 都没有**，库用法的入口只有 RAG + MCP op。skill 是把**流程级**判断
（顺序错了就返工的四步）交给 AI 的载体，所以它本身必须是**可信的**：

  ① **格式必须合 DSH 规范** —— 扫描根是工作区 `.dsh/skills/` 与 `.agents/skills/`，
     只扫**直接子项**（目录包 `<name>/SKILL.md` 或扁平 `<name>.md`，**不递归**）；
     frontmatter 必须有 `name` + `description`，`name` 必须匹配 `/^[a-z0-9]+(?:-[a-z0-9]+)*$/`。
     ⚠️ **格式不合法会被静默跳过**（只在日志里 warn，模型侧看不到"少了哪个 skill"），
     所以这条必须由用例兜住，不能靠肉眼。
  ② **引用的 op 名必须真实存在** —— 写错一个 op 名，AI 照着调就踩空。
  ③ **引用的仓内文档必须真实存在** —— 同上。
"""
import io
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import op_spec_loader as L  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS_DIR = os.path.join(REPO, '.dsh', 'skills')
NAME_RE = re.compile(r'^[a-z0-9]+(?:-[a-z0-9]+)*$')
OPS = set(L.registered())


def _skills():
    """扫工作区 skill 根的直接子项（与 DSH 的发现口径一致：不递归）。"""
    out = []
    if not os.path.isdir(SKILLS_DIR):
        return out
    for entry in sorted(os.listdir(SKILLS_DIR)):
        d = os.path.join(SKILLS_DIR, entry)
        if os.path.isdir(d):
            f = os.path.join(d, 'SKILL.md')
            if os.path.isfile(f):
                out.append((entry, f))
        elif entry.endswith('.md'):
            out.append((entry[:-3], os.path.join(SKILLS_DIR, entry)))
    return out


def _frontmatter(text):
    m = re.match(r'^---\r?\n(.*?)\r?\n---\r?\n', text, re.S)
    if not m:
        return None
    fm = {}
    for line in m.group(1).splitlines():
        if ':' in line and not line.startswith((' ', '\t', '-')):
            k, v = line.split(':', 1)
            fm[k.strip()] = v.strip()
    return fm


class TestSkillsExist(unittest.TestCase):
    def test_three_flow_skills_present(self):
        names = {n for n, _ in _skills()}
        for want in ('flythings-new-project', 'flythings-use-library',
                     'flythings-device-acceptance'):
            self.assertIn(want, names, '缺 skill %s（本会话 skill 目录里应能看到它）' % want)

    def test_no_nested_skill_files(self):
        """DSH **不递归**扫 `**/SKILL.md` —— 嵌套放的 skill 永远发现不到，属于静默失效。"""
        bad = []
        for root, dirs, files in os.walk(SKILLS_DIR):
            if os.path.abspath(root) == os.path.abspath(SKILLS_DIR):
                continue
            depth = os.path.relpath(root, SKILLS_DIR).count(os.sep)
            if depth >= 1 and 'SKILL.md' in files:
                bad.append(os.path.relpath(os.path.join(root, 'SKILL.md'), REPO))
        self.assertEqual(bad, [], '嵌套 SKILL.md 发现不到（要放成 <name>/SKILL.md）：%s' % bad)


class TestSkillFrontmatter(unittest.TestCase):
    def test_frontmatter_present_and_valid(self):
        missing = []
        for name, path in _skills():
            t = io.open(path, encoding='utf-8').read()
            fm = _frontmatter(t)
            if fm is None:
                missing.append('%s: 没有 YAML frontmatter' % name)
                continue
            if not fm.get('name'):
                missing.append('%s: frontmatter 缺 name' % name)
            elif not NAME_RE.match(fm['name']):
                missing.append('%s: name=%r 不合规（须 ^[a-z0-9]+(-[a-z0-9]+)*$）'
                               % (name, fm['name']))
            if not fm.get('description'):
                missing.append('%s: frontmatter 缺 description（它决定何时加载）' % name)
        self.assertEqual(missing, [], '不合规的 skill（DSH 会静默跳过）：\n  ' + '\n  '.join(missing))

    def test_dir_name_matches_frontmatter_name(self):
        for name, path in _skills():
            fm = _frontmatter(io.open(path, encoding='utf-8').read()) or {}
            self.assertEqual(fm.get('name'), os.path.basename(os.path.dirname(path)),
                             '目录名与 frontmatter.name 不一致（%s）' % name)

    def test_description_is_specific_enough(self):
        """description 要能判断"何时加载"：必须点出触发场景，不能只说"这是个流程"。"""
        for name, path in _skills():
            fm = _frontmatter(io.open(path, encoding='utf-8').read()) or {}
            d = str(fm.get('description') or '')
            self.assertGreater(len(d), 40, '%s 的 description 太短，无法判断何时加载' % name)
            self.assertTrue(re.search(r'用户说|当|时加载|加载', d),
                            '%s 的 description 没说清触发条件' % name)


class TestSkillReferencesAreReal(unittest.TestCase):
    """②③ 引用的 op 名与仓内文档必须真实存在 —— 写错的话 AI 照着做就踩空。"""

    def test_referenced_ops_exist(self):
        bad = []
        for name, path in _skills():
            t = io.open(path, encoding='utf-8').read()
            for op in sorted(set(re.findall(r'flythings_[a-z_]+', t))):
                if op not in OPS:
                    bad.append('%s: 引用了不存在的 op %s' % (name, op))
        self.assertEqual(bad, [], 'skill 里引用了不存在的 op：\n  ' + '\n  '.join(bad))

    def test_referenced_repo_paths_exist(self):
        """文档路径要真实存在；`knowledge/...` 与 `packages/...`、`components/...` 都算。"""
        bad = []
        pat = re.compile(r'`((?:knowledge|packages|components)/[A-Za-z0-9_./-]+\.(?:md|yaml))`')
        for name, path in _skills():
            t = io.open(path, encoding='utf-8').read()
            for rel in sorted(set(pat.findall(t))):
                if not os.path.exists(os.path.join(REPO, rel)):
                    bad.append('%s: 引用了不存在的文档 %s' % (name, rel))
        self.assertEqual(bad, [], 'skill 里引用了不存在的仓内文档：\n  ' + '\n  '.join(bad))

    def test_skills_do_not_mention_fv_framework(self):
        """范围口径：MCP 不服务 fv 新框架 —— skill 里也不许把它当可用路径教给 AI。"""
        bad = []
        for name, path in _skills():
            t = io.open(path, encoding='utf-8').read()
            for kw in ('fsc.json', 'app/**/*.fv', 'libzkgui.so'):
                if kw in t and '不服务' not in t and '别去用' not in t:
                    bad.append('%s: 提到 %s 却没说明"不在服务范围"' % (name, kw))
        self.assertEqual(bad, [], '\n  '.join(bad))


class TestWorkspaceInstructions(unittest.TestCase):
    """`AGENTS.md` = 工作区持久指令（DSH 自动加载项目根链上的 AGENTS.md/CLAUDE.md）。

    与 skill 的分工：skill 按**触发条件**加载（流程级），AGENTS.md 是**一进仓就有的基线**
    （纪律 + 材料在哪）。需求方问「有没有材料让 AI 正确处理」时，这两层缺一不可。
    """

    def test_agents_md_exists_and_covers_invariants(self):
        p = os.path.join(REPO, 'AGENTS.md')
        self.assertTrue(os.path.isfile(p), '缺 AGENTS.md（AI 进仓没有基线指令）')
        t = io.open(p, encoding='utf-8').read()
        for kw in ('check_consistency.py', 'EasyUI', '不服务 fv', 'package.yaml',
                   'platforms.md', 'flythings-new-project', '.dsh/skills', 'src/activity'):
            self.assertIn(kw, t, 'AGENTS.md 没写到关键点：%s' % kw)

    def test_agents_md_ops_exist(self):
        """AGENTS.md 里点名的 op 必须真实存在（否则 AI 一进仓就照着错名字调）。"""
        t = io.open(os.path.join(REPO, 'AGENTS.md'), encoding='utf-8').read()
        bad = [op for op in sorted(set(re.findall(r'flythings_[a-z_]+', t))) if op not in OPS]
        self.assertEqual(bad, [], 'AGENTS.md 引用了不存在的 op：%s' % bad)

    def test_agents_md_does_not_promise_fv(self):
        """范围口径要写清：提 fv 必须同时说明"本仓不服务"。"""
        t = io.open(os.path.join(REPO, 'AGENTS.md'), encoding='utf-8').read()
        if 'fv' in t:
            self.assertIn('不服务', t, 'AGENTS.md 提到 fv 却没说"不服务"')
            self.assertIn('不要采用', t, 'AGENTS.md 提到 fv 却没给"别用"的明确指令')


if __name__ == '__main__':
    unittest.main()
