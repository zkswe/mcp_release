# -*- coding: utf-8 -*-
"""MCP 原生原语契约：resources（知识文档/工具清单/版本）+ prompts（常用流程模板）。

为什么要有（检讨报告 §3.6）：只用 tools 时知识只能靠检索拿 3 条片段，客户端无法把整篇文档
当上下文挂载；prompts 则把「建工程 / 原型转布局 / 验收 / 部署调试 / 依赖」流程固化下来。
本用例钉住：能列、能读、能渲染、**越权路径必须拒绝**、参数缺失时提示先问用户。
"""
import asyncio
import json
import os
import subprocess
import sys
import unittest

import _util as U

RES_URIS = ('flythings://catalog/knowledge', 'flythings://tools', 'flythings://version')


def _server():
    import mcp_server
    return mcp_server.mcp


def _text(uri):
    items = asyncio.run(_server().read_resource(uri))
    return ''.join(getattr(c, 'content', '') for c in items)


class TestResources(unittest.TestCase):
    def test_listed(self):
        uris = {str(r.uri) for r in asyncio.run(_server().list_resources())}
        for u in RES_URIS:
            self.assertIn(u, uris)
        tmpls = {t.uriTemplate for t in asyncio.run(_server().list_resource_templates())}
        # 分类文档 + 根目录文档两个模板（FastMCP 模板参数只匹配单段，不能一个 {path} 通吃）
        self.assertIn('flythings://knowledge/{folder}/{file}', tmpls)
        self.assertIn('flythings://knowledge/{file}', tmpls)

    def test_knowledge_catalog_lists_docs(self):
        txt = _text('flythings://catalog/knowledge')
        self.assertIn('flythings://knowledge/', txt)
        for expect in ('devflow/', 'uicontrols/', 'device-screenshot.md'):
            self.assertIn(expect, txt)

    def test_read_knowledge_doc(self):
        txt = _text('flythings://knowledge/devflow/device-screenshot.md')
        self.assertIn('双缓冲', txt)
        self.assertIn('rotateScreen', txt)

    def test_read_root_doc(self):
        txt = _text('flythings://knowledge/README.md')
        self.assertIn('knowledge', txt)

    def test_tools_resource_has_risk_levels(self):
        txt = _text('flythings://tools')
        self.assertIn('read', txt)
        self.assertIn('flythings_', txt)
        self.assertIn('风险分级', txt)

    def test_version_resource(self):
        import kb_tools
        txt = _text('flythings://version')
        self.assertIn(kb_tools.MCP_VERSION, txt)
        self.assertIn(str(len(kb_tools.OP_NAMES)), txt)

    def test_path_escape_blocked(self):
        for bad in ('flythings://knowledge/../mcp_server.py',
                    'flythings://knowledge/%s' % '..%2Fmcp_server.py',
                    'flythings://knowledge/devflow/../../../mcp_server.py'):
            with self.assertRaises(Exception):
                _text(bad)

    def test_missing_doc_raises(self):
        with self.assertRaises(Exception):
            _text('flythings://knowledge/devflow/no-such-doc.md')


class TestPrompts(unittest.TestCase):
    WANT = {
        'flythings-new-project': ['platform', 'resolution', 'requirement'],
        'flythings-ui-from-prototype': ['requirement'],
        'flythings-ui-verify': ['project_root'],
        'flythings-deploy-debug': ['project_root', 'device'],
        'flythings-package-deps': ['requirement', 'platform'],
    }

    def test_listed_with_args(self):
        got = {p.name: [a.name for a in (p.arguments or [])]
               for p in asyncio.run(_server().list_prompts())}
        for name, args in self.WANT.items():
            self.assertIn(name, got, 'prompt 缺失: %s' % name)
            self.assertEqual(got[name], args)

    def test_render_with_args(self):
        g = asyncio.run(_server().get_prompt('flythings-ui-verify',
                                             {'project_root': 'C:/demo'}))
        txt = g.messages[0].content.text
        self.assertIn('C:/demo', txt)
        self.assertIn('flythings_ui_preview', txt)
        self.assertIn('flythings_device_screenshot', txt)
        self.assertIn('flythings_ui_diff', txt)

    def test_missing_args_tell_to_ask(self):
        g = asyncio.run(_server().get_prompt('flythings-deploy-debug', {}))
        self.assertIn('未提供', g.messages[0].content.text)

    def test_prompts_carry_safety_defaults(self):
        for name in self.WANT:
            g = asyncio.run(_server().get_prompt(name, {}))
            txt = g.messages[0].content.text
            self.assertIn('安全默认', txt, '%s 缺安全默认提醒' % name)


class TestBothServersRegisterExtras(unittest.TestCase):
    def test_flat_server_too(self):
        snip = ("import sys,json,asyncio;sys.path.insert(0,%r);import mcp_server_flat as f;"
                "r=asyncio.run(f.mcp.list_resources());p=asyncio.run(f.mcp.list_prompts());"
                "print(json.dumps({'res':len(r),'prompts':len(p)}))" % U.BASE)
        r = subprocess.run([sys.executable, '-X', 'utf8', '-c', snip],
                           capture_output=True, text=True, cwd=U.BASE)
        self.assertTrue(r.stdout.strip(), (r.stderr or '')[-300:])
        d = json.loads(r.stdout.strip().splitlines()[-1])
        self.assertGreaterEqual(d['res'], 3)
        self.assertEqual(d['prompts'], 5)


if __name__ == '__main__':
    unittest.main(verbosity=2)
