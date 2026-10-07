# -*- coding: utf-8 -*-
"""FlyThings 组件「平台能力矩阵」注册表加载器（唯一消费入口）。

真源 = 与本文件同目录的 platform_capabilities.json。回答两件事：
  ① 某组件在某平台能不能用、前置条件/实测值/限制是什么
  ② 某平台上能跑哪些组件          ← 以前要跨 15 篇 platforms.md 手拼，现在一次查询

设计纪律（与 ui_schema_loader.py / op_spec_loader.py 同构）：
  **消费方一律从注册表派生，禁止再抄一份。**
各篇 `components/*/platforms.md` 里那张矩阵表是**派生产物**（scripts/gen_component_platforms.py
重写），只保留原理、坑、验收方法与细节展开。

⚠️ 口径（2026-10-07 需求方）：**BLE 不在本矩阵里** —— 它是**组件包/依赖包**层级的能力
（与 `mqtt` 同级，见 `components_catalog.DECLARED_GAPS['ble']` 的登记），平台可用性以
`components/ble/platforms.md` 正文为准。

平台清单**不在这里重定义**：平台身份（arch/template/binTool/packageKey）以 `platforms.py` 为唯一真源，
本注册表只存「组件 × 平台」的能力行。

容错口径：注册表缺失 / 解析失败 / 查询不存在的组件 → 抛 PlatformCapError（带路径或组件名），**不静默**。

用法：
    import platform_cap_loader as pc
    pc.load()
    pc.components()                       # ['album_upload', 'blend2d', ...]（不含 ble：它是组件包层级，见 components_catalog.DECLARED_GAPS）
    pc.spec('blur')                       # 该组件的矩阵
    pc.render_table('blur')               # 渲染成 markdown 行（唯一实现）
    pc.rows_for_platform('Z20')           # [(组件, 行)] —— 「Z20 上能跑什么」
    pc.status_of('blur', 'Z20')           # 该组件在该平台那一行（含原始标签与单元格）
    pc.validate()                         # 自检问题列表（空 = 合规）
"""
import io
import json
import os

BASE = os.path.dirname(os.path.abspath(__file__))
REG_PATH = os.path.join(BASE, 'platform_capabilities.json')

# 平台身份口径（platforms.py）之外的合法键：只剩「全平台」。
# 口径（2026-10-02）：PC（自测/预烘形态）与 MCU Lite（另一套东西）**不进本矩阵**，
# 连同它们的行一起从注册表删除——所以这里不再把它们当合法平台键。
EXTRA_PLATFORMS = ('ALL',)

_CACHE = None


class PlatformCapError(RuntimeError):
    """注册表缺失 / 损坏 / 查询不存在的组件。消息里永远带路径或组件名。"""


def load():
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    if not os.path.isfile(REG_PATH):
        raise PlatformCapError('平台能力注册表缺失: %s（platform_capabilities.json 必须随包分发）'
                               % REG_PATH)
    try:
        with io.open(REG_PATH, encoding='utf-8') as f:
            reg = json.load(f)
    except Exception as e:
        raise PlatformCapError('平台能力注册表解析失败: %s（%s: %s）'
                               % (REG_PATH, type(e).__name__, e))
    if not isinstance(reg.get('components'), dict):
        raise PlatformCapError('平台能力注册表缺少 components 段: %s' % REG_PATH)
    _CACHE = reg
    return reg


def components():
    return sorted(load()['components'].keys())


def spec(comp):
    c = load()['components'].get(comp)
    if not isinstance(c, dict):
        raise PlatformCapError('%s 未登记进 platform_capabilities.json（改能力请改注册表）' % comp)
    return c


def columns(comp):
    return list(spec(comp).get('columns') or [])


def rows(comp):
    return list(spec(comp).get('rows') or [])


def _canon_query(platform):
    """把**查询输入**也折算成 platforms.py 的规范名：查 F136 应等价于查 F135。"""
    p = (platform or '').strip()
    up = p.upper()
    if up in EXTRA_PLATFORMS:
        return up
    try:
        import platforms as _pl
        return str(_pl.resolve(p).get('canonical') or up).upper()
    except Exception:
        return up


def _keys(row):
    """行的平台键：优先用注册表里预存的 canonical（已按 platforms.py 归一），回退 resolve。"""
    keys = row.get('canonical') or row.get('platforms') or []
    return [str(k).upper() for k in keys]


def platforms_of(comp):
    """该组件覆盖的平台键（规范名，去重排序）。"""
    out = []
    for r in rows(comp):
        for p in _keys(r):
            if p not in out:
                out.append(p)
    return sorted(out)


def rows_for_platform(platform):
    """「这台设备上能跑哪些组件」：[(组件, 行)]（同一组件可能有多个平台行）。"""
    key = _canon_query(platform)
    out = []
    for comp in components():
        for r in rows(comp):
            k = _keys(r)
            if key in k or 'ALL' in k:
                out.append((comp, r))
    return out


def components_for_platform(platform):
    """去重后的组件名列表（回答「Z20 上能跑什么」最常用）。"""
    out = []
    for comp, _ in rows_for_platform(platform):
        if comp not in out:
            out.append(comp)
    return sorted(out)


def status_of(comp, platform):
    """某组件在某平台的那一行（找不到回 None）。"""
    key = _canon_query(platform)
    for r in rows(comp):
        if key in _keys(r):
            return r
    return None


def cell(comp, platform, column):
    """取某组件/平台/列名的单元格文本（列名忽略首尾空白）。"""
    r = status_of(comp, platform)
    if not r:
        return None
    cols = columns(comp)
    for i, c in enumerate(cols):
        if c.strip() == column.strip():
            cells = r.get('cells') or []
            return cells[i] if i < len(cells) else None
    return None


# ---- 渲染：唯一实现（生成的表必须与这里逐字节一致，--check 才可能通过）----------

def render_table(comp, first_col='平台'):
    """把矩阵渲染成 markdown 表格行（含表头与分隔行）。"""
    cols = columns(comp)
    head = [first_col] + cols
    lines = ['| ' + ' | '.join(head) + ' |',
             '|' + '---|' * len(head)]
    for r in rows(comp):
        cells = [str(r.get('platform') or '')] + [str(x) for x in (r.get('cells') or [])]
        cells = (cells + [''] * len(head))[:len(head)]
        lines.append('| ' + ' | '.join(cells) + ' |')
    return lines


def validate():
    """自检：平台键是否合法、file 是否存在、单元格数是否与列数一致。返回问题列表。"""
    errs = []
    reg = load()
    if not str(reg.get('authority') or '').strip():
        errs.append('缺少 authority 声明')
    valid = set()
    try:
        import platforms as _pl
        valid = {p['platform'] for p in _pl.describe()}
    except Exception as e:                        # platforms.py 坏了不该让本表静默通过
        errs.append('读不到 platforms.py 的平台口径（%s: %s）' % (type(e).__name__, e))
    valid |= set(EXTRA_PLATFORMS)
    for comp, c in sorted(reg['components'].items()):
        f = c.get('file')
        if not f or not os.path.isfile(os.path.join(BASE, f)):
            errs.append('%s: file 指向不存在的文件: %s' % (comp, f))
        ncol = len(c.get('columns') or [])
        if ncol == 0:
            errs.append('%s: 没有列定义' % comp)
        if not c.get('rows'):
            errs.append('%s: 没有平台行' % comp)
        for r in c.get('rows') or []:
            if len(r.get('cells') or []) != ncol:
                errs.append('%s: 行 %s 的单元格数 %d != 列数 %d'
                            % (comp, r.get('platform'), len(r.get('cells') or []), ncol))
            if not (r.get('platforms') or r.get('canonical')):
                errs.append('%s: 行 %s 没解析出平台键（label=%r）'
                            % (comp, r.get('platform'), r.get('platform')))
            for p in _keys(r):
                if p not in valid:
                    errs.append('%s: 行 %s 的平台键 %r 不在 platforms.py 口径里'
                                % (comp, r.get('platform'), p))
    # 验收口径（verificationPolicy）：**登记过的**组件可以「不逐平台验」，但必须：
    #   ① 名单里的组件真实存在 ② verifiedOn 是它自己的一行 ③ 其余行**不许再出现「未验证」**
    #      （改口径就得把那些单元格改成 ➖ 并写明口径；不是留一堆 TODO 让它一直挂着）
    for pol in reg.get('verificationPolicy') or []:
        pid = pol.get('id')
        for key in ('id', 'components', 'verifiedOn', 'rule', 'why', 'decidedAt'):
            if not pol.get(key):
                errs.append('verificationPolicy[%s] 缺字段 %s' % (pid, key))
        comps = pol.get('components') or []
        if len(set(comps)) != len(comps):
            errs.append('verificationPolicy[%s] 组件有重复' % pid)
        for comp in comps:
            if comp not in reg['components']:
                errs.append('verificationPolicy[%s] 列了不存在的组件 %r' % (pid, comp))
                continue
            rows_ = rows(comp)
            on = pol.get('verifiedOn')
            if not any(on in _keys(r) for r in rows_):
                errs.append('verificationPolicy[%s] 说在 %s 验过，但 %s 没有这个平台的行'
                            % (pid, on, comp))
            for r in rows_:
                if on in _keys(r):
                    continue
                for cell in (r.get('cells') or []):
                    if '未验证' in cell or '待测' in cell:
                        errs.append('%s 行 %s 还写着「未验证」—— 该组件已在 verificationPolicy[%s] '
                                    '登记「只在 %s 单平台验收」，其余平台请改 ➖ 并写明口径'
                                    % (comp, r.get('platform'), pid, on))
    return errs


if __name__ == '__main__':
    print('组件 %d 个，能力行 %d 条' % (len(components()), sum(len(rows(c)) for c in components())))
    for comp in components():
        print('  %-24s %d 平台  %s' % (comp, len(rows(comp)), ' / '.join(platforms_of(comp))))
    errs = validate()
    print('自检：%s' % ('通过' if not errs else '\n  ' + '\n  '.join(errs)))
