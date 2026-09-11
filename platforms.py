# -*- coding: utf-8 -*-
"""平台唯一真相（single source of truth）。

为什么单独一个文件：平台名原先散落在 6 个入口各自手写默认值，且大小写不一
（`create_bin_project`/`gen_ui_test` 默认 `'z21'`，其余 12 处默认 `'F133'`），
模板/工具链/预编译工具的可用范围也没人集中声明 → 外部用户照 README 走容易踩空。
**新增或调整平台，只改本文件**（模板目录 + bin_tools 目录 + 别名都从这里读）。

约定：
- 平台名统一 **大写** 为规范形式（`F133` / `F135` / `T113` / `V85X` / `Z20` / `Z21`）；
- 入参一律过 `validate()`，大小写混写（`z21`）与历史别名（`F133EMMC`）自动归一；
- 目录名才是小写（`templates/HelloWord_Z21` 用规范名、`bin_tools/z21` 用小写键），
  分别用 `template_dir()` / `bin_tool_dir()` 取，**不要在业务代码里手写目录名**。
"""

# 规范名 -> 属性。template/binTool 由 scripts/check_consistency.py 对着真实目录校验。
PLATFORMS = {
    'F133': {
        'arch': 'riscv32', 'template': 'HelloWord_F133', 'binTool': 'f133',
        'alias': ('F133EMMC',), 'note': 'RISC-V，工具链与其他平台不可混用，严禁混入 glibc',
    },
    'F135': {
        'arch': 'arm', 'template': 'HelloWord_F135', 'binTool': 'f135',
        'alias': ('F136',), 'note': 'ARM',
    },
    'T113': {
        'arch': 'arm', 'template': 'HelloWord_T113', 'binTool': 't113',
        'alias': ('T113EMMC', 'T113STDCXX'), 'note': 'ARM，车载互联常用',
    },
    'V85X': {
        'arch': 'arm', 'template': 'HelloWord_V85X', 'binTool': 'v85x',
        'alias': ('V85XEMMC',), 'note': 'ARM，摄像头/DVR 常用',
    },
    'Z20': {
        'arch': 'arm', 'template': 'HelloWord_Z20', 'binTool': 'z20',
        'alias': (), 'note': 'ARM',
    },
    'Z21': {
        'arch': 'arm', 'template': 'HelloWord_Z21', 'binTool': 'z21',
        'alias': (), 'note': 'ARM',
    },
}

DEFAULT_PLATFORM = 'F133'

# 别名 -> 规范名（含自身）
_ALIASES = {}
for _name, _meta in PLATFORMS.items():
    _ALIASES[_name] = _name
    for _a in _meta.get('alias', ()):
        _ALIASES[_a] = _name


def supported() -> list:
    """按规范顺序返回支持的平台名。"""
    return list(PLATFORMS)


def normalize(name):
    """把用户输入归一为规范平台名；无法识别时返回 None（不抛错，供宽容路径用）。"""
    key = str(name or '').strip().upper().replace('-', '').replace('_', '')
    return _ALIASES.get(key)


def validate(name, default=None, allow_empty=False):
    """校验并归一平台名。

    - `name` 为空：`allow_empty=True` 时返回 ''（表示「全部平台」，如 list_packages）；
      否则用 `default`（再没有就用 DEFAULT_PLATFORM）。
    - 无法识别：抛 ValueError，消息里**列出全部支持项**（外部用户能直接改）。
    """
    if name is None or str(name).strip() == '':
        if allow_empty:
            return ''
        name = default or DEFAULT_PLATFORM
    got = normalize(name)
    if not got:
        raise ValueError('未知平台 %r；支持: %s（也可用别名，如 F133EMMC -> F133）'
                         % (name, ', '.join(supported())))
    return got


def meta(name):
    """取平台属性（先归一）。未知平台抛 ValueError。"""
    return PLATFORMS[validate(name)]


def template_dir_name(name) -> str:
    """IDE/包内模板目录名（规范大小写）。"""
    return meta(name)['template']


def bin_tool_dir(name) -> str:
    """预编译工具目录名（小写，对应 bin_tools/<name>/）。"""
    return meta(name)['binTool']


def arch(name) -> str:
    """CPU 架构（编译/工具链判别用）。"""
    return meta(name)['arch']


def describe() -> list:
    """给 AI/文档用的平台表：[{platform, arch, template, binTool, note}]。"""
    return [{'platform': n, 'arch': m['arch'], 'template': m['template'],
             'binTool': m['binTool'], 'note': m['note']}
            for n, m in PLATFORMS.items()]
