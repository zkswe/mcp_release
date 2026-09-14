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
        self.assertIn('flythings_ui_visual', txt)

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


class TestBinToolsSurface(unittest.TestCase):
    """「能力不止 op」：bin_tools 设备端工具必须在**工具面**可发现。

    2026-09-14 钟工反馈的回退位：外部 AI 数完 34 个 op 就断言「这版没有 touch 注入」——
    实际 touch 自 v0.27.40 起一直在 bin_tools/<平台>/ 下，只是当时工具面没有任何出口。
    三条出口各钉一条用例：get_version.binTools / flythings://tools 一节 / 分发器 docstring。
    """

    def test_get_version_exposes_bin_tools(self):
        import kb_tools
        d = json.loads(kb_tools.flythings_get_version())
        bt = d.get('binTools') or {}
        self.assertTrue(bt, 'flythings_get_version 缺 binTools 字段')
        self.assertIn('touch', bt.get('brief', {}), 'binTools.brief 缺 touch 说明')
        self.assertTrue(any('touch' in fs for fs in bt.get('byPlatform', {}).values()),
                        'binTools.byPlatform 里没有任何平台带 touch ELF')
        self.assertIn('不是 op', bt.get('note', ''), 'binTools.note 必须明说不是 op')

    def test_bin_tools_are_not_ops(self):
        """touch/busybox 是设备端 ELF，不能被当成 op（防后来人又去数 op 找触摸注入）。"""
        import kb_tools
        d = json.loads(kb_tools.flythings_get_version())
        for name in ('touch', 'busybox', 'ui_test', 'mt_test'):
            self.assertNotIn(name, d['tools'])
            self.assertNotIn(name, kb_tools.OP_NAMES)
            self.assertNotIn('flythings_' + name, d['tools'])

    def test_tools_resource_lists_bin_tools(self):
        txt = _text('flythings://tools')
        self.assertIn('设备端预编译工具', txt)
        self.assertIn('bin_tools', txt)
        self.assertIn('不是 op', txt)
        self.assertIn('touch', txt)

    def test_dispatcher_docstring_points_to_bin_tools(self):
        import mcp_server
        doc = mcp_server.flythings_kb.__doc__ or ''
        self.assertIn('bin_tools', doc)
        self.assertIn('binTools', doc)


if __name__ == '__main__':
    unittest.main(verbosity=2)
