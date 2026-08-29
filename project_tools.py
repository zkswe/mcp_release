# -*- coding: utf-8 -*-
"""FlyThings project tools: ftu read, project spec, validation, fui/fun integration."""
import json, os, re, shutil, subprocess, tempfile

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

# IDE 空白模板（新建项目骨架来源，保证框架约定天然正确）
# 优先用包内 templates/（分发包内置，客户无需装 IDE）；其次 IDE 安装目录
IDE_TEMPLATES = {
    'F133': r'C:\zkswe\FlyThingsPreview\bin\workspace\HelloWord_F133',
    'F135': r'C:\zkswe\FlyThingsPreview\bin\workspace\HelloWord_F135',
    'Z21':  r'C:\zkswe\FlyThingsPreview\bin\workspace\HelloWord_Z21',
    'T113': r'C:\zkswe\FlyThingsPreview\bin\workspace\HelloWord_T113Nor',
    'V85X': r'C:\zkswe\FlyThingsPreview\bin\workspace\Helloword_V85x',
    'Z20':  r'C:\zkswe\FlyThingsPreview\bin\workspace\Helloword_Z20',
}


def _template_dir(plat):
    """模板目录：包内 templates/HelloWord_<plat> 优先，其次 IDE 安装目录。"""
    pkg = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates', 'HelloWord_' + plat)
    if os.path.isdir(pkg):
        return pkg
    return IDE_TEMPLATES.get(plat, '')
PLATFORM_ALIASES = {
    'F133EMMC': 'F133', 'F136': 'F135', 'V85X': 'V85X', 'V85XEMMC': 'V85X',
    'T113': 'T113', 'T113EMMC': 'T113', 'T113STDCXX': 'T113', 'Z20': 'Z20',
}


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
def _run_fun(cmd, project_dir, device=''):
    """执行 fun.exe 命令（build/launch 等），在项目根目录运行。
    fun.exe 与 fui.exe 同目录（D:/zkswe/fun/ 或自动探测）。
    ⚠️ fun launch 不支持 -s 参数（带参数有其他问题），device 参数保留仅供 build_ui_flow 兼容，不追加到命令。"""
    if not os.path.isdir(project_dir):
        return {"success": False, "error": f"项目目录不存在: {project_dir}"}
    if not os.path.isfile(FUN_EXE):
        return {"success": False, "error": f"fun.exe 未找到（工具目录: {_tool_dir()}）。"
                f"请设置环境变量 FLYTHINGS_FUN_DIR 指向含 fun.exe/fui.exe 的目录，"
                f"或将其安装到 D:\\zkswe\\fun\\。"}
    args = [FUN_EXE, cmd]
    try:
        r = subprocess.run(args, cwd=project_dir,
                           capture_output=True, text=True, timeout=600,
                           stdin=subprocess.DEVNULL,  # ⚠️ 防 fun.exe 继承 MCP stdio 管道挂起
                           encoding='utf-8', errors='replace')
        return {"success": r.returncode == 0, "returncode": r.returncode,
                "stdout": (r.stdout or '')[-800:], "stderr": (r.stderr or '')[-800:]}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _rewrite_ftu_resolution(project_root, resolution):
    """重写 ui/*.ftu 内嵌的分辨率。
    ftu 里也含 resolution（根节点 resolution + position），只改 .settings prefs 不够，
    必须 unpack → 改 json 的 resolution/position → pack 回 ftu。
    ⚠️ 新版 fui.exe 仅支持 pack（json→ftu）：改直接用同目录 json 改分辨率后 pack 回 ftu；
    无 json 且 fui 不支持 unpack 时标记 failed（提示改用旧版 fui.exe 或手动处理）。
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
            # json 源：优先同目录已有 json；新版 fui.exe 无 unpack 时必需 json
            src_json = os.path.join(ui_dir, base + '.json')
            if os.path.isfile(src_json):
                shutil.copy2(src_json, tmp)
                jf = os.path.join(tmp, base + '.json')
            elif not _fui_supports_unpack():
                result["failed"].append({"ftu": fn,
                                          "error": f"当前 fui.exe 仅支持 pack 且无 {base}.json 可改分辨率，"
                                                   f"请换用支持 unpack 的旧版 fui.exe 或手动修改 json"})
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
            result["updated"].append(fn)
        except Exception as e:
            result["failed"].append({"ftu": fn, "error": str(e)})
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    return result


# ---------------- ui json/ftu 时间戳校验 ----------------
def _ui_timestamp_check(project_root, dev_threshold=30):
    """检查 ui 目录下 .json 与 .ftu 的修改时间一致性。
    返回 {"stale": [{json, ftu, jsonTime, ftuTime}], "missing": [{json}],
          "devModified": [{json, ftu, jsonTime, ftuTime}], "ok": [...]}。
    stale = json 比 ftu 新（改过 json 没重新 pack）；missing = 有 json 无 ftu；
    devModified = ftu 比 json 新超过 dev_threshold 秒（开发者/IDE 直接改过 ftu，
    改 json 前必须先 unpack ftu 同步，否则会覆盖开发者的修改）。"""
    ui_dir = os.path.join(project_root, 'ui')
    result = {"stale": [], "missing": [], "devModified": [], "ok": []}
    if not os.path.isdir(ui_dir):
        return result
    for fn in sorted(os.listdir(ui_dir)):
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
            elif ft > jt + dev_threshold:  # ftu 比 json 新超 30s → 开发者/IDE 改过 ftu
                result["devModified"].append({"json": fn, "ftu": fn[:-5] + '.ftu',
                                               "jsonTime": jt, "ftuTime": ft})
            else:
                result["ok"].append(fn)
        else:
            result["missing"].append(fn)
    return result


def _sync_ftu_to_json(project_root):
    """开发者/IDE 直接改过 ftu（ftu 比 json 新 >30s）时，先 unpack ftu 同步 json。
    返回 {"synced": [{ftu}], "skipped": [...], "failed": [{ftu, error}]}。
    以 ftu 为真源：unpack 出的 json 覆盖旧 json，后续修改 json 才不会丢开发者的改动。
    ⚠️ 新版 fui.exe 仅支持 pack（json→ftu），不支持 unpack：无法从 ftu 反解析，
    所有 devModified 标记为 skipped（提示以 json 为源重新 pack，开发者改动需手动同步）。"""
    ui_dir = os.path.join(project_root, 'ui')
    result = {"synced": [], "skipped": [], "failed": []}
    if not os.path.isdir(ui_dir):
        return result
    if not _fui_supports_unpack():
        ts = _ui_timestamp_check(project_root)
        for dm in ts.get('devModified', []):
            result["skipped"].append({"ftu": dm['ftu'],
                                       "reason": "当前 fui.exe 仅支持 pack，无法从 ftu 反解析 json；以 json 为源重新 pack（开发者对 ftu 的手改需手动同步到 json）"})
        return result
    ts = _ui_timestamp_check(project_root)
    for dm in ts.get('devModified', []):
        ftu_name = dm['ftu']
        ftu_path = os.path.join(ui_dir, ftu_name)
        tmp = tempfile.mkdtemp(prefix='ftu_sync_')
        try:
            shutil.copy2(ftu_path, tmp)
            r = _run_fui('unpack', tmp)
            if not r['success']:
                result["failed"].append({"ftu": ftu_name,
                                          "error": (r.get('stderr') or r.get('stdout') or '')[-200:]})
                continue
            jf = os.path.join(tmp, ftu_name[:-4] + '.json')
            if not os.path.isfile(jf):
                result["failed"].append({"ftu": ftu_name, "error": 'unpack 后未找到 json'})
                continue
            dst = os.path.join(ui_dir, ftu_name[:-4] + '.json')
            shutil.copy2(jf, dst)  # ftu 为准，覆盖旧 json
            # ⚠️ fui unpack 出的 json 的 mtime 是 ftu 内嵌的打包时间戳（旧），
            # 不调整会继续误判 devModified → 把 json mtime 对齐到 ftu 文件时间
            ft_mtime = os.path.getmtime(ftu_path)
            os.utime(dst, (ft_mtime, ft_mtime))
            result["synced"].append(ftu_name)
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


# ---------------- 工具 1: read_ftu ----------------
def flythings_read_ftu(ftu_path):
    """解析 .ftu 文件，返回 JSON 结构（resolution/controls/idMapping）。
    优化：ftu 同目录已有更新的同名 .json 时直接读 json（跳过 fui.exe 启动，防卡顿）。
    ⚠️ 新版 fui.exe 仅支持 pack（json→ftu），不支持 unpack：若目录下无同名 json，
    无法从 ftu 反解析布局，直接报错提示（不再尝试 unpack）。"""
    if not os.path.isfile(ftu_path):
        return {"success": False, "error": f"ftu 文件不存在: {ftu_path}"}
    d = os.path.dirname(os.path.abspath(ftu_path)) or '.'
    base = os.path.splitext(os.path.basename(ftu_path))[0]
    json_path = os.path.join(d, base + '.json')
    # 优先用已有 json（json 不旧于 ftu 时直接解析，无需启动 fui.exe）
    if os.path.isfile(json_path) and os.path.getmtime(json_path) >= os.path.getmtime(ftu_path):
        try:
            info = _parse_ui_json(json_path)
            if info.get('success'):
                info['source'] = 'json'
                return info
        except Exception:
            pass
    # json 缺失或旧于 ftu：新版 fui.exe 不支持 unpack → 降级提示
    if not _fui_supports_unpack():
        if os.path.isfile(json_path):
            info = _parse_ui_json(json_path)
            if info.get('success'):
                info['source'] = 'json'
                info['warning'] = 'json 旧于 ftu（当前 fui.exe 不支持 unpack，无法从 ftu 反解析，返回旧 json 仅供参考）'
                return info
        return {"success": False,
                "error": f"当前 fui.exe 仅支持 pack（json→ftu），不支持 unpack，无法从 ftu 反解析布局。"
                         f"请提供同目录的 {base}.json 文件，或换用支持 unpack 的旧版 fui.exe"}
    tmp = tempfile.mkdtemp(prefix='ftu_read_')
    try:
        shutil.copy2(ftu_path, tmp)
        r = _run_fui('unpack', tmp)
        if not r['success']:
            return {"success": False, "error": f"fui unpack 失败: {r.get('stderr') or r.get('stdout')}"}
        for fn in sorted(os.listdir(tmp)):
            if fn.endswith('.json'):
                info = _parse_ui_json(os.path.join(tmp, fn))
                info['source'] = 'ftu'
                return info
        return {"success": False, "error": "fui unpack 后未找到 json"}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def flythings_read_json(json_path):
    """解析 .json 布局文件，返回结构化信息。"""
    if not os.path.isfile(json_path):
        return {"success": False, "error": f"json 文件不存在: {json_path}"}
    return _parse_ui_json(json_path)


# ---------------- 工具 2: project spec ----------------
_PROJECT_SPEC = {
    "directoryRules": {
        "activity": "IDE生成目录（mainActivity.cpp/h 由 IDE 编译时根据 ftu 自动生成），禁止创建/修改/覆盖；业务代码只写 src/logic/*.cc",
        "logic": "用户唯一代码目录",
        "core": "独立模块目录"
    },
    "generationRules": {
        "idMacros": {"file": "mainActivity.h", "section": "/*TAG:Macro宏ID*/", "autoGenerated": True},
        "controlPointers": {"file": "mainActivity.cpp", "section": "/*TAG:GlobalVariable全局变量*/", "autoGenerated": True},
        "initSequence": "onCreate() → findControlByID() → mActivityPtr=this → onUI_init()"
    },
    "caveats": [
        "logic.cc 通过 #include 与 mainActivity.cpp 共享编译单元",
        "控件指针 mXXXPtr / ID_MAIN_* 宏 / 回调表全部由 IDE 编译时根据 ftu 自动生成，用户禁止手写定义",
        "禁止在 logic.cc 中定义 ID_MAIN_* 宏、static ZKxxx* 指针、new ZKxxx、findControlByID 初始化",
        "onUI_init() 时所有控件指针已由 IDE 初始化完毕，直接使用即可",
        "每个 logic.cc 必须包含 REGISTER_ACTIVITY_TIMER_TAB（不用定时器也保留空表）",
        "setBackgroundBmp 只调一次，帧刷新用 setInvalid 交替",
        "obtainListItemData_XXX 禁止耗时代码（滚动时每行调用）",
        "设备字库不支持 emoji 和特殊字符（■ ● ⌫ ℃ 等）",
        "新建项目应从 IDE 模板创建（flythings_create_project），勿手搭骨架",
        "工程文件 .project/.cproject/.settings 是 IDE 必需，缺失则项目无法编译",
        "Manifest 用新格式 <manifest platform=\"...\">（旧 <Manifest> 格式 IDE 不认）",
        "src/uart 为系统模板：UartContext/ProtocolSender 勿改，只改 ProtocolData.h 与 ProtocolParser.cpp 协议部分",
        "json 布局用 fui pack 生成 ftu（ui/ 下已附带 fui.exe）；编译推送用 fun.exe build / fun.exe launch（项目根目录已附带 fun.exe）",
        "⚠️ 交付流程：项目生成后直接用 fun.exe build 编译、fun.exe launch 推送设备，无需客户手动导入 FlyThings IDE 编译烧录",
        "需要三方能力（MQTT/HTTP/JSON/数据库/蓝牙/SSL/OTA/图片等）→ 先 flythings_search_package / flythings_recommend_manifest 检索现有 package，有包用包，禁止手写库或凭空 include",
        "代码 include 了三方库头文件 → Manifest.xml 必须声明对应 package（validate_project 会检查缺失依赖）"
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
    prefs = os.path.join(root, '.settings', 'com.zksw.flythings.easyui.prefs')
    if os.path.isfile(prefs):
        try:
            ptext = open(prefs, encoding='utf-8', errors='replace').read()
        except Exception:
            ptext = ''
        m = re.search(r'(?m)^resolution=([\w]+)$', ptext)
        if m:
            info['resolution'] = m.group(1)
            info['sources']['resolution'] = '.settings prefs'
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
    （F133/F135/Z21）与屏幕分辨率（如 800x480），然后调用 flythings_create_project
    创建项目；禁止到其他目录检索 json/ftu 文件。
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
                "hint": '空白项目（ui 目录无 .ftu 布局，无需再读取 json）：'
                        '直接向用户询问硬件平台（F133/F135/Z21）与屏幕分辨率（如 800x480），'
                        '然后调用 flythings_create_project 创建；禁止去其他目录检索 json/ftu。',
                "errors": [], "warnings": []}
    errors, warnings = [], []
    src = os.path.join(root, 'src')
    ui = os.path.join(root, 'ui')
    need_user = {'platform': not project_info['platform'],
                 'resolution': not project_info['resolution']}
    if need_user['platform'] or need_user['resolution']:
        warnings.append({'file': 'project', 'type': 'unknown_platform_resolution',
                         'msg': '无法确认硬件平台与屏幕分辨率（缺 Manifest 平台属性或 ui 布局/设置），'
                                '需要向用户询问平台（F133/F135/Z21）与分辨率（如 800x480）'})

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
                                 'msg': 'setBackgroundBmp 多次调用（应只调一次，帧刷新用 setInvalid）'})
            # ⚠️ 宏批量生成回调（如 #define DEFINE_DAY_CB(i) void onButtonClick_BtnDay##i(...) 展开 42 个日期格）
            #     → fun build 扫描 ftu 回调时识别不到宏展开 → 向 logic.cc 追加显式桩 → 与宏展开重定义冲突
            # 检测：以 #define 开头（含 \ 续行）的宏体内含回调签名模式（onXxxClick/onXxxChanged/onXxxTouch/onXxxTimer）
            for m in re.finditer(r'#define\s+\w+\s*\([^)]*\)\s*[^\n]*(?:\\\n[^\n]*)*', text):
                if re.search(r'(?:on\w*Click|on\w*Changed|on\w*Touch|on\w*Timer)', m.group(0)):
                    errors.append({'file': f'src/logic/{fn}', 'type': 'macro_generated_callback',
                                   'msg': f'宏生成回调 {m.group(0)[:44].strip()}...：fun build 无法识别宏展开的回调，'
                                          f'会向 logic.cc 追加同名桩导致重定义编译错误；请显式定义每个回调函数，禁止宏批量生成'})
                    break  # 每个文件只报一次
            # 已存在的回调函数名单（供提示用）
            defined_cbs = set(re.findall(r'(on(?:\w+Click|\w+Changed|\w+Touch|\w+Timer)_\w+)\s*\(', text))
    else:
        warnings.append({'file': 'src/logic', 'type': 'missing_dir', 'msg': 'src/logic 目录不存在'})

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
    try:
        import package_tools as pkgtools
        dep = pkgtools.flythings_check_project_deps(root)
        if dep.get('success'):
            for md in dep.get('missingDependencies', []):
                errors.append({'file': 'Manifest.xml', 'type': 'missing_dependency',
                               'msg': f"代码 include 了 {md['include']} 但 Manifest 未声明对应 package"
                                      f"（推荐: {', '.join(md['recommendedPackages'])}）"})
    except Exception as e:
        warnings.append({'file': 'Manifest.xml', 'type': 'dep_check_failed',
                         'msg': f'三方库依赖检查未执行: {e}'})

    # 1.9 HTTPS 证书检查（curl/curl-cxx + https 调用必须打包 resources/cacert.pem，
    #     否则 mbedtls 缺 CA 证书直接进程崩溃→看门狗重启，不报错）
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
            else:
                warnings.append({'file': 'resources/cacert.pem', 'type': 'cacert_ok',
                                 'msg': 'HTTPS 证书已就位（仅提示：证书过期会表现为握手失败，注意维护）'})

    # 2. activity 目录（不应含用户业务代码特征）
    # ⚠️ 模板 mainActivity.cpp 本身含 REGISTER_ACTIVITY_TIMER_TAB 系统代码，不能用它做特征；
    #    正确特征：用户代码是 .cc（被 include 进 activity.cpp），activity 目录只应存在 IDE 生成的 .cpp/.h
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
    else:
        warnings.append({'file': 'src/activity', 'type': 'missing_dir',
                         'msg': 'src/activity 目录不存在（IDE 编译后自动生成；若项目新建自模板则正常）'})

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
        # ftu 比 json 新超 30s → 开发者/IDE 直接改过 ftu（改 json 前必须先 unpack 同步）
        for d in ts.get('devModified', []):
            if _fui_supports_unpack():
                msg = (f"{d['ftu']} 修改时间晚于 {d['json']} 超 30 秒（开发者/IDE 直接改过 ftu，"
                       f"修改 json 前必须先 fui unpack 同步，否则会覆盖开发者改动）")
            else:
                msg = (f"{d['ftu']} 修改时间晚于 {d['json']} 超 30 秒（开发者/IDE 直接改过 ftu；"
                       f"当前 fui.exe 仅支持 pack 不支持 unpack，无法从 ftu 反解析——"
                       f"如需保留开发者对 ftu 的改动，请手动同步到 json，或换用支持 unpack 的旧版 fui.exe）")
            warnings.append({'file': f"ui/{d['ftu']}", 'type': 'dev_modified_ftu', 'msg': msg})
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



# ---------------- 工具 5: 附带 CLI 工具到项目 -------------
def flythings_attach_cli_tools(project_root, with_fyx=True):
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
    if with_fyx:
        dst = os.path.join(project_root, 'fun.exe')
        try:
            shutil.copy2(FUN_EXE, dst)
            results.append({"file": "fun.exe", "size": os.path.getsize(dst), "status": "copied"})
        except Exception as e:
            results.append({"file": "fun.exe", "status": "failed", "error": str(e)})
    ok = all(r.get('status') in ('copied', 'skipped') for r in results)
    return {"success": ok, "projectRoot": project_root, "files": results}
