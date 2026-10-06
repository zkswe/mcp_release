# -*- coding: utf-8 -*-
"""发布版薄壳 —— 实现体不在本文件。

本模块的函数体由 `bin/zkuitool.exe` 承载（Cython 编译的机器码，随包分发）。
此处只保留**签名、常量与转发**，供 MCP 以 `import region_attrib` 的方式继续使用。
"""
from _zktool import rpc as _rpc_call, cli as _cli_call

MOD = 'region_attrib'

LAYER_C = ["C/EMIT-FIELDS", "C/ASSET-GEOMETRY"]
LAYER_E = ["E/RENDERER-BLINDSPOT", "E/FONT-METRICS"]
LAYER_A = ["A/FRONTEND-REPORT"]
LAYER_U = ["U/UNATTRIBUTED"]

def attribute(page_json, render_png, device_png, render_report=None, frontend_report=None, project_root='', tol=2, max_ratio=1.0, min_block=8, runtime_caps=(), top=None):
    return _rpc_call(MOD, 'attribute', page_json, render_png, device_png, render_report, frontend_report, project_root, tol, max_ratio, min_block, runtime_caps, top)


if __name__ == '__main__':
    raise SystemExit(_cli_call(MOD))
