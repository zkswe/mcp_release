# -*- coding: utf-8 -*-
"""契约测试公共工具（stdlib only，离线零副作用）。

跑法（MCP 根目录或任意位置）：
    python -m unittest discover -s tests -q
    python scripts/check_consistency.py --with-tests
"""
import asyncio
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile

TESTS = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(TESTS)
for _p in (BASE, os.path.join(BASE, 'ui_tools'), TESTS):
    if _p not in sys.path:
        sys.path.insert(0, _p)

EXAMPLES = os.path.join(BASE, 'ui_tools', 'examples')


# ---------------------------------------------------------------------------
# 离线守卫：契约用例的契约是「离线、零设备依赖」（见 tests/README.md）。
#
# 为什么要有它（2026-10-03 实测）：此前是「按调用点逐个 mock」的写法 —— 用例 patch 了
# `pt._run_fun` / `pt._launch_gate` / `pt._device_sync_check`，但被测函数内部**又新加了一条**
# 设备调用（`flythings_build_ui_flow` 里的 `device_probes.clear_logcat`），mock 就漏了一条：
# fake gate 返回的假序列号 `S1` 被拿去**真 adb** 上执行；本机挂着设备时直接阻塞。
# 后果实测：单模块 78s / 91s，全套从文档宣称的「约 12 秒」涨到 **>900s**，把
# `check_consistency.py --with-tests` 自己的 900s 超时撞爆（门禁必红，且随"是否插设备"漂移）。
#
# 所以把边界从「逐个调用点」上收到「唯一出口」：**默认拦掉真实 adb**，语义等价于
# 「本机没有 adb」（这正是"离线"该有的行为，调用方本来就都要处理 adb 不可用）；
# 确实要起真进程的用例，用 `allow_subprocess()` 显式开口（目前只有 fui/工具链类用例需要）。
_ADB_GUARD = {'allow': False, 'blocked': 0, 'first_site': ''}


@contextlib.contextmanager
def allow_subprocess():
    """显式放行真实外部子进程（默认禁用）。用于确实需要真工具链的用例。"""
    old = _ADB_GUARD['allow']
    _ADB_GUARD['allow'] = True
    try:
        yield
    finally:
        _ADB_GUARD['allow'] = old


def adb_blocked_count():
    """被守卫拦下的 adb 调用次数（用例可据此断言「没漏到真设备」）。"""
    return _ADB_GUARD['blocked']


def adb_first_site():
    """第一次被拦下的调用点（`文件:行`），便于定位是哪个 op 漏了 mock。"""
    return _ADB_GUARD['first_site']


def _install_adb_guard():
    import adb_tools as _at
    real = _at._run

    def guarded(args, timeout=15):
        if _ADB_GUARD['allow']:
            return real(args, timeout=timeout)
        _ADB_GUARD['blocked'] += 1
        if not _ADB_GUARD['first_site']:
            import traceback
            frames = [f for f in traceback.extract_stack()[:-1]
                      if '/tests/' not in f.filename.replace('\\', '/')]
            if frames:
                f = frames[-1]
                _ADB_GUARD['first_site'] = '%s:%d' % (os.path.basename(f.filename), f.lineno)
        # 与「本机没装 adb」同形（rc=1 + 空输出），调用方本来就要处理这种情况。
        return 1, '', '[offline-guard] 契约用例默认不调用真实 adb'

    _at._run = guarded


_install_adb_guard()


def call(op, args=None):
    """走分发器（与客户端完全同一条路径），返回原始字符串。

    args 传 dict 会自动 json.dumps；传 str 则原样作为 args 下发（用于测非法 JSON 等边界）。
    """
    import mcp_server
    payload = args if isinstance(args, str) else json.dumps(args or {}, ensure_ascii=False)
    return asyncio.run(mcp_server.flythings_kb(op=op, args=payload))


def jcall(op, args=None):
    return json.loads(call(op, args))


def payload(result):
    """拆**分发器信封** → op 自己的返回体。

    分发器统一包一层 `{ok, op, data, warnings}`，其中 `data` 是 op 返回的 **JSON 字符串**
    （`ok` 的含义是"这次调用没炸"，**不是** op 自己的 `ok`）。
    断言 op 行为时要先拆这层，否则 `r['ok']` 恒真、业务字段（如 `converted`）根本不在顶层
    —— 2026-10-03 写 i18n 用例时踩到，故收成公共辅助（`result` 不是信封时原样返回）。
    """
    if isinstance(result, dict) and isinstance(result.get('data'), str):
        try:
            return json.loads(result['data'])
        except ValueError:
            return result
    return result


def manifest():
    return json.load(io.open(os.path.join(BASE, 'tools_manifest.json'), encoding='utf-8'))


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    io.open(path, 'w', encoding='utf-8', newline='\n').write(text)


def fixture(name):
    return os.path.join(EXAMPLES, name)


def project(tmp=None):
    """最小可识别工程骨架：package.properties + ui/ + resources/images/。"""
    tmp = tmp or tempfile.mkdtemp(prefix='mcp_test_')
    write(os.path.join(tmp, 'package.properties'), 'projectName=unittest\n')
    os.makedirs(os.path.join(tmp, 'resources', 'images'), exist_ok=True)
    os.makedirs(os.path.join(tmp, 'ui'), exist_ok=True)
    return tmp


# ⚠️ 某些环境里**删除**极慢：本机实测 `shutil.rmtree` ≈ 0.5~1.0 秒/条目
#    （正常机器 <1ms；`python -S` 关掉 Python 侧 shim 也一样 → 拦截在更低层）。
#    后果：全套 773 条用例 **85%~95% 的墙钟时间花在删临时目录上**，不是测试逻辑
#    （实测 test_deps_install_guard：61.6s 里 58.5s 是 rmtree，而它只删了 130 个条目；
#    清理改 no-op 后 70.2s → 3.5s）。
#    ⚠️ 这里的数字与 `WORK_PLAN.md` 的两处、`tests/README.md` 的一处一样，由
#    `check_consistency.py --with-tests` 的「当前用例数各处声明 == 实测」核对 —— 改规模时
#    门禁会指名道姓报出"哪一处写了多少、实测多少"，不要把它当装饰性注释。
#    本地快速迭代可设 FLYTHINGS_TEST_KEEP_TEMP=1 跳过清理 —— 临时目录用 mkdtemp 唯一命名，
#    残留不影响用例正确性，但会在 %TEMP% 里堆积（事后自行清理）。**CI / 发布闸门不要开。**
_KEEP_TEMP = (os.environ.get('FLYTHINGS_TEST_KEEP_TEMP') or '').strip() == '1'
# 删除通道：auto（默认，Windows 走系统 rmdir）/ shutil / none（跳过）。留作 A/B 与救急用。
_DEL = (os.environ.get('FLYTHINGS_TEST_DEL') or 'auto').strip().lower()


def cleanup(path):
    """删除临时工程。

    ⚠️ 本机实测（2026-10-03）：`shutil.rmtree` 删一棵 300 文件的临时树要 **40s**，
    而 `cmd /c rmdir /s /q` 只要 **5s**（快 ~8 倍）—— 沙箱对 `DeleteFile`
    （`os.remove` 走的那个）的拦截远重于 `RemoveDirectory`。
    由于用例总量里 85%~95% 的墙钟都花在删临时目录上（见本模块头部实测），这里在 Windows 上优先走
    系统 `rmdir`，失败再退化回 `shutil.rmtree`（不静默吞：退化后仍真删）。

    可用环境变量切换（A/B 与救急）：`FLYTHINGS_TEST_DEL=auto|shutil|none`；
    `FLYTHINGS_TEST_KEEP_TEMP=1` 等价于 `none` —— 只在本地快速迭代时用
    （临时目录是 mkdtemp 唯一命名，残留不影响用例正确性；但会在 %TEMP% 堆积）。CI / 发布闸门不要开。
    """
    if _KEEP_TEMP or _DEL == 'none':
        return
    if os.name == 'nt' and _DEL != 'shutil':
        try:
            r = subprocess.run(['cmd', '/c', 'rmdir', '/s', '/q', path],
                               capture_output=True, timeout=120)
            if r.returncode == 0 or not os.path.exists(path):
                return
        except Exception:
            pass                          # 退化到 shutil（下面真删）
    import shutil
    shutil.rmtree(path, ignore_errors=True)


_FTU_BYTES = {}


def ftu_bytes():
    """返回一个**真实合法**的 ftu 字节流（用随包 fui pack 一次性生成后缓存）。

    背景：以前用例直接写 4 字节占位 `ZKSR` 充当 ftu；规则①「只有 ftu 没 json → 自动 unpack」
    上线后，占位 ftu 会被判定为异常 ftu 并报错（这是期望行为），所以 fixture 得用真 ftu。
    """
    if 'v' in _FTU_BYTES:
        return _FTU_BYTES['v']
    data = b''
    tmp = tempfile.mkdtemp(prefix='mcp_ftu_')
    try:
        import project_tools as pt
        jp = os.path.join(tmp, 'main.json')
        write(jp, json.dumps({'id': 0, 'resolution': {'width': 1024, 'height': 600},
                              'position': {'left': 0, 'top': 0, 'width': 1024, 'height': 600}},
                             ensure_ascii=False))
        pt._run_fui('pack', tmp)
        fp = os.path.join(tmp, 'main.ftu')
        if os.path.isfile(fp):
            data = io.open(fp, 'rb').read()
    except Exception:
        data = b''
    finally:
        import shutil as _sh
        _sh.rmtree(tmp, ignore_errors=True)
    _FTU_BYTES['v'] = data
    return data
