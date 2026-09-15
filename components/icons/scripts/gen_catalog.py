# -*- coding: utf-8 -*-
"""gen_catalog.py —— 生成 `catalog.json`（**唯一写入者**，禁止手写维护）

两个来源合并：
  1) **vendor/tabler/map.json** —— 收录的 Tabler 图标（自绘替代方案），
     带 outline / filled 两态与 7 条 compose（多 glyph 叠放）组合；
  2) **scripts/author_svg.py 的自绘表**（`active_icons()`）—— 只保留两轮车仪表
     （转向箭头/大灯/远光/定速巡航），Tabler 风格不匹配的那套。

产出结构（每个图标一条）：
    name / category / icon / source / license / styles / states / tags（中英）
    defaultColor / sizes / variants{风格:{kind, svg{状态:路径} | parts{状态:[...]},
                                   states[], files{状态:文件名}}} / note
另含 naming / palette / categories / legacyMap（旧工程名 → 新产物名）。

用法：
    python scripts/gen_catalog.py            # 写 catalog.json
    python scripts/gen_catalog.py --check    # 只校验（不写盘）
"""

import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import gen_icons           # noqa: E402  （out_name 命名规则的唯一实现）
import author_svg          # noqa: E402  （自绘图标表）

VERSION = '0.2.0'
VENDOR_DIR = os.path.join(ROOT, 'vendor', 'tabler')
VENDOR_SIZES = [16, 20, 22, 24, 32, 44, 56]
SELF_SIZES = [22, 24, 32, 44, 56]

CATEGORIES = {
    'weather': '天气',
    'control': '开关/选项',
    'system': '通用系统',
    'device': '智能家居设备',
    'vehicle': '两轮车仪表',
}

# 检索用补充关键词（中文同义词为主；英文关键词由 name/tabler 名自动派生）
EXTRA_TAGS = {
    'wifi': ['无线', '无线网', '联网'], 'wifi-off': ['断网', '无网络', '离线'],
    'bluetooth': ['蓝牙', '配对'], 'battery': ['电量', '电池'], 'signal': ['信号', '格数'],
    'lock': ['锁', '已锁', '加密'], 'lock-open': ['开锁', '解锁'],
    'bell': ['通知', '提醒', '消息'], 'bell-off': ['静音', '免打扰', '消息免打扰'],
    'volume': ['音量', '声音'], 'volume-off': ['静音', '无声'],
    'search': ['搜索', '查找'], 'settings': ['设置', '齿轮', '配置'],
    'home': ['主页', '首页', '家'], 'more': ['更多', '三点'], 'more-vertical': ['更多', '竖三点'],
    'star': ['星标', '收藏', '评分'], 'heart': ['喜欢', '点赞', '收藏'],
    'power': ['电源', '开机', '关机'], 'trash': ['删除', '垃圾桶'],
    'pencil': ['编辑', '铅笔', '改名'], 'share': ['分享', '转发'], 'refresh': ['刷新', '同步'],
    'play': ['播放', '开始'], 'pause': ['暂停'], 'microphone': ['麦克风', '语音', '录音'],
    'camera': ['相机', '拍照'], 'photo': ['图片', '照片'], 'video': ['视频', '录像'],
    'user': ['用户', '个人', '我的'], 'users': ['多用户', '成员'],
    'mail': ['邮件', '邮箱'], 'calendar': ['日历', '日期'], 'clock': ['时钟', '时间'],
    'alarm': ['闹钟', '提醒'], 'warning': ['警告', '告警'], 'info': ['信息', '说明'],
    'eye': ['显示', '可见', '预览'], 'eye-off': ['隐藏', '不可见'],
    'download': ['下载'], 'upload': ['上传'], 'filter': ['筛选', '过滤'],
    'menu': ['菜单'], 'grid': ['网格', '宫格'], 'list': ['列表'],
    'map-pin': ['定位', '位置', '地点'], 'navigation': ['导航', '指路'],
    'compass': ['指南针', '方向'], 'gauge': ['仪表', '速度', '时速'],
    'shield': ['防护', '安防'], 'shield-check': ['安防开启', '已布防'],
    'bolt': ['闪电', '快充', '高压'], 'flame': ['火焰', '燃气', '点火'],
    'phone': ['电话', '拨打'], 'router': ['路由', '网关'], 'access-point': ['热点', 'AP'],
    'fingerprint': ['指纹', '生物识别'], 'device-mobile': ['手机', '移动端'],
    'speaker': ['扬声器', '外放'], 'music': ['音乐', '歌曲'],
    'checkbox': ['复选框', '勾选框'], 'square': ['方框', '未选'],
    'square-check': ['已勾选'], 'circle': ['圆', '未选'], 'circle-check': ['圆已选'],
    'circle-dot': ['单选', '圆点'], 'toggle-left': ['开关-关', '关闭'],
    'toggle-right': ['开关-开', '打开'], 'switch-2': ['拨动开关'], 'switch-3': ['拨动开关'],
    'selector': ['选择器', '下拉'], 'sliders': ['滑块', '调节'], 'progress': ['进度'],
    'loader': ['加载', '载入'], 'bulb': ['灯泡', '照明', '开灯'], 'bulb-off': ['关灯'],
    'lamp': ['台灯', '落地灯'], 'air-conditioning': ['空调', '制冷', '冷气'],
    'windmill': ['风扇', '风机', '新风'], 'tv': ['电视', '电视机'],
    'cctv': ['摄像头', '监控', '安防'], 'device-speaker': ['音箱', '智能音箱'],
    'plug': ['插座', '通电', '插头'], 'plug-connected': ['插座已接', '通电中'],
    'thermometer': ['温度计', '温控', '温度'], 'door': ['门', '门磁'], 'window': ['窗', '窗户'],
    'vacuum': ['扫地机', '扫地机器人', '清洁'], 'wash-machine': ['洗衣机'],
    'microwave': ['微波炉'], 'fridge': ['冰箱'], 'bath': ['浴缸', '浴室', '热水'],
    'sofa': ['沙发'], 'bed': ['床', '卧室'], 'solar-panel': ['太阳能', '光伏'],
    'robot': ['机器人'], 'fire-extinguisher': ['灭火器', '消防'],
    'scooter': ['电动车', '两轮车', '踏板车'], 'motorbike': ['摩托', '摩托车'],
    'steering-wheel': ['方向盘'], 'engine': ['引擎', '发动机'],
    'road': ['道路', '路面'], 'traffic-light': ['红绿灯', '交通灯'], 'car': ['汽车', '轿车'],
    'umbrella': ['雨伞', '带伞'], 'rainbow': ['彩虹'], 'droplet': ['水滴', '湿度'],
    'temp-sun': ['高温', '炎热'], 'temp-snow': ['低温', '寒冷'], 'snowflake': ['雪花', '雪'],
    'mist': ['薄雾'], 'storm': ['暴风雨', '狂风暴雨'], 'haze-moon': ['夜间霾'],
    'sunset': ['日落', '傍晚'], 'moon-stars': ['月+星', '星月'], 'clear-high': ['晴', '烈日'],
    'cloud-fog': ['雾', '多云转雾'],
}

# 旧工程名 → 新图标名（不含状态后缀）；带 _off/_on 的会被自动归到对应状态
LEGACY_ICON = {
    # 天气（inSightOS3 的 wx_ 56px / wxs_ 22px 两套前缀）
    'wx_clear': 'weather.clear', 'wxs_clear': 'weather.clear',
    'wx_partly': 'weather.partly-cloudy', 'wxs_partly': 'weather.partly-cloudy',
    'wx_cloud': 'weather.cloudy', 'wxs_cloud': 'weather.cloudy',
    'wx_overcast': 'weather.cloudy', 'wxs_overcast': 'weather.cloudy',
    'wx_shower': 'weather.shower', 'wxs_shower': 'weather.shower',
    'wx_rain_light': 'weather.rain', 'wxs_rain_light': 'weather.rain',
    'wx_rain': 'weather.rain', 'wxs_rain': 'weather.rain',
    'wx_rain_heavy': 'weather.storm', 'wxs_rain_heavy': 'weather.storm',
    'wx_cloud_rain': 'weather.rain', 'wxs_cloud_rain': 'weather.rain',
    'wx_rain_sun': 'weather.rain-sun', 'wxs_rain_sun': 'weather.rain-sun',
    'wx_thunder': 'weather.thunder', 'wxs_thunder': 'weather.thunder',
    'wx_thunder_sun': 'weather.thunder-sun', 'wxs_thunder_sun': 'weather.thunder-sun',
    'wx_hail': 'weather.hail', 'wxs_hail': 'weather.hail',
    'wx_sleet': 'weather.sleet', 'wxs_sleet': 'weather.sleet',
    'wx_snow': 'weather.snow', 'wxs_snow': 'weather.snow',
    'wx_snow_heavy': 'weather.snow', 'wxs_snow_heavy': 'weather.snow',
    'wx_fog': 'weather.cloud-fog', 'wxs_fog': 'weather.cloud-fog',
    'wx_haze': 'weather.haze', 'wxs_haze': 'weather.haze',
    'wx_moon': 'weather.moon', 'wxs_moon': 'weather.moon',
    'wx_moon_star': 'weather.moon-stars', 'wxs_moon_star': 'weather.moon-stars',
    'wx_moon_cloud': 'weather.moon-cloud', 'wxs_moon_cloud': 'weather.moon-cloud',
    'wx_wind': 'weather.wind', 'wxs_wind': 'weather.wind',
    # 智能家居面板 / 通用界面
    'ico_wifi': 'system.wifi', 'ico_bell': 'system.bell', 'ico_lock': 'system.lock',
    'ico_back': 'control.arrow-left', 'ico_more': 'system.more',
    'ico_cloud': 'weather.cloudy', 'ico_house': 'system.home',
    'ico_bt': 'system.bluetooth', 'ico_check_green': 'control.check',
    'ico_person': 'system.user', 'ic_ac': 'device.air-conditioning',
    'sw_off': 'control.toggle-left', 'sw_on': 'control.toggle-right',
    'sw_home_off': 'control.toggle-left', 'sw_home_on': 'control.toggle-right',
    # 两轮车仪表（01-ev-scooter-dashboard）
    'ic_left_main': 'vehicle.turn-left', 'ic_left_sport': 'vehicle.turn-left',
    'ic_left_nav': 'vehicle.turn-left', 'ic_left_alert': 'vehicle.turn-left',
    'ic_right_main': 'vehicle.turn-right', 'ic_right_sport': 'vehicle.turn-right',
    'ic_right_nav': 'vehicle.turn-right', 'ic_right_alert': 'vehicle.turn-right',
    'ic_light_main': 'vehicle.headlight', 'ic_light_sport': 'vehicle.headlight',
    'ic_light_nav': 'vehicle.headlight', 'ic_light_alert': 'vehicle.headlight',
    'ic_cruise_main': 'vehicle.cruise', 'ic_cruise_sport': 'vehicle.cruise',
    'ic_cruise_nav': 'vehicle.cruise', 'ic_cruise_alert': 'vehicle.cruise',
}

PALETTE = {
    'white': [255, 255, 255],
    'iosAccent': [0, 122, 255],
    'materialAccent': [33, 150, 243],
    'warn': [255, 149, 0],
    'danger': [255, 59, 48],
    'success': [52, 199, 89],
    'note': 'FlyThings 无 tint：颜色必须生成时烘焙；换色 = 用 --color 重新生成',
}


def auto_tags(name, tabler, note):
    """tags = 中文 note + 名字/上游名拆词（英文）+ 人工补充同义词。"""
    tags = []
    if note:
        tags.append(re.sub(r'（.*?）|\(.*?\)', '', note).strip())
    for src in (name, tabler or ''):
        tags += [w for w in re.split(r'[-_\s]+', src) if w and not w.isdigit()]
    tags += EXTRA_TAGS.get(name, [])
    out = []
    for t in tags:
        if t and t not in out:
            out.append(t)
    return out


def vendor_state_files(category, name, states):
    """单态图标：无状态后缀；两态：_off/_on。"""
    if not states:
        return {'': gen_icons.out_name(category, name)}
    return {st: gen_icons.out_name(category, name, None, st) for st in states}


def build_vendor_entries(rep):
    with io.open(os.path.join(VENDOR_DIR, 'map.json'), encoding='utf-8') as f:
        m = json.load(f)
    entries = []
    for it in m['icons']:
        cat, name = it['category'], it['name']
        style = 'tabler'
        if it.get('compose'):
            states = ['off', 'on']
            parts = {'off': [], 'on': []}
            for p in it['compose']:
                for st, sub in (('off', 'icons'), ('on', 'icons-filled')):
                    rel = 'vendor/tabler/%s/%s.svg' % (sub, p['tabler'])
                    if not os.path.isfile(os.path.join(ROOT, rel)):
                        rel = 'vendor/tabler/icons/%s.svg' % p['tabler']
                    parts[st].append(dict(svg=rel, dx=p['dx'], dy=p['dy'], scale=p['scale']))
            variant = dict(kind='compose', states=states, parts=parts,
                           files=vendor_state_files(cat, name, states),
                           note='多 glyph 叠放（dx/dy/scale 以 24 网格为 1.0）；'
                                'on 态优先用 filled，缺 filled 的部件沿用 outline')
        else:
            outline = 'vendor/tabler/' + it['outline']
            filled = ('vendor/tabler/' + it['filled']) if it.get('filled') else None
            states = ['off', 'on'] if filled else []
            variant = dict(kind='vendor', states=states,
                           svg=dict({'off': outline, 'on': filled} if filled else {'': outline}),
                           files=vendor_state_files(cat, name, states),
                           note=None if filled else 'Tabler 无 filled 变体 → 单态图（可加 --state 出 _off/_on）')
        for rel in (list(variant.get('svg', {}).values())
                    + [p['svg'] for ps in variant.get('parts', {}).values() for p in ps]):
            if not os.path.isfile(os.path.join(ROOT, rel)):
                rep.append('vendor 缺文件：%s → %s' % (it['name'], rel))
        entries.append(dict(
            name='%s.%s' % (cat, name), category=cat, icon=name,
            source=it['source'], license='MIT',
            tabler=it.get('tabler'), styles=[style], states=states,
            tags=auto_tags(name, it.get('tabler'), it.get('note')),
            defaultColor=[255, 255, 255], sizes=list(VENDOR_SIZES),
            variants={style: variant}, note=it.get('note'),
            aliases=[x for x in (it.get('tabler'),) if x],
        ))
    return entries


def build_self_entries(rep):
    entries = []
    for e in author_svg.active_icons():
        multi = len(e['styles']) > 1
        style = sorted(e['styles'])[0]
        suffix = style if (multi or style == 'material') else None
        states = [s for s in e['styles'][style].keys() if s]
        single = not states
        files = {}
        svg = {}
        for st, _els in e['styles'][style].items():
            files[st] = gen_icons.out_name(e['category'], e['name'], suffix, st or None)
            svg[st] = author_svg.svg_rel(e['category'], e['name'], suffix, st or None)
        entries.append(dict(
            name='%s.%s' % (e['category'], e['name']), category=e['category'], icon=e['name'],
            source='selfdrawn', license='project',
            tabler=None, styles=[style], states=states if not single else [],
            tags=auto_tags(e['name'], None, e['note']) + [t for t in e['tags'] if t not in
                                                          auto_tags(e['name'], None, e['note'])],
            defaultColor=e['defaultColor'], sizes=list(SELF_SIZES),
            variants={style: dict(kind='selfdrawn', svg=svg, states=states, files=files,
                                  note=None)},
            note=e['note'], aliases=e['aliases'], legacyNames=e['legacy'],
        ))
    return entries


def build_legacy_map(entries):
    by_name = {e['name']: e for e in entries}
    out = {}
    for old, target in LEGACY_ICON.items():
        e = by_name.get(target)
        if not e:
            continue
        var = e['variants'][e['styles'][0]]
        files = list(var['files'].values())
        st = None
        if old.endswith('_off'):
            st = 'off'
        elif old.endswith('_on'):
            st = 'on'
        want = var['files'].get(st) if st else None
        out[old] = ([want] + [f for f in files if f != want]) if want else files
    return out


def main(argv):
    write = '--check' not in argv
    rep = []
    vendor = build_vendor_entries(rep)
    selfdrawn = build_self_entries(rep)
    entries = vendor + selfdrawn
    names = [e['name'] for e in entries]
    dup = sorted({n for n in names if names.count(n) > 1})
    if dup:
        rep.append('重名图标：%s' % dup)
    with io.open(os.path.join(VENDOR_DIR, 'VERSION.txt'), encoding='utf-8') as f:
        ver = dict(l.split(': ', 1) for l in f.read().strip().split('\n') if ': ' in l)
    catalog = dict(
        module='icons', version=VERSION,
        description='FlyThings 图标资产库：vendor(tabler) 收录 + 少量自绘，单色烘焙 PNG，按需任意分辨率',
        generatedBy='scripts/gen_catalog.py（禁止手写 catalog.json）',
        sources=dict(
            vendor=dict(name='tabler', version=ver.get('version'), license='MIT',
                        url=ver.get('url'), sha256=ver.get('sha256(tarball)'),
                        vendored_at=ver.get('vendored_at'), map='vendor/tabler/map.json',
                        note='图形未修改；只做单色化 + 等比缩放（见 THIRD-PARTY.md）'),
            selfdrawn=dict(license='project', note='两轮车仪表一套（Tabler 风格不匹配）'),
        ),
        designGrid=24,
        naming=dict(png='ic_<分类>_<名字>[_<风格>][_off|_on].png',
                    svg='svg/<分类>/<名字>[_<风格>][_off|_on].svg（自绘）',
                    vendorSvg='vendor/tabler/{icons,icons-filled}/<glyph>.svg',
                    note='风格后缀仅在该图标提供多种风格时出现（vendor 图标风格=tabler，无后缀）'),
        render=dict(twoState='有 filled 的 vendor 图标：off=outline、on=filled；'
                             '无 filled：单态（加 --state 可强制出 _off/_on 同名图）',
                    compose='先各自栅格化再 alpha 合成（描边不互相穿插）',
                    stroke='px = max(1, round(基准 × size / 网格 × 2) / 2)'),
        palette=PALETTE,
        categories=CATEGORIES,
        counts=dict(icons=len(entries), vendor=len(vendor), selfdrawn=len(selfdrawn)),
        legacyMap=build_legacy_map(entries),
        icons=entries,
    )
    if write and not rep:
        with io.open(os.path.join(ROOT, 'catalog.json'), 'w', encoding='utf-8') as f:
            json.dump(catalog, f, ensure_ascii=False, indent=2)
            f.write('\n')
    print('icons=%d（vendor %d + 自绘 %d）  legacy=%d  %s'
          % (len(entries), len(vendor), len(selfdrawn), len(catalog['legacyMap']),
             'written' if (write and not rep) else ('check-only' if not write else 'ERROR')))
    for r in rep:
        print('  × %s' % r)
    return 1 if rep else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
