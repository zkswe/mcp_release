# -*- coding: utf-8 -*-
"""发布版薄壳 —— 实现体不在本文件。

本模块的函数体由 `bin/zkuitool.exe` 承载（Cython 编译的机器码，随包分发）。
此处只保留**签名、常量与转发**，供 MCP 以 `import ui_diff` 的方式继续使用。
"""
from _zktool import rpc as _rpc_call, cli as _cli_call

MOD = 'ui_diff'

def diff_images(a_path, b_path, tol=2, shift=1, min_area=4, open_k=3, out_png='', out_json='', box=None, blur=0.7, noise_bbox=10, show_noise=False):
    return _rpc_call(MOD, 'diff_images', a_path, b_path, tol, shift, min_area, open_k, out_png, out_json, box, blur, noise_bbox, show_noise)


if __name__ == '__main__':
    raise SystemExit(_cli_call(MOD))
