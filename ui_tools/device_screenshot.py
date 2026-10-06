# -*- coding: utf-8 -*-
"""发布版薄壳 —— 实现体不在本文件。

本模块的函数体由 `bin/zkuitool.exe` 承载（Cython 编译的机器码，随包分发）。
此处只保留**签名、常量与转发**，供 MCP 以 `import device_screenshot` 的方式继续使用。
"""
from _zktool import rpc as _rpc_call, cli as _cli_call

MOD = 'device_screenshot'

MONTHS3 = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
MI_FMT = {"0": "yuyv422", "1": "argb8888", "2": "abgr8888", "3": "bgra8888", "4": "rgb565", "5": "argb1555", "6": "argb4444", "10": "yuv422sp", "11": "yuv420sp"}
VDEC_CHN_HINT = "vdec 通道选错是多路场景「抓不到视频帧」的头号原因：工具默认 chn 0（单路/历史口径），SmartPanel 拼墙播放器（多屏拼接 h264_player）在 chn 1。换通道重试 vdec_chn=1 / 0；手工等价命令 `zkshot <out.raw> vdec <chn> 0`。注意：Z20 屏保 zkmedia 走 FFmpeg 软解、不建 MI VDEC 通道（chn 0 抽不到帧不一定是工具问题，见 knowledge/devflow/device-screenshot.md §4.1.1）。"

def capture(device='', out='', fmt='png', scale=1.0, quality=90, fb='/dev/fb0', width=0, height=0, pixel='auto', flip='', rotate='auto', offset_y=-1, crop='', layer='ui', timeout=180, keep_raw=False, name='', adb='', vdec_chn=0, _retry=False):
    return _rpc_call(MOD, 'capture', device, out, fmt, scale, quality, fb, width, height, pixel, flip, rotate, offset_y, crop, layer, timeout, keep_raw, name, adb, vdec_chn, _retry, _timeout=timeout + 30)

def _run(argv, timeout=60):
    """adb 执行仍走单一入口 adb_tools（离线守卫契约用例钉这条）。"""
    import adb_tools
    return adb_tools._run(argv, timeout=timeout)


if __name__ == '__main__':
    raise SystemExit(_cli_call(MOD))
