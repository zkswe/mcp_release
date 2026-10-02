# -*- coding: utf-8 -*-
"""旧 CLI 名清空的契约用例（v0.27.178）。

判据（2026-10-02）：**名字只有指向真实存在的东西才该留**。
`fyx` 在本仓库没有任何实体，却曾登记进 `tools_manifest.json` 名词表、并当作 op 参数名
`with_fyx`——AI 读到会以为还有这条命令可调。本用例钉住「清空不许回退」。

范围只限**常驻契约面**（名词表 / op 签名 / kb_tools 源码），**不含知识文档**：
`knowledge/devflow/cli-fun-toolchain.md` 里的 fuse 痕迹是兼容识别知识（老工程为什么带
`.fuse/` 产物目录、`FUSE_BUILD` 宏），删了反而无法诊断。
区分标准 = **要认识的老形态保留，可调的命令清空**。
"""
import ast
import io
import json
import os
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEPRECATED = ('fyx', 'fuse')      # 已不在当前工具链的历史命令名
LIVE_CLI = {'fun', 'fui'}         # 当前在用的命令行


def _read(p):
    with io.open(p, encoding='utf-8') as f:
        return f.read()


class TestCliNames(unittest.TestCase):

    def test_manifest_cli_lists_only_live_commands(self):
        man = json.loads(_read(os.path.join(BASE, 'tools_manifest.json')))
        keys = set((man.get('cli') or {}).keys())
        self.assertEqual(keys, LIVE_CLI,
                         '名词表只应登记当前在用的命令 %s，实际 %s'
                         % (sorted(LIVE_CLI), sorted(keys)))

    def test_op_signature_has_no_deprecated_cli(self):
        tree = ast.parse(_read(os.path.join(BASE, 'kb_tools.py')))
        hits = []
        for n in ast.walk(tree):
            if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not n.name.startswith('flythings_'):
                continue
            a = n.args
            for x in list(a.posonlyargs) + list(a.args) + list(a.kwonlyargs):
                if any(d in x.arg.lower() for d in DEPRECATED):
                    hits.append('%s(%s)' % (n.name, x.arg))
        self.assertEqual(hits, [], 'op 签名里还有旧 CLI 名参数：%s' % hits)

    def test_kb_tools_source_has_no_fyx(self):
        """fyx 已从仓库清零：kb_tools（AI 直接读的契约面）里不许再出现。"""
        src = _read(os.path.join(BASE, 'kb_tools.py'))
        self.assertNotIn('fyx', src.lower(),
                         'kb_tools.py 里又出现了 fyx（旧 CLI 名残留）')

    def test_fuse_only_survives_as_compat_knowledge(self):
        """fuse 允许留在知识文档（老形态识别），但不得作为命令行回到名词表。"""
        man = json.loads(_read(os.path.join(BASE, 'tools_manifest.json')))
        self.assertNotIn('fuse', set((man.get('cli') or {}).keys()))
        kbdoc = os.path.join(BASE, 'knowledge', 'devflow', 'cli-fun-toolchain.md')
        self.assertTrue(os.path.isfile(kbdoc),
                        'fuse 兼容知识文档必须存在（老工程诊断依赖它）')

    def test_with_fyx_param_gone(self):
        """`with_fyx` 参数已删（唯一调用恒传 True，参数无意义；实际行为=复制 fun.exe）。"""
        tree = ast.parse(_read(os.path.join(BASE, 'project_tools.py')))
        for n in ast.walk(tree):
            if isinstance(n, ast.FunctionDef) and n.name == 'flythings_attach_cli_tools':
                names = [x.arg for x in n.args.args]
                self.assertEqual(names, ['project_root'],
                                 'attach_cli_tools 签名应只剩 project_root，实际 %s' % names)
                return
        self.fail('project_tools.py 里找不到 flythings_attach_cli_tools')


if __name__ == '__main__':
    unittest.main()
