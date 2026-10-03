# -*- coding: utf-8 -*-
"""FlyThings project tools: ftu read, project spec, validation, fui/fun integration."""
import json, os, re, shutil, subprocess, tempfile, time

import platforms as _platforms  # 平台矩阵唯一来源（新增/调整平台只改 platforms.py）

try:                      # adb 单一入口（v0.27.84）：PC 端 adb 解析 + 设备探测 + 型号→平台
    import adb_tools as _adb
    _ADB = _adb
    _ADB_ERR = ''
except Exception as _e:   # 不阻断（无 adb 也能 build；launch 时才需要）
    _adb = None
    _ADB = None
    _ADB_ERR = repr(_e)

try:                      # 设备侧只读探针（launch 活性 / 运行时指纹 / 面板信息）
    import device_probes as _dprobe
except Exception as _e2:  # 不阻断（探针缺失只影响「对账/活性」这两条检查）
    _dprobe = None
    _DPROBE_ERR = repr(_e2)

# ---------- 工具链路径（可配置 + 自动探测）----------
# 优先级：环境变量 FLYTHINGS_FUN_DIR（用户显式指定，最高）> 包内 toolchain（随包分发）> 标准安装目录
_BASE = os.path.dirname(os.path.abspath(__file__))
_FUN_DIR_CANDIDATES = [
    os.environ.get('FLYTHINGS_FUN_DIR', ''),
    os.path.join(_BASE, 'toolchain'),                    # 分发包内置工具链（本包 toolchain/）
    os.path.join(os.path.dirname(_BASE), 'toolchain'),  # 原 tools/toolchain 结构
    r'D:\zkswe\fun',          # 正式工具链安装目录（与 fun.exe 同目录）
    r'C:\zkswe\fun',
]

def _tool_dir():
    """返回工具目录（第一个含 fui.exe 或 fun.exe 的候选）；找不到返回空串。
工具链可能只含 fui.exe（仅布局转换）或只含 fun.exe（仅编译推送），任一存在即可。"""
    for d in _FUN_DIR_CANDIDATES:
        if d and (os.path.isfile(os.path.join(d, 'fui.exe')) or os.path.isfile(os.path.join(d, 'fun.exe'))):
            return d
    return ''

def _tool_path(name):
    """在工具目录中查找可执行文件；工具目录缺失或文件不在其中则返回 name（让 subprocess 报错更直观）。"""
    d = _tool_dir()
    if not d:
        return name
    p = os.path.join(d, name)
    return p if os.path.isfile(p) else name

FUI_EXE = _tool_path('fui.exe')
FUN_EXE = _tool_path('fun.exe')

# ---------------- 构建产物目录（09-28 版 fun 起从 .fun/ 改名 .fsc/）----------------
# 新版 fun（v0.0.2+2609281006_e09dc96 起，内部包名 fun→fsc）把产物目录从 `<项目>/.fun/<平台>/`
# 改成 `<项目>/.fsc/<平台>/（锁文件 .fun-lock.json → .fsc-lock.json）。这里统一解析：
# **两代都认**（旧工程/旧工具链仍在 .fun/ 下的产物不会看不到），优先 .fsc。
BUILD_DIR_NAMES = ('.fsc', '.fun')


def _find_build_artifact(project_root, platform, *parts):
    """在 .fsc/<平台>/ 与 .fun/<平台>/ 里找构建产物；找不到回新名路径。"""
    cands = [os.path.join(project_root, name, platform, *parts) for name in BUILD_DIR_NAMES]
    for c in cands:
        if os.path.exists(c):
            return c
    return cands[0]


# IDE 空白模板（新建项目骨架来源，保证框架约定天然正确）
# 优先用包内 templates/（分发包内置，客户无需装 IDE）；其次 IDE 安装目录。
# ⚠️ 下面只是「默认探测起点」，不是平台白名单：`_template_dir` 会先在包内 templates/
# 里找，再按目录扫描 IDE workspace（大小写/命名差异也能认出来），最后才用这张表。
# 可用环境变量 FLYTHINGS_IDE_WORKSPACE 指向非默认安装目录。
IDE_WORKSPACE = os.environ.get('FLYTHINGS_IDE_WORKSPACE', r'C:\zkswe\FlyThingsPreview\bin\workspace')
IDE_TEMPLATES = {
    'F133': r'C:\zkswe\FlyThingsPreview\bin\workspace\HelloWord_F133',
    'F135': r'C:\zkswe\FlyThingsPreview\bin\workspace\HelloWord_F135',
    'Z21':  r'C:\zkswe\FlyThingsPreview\bin\workspace\HelloWord_Z21',
    'T113': r'C:\zkswe\FlyThingsPreview\bin\workspace\HelloWord_T113Nor',
    'V85X': r'C:\zkswe\FlyThingsPreview\bin\workspace\Helloword_V85x',
    'Z20':  r'C:\zkswe\FlyThingsPreview\bin\workspace\Helloword_Z20',
}


def _scan_ide_templates():
    """按真实目录扫 IDE workspace，返回 {规范平台名: 目录}。

为什么扫而不是只靠 IDE_TEMPLATES：那张表写死了本机路径与大小写
    （Helloword_V85x vs HelloWord_V85X），换机器/改目录名就“没模板”，
而真实能力应该看目录里到底有什么。
    """
    found = {}
    try:
        if not os.path.isdir(IDE_WORKSPACE):
            return found
        for name in sorted(os.listdir(IDE_WORKSPACE)):
            d = os.path.join(IDE_WORKSPACE, name)
            if not os.path.isdir(d):
                continue
            for plat in _platforms.supported():
                key = name.lower().replace('_', '').replace('-', '')
                # 只认 HelloWord*<平台> 形态，避免误抓同目录下别人的工程
                if key.startswith('helloword') and key.endswith(plat.lower()):
                    found.setdefault(plat, d)
    except OSError:
        return found
    return found


def _template_dir(plat):
    """模板目录：包内 templates/HelloWord_<plat> 优先 → IDE workspace 实扫 → 硬编码表兜底。"""
    pkg = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates', 'HelloWord_' + plat)
    if os.path.isdir(pkg):
        return pkg
    hit = _scan_ide_templates().get(plat)
    if hit:
        return hit
    legacy = IDE_TEMPLATES.get(plat, '')
    return legacy if legacy and os.path.isdir(legacy) else legacy
# 平台别名表改由 platforms.py 提供（v0.27.32 起单一来源）；保留同名常量供旧调用方兼容
PLATFORM_ALIASES = {a: n for n, m in _platforms.PLATFORMS.items() for a in m.get('alias', ())}


# ---------------- fui 基础 ----------------
def _fui_supports_unpack():
    """检测当前 fui.exe 的能力（仅支持 pack json→ftu 时为 False，布局以 json 为源）。
结果缓存，避免重复启动子进程。"""
    if getattr(_fui_supports_unpack, '_cached', None) is not None:
        return _fui_supports_unpack._cached
    try:
        r = subprocess.run([FUI_EXE, 'help'], capture_output=True, text=True, timeout=15,
                           stdin=subprocess.DEVNULL, encoding='utf-8', errors='replace')
        out = ((r.stdout or '') + (r.stderr or '')).lower()
        _fui_supports_unpack._cached = ('unpack' in out)
    except Exception:
        _fui_supports_unpack._cached = False
    return _fui_supports_unpack._cached


def _run_fui(cmd, target_dir):
    """执行 fui.exe 命令（pack），命令格式：fui.exe <cmd> <目录路径>。"""
    if not os.path.isdir(target_dir):
        return {"success": False, "error": f"目录不存在: {target_dir}"}
    try:
        r = subprocess.run([FUI_EXE, cmd, target_dir],
                           capture_output=True, text=True, timeout=60,
                           stdin=subprocess.DEVNULL,  # ⚠️ 防 fui.exe 继承 MCP stdio 管道挂起
                           encoding='utf-8', errors='replace')
        return {"success": r.returncode == 0, "returncode": r.returncode,
                "stdout": (r.stdout or '')[-600:], "stderr": (r.stderr or '')[-600:]}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ---------------- fun.exe 基础（build/launch）----------------
def _adb_online_devices():
    """列出「当前在线（state=device）」的 adb 设备 serial；adb 不可用/无设备回 []。
仅用于多设备歧义提示（拉不到不报错，不阻断流程）。
    ⚠️ v0.27.84 起 adb 一律走 adb_tools.resolve_adb()（不再写死 'adb' 字面量）。"""
    if _adb is None:
        return []
    try:
        devs, _err = _adb.list_devices_l()
    except Exception:
        return []
    return [d['serial'] for d in devs if d.get('state') == 'device']


def _run_fun(cmd, project_dir, device='', retries=1, timeout=600, extra=None):
    """执行 fun.exe 命令（build/launch 等），在项目根目录运行。
    fun.exe 与 fui.exe 同目录（D:/zkswe/fun/ 或自动探测）。
    launch 走网络推送（adb over wifi），网络抖动/推送中断会失败——retries>1 时
自动重试（间隔 2s），覆盖「网络超时静默/误推旧固件」场景；信任 fun 差分能力，
不自写 push 脚本校验产物。build 类本地命令 retries 保持 1（无需重试）。
    ⚠️ fun launch **支持**`-s <serial|IP>`（2026-09-16 实测修正；旧注「不支持 -s」作废）：
    device 非空时追加 `-s <device>`；device 为空且检测到多台在线设备时，回 warnings
    （多设备下 fun 静默取 adb 列表第一个 → 可能推错设备，症状是 launch 成功但界面不变）。
    extra: 追加到命令后的参数列表（如 fun pack -o <path>），默认 None。"""
    if not os.path.isdir(project_dir):
        return {"success": False, "error": "项目目录不存在: %s" % project_dir}
    if not os.path.isfile(FUN_EXE):
        return {"success": False, "error": "fun.exe 未找到（工具目录: %s）。"
                "请设置环境变量 FLYTHINGS_FUN_DIR 指向含 fun.exe/fui.exe 的目录，"
                "或将其安装到 D:\\zkswe\\fun\\。" % _tool_dir()}
    args = [FUN_EXE, cmd] + list(extra or [])
    # ⚠️ 2026-09-14 定：暂时发布的 MCP 不支持 `fun sim`（模拟器运行）——
    # 工具面不暴露该能力，这里再显式拦住，避免 AI 自行调用/文档误报“支持”。
    if cmd == 'sim':
        return {"success": False,
                "error": "MCP 暂不支持 fun sim（模拟器运行）",
                "hint": "要推真机调试用 flythings_build_ui_flow（fun launch）；"
                        "要出图验证用 flythings_device_screenshot；"
                        "模拟器请在本地命令行手动跑 fun sim。"}
    warnings = []
    if cmd == 'launch':
        if device:
            args += ['-s', str(device)]
        else:
            devs = _adb_online_devices()
            if len(devs) > 1:
                warnings.append(
                    '检测到 %d 台在线 adb 设备 %s，未指定 device：fun 会静默取列表第一个，'
                    '可能推错设备（建议传 device=\'<serial|IP>\'）' % (len(devs), devs))
    last = None
    for attempt in range(1, max(1, retries) + 1):
        try:
            r = subprocess.run(args, cwd=project_dir,
                               capture_output=True, text=True, timeout=timeout,
                               stdin=subprocess.DEVNULL,
                               encoding='utf-8', errors='replace')
            if r.returncode == 0:
                return {"success": True, "returncode": 0, "retried": attempt - 1,
                        "warnings": warnings,
                        "stdout": (r.stdout or '')[-800:], "stderr": (r.stderr or '')[-800:]}
            last = {"success": False, "returncode": r.returncode, "retried": attempt - 1,
                    "warnings": warnings,
                    "stdout": (r.stdout or '')[-800:], "stderr": (r.stderr or '')[-800:]}
        except subprocess.TimeoutExpired:
            last = {"success": False, "error": "fun %s 执行超时（>%ss）" % (cmd, timeout), "retried": attempt - 1}
        except Exception as e:
            last = {"success": False, "error": str(e), "retried": attempt - 1}
        if attempt < retries:
            time.sleep(2)  # 网络抖动自愈间隔
    last['error'] = last.get('error') or (last.get('stderr') or last.get('stdout') or '')[-300:]
    last['message'] = "fun %s 失败，已自动重试 %d 次" % (cmd, max(1, retries))
    return last


def _rewrite_ftu_resolution(project_root, resolution):
    """重写 ui/*.ftu 内嵌的分辨率。
    ftu 里也含 resolution（根节点 resolution + position），只改 .settings prefs 不够，
必须 unpack → 改 json 的 resolution/position → pack 回 ftu。
同目录已有 json 就直接改它（快）；没有 json 则按能力探测走 unpack（v0.27.91 起随包 fui 支持），
无 unpack 又无 json 时标记 failed（提示手动处理，不静默产空 ftu）。
返回 {"updated": [ftu名], "failed": [{ftu, error}]}。
    """
    ui_dir = os.path.join(project_root, 'ui')
    result = {"updated": [], "failed": []}
    if not os.path.isdir(ui_dir):
        return result
    try:
        w, h = (int(x) for x in str(resolution).lower().replace('x', ' ').split())
    except Exception:
        result["failed"].append({"ftu": '*', "error": f"分辨率格式错误: {resolution}（应为 WxH 如 800x480）"})
        return result
    for fn in sorted(os.listdir(ui_dir)):
        if not fn.endswith('.ftu'):
            continue
        ftu_path = os.path.join(ui_dir, fn)
        base = fn[:-4]
        tmp = tempfile.mkdtemp(prefix='ftu_res_')
        try:
            shutil.copy2(ftu_path, tmp)
            # json 源：优先同目录已有 json；fui 无 unpack 时必需 json（有则直接改，省一步反向）
            src_json = os.path.join(ui_dir, base + '.json')
            json_from_project = os.path.isfile(src_json)
            if json_from_project:
                shutil.copy2(src_json, tmp)
                jf = os.path.join(tmp, base + '.json')
            elif not _fui_supports_unpack():
                result["failed"].append({"ftu": fn,
                                          "error": f"当前 fui.exe 不含 unpack 且无 {base}.json 可改分辨率，"
                                                   f"请换用支持 unpack 的 fui.exe 或手动修改 json"})
                continue
            else:
                r = _run_fui('unpack', tmp)
                if not r['success']:
                    result["failed"].append({"ftu": fn, "error": (r.get('stderr') or r.get('stdout') or '')[-200:]})
                    continue
                jf = os.path.join(tmp, base + '.json')
                if not os.path.isfile(jf):
                    result["failed"].append({"ftu": fn, "error": 'unpack 后未找到 json'})
                    continue
            with open(jf, encoding='utf-8-sig') as f:
                data = json.load(f)
            data['resolution'] = {'width': w, 'height': h}
            pos = data.get('position', {})
            pos['width'], pos['height'] = w, h
            data['position'] = pos
            with open(jf, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            r2 = _run_fui('pack', tmp)
            if not r2['success']:
                result["failed"].append({"ftu": fn, "error": (r2.get('stderr') or r2.get('stdout') or '')[-200:]})
                continue
            shutil.copy2(os.path.join(tmp, fn), ftu_path)
            # json 是布局真源：工程里自带的 json 要同步写回（否则 json 留旧分辨率，
            # 下次 pack 把 ftu 打回旧值；且 ftu 新 json 旧会误报 devModified）
            if json_from_project:
                shutil.copy2(jf, src_json)
            result["updated"].append(fn)
        except Exception as e:
            result["failed"].append({"ftu": fn, "error": str(e)})
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    return result


# ---------------- ui json/ftu 时间戳校验 ----------------
def _ui_timestamp_check(project_root, dev_threshold=60):
    """检查 ui 目录下 .json 与 .ftu 的修改时间一致性。
返回 {"stale": [...], "missing": [{json}], "devModified": [...], "ftuOnly": [{ftu}], "ok": [...]}。
    stale = json 比 ftu 新（改过 json 没重新 pack）；missing = 有 json 无 ftu；
    ftuOnly = 只有 ftu 没有同名 json（老工程/IDE 工程 → 直接 unpack 转出 json）；
    devModified = ftu 比 json 新超过 dev_threshold 秒（**分钟级**= 用户/IDE 直接用 IDE 编辑过 ftu，
要先 unpack 同步；fui pack 生成时两者差 <1s，所以分钟级差异必是人为）。"""
    ui_dir = os.path.join(project_root, 'ui')
    result = {"stale": [], "missing": [], "devModified": [], "ftuOnly": [], "ok": []}
    if not os.path.isdir(ui_dir):
        return result
    names = sorted(os.listdir(ui_dir))
    for fn in names:
        if not fn.endswith('.json'):
            continue
        jp = os.path.join(ui_dir, fn)
        fp = os.path.join(ui_dir, fn[:-5] + '.ftu')
        jt = os.path.getmtime(jp)
        if os.path.isfile(fp):
            ft = os.path.getmtime(fp)
            if jt > ft + 1:  # json 比 ftu 新（容差 1 秒）
                result["stale"].append({"json": fn, "ftu": fn[:-5] + '.ftu',
                                         "jsonTime": jt, "ftuTime": ft})
            elif ft > jt + dev_threshold:  # ftu 比 json 新「分钟级」→ 用户/IDE 编辑过 ftu
                result["devModified"].append({"json": fn, "ftu": fn[:-5] + '.ftu',
                                               "jsonTime": jt, "ftuTime": ft})
            else:
                result["ok"].append(fn)
        else:
            result["missing"].append(fn)
    # 只有 ftu 没有同名 json（自动同步规则①：直接转出 json）
    for fn in names:
        if fn.endswith('.ftu') and not os.path.isfile(os.path.join(ui_dir, fn[:-4] + '.json')):
            result["ftuOnly"].append(fn)
    return result


def _sync_ftu_to_json(project_root):
    """ftu → json 的**自动**同步（2026-09-18 口径，只在这两种情况下做）：
    ① 只有 ftu 没有同名 json（老工程/纯 IDE 工程）→ 直接 unpack 转出 json；
    ② ftu 比 json 新**分钟级**（≥ dev_threshold=60s → 用户/IDE 编辑过 ftu）→ unpack 覆盖 json；
    ③ 其余情况**不做 ftu→json**（json 是布局源，只需 json→ftu）。
返回 {"synced": [{ftu}], "syncedDetail": [{ftu, why}], "skipped": [...], "failed": [...]}。
    """
    ui_dir = os.path.join(project_root, 'ui')
    result = {"synced": [], "syncedDetail": [], "skipped": [], "failed": []}
    if not os.path.isdir(ui_dir):
        return result
    ts = _ui_timestamp_check(project_root)
    todo = [{"ftu": f, "why": "ftuOnly：只有 ftu 没有 json"} for f in ts.get('ftuOnly', [])]
    todo += [{"ftu": d['ftu'], "why": "devModified：ftu 比 json 新分钟级（用户/IDE 编辑过）"}
             for d in ts.get('devModified', [])]
    if not todo:
        result["skipped"].append({"ftu": '*', "reason": "json 为源且不比 ftu 旧 → 不需要 ftu→json"})
        return result
    if not _fui_supports_unpack():
        for t in todo:
            result["skipped"].append({"ftu": t['ftu'],
                                       "reason": "当前 fui.exe 不含 unpack，无法从 ftu 反解析 json；"
                                                 "以 json 为源重新 pack（用户对 ftu 的编辑需手动同步到 json）"})
        return result
    for t in todo:
        ftu_name = t['ftu']
        ftu_path = os.path.join(ui_dir, ftu_name)
        tmp = tempfile.mkdtemp(prefix='ftu_sync_')
        try:
            shutil.copy2(ftu_path, tmp)
            r = _run_fui('unpack', tmp)
            if not r['success']:
                # ⚠️ 异常 ftu（不是合法 ftu / 已损坏）→ 明确报错并告知用户，不静默跳过（2026-09-18 09:14）
                result["failed"].append({
                    "ftu": ftu_name, "why": t['why'],
                    "error": ((r.get('stderr') or r.get('stdout') or '')[-200:] or 'unpack 失败').strip(),
                    "hint": f"ui/{ftu_name} 不能反解析（不是合法 ftu 或文件已损坏）→ 无法转出 json；"
                            f"请提供对应的 {ftu_name[:-4]}.json，或重新导出/修复这个 ftu"})
                continue
            jf = os.path.join(tmp, ftu_name[:-4] + '.json')
            if not os.path.isfile(jf):
                result["failed"].append({
                    "ftu": ftu_name, "why": t['why'], "error": 'unpack 返回成功但没产出 json',
                    "hint": f"ui/{ftu_name} 反解析未产出 json（文件异常）；请提供 {ftu_name[:-4]}.json 或重新导出该 ftu"})
                continue
            dst = os.path.join(ui_dir, ftu_name[:-4] + '.json')
            shutil.copy2(jf, dst)  # ftu 为准，覆盖/创建同名 json
            # ⚠️ unpack 出的 json 的 mtime 是 ftu 内嵌的打包时间戳（旧），
            # 不调整会继续误判 devModified → 把 json mtime 对齐到 ftu 文件时间
            ft_mtime = os.path.getmtime(ftu_path)
            os.utime(dst, (ft_mtime, ft_mtime))
            result["synced"].append(ftu_name)
            result["syncedDetail"].append({"ftu": ftu_name, "why": t['why']})
        except Exception as e:
            result["failed"].append({"ftu": ftu_name, "error": str(e)})
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    return result

# ---------------- json 解析 ----------------
def _parse_ui_json(json_path):
    try:
        with open(json_path, encoding='utf-8-sig') as f:
            data = json.load(f)
    except Exception as e:
        return {"success": False, "error": f"json 解析失败: {e}"}
    res = data.get('resolution', {})
    controls, id_mapping = [], {}
    for key, val in data.items():
        if key in ('id', 'resolution', 'position', 'backgroundColor', 'beepEnable', 'topmost'):
            continue
        if isinstance(val, dict) and '__' in key:
            ctype = key.split('__')[0]
            cap = val.get('caption', '')
            cid = val.get('id')
            controls.append({'key': key, 'caption': cap, 'id': cid, 'type': ctype})
            if cap:
                id_mapping[cap] = cid
    return {"success": True,
            "resolution": {"width": res.get('width'), "height": res.get('height')},
            "controls": controls, "idMapping": id_mapping}


# ---------------- 工具 1: read_json ----------------
def flythings_read_json(json_path):
    """解析 .json 布局文件，返回结构化信息。
    ⚠️ 传入 .ftu 时不再当「加密无法解析」：本 op 只读 json，请先用 flythings_fui_unpack 反解析。
    """
    if json_path.lower().endswith('.ftu'):
        return {"success": False, "isFtu": True,
                "error": "本 op 只解析 json；ftu 是二进制布局（设备实际加载的文件），先反解析再读。",
                "hint": "调 flythings_fui_unpack(ftu_path=...) 得到 jsonPath（默认覆盖同目录同名 json；"
                        "要保留原 json 传 overwrite=false），再把 jsonPath 传给本 op"}
    if not os.path.isfile(json_path):
        return {"success": False, "error": f"json 文件不存在: {json_path}"}
    return _parse_ui_json(json_path)


# ---------------- 工具 2: project spec ----------------
_PROJECT_SPEC = {
    "directoryRules": {
        "activity": "IDE生成目录（mainActivity.cpp/h 由 IDE 编译时根据 ftu 自动生成），禁止创建/修改/覆盖；业务代码只写 src/logic/*.cc",
        "logic": "UI与业务的关联层（回调里取控件指针/刷界面/调业务对象），不做复杂逻辑；复杂功能拆独立 C++ 类放业务域目录并在 logic include+调用",
        "domain": "业务域目录：直接建在 src/ 下、按业务域命名（src/network/、src/media/、src/storage/ 等），不要在 src/ 下再分 core/modules 中间层"
    },
    "generationRules": {
        "idMacros": {"file": "mainActivity.h", "section": "/*TAG:Macro宏ID*/", "autoGenerated": True},
        "controlPointers": {"file": "mainActivity.cpp", "section": "/*TAG:GlobalVariable全局变量*/", "autoGenerated": True},
        "initSequence": "onCreate() → findControlByID() → mActivityPtr=this → onUI_init()"
    },
    "caveats": [
        "编译体系有**两套**，别混（2026-09-17 需求方纠偏）：**IDE**编译 src/activity/*.cpp（再由它 #include logic.cc）；**fun build 直接把 src/logic/*.cc 当编译单元，src/activity/* 完全不参与编译**（fun 自动生成入口与分发：generated/{event,event_dispatcher,ui_main}.cpp；编译宏 FUN_BUILD=1）。实测：构建目录 <平台>/CMakeLists.txt 的 add_library 只有 Main.cpp + logic/mainLogic.cc + uart/*.cpp + generated/*.cpp",
        "控件指针 mXXXPtr / ID_MAIN_* 宏 / 回调表全部由 IDE 编译时根据 ftu 自动生成，用户禁止手写定义",
        "禁止在 logic.cc 中定义 ID_MAIN_* 宏、static ZKxxx* 指针、new ZKxxx、findControlByID 初始化",
        "onUI_init() 时所有控件指针已由 IDE 初始化完毕，直接使用即可",
        "每个 logic.cc 必须包含 REGISTER_ACTIVITY_TIMER_TAB（不用定时器也保留空表）",
        "setBackgroundBmp 只调一次；帧刷新用 setInvalid(!isInvalid()) 交替——**仅限只读 textview**（button 等可交互控件会被置为无效态=禁用，见 knowledge/uicontrols/touch-events.md §6）",
        "obtainListItemData_XXX 禁止耗时代码（滚动时每行调用）",
        "设备字库不支持 emoji 和特殊字符（■ ● ⌫ ℃ 等）",
        "新建项目应从 IDE 模板创建（flythings_create_project），勿手搭骨架",
        "工程文件 .project/.cproject/.settings 是 IDE 必需，缺失则项目无法编译",
        "Manifest 用新格式 <manifest platform=\"...\">（旧 <Manifest> 格式 IDE 不认）",
        "代码层架构：logic/*.cc 只做 UI 与业务的关联操作（取控件指针/setText/调业务对象）；复杂功能开发成独立 C++ 类放**业务域目录**，在 logic include+调用；新增业务代码一律用 .cpp/.h（独立编译单元，fun build 自动编译），禁止新建 .cc 文件——.cc 是 IDE 按页面生成的 logic 专属（仅 mainLogic.cc 等），靠 mainActivity.cpp #include 进编译单元，手写 .cc 不会被编译——IDE 体系里 Makefile 只编 %.cpp %.c，fun 体系里只把 src/logic/*.cc 当编译单元；所以业务代码一律用 .cpp/.h",
        "src 目录命名（2026-09-13 需求方定规）：按业务域直接建在 src/ 下，不设 core/modules 中间分层——如 src/network/NetworkManager.cpp+.h、src/media/MediaPlayer.cpp+.h、src/storage/ConfigStore.cpp+.h；域名为小写英文单数名词，文件=域内一个职责类（大驼峰，与文件名一致）；include 用相对 src/ 路径（#include \"network/NetworkManager.h\"）",
        "页面架构（2026-09-13 定规；**默认口径先看这条**）：**一个工程默认只有一个 Activity**（ui/main.ftu + src/activity/mainActivity.* + src/logic/mainLogic.cc）——**多个页面不是多个 ftu/Activity**，同一业务域内的页面/页签/二级页/弹窗/整屏遮挡 → **同一个 ftu 里的多个整屏 window + showWnd/hideWnd 切换**；只有跨业务域、需独立生命周期或返回栈、超大页面才拆独立 ftu（openActivity）；并列内容区翻页 → pagewindow/slidewindow/scrollwindow 容器。底层关系：ftu=Activity=独立编译单元（独立生命周期/返回栈），window=同 Activity 内显隐（零切换成本/共享指针）。详见知识库 devflow/page-architecture-spec.md",
        "**不要改构建目录里的 <平台>/CMakeLists.txt**（09-28 起 `.fsc/<平台>/`，旧版 `.fun/<平台>/`；fun 自动生成，文件头写着 Don't edit this file manually，下次 build 会覆盖；改它没有意义也不会生效）：要加源文件就放到 src/ 下（业务代码一律 .cpp/.h），fun 会把 src/**/*.cpp 与 src/logic/*.cc 收进编译单元",
        "src/uart 为系统模板：UartContext/ProtocolSender 勿改，只改 ProtocolData.h 与 ProtocolParser.cpp 协议部分",
        "布局遮挡/点不到/谁压谁 → flythings_layout_audit（纯几何静态判定，先看 json 再截图）；json 布局用 fui pack 生成 ftu（ui/ 下已附带 fui.exe）；编译推送用 fun.exe build / fun.exe launch（项目根目录已附带 fun.exe）",
        "⚠️ 交付流程：项目生成后直接用 fun.exe build 编译、fun.exe launch 推送设备，无需客户手动导入 FlyThings IDE 编译烧录",
        "需要三方能力（MQTT/HTTP/JSON/数据库/蓝牙/SSL/OTA/图片等）→ 先 flythings_package_search / flythings_manifest 检索现有 package，有包用包，禁止手写库或凭空 include",
        "代码 include 了三方库头文件 → Manifest.xml 必须声明对应 package（validate_project 会检查缺失依赖）；**框架基础包 base-utility 同理且更容易被漏**：代码或 fun 生成的 generated/*.h 里出现 `#include <base/...>`（典型 base/functional.h）→ Manifest 必须有 `<package id=\"base-utility\" version=\"^10.0.0\"/>`，缺了 fun build 直接 `fatal error: base/functional.h: No such file or directory`（老工程/自建工程高发）；用 flythings_add_package 加包后**必须重跑 fun install**，否则 include 路径不进 CMake",
        "GPIO 外设控制：代码能力非 UI 控件——#include \"utils/GpioHelper.h\"（zkhardware 包）；GpioHelper::input(pin) 读（1高/0低/-1失败）/ output(pin,val) 写（1高/0低）/ registerGpioListener 边沿监听；引脚名按平台不同（Z11:B_02/E_20、SV50PB:PIN7、SV50PC:PIN2、H500S:PG0、SV50PD:A0，头文件有宏）；模组需启用 gpio 功能并升级固件",
    ]
}


def flythings_get_project_spec():
    """返回 FlyThings 项目的结构化规范约束。"""
    return _PROJECT_SPEC


# ---------------- 项目平台/分辨率探测 ----------------
def _detect_project_info(root):
    """从项目文件探测硬件平台与屏幕分辨率。
探测顺序：
      platform  <- Manifest.xml 的 <manifest platform="...">
      resolution <- .settings/com.zksw.flythings.easyui.prefs 的 resolution=
      resolution <- ui/*.json 的 resolution 字段（兜底）
返回 {"platform": str|None, "resolution": str|None, "sources": {...}}。
任一缺失即返回 None，调用方（AI）应据此向用户询问。
    """
    info = {"platform": None, "resolution": None, "sources": {}}
    mf = os.path.join(root, 'Manifest.xml')
    if os.path.isfile(mf):
        try:
            mtext = open(mf, encoding='utf-8', errors='replace').read()
        except Exception:
            mtext = ''
        m = re.search(r'<manifest\s+platform=["\']([^"\']+)["\']', mtext)
        if m:
            info['platform'] = m.group(1)
            info['sources']['platform'] = 'Manifest.xml'
    _r = read_resolution(root)
    if _r:
        info['resolution'] = _r.replace('x', 'x')
        info['sources']['resolution'] = ('.settings prefs'
                                        if os.path.isdir(os.path.join(root, '.settings'))
                                        else 'ui json')
    if not info['resolution']:
        ui_dir = os.path.join(root, 'ui')
        if os.path.isdir(ui_dir):
            for fn in sorted(os.listdir(ui_dir)):
                if fn.endswith('.json'):
                    try:
                        with open(os.path.join(ui_dir, fn), encoding='utf-8-sig') as f:
                            j = json.load(f)
                        res = j.get('resolution', {})
                        w, h = res.get('width'), res.get('height')
                        if w and h:
                            info['resolution'] = f'{w}x{h}'
                            info['sources']['resolution'] = f'ui/{fn}'
                            break
                    except Exception:
                        continue
    return info


# ---------------- 工具 3: validate project ----------------
def _is_empty_project(root):
    """空白项目判定：ui 目录不存在，或其中没有任何 .ftu 文件。
    ftu 是设备实际加载的布局文件（json 只是中间产物）；没有 ftu 即视为空白项目，
无需再去读取 json。返回 True/False。
    """
    ui_dir = os.path.join(root, 'ui')
    if not os.path.isdir(ui_dir):
        return True
    return not any(f.endswith('.ftu') for f in os.listdir(ui_dir))


def flythings_validate_project(root):
    """检查项目是否符合 FlyThings 规范，返回 errors/warnings。

    ⚠️ 空白项目判定：工作目录 ui/ 下没有 .ftu 即视为空白项目（无需再去读 json），
返回 isEmptyProject=true，此时不再做任何检查，直接向用户询问硬件平台
与屏幕分辨率（如 800x480），然后调用 flythings_create_project 创建项目；
禁止到其他目录检索 json/ftu 文件。
    （待询问的平台清单不在这里写死：用 platforms.py 的 supported()，
不要在提示文案里手写枚举——那就成了第二份平台真相。）
若 projectInfo.platform 或 projectInfo.resolution 为 null（非空白项目但缺 Manifest/ui 布局），
同样必须停下来向用户询问这两个选项，禁止自行猜测或用默认值继续。
    """
    if not os.path.isdir(root):
        return {"success": False, "error": f"项目目录不存在: {root}"}
    project_info = _detect_project_info(root)
    if _is_empty_project(root):
        return {"success": True, "isEmptyProject": True,
                "projectInfo": project_info,
                "needUserInput": {'platform': not project_info['platform'],
                                   'resolution': not project_info['resolution']},
                "supportedPlatforms": _platforms.supported(),
                "hint": '空白项目（ui 目录无 .ftu 布局，无需再读取 json）：'
                        '直接向用户询问硬件平台（%s）与屏幕分辨率（如 800x480），'
                        '然后调用 flythings_create_project 创建；'
                        '禁止去其他目录检索 json/ftu。' % '/'.join(_platforms.supported()),
                "errors": [], "warnings": []}
    errors, warnings = [], []
    src = os.path.join(root, 'src')
    ui = os.path.join(root, 'ui')
    need_user = {'platform': not project_info['platform'],
                 'resolution': not project_info['resolution']}
    if need_user['platform'] or need_user['resolution']:
        warnings.append({'file': 'project', 'type': 'unknown_platform_resolution',
                         'msg': '无法确认硬件平台与屏幕分辨率（缺 Manifest 平台属性或 ui 布局/设置），'
                                '需要向用户询问平台（%s）与分辨率（如 800x480）'
                                % '/'.join(_platforms.supported())})

    # 0.9 分辨率 vs 模板（480×480 灰窗事件防线的**离线半部**；在线半部在 build_ui_flow）：
    #     工程分辨率与所用平台模板不一致 → 大概率是改错（也可能是刻意适配不同面板，所以要人确认）。
    tpl_root = os.path.join(_BASE, 'templates')
    tpl_res = ''
    if project_info.get('platform'):
        tpl_res = read_resolution(_template_dir(project_info['platform']) or '')
    if tpl_res and project_info.get('resolution') and tpl_res != project_info['resolution']:
        warnings.append({'file': 'ui', 'type': 'resolution_differs_from_template',
                         'msg': '工程分辨率 %s 与 %s 模板的 %s 不同 —— 确认是**刻意适配另一块面板**'
                                '（那就继续）还是改错；分辨率与面板不符会灰窗/黑屏，'
                                '真机流程还会再核一次'
                                % (project_info['resolution'], project_info['platform'], tpl_res)})

    # 1. logic 层
    logic_dir = os.path.join(src, 'logic')
    if os.path.isdir(logic_dir):
        for fn in sorted(os.listdir(logic_dir)):
            if not fn.endswith(('.cc', '.cpp')):
                continue
            p = os.path.join(logic_dir, fn)
            try:
                text = open(p, encoding='utf-8', errors='replace').read()
            except Exception:
                continue
            for m in re.finditer(r'#define\s+(ID_MAIN_\w+)', text):
                errors.append({'file': f'src/logic/{fn}', 'type': 'redefinition',
                               'msg': f'{m.group(1)} 不应在 logic 层定义（IDE 自动生成在 mainActivity.h）'})
            # 手写控件指针定义（static ZKxxx* mXxxPtr）
            for m in re.finditer(r'static\s+ZK\w+\s*\*\s*(m\w+Ptr)\s*=', text):
                errors.append({'file': f'src/logic/{fn}', 'type': 'manual_control_ptr',
                               'msg': f'{m.group(1)} 不应在 logic 层定义（控件指针由 IDE 生成在 mainActivity.cpp）'})
            # new ZKxxx 手动创建控件
            for m in re.finditer(r'new\s+ZK\w+', text):
                errors.append({'file': f'src/logic/{fn}', 'type': 'manual_new_control',
                               'msg': '禁止在 logic 层 new 控件（控件由 ftu/IDE 管理）'})
            # findControlByID 出现在 logic 层（应直接用 IDE 生成的指针）
            for m in re.finditer(r'findControlByID\s*\(', text):
                warnings.append({'file': f'src/logic/{fn}', 'type': 'manual_find_control',
                                 'msg': 'logic 层使用 findControlByID（一般应直接用 IDE 生成的 mXXXPtr；仅动态控件场景需要）'})
            if 'REGISTER_ACTIVITY_TIMER_TAB' not in text:
                warnings.append({'file': f'src/logic/{fn}', 'type': 'missing_timer_tab',
                                 'msg': '缺少 REGISTER_ACTIVITY_TIMER_TAB（每个 logic.cc 必须有，不用定时器也保留空表）'})
            if len(re.findall(r'setBackgroundBmp', text)) > 1:
                warnings.append({'file': f'src/logic/{fn}', 'type': 'bg_bmp_multi',
                                 'msg': 'setBackgroundBmp 多次调用（应只调一次；帧刷新用 setInvalid 交替——仅限只读 textview，交互控件会被禁用）'})
            # ⚠️ 宏批量生成回调（如 #define DEFINE_DAY_CB(i) void onButtonClick_BtnDay##i(...) 展开 42 个日期格）
            #     → fun build 扫描 ftu 回调时识别不到宏展开 → 向 logic.cc 追加显式桩 → 与宏展开重定义冲突
            # 检测：以 #define 开头（含 \ 续行）的宏体内含回调签名模式（onXxxClick/onXxxChanged/onXxxTouch/onXxxTimer）
            for m in re.finditer(r'#define\s+\w+\s*\([^)]*\)\s*[^\n]*(?:\\\n[^\n]*)*', text):
                if re.search(r'(?:on\w*Click|on\w*Changed|on\w*Touch|on\w*Timer)', m.group(0)):
                    errors.append({'file': f'src/logic/{fn}', 'type': 'macro_generated_callback',
                                   'msg': f'宏生成回调 {m.group(0)[:44].strip()}...：fun build 无法识别宏展开的回调，'
                                          f'会向 logic.cc 追加同名桩导致重定义编译错误；请显式定义每个回调函数，禁止宏批量生成'})
                    break  # 每个文件只报一次
    else:
        warnings.append({'file': 'src/logic', 'type': 'missing_dir', 'msg': 'src/logic 目录不存在'})

    # 1.1 ⚠️ 手写 .cc 检查（2026-08-31）：.cc 是 IDE 按页面生成的 logic 专属（xxxLogic.cc，
    #靠 mainActivity.cpp #include 进编译单元）；Makefile 只编译 %.cpp %.c，手写 .cc 不会被编译。
    #新增业务代码一律用 .cpp/.h，禁止新建 .cc 模拟 logic.cc。
    for _r2, _dirs2, _files2 in os.walk(src):
        for fn in _files2:
            if not fn.endswith('.cc'):
                continue
            full = os.path.join(_r2, fn)
            rel = os.path.relpath(full, root).replace('\\', '/')
            # IDE 生成规律：logic 目录下 xxxLogic.cc（mainLogic.cc 等，对应页面）
            if os.path.dirname(full).replace('\\', '/').endswith('/logic') \
                    and re.match(r'^\w*Logic\.cc$', fn):
                continue  # 合法 IDE 生成
            errors.append({'file': rel, 'type': 'manual_cc_file',
                           'msg': f'{rel} 是手写 .cc 文件：.cc 是 IDE 按页面生成的 logic 专属（xxxLogic.cc），'
                                  f'Makefile 只编译 %.cpp %.c，手写 .cc 不会被编译；新增业务代码请用 .cpp/.h'})

    # 1.5 IDE 工程文件（缺失则 IDE 打不开/无法编译）
    for ef, desc in (('.project', '.project 工程文件'), ('.cproject', '.cproject 工程配置'),
                     ('.settings', '.settings 工程属性目录')):
        if not os.path.exists(os.path.join(root, ef)):
            errors.append({'file': ef, 'type': 'missing_ide_file',
                           'msg': f'缺少 {desc}（IDE 必需，建议用 flythings_create_project 从模板创建）'})

    # 1.6 Manifest 格式（新格式 <manifest platform> vs 旧 <Manifest>）
    mf = os.path.join(root, 'Manifest.xml')
    if os.path.isfile(mf):
        try:
            mtext = open(mf, encoding='utf-8', errors='replace').read()
        except Exception:
            mtext = ''
        if '<manifest platform=' not in mtext:
            errors.append({'file': 'Manifest.xml', 'type': 'old_manifest_format',
                           'msg': 'Manifest 不是新格式 <manifest platform="...">（旧 <Manifest> 格式 IDE 无法解析）'})
    else:
        errors.append({'file': 'Manifest.xml', 'type': 'missing_file', 'msg': 'Manifest.xml 不存在'})

    # 1.7 uart 模板完整性（Main.cpp 引用 UartContext 则必须有）
    uart_dir = os.path.join(src, 'uart')
    main_cpp = os.path.join(src, 'Main.cpp')
    main_txt = ''
    if os.path.isfile(main_cpp):
        try:
            main_txt = open(main_cpp, encoding='utf-8', errors='replace').read()
        except Exception:
            main_txt = ''
    if 'UartContext' in main_txt or 'openUart' in main_txt:
        if not os.path.isdir(uart_dir):
            errors.append({'file': 'src/uart', 'type': 'missing_uart_dir',
                           'msg': 'Main.cpp 引用 UartContext 但 src/uart 目录缺失（模板自带，勿手写）'})
        else:
            for uf in ('UartContext.h', 'UartContext.cpp', 'ProtocolParser.h',
                       'ProtocolParser.cpp', 'ProtocolData.h', 'ProtocolSender.h',
                       'ProtocolSender.cpp', 'CommDef.h'):
                if not os.path.isfile(os.path.join(uart_dir, uf)):
                    warnings.append({'file': f'src/uart/{uf}', 'type': 'uart_missing_file',
                                     'msg': f'src/uart/{uf} 缺失（系统模板文件，建议从 IDE 模板补齐）'})

    # 1.8 三方库依赖检查（代码 include 了三方库但 Manifest 未声明 → error）
    #含框架基础依赖（v0.27.83）：base 头文件（含 fun 生成的 generated/*.h）→ Manifest 必须有 base-utility
    try:
        import package_tools as pkgtools
        dep = pkgtools.flythings_check_project_deps(root)
        if dep.get('success'):
            for md in dep.get('missingDependencies', []):
                if md.get('kind') == 'framework':
                    # 框架基础包：msg/hint 更具体（老工程高发，别只说「加依赖」）
                    errors.append({'file': 'Manifest.xml', 'type': 'missing_framework_dependency',
                                   'msg': md.get('msg'), 'hint': md.get('fix')})
                    continue
                errors.append({'file': 'Manifest.xml', 'type': 'missing_dependency',
                               'msg': f"代码 include 了 {md['include']} 但 Manifest 未声明对应 package"
                                      f"（推荐: {', '.join(md['recommendedPackages'])}）"})
    except Exception as e:
        warnings.append({'file': 'Manifest.xml', 'type': 'dep_check_failed',
                         'msg': f'三方库依赖检查未执行: {e}'})

    # 1.9 HTTPS 证书检查（curl/curl-cxx + https 调用必须打包 resources/cacert.pem，
    #否则 mbedtls 缺 CA 证书直接进程崩溃→看门狗重启，不报错）
    mtext = ''
    mf = os.path.join(root, 'Manifest.xml')
    if os.path.isfile(mf):
        try:
            mtext = open(mf, encoding='utf-8', errors='replace').read()
        except Exception:
            mtext = ''
    has_http_pkg = bool(re.search(r'<package\s+id="(?:curl|curl-cxx)"', mtext))
    if has_http_pkg:
        https_use = False
        src_dir = os.path.join(root, 'src')
        if os.path.isdir(src_dir):
            for base, _, files in os.walk(src_dir):
                for fn in files:
                    if not fn.endswith(('.cc', '.cpp', '.h', '.hpp')):
                        continue
                    try:
                        t = open(os.path.join(base, fn), encoding='utf-8', errors='replace').read()
                    except Exception:
                        continue
                    if re.search(r'https?://', t) and re.search(r'curl|CURL', t):
                        https_use = True
                        break
                if https_use:
                    break
        if https_use:
            cacert = os.path.join(root, 'resources', 'cacert.pem')
            if not os.path.isfile(cacert):
                errors.append({'file': 'resources/cacert.pem', 'type': 'missing_cacert',
                               'msg': '使用 curl/curl-cxx 请求 HTTPS 但 resources/cacert.pem 缺失：'
                                      'Z21 上 mbedtls 缺 CA 证书不会优雅报错，而是进程崩溃被看门狗反复拉起。'
                                      '必须从 curl 包或系统导出 cacert.pem 放入 resources/'})

    # 2. activity 目录（不应含用户业务代码特征）
    # ⚠️ 模板 mainActivity.cpp 本身含 REGISTER_ACTIVITY_TIMER_TAB 系统代码，不能用它做特征；
    #正确特征：用户代码是 .cc（被 include 进 activity.cpp），activity 目录只应存在 IDE 生成的 .cpp/.h
    act_dir = os.path.join(src, 'activity')
    if os.path.isdir(act_dir):
        for fn in sorted(os.listdir(act_dir)):
            if fn.endswith('.cc'):
                warnings.append({'file': f'src/activity/{fn}', 'type': 'illegal_code',
                                 'msg': 'activity 目录出现 .cc 文件，疑似添加了用户代码（禁止修改 activity 目录）'})
            elif fn.endswith(('.cpp', '.h')):
                p = os.path.join(act_dir, fn)
                try:
                    text = open(p, encoding='utf-8', errors='replace').read()
                except Exception:
                    continue
                # IDE 生成文件以 /gen auto by zuitools 开头；无此标记且含业务特征 → 疑似手改
                if '/gen auto by zuitools' not in text and (
                        'onButtonClick_' in text or 'REGISTER_ACTIVITY_TIMER_TAB[] =' in text
                        or 'onEditTextChanged_' in text):
                    warnings.append({'file': f'src/activity/{fn}', 'type': 'illegal_code',
                                     'msg': f'{fn} 无 IDE 生成标记但含业务代码特征，疑似手改（禁止修改 activity 目录）'})

    # 3. ui json/ftu 配对 + 时间戳校验（防改 json 忘 pack）
    if os.path.isdir(ui):
        ftus = {f for f in os.listdir(ui) if f.endswith('.ftu')}
        for fn in sorted(os.listdir(ui)):
            if fn.endswith('.json'):
                if fn[:-5] + '.ftu' not in ftus:
                    warnings.append({'file': f'ui/{fn}', 'type': 'not_packed',
                                     'msg': 'JSON 未打包为 ftu，请执行 fui pack（设备加载的是 ftu 不是 json）'})
        # json 比 ftu 新 → 改了 json 但没重新 pack
        ts = _ui_timestamp_check(root)
        for s in ts.get('stale', []):
            warnings.append({'file': f"ui/{s['json']}", 'type': 'stale_ftu',
                             'msg': f"{s['json']} 修改时间晚于 {s['ftu']}（改过 json 未重新 fui pack，"
                                    f"设备仍会运行旧版 ftu 布局）"})
        # ftu 比 json 新「分钟级」= 用户/IDE 直接编辑过 ftu（build_ui_flow 会自动 unpack 同步 json）
        for d in ts.get('devModified', []):
            if _fui_supports_unpack():
                msg = (f"{d['ftu']} 修改时间晚于 {d['json']} 分钟级（用户/IDE 编辑过 ftu；"
                       f"build_ui_flow 会先 fui unpack 同步 json 再继续，避免覆盖编辑）")
            else:
                msg = (f"{d['ftu']} 修改时间晚于 {d['json']} 分钟级（用户/IDE 编辑过 ftu；"
                       f"当前 fui.exe 不含 unpack，无法从 ftu 反解析——"
                       f"如需保留对 ftu 的编辑，请手动同步到 json，或换用支持 unpack 的 fui.exe）")
            warnings.append({'file': f"ui/{d['ftu']}", 'type': 'dev_modified_ftu', 'msg': msg})
        # 只有 ftu 没有同名 json（build_ui_flow 会自动转出 json）
        for f in ts.get('ftuOnly', []):
            warnings.append({'file': f"ui/{f}", 'type': 'ftu_without_json',
                             'msg': f"{f} 没有同名 json（纯 ftu 工程）；build_ui_flow 会自动 fui unpack 转出 json"})
    else:
        warnings.append({'file': 'ui', 'type': 'missing_dir', 'msg': 'ui 目录不存在'})

    # 4. Main.cpp 入口
    main_cpp = os.path.join(src, 'Main.cpp')
    if os.path.isfile(main_cpp):
        try:
            text = open(main_cpp, encoding='utf-8', errors='replace').read()
        except Exception:
            text = ''
        for entry in ('onEasyUIInit', 'onStartupApp'):
            if entry not in text:
                errors.append({'file': 'src/Main.cpp', 'type': 'missing_entry',
                               'msg': f'缺少 {entry} 入口'})
    else:
        errors.append({'file': 'src/Main.cpp', 'type': 'missing_file', 'msg': 'src/Main.cpp 不存在'})

    return {"success": True, "projectInfo": project_info, "needUserInput": need_user,
            "errors": errors, "warnings": warnings}


# ---------------- 工具 4: fui pack/unpack ----------------
def _count_controls(json_path):
    try:
        with open(json_path, encoding='utf-8-sig') as f:
            data = json.load(f)
        res = data.get('resolution', {})
        count = sum(1 for k, v in data.items() if isinstance(v, dict) and '__' in k)
        return count, f"{res.get('width')}x{res.get('height')}"
    except Exception:
        return 0, ''


def flythings_fui_pack(json_path):
    """将 json 布局打包为 ftu（在 json 所在目录执行 fui pack）。"""
    if not os.path.isfile(json_path):
        return {"success": False, "error": f"json 文件不存在: {json_path}"}
    d = os.path.dirname(os.path.abspath(json_path)) or '.'
    r = _run_fui('pack', d)
    base = os.path.splitext(os.path.basename(json_path))[0]
    ftu_path = os.path.join(d, base + '.ftu')
    count, res = _count_controls(json_path)
    return {"success": r['success'],
            "ftuPath": ftu_path if os.path.isfile(ftu_path) else None,
            "controlsCount": count, "resolution": res,
            "detail": (r.get('stderr') or r.get('stdout')) if not r['success'] else None}


def flythings_fui_unpack(ftu_path, output_json='', overwrite=True):
    """ftu 反解析回 json（fui unpack；随包 fui 自 v0.27.91 起支持）。

    ⚠️ 默认**覆盖**同目录同名 json（ftu 为真源）；要保留原 json 传 overwrite=False
    （写到 <name>.unpacked.json，已存在则追加序号），或用 output_json 指定路径。
返回 {"success", "ftuPath", "jsonPath", "overwritten", "controlsCount", "resolution"}。
    """
    if not os.path.isfile(ftu_path):
        return {"success": False, "error": f"ftu 文件不存在: {ftu_path}"}
    if not str(ftu_path).lower().endswith('.ftu'):
        return {"success": False, "error": f"不是 .ftu 文件: {ftu_path}（json 直接读，无需 unpack）"}
    if not _fui_supports_unpack():
        return {"success": False, "fuiUnpackSupported": False,
                "error": f"当前 fui.exe 不含 unpack，无法从 ftu 反解析（{FUI_EXE}）",
                "hint": "换用支持 unpack 的 fui.exe（随包 toolchain/fui.exe 自 v0.27.91 起已支持）"}
    d = os.path.dirname(os.path.abspath(ftu_path)) or '.'
    base = os.path.splitext(os.path.basename(ftu_path))[0]
    src_json = os.path.join(d, base + '.json')
    if output_json:
        target = os.path.abspath(output_json)
        _d = os.path.dirname(target)
        if _d and not os.path.isdir(_d):          # 显式目标：父目录不存在就建（失败要出声）
            try:
                os.makedirs(_d, exist_ok=True)
            except OSError as e:
                return {"success": False, "error": f"输出目录不可用: {_d}（{e}）"}
    elif overwrite:
        target = src_json                        # 默认：覆盖对应 json（ftu 为真源）
    else:
        target = os.path.join(d, base + '.unpacked.json')
        i = 2
        while os.path.isfile(target):  # 指定不覆盖时：连 .unpacked.json 都在就换序号
            target = os.path.join(d, f'{base}.unpacked{i}.json')
            i += 1
    try:
        r = subprocess.run([FUI_EXE, 'unpack', ftu_path, target],
                           capture_output=True, text=True, timeout=60,
                           stdin=subprocess.DEVNULL,
                           encoding='utf-8', errors='replace')
    except Exception as e:
        return {"success": False, "error": f"fui unpack 执行失败: {e}"}
    if r.returncode != 0 or not os.path.isfile(target):
        return {"success": False, "ftuPath": ftu_path, "jsonPath": None,
                "error": ((r.stderr or '') + (r.stdout or ''))[-300:] or 'fui unpack 失败'}
    count, res = _count_controls(target)
    return {"success": True, "ftuPath": ftu_path, "jsonPath": target,
            "overwritten": os.path.abspath(target) == os.path.abspath(src_json),
            "controlsCount": count, "resolution": res}



# ---------------- 工具 4.6: 静态层叠/遮挡审计（纯几何，0 token）----------------
# 2026-09-18：用户说「控件被盖住 / 点不到 / 位置不对」时，json 本身就能判定，
# 不要一上来就截图（截图贵且只能看视觉、看不出触摸被谁抢）。
_INTERACTIVE_TYPES = {
    'button', 'edittext', 'listview', 'seekbar', 'circlebar', 'checkbox', 'qrcode',
    'radiogroup', 'slidewindow', 'pagewindow', 'scrollwindow', 'videoview', 'diagram', 'pointer',
}


def _ctl_box(node):
    """控件盒 (l, t, r, b)；position 缺失/非正尺寸返回 None。"""
    p = node.get('position') if isinstance(node, dict) else None
    if not isinstance(p, dict):
        return None
    try:
        l, t = int(p.get('left', 0)), int(p.get('top', 0))
        w, h = int(p.get('width', 0)), int(p.get('height', 0))
    except (TypeError, ValueError):
        return None
    if w <= 0 or h <= 0:
        return None
    return (l, t, l + w, t + h)


def _box_intersect(a, b):
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


def _box_cover(a, b):
    return a[0] <= b[0] and a[1] <= b[1] and a[2] >= b[2] and a[3] >= b[3]


def _audit_page(name, data):
    """单页审计：返回 findings[]（纯几何判定，不猜）。"""
    findings = []
    pages = data.get('resolution') or {}
    try:
        RW, RH = int(pages.get('width') or 0), int(pages.get('height') or 0)
    except (TypeError, ValueError):
        RW = RH = 0
    groups = {}

    def walk(obj, path):
        if not isinstance(obj, dict):
            return
        for k, v in obj.items():
            if isinstance(v, dict) and '__' in k:
                groups.setdefault(path, []).append((k, v))
                walk(v, (path + '/' + k) if path else k)

    walk(data, '')
    for parent, children in groups.items():
        infos = []
        for order, (key, node) in enumerate(children):
            box = _ctl_box(node)
            ctype = key.split('__')[0]
            infos.append({
                'key': key, 'type': ctype, 'box': box, 'order': order,
                'visible': node.get('visible', True) is not False,
                'touchable': bool(node.get('touchable')),
                'touchPass': node.get('touchPass'),
                'interactive': ctype in _INTERACTIVE_TYPES,
                'children': [x for x in children if x[1] is node],
            })
        vis = [i for i in infos if i['visible'] and i['box']]
        for i, a in enumerate(vis):
            # 整屏层（盖子）——「点哪都没反应」头号嫌疑
            if RW and RH and a['touchable'] and a['box'] == (0, 0, RW, RH):
                # 只有「整屏 + touchable」才是问题：整屏 window 作为页面容器是正常写法
                findings.append({
                    'kind': 'fullscreen_layer', 'page': name, 'path': (parent + '/' + a['key']).strip('/'),
                    'why': ('整屏可点层 %s（%s）覆盖全屏且 touchable=true → 会吞掉整屏触摸'
                            % (a['key'], a['type'])),
                    'fix': ('隐藏页用 visible:false（不要整屏 touchable 层）；遮罩只覆盖需要拦截的区域；'
                            '装饰/容器要穿透：touchable:false + touchPass:true')})
            if not a['interactive'] or not a['touchable']:
                pass
            for b in vis:
                if a is b or not _box_intersect(a['box'], b['box']):
                    continue
                # 目标：b 是可交互控件，看谁挡它 / 抢它触摸
                if b['interactive'] and b['touchable']:
                    if a['order'] < b['order'] and a['touchable'] and _box_cover(a['box'], b['box']):
                        findings.append({
                            'kind': 'touch_steal', 'page': name,
                            'control': (parent + '/' + b['key']).strip('/'),
                            'by': (parent + '/' + a['key']).strip('/'),
                            'why': ('同层更早定义的 touchable 控件 %s（%s）完整覆盖 %s → 触摸按定义顺序先被它拿走（F133 实测：'
                                    '遮罩 button 压住卡片 window 时卡片内按钮点不动）'
                                    % (a['key'], a['type'], b['key'])),
                            'fix': '把遮挡物改 touchable:false + touchPass:true（要穿透），或让它定义为子级/移除'})
                    elif a['order'] > b['order'] and a['touchable'] and _box_cover(a['box'], b['box']):
                        findings.append({
                            'kind': 'covered_interactive', 'page': name,
                            'control': (parent + '/' + b['key']).strip('/'),
                            'by': (parent + '/' + a['key']).strip('/'),
                            'why': ('上层 touchable 控件 %s（%s）完整盖住可交互控件 %s → 视觉与触摸都被挡'
                                    % (a['key'], a['type'], b['key'])),
                            'fix': '调整 position（不要完全盖住）、缩小遮挡层、或把被盖控件 move 到可见区域'})
                    elif a['order'] < b['order'] and _box_intersect(a['box'], b['box']) and not a['touchable']:
                        if a['touchPass'] is not True:
                            findings.append({
                                'kind': 'pass_through_missing', 'page': name,
                                'control': (parent + '/' + a['key']).strip('/'),
                                'over': (parent + '/' + b['key']).strip('/'),
                                'why': ('装饰/容器 %s（%s）touchable:false 但没有 touchPass:true，与可交互控件 %s 重叠 → '
                                        '可能拦住下层触摸（铁律：装饰件要 touchable:false + touchPass:true）'
                                        % (a['key'], a['type'], b['key'])),
                                'fix': 'setTouchable(false) + setTouchPass(true)（json touchPass:true）'})
                elif a['order'] < b['order'] and _box_intersect(a['box'], b['box']):
                    findings.append({
                        'kind': 'overlap', 'page': name,
                        'control': (parent + '/' + a['key']).strip('/'),
                        'over': (parent + '/' + b['key']).strip('/'),
                        'why': ('同层 %s（%s）与 %s（%s）盒子相交（后者在上层：json 书写顺序=层叠顺序）'
                                % (a['key'], a['type'], b['key'], b['type'])),
                        'fix': '确认是否故意叠放；要穿透加 touchPass:true，要隐藏用 visible:false'})
    # 去重（同一对只报一次，按 kind+control+by）
    seen, uniq = set(), []
    for f in findings:
        sig = (f['kind'], f.get('control', ''), f.get('by') or f.get('over', ''))
        if sig in seen:
            continue
        seen.add(sig)
        uniq.append(f)
    return uniq


def flythings_layout_audit(project_root, page=''):
    """静态审计 ui/*.json 的层叠/遮挡/触摸穿透（纯几何，0 token）。

    ⚠️ 用户说「控件被盖住 / 点不到 / 位置不对 / 谁挡着谁」时**先调本 op**（json 就能判定），
不要一上来截图；只有需要确认视觉样式（颜色/字体/切图/锯齿）才用 device_screenshot + ui_diff。
返回 {pages:[{file, findings:[{kind, control, by, why, fix}]}], summary}。
    kind：fullscreen_layer 整屏层 / touch_steal 同层更早的 touchable 抢触摸 /
    covered_interactive 被上层可交互控件盖住 / pass_through_missing 缺 touchPass / overlap 盒子相交。
    """
    if not os.path.isdir(project_root):
        return {"success": False, "error": f"项目目录不存在: {project_root}"}
    ui_dir = os.path.join(project_root, 'ui')
    if not os.path.isdir(ui_dir):
        return {"success": False, "error": f"ui 目录不存在: {ui_dir}"}
    files = []
    for fn in sorted(os.listdir(ui_dir)):
        if fn.endswith('.json'):
            files.append(os.path.join(ui_dir, fn))
    for sub in sorted(os.listdir(ui_dir)):
        d = os.path.join(ui_dir, sub)
        if os.path.isdir(d):
            for fn in sorted(os.listdir(d)):
                if fn.endswith('.json'):
                    files.append(os.path.join(d, fn))
    if page:
        files = [f for f in files if page in os.path.basename(f) or page in f.replace('\\', '/')]
    pages, total = [], 0
    for fp in files:
        try:
            data = json.load(open(fp, encoding='utf-8-sig'))
        except Exception as e:
            pages.append({"file": os.path.relpath(fp, ui_dir).replace('\\', '/'), "error": str(e),
                          "findings": []})
            continue
        fs = _audit_page(os.path.relpath(fp, ui_dir).replace('\\', '/'), data)
        total += len(fs)
        pages.append({"file": os.path.relpath(fp, ui_dir).replace('\\', '/'), "findings": fs})
    if not pages:
        return {"success": True, "hint": "没有扫到 ui/*.json 布局", "pages": [], "summary": {"pages": 0, "findings": 0}}
    return {"success": True, "pages": pages,
            "summary": {"pages": len(pages), "findings": total},
            "note": '纯几何静态判定（z 序=json 书写顺序；同层更早的 touchable 先拿触摸）。'
                    '视觉样式（颜色/字体/切图）仍需 device_screenshot；改动前后对比用 ui_visual(action="diff")。'}


# ---------------- 工具 4.5: 创建可执行程序项目 (fun create --type bin) -------------
def _is_elf(path):
    """检测文件是否为 ELF 可执行文件（魔数 \x7fELF）。"""
    try:
        with open(path, 'rb') as f:
            return f.read(4) == b'\x7fELF'
    except Exception:
        return False


def flythings_create_bin_project(project_root, project_name='',
                                 platform=_platforms.DEFAULT_BIN_PLATFORM,
                                 app_version='1.0.0', description='', with_build=True):
    """创建「可执行程序」类型项目（fun create --type bin）并编译为直接可运行的 ELF 二进制。

    - 项目类型 4 选 1：zkgui（UI应用）/ bin（可执行程序）/ staticLibrary / sharedLibrary
    - bin 项目结构极简：fun.json（"type": "executable"）+ src/main.cpp（标准 int main()）
    - 编译：fun build → 产物 .fsc/{platform}/{项目名}（09-28 前为 .fun/），ELF 魔数验证
    - 部署：adb push + chmod +x 直接跑（无 zkgui 宿主，不能启动 UI 应用）
    - 非交互：自动传 --app-version/--description 跳过向导；目录非空直接报错（防覆盖询问卡死）

传入项目根目录（可不存在，自动创建）、平台（默认同 `platforms.DEFAULT_BIN_PLATFORM`；
大小写不敏感，别名可归一，未知平台会报错并列出支持项）、项目名（缺省取目录名）。
返回创建结果 + 编译日志 + 产物路径与 ELF 验证。
    """
    try:
        # 出口统一小写（fun.exe / 产物目录 <小写平台> 的既有约定；09-28 起为 .fsc/<小写平台>/，旧版 .fun/）
        platform = _platforms.bin_tool_dir(platform or _platforms.DEFAULT_BIN_PLATFORM)
    except ValueError as e:
        return {"success": False, "error": str(e)}
    root = os.path.abspath(project_root)
    name = (project_name or os.path.basename(root)).strip()
    if not re.match(r'^[A-Za-z][A-Za-z0-9_]*$', name):
        return {"success": False,
                "error": f"项目名不合法: {name!r}（应字母开头，仅字母/数字/下划线）"}
    if os.path.isdir(root) and os.listdir(root):
        return {"success": False,
                "error": f"目录非空: {root}（bin 项目需在空目录创建，防止覆盖询问卡死）"}
    os.makedirs(root, exist_ok=True)
    # 1. 创建（非交互：显式传 app-version/description 跳过向导）
    args = [FUN_EXE, 'create', '--name', name, '--platform', platform,
            '--type', 'bin', '--app-version', app_version or '1.0.0']
    if description:
        args += ['--description', description]
    args += ['.']
    try:
        r = subprocess.run(args, cwd=root, capture_output=True, text=True, timeout=120,
                           stdin=subprocess.DEVNULL,  # ⚠️ 防继承 MCP stdio 管道挂起
                           encoding='utf-8', errors='replace')
    except Exception as e:
        return {"success": False, "error": f"fun create 执行失败: {e}"}
    create_ok = r.returncode == 0
    create_log = ((r.stdout or '') + (r.stderr or ''))[-600:]
    result = {"success": create_ok, "projectRoot": root, "name": name,
              "platform": platform, "type": "bin", "createLog": create_log}
    if not create_ok:
        result["error"] = f"fun create 失败(rc={r.returncode}): {create_log}"
        return result
    # 2. 编译
    if with_build:
        rb = subprocess.run([FUN_EXE, 'build'], cwd=root, capture_output=True, text=True,
                            timeout=600, stdin=subprocess.DEVNULL,
                            encoding='utf-8', errors='replace')
        build_ok = rb.returncode == 0
        result["buildSuccess"] = build_ok
        result["buildLog"] = ((rb.stdout or '') + (rb.stderr or ''))[-800:]
        if not build_ok:
            result["error"] = f"fun build 失败(rc={rb.returncode}): {result['buildLog']}"
            return result
    # 3. 产物定位 + ELF 验证
    out = _find_build_artifact(root, platform, name)
    exists = os.path.isfile(out)
    result.update({
        "outputPath": out if exists else None,
        "outputSize": os.path.getsize(out) if exists else 0,
        "isElfExecutable": _is_elf(out) if exists else False,
        "deployHint": f"adb push {out} /tmp/ && adb shell chmod +x /tmp/{name} && adb shell /tmp/{name}",
    })
    return result


# ---------------- 工具 5: 附带 CLI 工具到项目 -------------
def flythings_attach_cli_tools(project_root):
    """将 fui.exe（→ui/）和 fun.exe（→项目根）复制到新建项目目录，随项目分发给用户。
传入项目根目录完整路径。返回复制结果。
    ⚠️ 交付流程：fun.exe 用于 build 编译 + launch 推送，无需客户手动导入 IDE。"""
    if not os.path.isdir(project_root):
        return {"success": False, "error": f"项目目录不存在: {project_root}"}
    results = []
    # fui.exe → ui/ 目录（pack/unpack 在 ui 目录执行）
    ui_dir = os.path.join(project_root, 'ui')
    if os.path.isdir(ui_dir):
        dst = os.path.join(ui_dir, 'fui.exe')
        try:
            shutil.copy2(FUI_EXE, dst)
            results.append({"file": "ui/fui.exe", "size": os.path.getsize(dst), "status": "copied"})
        except Exception as e:
            results.append({"file": "ui/fui.exe", "status": "failed", "error": str(e)})
    else:
        results.append({"file": "ui/fui.exe", "status": "skipped", "reason": "ui 目录不存在"})
    # fun.exe → 项目根目录（build 编译 + launch 推送）
    dst = os.path.join(project_root, 'fun.exe')
    try:
        shutil.copy2(FUN_EXE, dst)
        results.append({"file": "fun.exe", "size": os.path.getsize(dst), "status": "copied"})
    except Exception as e:
        results.append({"file": "fun.exe", "status": "failed", "error": str(e)})
    ok = all(r.get('status') in ('copied', 'skipped') for r in results)
    return {"success": ok, "projectRoot": project_root, "files": results}


# ---------------- 工具 4.6: 编辑 json/ftu 布局 ----------------
def _find_control(data, target):
    """按 caption（优先）或控件 key 查找控件。返回 (key, value)。
递归进入嵌套容器（window 里的子控件），否则嵌套 caption 永远「未找到」。"""
    for key, val in data.items():
        if not isinstance(val, dict) or '__' not in key:
            continue
        if val.get('caption') == target or key == target:
            return key, val
    for key, val in data.items():
        if not isinstance(val, dict) or '__' not in key:
            continue
        sub_key, sub_val = _find_control(val, target)
        if sub_val is not None:
            return sub_key, sub_val
    return None, None


def _find_parent(data, key):
    """返回包含指定控件 key 的父 dict（递归），找不到返回 None。供嵌套 remove 用。"""
    if key in data:
        return data
    for k, val in data.items():
        if isinstance(val, dict) and '__' in k:
            p = _find_parent(val, key)
            if p is not None:
                return p
    return None


def _apply_edits(data, ops):
    """应用编辑操作到 json 布局。ops 为操作列表。返回 (success, report)。
支持操作：
      set      {"op":"set", "target":"caption或key", "props":{...}}修改控件属性
      remove   {"op":"remove", "target":"caption或key"}删除控件
      add      {"op":"add", "template":"caption或key", "newKey":"textview__4", "props":{...}}复制模板控件新增并改属性
      set_root {"op":"set_root", "props":{"backgroundColor":"#FFFFFF"}}修改根属性（resolution/position/backgroundColor 等）
    """
    report = []
    failures = 0
    for op in ops:
        if not isinstance(op, dict):
            report.append(f'[跳过] 非法操作: {op}')
            failures += 1
            continue
        kind = op.get('op')
        if kind == 'set':
            key, val = _find_control(data, op.get('target', ''))
            if val is None:
                report.append(f'[失败] 未找到控件: {op.get("target")}')
                failures += 1
                continue
            props = op.get('props') or {}
            changed = [p for p in props if val.get(p) != props[p]]
            val.update(props)
            report.append(f'[OK] 修改 {key}: {changed if changed else "无变化"}')
        elif kind == 'remove':
            key, _ = _find_control(data, op.get('target', ''))
            if key is None:
                report.append(f'[失败] 未找到控件: {op.get("target")}')
                failures += 1
                continue
            parent = _find_parent(data, key)
            (parent if parent is not None else data).pop(key, None)
            report.append(f'[OK] 删除 {key}')
        elif kind == 'add':
            tkey, tval = _find_control(data, op.get('template', ''))
            if tval is None:
                report.append(f'[失败] 模板控件不存在: {op.get("template")}')
                failures += 1
                continue
            new_key = op.get('newKey', '')
            if not new_key:
                report.append('[失败] 缺少 newKey')
                failures += 1
                continue
            if new_key in data:
                report.append(f'[失败] key 已存在: {new_key}')
                failures += 1
                continue
            import copy as _copy
            new_val = _copy.deepcopy(tval)
            new_val.update(op.get('props') or {})
            data[new_key] = new_val
            report.append(f'[OK] 新增 {new_key}（基于 {tkey}）')
        elif kind == 'set_root':
            props = op.get('props') or {}
            changed = [p for p in props if data.get(p) != props[p]]
            data.update(props)
            report.append(f'[OK] 修改根节点: {changed if changed else "无变化"}')
        else:
            report.append(f'[跳过] 未知操作: {kind}')
            failures += 1
    return failures == 0, report


def _edit_json(json_path, operations):
    """编辑 json 布局文件（控件属性/增删/根属性），保存回原文件。
    operations 为 JSON 数组字符串，如：
    [{"op":"set","target":"按钮标题","props":{"x":100,"y":200,"text":"新文本"}}]
返回编辑报告。改完 json 后需 fui pack 生成 ftu（或直接编辑 ftu 用 flythings_edit_ftu）。"""
    if not os.path.isfile(json_path):
        return {"success": False, "error": f"json 文件不存在: {json_path}"}
    if isinstance(operations, str):
        try:
            ops = json.loads(operations)
        except Exception as e:
            return {"success": False, "error": f"operations 不是合法 JSON: {e}"}
    else:
        ops = operations or []
    try:
        with open(json_path, encoding='utf-8-sig') as f:
            data = json.load(f)
    except Exception as e:
        return {"success": False, "error": f"json 解析失败: {e}"}
    ok, report = _apply_edits(data, ops)
    bak = json_path + '.bak'
    try:
        shutil.copy2(json_path, bak)  # v0.27.31：写回前先备份 json，失败则不写入
    except Exception as e:
        return {"success": False, "error": f"json 备份失败（未写入任何修改）: {e}"}
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return {"success": ok, "jsonPath": json_path, "jsonBackup": bak, "report": report,
            "controlsCount": sum(1 for k, v in data.items() if isinstance(v, dict) and '__' in k)}


def flythings_edit_ftu(ftu_path, operations, output_ftu='', overwrite=False):
    """编辑 ftu 布局：自动应用编辑到 json 后 pack 回 ftu。
    ⚠️ 默认不覆盖原 ftu（overwrite=False）：pack 产物落到 <name>.edited.ftu，原 ftu 原样还原；
确认效果后再传 overwrite=True 覆盖原 ftu（或 output_ftu 指定目标）。原 ftu 与 json 都留 .bak。
    operations 为 JSON 数组字符串，支持 set/remove/add/set_root（见 _apply_edits）。
    ⚠️ 布局以 json 为源：同目录已有 json 就直接改它再 pack 回 ftu；**没有 json 时按能力自动 unpack**
    （fui 含 unpack 时从 ftu 反解析出 json 再改；旧版 fui 无 unpack 才报错）。
客户说「把这个按钮往右移/改文本/换颜色/删掉某控件/复制一个控件」时调用。"""
    if not os.path.isfile(ftu_path):
        return {"success": False, "error": f"ftu 文件不存在: {ftu_path}"}
    src_dir = os.path.dirname(os.path.abspath(ftu_path)) or '.'
    base = os.path.splitext(os.path.basename(ftu_path))[0]
    json_path = os.path.join(src_dir, base + '.json')
    unpacked_source = False
    if not os.path.isfile(json_path):
        if not _fui_supports_unpack():
            return {"success": False,
                    "error": f"缺少同目录 {base}.json（布局以 json 为源，请先提供 json 布局再编辑）"}
        # v0.27.91：随包 fui 含 unpack → 从 ftu 反解析出 json 当编辑源（ftu 为真源）
        u = flythings_fui_unpack(ftu_path, json_path, overwrite=True)
        if not u.get('success'):
            return {"success": False,
                    "error": f"缺少 {base}.json 且 fui unpack 反解析失败: {u.get('error')}"}
        unpacked_source = True
    orig_ftu = os.path.abspath(ftu_path)
    ftu_bak = orig_ftu + '.bak'
    try:
        shutil.copy2(orig_ftu, ftu_bak)  # 无论是否覆盖都先备份原 ftu（可回滚）
    except Exception as e:
        return {"success": False, "error": f"原 ftu 备份失败（未做任何修改）: {e}"}
    ed = _edit_json(json_path, operations)
    if not ed['success']:
        return ed
    r = _run_fui('pack', src_dir)
    if not r['success']:
        return {"success": False, "error": f"fui pack 失败: {r.get('stderr') or r.get('stdout')}",
                "report": ed['report']}
    packed = os.path.join(src_dir, base + '.ftu')
    if output_ftu:
        target = os.path.abspath(output_ftu)
    elif overwrite:
        target = orig_ftu
    else:
        target = os.path.join(src_dir, base + '.edited.ftu')
    if os.path.abspath(packed) != target:
        shutil.copy2(packed, target)
    overwrote = bool(overwrite) and target == orig_ftu
    if not overwrote:
        # pack 已把原 ftu 覆盖，这里还原，保证「默认不覆盖」真的成立
        shutil.copy2(ftu_bak, orig_ftu)
    return {"success": True, "ftuPath": target, "overwriteOriginal": overwrote,
            "backup": ftu_bak, "jsonPath": json_path, "jsonBackup": ed.get('jsonBackup'),
            "unpackedSource": unpacked_source,
            "report": ed['report'], "controlsCount": ed.get('controlsCount'), "syncedJson": True,
            "hint": (f"已覆盖原 ftu（备份 {os.path.basename(ftu_bak)}，回滚=拷回该文件）" if overwrote
                     else f"默认不覆盖原 ftu：修改结果在 {os.path.basename(target)}；"
                          f"确认无误后传 overwrite=True 覆盖原文件")}


# ---------------- 工具 6: UI 构建流程（pack → build → launch）----------------
# ---- 设备门（v0.27.84）：决定「往哪台设备推」，不猜 -------------------------
def _devices_brief(devs):
    """给返回体用的设备列表（serial + model + 平台匹配情况，不泄漏 IP 以外信息）。"""
    return [{'serial': d.get('serial'), 'model': d.get('model') or '',
             'platform': d.get('platform') or '',
             'platformConfidence': d.get('modelConfidence') or 'unknown',
             'state': d.get('state') or 'device'} for d in (devs or [])]


def _launch_gate(platform, device):
    """设备探测 + 选机决策（0 台 / 多台 / 恰好 1 台，多台**不猜**）。
返回 {'needDeviceInput','serial','model','platformMatch','installHint','message',
         'devices','offline','adb','adbSource','explicit','connectNote'}
    """
    g = {'needDeviceInput': False, 'serial': '', 'model': '', 'platformMatch': '',
         'installHint': '', 'message': '', 'devices': [], 'offline': [],
         'adb': '', 'adbSource': '', 'explicit': bool(device),
         'connectNote': '', 'count': 0}
    if _adb is None:
        g['needDeviceInput'] = True
        g['message'] = 'adb 子系统不可用（adb_tools 导入失败：%s）' % _ADB_ERR
        g['installHint'] = ('把本包的 adb_tools.py 恢复（或设环境变量 ADB 指向 adb），'
                            '再重试；adb 不可用时也可用 flythings_device_screenshot 先看设备是否可达。')
        return g

    def _probe():
        try:
            return _adb.probe_devices()
        except Exception as e:                     # 探测自身出错不抛给上层
            return {'ok': False, 'error': '设备探测异常: %r' % e, 'online': [], 'offline': [],
                    'adb': '', 'adbSource': '', 'adbVersion': '', 'count': 0}

    pr = _probe()
    g['adb'] = pr.get('adb') or ''
    g['adbSource'] = pr.get('adbSource') or ''
    # 网络接入：用户给了 <ip>:5555 但不在列表里 → 先 connect 一次再探
    if device and ':' in str(device) and not any(d.get('serial') == device for d in pr.get('online') or []):
        try:
            ok, txt = _adb.connect(device)
            g['connectNote'] = 'adb connect %s → %s' % (device, txt or ('ok' if ok else 'failed'))
            if ok:
                pr = _probe()
        except Exception as e:
            g['connectNote'] = 'adb connect %s 异常: %r' % (device, e)
    online = list(pr.get('online') or [])
    g['devices'] = online
    g['count'] = len(online)
    g['offline'] = list(pr.get('offline') or [])

    if not pr.get('ok'):
        g['needDeviceInput'] = True
        g['message'] = '设备探测失败：%s' % (pr.get('error') or '未知原因')
        g['installHint'] = _adb.install_hint(platform, g['offline'], pr.get('error') or '')
        return g

    chosen = None
    if device:
        hit = [d for d in online if d.get('serial') == str(device)]
        if not hit:
            g['needDeviceInput'] = True
            g['message'] = ('指定设备 %r 不在 adb 在线列表（当前在线：%s）；'
                            '网络设备请确认已 adb connect，USB 设备请确认已插好并授权。'
                            % (device, [d.get('serial') for d in online] or '无'))
            g['installHint'] = _adb.install_hint(platform, g['offline'] + online)
            return g
        chosen = hit[0]
    else:
        if not online:
            g['needDeviceInput'] = True
            g['message'] = '未检测到可用的 FlyThings 设备（adb devices 里没有 state=device 的机器）'
            g['installHint'] = _adb.install_hint(platform, g['offline'])
            return g
        if len(online) > 1:
            g['needDeviceInput'] = True
            g['message'] = ('检测到 %d 台在线设备：**不自动选择**（fun 在多设备下静默取列表第一个 → 可能推错设备）。'
                            '请显式传 device=\'<serial|IP>\' 重试。' % len(online))
            g['installHint'] = _adb.multi_device_hint(online, platform)
            return g
        chosen = online[0]

    g['serial'] = chosen.get('serial') or ''
    g['model'] = chosen.get('model') or ''
    g['platformMatch'] = _adb.match_platform(g['model'], platform)
    if g['platformMatch'] == 'mismatch' and not g['explicit']:
        g['needDeviceInput'] = True
        g['message'] = ('唯一在线设备 %s（model=%s）与工程平台 %s **不一致**：'
                        'fun launch 会直接 FATAL platform not match。'
                        '确认要推这台就显式传 device=\'%s\'（显式指定=你知情）'
                        % (g['serial'], g['model'] or '未知', platform or '?', g['serial']))
        g['installHint'] = _adb.install_hint(platform, online)
        return g
    return g


def _device_sync_check(project_root, serial, platform):
    """本地 vs 设备侧（/tmp）ftu / so 的字节与 md5 —— 判定 staleOnDevice。

设备侧路径来自 fun launch 的部署约定：UI 资源 → `/tmp/ui/`，库 → `/tmp/lib/`。
返回 {'checked':bool,'ftu':[...],'so':[...],'stale':[...],'allMatch':bool,'reason':''}
    """
    out = {'checked': False, 'ftu': [], 'so': [], 'stale': [], 'allMatch': False, 'reason': ''}
    if _adb is None or not serial:
        out['reason'] = 'adb 子系统不可用' if _adb is None else '无设备'
        return out
    ui_dir = os.path.join(project_root, 'ui')
    names = []
    if os.path.isdir(ui_dir):
        names = sorted(f for f in os.listdir(ui_dir) if f.lower().endswith('.ftu'))
    truncated = names[8:]
    for f in names[:8]:
        c = _adb.compare_with_device('', serial, os.path.join(ui_dir, f), '/tmp/ui/' + f,
                                     platform=platform)
        c['name'] = f
        c['kind'] = 'ftu'
        out['ftu'].append(c)
    key = _platforms.package_key(platform or '') if platform else ''
    so_local = _find_build_artifact(project_root, key, 'libzkgui.so') if key else ''
    if so_local and os.path.isfile(so_local):
        c = _adb.compare_with_device('', serial, so_local, '/tmp/lib/libzkgui.so',
                                     platform=platform)
        c['name'] = 'libzkgui.so'
        c['kind'] = 'so'
        out['so'].append(c)
    out['checked'] = True
    if truncated:
        out['truncated'] = truncated
    items = out['ftu'] + out['so']
    out['stale'] = [c for c in items if not c.get('same')]
    out['allMatch'] = bool(items) and not out['stale']
    if not items:
        out['reason'] = '本地没有可比对的 ftu/so（ui/*.ftu 为空？）'
    return out


def read_resolution(path):
    """从工程目录读屏幕分辨率 → 'WxH' 或 ''（**唯一实现**，别再写第二套）。

    顺序：`.settings/*.prefs` 的 `resolution=` → `ui/*.json` 的 `resolution` 字段。
    `_detect_project_info` 与 `translate_tools`（迁移基准屏缺省跟随工程）都用它。
    """
    if not path or not os.path.isdir(path):
        return ''
    _read_errors = []          # 读失败的文件（此处只作说明用，不阻断取分辨率）
    st = os.path.join(path, '.settings')
    if os.path.isdir(st):
        for fn in sorted(os.listdir(st)):
            if not fn.endswith('.prefs'):
                continue
            try:
                with open(os.path.join(st, fn), encoding='utf-8', errors='replace') as fh:
                    txt = fh.read()
            except OSError as e:
                # 读不了 = 这个文件给不出分辨率（不是错），继续看下一个；不静默跳过而不说明
                txt = ''
                _read_errors.append('%s（%s）' % (fn, type(e).__name__))
            m = re.search(r'(?m)^resolution=(\d{2,5})x(\d{2,5})\s*$', txt)
            if m:
                return '%sx%s' % (m.group(1), m.group(2))
    ui = os.path.join(path, 'ui')
    if os.path.isdir(ui):
        for fn in sorted(os.listdir(ui)):
            if not fn.endswith('.json'):
                continue
            try:
                with open(os.path.join(ui, fn), encoding='utf-8', errors='replace') as fh:
                    d = json.loads(fh.read())
            except Exception:
                continue
            r = d.get('resolution') or {}
            if r.get('width') and r.get('height'):
                return '%sx%s' % (r['width'], r['height'])
    return ''


def _project_easyui_revision(root):
    """工程**解析到**的 easyui 版本 → (version, source)。

    来源是工具生成物（非手写）：`.fsc-lock.json`（09-28 起）/ `.fun-lock.json`（旧名）/ `.deps.lock`。
    取 `id=easyui` 那条的 `revision` —— Manifest 里写的是**范围**（如 `^2.2.0`），真版本在锁文件里
    （见 knowledge/devflow/easyui-version-capability.md）。拿不到回 ('', '')，不猜。
    """
    for name in ('.fsc-lock.json', '.fun-lock.json'):
        fp = os.path.join(root, name)
        if not os.path.isfile(fp):
            continue
        try:
            with open(fp, encoding='utf-8', errors='replace') as fh:
                data = json.loads(fh.read())
        except Exception:
            continue
        for _plat, items in (data.get('dependencies') or {}).items():
            if isinstance(items, dict) and isinstance(items.get('easyui'), dict):
                rev = items['easyui'].get('revision') or items['easyui'].get('version')
                if rev:
                    return str(rev), name
    dp = os.path.join(root, '.deps.lock')
    if os.path.isfile(dp):
        try:
            with open(dp, encoding='utf-8', errors='replace') as fh:
                txt = fh.read()
        except OSError:
            txt = ''
        m = re.search(r'"id"\s*:\s*"easyui".*?"revision"\s*:\s*"([^"]+)"', txt, re.S)
        if m:
            return m.group(1), '.deps.lock'
    mf = os.path.join(root, 'Manifest.xml')
    if os.path.isfile(mf):
        try:
            with open(mf, encoding='utf-8', errors='replace') as fh:
                txt = fh.read()
        except OSError:
            txt = ''
        m = re.search(r'<package\s+id="easyui"\s+version="([^"]+)"', txt)
        if m:
            return m.group(1), 'Manifest.xml(范围,非真版本)'
    return '', ''


def _device_runtime_pre_launch(serial, platform, project_info, root):
    """launch **前**的设备侧核对 → {'step','warnings'}（任务 7 + 8）。

    ① easyui 同源对账：工程解析到的 easyui 版本 vs **设备固件**的 `ro.easyui.version`。
       编译期版本 ≠ 设备运行库版本（控件由运行库提供）；不一致时 AI 判「某控件存在」会判错。
    ② 面板分辨率核对：工程分辨率 vs 设备面板（fb 可见宽 + 硬件层目标）→ 480×480 灰窗事件防线。
    """
    out = {'step': None, 'warnings': [], 'easyui': None, 'panel': None}
    if _dprobe is None or not serial:
        return out
    easyui = {}
    panel = {}
    try:
        easyui = _dprobe.easyui_runtime(serial, platform)
    except Exception as e:
        easyui = {'error': '%s: %s' % (type(e).__name__, e)}
    try:
        panel = _dprobe.panel_info(serial)
        hw = _dprobe.hw_panel_target(serial, panel.get('visibleWidth'))
        if hw.get('resolution'):
            panel['panelResolution'] = hw['resolution']
            panel['hwTarget'] = hw.get('raw')
    except Exception as e:
        panel = {'error': '%s: %s' % (type(e).__name__, e)}
    out['easyui'] = easyui
    out['panel'] = panel

    # ① easyui 对账
    local_rev, local_src = _project_easyui_revision(root)
    fw = (easyui or {}).get('firmwareVersion') or ''
    if fw and local_rev:
        lv, fv = local_rev.lstrip('^~>=<v '), fw.strip()
        if lv.split('.')[0] != fv.split('.')[0]:
            out['warnings'].append(
                '⚠️ easyui 版本不同源：工程解析到 %s（%s），而**设备固件**里是 %s —— '
                '控件由设备运行库提供，主版本不一致时「某控件在不在」的判定会错'
                '（见 knowledge/devflow/easyui-version-capability.md；'
                'launch 推的是 app 侧库，不会改设备固件里的 easyui）'
                % (local_rev, local_src or '来源未知', fw))
    # ② 面板分辨率核对
    proj_res = (project_info or {}).get('resolution') or ''
    panel_res = (panel or {}).get('panelResolution') or ''
    if not panel_res and (panel or {}).get('visibleWidth'):
        panel_res = '%sx?' % panel['visibleWidth']
    if proj_res and panel_res and not panel_res.endswith('x?'):
        pw, ph = (panel_res.split('x') + ['', ''])[:2]
        jw, jh = (proj_res.split('x') + ['', ''])[:2]
        rotated = (jw, jh) == (ph, pw)          # 竖屏/横屏旋转是正常的
        if (jw, jh) != (pw, ph) and not rotated:
            out['warnings'].append(
                '⚠️ 工程分辨率 %s 与设备面板 %s 不一致（面板来源：%s）——'
                '尺寸不符会出现灰窗/黑屏或布局错位；确认是刻意适配再继续'
                % (proj_res, panel_res,
                   'fb 可见宽 + ' + ((panel or {}).get('hwTarget') or '硬件层目标')
                   if (panel or {}).get('hwTarget') else 'fb 可见宽'))
    elif proj_res and panel_res.endswith('x?'):
        out['warnings'].append(
            '设备面板宽度是 %s，与工程分辨率 %s 的宽不同 —— 面板高度没能自动判定，请人工核对'
            % (panel_res[:-1], proj_res))
    return out


def _device_cfg_paths(serial):
    """launch **后**核对设备 EasyUI.cfg 里的资源目录是否真的存在 → {'cfg','missing','paths'}。

    `resPath` / `languagePath` / `font` 任一路径不存在 → 界面走 fallback（缺字/英文/空图），
    而这类问题只看 logcat 是不报错的。历史坑：`/tmp/tr 不存在`（i18n 目录没推上去）。
    """
    out = {'cfg': '', 'missing': [], 'paths': {}}
    if _dprobe is None or not serial:
        return out
    bb = _dprobe.busybox(serial) or 'busybox'
    for cand in ('/tmp/EasyUI.cfg', '/res/etc/EasyUI.cfg', '/mnt/extsd/EasyUI.cfg'):
        txt = _dprobe.sh(serial, 'cat %s 2>/dev/null' % cand, timeout=10)
        if txt and '{' in txt:
            out['cfg'] = cand
            break
    if not out['cfg']:
        return out
    for key in ('resPath', 'languagePath', 'font'):
        m = re.search(r'"%s"\s*:\s*"([^"]+)"' % key, txt)
        if not m:
            continue
        path = m.group(1)
        out['paths'][key] = path
        check = ('test -d %s' % path) if not path.lower().endswith(('.ttf', '.ttc')) \
            else ('test -f %s' % path)
        got = _dprobe.sh(serial, '%s %s && echo __yes__' % (bb, check), timeout=8)
        if '__yes__' not in (got or ''):
            out['missing'].append('%s=%s' % (key, path))
    return out


def _launch_liveness(serial):
    """launch **后**验「界面真的起来了」→ {'verdict','evidence','liveness','detail'}（任务 5）。

    verdict：
      `confirmed`  —— 看到强证据（`registerActivity name:` / `onUI_show` / `onUI_init`），
                      或弱证据 + GUI 进程活着
      `suspicious` —— 只看到弱证据/什么都没有，且 GUI 进程**不在**或卡在 D 状态
                      → 这就是黑屏事件同型（推送成功但界面没起来）
      `unknown`    —— logcat 或进程表都拿不到（**不要据此断言**）
    """
    out = {'verdict': 'unknown', 'evidence': None, 'liveness': None, 'detail': ''}
    if _dprobe is None or not serial:
        out['detail'] = '设备探针不可用'
        return out
    ev = {}
    lv = {}
    try:
        ev = _dprobe.launch_evidence(serial, wait=6)
    except Exception as e:
        ev = {'tier': 'none', 'error': '%s: %s' % (type(e).__name__, e)}
    try:
        lv = _dprobe.gui_liveness(serial)
    except Exception as e:
        lv = {'verdict': 'unknown', 'error': '%s: %s' % (type(e).__name__, e)}
    out['evidence'] = ev
    out['liveness'] = lv
    tier = ev.get('tier') or 'none'
    gui = lv.get('verdict') or 'unknown'
    if tier == 'strong' or (tier == 'weak' and gui == 'alive'):
        out['verdict'] = 'confirmed'
        out['detail'] = 'logcat 见「%s」（%s），GUI 进程 %s' % (
            ev.get('marker') or '?', ev.get('line') or '?', gui)
    elif gui in ('absent', 'blocked'):
        out['verdict'] = 'suspicious'
        out['detail'] = '%s；logcat 证据=%s' % (lv.get('detail') or '', tier)
    else:
        out['detail'] = '证据不足（logcat tier=%s，GUI=%s）' % (tier, gui)
    return out


def flythings_build_ui_flow(project_root, with_launch=True, device='',
                           font_check='auto', font_tier=''):
    """FlyThings UI 构建流程（关键步骤，不可跳过）：
    ① 检查 ui/*.json 与 *.ftu 修改时间一致性
       - json 比 ftu 新 = 改过 json 没重新打包
       - ftu 比 json 新「分钟级」(≥60 秒) = 开发者/IDE 直接改过 ftu → 先 unpack 同步 json 再继续
    ② 有改动才 fui pack <ui目录>（设备实际加载的是 FTU 而非 JSON）
    ③ fun install 同步 Manifest 依赖（每次 build 前执行，Manifest 变更自动拉取新依赖）
       ⚠️ install 失败**不阻断**（离线/依赖已装场景），但会在返回体顶层给 `warnings` 明说原因
    ③.5 框架基础依赖体检（v0.27.83）：Manifest 未声明且未解析到 base-utility 时，在返回体点明
       「依赖未装/缺包」（fun 生成的 generated/*.h 固定 #include <base/functional.h>），
不把 ninja 的 fatal error 丢给用户；能解析则不加任何 step/warning（正常路径零噪音）
    ③.6 字体体检（v0.27.86）：扫设备字体（连不上退化工程侧 self-scan），缺中文**默认自动投递**
       common 档思源黑体进工程 font/；font_check='off' 关，font_tier='full'/'multi' 换版；
细节见 knowledge/devflow/custom-font-config.md §0.2
    ④ fun build 编译 C++ 代码
    ⑤ 设备探测（adb devices -l + getprop 型号）→ fun launch 推送并运行
       —— **v0.27.84 起默认执行（with_launch=True）**，传 with_launch=False 可跳过（只编译不碰设备）。
探测规则（不猜）：0 台 → needDeviceInput + installHint；多台 → 列 serial/model + 平台匹配，
要求显式 device=；恰好 1 台且平台匹配 → 自动 launch。
返回体写清 launched/pushed/device/model/platformMatch，并比对设备侧 /tmp/ui/*.ftu 与
       /tmp/lib/libzkgui.so 的字节+md5 → staleOnDevice=true 时明说「设备上跑的还是旧版」。
    ⚠️ 失败时 needDeviceInput=true + installHint，必须询问接入方式：
       1) USB：先确认装好 ADB 驱动、设备开 USB 调试并授权；2) 网络：用户给 IP 后用 device='<ip>:5555' 重试。
禁止替用户猜测 IP。
    ⚠️ 常见错误：修改 JSON 后直接 launch 忘记 pack，设备上仍运行旧版 FTU 布局；
开发者改过 ftu 时若直接改 json 会覆盖其修改（必须先 unpack ftu 同步）。
传入项目根目录完整路径。返回每步结果与最终时间戳校验。"""
    if not os.path.isdir(project_root):
        return {"success": False, "error": f"项目目录不存在: {project_root}"}
    ui_dir = os.path.join(project_root, 'ui')
    if not os.path.isdir(ui_dir):
        return {"success": False, "error": f"ui 目录不存在: {ui_dir}"}
    project_info = _detect_project_info(project_root)   # 平台（供框架依赖体检取包生态键）

    steps = []

    # ① 时间戳检查（ftu→json 只在两种情况下自动做：只有 ftu 没 json；ftu 比 json 新「分钟级」= 用户/IDE 编辑过）
    ts_before = _ui_timestamp_check(project_root)
    dev_modified = ts_before['devModified']
    ftu_only = ts_before['ftuOnly']
    stale = ts_before['stale'] + [{'json': j} for j in ts_before['missing']]
    steps.append({"step": "check_timestamps",
                  "stale": ts_before['stale'], "missing": ts_before['missing'],
                  "devModified": dev_modified, "ftuOnly": ftu_only,
                  "needPack": bool(stale or dev_modified or ftu_only)})

    # ①.5 只有 ftu 没 json → 直接转出 json；ftu 比 json 新分钟级 → unpack 同步 json（其余情况不做反向）
    sync_warnings = []
    if dev_modified or ftu_only:
        sync = _sync_ftu_to_json(project_root)
        sync_warnings = list(sync.get('warnings') or [])
        steps.append({"step": "sync ftu→json", "success": not sync['failed'],
                      "synced": sync['synced'], "syncedDetail": sync.get('syncedDetail', []),
                      "skipped": sync.get('skipped', []), "failed": sync['failed'],
                      "warnings": sync_warnings})
        if sync['failed']:
            f0 = sync['failed'][0]
            return {"success": False, "steps": steps, "failed": sync['failed'],
                    "error": f"ftu → json 转换失败（ui/{f0.get('ftu')}）：{f0.get('error')}",
                    "hint": f0.get('hint') or '请检查该 ftu 是否合法（或改提供同名 json）后重试'}

    # ② fui pack（有 stale/missing/ftuOnly/devModified 才执行；没有则跳过并说明）
    if stale or dev_modified or ftu_only:
        r = _run_fui('pack', ui_dir)
        steps.append({"step": "fui pack", "success": r['success'],
                      "detail": (r.get('stderr') or r.get('stdout') or '')[-400:]})
        if not r['success']:
            return {"success": False, "steps": steps,
                    "error": "fui pack 失败（json 布局可能不合法）"}
    else:
        steps.append({"step": "fui pack", "success": True, "skipped": "json 与 ftu 时间戳一致，无需重新打包"})

    # ③ fun install（同步 Manifest 依赖，Manifest 变更后自动拉取新包）
    warnings = list(sync_warnings)   # ftu→json 的跳过/告警不静默
    ri = _run_fun('install', project_root)
    install_out = (ri.get('stderr') or ri.get('stdout') or ri.get('error') or '')
    steps.append({"step": "fun install", "success": ri['success'],
                  "detail": install_out[-400:]})
    # ⚠️ install 失败**不阻断**（依赖可能已装过：离线/无变更场景），但**不再静默**：
    #必须在返回体顶层给 warnings —— 否则用户只看到 ninja 的 `fatal error: base/functional.h:
    #    No such file or directory`，会以为是代码问题，排查被带偏（2026-09-17 需求方反馈）。
    if not ri['success']:
        steps[-1]['note'] = ('fun install 失败但继续 build（依赖可能已就绪）；'
                             '若 build 报缺依赖请检查 Manifest/网络')
        warnings.append('fun install 失败（%s）：常见于 Manifest 缺 base-utility（代码/生成的 '
                        'generated/*.h 引用 base 头文件）或改过 Manifest 未重装 → 请先 '
                        'flythings_add_package(project_root, "base-utility", with_install=True) / '
                        'fun install 再 build；详见 knowledge/devflow/cli-fun-toolchain.md §4.7'
                        % ((install_out.strip().replace('\n', ' ')[:160])
                           or '原因见 steps 里 fun install 的 detail'))

    # ③.5 前置体检（build 前）：框架基础头能不能解析（不可解析就直接点明「依赖未装/缺包」，
    #不把 ninja 的编译错误丢给用户）；已能解析时**不加 step/warning**，正常路径零噪音。
    fw = {}
    try:
        import package_tools as pkgtools
        fw = pkgtools.framework_dep_status(project_root,
                                           project_info.get('platform') or '')
    except Exception as e:                      # 体检本身出错不阻断（不影响原流程）
        fw = {'success': False, 'error': str(e)}
    if fw.get('success') and fw.get('missing'):
        for d in fw['missing']:
            warnings.append('⚠️ 依赖未装/缺包：%s（%s；本地注册表证据：%s）—— 判定=%s；修复：%s'
                            % (d['package'], d['why'],
                               d['headerInRegistry'] or '本机注册表里也没找到该头文件',
                               'Manifest 未声明且依赖未解析'
                               if not (d['declared'] or d['resolved'])
                               else '头文件不在 include 路径里',
                               d['fix']))
        steps.append({"step": "check_framework_deps", "success": False,
                      "detail": fw['missing'][0]['msg'],
                      "packages": [d['package'] for d in fw['missing']],
                      "evidence": fw['missing'][0]['evidence'],
                      "fix": fw['missing'][0]['fix']})

    # ③.6 字体体检（v0.27.86）：设备侧优先（缺中文 → 默认自动投递 common）；无设备退化到
    #工程侧 self-scan；font_check='off' 时**不加任何字体 step**（开关显式关闭）。
    #设备探测提前到这里（字体体检要用），⑤ 复用同一结果 —— 不重复探 adb。
    plat = project_info.get('platform') or ''
    gate = _launch_gate(plat, device) if with_launch else None
    font_fields = None
    try:
        import font_tools as ftools
        font_status = ftools.font_preflight(
            project_root, plat, device=device, font_check=font_check, font_tier=font_tier,
            apply=True, allow_device=bool(with_launch or device),
            known_online=(gate.get('devices') if gate else None))
        font_fields = ftools.compact(font_status)
        if font_status.get('info'):
            font_fields['info'] = font_status['info']   # info 不是 warning（不进 warnings）
        if font_status.get('enabled'):
            delivered = font_status.get('delivered') or {}
            steps.append({"step": "check_font", "success": not (
                              font_status.get('missingChinese') and not delivered.get('applied')),
                          "mode": font_status.get('mode'),
                          "verdict": font_status.get('verdict'),
                          "missingChinese": font_status.get('missingChinese'),
                          "maxFontBytes": font_status.get('maxFontBytes'),
                          "advisedTier": font_status.get('advisedTier'),
                          "tier": font_status.get('tier'),
                          "delivered": delivered,
                          "deviceFonts": font_status.get('deviceFonts'),
                          # 硬判据（v0.27.87）：source=cmap 时 coverage 才有数；size = 退回体积判据
                          "source": font_status.get('source'),
                          "cmapCoverageGB2312L1": font_status.get('cmapCoverageGB2312L1'),
                          "checkedFont": font_status.get('checkedFont'),
                          "probe": font_status.get('probe'),
                          "note": font_status.get('note'),
                          "detail": ('已自动投递 %s：%s' % (font_status.get('tier'),
                                                           '、'.join(delivered.get('files') or []))
                                     if delivered.get('applied') else
                                     ('缺中文字库，未完成投递（见 warnings）'
                                      if font_status.get('missingChinese') else
                                      '%s已有中文字库（%s KB%s），无需投递'
                                      % ('设备侧' if font_status.get('mode') == 'device'
                                         else '工程侧', font_status.get('maxFontKB'),
                                         '，GB2312 一级覆盖率 %s%%'
                                         % font_status.get('cmapCoverageGB2312L1')
                                         if font_status.get('source') == 'cmap' else '')))})
        for w in (font_status.get('warnings') or []):
            warnings.append(w)
    except Exception as e:                      # 字体体检出错不阻断构建（但明说）
        warnings.append('字体体检异常（不阻断构建）: %s: %s' % (type(e).__name__, e))
        font_fields = {'enabled': False, 'mode': 'error',
                       'note': '字体体检异常，未见结论'}

    # ④ fun build（编译）
    rb = _run_fun('build', project_root)
    steps.append({"step": "fun build", "success": rb['success'],
                  "detail": (rb.get('stderr') or rb.get('stdout') or rb.get('error') or '')[-500:]})
    if not rb['success']:
        err = rb.get('error') or "fun build 失败"
        bout = (rb.get('stderr') or '') + (rb.get('stdout') or '')
        # 缺基础头导致的编译失败 → 翻译成「依赖未装/缺包」，不要把 ninja 原文丢给用户
        if 'base/' in bout and 'No such file or directory' in bout:
            err += ('\n——这是**依赖未装/缺包**（不是代码错误）：fun 生成的 generated/*.h 固定 '
                    '#include <base/...>，Manifest 必须有 base-utility 且重跑过 fun install '
                    '（flythings_add_package(project_root, "base-utility", with_install=True)）。'
                    '详见 knowledge/devflow/cli-fun-toolchain.md §4.7')
        res = {"success": False, "steps": steps, "error": err}
        if font_fields is not None:
            res['fontCheck'] = font_fields
        if warnings:
            res['warnings'] = warnings
        return res

    # ⑤ 设备探测 + fun launch（v0.27.84：默认执行）
    launched = False
    pushed = False
    devinfo = {'serial': '', 'model': '', 'platformMatch': '', 'adb': '', 'adbSource': '',
               'needDeviceInput': False, 'installHint': '', 'deviceSync': None}
    runtime = {}          # launch 前核对（easyui 对账 / 面板分辨率）
    liveness = {}         # launch 后活性（logcat 证据 + GUI 进程）
    cfginfo = {}          # launch 后设备 EasyUI.cfg 资源目录核对
    if with_launch:
        gate = gate or _launch_gate(plat, device)
        devinfo['serial'] = gate['serial']
        devinfo['model'] = gate['model']
        devinfo['platformMatch'] = gate['platformMatch']
        devinfo['adb'] = gate['adb']
        devinfo['adbSource'] = gate['adbSource']
        if gate['connectNote']:
            steps.append({"step": "adb connect", "success": True, "detail": gate['connectNote']})
        if gate['needDeviceInput']:
            steps.append({"step": "device_probe", "success": False,
                          "count": gate['count'], "devices": _devices_brief(gate['devices']),
                          "offline": [d.get('serial') for d in gate['offline']],
                          "detail": gate['message']})
            res = {"success": False, "steps": steps,
                   "needDeviceInput": True, "installHint": gate['installHint'],
                   "message": gate['message'], "device": gate['serial'],
                   "model": gate['model'], "platformMatch": gate['platformMatch'],
                   "devices": _devices_brief(gate['devices']),
                   "adb": gate['adb'], "adbSource": gate['adbSource'],
                   "launched": False, "pushed": False, "staleOnDevice": False,
                   "error": gate['message']}
            if font_fields is not None:
                res['fontCheck'] = font_fields
            if warnings:
                res['warnings'] = warnings
            return res
        steps.append({"step": "device_probe", "success": True,
                      "count": gate['count'], "devices": _devices_brief(gate['devices']),
                      "chosen": gate['serial'], "model": gate['model'],
                      "platformMatch": gate['platformMatch'],
                      "adbSource": gate['adbSource']})
        # ①.5 设备运行时核对（v0.27.179，任务 7/8）：**launch 前**就能拦的两件事
        #     easyui 同源对账（编译期版本 ≠ 设备运行库版本）+ 面板分辨率核对（灰窗事件防线）
        runtime = _device_runtime_pre_launch(gate['serial'], plat, project_info, project_root)
        if runtime.get('easyui') or runtime.get('panel'):
            steps.append({"step": "check_device_runtime", "success": not runtime['warnings'],
                          "easyui": runtime.get('easyui'), "panel": runtime.get('panel'),
                          "detail": ('easyui 固件 %s / 工程 %s；面板 %s'
                                     % ((runtime.get('easyui') or {}).get('firmwareVersion') or '?',
                                        _project_easyui_revision(project_root)[0] or '?',
                                        (runtime.get('panel') or {}).get('panelResolution') or '?'))})
        warnings.extend(runtime['warnings'])
        # ①.6 证据窗口刷新（v0.27.180）：`logcat -d` 读的是**整个缓冲区**，含 launch 之前的旧行 ——
        #     不清缓冲就可能把上一轮的 `onUI_show` 当成本轮证据（假 confirmed）。
        #     清失败只记 warning（有些固件的 logd 不响应 -c，不该因此拦掉整条流程）。
        if _dprobe is not None and gate['serial']:
            try:
                cleared = _dprobe.clear_logcat(gate['serial'])
            except Exception as e:                       # noqa: BLE001
                cleared, why = False, '%s: %s' % (type(e).__name__, e)
            else:
                why = ''
            if not cleared:
                warnings.append('清 logcat 缓冲失败（%s）：本轮「界面起来了吗」的证据可能含旧行'
                                % (why or '设备未响应 logcat -c'))
        if gate['platformMatch'] == 'unknown':
            warnings.append('设备型号无法比对平台（model=%s，%s）：'
                            'fun launch 自己会做平台校验（不匹配会 FATAL platform not match），'
                            '推错机器时请显式传 device=。'
                            % (gate['model'] or '未知',
                               '型号表未登记' if gate['model'] else '设备未回报 ro.product.model'))
        # 平台：优先用接口给的；未指定时唯一设备也推（平台未知不拦，fun 自己校验）
        rl = _run_fun('launch', project_root, device=gate['serial'], retries=5)
        steps.append({"step": "fun launch", "success": rl['success'],
                      "device": gate['serial'],
                      "detail": (rl.get('stderr') or rl.get('stdout') or rl.get('error') or '')[-400:]})
        if not rl['success']:
            fail_msg = ('fun launch 失败（已自动重试 5 次）：设备 %s 推送未生效。'
                        % (gate['serial'] or '?'))
            raw_out = (rl.get('stderr') or rl.get('stdout') or rl.get('error') or '')
            mechanism = _adb.fun_multi_device_error(raw_out) if _adb is not None else ''
            if mechanism:
                fail_msg += ' ' + mechanism
            else:
                fail_msg += ' 已知设备可能掉线/网络推送中断，请确认设备在线后重试。'
            res = {"success": False, "steps": steps,
                   "needDeviceInput": True,
                   "installHint": (_adb.install_hint(plat, gate['devices'])
                                    if _adb is not None else ''),
                   "message": fail_msg,
                   "device": gate['serial'], "model": gate['model'],
                   "platformMatch": gate['platformMatch'],
                   "launched": False, "pushed": False,
                   "error": rl.get('error') or raw_out[-300:]}
            if font_fields is not None:
                res['fontCheck'] = font_fields
            if warnings:
                res['warnings'] = warnings
            return res
        launched = True
        pushed = True
        # ⑤.1 launch 活性（v0.27.179，任务 5）：fun 返回 0 只说明**推送成功**，不说明界面起来了。
        #      黑屏事件的形态就是「推送成功 + 面板黑着」却回了 launched=true —— 所以这里按
        #      logcat 证据 + GUI 进程活性复核；**证据不足不报 launched=true**。
        liveness = {}
        if _dprobe is not None:
            try:
                liveness = _launch_liveness(gate['serial'])
            except Exception as e:
                liveness = {'verdict': 'unknown', 'detail': '%s: %s' % (type(e).__name__, e)}
            steps.append({"step": "verify_launch_liveness", "success": liveness.get('verdict') == 'confirmed',
                          "verdict": liveness.get('verdict'),
                          "marker": (liveness.get('evidence') or {}).get('marker'),
                          "guiProcess": (liveness.get('liveness') or {}).get('verdict'),
                          "detail": liveness.get('detail')})
            if liveness.get('verdict') == 'suspicious':
                launched = False
                warnings.append('⚠️ launch 推送成功，但**没看到界面起来的证据**：%s。'
                                '三件事按序查：① logcat 有无异常/缺库；'
                                '② flythings_device_screenshot 抓屏看实际画面（能抓但画面黑 = 应用没画）；'
                                '③ 设备端进程是否卡在 D 状态（D 状态 kill 不掉，需断电重启）。'
                                % (liveness.get('detail') or '证据不足'))
            elif liveness.get('verdict') == 'unknown':
                warnings.append('界面是否真的起来**无法确认**（%s）——不要仅凭 launched 下结论，'
                                '建议抓屏复核。' % (liveness.get('detail') or '证据不足'))
        # ⑤.2 设备 EasyUI.cfg 的资源目录核对（任务 9）：resPath/languagePath/font 不存在时
        #      界面静默走 fallback（缺字/英文/空图），logcat 不报错 —— 历史坑 /tmp/tr 不存在。
        cfginfo = {}
        try:
            cfginfo = _device_cfg_paths(gate['serial'])
        except Exception as e:
            cfginfo = {'error': '%s: %s' % (type(e).__name__, e)}
        if cfginfo.get('missing'):
            steps.append({"step": "check_device_cfg_paths", "success": False,
                          "cfg": cfginfo.get('cfg'), "missing": cfginfo['missing'],
                          "paths": cfginfo.get('paths'),
                          "detail": '设备 EasyUI.cfg 里这些路径不存在 → 界面会走 fallback（缺字/英文/空图）'})
            warnings.append('⚠️ 设备 %s 的资源路径不存在：%s —— launch 只推 app 与 %s，'
                            '**i18n/字体目录要随包或手动补**（历史坑 /tmp/tr 不存在）'
                            % (cfginfo.get('cfg'), '、'.join(cfginfo['missing']),
                               cfginfo.get('paths', {}).get('resPath') or 'resPath'))
        sync = _device_sync_check(project_root, gate['serial'], plat)
        devinfo['deviceSync'] = sync
        # ⑤.5 字体部署后复查（v0.27.87）：本次投递过字体 → 回看设备侧字库现状
        #      （轻量：只看名字/体积，不重拉 —— 字库要 pack_upgrade 固化才变）
        if font_fields is not None and (font_fields.get('delivered') or {}).get('applied') \
                and font_fields.get('mode') == 'device':
            try:
                ftools = __import__('font_tools')
                after = ftools.recheck_after_deploy(
                    gate['serial'], plat, project_root, font_fields.get('delivered') or {})
                font_fields['deviceAfterDeploy'] = after
                for w in (after.get('warnings') or []):
                    warnings.append(w)
            except Exception as e:            # 复查出错不改构建结论（但明说）
                warnings.append('字体部署后复查异常：%s: %s' % (type(e).__name__, e))
        steps.append({"step": "verify_device_sync", "success": sync['allMatch'],
                      "device": gate['serial'],
                      "ftu": [{'name': c['name'], 'localBytes': c['localBytes'],
                               'deviceBytes': c['deviceBytes'], 'same': c['same'],
                               'reason': c['reason']} for c in sync['ftu']],
                      "so": [{'name': c['name'], 'localBytes': c['localBytes'],
                              'deviceBytes': c['deviceBytes'], 'same': c['same'],
                              'reason': c['reason']} for c in sync['so']],
                      "detail": sync['reason']})
        if sync['stale']:
            warnings.append(_adb.stale_hint(sync['stale']) if _adb is not None
                            else '设备侧文件与本地不一致（adb 子系统不可用，未能给出明细）')
    else:
        steps.append({"step": "fun launch", "success": True,
                      "skipped": "with_launch=False：本次只编译不推设备（保守开关）"})

    # 最终时间戳校验（打包后 json 不应比 ftu 新）
    ts_after = _ui_timestamp_check(project_root)
    steps.append({"step": "verify_timestamps",
                  "stale": ts_after['stale'], "missing": ts_after['missing'],
                  "ok": ts_after['ok']})
    res = {"success": True, "projectRoot": project_root, "steps": steps,
           "finalCheck": {"stale": ts_after['stale'], "missing": ts_after['missing']},
           "launched": launched, "pushed": pushed,
           "device": devinfo['serial'], "model": devinfo['model'],
           "platformMatch": devinfo['platformMatch'],
           "staleOnDevice": bool(devinfo['deviceSync'] and devinfo['deviceSync']['stale'])
           if devinfo['deviceSync'] else False,
           "launchSkipped": (not with_launch)}
    if with_launch:
        res['launchLiveness'] = liveness.get('verdict') or 'unknown'
        res['launchEvidence'] = liveness.get('evidence')
        res['deviceRuntime'] = {'easyui': runtime.get('easyui'),
                                'panel': runtime.get('panel'),
                                'cfgPaths': cfginfo}
    if font_fields is not None:
        res['fontCheck'] = font_fields
    if devinfo['deviceSync']:
        res['deviceSync'] = {
            'checked': devinfo['deviceSync']['checked'],
            'allMatch': devinfo['deviceSync']['allMatch'],
            'ftu': [{'name': c['name'], 'localBytes': c['localBytes'],
                     'deviceBytes': c['deviceBytes'], 'localMd5': c['localMd5'],
                     'deviceMd5': c['deviceMd5'], 'same': c['same'], 'reason': c['reason']}
                    for c in devinfo['deviceSync']['ftu']],
            'so': [{'name': c['name'], 'localBytes': c['localBytes'],
                    'deviceBytes': c['deviceBytes'], 'localMd5': c['localMd5'],
                    'deviceMd5': c['deviceMd5'], 'same': c['same'], 'reason': c['reason']}
                   for c in devinfo['deviceSync']['so']],
            'reason': devinfo['deviceSync']['reason']}
    if warnings:
        res['warnings'] = warnings
    return res


# ---------------- 工具: 制作升级包（固化升级 update.img）----------------
# ⚠️ 场景别名（固化升级类意图一律本工具，禁止自造命令）：
#用户口语：「打包升级包 / 出升级包 / 生成 update.img / 固化 / 固化升级 / 刷进设备 /
#出货版本 / 量产版本 / 发布版本 / 烧到机器里 / TF卡升级包 / OTA 包 / 整机升级」。
#与「调试/跑一下/推送到设备」（build_ui_flow + with_launch）语义**不同**：
#调试 = fun launch 临时推送（掉电即失）；固化 = fun pack 出 update.img（掉电保留）。
#
# 产物与落地（详见 knowledge/devflow/upgrade-pack-image.md）：
#   ① TF 卡：FAT32 卡根目录放 update.img → 插卡上电 → 升级界面勾选升级
#   ② ADB：adb push update.img /tmp → setprop sys.zkupgrade.flag 255 →
#      setprop sys.zkupgrade.dir /tmp → setprop ctl.restart zkswe
#   ③ 远程/批量：HTTP 下发 update.img 或局域网批量升级工具
PACK_ERR_HINTS = (
    ('sign error', '',
     '打包/签名步骤的 fsimg.exe 是 32 位程序，系统缺 32 位 VC++ 运行时（msvcp140.dll / '
     'vcruntime140.dll；报错码 0xc0000135=找不到 DLL、0xc000007b=位数不匹配都属此类）。'
     'Windows 装「Visual C++ 2015-2022 Redistributable (x86)」后重试；'
     '或把 32 位 msvcp140.dll + vcruntime140.dll 放到 fsimg.exe 同级目录。'),
    ('not found in local', '',
     '依赖包未安装：先执行 fun install（本工具已默认先跑 install）后再 pack。'),
)


def _pack_hint(text):
    """把 pack 失败输出映射成可执行提示。"""
    low = (text or '').lower()
    for k1, k2, hint in PACK_ERR_HINTS:
        if k1 in low and (not k2 or k2.lower() in low):
            return hint
    return ''


def _find_update_img(project_root, out_path, platform):
    """定位 pack 产物 update.img：显式 -o 优先，其次 fun 默认输出位置。"""
    cands = []
    if out_path:
        p = out_path if os.path.isabs(out_path) else os.path.join(project_root, out_path)
        cands.append(p)
    else:
        cands.append(os.path.join(project_root, 'out', 'update.img'))
        for _name in BUILD_DIR_NAMES:      # .fsc（09-28 起）/ .fun（旧版）都找
            if platform:
                cands.append(os.path.join(project_root, _name, platform, 'update.img'))
            _base = os.path.join(project_root, _name)
            if os.path.isdir(_base):
                for d in sorted(os.listdir(_base)):
                    cands.append(os.path.join(_base, d, 'update.img'))
    for p in cands:
        if os.path.isfile(p):
            return p
    return ''


def flythings_pack_upgrade(project_root, out_path='', release_version='', ab=False,
                           with_build=False, dry_run=False):
    """制作升级包 update.img（固化升级用，区别于调试推送）。
    ⚠️ 场景别名（固化升级类意图一律本工具，禁止自造脚本/命令）：用户口语：「打包升级包/出升级包/生成 update.img/固化/固化升级/刷进设备/出货版本/
量产版本/发布版本/烧到机器里/TF卡升级包/OTA 包/整机升级」。
    ⚠️ 与「调试/跑一下/推送到设备」语义不同：那是 build_ui_flow（fun launch 临时推送，
掉电即失，不固化）；要固化到设备、掉电保留，必须本工具出 update.img。
流程：① fun install 同步依赖 → ②（可选 with_build=True）fun build →
      ③ fun pack（-o 指定输出，--release-version 指定版本号，--ab 出 AB 系统 OTA 包）。
产物：默认 .fsc/<平台>/update.img（09-28 前为 .fun/；-o 可改）；返回路径/大小/时间与三种刷法说明。
    dry_run=True 只回命令计划不执行（写操作默认安全）。
    ⚠️ Windows 常见坑：`FATAL sign error: exit status 0xc0000135 / 0xc000007b` = 缺 32 位
      VC++ 运行时（fsimg.exe 是 32 位）；`package xxx not found in local` = 先 fun install。
    """
    if not os.path.isdir(project_root):
        return {"success": False, "error": "项目目录不存在: %s" % project_root}
    if not os.path.isdir(os.path.join(project_root, 'ui')) and \
            not os.path.isfile(os.path.join(project_root, 'Manifest.xml')):
        return {"success": False,
                "error": "不是 fun 工程根目录（缺 ui/ 且缺 Manifest.xml）: %s" % project_root}

    info = _detect_project_info(project_root)
    platform = info.get('platform') or ''
    extra = []
    if platform:
        extra += ['-p', platform]
    if release_version:
        extra += ['--release-version', str(release_version)]
    if ab:
        extra.append('--ab')
    if out_path:
        extra += ['-o', out_path]
    cmdline = 'fun pack' + ('' if not extra else ' ' + ' '.join(extra))

    if dry_run:
        return {"success": True, "dryRun": True, "projectRoot": project_root,
                "platform": platform, "command": cmdline,
                "plan": ["fun install",
                         ("fun build" if with_build else "fun build（跳过，with_build=False）"),
                         cmdline],
                "output": out_path or ('.fsc/%s/update.img' % (platform or '<platform>')),
                "note": "dry_run 只回计划不执行；确认后传 dry_run=False 出包"}

    steps = []
    ri = _run_fun('install', project_root, timeout=900)
    steps.append({"step": "fun install", "success": ri['success'],
                  "detail": (ri.get('stderr') or ri.get('stdout') or ri.get('error') or '')[-400:]})

    if with_build:
        rb = _run_fun('build', project_root, timeout=1800)
        steps.append({"step": "fun build", "success": rb['success'],
                      "detail": (rb.get('stderr') or rb.get('stdout') or rb.get('error') or '')[-500:]})
        if not rb['success']:
            return {"success": False, "steps": steps, "error": rb.get('error') or "fun build 失败"}

    rp = _run_fun('pack', project_root, timeout=1800, extra=extra)
    out_text = (rp.get('stderr') or '') + (rp.get('stdout') or '')
    steps.append({"step": "fun pack", "success": rp['success'], "command": cmdline,
                  "detail": out_text[-500:]})

    img = _find_update_img(project_root, out_path, platform)
    if not rp['success'] and not img:
        hint = _pack_hint(out_text) or _pack_hint(rp.get('error') or '')
        res = {"success": False, "steps": steps, "platform": platform,
               "command": cmdline, "error": rp.get('error') or out_text[-300:]}
        if hint:
            res['hint'] = hint
        return res

    size = os.path.getsize(img) if img else 0
    return {
        "success": bool(img),
        "projectRoot": project_root,
        "platform": platform,
        "command": cmdline,
        "steps": steps,
        "updateImg": img,
        "sizeBytes": size,
        "sizeMB": round(size / 1048576.0, 2),
        "modified": (time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(os.path.getmtime(img)))
                     if img else ''),
        "howToFlash": [
            "TF卡（最常用）：卡格式化 FAT32，根目录放 update.img → 插卡重新上电 → "
            "升级界面勾选项目点升级；升级完及时拔卡防重复升级",
            "ADB 固化：adb push update.img /tmp/update.img && adb shell setprop "
            "sys.zkupgrade.flag 255 && adb shell setprop sys.zkupgrade.dir /tmp && "
            "adb shell setprop ctl.restart zkswe",
            "插卡自动升级：卡根目录再放无后缀文件 zkautoupgrade（内容=延时秒数）自动升级；"
            "zkrebootdelay 控制升级完延时重启",
            "远程/批量：设备端 HTTP 下载 update.img 走 OTA；局域网批量升级工具（Z20/Z21/Z261）",
        ],
        "note": "update.img 是固化升级包（掉电保留）；调试推送请用 build_ui_flow（fun launch）",
    }

# ---------------- 工具 7: 从 IDE 模板创建项目骨架 -------------
_IDE_BUILDER_IDS = (
    'com.flythings.managedbuild.core.builder',
    'org.eclipse.cdt.managedbuilder.core.genmakebuilder',
    'org.eclipse.cdt.managedbuilder.core.ScannerConfigBuilder',
)


def _project_names_in_files(root):
    """取出模板里**真实**的旧工程名（不是目录名）。

旧工程名只出现在这些位置：.project 的 <name>、.cproject 的
    name="/XXX(/Release|/Debug)" 工作区路径、<project id="XXX.flythings..."> 前缀。

    ⚠️ .project 里除了工程名，"""
    names = set()
    pj = os.path.join(root, '.project')
    if os.path.isfile(pj):
        txt = open(pj, encoding='utf-8', errors='replace').read()
        # ⚠️ 只取 <projectDescription> 下的第一个 <name>（= 工程名）。
        #    <buildCommand><name> 里装的是 Eclipse Builder ID
        #    （com.flythings.managedbuild.core.builder / org.eclipse.cdt.*），
        #它们不是工程名，一旦被当旧名替换掉，IDE 就认不出 builder ——
        #症状：编译无任何输出，CDT Build Console 空白（"没法编译"）。
        m = re.search(r'<projectDescription>\s*<name>\s*([^<]+?)\s*</name>', txt)
        if m:
            names.add(m.group(1).strip())
    cj = os.path.join(root, '.cproject')
    if os.path.isfile(cj):
        txt = open(cj, encoding='utf-8', errors='replace').read()
        names |= set(re.findall(r'name="/([^/"]+)', txt))
        names |= set(re.findall(r'<project id="([^."]+)\.', txt))
    return {n for n in names if n.strip()}


def _repair_project_builders(txt, tpl_txt):
    """兜底：.project 的 buildSpec 必须用 Eclipse Builder ID。

历史 bug（2026-09-17 修复）：旧版 _project_names_in_files 把所有 <name> 都当旧工程名，
    buildCommand 的 Builder ID 被替换成工程名 → IDE 无 builder → 编译无输出。
这里检测缺失就从模板原文恢复整个 <buildSpec> 段。
    """
    if all(b in txt for b in _IDE_BUILDER_IDS):
        return txt
    if tpl_txt:
        m = re.search(r'<buildSpec>.*?</buildSpec>', tpl_txt, re.S)
        if m:
            return re.sub(r'<buildSpec>.*?</buildSpec>', m.group(0), txt, flags=re.S)
    return txt


def flythings_create_project(project_root, platform=None, resolution=None,
                             app_name='', with_cli=True, force=False):
    """从 HelloWord 基础 Demo 项目复制骨架创建完整 FlyThings 项目。
    - 模板源：包内 templates/HelloWord_<平台>（或 IDE 安装目录）
    - 自动替换：工程名 / 分辨率（.settings prefs + ftu 内嵌）/ 平台（Manifest.xml）
    - 附带 fui.exe + fun.exe（with_cli=True），交付用 fun.exe build + launch，无需客户导入 IDE
传入目标项目根目录完整路径、平台（用 platforms.py 的 supported() 取，别手写枚举）
与分辨率（如 800x480）。

    ⚠️⚠️ 硬性要求：platform 与 resolution 必须由用户明确提供，禁止猜测或使用默认值。
若用户未指定硬件平台或屏幕分辨率（如 800x480），
本工具会直接返回错误，拒绝创建——必须先向用户询问这两个参数再调用。
    """
    if not platform or not str(platform).strip():
        return {"success": False,
                "error": "缺少硬件平台：请先向用户询问平台（%s），禁止猜测"
                         % '/'.join(_platforms.supported())}
    if not resolution or not str(resolution).strip():
        return {"success": False, "error": "缺少屏幕分辨率：请先向用户询问分辨率（如 800x480、480x272），禁止猜测"}
    if not re.fullmatch(r'\d+\s*[xX]\s*\d+', str(resolution).strip()):
        return {"success": False, "error": f"分辨率格式错误: {resolution}（应为 WxH，如 800x480、480x272）"}
    root = os.path.abspath(project_root)
    if os.path.isdir(root) and any(os.listdir(root)) and not force:
        return {"success": False, "error": f"目标目录非空: {root}（如需覆盖请传 force=True）"}
    try:
        plat = _platforms.validate(platform)   # 大小写/别名归一；未知平台报错并列出支持项
    except ValueError as e:
        return {"success": False, "error": str(e)}
    tpl = _template_dir(plat)
    if not tpl or not os.path.isdir(tpl):
        return {"success": False,
                "error": f"无 {platform} 的 IDE 空白模板（支持平台: {', '.join(_platforms.supported())}，"
                         f"或包内 templates/）"}
    os.makedirs(root, exist_ok=True)
    # 1. 复制模板全部文件（跳过 Release 编译产物）
    for name in os.listdir(tpl):
        if name in ('Release',):
            continue
        s = os.path.join(tpl, name)
        d = os.path.join(root, name)
        if os.path.isdir(s):
            shutil.copytree(s, d, dirs_exist_ok=True)
        else:
            shutil.copy2(s, d)
    # 2. 替换工程名（.project / .cproject）
    #    ⚠️ 只替换模板「目录名」是不够的：模板内容里的真实工程名常与目录名不一致
    #    （HelloWord_V85X 目录里 .project 写 Helloword_V85x、.cproject 残留 template_z20_smarthome；
    #      HelloWord_T113 目录里写 HelloWord_T113Nor）——只按目录名替换会漏改或半改
    #    （T113 会剩下 "Nor" 尾巴），新工程名仍挂着模板残留。
    #改为：从模板文件内容读出真实旧名（含目录名兜底），长的先替换。
    tpl_name = os.path.basename(tpl)
    new_name = app_name.strip() or os.path.basename(root)
    old_names = ({tpl_name} | _project_names_in_files(root)) - {new_name}
    for fn in ('.project', '.cproject'):
        p = os.path.join(root, fn)
        if not os.path.isfile(p):
            continue
        txt = open(p, encoding='utf-8', errors='replace').read()
        for old in sorted(old_names, key=len, reverse=True):
            if old:
                txt = txt.replace(old, new_name)
        if fn == '.project':   # 兜底：<name> 字段必须就是新工程名
            txt = re.sub(r'<name>[^<]*</name>', '<name>%s</name>' % new_name,
                         txt, count=1)
            # 兜底 2：Builder ID 不能被工程名覆盖（否则 IDE 编译无输出）
            tpl_pj = os.path.join(tpl, '.project')
            tpl_txt = (open(tpl_pj, encoding='utf-8', errors='replace').read()
                       if os.path.isfile(tpl_pj) else '')
            txt = _repair_project_builders(txt, tpl_txt)
        open(p, 'w', encoding='utf-8').write(txt)
    # 3. 更新 .settings 分辨率
    prefs = os.path.join(root, '.settings', 'com.zksw.flythings.easyui.prefs')
    if os.path.isfile(prefs):
        txt = open(prefs, encoding='utf-8', errors='replace').read()
        txt = re.sub(r'(?m)^resolution=.*$', f'resolution={resolution}', txt)
        open(prefs, 'w', encoding='utf-8').write(txt)
    # 3.5 更新 ui/*.ftu 内嵌分辨率（ftu 里也含 resolution，必须 unpack→改 json→pack 回）
    ftu_res = _rewrite_ftu_resolution(root, resolution)
    res_norm = re.sub(r'\s*[xX]\s*', 'x', str(resolution).strip())
    # 4. 更新 Manifest 平台（新格式）
    mf = os.path.join(root, 'Manifest.xml')
    if os.path.isfile(mf):
        txt = open(mf, encoding='utf-8', errors='replace').read()
        txt = re.sub(r'<manifest platform="[^"]*"', f'<manifest platform="{plat}"', txt)
        txt = re.sub(r'enableOnPlatforms="[^"]*"', f'enableOnPlatforms="{plat}"', txt)
        open(mf, 'w', encoding='utf-8').write(txt)
    # 5. 附带 CLI 工具
    cli = {"skipped": True}
    if with_cli:
        cli = flythings_attach_cli_tools(root)
    return {"success": True, "projectRoot": root, "platform": plat,
            "resolution": res_norm, "fromTemplate": tpl,
            "ftuResolution": ftu_res, "cliTools": cli, "notes": [
                "控件指针/ID宏由 IDE 编译时自动生成，logic.cc 直接使用 mXXXPtr，禁止手写定义",
                "src/uart 为系统模板：只改 ProtocolData.h / ProtocolParser.cpp 的协议解析",
                "ui/ 下放 json+ftu，用 fui pack 生成 ftu（已附带 fui.exe）",
                "logic.cc 必须保留 REGISTER_ACTIVITY_TIMER_TAB（空表也行）",
                "⚠️ 交付：项目生成后直接用 fun.exe build 编译、fun.exe launch 推送设备，"
                "无需客户手动导入 FlyThings IDE 编译烧录（fun.exe 已附带在项目根目录）"]}
