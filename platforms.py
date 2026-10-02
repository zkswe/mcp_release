# -*- coding: utf-8 -*-
"""平台唯一真相（single source of truth）。

为什么单独一个文件：平台名原先散落在 6 个入口各自手写默认值，且大小写不一
（`create_bin_project`/`gen_ui_test` 默认 `'z21'`，其余 12 处默认 `'F133'`），
模板/工具链/预编译工具的可用范围也没人集中声明 → 外部用户照 README 走容易踩空。
**新增或调整平台，只改本文件**（模板目录 + bin_tools 目录 + 别名都从这里读）。

约定：
- 平台名统一 **大写**为规范形式（`F133` / `F135` / `T113` / `V85X` / `Z20` / `Z21` / `Z235X`）；
- 入参一律过 `validate()`，大小写混写（`z21`）与历史别名（`F133EMMC`）自动归一；
- 目录名才是小写（`templates/HelloWord_Z21` 用规范名、`bin_tools/z21` 用小写键），
分别用 `template_dir()` / `bin_tool_dir()` 取，**不要在业务代码里手写目录名**。

⚠️ 三层平台命名空间（v0.27.41 起在这里统一，别再各写一份）：
1. **规范名**`PLATFORMS`：可建工程（有 IDE 模板 + bin_tools 预编译工具）。
2. **包生态键**`PACKAGE_KEYS` / `PACKAGE_ALIASES`：依赖包注册表 /
   `package_catalog.json` 用的键（按 SoC 变体分：`f133emmc` / `f136emmc` /
   `t113stdcxx` / `v85xemmc` / `v853`…）。**与规范名不是简单大小写关系**：
   `F135` 的包键是 `f136`，`V85X` 的包键是 `v85x`。
3. **仅包生态平台**`PACKAGE_ONLY`：包生态里真实存在、但 MCP 没有模板/工具链
   （`z6s` / `z261` / `h500s` / `a33nor`）。查询要认，建工程要**说清原因地**拒绝，
不能当成「未知平台」（否则 AI/用户会以为平台不存在）。

旧写法「按平台名字符串白名单判定能力」是错的（同一个平台名，包查询认、建工程不认）；
现在一律走 `resolve()` / `package_key()`，**按真实存在的名字与目录判定**。
"""

# 规范名 -> 属性。template/binTool 由 scripts/check_consistency.py 对着真实目录校验。
PLATFORMS = {
    'F133': {
        'arch': 'riscv64', 'template': 'HelloWord_F133', 'binTool': 'f133',
        'alias': ('F133EMMC',),
        'note': 'RISC-V64（C906 核，isa rv64imafdcvu）；工具链 riscv64-unknown-linux-musl-g++（musl），'
                '与其他平台不可混用，严禁混入 glibc',
    },
    'F135': {
        'arch': 'riscv64', 'template': 'HelloWord_F135', 'binTool': 'f135',
        'alias': ('F136',),
        'note': 'RISC-V64（C906 核）—— 与 F133 同核，不是 ARM；工具链与 F133 同族不可混用（F136 归一为本平台）',
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
    'Z235X': {
        'arch': 'arm', 'template': 'HelloWord_Z235X', 'binTool': 'z235x',
        'alias': (), 'note': 'ARM（SSD2355）；模板已带 base-utility（缺它 fun build 会 fatal error: base/functional.h）；编译需本地把工具链放到 <fun 安装目录>/toolchains/z235x（未随包分发，见 cli-fun-toolchain.md §4.6）；设备端预编译工具待补（bin_tools/z235x 仅占位说明）',
    },
}

DEFAULT_PLATFORM = 'F133'

# 显式例外（历史行为，勿改）：只建 bin 工程 / UI 测试脚手架时的默认平台。
# 以前它散在 create_bin_project / gen_ui_test 的签名里，看不出是「刻意」还是「漂移」，
# 现在登记在这里，与 DEFAULT_PLATFORM 的差异就是一处可见决定。
DEFAULT_BIN_PLATFORM = 'Z21'

# ---------------- 包生态命名空间（依赖包注册表 / package_catalog.json）----------------

# 规范名 -> 包生态主键（注意 F135 -> f136 不是同名小写）
PACKAGE_KEYS = {
    'F133': 'f133', 'F135': 'f136', 'T113': 't113',
    'V85X': 'v85x', 'Z20': 'z20', 'Z21': 'z21',
    'Z6S': 'z6s', 'Z261': 'z261', 'Z235X': 'z235x',
    'H500S': 'h500s', 'A33NOR': 'a33nor',
}

# 包生态里**真实存在**的键 -> 规范名（package_catalog.json / 本地 registry 里确实有这些键）。
# v0.27.41 从 package_tools.PLATFORM_ALIAS（只有 v85x 家族）统一收拢到这里。
PACKAGE_KEY_ALIASES = {
    'f133': 'F133', 'f133emmc': 'F133',
    'f136': 'F135', 'f136emmc': 'F135',
    't113': 'T113', 't113emmc': 'T113', 't113stdcxx': 'T113',
    'v85x': 'V85X', 'v85xemmc': 'V85X',
    'z20': 'Z20', 'z21': 'Z21',
    'z6s': 'Z6S', 'z261': 'Z261', 'z235x': 'Z235X',
    'h500s': 'H500S', 'a33nor': 'A33NOR',
}

# 只作入参归一用、**不对应任何真实包键**的历史写法（V85x 家族旧名，
# 直接拿去查包会查空，必须先归一到 v85x）。
#
# ⚠️ V85x 家族写法收齐（v0.27.87，需求方问「这几个你适配了吗」）：
#   **V851 / V851S / V851S3 / V853 / V853S / V553 / V552**一律归一到 **V85X**平台；
#包键统一走 **`v85x`（SPINOR）或 `v85xemmc`（EMMC）**（两个键在 package_catalog.json /
#注册表里真实存在），**不要拿 `v851s` 这种芯片名当平台键去查包**（查不到任何包）。
PACKAGE_INPUT_ALIASES = {'v853': 'V85X', 'v552': 'V85X', 'v553': 'V85X',
                         'v851': 'V85X', 'v851s': 'V85X', 'v851s3': 'V85X',
                         'v853s': 'V85X'}

# 兼容旧名：合并视图（package_tools.PLATFORM_ALIAS 引用的就是这个对象）
PACKAGE_ALIASES = dict(PACKAGE_KEY_ALIASES)
PACKAGE_ALIASES.update(PACKAGE_INPUT_ALIASES)

# 只有依赖包生态、没有 IDE 模板/预编译工具的平台。
# chips 取自 package_catalog.json（空 = 目录里也没登记，仅包名可见）。
PACKAGE_ONLY = {
    'Z6S': {'chips': [], 'note': '仅依赖包生态（package_catalog 里 1 个包）'},
    'Z261': {'chips': ['SSD261Q'], 'note': '仅依赖包生态（60 个包）'},
    'H500S': {'chips': [], 'note': '仅依赖包生态（16 个包）'},
    'A33NOR': {'chips': [], 'note': '仅依赖包生态（13 个包）'},
}

# 别名 -> 规范名（含自身）
_ALIASES = {}
for _name, _meta in PLATFORMS.items():
    _ALIASES[_name] = _name
    for _a in _meta.get('alias', ()):
        _ALIASES[_a] = _name

# 全部已知平台名（可建工程 + 仅包生态），供提示文案与校验用
ALL_PLATFORM_NAMES = list(PLATFORMS) + list(PACKAGE_ONLY)


def supported() -> list:
    """按规范顺序返回**可建工程**的平台名。"""
    return list(PLATFORMS)


def _key(name) -> str:
    """归一成「无分隔符小写」键（与包生态键同形）。"""
    return ''.join(ch for ch in str(name or '').strip().lower()
                   if ch.isalnum())


def _canonical_or_none(name):
    """宽容归一：可建工程名 → 规范名；包生态名（含变体/旧名）→ 规范名；都不是 → None。"""
    got = normalize(name)
    if got:
        return got
    k = _key(name)
    return PACKAGE_KEY_ALIASES.get(k) or PACKAGE_INPUT_ALIASES.get(k)


def _near(name, limit=3):
    """相近的已知平台名（拼写纠错用；只做子串/前后缀近似，不猜）。"""
    k = _key(name)
    if not k:
        return []
    out = []
    for cand in ALL_PLATFORM_NAMES:
        c = _key(cand)
        if k in c or c in k:
            out.append(cand)
        elif len(k) >= 3 and (c.startswith(k[:3]) or k.startswith(c[:3])):
            out.append(cand)
    return out[:limit]


def normalize(name):
    """把用户输入归一为规范平台名；无法识别时返回 None（不抛错，供宽容路径用）。"""
    key = str(name or '').strip().upper().replace('-', '').replace('_', '')
    return _ALIASES.get(key)


def package_key(name) -> str:
    """平台名 → 包生态键（依赖包注册表 / package_catalog.json 用的键）。

入参可以是规范名（`F135`）、历史别名（`F133EMMC` / `V853`）、或已经是包键（`f136emmc`）。
    - 已经是**真实包键**就原样返回（保真：emmc/stdcxx 变体各自有自己的包集）；
    - 否则先归一到规范名，再取该平台的主键（注意 F135 -> f136）。
    **不做白名单拦截**：认不出来就原样小写返回，让包查询层按真实键去查（查不到自然回空）。
    """
    k = _key(name)
    if k in PACKAGE_KEY_ALIASES or k in PACKAGE_KEYS.values():
        return k
    canon = _canonical_or_none(name)
    return PACKAGE_KEYS.get(canon, k)


def resolve(name):
    """平台名 → 完整解析结果（按**真实能力**判定，不是字符串白名单）。

返回 None 表示与任何已知平台都不沾边。否则：
      {input, canonical, packageKey, buildable, template, binTool,
       packageOnly, chips, note, known}
    `buildable=False`（仅包生态）时 `template`/`binTool` 为空，但 `packageOnly=True`
会说明它是真实平台、只是 MCP 没有模板/工具链。
    """
    if name is None or str(name).strip() == '':
        return None
    pk = package_key(name)
    canon = _canonical_or_none(name)
    if canon in PLATFORMS:
        m = PLATFORMS[canon]
        return {'input': name, 'canonical': canon, 'packageKey': pk,
                'buildable': True, 'template': m['template'], 'binTool': m['binTool'],
                'arch': m['arch'], 'packageOnly': False, 'chips': [],
                'note': m['note'], 'known': True}
    if canon in PACKAGE_ONLY:
        m = PACKAGE_ONLY[canon]
        return {'input': name, 'canonical': canon, 'packageKey': pk,
                'buildable': False, 'template': '', 'binTool': '', 'arch': '',
                'packageOnly': True, 'chips': m.get('chips') or [],
                'note': m.get('note') or '', 'known': True}
    return None


def validate(name, default=None, allow_empty=False):
    """校验并归一平台名（**建工程口径**：只接受有模板/工具链的规范名）。

    - `name` 为空：`allow_empty=True` 时返回 ''（表示「全部平台」，如 list_packages）；
否则用 `default`（再没有就用 DEFAULT_PLATFORM）。
    - 无法识别：抛 ValueError，消息里**列出全部支持项**（外部用户能直接改）。
    - 名字是真的、但只有包生态：抛 ValueError 并**说清是缺模板而不是平台不存在**
      （旧文案一律回「未知平台」，等于把真实平台判成不存在）。
    """
    if name is None or str(name).strip() == '':
        if allow_empty:
            return ''
        name = default or DEFAULT_PLATFORM
    tried = name
    got = _canonical_or_none(name)
    if not got:
        near = _near(tried)
        raise ValueError('未知平台 %r；支持: %s（也可用别名，如 F133EMMC -> F133）%s'
                         % (tried, ', '.join(supported()),
                            ('；相近的已知平台: %s' % ', '.join(near)) if near else ''))
    if got in PACKAGE_ONLY:
        meta_ = PACKAGE_ONLY[got]
        raise ValueError(
            '平台 %s 只有依赖包生态，MCP 没有它的 IDE 模板/预编译工具，无法在此平台建工程/编译；'
            '可建工程的平台: %s'
            % (got, ', '.join(supported())))
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
    """给 AI/文档用的平台表：[{platform, arch, template, binTool, packageKey,
    buildable, note}]；末尾再附「仅包生态」平台（buildable=false，无模板）。"""
    out = [{'platform': n, 'arch': m['arch'], 'template': m['template'],
            'binTool': m['binTool'], 'packageKey': PACKAGE_KEYS.get(n, ''),
            'buildable': True, 'note': m['note']}
           for n, m in PLATFORMS.items()]
    out += [{'platform': n, 'arch': '', 'template': '', 'binTool': '',
             'packageKey': PACKAGE_KEYS.get(n, ''), 'buildable': False,
             'note': m.get('note') or '仅依赖包生态'}
            for n, m in PACKAGE_ONLY.items()]
    return out


def package_keys() -> list:
    """包生态里**真实存在**的全部键（供一致性闸门对着 package_catalog.json 比对）。"""
    return sorted(set(PACKAGE_KEYS.values()) | set(PACKAGE_KEY_ALIASES))
