# -*- coding: utf-8 -*-
"""发布版薄壳 —— 实现体不在本文件。

本模块的函数体由 `bin/zkuitool.exe` 承载（Cython 编译的机器码，随包分发）。
此处只保留**签名、常量与转发**，供 MCP 以 `import json2img` 的方式继续使用。
"""
from _zktool import rpc as _rpc_call, cli as _cli_call

MOD = 'json2img'

__version__ = "0.1.1"
ALIGN_MEASURED = {"36": ["l", "c"], "37": ["c", "c"], "38": ["r", "c"], "33": ["c", "t"], "41": ["c", "b"]}
ALIGN_UNCALIBRATED = {"4": ["l", "c"], "5": ["c", "c"], "6": ["r", "c"], "0": ["l", "t"], "1": ["c", "t"], "2": ["r", "t"]}
ALIGN_DEFAULT = [36, ["l", "c"]]
ICON_TIERS = [56, 24, 22]
STATUS_VALUES = ["implemented", "approximate", "unsupported"]


if __name__ == '__main__':
    raise SystemExit(_cli_call(MOD))
