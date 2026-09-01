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


# ---------------- 工具 1: read_json ----------------
def flythings_read_json(json_path):
    """解析 .json 布局文件，返回结构化信息。
    ⚠️ 传入 .ftu 时提示：ftu 为加密文件无法解析，可提供设计文件 / AI 重新设计界面 / 采用 HTML 布局。
    """
    if json_path.lower().endswith('.ftu'):
        return {"success": False,
                "error": "由于 ftu 为加密文件无法解析，您可以提供您的设计文件或者采用 AI 重新设计界面或者采用 HTML 布局。"}
    if not os.path.isfile(json_path):
        return {"success": False, "error": f"json 文件不存在: {json_path}"}
    return _parse_ui_json(json_path)


# ---------------- 工具 2: project spec ----------------
_PROJECT_SPEC = {
    "directoryRules": {
        "activity": "IDE生成目录（mainActivity.cpp/h 由 IDE 编译时根据 ftu 自动生成），禁止创建/修改/覆盖；业务代码只写 src/logic/*.cc",
        "logic": "UI与业务的关联层（回调里取控件指针/刷界面/调业务对象），不做复杂逻辑；复杂功能拆独立 C++ 类放自建目录（core/modules/business 等）并在 logic include+调用",
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
        "代码层架构：logic/*.cc 只做 UI 与业务的关联操作（取控件指针/setText/调业务对象）；复杂功能开发成独立 C++ 类放自建目录（src/core/、src/modules/ 等），在 logic include+调用；新增业务代码一律用 .cpp/.h（独立编译单元，fun build 自动编译），禁止新建 .cc 文件——.cc 是 IDE 按页面生成的 logic 专属（仅 mainLogic.cc 等），靠 mainActivity.cpp #include 进编译单元，手写 .cc 不会被编译（Makefile 只编 %.cpp %.c）",
        "src/uart 为系统模板：UartContext/ProtocolSender 勿改，只改 ProtocolData.h 与 ProtocolParser.cpp 协议部分",
        "json 布局用 fui pack 生成 ftu（ui/ 下已附带 fui.exe）；编译推送用 fun.exe build / fun.exe launch（项目根目录已附带 fun.exe）",
        "⚠️ 交付流程：项目生成后直接用 fun.exe build 编译、fun.exe launch 推送设备，无需客户手动导入 FlyThings IDE 编译烧录",
        "需要三方能力（MQTT/HTTP/JSON/数据库/蓝牙/SSL/OTA/图片等）→ 先 flythings_search_package / flythings_recommend_manifest 检索现有 package，有包用包，禁止手写库或凭空 include",
        "代码 include 了三方库头文件 → Manifest.xml 必须声明对应 package（validate_project 会检查缺失依赖）"
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

    # 1.1 ⚠️ 手写 .cc 检查（沛哥 2026-08-31）：.cc 是 IDE 按页面生成的 logic 专属（xxxLogic.cc，
    #     靠 mainActivity.cpp #include 进编译单元）；Makefile 只编译 %.cpp %.c，手写 .cc 不会被编译。
    #     新增业务代码一律用 .cpp/.h，禁止新建 .cc 模拟 logic.cc。
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



# ---------------- 工具 4.5: 创建可执行程序项目 (fun create --type bin) -------------
def _is_elf(path):
    """检测文件是否为 ELF 可执行文件（魔数 \x7fELF）。"""
    try:
        with open(path, 'rb') as f:
            return f.read(4) == b'\x7fELF'
    except Exception:
        return False


def flythings_create_bin_project(project_root, project_name='', platform='z21',
                                 app_version='1.0.0', description='', with_build=True):
    """创建「可执行程序」类型项目（fun create --type bin）并编译为直接可运行的 ELF 二进制。

    - 项目类型 4 选 1：zkgui（UI应用）/ bin（可执行程序）/ staticLibrary / sharedLibrary
    - bin 项目结构极简：fun.json（"type": "executable"）+ src/main.cpp（标准 int main()）
    - 编译：fun build → 产物 .fun/{platform}/{项目名}，ELF 魔数验证
    - 部署：adb push + chmod +x 直接跑（无 zkgui 宿主，不能启动 UI 应用）
    - 非交互：自动传 --app-version/--description 跳过向导；目录非空直接报错（防覆盖询问卡死）

    传入项目根目录（可不存在，自动创建）、平台（默认 z21，支持 z20/t113/f133 等）、
    项目名（缺省取目录名）。返回创建结果 + 编译日志 + 产物路径与 ELF 验证。
    """
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
    out = os.path.join(root, '.fun', platform, name)
    exists = os.path.isfile(out)
    result.update({
        "outputPath": out if exists else None,
        "outputSize": os.path.getsize(out) if exists else 0,
        "isElfExecutable": _is_elf(out) if exists else False,
        "deployHint": f"adb push {out} /tmp/ && adb shell chmod +x /tmp/{name} && adb shell /tmp/{name}",
    })
    return result


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


# ---------------- 工具 4.6: 编辑 json/ftu 布局 ----------------
def _find_control(data, target):
    """按 caption（优先）或控件 key 查找控件。返回 (key, value)。"""
    for key, val in data.items():
        if not isinstance(val, dict) or '__' not in key:
            continue
        if val.get('caption') == target or key == target:
            return key, val
    return None, None


def _apply_edits(data, ops):
    """应用编辑操作到 json 布局。ops 为操作列表。返回 (success, report)。
    支持操作：
      set      {"op":"set", "target":"caption或key", "props":{...}}  修改控件属性
      remove   {"op":"remove", "target":"caption或key"}            删除控件
      add      {"op":"add", "template":"caption或key", "newKey":"textview__4", "props":{...}}  复制模板控件新增并改属性
      set_root {"op":"set_root", "props":{"backgroundColor":"#FFFFFF"}}  修改根属性（resolution/position/backgroundColor 等）
    """
    report = []
    for op in ops:
        if not isinstance(op, dict):
            report.append(f'[跳过] 非法操作: {op}')
            continue
        kind = op.get('op')
        if kind == 'set':
            key, val = _find_control(data, op.get('target', ''))
            if val is None:
                report.append(f'[失败] 未找到控件: {op.get("target")}')
                continue
            props = op.get('props') or {}
            changed = [p for p in props if val.get(p) != props[p]]
            val.update(props)
            report.append(f'[OK] 修改 {key}: {changed if changed else "无变化"}')
        elif kind == 'remove':
            key, _ = _find_control(data, op.get('target', ''))
            if key is None:
                report.append(f'[失败] 未找到控件: {op.get("target")}')
                continue
            data.pop(key, None)
            report.append(f'[OK] 删除 {key}')
        elif kind == 'add':
            tkey, tval = _find_control(data, op.get('template', ''))
            if tval is None:
                report.append(f'[失败] 模板控件不存在: {op.get("template")}')
                continue
            new_key = op.get('newKey', '')
            if not new_key:
                report.append('[失败] 缺少 newKey')
                continue
            if new_key in data:
                report.append(f'[失败] key 已存在: {new_key}')
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
    return True, report


def flythings_edit_json(json_path, operations):
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
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return {"success": ok, "jsonPath": json_path, "report": report,
            "controlsCount": sum(1 for k, v in data.items() if isinstance(v, dict) and '__' in k)}


def flythings_edit_ftu(ftu_path, operations, output_ftu=''):
    """编辑 ftu 布局：自动应用编辑到 json 后 pack 回 ftu（默认覆盖原文件，或 output_ftu 指定新文件）。
    operations 为 JSON 数组字符串，支持 set/remove/add/set_root（见 _apply_edits）。
    ⚠️ 布局以 json 为源：优先直接编辑同目录已有 json 再 pack 回 ftu；无 json 时报错。
    客户说「把这个按钮往右移/改文本/换颜色/删掉某控件/复制一个控件」时调用。"""
    if not os.path.isfile(ftu_path):
        return {"success": False, "error": f"ftu 文件不存在: {ftu_path}"}
    src_dir = os.path.dirname(os.path.abspath(ftu_path)) or '.'
    base = os.path.splitext(os.path.basename(ftu_path))[0]
    json_path = os.path.join(src_dir, base + '.json')
    if not os.path.isfile(json_path):
        return {"success": False,
                "error": f"缺少同目录 {base}.json（布局以 json 为源，请先提供 json 布局再编辑）"}
    ed = flythings_edit_json(json_path, operations)
    if not ed['success']:
        return ed
    r = _run_fui('pack', src_dir)
    if not r['success']:
        return {"success": False, "error": f"fui pack 失败: {r.get('stderr') or r.get('stdout')}",
                "report": ed['report']}
    new_ftu = os.path.join(src_dir, base + '.ftu')
    dst = os.path.abspath(output_ftu) if output_ftu else os.path.abspath(ftu_path)
    if os.path.abspath(new_ftu) != dst:
        shutil.copy2(new_ftu, dst)
    return {"success": True, "ftuPath": dst, "report": ed['report'],
            "controlsCount": ed.get('controlsCount'), "syncedJson": True}


# ---------------- 工具 6: UI 构建流程（pack → build → launch）----------------
def flythings_build_ui_flow(project_root, with_launch=True, device=''):
    """FlyThings UI 构建流程（关键步骤，不可跳过）：
    ① 检查 ui/*.json 与 *.ftu 修改时间一致性
       - json 比 ftu 新 = 改过 json 没重新打包
       - ftu 比 json 新超 30 秒 = 开发者/IDE 直接改过 ftu → 先 unpack 同步 json 再继续
    ② 有改动才 fui pack <ui目录>（设备实际加载的是 FTU 而非 JSON）
    ③ fun install 同步 Manifest 依赖（每次 build 前执行，Manifest 变更自动拉取新依赖）
    ④ fun build 编译 C++ 代码
    ⑤ fun build 通过后直接 fun launch 推送设备并启动（默认，with_launch=False 可跳过）
    ⚠️ launch 失败（无 adb 设备）时返回 needDeviceInput=true，此时必须询问用户接入方式：
       1) USB 接入：将设备通过 USB 连电脑，然后重试本工具；
       2) 网络接入：让用户提供设备 IP（如 192.168.1.100），用 device='<ip>' 重试（走 fun launch -s <ip>）。
       禁止替用户猜测 IP。
    ⚠️ 常见错误：修改 JSON 后直接 launch 忘记 pack，设备上仍运行旧版 FTU 布局；
    开发者改过 ftu 时若直接改 json 会覆盖其修改（必须先 unpack ftu 同步）。
    传入项目根目录完整路径。返回每步结果与最终时间戳校验。"""
    if not os.path.isdir(project_root):
        return {"success": False, "error": f"项目目录不存在: {project_root}"}
    ui_dir = os.path.join(project_root, 'ui')
    if not os.path.isdir(ui_dir):
        return {"success": False, "error": f"ui 目录不存在: {ui_dir}"}

    steps = []

    # ① 时间戳检查（含开发者修改检测：ftu 比 json 新超 30s）
    ts_before = _ui_timestamp_check(project_root)
    dev_modified = ts_before['devModified']
    stale = ts_before['stale'] + [{'json': j} for j in ts_before['missing']]
    steps.append({"step": "check_timestamps",
                  "stale": ts_before['stale'], "missing": ts_before['missing'],
                  "devModified": dev_modified,
                  "needPack": bool(stale or dev_modified)})

    # ①.5 开发者改过 ftu → 先 unpack ftu 同步 json（以 ftu 为真源）
    if dev_modified:
        sync = _sync_ftu_to_json(project_root)
        steps.append({"step": "sync ftu→json", "success": not sync['failed'],
                      "synced": sync['synced'], "failed": sync['failed']})
        if sync['failed']:
            return {"success": False, "steps": steps,
                    "error": f"unpack ftu 同步 json 失败: {sync['failed'][0]['error']}"}

    # ② fui pack（有 stale/missing/devModified 才执行；没有则跳过并说明）
    if stale or dev_modified:
        r = _run_fui('pack', ui_dir)
        steps.append({"step": "fui pack", "success": r['success'],
                      "detail": (r.get('stderr') or r.get('stdout') or '')[-400:]})
        if not r['success']:
            return {"success": False, "steps": steps,
                    "error": "fui pack 失败（json 布局可能不合法）"}
    else:
        steps.append({"step": "fui pack", "success": True, "skipped": "json 与 ftu 时间戳一致，无需重新打包"})

    # ③ fun install（同步 Manifest 依赖，Manifest 变更后自动拉取新包）
    ri = _run_fun('install', project_root)
    steps.append({"step": "fun install", "success": ri['success'],
                  "detail": (ri.get('stderr') or ri.get('stdout') or ri.get('error') or '')[-400:]})
    # ⚠️ install 失败不阻断：依赖可能已装过（离线/无变更场景），继续 build 让真实错误暴露
    if not ri['success']:
        steps[-1]['note'] = 'fun install 失败但继续 build（依赖可能已就绪）；若 build 报缺依赖请检查 Manifest/网络'

    # ④ fun build（编译）
    rb = _run_fun('build', project_root)
    steps.append({"step": "fun build", "success": rb['success'],
                  "detail": (rb.get('stderr') or rb.get('stdout') or rb.get('error') or '')[-500:]})
    if not rb['success']:
        return {"success": False, "steps": steps,
                "error": rb.get('error') or "fun build 失败"}

    # ⑤ fun launch（build 通过后直接推送启动；失败→询问设备接入方式）
    if with_launch:
        rl = _run_fun('launch', project_root, device=device)
        steps.append({"step": "fun launch", "success": rl['success'],
                      "device": device or '(自动发现 USB 设备)',
                      "detail": (rl.get('stderr') or rl.get('stdout') or rl.get('error') or '')[-400:]})
        if not rl['success']:
            return {"success": False, "steps": steps,
                    "needDeviceInput": True,
                    "message": "fun launch 失败：未检测到可用的 adb 设备（或设备未连接）。"
                                "请询问用户接入方式："
                                "1) USB 接入：将设备通过 USB 连接到电脑后重试本工具；"
                                "2) 网络接入：请用户提供设备 IP（如 192.168.1.100），"
                                "用 device='<ip>' 重新调用（将执行 fun launch -s <ip>）。",
                    "error": rl.get('error') or (rl.get('stderr') or rl.get('stdout') or '')[-300:]}
    else:
        steps.append({"step": "fun launch", "success": True, "skipped": "未请求推送（with_launch=False）"})

    # 最终时间戳校验（打包后 json 不应比 ftu 新）
    ts_after = _ui_timestamp_check(project_root)
    steps.append({"step": "verify_timestamps",
                  "stale": ts_after['stale'], "missing": ts_after['missing'],
                  "ok": ts_after['ok']})
    return {"success": True, "projectRoot": project_root, "steps": steps,
            "finalCheck": {"stale": ts_after['stale'], "missing": ts_after['missing']}}


# ---------------- 工具 7: 从 IDE 模板创建项目骨架 -------------
def flythings_create_project(project_root, platform=None, resolution=None,
                             app_name='', with_cli=True, force=False):
    """从 HelloWord 基础 Demo 项目复制骨架创建完整 FlyThings 项目。
    - 模板源：包内 templates/HelloWord_<平台>（或 IDE 安装目录）
    - 自动替换：工程名 / 分辨率（.settings prefs + ftu 内嵌）/ 平台（Manifest.xml）
    - 附带 fui.exe + fun.exe（with_cli=True），交付用 fun.exe build + launch，无需客户导入 IDE
    传入目标项目根目录完整路径、平台（F133/F135/Z21）与分辨率（如 800x480）。

    ⚠️⚠️ 硬性要求：platform 与 resolution 必须由用户明确提供，禁止猜测或使用默认值。
    若用户未指定硬件平台（F133/F135/Z21）或屏幕分辨率（如 800x480），
    本工具会直接返回错误，拒绝创建——必须先向用户询问这两个参数再调用。
    """
    if not platform or not str(platform).strip():
        return {"success": False, "error": "缺少硬件平台：请先向用户询问平台（F133/F135/Z21），禁止猜测"}
    if not resolution or not str(resolution).strip():
        return {"success": False, "error": "缺少屏幕分辨率：请先向用户询问分辨率（如 800x480、480x272），禁止猜测"}
    if not re.fullmatch(r'\d+\s*[xX]\s*\d+', str(resolution).strip()):
        return {"success": False, "error": f"分辨率格式错误: {resolution}（应为 WxH，如 800x480、480x272）"}
    root = os.path.abspath(project_root)
    if os.path.isdir(root) and any(os.listdir(root)) and not force:
        return {"success": False, "error": f"目标目录非空: {root}（如需覆盖请传 force=True）"}
    plat = platform.upper()
    tpl_plat = PLATFORM_ALIASES.get(plat, plat)
    tpl = _template_dir(tpl_plat)
    if not tpl or not os.path.isdir(tpl):
        return {"success": False, "error": f"无 {platform} 的 IDE 空白模板（可用: {', '.join(IDE_TEMPLATES)}，或包内 templates/）"}
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
    tpl_name = os.path.basename(tpl)
    new_name = app_name.strip() or os.path.basename(root)
    for fn in ('.project', '.cproject'):
        p = os.path.join(root, fn)
        if os.path.isfile(p):
            txt = open(p, encoding='utf-8', errors='replace').read()
            txt = txt.replace(tpl_name, new_name)
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
        cli = flythings_attach_cli_tools(root, with_fyx=True)
    return {"success": True, "projectRoot": root, "platform": plat,
            "resolution": res_norm, "fromTemplate": tpl,
            "ftuResolution": ftu_res, "cliTools": cli, "notes": [
                "控件指针/ID宏由 IDE 编译时自动生成，logic.cc 直接使用 mXXXPtr，禁止手写定义",
                "src/uart 为系统模板：只改 ProtocolData.h / ProtocolParser.cpp 的协议解析",
                "ui/ 下放 json+ftu，用 fui pack 生成 ftu（已附带 fui.exe）",
                "logic.cc 必须保留 REGISTER_ACTIVITY_TIMER_TAB（空表也行）",
                "⚠️ 交付：项目生成后直接用 fun.exe build 编译、fun.exe launch 推送设备，"
                "无需客户手动导入 FlyThings IDE 编译烧录（fun.exe 已附带在项目根目录）"]}
