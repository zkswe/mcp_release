# -*- coding: utf-8 -*-
"""发布版薄壳 —— 实现体不在本文件。

本模块的函数体由 `bin/zkuitool.exe` 承载（Cython 编译的机器码，随包分发）。
此处只保留**签名、常量与转发**，供 MCP 以 `import html2json` 的方式继续使用。
"""
from _zktool import rpc as _rpc_call, cli as _cli_call

MOD = 'html2json'

ID_BASE = {"textview": 50000, "button": 20000, "edittext": 51000, "seekbar": 91000, "window": 110000, "listview": 80000, "checkbox": 94500, "radiogroup": 94000, "radiobutton": 94100, "subitem": 24000, "imageanim": 160000, "circlebar": 130000, "diagram": 60000, "digitalclock": 93000, "slidewindow": 30000, "scrollwindow": 32000, "pagewindow": 31000, "slidetext": 98000, "cameraview": 97000, "painter": 52000, "pointer": 90000, "qrcode": 92000, "videoview": 95000}
CLASS_MAP = {"textview": ["text", "tv", "label", "txt"], "button": ["btn", "button", "b"], "edittext": ["input", "edit", "edittext"], "seekbar": ["bar", "seekbar", "progress", "slider", "range"], "window": ["card", "window", "win", "panel"], "modal": ["modal", "dialog", "popup"], "listview": ["list", "listview", "lv"], "checkbox": ["checkbox", "check", "cb"], "radiogroup": ["radio", "radiogroup", "rg"], "icon": ["icon", "img", "image", "pic", "iconfont"], "circlebar": ["circlebar", "circular", "ring"], "diagram": ["diagram", "wave", "chart"], "digitalclock": ["digitalclock", "clock", "time"], "imageanim": ["imageanim", "anim", "gif"], "slidewindow": ["slidewindow", "slide", "launcher"], "scrollwindow": ["scrollwindow", "scrollwin", "scroll"], "pagewindow": ["pagewindow", "page", "pager"], "slidetext": ["slidetext", "candidate", "cand"], "cameraview": ["cameraview", "camera"], "painter": ["painter", "canvas", "draw"], "pointer": ["pointer", "gauge", "dial"], "qrcode": ["qrcode", "qr"], "videoview": ["videoview", "video"]}
ALIGN = {"left": 36, "center": 37, "right": 38, "l": 36, "c": 37, "r": 38}
AUTO_NAME = {"textview": "TextView", "button": "Button", "edittext": "EditText", "seekbar": "SeekBar", "window": "Window", "listview": "ListView", "checkbox": "CheckBox", "radiogroup": "RadioGroup", "icon": "ImageView"}

def html2json(input_html, output_json=None, res=None, asset_dir=None, merge_windows=False):
    return _rpc_call(MOD, 'html2json', input_html, output_json, res, asset_dir, merge_windows)


if __name__ == '__main__':
    raise SystemExit(_cli_call(MOD))
