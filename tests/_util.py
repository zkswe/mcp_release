# -*- coding: utf-8 -*-
"""契约测试公共工具（stdlib only，离线零副作用）。

跑法（MCP 根目录或任意位置）：
    python -m unittest discover -s tests -q
    python scripts/check_consistency.py --with-tests
"""
import asyncio
import io
import json
import os
import sys
import tempfile

TESTS = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(TESTS)
for _p in (BASE, os.path.join(BASE, 'ui_tools'), TESTS):
    if _p not in sys.path:
        sys.path.insert(0, _p)

EXAMPLES = os.path.join(BASE, 'ui_tools', 'examples')


def call(op, args=None):
    """走分发器（与客户端完全同一条路径），返回原始字符串。

    args 传 dict 会自动 json.dumps；传 str 则原样作为 args 下发（用于测非法 JSON 等边界）。
    """
    import mcp_server
    payload = args if isinstance(args, str) else json.dumps(args or {}, ensure_ascii=False)
    return asyncio.run(mcp_server.flythings_kb(op=op, args=payload))


def jcall(op, args=None):
    return json.loads(call(op, args))


def manifest():
    return json.load(io.open(os.path.join(BASE, 'tools_manifest.json'), encoding='utf-8'))


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    io.open(path, 'w', encoding='utf-8', newline='\n').write(text)


def fixture(name):
    return os.path.join(EXAMPLES, name)


def project(tmp=None):
    """最小可识别工程骨架：package.properties + ui/ + resources/images/。"""
    tmp = tmp or tempfile.mkdtemp(prefix='mcp_test_')
    write(os.path.join(tmp, 'package.properties'), 'projectName=unittest\n')
    os.makedirs(os.path.join(tmp, 'resources', 'images'), exist_ok=True)
    os.makedirs(os.path.join(tmp, 'ui'), exist_ok=True)
    return tmp


def cleanup(path):
    import shutil
    shutil.rmtree(path, ignore_errors=True)
