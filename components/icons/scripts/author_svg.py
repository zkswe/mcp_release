# -*- coding: utf-8 -*-
"""author_svg.py —— 图标几何与语义的**权威定义（手工编写）**，并生成 `svg/**` + `catalog.json`

为什么用脚本"手写"而不是一个个 .svg 文件敲：
  图标要成套、要统一网格/线宽/光学居中，还要 ios/material 两风格同源 —— 用参数化几何写
  （太阳的射线数、云的鼓包半径、铃铛的弧度都可调），比 86 个孤立文件更好维护、更好评审。
  产物依旧是**每个人一眼能读的独立 .svg**：`svg/<分类>/<名字>[_<风格>].svg`，
  改完这里重跑一次即可；`svg/` 里的文件也可以被任何标准 SVG 工具直接打开。

设计规范（README §3 有完整说明）：
  - 非天气图标：`viewBox="0 0 24 24"`，2 单位网格对齐，光学居中；线宽基准 data-base-stroke=1.75
  - 天气图标：`viewBox="0 0 100 100"`，几何 **1:1 复刻**已量产的 inSightOS3 `wx_*` 天气图标
    （太阳=实心圆+8 射线 / 云=鼓包+平底 / 雨=水滴 / 雪=六轴雪花 / 月牙），基准线宽 7
  - ios：线框为主（stroke，round cap/join）；material：实心为主（fill + 挖空 data-cut）
  - 颜色一律 `currentColor`（渲染时按 --color 烘焙成纯色 PNG，不做灰阶/渐变/阴影）

**v0.2.0 起的分工**（2026-09-16）：
  · 天气/开关选项/通用系统/智能家居 四类已改为收录 **vendor/tabler**（见 gen_catalog.py），
    本文件的这些几何**不再进入主线**，只在 `svg_retired/` 留档（可删，不影响任何流程）；
  · 自绘只保留 **两轮车仪表（vehicle）**：转向箭头/大灯/远光/定速巡航 —— Tabler 风格不匹配。

用法：
    python scripts/author_svg.py            # 生成 svg/（主线自绘）+ svg_retired/（留档）
    python scripts/author_svg.py --check    # 只校验（不写盘）
"""

import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

from geomlib import (P, C, R, LN, ST, FL, NONE, poly_d, arc_d, arc_pts, circle_pts,
                     ellipse_pts, circle_circle, cloud_d, crescent_d, star_pts, heart_pts,
                     sun_els, drop_els, snow_els, bolt_els, arrow_els, gear_els)

VERSION = '0.1.0'


# --------------------------------------------------------------------------- #
# 通用小工具
# --------------------------------------------------------------------------- #
def rot_pts(pts, deg, cx=12.0, cy=12.0):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return [(cx + (x - cx) * c - (y - cy) * s, cy + (x - cx) * s + (y - cy) * c) for x, y in pts]


def wedge(cx, cy, r, a0, a1):
    """扇形（用于实心弧块）。"""
    return poly_d([(cx, cy)] + arc_pts(cx, cy, r, a0, a1) + [(cx, cy)], close=True)


def slash_band(x1, y1, x2, y2, w=4.6):
    """斜杠（"禁用"语义）：先画同宽的 cut 带，再压一条同色斜线 —— 用顺序合成造出"缝"。"""
    return [LN(x1, y1, x2, y2, a=ST(w), cut=True), LN(x1, y1, x2, y2, a=ST(1.75))]


def drape_pts(x, y0, y1, amp, phase=0.0, n=18):
    """窗帘波浪边（正弦采样，用于实心帘布轮廓）。"""
    pts = []
    for i in range(n + 1):
        t = i / float(n)
        y = y0 + (y1 - y0) * t
        pts.append((x + amp * math.sin(2 * math.pi * t + phase), y))
    return pts


# --------------------------------------------------------------------------- #
# 图标表
# --------------------------------------------------------------------------- #
ICONS = []


def icon(cat, name, tags, styles, sizes, grid=24, base=1.75, aliases=(), legacy=(),
         note=None, color=(255, 255, 255)):
    """注册一个图标。styles: {风格: {状态: [元素]}}；状态 '' 表示单态。"""
    ICONS.append(dict(category=cat, name=name, tags=list(tags), styles=styles, sizes=list(sizes),
                      grid=grid, base=base, aliases=list(aliases), legacy=list(legacy),
                      note=note, defaultColor=list(color)))


def two(off, on):
    return {'off': list(off), 'on': list(on)}


def one(els):
    return {'': list(els)}


# =========================================================================== #
# 一、天气（100 网格，1:1 复刻 inSightOS3 wx_* 画法）
# =========================================================================== #
W_BASE = 7.0            # 云的描边（100 网格）；太阳射线 2.6；雪花 5.5
W_SUN = 2.6

# 三鼓包云：左右圆与底线相切（cy+r == yb），中圆抬高——轮廓天然是"鼓包+平底"
CLOUD3 = [(29.0, 56.0, 26.0), (50.0, 45.0, 29.0), (71.0, 56.0, 26.0)]
CLOUD3_YB = 82.0
# 双鼓包云（大：占满下半幅）与双鼓包云（小：给太阳/月牙让位）
CLOUD2 = [(36.0, 50.0, 20.0), (60.0, 46.0, 24.0)]
CLOUD2_YB = 70.0
CLOUD2S = [(33.0, 49.0, 17.0), (50.0, 46.0, 20.0)]
CLOUD2S_YB = 66.0


def w_cloud_els(bumps=3, shift=0.0, mode='stroke', small=False):
    if small:
        cs, yb = CLOUD2S, CLOUD2S_YB
    elif bumps == 3:
        cs, yb = CLOUD3, CLOUD3_YB
    else:
        cs, yb = CLOUD2, CLOUD2_YB
    cs = [(cx, cy + shift, r) for cx, cy, r in cs]
    return [P(cloud_d(cs, yb + shift), FL() if mode == 'fill' else ST(W_BASE))]


def weather(cat_name, tags, els_ios, legacy, grid=100, base=W_BASE, note=None, aliases=()):
    icon('weather', cat_name, tags, {'ios': one(els_ios)}, [22, 56],
         grid=grid, base=base, legacy=legacy, note=note, aliases=aliases)


# --- 太阳系 ---
weather('clear', ['晴', '晴天', 'clear', 'sunny', 'sun'],
        sun_els(50, 50, 13, n=8, rin=1.45, rout=2.15, sw=W_SUN),
        ['wx_clear', 'wxs_clear'], base=W_SUN, note='太阳：实心圆 + 8 根放射线')
weather('partly-cloudy', ['多云转晴', '晴间多云', 'partly cloudy', 'partly-cloudy', 'cloud-sun'],
        sun_els(72, 20, 10, n=8, rin=1.5, rout=2.4, sw=W_SUN)
        + w_cloud_els(2, shift=6.0, small=True),
        ['wx_partly', 'wxs_partly'],
        aliases=['weather.cloud-sun', 'cloud-sun', 'cloud_sun'],
        note='太阳 + 双鼓包云（云下落让出日轮，射线控制在 96% 以内不出画布）')
weather('cloudy', ['多云', '阴天', 'cloudy', 'cloud'],
        w_cloud_els(3), ['wx_cloud', 'wxs_cloud'], note='三鼓包 + 平底云（线框）')
weather('overcast', ['阴', '阴天', 'overcast'],
        w_cloud_els(3, mode='fill'), ['wx_overcast', 'wxs_overcast'],
        note='实心云（与 cloudy 区分：旧版两者同图，这里改为实心表达"密云"）')
weather('rain-light', ['小雨', 'light rain', 'drizzle'],
        drop_els(50, 34, 15), ['wx_rain_light', 'wxs_rain_light'], note='单滴大雨滴')
weather('rain', ['中雨', '雨', 'rain'],
        drop_els(38, 34, 12) + drop_els(62, 44, 10) + drop_els(50, 66, 12),
        ['wx_rain', 'wxs_rain'], note='三滴错落')
weather('rain-heavy', ['大雨', '暴雨', 'heavy rain'],
        drop_els(34, 26, 11) + drop_els(56, 30, 13) + drop_els(44, 58, 12) + drop_els(68, 62, 10),
        ['wx_rain_heavy', 'wxs_rain_heavy'], note='四滴（旧版有，保留）')
weather('cloud-rain', ['雨', '云雨', 'rain', 'cloud rain'],
        w_cloud_els(2) + [P(poly_d(arc_pts(32, 82, 6.5, 0, 360), close=True), FL()),
                          P(poly_d(arc_pts(50, 92, 6.5, 0, 360), close=True), FL()),
                          P(poly_d(arc_pts(68, 82, 6.5, 0, 360), close=True), FL())],
        ['wx_cloud_rain', 'wxs_cloud_rain'], note='云 + 3 滴（雨滴为水滴形：下圆上尖）')
weather('shower', ['阵雨', 'shower'],
        w_cloud_els(2) + [P(poly_d([(34, 86), (33.0, 92.5), (35.0, 92.5)], close=True), FL()),
                          P(poly_d([(50, 88), (49.0, 94.5), (51.0, 94.5)], close=True), FL()),
                          P(poly_d([(66, 86), (65.0, 92.5), (67.0, 92.5)], close=True), FL())],
        ['wx_shower', 'wxs_shower'],
        note='阵雨：短线雨丝（与 cloud-rain 的雨滴区分；旧版两者同图）')
weather('rain-sun', ['太阳雨', '阵雨转晴', 'rain sun', 'showers'],
        w_cloud_els(2, shift=3.0, small=True)
        + sun_els(76, 18, 9.0, n=4, rin=1.55, rout=2.4, sw=2.8)
        + [P(poly_d([(32, 80), (31.0, 86.5), (33.0, 86.5)], close=True), FL()),
           P(poly_d([(48, 84), (47.0, 90.5), (49.0, 90.5)], close=True), FL()),
           P(poly_d([(64, 80), (63.0, 86.5), (65.0, 86.5)], close=True), FL())],
        ['wx_rain_sun', 'wxs_rain_sun'], note='云 + 小太阳 + 雨丝（太阳右移下移，避开云轮廓）')
weather('thunder', ['雷', '雷阵雨', 'thunder', 'storm'],
        w_cloud_els(2, small=True) + bolt_els(50, 80, 26),
        ['wx_thunder', 'wxs_thunder'],
        note='云 + 闪电（已修正旧版：原闪电 y 到 126 被画布裁断，这里缩进云下到 93）')
weather('thunder-sun', ['雷阵雨转晴', 'thunder sun'],
        w_cloud_els(2, small=True) + bolt_els(50, 80, 26)
        + sun_els(20, 18, 8, n=4, rin=1.5, rout=2.4, sw=2.6),
        ['wx_thunder_sun', 'wxs_thunder_sun'],
        note='云 + 闪电 + 小太阳（小太阳内移，避免旧版射线出画布被裁）')
weather('snow', ['雪', '小雪', 'snow'],
        snow_els(50, 50, 30, sw=5.5), ['wx_snow', 'wxs_snow'],
        note='六轴雪花 + 小叉（旧版为花瓣状；小尺寸下六轴更清晰）')
weather('snow-heavy', ['大雪', 'snow heavy'],
        snow_els(42, 58, 26, sw=4.6) + snow_els(74, 26, 16, sw=3.6),
        ['wx_snow_heavy', 'wxs_snow_heavy'], note='大小两朵雪花')
weather('sleet', ['雨夹雪', 'sleet'],
        drop_els(26, 32, 8.5) + drop_els(22, 62, 8.5) + snow_els(68, 50, 20, sw=4.0),
        ['wx_sleet', 'wxs_sleet'], note='两滴雨 + 雪花')
weather('hail', ['冰雹', 'hail'],
        w_cloud_els(2, small=True) + [C(36, 78, 5.0, FL()), C(50, 84, 5.0, FL()),
                                      C(64, 78, 5.0, FL())],
        ['wx_hail', 'wxs_hail'],
        note='云 + 冰丸（旧版 hail 直接复用 thunder 图，这里改为真正的冰丸）')
weather('fog', ['雾', 'fog', 'mist'],
        w_cloud_els(2, small=True) + [LN(26, 78, 74, 78, ST(4.5)), LN(34, 90, 66, 90, ST(4.5))],
        ['wx_fog', 'wxs_fog'], note='云 + 两条雾带')
weather('haze', ['霾', '浮尘', '悬浮', 'haze', 'smog'],
        [C(50, 22, 16, FL()),
         LN(8, 50, 92, 50, ST(6)), LN(16, 62, 84, 62, ST(6)),
         LN(8, 74, 92, 74, ST(6)), LN(16, 86, 84, 86, ST(6))],
        ['wx_haze', 'wxs_haze'], base=6.0, note='被遮的太阳 + 密集横线（与雾区分）')
weather('wind', ['风', '大风', 'wind', 'windy'],
        [LN(16, 38, 60, 38, ST(4.6)), P(arc_d(66, 38, 14, -90, 170), ST(4.6)),
         LN(24, 64, 54, 64, ST(4.6)), P(arc_d(60, 64, 14, -90, 170), ST(4.6))],
        ['wx_wind', 'wxs_wind'], base=4.6, note='两段风向线 + 卷曲')
weather('moon', ['夜', '晴夜', '月', 'moon', 'night'],
        [P(crescent_d((44, 50), 28, (82, 38), 28), ST(6.0))],
        ['wx_moon', 'wxs_moon'], base=6.0,
        note='细月牙：外圆 r28 与偏移圆相减（厚度 ≈16 单位）；旧版因 outline() 把 u×SS 乘了两次，'
             '实际描边厚达 14 单位、月牙被填实，本套按设计意图还原')
weather('moon-star', ['晴夜', '星月', 'moon star'],
        [P(crescent_d((42, 52), 26, (77, 41), 26), ST(6.0)),
         P(poly_d([(70, 14), (72.6, 19.6), (78.4, 22.2), (72.6, 24.8), (70, 30.4),
                   (67.4, 24.8), (61.6, 22.2), (67.4, 19.6)], close=True), FL())],
        ['wx_moon_star', 'wxs_moon_star'], base=6.0, note='月牙 + 四角星')
weather('moon-cloud', ['多云夜', '夜间多云', 'moon cloud'],
        [P(crescent_d((74, 17), 16, (96, 8), 16), ST(6.0))]
        + w_cloud_els(2, shift=12.0, small=True),
        ['wx_moon_cloud', 'wxs_moon_cloud'],
        note='月牙 + 云（月牙上抬到云轮廓之上、云整体下移 12——旧版两者叠在一起糊成一团）')
weather('moon-rain', ['夜雨', '夜间小雨', 'moon rain'],
        [P(crescent_d((70, 24), 18, (95, 15), 18), ST(6.0))]
        + [P(poly_d(arc_pts(28, 50, 11, 0, 360), close=True), FL()),
           P(poly_d(arc_pts(46, 64, 9, 0, 360), close=True), FL()),
           P(poly_d(arc_pts(32, 80, 11, 0, 360), close=True), FL())],
        [], base=6.0, note='月牙 + 三滴夜雨（旧版缺失；与 rain 同画法：只有雨滴、不画云）')
weather('sunrise', ['日出', '太阳升起', 'sunrise'],
        [LN(10, 84, 90, 84, ST(6)),
         P(arc_d(50, 84, 26, 180, 360), ST(7)),
         LN(50, 46, 50, 34, ST(6)),
         LN(24, 52, 17, 45, ST(6)),
         LN(76, 52, 83, 45, ST(6))],
        [], base=7.0, note='地平线 + 半日 + 三道射线（旧版缺失，新增）')


# =========================================================================== #
# 二、开关 / 选项（control）—— ios + material 双风格
# =========================================================================== #
def toggle_els(style):
    if style == 'ios':
        off = [R(1.6, 6.4, 20.8, 11.2, rx=5.6, a=ST()), C(7.4, 12, 2.9, FL())]
        on = [R(1.6, 6.4, 20.8, 11.2, rx=5.6, a=FL()), C(16.6, 12, 4.1, cut=True, fill='currentColor')]
    else:
        off = [R(1.0, 6.0, 22.0, 12.0, rx=6.0, a=ST(2.1)), C(7.6, 12, 3.6, FL())]
        on = [R(1.0, 6.0, 22.0, 12.0, rx=6.0, a=FL()), C(16.6, 12, 4.6, cut=True, fill='currentColor')]
    return two(off, on)


def checkbox_els(style):
    if style == 'ios':
        off = [R(3.6, 3.6, 16.8, 16.8, rx=4.4, a=ST())]
        on = [R(3.6, 3.6, 16.8, 16.8, rx=4.4, a=FL()),
              P('M7.4,12.4 L10.8,15.8 L16.9,8.5', a=ST(1.9), cut=True)]
    else:
        off = [R(3.2, 3.2, 17.6, 17.6, rx=2.6, a=ST(2.1))]
        on = [R(3.2, 3.2, 17.6, 17.6, rx=2.6, a=FL()),
              P('M7.2,12.4 L10.7,15.9 L17.0,8.4', a=ST(2.4), cut=True)]
    return two(off, on)


def radio_els(style):
    if style == 'ios':
        off = [C(12, 12, 8.4, ST())]
        on = [C(12, 12, 8.4, ST()), C(12, 12, 4.4, FL())]
    else:
        off = [C(12, 12, 8.8, ST(2.1))]
        on = [C(12, 12, 8.8, ST(2.1)), C(12, 12, 5.1, FL())]
    return two(off, on)


CHEV_UP = [(7.41, 15.41), (12, 10.83), (16.59, 15.41), (18, 14), (12, 8), (6, 14)]


def chevron_els(direction, style):
    deg = {'up': 0, 'right': 90, 'down': 180, 'left': 270}[direction]
    if style == 'material':
        return [P(poly_d(rot_pts(CHEV_UP, deg), close=True), FL())]
    pts = rot_pts([(6.6, 15.0), (12, 9.6), (17.4, 15.0)], deg)
    return [P(poly_d(pts, close=False), a=ST())]


icon('control', 'toggle', ['开关', '拨动', 'toggle', 'switch', 'on off'],
     {'ios': toggle_els('ios'), 'material': toggle_els('material')}, [22, 24, 44, 56],
     aliases=['control.toggle-ios', 'control.toggle-material', 'ic_control_toggle_ios'],
     legacy=['sw_off', 'sw_on', 'sw_home_off', 'sw_home_on'],
     note='on 态圆钮用挖空表达（真透明 → 露出底图）；off 为常规线框 + 左侧实心钮')
icon('control', 'checkbox', ['复选框', '勾选', 'checkbox', 'check', 'tick'],
     {'ios': checkbox_els('ios'), 'material': checkbox_els('material')}, [22, 24, 44, 56],
     aliases=['control.checkbox-ios', 'control.checkbox-material'])
icon('control', 'radio', ['单选', '单选框', 'radio', 'option'],
     {'ios': radio_els('ios'), 'material': radio_els('material')}, [22, 24, 44, 56],
     aliases=['control.radio-ios', 'control.radio-material'])
for _d in ('up', 'down', 'left', 'right'):
    icon('control', 'chevron-%s' % _d, ['箭头', '折叠', 'chevron', _d],
         {'ios': one(chevron_els(_d, 'ios')), 'material': one(chevron_els(_d, 'material'))},
         [16, 22, 24, 44, 56], aliases=['control.chevron-%s-ios' % _d])
for _d in ('up', 'down', 'left', 'right'):
    icon('control', 'arrow-%s' % _d, ['箭头', '方向', 'arrow', _d],
         {'ios': one(arrow_els(_d, 'ios')), 'material': one(arrow_els(_d, 'material'))},
         [16, 22, 24, 44, 56])
icon('control', 'check', ['对勾', '确认', 'check', 'ok', 'done'],
     {'ios': one([P('M5.2,12.6 L9.7,17.2 L18.9,7.4', a=ST())]),
      'material': one([P('M5.0,12.5 L9.7,17.2 L19.0,7.4', a=ST(2.4))])}, [16, 22, 24, 44, 56])
icon('control', 'close', ['关闭', '删除', 'close', 'x', 'cancel'],
     {'ios': one([LN(6.0, 6.0, 18.0, 18.0, ST()), LN(18.0, 6.0, 6.0, 18.0, ST())]),
      'material': one([LN(5.6, 5.6, 18.4, 18.4, ST(2.4)), LN(18.4, 5.6, 5.6, 18.4, ST(2.4))])},
     [16, 22, 24, 44, 56])
icon('control', 'plus', ['加号', '新增', 'plus', 'add'],
     {'ios': one([LN(12, 5.2, 12, 18.8, ST()), LN(5.2, 12, 18.8, 12, ST())]),
      'material': one([LN(12, 5.0, 12, 19.0, ST(2.4)), LN(5.0, 12, 19.0, 12, ST(2.4))])},
     [16, 22, 24, 44, 56])
icon('control', 'minus', ['减号', '移除', 'minus', 'remove'],
     {'ios': one([LN(5.2, 12, 18.8, 12, ST())]),
      'material': one([LN(5.0, 12, 19.0, 12, ST(2.6))])}, [16, 22, 24, 44, 56])
icon('control', 'slider-knob', ['滑杆', '滑块', 'slider', 'knob', 'thumb'],
     {'ios': one([C(12, 12, 8.4, ST()), C(12, 12, 2.4, FL())]),
      'material': one([C(12, 12, 9.2, FL()), C(12, 12, 4.3, cut=True, fill='currentColor')])},
     [16, 22, 24, 32, 44, 56])
icon('control', 'ring-progress', ['进度环', '环形进度', 'ring', 'progress', 'loading'],
     {'ios': one([P(arc_d(12, 12, 8.6, -90, 190), ST()), C(12, 3.4, 1.7, FL())]),
      'material': one([P(arc_d(12, 12, 8.4, -90, 200), ST(2.4)), C(12, 3.6, 2.1, FL())])},
     [22, 24, 32, 44, 56])


# =========================================================================== #
# 三、通用系统（system）
# =========================================================================== #
def wifi_els(sw, radii, dot_r, cy=16.4, dot_y=19.6):
    els = [P(arc_d(12, cy, rr, 212, 328), ST(sw)) for rr in radii]
    els.append(C(12, dot_y, dot_r, FL()))
    return els


icon('system', 'wifi', ['无线', '无线网', 'wifi', 'wireless', 'network'],
     {'ios': one(wifi_els(1.75, (10.6, 7.2, 4.0), 1.7)),
      'material': one(wifi_els(2.6, (10.2, 6.9, 3.7), 2.4))},
     [16, 22, 24, 44, 56], legacy=['ico_wifi'],
     note='material 变体为加粗圆弧（Material Symbols 的 wifi 是填充扇形，本套用加粗近似）')
icon('system', 'wifi-off', ['断开网络', '无网络', 'wifi off', 'disconnect'],
     {'ios': one(wifi_els(1.75, (10.6, 7.2, 4.0), 1.7) + slash_band(3.6, 4.0, 20.4, 20.0)),
      'material': one(wifi_els(2.6, (10.2, 6.9, 3.7), 2.4) + slash_band(3.6, 4.0, 20.4, 20.0, 5.6))},
     [16, 22, 24, 44, 56], note='断开态：沿斜杠挖缝再压线（线框图标不能靠"盖住"表达）')
icon('system', 'bluetooth', ['蓝牙', 'bluetooth', 'bt'],
     {'ios': one([P('M6.6,6.4 L17.4,17.6 L12,22.4', a=ST()),
                  P('M12,1.6 L17.4,6.4 L6.6,17.6', a=ST())]),
      'material': one([P('M6.6,6.4 L17.4,17.6 L12,22.4', a=ST(2.3)),
                       P('M12,1.6 L17.4,6.4 L6.6,17.6', a=ST(2.3))])},
     [16, 22, 24, 44, 56], legacy=['ico_bt'])


def battery_els(style, level=1.0, charging=False, states=None):
    sw = 1.75 if style == 'ios' else 2.1
    body = [R(2.4, 7.4, 17.6, 11.0, rx=3.0, a=ST(sw)),
            R(20.6, 10.6, 1.6, 2.8, rx=0.8, a=FL())]
    if charging:
        body.extend(bolt_els(12, 12.9, 9.0))
    elif level > 0:
        body.append(R(4.4, 9.4, max(1.8, 13.4 * level), 7.0, rx=1.5, a=FL()))
    return body


for _lvl, _nm, _tg in ((0.0, '0', ['空电']), (0.25, '25', ['低电']), (0.5, '50', ['半电']),
                       (0.75, '75', ['较满']), (1.0, '100', ['满电'])):
    icon('system', 'battery-%s' % _nm, ['电池', '电量'] + _tg + ['battery', _nm],
         {'ios': one(battery_els('ios', _lvl)), 'material': one(battery_els('material', _lvl))},
         [16, 22, 24, 44, 56])
icon('system', 'battery-charging', ['充电', '充电中', 'battery charging', 'charging'],
     {'ios': one(battery_els('ios', charging=True)),
      'material': one(battery_els('material', charging=True))}, [16, 22, 24, 44, 56])

_BAR_H = (5.0, 9.0, 13.0, 17.0)
for _k in (1, 2, 3, 4):
    def _sig(style, k=_k):
        sw = 1.75 if style == 'ios' else 1.9
        els = []
        for i in range(4):
            y = 19.8 - _BAR_H[i]
            els.append(R(3.0 + i * 5.0, y, 3.4, _BAR_H[i], rx=1.1,
                         a=FL() if i < k else ST(sw)))
        return els
    icon('system', 'signal-%d' % _k, ['信号', '强度', 'signal', 'bars', '%d 格' % _k],
         {'ios': one(_sig('ios')), 'material': one(_sig('material'))}, [16, 22, 24, 44, 56],
         note='已连格=实心，未连格=线框（单色图标用"实/空"表达强度）')

BELL_DOME = arc_pts(12, 10.8, 5.4, 180, 360)


def bell_els(style):
    if style == 'ios':
        return [P(arc_d(12, 10.8, 5.4, 180, 360), ST()),
                LN(6.6, 10.8, 6.6, 17.4, ST()), LN(17.4, 10.8, 17.4, 17.4, ST()),
                LN(5.4, 17.4, 18.6, 17.4, ST()), C(12, 4.4, 1.0, FL()),
                P(arc_d(12, 17.8, 2.5, 38, 142), ST())]
    return [P(poly_d(BELL_DOME + [(17.4, 16.8), (6.6, 16.8)], close=True), FL()),
            R(5.2, 16.6, 13.6, 1.9, rx=0.95, a=FL()), C(12, 4.6, 1.5, FL()),
            P(poly_d(arc_pts(12, 18.0, 2.7, 25, 155) + [(12, 18.0)], close=True), FL())]


icon('system', 'bell', ['通知', '铃铛', '提醒', 'bell', 'notification', 'alert'],
     {'ios': one(bell_els('ios')), 'material': one(bell_els('material'))},
     [16, 22, 24, 44, 56], legacy=['ico_bell'])
icon('system', 'bell-off', ['免打扰', '静音', '关闭通知', 'bell off', 'mute', 'dnd'],
     {'ios': one(bell_els('ios') + slash_band(3.4, 4.2, 20.6, 20.2)),
      'material': one(bell_els('material') + slash_band(3.4, 4.2, 20.6, 20.2, 5.2))},
     [16, 22, 24, 44, 56])


def lock_els(style, opened=False):
    sw = 1.75 if style == 'ios' else 2.2
    els = []
    if opened:
        els.append(P(arc_d(13.2, 9.8, 4.4, 180, 350), ST(sw)))
        els.append(LN(8.8, 9.8, 8.8, 10.8, ST(sw)))
    else:
        els.append(P(arc_d(12, 10.8, 4.2, 180, 360), ST(sw)))
    if style == 'ios':
        els.append(R(4.8, 10.6, 14.4, 10.2, rx=2.8, a=ST()))
        els.append(C(12, 15.6, 1.3, FL()))
    else:
        els.append(R(4.6, 10.4, 14.8, 10.4, rx=2.6, a=FL()))
        els.append(C(12, 14.8, 1.5, cut=True, fill='currentColor'))
        els.append(R(11.2, 15.6, 1.6, 3.2, rx=0.8, cut=True, fill='currentColor'))
    return els


icon('system', 'lock', ['锁', '已锁定', 'lock', 'locked', 'secure'],
     {'ios': one(lock_els('ios')), 'material': one(lock_els('material'))},
     [16, 22, 24, 44, 56], legacy=['ico_lock'])
icon('system', 'unlock', ['解锁', '已解锁', 'unlock', 'unlocked', 'open'],
     {'ios': one(lock_els('ios', True)), 'material': one(lock_els('material', True))},
     [16, 22, 24, 44, 56])
icon('system', 'search', ['搜索', '查找', 'search', 'find', 'magnifier'],
     {'ios': one([C(10.7, 10.7, 6.5, ST()), LN(15.4, 15.4, 20.4, 20.4, ST())]),
      'material': one([C(10.7, 10.7, 6.6, ST(2.3)), LN(15.5, 15.5, 20.4, 20.4, ST(2.3))])},
     [16, 22, 24, 44, 56])
icon('system', 'settings', ['设置', '齿轮', 'settings', 'gear', 'config'],
     {'ios': one(gear_els(12, 12, solid=False)), 'material': one(gear_els(12, 12, solid=True))},
     [16, 22, 24, 44, 56], note='material 为实心齿盘 + 挖孔（负空间）')
icon('system', 'home', ['主页', '首页', '家', 'home', 'house'],
     {'ios': one([P('M3.6,10.6 L12,3.6 L20.4,10.6', a=ST()),
                  P('M5.9,9.4 L5.9,20.2 L18.1,20.2 L18.1,9.4', a=ST()),
                  P('M10.2,20.2 L10.2,14.6 L13.8,14.6 L13.8,20.2', a=ST())]),
      'material': one([P(poly_d([(12, 3.0), (21.3, 11.4), (19.1, 11.4), (19.1, 20.6),
                                 (4.9, 20.6), (4.9, 11.4), (2.7, 11.4)], close=True), FL()),
                       R(10.1, 14.3, 3.8, 6.3, rx=0.7, cut=True, fill='currentColor')])},
     [16, 22, 24, 44, 56], legacy=['ico_house'])
icon('system', 'back', ['返回', '后退', 'back', 'return', 'arrow left'],
     {'ios': one([LN(19.6, 12, 5.6, 12, ST()), P('M11.2,5.6 L4.8,12 L11.2,18.4', a=ST())]),
      'material': one([P(poly_d([(19.4, 10.4), (11.0, 10.4), (15.4, 6.0), (13.6, 4.2),
                                 (6.0, 11.8), (13.6, 19.4), (15.4, 17.6), (11.0, 13.2),
                                 (19.4, 13.2)], close=True), FL())])},
     [16, 22, 24, 44, 56], legacy=['ico_back'])
icon('system', 'more', ['更多', '三点', 'more', 'menu', 'ellipsis'],
     {'ios': one([C(5.3, 12, 1.9, FL()), C(12, 12, 1.9, FL()), C(18.7, 12, 1.9, FL())]),
      'material': one([C(5.3, 12, 2.2, FL()), C(12, 12, 2.2, FL()), C(18.7, 12, 2.2, FL())])},
     [16, 22, 24, 44, 56], legacy=['ico_more'])


def star_els(style, filled):
    pts = star_pts(12, 12.4, 9.6, 3.9)
    if filled:
        return [P(poly_d(pts, close=True), FL())]
    return [P(poly_d(pts, close=True), a=ST(2.2 if style == 'material' else 1.75))]


def heart_els(style, filled):
    pts = heart_pts(12, 12.4, 19.4)
    if filled:
        return [P(poly_d(pts, close=True), FL())]
    return [P(poly_d(pts, close=True), a=ST(2.2 if style == 'material' else 1.75))]


for _st, _fn, _tg in (('ios', star_els, ['星标', 'star']), ('material', star_els, [])):
    pass
icon('system', 'star', ['星标', '收藏', 'star', 'favorite', 'rate'],
     {'ios': two(star_els('ios', False), star_els('ios', True)),
      'material': two(star_els('material', False), star_els('material', True))},
     [16, 22, 24, 44, 56], note='on 态 = 实心（收藏/选中）')
icon('system', 'heart', ['喜欢', '心', 'heart', 'like', 'love'],
     {'ios': two(heart_els('ios', False), heart_els('ios', True)),
      'material': two(heart_els('material', False), heart_els('material', True))},
     [16, 22, 24, 44, 56], note='on 态 = 实心')
icon('system', 'power', ['电源', '开机', '关机', 'power', 'on off'],
     {'ios': one([LN(12, 3.2, 12, 12.6, ST()), P(arc_d(12, 12.4, 8.6, -52, 232), ST())]),
      'material': one([LN(12, 3.0, 12, 12.6, ST(2.4)), P(arc_d(12, 12.4, 8.8, -52, 232), ST(2.4))])},
     [16, 22, 24, 44, 56])
icon('system', 'trash', ['删除', '垃圾桶', 'trash', 'delete', 'remove'],
     {'ios': one([LN(3.6, 6.6, 20.4, 6.6, ST()),
                  P('M8.6,6.6 L9.0,4.4 L15.0,4.4 L15.4,6.6', a=ST()),
                  P('M5.8,6.6 L6.8,19.8 L17.2,19.8 L18.2,6.6', a=ST()),
                  LN(10.0, 10.0, 10.0, 16.6, ST()), LN(14.0, 10.0, 14.0, 16.6, ST())]),
      'material': one([P(poly_d([(8.4, 6.4), (8.8, 4.2), (15.2, 4.2), (15.6, 6.4)], close=True), FL()),
                       P(poly_d([(3.4, 6.4), (20.6, 6.4), (20.6, 8.0), (3.4, 8.0)], close=True), FL()),
                       P(poly_d([(6.0, 8.8), (18.0, 8.8), (17.0, 20.4), (7.0, 20.4)], close=True), FL()),
                       R(10.6, 10.8, 1.6, 7.2, rx=0.8, cut=True, fill='currentColor'),
                       R(13.8, 10.8, 1.6, 7.2, rx=0.8, cut=True, fill='currentColor')])},
     [16, 22, 24, 44, 56])
icon('system', 'edit', ['编辑', '铅笔', 'edit', 'pencil', 'write'],
     {'ios': one([P(poly_d([(4.0, 20.0), (5.4, 16.4), (15.0, 6.8), (17.2, 9.0),
                            (7.6, 18.6)], close=True), a=ST()),
                  LN(6.0, 15.6, 8.4, 18.0, ST())]),
      'material': one([P(poly_d([(3.6, 20.4), (5.1, 16.2), (15.0, 6.3), (17.7, 9.0),
                                 (7.8, 18.9)], close=True), FL()),
                       LN(6.0, 15.4, 8.4, 17.8, ST(1.7), cut=True)])},
     [16, 22, 24, 44, 56])
icon('system', 'share', ['分享', '共享', 'share', 'send'],
     {'ios': one([C(18, 5.6, 2.2, FL()), C(6, 12, 2.2, FL()), C(18, 18.4, 2.2, FL()),
                  LN(7.9, 10.9, 16.1, 6.7, ST()), LN(7.9, 13.1, 16.1, 17.3, ST())]),
      'material': one([C(18, 5.6, 2.6, FL()), C(6, 12, 2.6, FL()), C(18, 18.4, 2.6, FL()),
                       LN(8.2, 10.8, 15.8, 6.9, ST(2.4)), LN(8.2, 13.2, 15.8, 17.1, ST(2.4))])},
     [16, 22, 24, 44, 56])
icon('system', 'cloud', ['云', '云端', 'cloud', 'online'],
     {'ios': one([P(cloud_d([(7.2, 15.0, 3.4), (12.0, 12.8, 5.6), (16.6, 15.0, 3.4)], 18.4),
                      a=ST())]),
      'material': one([P(cloud_d([(7.4, 15.2, 3.6), (12.0, 12.6, 5.8), (16.6, 15.2, 3.6)], 18.8),
                         FL())])},
     [16, 22, 24, 44, 56], legacy=['ico_cloud'])


# =========================================================================== #
# 四、智能家居设备（device）
# =========================================================================== #
def bulb_els(style, on_state=False):
    rays = []
    if on_state:
        for a in (-140, -90, -40):
            ar = math.radians(a)
            rays.append(LN(12 + math.cos(ar) * 7.2, 9.2 + math.sin(ar) * 7.2,
                           12 + math.cos(ar) * 9.4, 9.2 + math.sin(ar) * 9.4, ST(1.6)))
    if style == 'ios':
        if on_state:
            return [C(12, 9.4, 5.4, FL()),
                    P(arc_d(12, 10.6, 2.7, 195, 345), ST(1.7), cut=True),
                    LN(9.8, 14.2, 9.8, 16.4, ST()), LN(14.2, 14.2, 14.2, 16.4, ST()),
                    LN(9.8, 16.4, 14.2, 16.4, ST())] + rays
        return [C(12, 9.6, 5.7, ST()),
                LN(9.6, 14.4, 9.6, 16.4, ST()), LN(14.4, 14.4, 14.4, 16.4, ST()),
                LN(9.6, 16.4, 14.4, 16.4, ST()),
                P(arc_d(12, 10.8, 2.8, 195, 345), ST(1.5))]
    els = [C(12, 9.4, 5.6, FL()),
           P(arc_d(12, 10.8, 2.8, 200, 340), ST(1.7), cut=True),
           P(poly_d([(9.6, 14.0), (14.4, 14.0), (14.4, 16.6), (9.6, 16.6)], close=True), FL()),
           R(9.4, 16.4, 5.2, 1.6, rx=0.8, a=FL())]
    return els + rays


icon('device', 'light', ['灯', '灯泡', '照明', 'light', 'bulb', 'lamp'],
     {'ios': two(bulb_els('ios', False), bulb_els('ios', True)),
      'material': two(bulb_els('material', False), bulb_els('material', True))},
     [16, 22, 24, 32, 44, 56], aliases=['device.light-bulb'], legacy=['ic_light_main'],
     note='on 态：灯丝挖空 + 三道外射线（视觉上"亮"）')


def strip_els(style, on_state=False):
    sw = 1.75 if style == 'ios' else 2.1
    body = R(2.4, 9.4, 19.2, 5.0, rx=2.4, a=FL() if on_state else ST(sw))
    dots = [C(6.4, 11.9, 1.0, cut=True, fill='currentColor') if on_state else C(6.4, 11.9, 0.95, FL()),
            C(10.4, 11.9, 1.0, cut=True, fill='currentColor') if on_state else C(10.4, 11.9, 0.95, FL()),
            C(14.4, 11.9, 1.0, cut=True, fill='currentColor') if on_state else C(14.4, 11.9, 0.95, FL()),
            C(18.4, 11.9, 1.0, cut=True, fill='currentColor') if on_state else C(18.4, 11.9, 0.95, FL())]
    return [body] + dots


icon('device', 'light-strip', ['灯带', '氛围灯', '灯条', 'light strip', 'led'],
     {'ios': two(strip_els('ios', False), strip_els('ios', True)),
      'material': two(strip_els('material', False), strip_els('material', True))},
     [16, 22, 24, 32, 44, 56], legacy=['ic_strip_arc'])
icon('device', 'ac', ['空调', '制冷', 'air conditioner', 'ac', 'cool'],
     {'ios': one(snow_els(12, 12, 8.8, sw=1.9)),
      'material': one(snow_els(12, 12, 8.4, sw=2.5))}, [16, 22, 24, 32, 44, 56],
     legacy=['ic_ac'], note='雪花即"制冷"语义（旧版 ic_ac 亦为雪花）')
icon('device', 'fan', ['风扇', '新风', '换气', 'fan', 'ventilation'],
     {'ios': one([P(poly_d(ellipse_pts(12 + 4.0 * math.cos(math.radians(-90 + i * 120)),
                                       12 + 4.0 * math.sin(math.radians(-90 + i * 120)),
                                       4.6, 2.5, rot_deg=-90 + i * 120), close=True), a=ST())
                  for i in range(3)] + [C(12, 12, 1.7, FL())]),
      'material': one([P(poly_d(ellipse_pts(12 + 4.1 * math.cos(math.radians(-90 + i * 120)),
                                            12 + 4.1 * math.sin(math.radians(-90 + i * 120)),
                                            4.8, 2.7, rot_deg=-90 + i * 120), close=True), FL())
                       for i in range(3)] + [C(12, 12, 1.9, cut=True, fill='currentColor')])},
     [16, 22, 24, 32, 44, 56])
_DRAPE_L = drape_pts(5.0, 5.2, 19.2, 0.55)
_DRAPE_L2 = drape_pts(10.2, 5.2, 19.2, 0.55, math.pi)
_DRAPE_R = drape_pts(19.0, 5.2, 19.2, 0.55)
_DRAPE_R2 = drape_pts(13.8, 5.2, 19.2, 0.55, math.pi)
icon('device', 'curtain', ['窗帘', '电动窗帘', 'curtain', 'blind'],
     {'ios': one([LN(2.8, 5.0, 21.2, 5.0, ST())] +
                 [P(poly_d(p, close=False), a=ST()) for p in (_DRAPE_L, _DRAPE_L2, _DRAPE_R, _DRAPE_R2)]),
      'material': one([LN(2.4, 4.8, 21.6, 4.8, ST(2.2)),
                       P(poly_d(list(_DRAPE_L) + list(reversed(_DRAPE_L2)), close=True), FL()),
                       P(poly_d(list(_DRAPE_R) + list(reversed(_DRAPE_R2)), close=True), FL())])},
     [16, 22, 24, 32, 44, 56])
icon('device', 'tv', ['电视', '电视机', 'tv', 'television'],
     {'ios': one([R(2.6, 5.0, 18.8, 12.4, rx=2.2, a=ST()),
                  LN(8.6, 21.0, 15.4, 21.0, ST()), LN(12, 17.4, 12, 21.0, ST())]),
      'material': one([P(poly_d([(4.6, 4.8), (19.4, 4.8), (21.0, 6.4), (21.0, 16.2),
                                 (19.4, 17.8), (4.6, 17.8), (3.0, 16.2), (3.0, 6.4)], close=True), FL()),
                       LN(8.6, 21.0, 15.4, 21.0, ST(2.2)), LN(12, 17.8, 12, 21.0, ST(2.2))])},
     [16, 22, 24, 32, 44, 56])
icon('device', 'camera', ['摄像头', '相机', '监控', 'camera', 'webcam'],
     {'ios': one([P('M3.2,8.6 L3.2,18.6 L20.8,18.6 L20.8,8.6 L15.6,8.6 L14.0,6.0 '
                    'L10.0,6.0 L8.4,8.6 Z', a=ST(), cut=False),
                  C(12, 13.4, 3.4, ST())]),
      'material': one([P(poly_d([(3.0, 8.4), (8.6, 8.4), (10.2, 5.8), (13.8, 5.8), (15.4, 8.4),
                                 (21.0, 8.4), (21.0, 18.8), (3.0, 18.8)], close=True), FL()),
                       C(12, 13.4, 3.6, cut=True, fill='currentColor'),
                       C(12, 13.4, 1.7, FL())])}, [16, 22, 24, 32, 44, 56])
icon('device', 'plug', ['插座', '插头', '通电', 'plug', 'socket', 'power point'],
     {'ios': one([R(8.2, 3.2, 2.2, 4.6, rx=1.1, a=FL()), R(13.6, 3.2, 2.2, 4.6, rx=1.1, a=FL()),
                  R(6.2, 7.8, 11.6, 8.2, rx=2.2, a=ST()),
                  P('M12,16.0 C12,18.0 10.4,18.2 10.4,20.6', a=ST())]),
      'material': one([R(8.0, 3.0, 2.6, 5.0, rx=1.3, a=FL()), R(13.4, 3.0, 2.6, 5.0, rx=1.3, a=FL()),
                       R(6.0, 7.6, 12.0, 8.6, rx=2.4, a=FL()),
                       P('M12,16.2 C12,18.2 10.4,18.4 10.4,20.6', a=ST(2.1))])},
     [16, 22, 24, 32, 44, 56])
icon('device', 'speaker', ['音箱', '喇叭', 'speaker', 'audio'],
     {'ios': one([R(5.6, 3.2, 12.8, 17.6, rx=2.6, a=ST()), C(12, 7.8, 2.5, ST()),
                  C(12, 15.0, 3.7, ST())]),
      'material': one([R(5.4, 3.0, 13.2, 18.0, rx=2.8, a=FL()),
                       C(12, 8.0, 2.7, cut=True, fill='currentColor'),
                       C(12, 15.2, 3.9, cut=True, fill='currentColor')])},
     [16, 22, 24, 32, 44, 56])
icon('device', 'thermostat', ['温控', '温度', '地暖', 'thermostat', 'temperature', 'heating'],
     {'ios': one([R(10.4, 4.2, 3.2, 13.6, rx=1.6, a=ST()), C(12, 17.6, 3.6, ST()),
                  R(11.4, 7.6, 1.2, 10.4, rx=0.6, a=FL()), C(12, 17.6, 1.9, FL())]),
      'material': one([R(10.2, 4.0, 3.6, 13.4, rx=1.8, a=FL()),
                       C(12, 17.6, 3.9, FL()),
                       R(11.4, 7.0, 1.2, 9.4, rx=0.6, cut=True, fill='currentColor')])},
     [16, 22, 24, 32, 44, 56], aliases=['device.temp'])
icon('device', 'door', ['门', '门锁', 'door', 'entrance'],
     {'ios': one([R(5.6, 2.8, 12.8, 18.4, rx=1.4, a=ST()), C(15.2, 12, 1.2, FL())]),
      'material': one([R(5.4, 2.6, 13.2, 18.8, rx=1.6, a=FL()),
                       C(15.0, 12, 1.5, cut=True, fill='currentColor')])},
     [16, 22, 24, 32, 44, 56])
icon('device', 'window', ['窗户', '窗', 'window'],
     {'ios': one([R(3.4, 3.4, 17.2, 17.2, rx=1.6, a=ST()), LN(12, 3.4, 12, 20.6, ST()),
                  LN(3.4, 12, 20.6, 12, ST())]),
      'material': one([R(3.2, 3.2, 17.6, 17.6, rx=1.8, a=FL()),
                       LN(12, 3.2, 12, 20.8, ST(2.0), cut=True),
                       LN(3.2, 12, 20.8, 12, ST(2.0), cut=True)])},
     [16, 22, 24, 32, 44, 56])
icon('device', 'sensor', ['传感器', '人体感应', 'sensor', 'motion', 'pir'],
     {'ios': one([R(8.6, 13.0, 6.8, 7.6, rx=1.8, a=ST())] +
                 [P(arc_d(12, 13.0, rr, 205, 335), ST()) for rr in (4.6, 7.2, 9.4)]),
      'material': one([R(8.4, 12.8, 7.2, 8.0, rx=2.0, a=FL())] +
                      [P(arc_d(12, 13.0, rr, 205, 335), ST(2.4)) for rr in (4.8, 7.4, 9.6)])},
     [16, 22, 24, 32, 44, 56])
icon('device', 'water-heater', ['热水器', '热水', 'water heater', 'boiler'],
     {'ios': one([R(8.0, 5.4, 8.0, 12.6, rx=3.6, a=ST()), LN(12, 5.4, 12, 2.4, ST()),
                  LN(9.4, 2.4, 14.6, 2.4, ST())] + drop_els(12, 12.4, 1.7)),
      'material': one([R(7.8, 5.2, 8.4, 13.4, rx=3.8, a=FL()),
                       LN(12, 5.2, 12, 2.4, ST(2.1)), LN(9.4, 2.4, 14.6, 2.4, ST(2.1)),
                       C(12, 13.6, 2.0, cut=True, fill='currentColor'),
                       P(poly_d([(12, 9.4), (10.6, 12.4), (13.4, 12.4)], close=True),
                         cut=True, fill='currentColor')])},
     [16, 22, 24, 32, 44, 56])
icon('device', 'air-purifier', ['净化器', '空气净化', 'air purifier', 'purifier', 'hepa'],
     {'ios': one([R(5.8, 3.6, 12.4, 16.8, rx=2.6, a=ST()), C(12, 9.0, 2.9, ST())] +
                 [LN(8.6, y, 15.4, y, ST()) for y in (14.8, 16.6, 18.4)]),
      'material': one([R(5.6, 3.4, 12.8, 17.2, rx=2.8, a=FL()),
                       C(12, 9.2, 3.1, cut=True, fill='currentColor'),
                       C(12, 9.2, 1.4, FL())] +
                      [R(8.4, y, 7.2, 1.3, rx=0.65, cut=True, fill='currentColor')
                       for y in (14.6, 16.5, 18.4)])},
     [16, 22, 24, 32, 44, 56])
icon('device', 'vacuum', ['扫地机', '扫地机器人', 'vacuum', 'robot', 'cleaner'],
     {'ios': one([C(12, 12, 8.8, ST()), P(arc_d(12, 12, 8.8, -150, -30), ST(2.2)),
                  C(12, 12, 2.0, FL())]),
      'material': one([C(12, 12, 9.0, FL()), C(12, 12, 6.9, cut=True, fill='currentColor'),
                       C(12, 12, 2.2, FL()),
                       P(arc_d(12, 12, 9.0, -150, -30), ST(3.0), cut=True)])},
     [16, 22, 24, 32, 44, 56])


# =========================================================================== #
# 五、两轮车仪表（vehicle，自绘）—— Tabler 风格不匹配，保留自绘
# =========================================================================== #
def thick_arrow_els(direction, state):
    """转向箭头：粗杆 + 三角头（与 projects/.../01-ev-scooter-dashboard 的 ic_left/right 同构）。"""
    deg = {'left': 180, 'right': 0}[direction]

    def T(pts):
        # 先在原点坐标系里旋转，再平移到 24 网格中心（rot_pts 默认绕 (12,12)，这里传 0）
        return [(x + 12.0, y + 12.0) for x, y in rot_pts(pts, deg, 0.0, 0.0)]

    body = T([(-9.4, -2.4), (2.6, -2.4), (2.6, 2.4), (-9.4, 2.4)])
    head = T([(2.6, -5.0), (11.0, 0.0), (2.6, 5.0)])
    a = FL() if state == 'on' else ST()
    return [P(poly_d(body, close=True), a), P(poly_d(head, close=True), a)]


def bulb_els(state, beams=0):
    """大灯：灯泡（圆头 + 灯座 + 灯丝）+ 可选光束（on 态：灯丝挖空 + 光束）。"""
    if state == 'on':
        els = [C(12, 7.8, 4.5, FL()), P(arc_d(12, 8.9, 2.5, 200, 340), ST(1.6), cut=True)]
    else:
        els = [C(12, 7.8, 4.5, ST()), P(arc_d(12, 8.9, 2.5, 200, 340), ST(1.5))]
    els += [LN(9.5, 11.9, 9.5, 13.6, ST()), LN(14.5, 11.9, 14.5, 13.6, ST()),
            LN(9.5, 13.6, 14.5, 13.6, ST())]
    for i in range(beams):
        y = 16.2 + i * 1.9
        x0 = 8.4 + i * 0.8
        els.append(LN(x0, y, 24.0 - x0, y, ST(1.6)))
    return els


def cruise_els(state):
    """定速巡航：闪电（同构 Feather zap，缩到 15 单位）。"""
    k = 15.0 / 20.0
    pts = [(13, 2), (3, 14), (12, 14), (11, 22), (21, 10), (12, 10)]
    pts = [(12.0 + (x - 12) * k, 12.4 + (y - 12) * k) for x, y in pts]
    return [P(poly_d(pts, close=True), FL() if state == 'on' else ST())]


_TURN_LEGACY = ('ic_left_main', 'ic_left_sport', 'ic_left_nav', 'ic_left_alert')
_TURN_LEGACY_R = ('ic_right_main', 'ic_right_sport', 'ic_right_nav', 'ic_right_alert')

icon('vehicle', 'turn-left', ['左转', '转向灯', '方向', 'turn left', 'indicator'],
     {'ios': two(thick_arrow_els('left', 'off'), thick_arrow_els('left', 'on'))},
     [22, 24, 32, 44, 56], legacy=list(_TURN_LEGACY),
     note='两轮车仪表转向箭头（自绘：Tabler 的箭头是细线，仪表要粗实）')
icon('vehicle', 'turn-right', ['右转', '转向灯', '方向', 'turn right', 'indicator'],
     {'ios': two(thick_arrow_els('right', 'off'), thick_arrow_els('right', 'on'))},
     [22, 24, 32, 44, 56], legacy=list(_TURN_LEGACY_R),
     note='同 turn-left，方向相反')
icon('vehicle', 'headlight', ['大灯', '近光灯', '车灯', 'headlight', 'low beam'],
     {'ios': two(bulb_els('off', 0), bulb_els('on', 2))},
     [22, 24, 32, 44, 56],
     legacy=['ic_light_main', 'ic_light_sport', 'ic_light_nav', 'ic_light_alert'],
     note='大灯（近光）：off 白描边 / on 实心 + 两道近光光束（对应旧版 ic_light_*_on 的琥珀色，用 --color 烘焙）')
icon('vehicle', 'high-beam', ['远光灯', '远光', 'high beam', 'full beam'],
     {'ios': two(bulb_els('off', 0), bulb_els('on', 4))},
     [22, 24, 32, 44, 56], note='远光：on 态光束多两道（与近光区分）')
icon('vehicle', 'cruise', ['定速巡航', '巡航', 'cruise', '定速'],
     {'ios': two(cruise_els('off'), cruise_els('on'))},
     [22, 24, 32, 44, 56],
     legacy=['ic_cruise_main', 'ic_cruise_sport', 'ic_cruise_nav', 'ic_cruise_alert'],
     note='定速巡航 = 闪电（旧版 ic_cruise_* 同构）')


# =========================================================================== #
# 输出：svg/（主线自绘）+ svg_retired/（留档）
#   目录分工：天气/开关选项/通用系统/智能家居 已由 vendor(tabler) 承担，
#   它们的几何仍写在本文件里（可复现），但只落到 svg_retired/，不进入 catalog。
#   catalog.json 由 scripts/gen_catalog.py 统一生成（vendor map + 本文件的自绘表）。
# =========================================================================== #
ACTIVE_CATEGORIES = ('vehicle',)


def svg_rel(cat, name, style=None, state=None, retired=False):
    return '%s/%s/%s%s%s.svg' % ('svg_retired' if retired else 'svg', cat, name,
                                 ('_' + style) if style else '',
                                 ('_' + state) if state else '')


def build_svg(entry, els):
    grid = entry['grid']
    body = ('\n  ' + '\n  '.join(els)) if els else ''
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %g %g" '
            'data-base-stroke="%s">%s\n</svg>\n'
            % (grid, grid, ('%g' % entry['base']), body))


def expand(entry):
    """(图标, 风格, 状态) → 渲染任务；state 为 '' 表示单态。"""
    multi = len(entry['styles']) > 1
    out = []
    for style, states in sorted(entry['styles'].items()):
        suffix = style if (multi or style == 'material') else None
        for state, els in states.items():
            out.append(dict(style=style, style_suffix=suffix, state=state, els=els,
                            svg=svg_rel(entry['category'], entry['name'], suffix,
                                        state or None, entry['category'] not in ACTIVE_CATEGORIES)))
    return out


def active_icons():
    """主线自绘图标（vehicle 等）——gen_catalog.py 直接调用这里，避免两份清单。"""
    return [e for e in ICONS if e['category'] in ACTIVE_CATEGORIES]


def main(argv):
    write = '--check' not in argv
    n_active = n_retired = 0
    for e in ICONS:
        for j in expand(e):
            if write:
                p = os.path.join(ROOT, j['svg'].replace('/', os.sep))
                os.makedirs(os.path.dirname(p), exist_ok=True)
                with open(p, 'w', encoding='utf-8') as f:
                    f.write(build_svg(e, j['els']))
            if j['svg'].startswith('svg_retired/'):
                n_retired += 1
            else:
                n_active += 1
    print('selfdrawn icons=%d  svg(active)=%d  svg(retired 留档)=%d  %s'
          % (len(ICONS), n_active, n_retired, 'written' if write else 'check-only'))
    print('catalog.json 由 scripts/gen_catalog.py 生成')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
