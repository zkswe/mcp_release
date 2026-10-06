# -*- coding: utf-8 -*-
"""发布版薄壳 —— 实现体不在本文件。

本模块的函数体由 `bin/zkuitool.exe` 承载（Cython 编译的机器码，随包分发）。
此处只保留**签名、常量与转发**，供 MCP 以 `import check_all` 的方式继续使用。
"""
from _zktool import rpc as _rpc_call, cli as _cli_call

MOD = 'check_all'

FUI = "C:\\Users\\zkswe\\.openclaw\\workspace\\tools\\FlyThings_mcp_open\\ui_tools\\..\\toolchain\\fui.exe"
SEEKBAR_PIC_FIELDS = ["progressPic", "secondaryProgressPic", "backgroundPic", "thumbPic"]

def verify_assets(project_root):
    return _rpc_call(MOD, 'verify_assets', project_root)

def check_aa_assets(project_root, timeout=1800):
    return _rpc_call(MOD, 'check_aa_assets', project_root, timeout)

def check_arc_quality(project_root):
    return _rpc_call(MOD, 'check_arc_quality', project_root)

def check_shape_audit(project_root, kind):
    return _rpc_call(MOD, 'check_shape_audit', project_root, kind)

def _required_keys(tpl_key):
    return _rpc_call(MOD, '_required_keys', tpl_key)


if __name__ == '__main__':
    raise SystemExit(_cli_call(MOD))
