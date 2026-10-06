# -*- coding: utf-8 -*-
"""薄壳转发层：定位并调用 `bin/zkuitool.exe`。

为什么存在：发布版把 ui_tools 的实现体收进了 `bin/zkuitool.exe`（Cython 编译，
无源码），但 MCP 仍以 `import check_all` 这类方式使用它们 —— 于是同名模块保留为
**只含签名与转发**的薄壳，函数体统一走本层。

环境变量 `ZKUITOOL` 可覆盖 exe 路径（调试/换架构时用）。
"""
import json
import os
import subprocess
import sys
import tempfile

__all__ = ['exe_path', 'rpc', 'cli']

# 默认超时（秒）：实测常规调用 0.2～0.7 s，60 s = 近百倍余量；
# 真机拖帧 / 全量 AA 审计 / 批量出图 / 裁字库这类**本来就慢**的调用，
# 由薄壳把它自带的 `timeout` 参数透传成 `_timeout=…`（见 scripts/gen_ui_tools_stubs.py），
# 也可用环境变量 `ZKUITOOL_TIMEOUT` 全局覆盖。
DEFAULT_TIMEOUT = 60

_CACHE = {}


def _root():
    """MCP 包根（ui_tools 的上一级）。"""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def exe_path():
    if 'exe' in _CACHE:
        return _CACHE['exe']
    env = os.environ.get('ZKUITOOL', '')
    cands = []
    if env:
        cands.append(env)
    base = _root()
    cands += [os.path.join(base, 'bin', 'zkuitool', 'zkuitool.exe'),   # onedir（发布版默认）
              os.path.join(base, 'bin', 'zkuitool', 'zkuitool'),
              os.path.join(base, 'bin', 'zkuitool.exe'),             # onefile（内部/单文件形态）
              os.path.join(base, 'bin', 'zkuitool'),
              os.path.join(base, 'toolchain', 'zkuitool.exe'),
              os.path.join(base, 'toolchain', 'zkuitool')]
    for c in cands:
        if c and os.path.isfile(c):
            _CACHE['exe'] = c
            return c
    raise RuntimeError(
        '未找到 zkuitool.exe：请确认它随包位于 <包根>/bin/ 下，或用环境变量 '
        'ZKUITOOL 指向可执行文件。')


def _jsonable(v):
    if isinstance(v, os.PathLike):
        return os.fspath(v)
    if isinstance(v, (list, tuple, set, frozenset)):
        return [_jsonable(x) for x in v]
    if isinstance(v, dict):
        return {str(k): _jsonable(x) for k, x in v.items()}
    return v


def rpc(mod, func, *args, **kwargs):
    """把 `mod.func(*args, **kwargs)` 交给 exe 执行并取回返回值。

    超时顺序：`_timeout=` 关键字（函数级，薄壳对自带 timeout 的函数会自动传）
    → 环境变量 `ZKUITOOL_TIMEOUT` → `DEFAULT_TIMEOUT`（60 s）。
    **不允许无限等** —— 2026-10-06 实测过转发进程挂住把父进程一起拖死。
    """
    exe = exe_path()
    per_call = kwargs.pop('_timeout', None)
    raw = per_call if per_call else (os.environ.get('ZKUITOOL_TIMEOUT') or DEFAULT_TIMEOUT)
    try:
        timeout = int(raw)
    except (TypeError, ValueError):
        raise RuntimeError('超时值需为整数秒，当前=%r' % (raw,))
    tmp = tempfile.mkdtemp(prefix='zkuitool-')
    a_path = os.path.join(tmp, 'args.json')
    o_path = os.path.join(tmp, 'out.json')
    with open(a_path, 'w', encoding='utf-8') as f:
        json.dump({'args': _jsonable(list(args)), 'kwargs': _jsonable(dict(kwargs))},
                  f, ensure_ascii=False, default=str)
    cmd = [exe, 'rpc', '%s.%s' % (mod, func), '--args', a_path, '--out', o_path]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              encoding='utf-8', errors='replace', timeout=timeout)
    except subprocess.TimeoutExpired:
        raise RuntimeError('zkuitool rpc 超时（%ds）：%s.%s —— 可用 ZKUITOOL_TIMEOUT 调大'
                           % (timeout, mod, func))
    except OSError as e:
        raise RuntimeError('zkuitool.exe 执行失败: %s' % e)
    if not os.path.isfile(o_path):
        tail = ((proc.stderr or '') + (proc.stdout or '')).strip().splitlines()[-6:]
        raise RuntimeError('zkuitool rpc 无输出（rc=%s）：%s' % (proc.returncode, ' | '.join(tail)))
    with open(o_path, encoding='utf-8') as f:
        payload = json.load(f)
    if not payload.get('ok'):
        err = payload.get('error') or {}
        raise RuntimeError('[%s] %s' % (err.get('type', 'Error'), err.get('msg', '未知错误')))
    return payload.get('result')


def cli(mod):
    """CLI 透传：`python ui_tools/<mod>.py <args>` → `zkuitool <mod> <args>`。"""
    return subprocess.call([exe_path(), mod] + list(sys.argv[1:]))
