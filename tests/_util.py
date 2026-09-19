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


_FTU_BYTES = {}


def ftu_bytes():
    """返回一个**真实合法**的 ftu 字节流（用随包 fui pack 一次性生成后缓存）。

    背景：以前用例直接写 4 字节占位 `ZKSR` 充当 ftu；规则①「只有 ftu 没 json → 自动 unpack」
    上线后，占位 ftu 会被判定为异常 ftu 并报错（这是期望行为），所以 fixture 得用真 ftu。
    """
    if 'v' in _FTU_BYTES:
        return _FTU_BYTES['v']
    data = b''
    tmp = tempfile.mkdtemp(prefix='mcp_ftu_')
    try:
        import project_tools as pt
        jp = os.path.join(tmp, 'main.json')
        write(jp, json.dumps({'id': 0, 'resolution': {'width': 1024, 'height': 600},
                              'position': {'left': 0, 'top': 0, 'width': 1024, 'height': 600}},
                             ensure_ascii=False))
        pt._run_fui('pack', tmp)
        fp = os.path.join(tmp, 'main.ftu')
        if os.path.isfile(fp):
            data = io.open(fp, 'rb').read()
    except Exception:
        data = b''
    finally:
        import shutil as _sh
        _sh.rmtree(tmp, ignore_errors=True)
    _FTU_BYTES['v'] = data
    return data
