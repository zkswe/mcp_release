# -*- coding: utf-8 -*-
"""发布版薄壳 —— 实现体不在本文件。

本模块的函数体由 `bin/zkuitool.exe` 承载（Cython 编译的机器码，随包分发）。
此处只保留**签名、常量与转发**，供 MCP 以 `import ui_editor` 的方式继续使用。
"""
from _zktool import rpc as _rpc_call, cli as _cli_call

MOD = 'ui_editor'

def make_editor(target, out_html=''):
    return _rpc_call(MOD, 'make_editor', target, out_html)


if __name__ == '__main__':
    raise SystemExit(_cli_call(MOD))
