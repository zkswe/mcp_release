# -*- coding: utf-8 -*-
"""FlyThings package ecosystem tools: search, API docs, dependency resolution, manifest generation."""
import json, os, re, sys, urllib.request, xml.etree.ElementTree as ET

import platforms as _platforms  # 平台解析唯一来源（包生态键也在这里，别再各写一份）

REGISTRY_CANDIDATES = [
    # 本地包注册表（多目录合并：不同工具链/历史下载可能分散存放，全扫不漏包）
    os.environ.get('FLYTHINGS_REGISTRY', ''),      # 环境变量显式指定（最高优先）
    os.path.join(os.path.expanduser('~'), '.fun', 'registry', 'public'),     # MCP 默认注册表（f133/z21 基础包）
    os.path.join(os.path.expanduser('~'), '.fuse', 'registry', 'public'),    # 历史注册表（f133 全量 30+ 包：ntp/curl/mqtt-cxx 等）
    r'C:\zkswe\fun\registry\public',             # fun.exe 工具链自带注册表
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


def _parse_header_classes(include_dir, max_classes=8):
    """从头文件粗解析类与 public 方法签名"""
    classes = []
    if not os.path.isdir(include_dir):
        return []
    for root, _, files in os.walk(include_dir):
        if len(classes) >= max_classes:
            break
        for fn in files:
            if not fn.endswith(('.h', '.hpp')):
                continue
            rel = os.path.relpath(os.path.join(root, fn), include_dir).replace('\\', '/')
            try:
                text = open(os.path.join(root, fn), encoding='utf-8', errors='replace').read()
            except Exception:
                continue
            cls_names = re.findall(r'class\s+(\w+)', text)
            methods = []
            for line in text.split('\n'):
                s = line.strip()
                if re.match(r'^(bool|void|int|float|double|char|unsigned|long|std::|const|virtual|static)', s) \
                        and '(' in s and ';' in s and not s.startswith(('if', 'for', 'while', 'return')):
                    methods.append(s[:120])
            if cls_names:
                for cn in cls_names[:3]:
                    entry = {'name': cn, 'header': rel}
                    if methods:
                        entry['methods'] = methods[:12]
                    classes.append(entry)
                    if len(classes) >= max_classes:
                        break
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
BUILTIN_PKGS = {'easyui', 'log', 'zkhardware', 'zknet', 'zkmedia', 'zkmisc', 'base-utility'}


def flythings_check_project_deps(project_root, platform='F133'):
    """扫描项目代码 include 的三方库，与 Manifest.xml 已声明依赖对比，返回缺失依赖。
    新建/交付项目前调用，避免"用了三方库但没声明"导致编译失败。"""
    root = os.path.abspath(project_root)
    src = os.path.join(root, 'src')
    if not os.path.isdir(src):
        return {'success': False, 'error': f'src 目录不存在: {src}'}
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
    declared = set()
    mf = os.path.join(root, 'Manifest.xml')
    if os.path.isfile(mf):
        try:
            mtext = open(mf, encoding='utf-8', errors='replace').read()
        except Exception:
            mtext = ''
        declared = set(re.findall(r'<package\s+id="([^"]+)"', mtext))
    # 4. 缺失依赖
    missing = []
    for inc, pkgs in sorted(detected.items()):
        need = [p for p in pkgs if p not in BUILTIN_PKGS]
        if need and not any(p in declared for p in need):
            missing.append({'include': inc, 'recommendedPackages': need,
                            'hint': '在 Manifest.xml 添加依赖或移除该 include'})
    return {'success': True, 'projectRoot': root, 'platform': platform,
            'declaredPackages': sorted(declared),
            'detectedIncludes': sorted(detected.keys()),
            'missingDependencies': missing}


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
                      'description': PKG_DESC.get(n, '')}
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
                'versions': local_versions, 'source': 'local registry'}
    cv = _catalog_versions(package, np_)
    if cv:
        return {'success': True, 'package': package, 'platform': platform,
                'description': PKG_DESC.get(package, ''),
                'versions': cv, 'source': 'offline catalog'}
    online = _online_versions(package, np_)
    return {'success': True, 'package': package, 'platform': platform,
            'description': PKG_DESC.get(package, ''),
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


def flythings_get_package_api(package_id, platform='F133', version=None):
    """获取 package 的头文件路径、类方法签名、使用示例。"""
    versions = _pkg_versions(package_id, platform)
    v = version or (versions[0] if versions else None)  # versions 降序，[0] 为最新
    if not versions:
        return {'success': False, 'error': f'平台 {platform} 未找到包 {package_id}'}
    inc = os.path.join(_pkg_dir(package_id, platform), v, 'include')
    classes = _parse_header_classes(inc) if os.path.isdir(inc) else []
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
            'classes': classes, 'examples': examples}


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
    # fun install 会自动解析；显式再列一份 curl@8.12.1 反而与变体版本冲突导致安装失败。
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
        note = (note + '；' if note else '') + f'以下传递依赖不显式列出（宿主包 Manifest 已声明，fun install 自动解析，避免版本冲突）：{", ".join(transitive)}'
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
    """把 package 添加进项目 Manifest.xml 并执行 fun install 拉取依赖（添加包闭环流程）。

    - 版本解析顺序：本地 registry → 离线 catalog → 在线（semver 取最新，不依赖包实体是否存在）
    - 已声明同包则更新版本；未声明则追加 <package id version/>
    - with_install=True（默认）执行 fun install 同步依赖（Manifest 变更后自动拉取）
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

    # 3. fun install 同步依赖（Manifest 变更后拉取新包）
    install = {'executed': False}
    if with_install:
        try:
            import project_tools as _pt
            ri = _pt._run_fun('install', root)
            install = {'executed': True, 'success': ri['success'],
                       'detail': (ri.get('stderr') or ri.get('stdout') or ri.get('error') or '')[-400:]}
            if not ri['success']:
                install['note'] = 'fun install 失败（网络/工具链问题），Manifest 已更新；重试 flythings_build_ui_flow 或手动 fun install'
        except Exception as e:
            install = {'executed': True, 'success': False, 'error': str(e)}
    return {'success': True, 'package': pkg, 'version': v, 'platform': platform,
            'versionSource': 'local' if vers else 'catalog/online',
            'action': action, 'manifestPath': mf, 'install': install}
