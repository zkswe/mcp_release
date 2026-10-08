# -*- coding: utf-8 -*-
"""FlyThings package ecosystem tools: search, API docs, dependency resolution, manifest generation."""
import io
import json, os, re, sys, urllib.request, xml.etree.ElementTree as ET

import platforms as _platforms  # 平台解析唯一来源（包生态键也在这里，别再各写一份）

REGISTRY_CANDIDATES = [
    # 本地包注册表（多目录合并：不同工具链/历史下载可能分散存放，全扫不漏包）
    os.environ.get('FLYTHINGS_REGISTRY', ''),      # 环境变量显式指定（最高优先）
    os.path.join(os.path.expanduser('~'), '.fsc', 'registry', 'public'),     # 09-28 版 fun 的新家（fsc）
    os.path.join(os.path.expanduser('~'), '.fun', 'registry', 'public'),     # 旧家（fun，历史包都在这里）
    os.path.join(os.path.expanduser('~'), '.fuse', 'registry', 'public'),    # 历史注册表（f133 全量 30+ 包：ntp/curl/mqtt-cxx 等）
    r'C:\zkswe\fsc\registry\public',             # fsc.exe 工具链自带注册表
]


def _registry_dirs():
    """返回所有存在的注册表目录（去重，按候选顺序）。"""
    dirs = []
    for d in REGISTRY_CANDIDATES:
        if d and os.path.isdir(d) and d not in dirs:
            dirs.append(d)
    return dirs


def _pkg_dir(pkg, platform):
    """返回包含该包的注册表目录（跨候选扫描，返回第一个存在的包目录）。
    若所有注册表都无此包，回退第一个存在的注册表（让调用方自然走 catalog/online）。"""
    np_ = _norm_platform(platform)
    for d in _registry_dirs():
        p = os.path.join(d, np_, pkg)
        if os.path.isdir(p):
            return p
    dirs = _registry_dirs()
    if dirs:
        return os.path.join(dirs[0], np_, pkg)
    # 无任何注册表目录：回退默认候选（排除空的环境变量）
    fallback = next((d for d in REGISTRY_CANDIDATES if d), REGISTRY_CANDIDATES[-1])
    return os.path.join(fallback, np_, pkg)
PACKAGE_API = 'https://package.flythings.cn/api/platforms/{platform}/packages/{pkg}/versions?simple=true'
PKG_URL = 'https://package.flythings.cn/{platform}/{pkg}/{version}'

# 包功能描述
PKG_DESC = {
    'easyui': 'UI 框架（核心，必装）', 'log': '日志库',
    'zkhardware': '硬件能力（串口 UART/GPIO/按键等）', 'zknet': '网络能力（Socket/HTTP 等）',
    'zkmedia': '媒体播放', 'zkmisc': '系统杂项（日期/设置/设备信息）',
    'base-json': 'JSON 解析', 'base-utility': '基础工具库（字符串/文件/系统）',
    'mqtt-cxx': 'MQTT C++ 封装库', 'paho-mqtt3as': 'MQTT 3.1.1 C 异步客户端（SSL）',
    'paho-mqtt3a': 'MQTT 3.1.1 C 异步客户端',
    'btstack': 'BLE 蓝牙协议栈', 'ntp': 'NTP 时间同步',
    'curl-cxx': 'HTTP C++ 封装库', 'curl': 'curl 库（HTTP 客户端）',
    'openssl': 'SSL/TLS 加密', 'mbedtls': '轻量 TLS（Z20）',
    'sqlite3': 'SQLite 数据库', 'rapidjson': 'JSON 解析（快速版）',
    'ext_widgets': '扩展控件库', 'png': 'PNG 解码', 'jpeg': 'JPEG 解码',
    'awjpegdecoder': 'JPEG 硬件解码', 'awmetadataretriever': '媒体元数据提取',
    'webpdemux': 'WebP 解码', 'nanovg': '矢量绘图',
    'freetype': 'FreeType 字体渲染', 'unibreak': 'Unicode 文本断行',
    'pinyin': '拼音输入法', 'ini': 'INI 配置解析', 'z': 'zlib 压缩',
    'cares': '异步 DNS', 'ext4': 'ext4 文件系统（Z20）',
}

# 功能关键词 → 推荐包
FEATURE_MAP = {
    'mqtt': ['mqtt-cxx'], '消息推送': ['mqtt-cxx'], '推送': ['mqtt-cxx'],
    'ssl_mqtt': ['mqtt-cxx', 'paho-mqtt3as', 'openssl'],
    'http': ['curl-cxx', 'openssl', 'z'], '网络请求': ['curl-cxx', 'openssl', 'z'],
    'http_download': ['curl-cxx', 'cares', 'openssl', 'z'], '下载': ['curl-cxx', 'cares'],
    'ota': ['curl-cxx', 'openssl', 'z'], '升级': ['curl-cxx', 'openssl', 'z'],
    '蓝牙': ['btstack'], 'ble': ['btstack'],
    'json': ['base-json', 'rapidjson'],
    '数据库': ['sqlite3'], 'sqlite': ['sqlite3'],
    '时间同步': ['ntp'], 'ntp': ['ntp'],
    '串口': ['zkhardware'], 'uart': ['zkhardware'], 'gpio': ['zkhardware'],
    '图片': ['png', 'jpeg', 'awjpegdecoder', 'webpdemux'], '图像': ['png', 'jpeg', 'awjpegdecoder'],
    '媒体': ['zkmedia', 'awmetadataretriever'], '视频': ['zkmedia'], '音频': ['zkmedia'], 'audio': ['zkmedia'],
    '拼音': ['pinyin'], '输入法': ['pinyin'],
    '加密': ['openssl', 'mbedtls'], 'ssl': ['openssl'], 'tls': ['openssl', 'mbedtls'],
    '日志': ['log'], '扩展控件': ['ext_widgets'], '控件': ['ext_widgets'],
    '矢量': ['nanovg'], '字体': ['freetype', 'unibreak'], '断行': ['unibreak'],
    '压缩': ['z'], 'dns': ['cares'], '配置文件': ['ini'], 'ini': ['ini'],
    'webp': ['webpdemux'], '元数据': ['awmetadataretriever'],
}

# 基础依赖（UI 项目默认件：easyui 核心 + 日志 + 硬件 + 网络 + 基础工具库）
BASE_DEPS = ['easyui', 'log', 'zkhardware', 'zknet', 'base-utility']

# 静态依赖表（无 Manifest.xml 的包兜底）
STATIC_DEPS = {
    'curl': [{'id': 'openssl', 'version': '^1.1.1'}, {'id': 'cares', 'version': '^1.17.2'}, {'id': 'z', 'version': '^1.2.11'}],
    'curl-cxx': [{'id': 'curl', 'version': '^8.0.0'}, {'id': 'openssl', 'version': '^1.1.1'}, {'id': 'z', 'version': '^1.2.11'}],
    'mqtt-cxx': [{'id': 'paho-mqtt3as', 'version': '^1.3.13'}, {'id': 'base-utility', 'version': '^10.0.0'}, {'id': 'z', 'version': '1.2.11'}],
    'paho-mqtt3as': [{'id': 'openssl', 'version': '^1.1.1'}],
    'paho-mqtt3a': [],
    'openssl': [{'id': 'z', 'version': '^1.2.11'}],
    'cares': [], 'z': [], 'base-json': [], 'base-utility': [], 'btstack': [],
    'easyui': [], 'log': [], 'zkhardware': [], 'zknet': [],
    'ntp': [{'id': 'base-utility', 'version': '^10.8.0'}],   # ntp@2.1.1 Manifest 真实依赖（修复：此前为空导致依赖树错误）
    'sqlite3': [], 'rapidjson': [], 'ext_widgets': [], 'png': [], 'jpeg': [],
    'awjpegdecoder': [], 'awmetadataretriever': [], 'webpdemux': [], 'nanovg': [],
    'freetype': [], 'unibreak': [], 'pinyin': [], 'ini': [], 'mbedtls': [], 'ext4': [],
    'zkmisc': [], 'zkmedia': [],
}

# 已知冲突/ABI 规则
CONFLICT_RULES = [
    {'type': 'symbol_collision', 'symbol': 'SHA1_Update',
     'packages': ['paho-mqtt3a', 'openssl'],
     'suggestion': '使用 paho-mqtt3as 替代 paho-mqtt3a（内置 SHA1 自包含），或移除显式 openssl'},
    {'type': 'abi_incompatible', 'packageA': 'curl', 'packageB': 'openssl',
     'versionA': '^8.0.0', 'versionB': '^3.0.0',
     'reason': 'curl 预编译库使用 OpenSSL 1.x API（EVP_PKEY_id, SSL_get_peer_certificate），OpenSSL 3.0 已移除',
     'suggestion': 'openssl 版本降到 1.1.1-g'},
]

SEARCH_KEYWORDS = {
    'mqtt': 'mqtt', 'json': 'json', 'http': 'http', 'curl': 'curl', 'ssl': 'ssl',
    'tls': 'tls', 'ota': 'ota', 'ble': 'ble', '蓝牙': 'ble', 'audio': 'audio',
    '音频': 'audio', 'media': 'media', '加密': 'ssl', 'database': 'sqlite',
    '数据库': 'sqlite', 'json解析': 'json',
}

# 平台别名表改由 platforms.py 提供（v0.27.41 起单一来源）；保留同名常量供旧调用方兼容。
# 以前这里只认 v85x 家族（缺 F133EMMC / F136 / T113STDCXX 等），与建工程侧的
# platforms.PLATFORMS 不是同一套 → 同一个平台名，包查询认、建工程不认。
PLATFORM_ALIAS = _platforms.PACKAGE_ALIASES

# 离线目录（全平台包快照，catalog_builder.py 生成；相对本文件所在目录，便于分发；PyInstaller 打包后取 _MEIPASS）
_BASE = sys._MEIPASS if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
CATALOG_PATH = os.path.join(_BASE, 'package_catalog.json')
_catalog_cache = None


def _load_catalog():
    global _catalog_cache
    if _catalog_cache is None:
        try:
            _catalog_cache = json.load(open(CATALOG_PATH, encoding='utf-8'))
        except Exception:
            _catalog_cache = {}
    return _catalog_cache


def _catalog_versions(pkg, platform):
    """从离线目录取包版本（含全部版本列表，semver 降序保险）。"""
    cat = _load_catalog()
    info = cat.get(platform, {}).get('packages', [])
    for pk in info:
        if pk.get('name') == pkg:
            vers = pk.get('versions') or ([pk.get('version')] if pk.get('version') else [])
            return _sort_versions(vers)
    return []

# 全平台包清单（f133+z20 并集；无本地缓存的平台用它 + 在线查版本）
ALL_PKG_NAMES = None

_version_cache = {}


def _norm_platform(platform):
    """平台名 → 包生态键（单一来源：platforms.package_key）。

    宽容：认不出来就原样小写（让查询按真实键去查，查不到自然回空），
    不再用白名单拦截——那会把 f136emmc/z261 这类真实平台错误地吞掉。"""
    return _platforms.package_key(platform)


def _ver_key(v):
    """版本字符串 → 可排序 key（semver 数字分段比较）。
    解决字符串排序 bug：'2.0.0' > '10.10.2'（字符串比较），
    必须按数字分段：10.10.2 > 2.0.0 > 1.0.9。
    支持 1.0.1 / 2.1.1-g / 0.0.2 / 10.10.2 等形态（尾缀忽略）。"""
    s = str(v or '').strip()
    # 去掉 build/变体尾缀（如 2.1.1-g → 2.1.1），只取前 3 段数字
    s = re.split(r'[-+]', s)[0]
    parts = re.findall(r'\d+', s)
    nums = [int(x) for x in parts[:3]]
    while len(nums) < 3:
        nums.append(0)
    return tuple(nums)


def _sort_versions(vers):
    """版本列表降序（最新在前，semver 数字比较）。"""
    return sorted(vers, key=_ver_key, reverse=True)


def _all_pkg_names():
    """全部平台包名并集（本地 registry + 离线 catalog 快照）。"""
    global ALL_PKG_NAMES
    if ALL_PKG_NAMES is None:
        reg = _scan_registry()
        names = set()
        for pkgs in reg.values():
            names.update(pkgs.keys())
        # 离线 catalog（全平台快照）补全：registry 只有已安装/下载过的包，catalog 才有完整生态
        try:
            cat = _load_catalog()
            for info in cat.values():
                if isinstance(info, dict):
                    for pk in info.get('packages', []):
                        names.add(pk.get('name'))
        except Exception:
            pass
        ALL_PKG_NAMES = sorted(names)
    return ALL_PKG_NAMES


def _online_versions(pkg, platform):
    key = f'{pkg}:{platform}'
    if key in _version_cache:
        return _version_cache[key]
    try:
        url = PACKAGE_API.format(platform=platform, pkg=pkg)
        req = urllib.request.Request(url, headers={'User-Agent': 'openclaw-mcp'})
        with urllib.request.urlopen(req, timeout=10) as r:
            raw = json.load(r)
        if isinstance(raw, list):
            ver = raw
        elif isinstance(raw, dict):
            data = raw.get('data', raw)
            if isinstance(data, dict):
                ver = data.get('items', [])
            else:
                ver = data if isinstance(data, list) else []
        else:
            ver = []
        _version_cache[key] = _sort_versions(ver)
        return _version_cache[key]
    except Exception:
        _version_cache[key] = []
        return []


def _scan_registry():
    """扫描全部注册表目录（多目录合并），返回 {平台: {包: [版本...]}}。"""
    result = {}
    for reg in _registry_dirs():
        if not os.path.isdir(reg):
            continue
        for plat in os.listdir(reg):
            pd = os.path.join(reg, plat)
            if not os.path.isdir(pd):
                continue
            plat_key = plat.lower()
            pkgs = result.setdefault(plat_key, {})
            for pkg in os.listdir(pd):
                pp = os.path.join(pd, pkg)
                if os.path.isdir(pp):
                    versions = [v for v in os.listdir(pp)
                                if os.path.isdir(os.path.join(pp, v))]
                    # 多目录版本并集（不覆盖已有，缺的补上），semver 降序
                    old = pkgs.get(pkg) or []
                    pkgs[pkg] = _sort_versions(set(old) | set(versions))
    return result


def _pkg_versions(pkg, platform):
    """取包可用版本，返回降序列表（最新在前）。
    本地 registry（升序）反转对齐；catalog/online 本就是降序。
    调用方统一取 versions[0] 为最新版本。"""
    base = _pkg_dir(pkg, platform)
    local = []
    if os.path.isdir(base):
        local = _sort_versions(v for v in os.listdir(base) if os.path.isdir(os.path.join(base, v)))
    if local:
        return local
    cv = _catalog_versions(pkg, _norm_platform(platform))
    if cv:
        return cv
    return _online_versions(pkg, _norm_platform(platform))


def _pkg_deps(pkg, platform, version=None):
    """读包依赖：优先 Manifest.xml，缺失用静态表。版本取最新（versions[0]）。"""
    versions = _pkg_versions(pkg, platform)
    v = version or (versions[0] if versions else None)
    if v:
        mf = os.path.join(_pkg_dir(pkg, platform), v, 'Manifest.xml')
        if os.path.isfile(mf):
            try:
                tree = ET.parse(mf)
                deps = [{'id': el.get('id'), 'version': el.get('version')}
                        for el in tree.getroot().findall('.//package')]
                if deps:
                    return deps
            except Exception:
                pass
    return [dict(d) for d in STATIC_DEPS.get(pkg, [])]


def _pkg_readme(pkg, platform, version=None):
    versions = _pkg_versions(pkg, platform)
    v = version or (versions[0] if versions else None)
    if not v:
        return ''
    p = os.path.join(_pkg_dir(pkg, platform), v, 'README.md')
    if os.path.isfile(p):
        try:
            return open(p, encoding='utf-8', errors='replace').read()
        except Exception:
            return ''
    return ''


def _pkg_headers(pkg, platform, version=None):
    versions = _pkg_versions(pkg, platform)
    v = version or (versions[0] if versions else None)
    if not v:
        return []
    inc = os.path.join(_pkg_dir(pkg, platform), v, 'include')
    headers = []
    if os.path.isdir(inc):
        for root, _, files in os.walk(inc):
            for fn in files:
                if fn.endswith(('.h', '.hpp')):
                    headers.append(os.path.relpath(os.path.join(root, fn), inc).replace('\\', '/'))
    return sorted(headers)


def _extract_code_blocks(text, limit=5):
    blocks = []
    for m in re.finditer(r'```(?:cpp|c\+\+|c|cc)?\s*\n(.*?)```', text or '', re.S):
        code = m.group(1).strip()
        if code:
            blocks.append(code[:600])
    return blocks[:limit]


_TYPE_WORDS = ('bool', 'void', 'int', 'float', 'double', 'char', 'unsigned', 'long',
               'short', 'size_t', 'uint8_t', 'uint16_t', 'uint32_t', 'uint64_t',
               'int8_t', 'int16_t', 'int32_t', 'int64_t', 'std::', 'const', 'virtual',
               'static', 'inline', 'explicit')

# 头文件优先级：控件/应用层在前，内部实现与三方件在后。
# 为什么要它（2026-10-05 实测）：原实现按 os.walk 顺序取，`max_classes` 一满就停，
# 于是 easyui 只给出前 8 个（app/ 与 control/Common.h），**ZKPainter 这类真正要用的控件头拿不到**。
_HEADER_PRIORITY = (
    ('control/', 0), ('window/', 1), ('app/', 2), ('manager/', 3),
    ('utils/', 4), ('media/', 5), ('json/', 6), ('os/', 7), ('system/', 8),
    ('storage/', 9), ('security/', 10), ('entry/', 11), ('ime/', 12),
)


def _header_rank(rel):
    for pre, rank in _HEADER_PRIORITY:
        if rel.startswith(pre):
            return rank
    return 50


def _iter_public_methods(lines):
    """在一个类的 `public:` 区里取方法签名（**带上下文**，不是全文件瞎扫）。

    原实现的两个错（2026-10-05 定位，正是「AI 写 painter 方法名不对」的机制）：
      ① **类名张冠李戴**：`re.findall(r'class\\s+(\\w+)')` 取文件里前 3 个 class 字面量，
         而真正导出的是 `class ZKPainter : public ZKBase`，被选中的却是 `class ZKPainterPrivate`
         （内部 Pimpl）；方法还是**全文件**扫出来的，于是原样挂到 Private 名下 → AI 拿到的是
         内部类的"方法表"。
      ② **`max_classes=8` 就停**：走目录顺序，数满 8 个类直接 break → 后面的控件头永不出现。
    另外**内部类名本身不该出现在给 AI 的 API 面上**（`*Private` / `*Impl` 是实现细节），
    这里一并过滤；方法行也不再截断到 120 字符（参数默认值就在后半截）。
    """
    out, seen = [], set()
    in_public = False
    depth = 0
    for raw in lines:
        s = raw.strip()
        if not s or s.startswith('//') or s.startswith('*') or s.startswith('/*'):
            continue
        if s.startswith('public:'):
            in_public = True
            depth = 0
            continue
        if s.startswith(('private:', 'protected:')):
            in_public = False
            continue
        if not in_public:
            continue
        depth += s.count('{') - s.count('}')
        if depth > 0:
            continue                    # 内联函数体内部：跳过（签名行已过）
        if ';' not in s or '{' in s:
            continue
        cand = s
        if not s.startswith(_TYPE_WORDS):
            m = re.search(r'\b([A-Za-z_]\w*)\s*\([^;]*\)\s*(?:const)?\s*;', s)
            if not m:
                continue
            cand = s[m.start():]
        if '`' in cand or ('"' in cand and 'return' in cand):
            continue
        if cand not in seen:
            seen.add(cand)
            out.append(cand)
    return out


def _parse_header_classes(include_dir, max_classes=8, focus=''):
    """从头文件解析**公开类与 public 方法签名**（唯一实现，被 `flythings_get_package_api` 消费）。

    `focus` 非空时只返回该类（大小写不敏感），且**不限数量**——"问一个类"是最高频用法，
    返回 8 个无关类既费 token 又误导（`ZKPainter` 与 `ZKTextView` 的方法完全不可互换）。
    """
    if not os.path.isdir(include_dir):
        return []
    want = (focus or '').strip().lower()
    files = []
    for root, _, fs in os.walk(include_dir):
        for fn in fs:
            if fn.endswith(('.h', '.hpp')):
                p = os.path.join(root, fn)
                rel = os.path.relpath(p, include_dir).replace('\\', '/')
                files.append((_header_rank(rel), rel, p))
    files.sort(key=lambda t: (t[0], t[1]))

    classes = []
    for _rank, rel, path in files:
        try:
            lines = io.open(path, encoding='utf-8', errors='replace').read().splitlines()
        except OSError as e:
            # 不静默（DESIGN_SPEC 第 3 条 / 静默 except lint）：读不了的头文件要**报到 stderr**，
            # 否则"少解析了几个类"看起来像"这个包就这些类"。
            sys.stderr.write('[warn] 头文件读不了，已跳过: %s（%s）\n'
                             % (rel, e.strerror or type(e).__name__))
            continue
        for m in re.finditer(r'^\s*class\s+(\w+)\s*(?::|\{|$)', '\n'.join(lines), re.M):
            name = m.group(1)
            if name.endswith(('Private', 'Impl')) or name in ('Class',):
                continue
            if want and name.lower() != want:
                continue
            start = '\n'.join(lines).count('\n', 0, m.start())
            end = len(lines)
            for j in range(start + 1, len(lines)):
                if re.match(r'^\s*\}?\s*;\s*$', lines[j]):
                    end = j
                    break
            methods = _iter_public_methods(lines[start:end])
            if not methods:
                continue                # 前向声明 / 无公开方法的类：不进 API 面
            classes.append({'name': name, 'header': rel, 'methods': methods})
            if want:
                return classes         # focus：拿到就走
            if len(classes) >= max_classes:
                return classes
    return classes


# 头文件特征 → 候选 package（按优先级；仅匹配明确三方库，避免误报系统/标准库）
INCLUDE_PKG_MAP = [
    (('mqtt', 'paho'), ['mqtt-cxx', 'paho-mqtt3as']),
    (('curl/', 'libcurl'), ['curl-cxx', 'curl']),
    (('rapidjson/',), ['rapidjson']),
    (('json-c/', 'cJSON.h'), ['base-json']),
    (('sqlite3',), ['sqlite3']),
    (('btstack/',), ['btstack']),
    (('openssl/',), ['openssl']),
    (('ntp',), ['ntp']),
    (('pinyin',), ['pinyin']),
    (('nanovg',), ['nanovg']),
    (('freetype',), ['freetype']),
    (('zlib.h', 'zconf.h'), ['z']),
    (('png.h',), ['png']),
    (('jpeglib.h',), ['jpeg']),
    (('webp/',), ['webpdemux']),
    (('ext_widgets',), ['ext_widgets']),
    (('unibreak',), ['unibreak']),
    (('ini.h', 'inih'), ['ini']),
]

# 内置基础包（IDE/模板自带，无需显式声明也不算缺失）
# ⚠️ 2026-09-17 口径修正：`base-utility` **不属于**此列——它不是模板/IDE 自动带的，而是「fun 生成的
#    generated/*.h 固定引用 base 头文件」所必需。曾把它当内置包 → 「老工程 Manifest 缺 base-utility」
#    被依赖检查放过，用户只看到 `fatal error: base/functional.h: No such file or directory`。
BUILTIN_PKGS = {'easyui', 'log', 'zkhardware', 'zknet', 'zkmedia', 'zkmisc'}

# ---------------- 框架基础依赖（v0.27.83）----------------
# 包 ↔ 头文件判定表（只做有实测依据的，不臆造）：
#   ① 证据（本机实测 2026-09-17）：构建目录 `<项目>/{.fsc|.fun}/<平台>/generated/event_{dispatcher,app}.{h,cpp}`
#      固定 `#include <base/functional.h>` / `base/base.h` / `base/defer.h` / `base/exception.h`
#      —— 这些文件由 fun 自己生成，任何 UI 工程第一次 build 都会出现 → 缺包必 fatal error。
#   ② ⚠️ `base/` 前缀**不是 base-utility 独占**（本机注册表实扫）：base-http-client→`base/http_*.h`、
#      base-json→`base/json_*.h`、easyui 3.0.0(Z20)→`base/fy_*.h`；故按「精确头名 + 前缀排除」判定。
FRAMEWORK_DEPS = [
    {'package': 'base-utility',
     'headers': ('base/functional.h', 'base/base.h', 'base/defer.h', 'base/exception.h'),
     'prefix': 'base/',
     'excludePrefixes': ('base/http_', 'base/json_', 'base/fy_'),
     'suggestedVersion': '^10.0.0',
     'why': 'fun 生成的 generated/event_dispatcher.h 等固定 #include <base/functional.h>',
     'fix': 'flythings_add_package(project_root, "base-utility", with_install=True)'
            '（等价：Manifest.xml 加 <package id="base-utility" version="^10.0.0"/> 后重跑 fsc install；'
            '改过 Manifest 必须重装，否则新包的 include 路径不会进 CMake）'},
]


def _read_text(path):
    """读文本（utf-8，容错）；失败回空串。"""
    try:
        with open(path, encoding='utf-8', errors='replace') as f:
            return f.read()
    except Exception:
        return ''


def _manifest_platform(root):
    """Manifest.xml 的 platform 属性（读不到回空串）。"""
    mf = os.path.join(root, 'Manifest.xml')
    if not os.path.isfile(mf):
        return ''
    m = re.search(r'<manifest\s[^>]*platform=["\']([^"\']+)["\']', _read_text(mf))
    return m.group(1) if m else ''


def _declared_packages(root):
    """Manifest.xml 里声明的 package id 集合。"""
    mf = os.path.join(root, 'Manifest.xml')
    if not os.path.isfile(mf):
        return set()
    return set(re.findall(r'<package\s+id="([^"]+)"', _read_text(mf)))


def _resolved_packages(root):
    """已**解析**（= 真装上、include 路径会进 CMake）的包集合 + 证据文件。

    来源是工具生成物（非手写）：`.fsc-lock.json`（09-28 起；旧名 `.fun-lock.json`，两代都读）+ `.deps.lock`（IDE 版本锁）。
    用途：避免「Manifest 没写、但被传递依赖装上了」的误报（实测：easyui 会带出 base-utility）。
    返回 (set, [证据文件名])。"""
    pkgs, ev = set(), []
    for _lock in ('.fsc-lock.json', '.fun-lock.json'):
        fp = os.path.join(root, _lock)
        if not os.path.isfile(fp):
            continue
        try:
            data = json.loads(_read_text(fp))
        except Exception:
            data = {}
        for _plat, items in (data.get('dependencies') or {}).items():
            if not isinstance(items, dict):
                continue
            pkgs.update(k for k in items if isinstance(k, str))
            for v in items.values():      # 条目里嵌的传递依赖
                if isinstance(v, dict) and isinstance(v.get('dependencies'), dict):
                    pkgs.update(k for k in v['dependencies'] if isinstance(k, str))
        ev.append(_lock)
    dp = os.path.join(root, '.deps.lock')
    if os.path.isfile(dp):
        ids = re.findall(r'"id"\s*:\s*"([^"]+)"', _read_text(dp))
        if ids:
            pkgs.update(ids)
            ev.append('.deps.lock')
    return pkgs, ev


def _registry_header_path(platform, pkg, header):
    """本机包注册表里找 <注册表>/<平台键>/<包>/<版本>/include/<头文件>，返回命中的绝对路径（无则空串）。
    只作**证据**（可解析的头文件长什么样），不决定判定（判定看 Manifest/锁，注册表里有不等于工程 include 路径里有）。"""
    key = _norm_platform(platform or _platforms.DEFAULT_PLATFORM)
    hits = []
    for d in _registry_dirs():
        pdir = os.path.join(d, key, pkg)
        if not os.path.isdir(pdir):
            continue
        try:
            vers = os.listdir(pdir)
        except Exception:
            continue
        for ver in vers:
            p = os.path.join(pdir, ver, 'include', *header.split('/'))
            if os.path.isfile(p):
                hits.append((_ver_key(ver), p))
    return sorted(hits)[-1][1] if hits else ''


def _is_framework_header(dep, inc):
    """include 是否属于该框架包（精确头名优先；前缀匹配时排除其它包已占用的子前缀，如 base/http_*）。"""
    low = (inc or '').strip().lower()
    if low in dep['headers']:
        return True
    if not low.startswith(dep['prefix']):
        return False
    return not any(low.startswith(x) for x in dep['excludePrefixes'])


def _framework_include_evidence(root, dep):
    """找「代码」或「fun 生成的 generated/*.h」里对该框架包头文件的引用。返回 [{'file','include'}]。"""
    roots = []
    src = os.path.join(root, 'src')
    if os.path.isdir(src):
        roots.append(src)
    # fun 生成物（generated/{event*,ui_main}.{h,cpp}）：.fsc（09-28 起）/ .fun（旧版）都扫
    for _name in ('.fsc', '.fun'):
        fun_dir = os.path.join(root, _name)
        if os.path.isdir(fun_dir):
            try:
                for plat in sorted(os.listdir(fun_dir)):
                    g = os.path.join(fun_dir, plat, 'generated')
                    if os.path.isdir(g):
                        roots.append(g)
            except Exception:
                pass
    out = []
    for r in roots:
        for base, _, files in os.walk(r):
            for fn in files:
                if not fn.endswith(('.h', '.hpp', '.c', '.cc', '.cpp')):
                    continue
                p = os.path.join(base, fn)
                txt = _read_text(p)
                if not txt:
                    continue
                for m in re.finditer(r'#\s*include\s*[<"]?([^">\n]+)[">]', txt):
                    if _is_framework_header(dep, m.group(1)):
                        out.append({'file': os.path.relpath(p, root).replace('\\', '/'),
                                    'include': m.group(1).strip()})
    return out


def framework_dep_status(project_root, platform=''):
    """框架基础依赖体检（v0.27.83）：包 ↔ 头文件 ↔ Manifest/依赖锁。

    判定 `ok` = Manifest 已声明 **或** 依赖已解析（传递依赖装上也算 —— 不制造误报）。
    判定 `required` = 代码/fun 生成的 generated/*.h 已引用该包头文件，或工程本身是 fun 会生成
                     这些代码的 UI 工程（有 ui/*.ftu 且 fsc.json 不是 executable）。
    缺包时回 `missing[]`，每项带实测证据（file/include）、why 与可照做的 fix。
    返回 {success, projectRoot, platform, ok, deps[], missing[], hint}。"""
    root = os.path.abspath(project_root)
    if not os.path.isdir(root):
        return {'success': False, 'error': '项目目录不存在: %s' % root}
    plat = _manifest_platform(root) or platform or _platforms.DEFAULT_PLATFORM
    declared = _declared_packages(root)
    resolved, res_ev = _resolved_packages(root)
    ui_dir = os.path.join(root, 'ui')
    has_ui = (os.path.isdir(ui_dir)
              and any(f.endswith('.ftu') for f in os.listdir(ui_dir)))
    is_bin = False                                # fsc create --type bin：不出 UI 生成代码，不适用
    fj = os.path.join(root, 'fsc.json')
    if os.path.isfile(fj):
        try:
            is_bin = json.loads(_read_text(fj)).get('type') == 'executable'
        except Exception:
            is_bin = False
    deps, missing = [], []
    for dep in FRAMEWORK_DEPS:
        pkg = dep['package']
        ev = _framework_include_evidence(root, dep)
        required = bool(ev) or (has_ui and not is_bin)
        d = {'package': pkg, 'required': required,
             'declared': pkg in declared, 'resolved': pkg in resolved,
             'resolvedEvidence': list(res_ev),
             'evidence': ev[:5], 'evidenceCount': len(ev),
             'headers': list(dep['headers']), 'why': dep['why'],
             'headerInRegistry': _registry_header_path(plat, pkg, dep['headers'][0]),
             'fix': dep['fix']}
        d['ok'] = bool(d['declared'] or d['resolved'])
        if required and not d['ok']:
            first = ev[0] if ev else None
            inc = first['include'] if first else dep['headers'][0]
            where = ('%s（%s）' % (first['file'], inc) if first else
                     'fun 生成的 generated/*.h（%s）' % dep['headers'][0])
            d['include'] = inc
            d['msg'] = ('框架基础依赖缺失：%s引用了 base 头文件，但 Manifest 未声明 %s'
                        '（%s）→ fsc build 会 fatal error: base/functional.h: No such file or directory'
                        % (where, pkg, dep['why']))
            d['hint'] = d['msg'] + '；修复：' + dep['fix']
            missing.append(d)
        deps.append(d)
    return {'success': True, 'projectRoot': root, 'platform': plat,
            'declaredPackages': sorted(declared), 'resolvedPackages': sorted(resolved),
            'resolvedEvidence': res_ev, 'ok': not missing, 'deps': deps, 'missing': missing,
            'hint': (missing[0]['hint'] if missing else '')}


def _font_tiers(root, explicit_tier=''):
    """**选字库**（唯一实现在 `font_tools.font_tier_menu`，本函数只做包装与错误兜底）。

    返回 `(fontTiers, issues)`：`fontTiers` 给三档菜单 + 按本工程字集的推荐档 + 现工程档位；
    `issues` 只在「显式指定的档位不存在」时给一条可执行提示（不静默忽略）。
    菜单算不出来时**不静默**：`fontTiers` 带 `enabled:false` + `error`。
    """
    out, issues = {}, []
    try:
        import font_tools as ftools
        out = ftools.font_tier_menu(root)
    except Exception as e:                      # noqa: BLE001
        return ({'enabled': False, 'error': '字库档位菜单不可用: %s: %s'
                 % (type(e).__name__, e), 'hint': '见 font_tools.font_tier_menu'}, issues)
    # 显式指定档位 → 与真源档位表对账（错了要说，不许当成生效）
    if explicit_tier:
        tiers = out.get('tierOrder') or []
        if explicit_tier in tiers:
            row = next((t for t in (out.get('tiers') or []) if t.get('tier') == explicit_tier), {})
            out['requested'] = {'tier': explicit_tier, 'known': True,
                                'bytes': row.get('bytes'), 'sizeKB': row.get('sizeKB'),
                                'command': row.get('command')}
        else:
            out['requested'] = {'tier': explicit_tier, 'known': False}
            issues.append({'kind': 'fontTier', 'tier': explicit_tier, 'known': False,
                           'msg': '指定的字库档位不存在: %r' % explicit_tier,
                           'hint': '可选档位: %s（按本工程字集的推荐档见 fontTiers.recommend）'
                                   % ('、'.join(tiers) or '(取不到)')})
    return out, issues


def _font_tiers_only(root, error):
    """src 缺失时的降级返回：依赖体检失败，但**选字库照常给**（各自独立，不互相拖累）。"""
    font_tiers, tier_issues = _font_tiers(root)
    out = {'success': False, 'error': error, 'projectRoot': root, 'depsOk': False,
           'missingDependencies': [], 'fontTiers': font_tiers, 'fontIssues': tier_issues,
           'hint': ('依赖体检需要 src/；选字库不依赖它 —— 见 fontTiers'
                    '（菜单 + 按本工程字集的推荐档 + 现档位）')}
    return out


def flythings_check_project_deps(project_root, platform='F133', device='',
                                 font_check='auto', font_tier='', font_apply=False):
    """扫描项目代码 include 的三方库，与 Manifest.xml 已声明依赖对比，返回缺失依赖。
    新建/交付项目前调用，避免"用了三方库但没声明"导致编译失败。
    另含**框架基础依赖**体检（v0.27.83）：base 头文件（含 fun 生成的 generated/*.h）→ 必须有 base-utility。
    另含**字体体检**（v0.27.86，`fontCheck` 字段）：缺中文字库 / prefs 引用断链 → `fontIssues` 给结论与
    一键修复命令；默认**只报不投**（`font_apply=True` 才真投递；`flythings_build_ui_flow` 默认自动投递）。
    传 `device='<serial|IP:5555>'` 时额外扫设备字体；不传则只做工程侧检查（不碰 adb）。

    另含**选字库**（2026-10-05，`fontTiers` 字段）：三档菜单（体积读字体文件实际字节）+ 按本工程
    实际字集算的**推荐档** + 现工程档位 → `recommend.nextAction` 直接给可执行下一步。
    ⚠️ 优先用现成三档（`font_tier='common'|'full'|'multi'`）；**自己裁字库只在存储/内存异常时用**
    （`fontTiers.subset.when`）—— 日常缺中文请选档，不要一上来就裁。"""
    root = os.path.abspath(project_root)
    src = os.path.join(root, 'src')
    if not os.path.isdir(src):
        # 依赖体检没法做，但**选字库是独立能力**（只看 ui/*.json 的文案字集）→ 照样返回，
        # 不让调用方为了选档先造一个 src（不返回空的失败）。
        return _font_tiers_only(root, f'src 目录不存在: {src}')
    # 1. 收集全部 include
    includes = set()
    for base, _, files in os.walk(src):
        for fn in files:
            if not fn.endswith(('.cc', '.cpp', '.h', '.hpp')):
                continue
            p = os.path.join(base, fn)
            try:
                text = open(p, encoding='utf-8', errors='replace').read()
            except Exception:
                continue
            for m in re.finditer(r'#\s*include\s*[<"]([^">]+)[">]', text):
                includes.add(m.group(1).strip())
    # 2. 匹配 package
    detected = {}   # include -> [pkgs]
    for inc in sorted(includes):
        low = inc.lower()
        for pats, pkgs in INCLUDE_PKG_MAP:
            if any(p in low for p in pats):
                detected.setdefault(inc, []).extend(pkgs)
    # 3. Manifest 已声明
    declared = _declared_packages(root)
    # 4. 缺失依赖
    missing = []
    for inc, pkgs in sorted(detected.items()):
        need = [p for p in pkgs if p not in BUILTIN_PKGS]
        if need and not any(p in declared for p in need):
            missing.append({'include': inc, 'recommendedPackages': need,
                            'hint': '在 Manifest.xml 添加依赖或移除该 include'})
    # 5. 框架基础依赖（v0.27.83）：base 头文件（含 fun 生成的 generated/*.h）→ Manifest 必须有 base-utility
    fw = framework_dep_status(root, platform)
    for d in fw.get('missing', []):
        missing.append({'include': d['include'], 'recommendedPackages': [d['package']],
                        'kind': 'framework', 'declared': d['declared'], 'resolved': d['resolved'],
                        'evidence': d['evidence'], 'msg': d['msg'], 'hint': d['hint'],
                        'fix': d['fix']})
    # 6. 字体体检（v0.27.86）：缺中文字库 / prefs 字体引用断链 → fontCheck + fontIssues
    #    默认只报不投（font_apply=True 才投递）→ 本 op 默认仍是「只读体检」；
    #    传 device= 才扫设备字体（不传就不碰 adb，离线可跑）。
    font, font_issues = {}, []
    try:
        import font_tools as ftools
        st = ftools.font_preflight(root, platform, device=device, font_check=font_check,
                                   font_tier=font_tier, apply=bool(font_apply),
                                   allow_device=bool(device))
        font = ftools.compact(st)
        font['warnings'] = st.get('warnings') or []
        if st.get('info'):
            font['info'] = st['info']
        if st.get('missingChinese'):
            tier = st.get('tier') or 'common'
            fix = ftools.repair_command(root, tier)
            where = ('设备侧扫描' if st.get('deviceScanned')
                     else '工程侧检查（未连设备）')
            font['repair'] = fix
            # 硬判据（v0.27.87）：报出 GB2312 一级覆盖率（不看体积猜）
            cov = ''
            if st.get('source') == 'cmap':
                cov = '，GB2312 一级覆盖率 %s%%（阈值 90%% 算 ok）' % st.get('cmapCoverageGB2312L1')
            font_issues.append({
                'kind': 'font', 'verdict': st.get('verdict'),
                'missingChinese': True, 'maxFontBytes': st.get('maxFontBytes'),
                'advisedTier': tier,
                'source': st.get('source'),
                'cmapCoverageGB2312L1': st.get('cmapCoverageGB2312L1'),
                'checkedFont': st.get('checkedFont'),
                'delivered': st.get('delivered'),
                'msg': ('缺中文字库（%s）：判定=%s%s，最大字体 %s KB → 界面汉字会变方块；默认投 %s 档'
                        % (where, st.get('verdict'), cov, st.get('maxFontKB'), tier)),
                'hint': ('直接跑 flythings_build_ui_flow（默认自动投递 common）或本 op 传 '
                         'font_apply=True；命令行：' + fix)})
        elif st.get('enabled') and st.get('verdict') in ('partial_cjk', 'project_partial_cjk'):
            font_issues.append({'kind': 'font', 'verdict': st.get('verdict'),
                                'missingChinese': False,
                                'maxFontBytes': st.get('maxFontBytes'),
                                'advisedTier': 'full',
                                'msg': '字库只到「常用字」级别（%s KB）：有生僻字需求换 full 档'
                                       % st.get('maxFontKB'),
                                'hint': "flythings_build_ui_flow(font_tier='full')（生僻字）"
                                        "或 font_tier='multi'（多语言/日韩）"})
    except Exception as e:                      # 字体体检出错不影响依赖体检结果
        font = {'enabled': False,
                'error': '字体体检异常: %s: %s' % (type(e).__name__, e)}
        font_issues.append({'kind': 'font', 'enabled': False,
                            'msg': font['error'], 'hint': '见 font_tools.py'})
    # 7. 选字库（2026-10-05）：三档菜单 + 按本工程字集的推荐档 + 现工程档位。
    #    「选档」是日常口子，「自己裁字库」只在存储/内存异常时用（口径见 fontTiers.subset）。
    #    与 #6 的 fontCheck 分工：fontCheck 答「设备/工程现在缺不缺中文」，fontTiers 答「该选哪档」。
    font_tiers, tier_issues = _font_tiers(root, font_tier)
    font_issues.extend(tier_issues)
    return {'success': True, 'projectRoot': root, 'platform': platform,
            'declaredPackages': sorted(declared),
            'detectedIncludes': sorted(detected.keys()),
            'missingDependencies': missing,
            'frameworkDeps': fw.get('deps', []),
            'fontCheck': font,
            'fontIssues': font_issues,
            'fontTiers': font_tiers}


def flythings_list_packages(platform=None):
    """列出 FlyThings 依赖包生态（指定平台或全部），含功能描述与版本。
    本地无缓存的平台（如 Z21/V85x）自动在线查询版本。"""
    reg = _scan_registry()
    platforms = [platform] if platform else list(reg.keys())
    out = {'platforms': {}}
    for p in platforms:
        np_ = _norm_platform(p)
        pkgs = reg.get(np_, {})
        if pkgs:
            items = [{'name': n, 'version': v[-1] if v else None,
                      'description': PKG_DESC.get(n, ''), 'hasCard': _has_card(n)}
                     for n, v in sorted(pkgs.items())]
        else:
            # 无本地缓存：用离线目录（全平台快照）
            cat = _load_catalog()
            cat_pkgs = {pk['name']: (pk.get('versions') or [pk.get('version')] if pk.get('version') else [])
                        for pk in cat.get(np_, {}).get('packages', [])}
            if cat_pkgs:
                items = [{'name': n,
                          'version': v[0] if v else None,
                          'description': PKG_DESC.get(n, ''),
                          'versionSource': 'catalog'}
                         for n, v in sorted(cat_pkgs.items())]
            else:
                items = []
                for n in _all_pkg_names():
                    vers = _online_versions(n, np_)
                    items.append({'name': n,
                                  'version': vers[0] if vers else None,
                                  'description': PKG_DESC.get(n, ''),
                                  'versionSource': 'online' if vers else 'unknown'})
        out['platforms'][p] = items
    return {'success': True, 'count': sum(len(v) for v in out['platforms'].values()),
            'platforms': out['platforms']}


def flythings_query_package(package, platform='F133'):
    """查询依赖包在指定平台的可用版本（本地 registry → 离线目录 → 在线）。"""
    np_ = _norm_platform(platform)
    base = _pkg_dir(package, platform)
    local_versions = []
    if os.path.isdir(base):
        local_versions = _sort_versions(v for v in os.listdir(base)
                                        if os.path.isdir(os.path.join(base, v)))
    if local_versions:
        return {'success': True, 'package': package, 'platform': platform,
                'description': PKG_DESC.get(package, ''),
                'cardSummary': (package_card(package) or {}).get('summary') or None,
                'hasCard': _has_card(package),
                'versions': local_versions, 'source': 'local registry'}
    cv = _catalog_versions(package, np_)
    if cv:
        return {'success': True, 'package': package, 'platform': platform,
                'description': PKG_DESC.get(package, ''),
                'versions': cv, 'source': 'offline catalog'}
    online = _online_versions(package, np_)
    return {'success': True, 'package': package, 'platform': platform,
            'description': PKG_DESC.get(package, ''),
            'cardSummary': (package_card(package) or {}).get('summary') or None,
            'hasCard': _has_card(package),
            'versions': online, 'source': 'package.flythings.cn' if online else 'unknown'}


def flythings_search_package(keyword, platform='F133'):
    """根据功能关键词搜索可用 package（mqtt/json/http/ssl/ble/ota/audio 等）。
    候选包来源：本地 registry 包名 ∪ 离线 catalog 全平台快照 ∪ 在线探测。
    ⚠️ 只依赖本地 registry 会漏掉未下载过的包（如 z21 上 curl-cxx/ntp），必须叠加 catalog。"""
    kw = str(keyword).strip().lower()
    mapped = SEARCH_KEYWORDS.get(kw, kw)
    np_ = _norm_platform(platform)
    # 候选包名：registry ∪ catalog（关键修复：registry 只有已装/已下载包，catalog 是全量快照）
    cand = {}
    reg = _scan_registry()
    reg_pkgs = reg.get(np_, {})
    cand.update(reg_pkgs)
    try:
        cat = _load_catalog()
        for pk in cat.get(np_, {}).get('packages', []):
            name = pk.get('name')
            if name and name not in cand:
                cand[name] = pk.get('versions') or ([pk.get('version')] if pk.get('version') else [])
    except Exception:
        pass
    if not cand:
        cand = {n: _online_versions(n, np_) for n in _all_pkg_names()}
    results = []
    for name, versions in sorted(cand.items()):
        hay = f'{name} {PKG_DESC.get(name, "")}'.lower()
        if mapped in name.lower() or mapped in hay:
            v = versions[0] if versions else None
            deps = _pkg_deps(name, platform, v)
            results.append({
                'id': name, 'version': v,
                'description': PKG_DESC.get(name, ''),
                'url': PKG_URL.format(platform=np_, pkg=name, version=v) if v else None,
                'dependencies': deps,
            })
    return {'success': True, 'keyword': keyword, 'platform': platform, 'packages': results}


def flythings_get_package_api(package_id, platform='F133', version=None, focus=''):
    """获取 package 的头文件路径、类方法签名、使用示例。

    `focus` = 只看某一个类（**不看**该包其它类）。为什么要有它（2026-10-05）：
    ① 问"`ZKPainter` 怎么画弧"是最高频用法，而要用的那个类**常排在 8 名之外**——
       原实现 `max_classes=8` 且按目录顺序取，easyui 永远只给前 8 个（app/ 与 Common.h），
       `ZKPainter` 根本不出现；② 顺带返回 8 个无关类既费 token 又误导。
    签名一律来自**本地已安装的 registry 头文件**（`~/.fsc/registry/public/<平台>/<包>/<版本>/include`），
    不是本仓抄的副本 —— 换平台/换版本自动跟着变。⚠️ **它由 `fsc install` 落盘**（2026-10-05 用户口径）：
    `registry/public/` 下**只有跑过 install 的平台**（本机实测只有 v85x / z20），没装过的平台
    即使"服务端有该包"也拿不到头文件 —— 这种情况这里**明确报错并给 fix 命令**，不返回空的类表。
    """
    versions = _pkg_versions(package_id, platform)
    v = version or (versions[0] if versions else None)  # versions 降序，[0] 为最新
    if not versions:
        return {'success': False, 'error': f'平台 {platform} 未找到包 {package_id}',
                'card': package_card(package_id)}
    inc = os.path.join(_pkg_dir(package_id, platform), v, 'include')
    if not os.path.isdir(inc):
        # ⚠️ **不静默**（2026-10-05 实测缺口）：目录不在时原实现返回 success=True + 空 headers/classes，
        # 调用方分不清"这个平台没装包"与"这个包没有可解析的类" —— 前者要装、后者要用别的手段看 API。
        # 报错文案必须给出**可执行**的下一步（DESIGN_SPEC 第 3 条：读不到要显式降级并说怎么复验）。
        #
        # 2026-10-05 补（需求方口径「远端提供的这些库是否有对应材料让 AI 正确处理」）：
        # `success` 仍为 False（"平台级精确签名没拿到"这个事实不能掩盖，有用例钉着），
        # 但**必须把仓库包卡里的离线 API 面一并给出** —— `packages/<包>/package.yaml` 就是为 AI 写的
        # （summary / entry / api 签名 / usage_cpp / 真机 verified / gotchas），它是**确定性、离线、可复现**的。
        # 否则调用方看到 False 就止步，明明手里已经有一份能直接用的 API 资料。
        card = package_card(package_id)
        offline = None
        if card:
            offline = {
                'source': card.get('cardPath'),
                'kind': 'repo-card',
                'summary': card.get('summary'),
                'entry': card.get('entry'),
                'headers': card.get('headers'),
                'api': card.get('api'),
                'usage': card.get('usage_cpp'),
                'gotchas': card.get('gotchas'),
                'verified': card.get('verified'),
                'readme': card.get('readmePath'),
            }
        return {'success': False,
                'error': (f'{platform} 的 {package_id} 头文件不在本机（{inc} 不存在）'
                          f'—— 本机 registry/public/ 下只有**跑过 `fsc install` 的平台**'),
                'hint': (f'先在该平台工程里跑一次安装：`fsc install --platform {str(platform).lower()}`'
                         '（或 `flythings_add_package(project_root, "<包名>", with_install=True)`），'
                         '然后重试本 op；**只是想看 API 怎么用**则不必装 —— 直接用下面的 offlineApi'),
                'offlineApi': offline,
                'offlineNote': ('以上来自仓库包卡（packages/%s/package.yaml，头文件实读写成、含真机实测坑），'
                                '**离线可用、可复现**；差异点：easyui 等库的**版本**在不同平台不同，'
                                '若要逐字节的当平台签名，仍需 fsc install 后重试' % package_id)
                               if offline else ('仓库里没有 %s 的包卡，装好后重试' % package_id),
                'version': v, 'platform': platform, 'package': package_id,
                'card': card}
    classes = _parse_header_classes(inc, focus=focus)
    readme = _pkg_readme(package_id, platform, v)
    examples = _extract_code_blocks(readme)
    if not examples:
        # 静态示例兜底（常用包）
        static_ex = {
            'mqtt-cxx': 'mqtt::Client::Configuration conf;\nconf.server = "mqtt://host:port";\nconf.client_id = "device_id";\nconf.username = "user";\nconf.password = "pass";\nauto client = std::unique_ptr<mqtt::Client>(new mqtt::Client(conf));',
            'base-json': 'base::JSONObject obj;\nobj.put("key", "value");\nauto parsed = base::JSONObject::parse(str);',
        }
        if package_id in static_ex:
            examples = [static_ex[package_id]]
    return {'success': True, 'package': package_id, 'version': v,
            'platform': platform,
            'headers': _pkg_headers(package_id, platform, v),
            'classes': classes, 'examples': examples,
            'card': package_card(package_id)}


def flythings_resolve_dependencies(packages, platform='F133'):
    """递归解析 package 完整依赖树，检测符号冲突与 ABI 不兼容。packages 为 [{'id','version'}]。"""
    if isinstance(packages, str):
        packages = json.loads(packages) if packages.startswith('[') else [{'id': packages}]
    tree, resolved, seen = {}, [], set()

    def walk(pkg_id, version=None, depth=0):
        if depth > 6:
            return
        key = f'{pkg_id}:{version or "*"}'
        if key in seen:
            return
        seen.add(key)
        deps = _pkg_deps(pkg_id, platform, version)
        tree[key] = {'depends': [f"{d['id']}:{d['version']}" for d in deps]}
        if pkg_id not in resolved:
            resolved.append(pkg_id)
        for d in deps:
            walk(d['id'], d['version'], depth + 1)

    for p in packages:
        walk(p.get('id'), p.get('version'))

    # 冲突检测
    conflicts = []
    ids = set(resolved)
    if 'paho-mqtt3a' in ids and 'openssl' in ids:
        conflicts.append(CONFLICT_RULES[0])
    for rule in CONFLICT_RULES:
        if rule['type'] == 'abi_incompatible':
            if rule['packageA'] in ids and rule['packageB'] in ids:
                conflicts.append(rule)
    return {'success': True, 'dependencyTree': tree,
            'resolvedPackages': resolved, 'conflicts': conflicts}


def flythings_generate_manifest(features, platform='F133'):
    """根据功能需求自动生成 Manifest.xml（含依赖递归补齐与 resolution 说明）。"""
    if isinstance(features, str):
        features = [f.strip() for f in str(features).split(',') if f.strip()]
    selected, resolution = [], {}
    for f in features:
        fl = str(f).strip().lower()
        matched = False
        for key, pkgs in FEATURE_MAP.items():
            if key.lower() in fl or (len(fl) >= 2 and fl in key.lower()):
                selected.extend(pkgs)
                resolution[f] = ' + '.join(pkgs)
                matched = True
                break
        if not matched and fl in PKG_DESC:
            selected.append(fl)
            resolution[f] = fl
    # 递归补齐依赖：显式需求缺失 → missing；传递依赖缺失 → 视为系统件过滤
    deps, seen = [], set()
    queue = list(BASE_DEPS + selected)
    missing, system_deps = [], []
    explicit = set(BASE_DEPS) | set(selected)
    reg = _scan_registry()
    np_ = _norm_platform(platform)
    local_vers = reg.get(np_, {})

    def _resolve_version(p):
        lv = local_vers.get(p) or []
        if lv:
            return _sort_versions(lv)[0], 'local'  # semver 降序取最新（listdir 无序）
        cv = _catalog_versions(p, np_)
        if cv:
            return _sort_versions(cv)[0], 'catalog'
        ov = _sort_versions(_online_versions(p, np_))[:1]
        if ov:
            return ov[0], 'online'
        return None, 'unknown'

    while queue:
        p = queue.pop(0)
        if p in seen:
            continue
        seen.add(p)
        ver, src = _resolve_version(p)
        if not ver:
            if p in explicit:
                missing.append(p)      # 用户需求/基础包缺失：如实报告
                deps.append(p)         # 保留（version ?），让用户知晓
            else:
                system_deps.append(p)  # 传递依赖缺失：系统内部件，过滤
                continue
        else:
            deps.append(p)
        for d in _pkg_deps(p, platform):
            if d['id'] not in seen:
                queue.append(d['id'])

    # ⚠️ 只显式列出用户需求 + 基础依赖（explicit 集合）；传递依赖不写入 manifest：
    # 宿主包（如 curl-cxx）自带 Manifest.xml 声明了其依赖（如 curl@8.12.1-mbedtls 变体），
    # fsc install 会自动解析；显式再列一份 curl@8.12.1 反而与变体版本冲突导致安装失败。
    pkg_list = []
    for p in deps:
        if p not in explicit:
            continue
        ver, src = _resolve_version(p)
        pkg_list.append({'id': p, 'version': ver or '?', 'versionSource': src})
    transitive = sorted(set(deps) - explicit)
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', '<!DOCTYPE flythings>',
             f'<manifest cyclicDependency="true" platform="{platform}">',
             f'\t<dependencies enableOnPlatforms="{platform}">']
    for p in pkg_list:
        lines.append(f'\t\t<package id="{p["id"]}" version="{p["version"]}"></package>')
    lines.append('\t</dependencies>')
    lines.append('</manifest>')
    # resolution 附加说明
    note = ''
    if 'ssl_mqtt' in [str(x).lower() for x in features]:
        note = 'openssl 1.1.1-g 与 curl ABI 兼容；paho-mqtt3as 替代 paho-mqtt3a 避免 SHA1 冲突'
    if transitive:
        note = (note + '；' if note else '') + f'以下传递依赖不显式列出（宿主包 Manifest 已声明，fsc install 自动解析，避免版本冲突）：{", ".join(transitive)}'
    if missing:
        note = (note + '；' if note else '') + f'以下包在 {platform} 平台未找到（版本不可用，需确认平台支持或包名）：{", ".join(missing)}'
    if system_deps:
        note = (note + '；' if note else '') + f'以下为包内部组件已自动过滤（随宿主包分发，无需显式声明）：{", ".join(sorted(set(system_deps)))}'
    return {'success': True, 'platform': platform,
            'manifest': '\n'.join(lines),
            'resolution': resolution, 'note': note,
            'missingPackages': missing}


def flythings_recommend_manifest(features, platform='F133'):
    """（兼容旧接口）根据功能需求推荐 Manifest.xml 依赖配置。"""
    r = flythings_generate_manifest(features, platform)
    r['manifestXml'] = r.pop('manifest')
    return r


def flythings_add_package(project_root, package, version=None, platform=None, with_install=True):
    """把 package 添加进项目 Manifest.xml 并执行 fsc install 拉取依赖（添加包闭环流程）。

    - 版本解析顺序：本地 registry → 离线 catalog → 在线（semver 取最新，不依赖包实体是否存在）
    - 已声明同包则更新版本；未声明则追加 <package id version/>
    - with_install=True（默认）执行 fsc install 同步依赖（Manifest 变更后自动拉取）
    返回 {success, package, version, versionSource, manifestPath, install}。
    用户说「给项目加个 XXX 包 / 项目要用 MQTT 需要加依赖」时调用。
    """
    root = os.path.abspath(project_root)
    mf = os.path.join(root, 'Manifest.xml')
    if not os.path.isfile(mf):
        return {'success': False, 'error': f'Manifest.xml 不存在: {mf}'}
    # 平台探测：参数 > Manifest 平台
    if not platform:
        try:
            mtext = open(mf, encoding='utf-8', errors='replace').read()
        except Exception:
            mtext = ''
        m = re.search(r'<manifest\s+platform=["\']([^"\']+)["\']', mtext)
        if m:
            platform = m.group(1)
    if not platform:
        return {'success': False, 'error': '无法确认平台（缺 Manifest platform 属性），请显式传 platform'}
    pkg = str(package).strip()
    if not pkg:
        return {'success': False, 'error': 'package 名为空'}

    # 1. 解析版本（semver 取最新；不纠结包实体是否存在，catalog/online 兜底）
    vers = _pkg_versions(pkg, platform)
    v = version or (vers[0] if vers else None)
    if not v:
        return {'success': False, 'error': f'平台 {platform} 未找到包 {pkg}（本地/catalog/在线均无版本）'}
    v = str(v).strip()

    # 2. 读取并更新 Manifest（保留原格式与已有依赖）
    try:
        mtext = open(mf, encoding='utf-8', errors='replace').read()
    except Exception as e:
        return {'success': False, 'error': f'读取 Manifest 失败: {e}'}
    dep_re = re.compile(r'(<dependencies[^>]*>)(.*?)(</dependencies>)', re.S)
    m = dep_re.search(mtext)
    if not m:
        return {'success': False, 'error': 'Manifest 缺少 <dependencies> 区块'}
    open_tag, body, close_tag = m.group(1), m.group(2), m.group(3)
    # 同包已声明 → 更新版本
    pkg_re = re.compile(r'(<package\s+id="' + re.escape(pkg) + r'"\s+version=")([^"]*)(")')
    if pkg_re.search(body):
        new_body = pkg_re.sub(r'\g<1>' + v + r'\3', body)
        action = 'update'
    else:
        indent = '\t\t'
        new_body = body.rstrip() + '\n' + indent + f'<package id="{pkg}" version="{v}"></package>\n'
        action = 'add'
    mtext = mtext[:m.start()] + open_tag + new_body + close_tag + mtext[m.end():]
    try:
        with open(mf, 'w', encoding='utf-8') as f:
            f.write(mtext)
    except Exception as e:
        return {'success': False, 'error': f'写入 Manifest 失败: {e}'}

    # 3. fsc install 同步依赖（Manifest 变更后拉取新包）
    install = {'executed': False}
    if with_install:
        try:
            import project_tools as _pt
            ri = _pt._run_fun('install', root)
            install = {'executed': True, 'success': ri['success'],
                       'detail': (ri.get('stderr') or ri.get('stdout') or ri.get('error') or '')[-400:]}
            if not ri['success']:
                install['note'] = 'fsc install 失败（网络/工具链问题），Manifest 已更新；重试 flythings_build_ui_flow 或手动 fsc install'
        except Exception as e:
            install = {'executed': True, 'success': False, 'error': str(e)}
    return {'success': True, 'package': pkg, 'version': v, 'platform': platform,
            'versionSource': 'local' if vers else 'catalog/online',
            'action': action, 'manifestPath': mf, 'install': install}

# ==================== 仓库内置「包卡」（packages/<包>/package.yaml） ====================
# 背景（2026-09-29 审查报告 P0①）：AI 通过工具只能看到 registry 的头文件/README，
# 我们写的 11 张包卡（summary / api / usage_cpp / gotchas / verified_*）原先**取不到**。
# 这里把包卡接进工具返回，registry 仍作兜底（包卡不存在时行为不变）。
REPO_PACKAGES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'packages')
_PACKAGE_CARDS = {}


def _repo_card_path(pkg):
    p = os.path.join(REPO_PACKAGES_DIR, str(pkg), 'package.yaml')
    return p if os.path.isfile(p) else None


def _load_yaml_file(path):
    """优先 pyyaml；不可用时返回 None（调用方降级为「无包卡」）。"""
    try:
        import yaml  # noqa
        with open(path, encoding='utf-8') as fp:
            return yaml.safe_load(fp)
    except Exception:
        return None


def package_card(pkg):
    """仓库里的包卡（不存在/解析失败 → None）。带进程内缓存。"""
    key = str(pkg)
    if key in _PACKAGE_CARDS:
        return _PACKAGE_CARDS[key]
    path = _repo_card_path(key)
    card = None
    if path:
        data = _load_yaml_file(path)
        if isinstance(data, dict):
            card = {k: data.get(k) for k in
                    ('id', 'version', 'summary', 'entry', 'headers', 'api', 'deps',
                     'usage_cpp', 'gotchas', 'see_also')}
            card['platforms'] = data.get('platforms')
            card['verified'] = {k: v for k, v in data.items()
                                if isinstance(k, str) and k.startswith('verified')}
            card['cardPath'] = 'packages/%s/package.yaml' % key
            card['readmePath'] = 'packages/%s/README.md' % key
    _PACKAGE_CARDS[key] = card
    return card


def _has_card(pkg):
    return package_card(pkg) is not None


def _cards_dir():
    return REPO_PACKAGES_DIR
