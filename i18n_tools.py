#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""FlyThings 多国语言（i18n）工具：scan 诊断 / export 导出待翻译 / import 写回生成 .tr /
add_language 添加新语言 / refactor 布局文本转 @key。

机制（官方 i18n.html + SampleUI-New 实测，2026-08-29 沉淀）：
- 翻译文件 = 项目根目录 i18n/<语言>.tr，Android strings.xml 同款 XML：
    <?xml version="1.0" encoding="utf-8"?>
    <resources>
        <string name="about_me">关于我们</string>
    </resources>
- 文件名三段式：xx_XX-语言名.tr（语言代号 2 小写 + 地区代号 2 大写 + 语言名显示在切换列表），
如 fr_FR-法语.tr / es_ES-西班牙语.tr / ru_RU-俄语.tr；默认四种语言 zh_CN/en_US/ja_JP/ko_KR
- 布局 json/ftu 文本控件 text 写 @key（如 "@about_me"），运行时按当前语言自动解析
- 代码动态翻译：setTextTr("key")（不带@）；拼接取词：LANGUAGEMANAGER->getValue("key")
  （easyui 包 manager/LanguageManager.h）
- 语言切换：EASYUICONTEXT->updateLocalesCode("zh_CN") 或 openActivity("LanguageSettingActivity")
  ⚠️ 只有 updateLocalesCode 会立即刷新**已打开页面**的文案
  （内部 = LanguageManager::setCurrentCode + 遍历 ActivityStack 调 BaseApp::updateLocales）。
只调 LANGUAGEMANAGER->setCurrentCode 不会刷新在屏控件文本，用户要「退出重进」才看到新语言。
- 换行转义：**唯一写法 = XML 字符引用 `&#x000A;`**（官方 i18n 文档原文：
  `<string name="new_line_test">第一行&#x000A;第二行</string>`）。
  **本工具写 `.tr` 一律写 `&#x000A;`**（制表 `&#x0009;`、回车 `&#x000D;` 同理）—— 单一口径，不存在第二种写法。
  读时**额外容忍**历史字面 `\n` / `\t` / `\\`（旧版本工具写出的文件），保证老工程零迁移；
  但**写回会归一成字符引用**（见 `_write_tr`）。
  设备侧硬要求不变：json 里必须是真实 `0x0A`；
框架取值不做反斜杠还原，设备端 zk_gdi_draw_text 按 0x0A 切行。
多语言需字体支持（默认精简字体，建议 font_cut_tool 自定义字体）；
  ⚠️ 精简字库常缺 `&`、`@` 等 ASCII 符号 → 文案里禁用（用 "and" / 空格 代替），
否则设备上该字符空白或出乱码。改文案后建议核对字库 cmap 覆盖。

本工具只做文件读写与诊断，翻译内容由调用方 AI 提供（MCP 零远程依赖）；
翻译要求专业：结合项目语境（如车载项目 CAN BUS 保持行业术语，不直译公共汽车）。

设备端加载格式（2026-09-08 实测，V553 项目）：
- zkgui 实际加载的是 i18n/<lang>.json（不是 .tr），路径 /tmp/tr/<lang>.json（DEBUG）。
- fun launch 只推 ftu/images/font/lib/cfg，**不推 i18n 的 .tr/.json**（CHANGELOG 2026-09-02
需求方定规"部署统一 fun launch"是针对代码+资源，i18n 仍需本工具显式推送）。
- 改完翻译（import / add_language / refactor 改 .tr）后必须调 flythings_i18n(action="to_json")
转 json 并推送，否则设备仍跑旧翻译（logcat 刷 'not found value' 警告）。
- 生产固件把 json 打包到 /res/，不需要推送（无需调用本工具的 push 步骤）。
"""
import io, os, re, glob, json, subprocess
import xml.etree.ElementTree as ET
from xml.sax.saxutils import unescape as _xml_unescape

TR_HEADER = '<?xml version="1.0" encoding="utf-8"?>\n<resources>\n'
TR_FOOTER = '</resources>\n'


def _i18n_dir(project_root):
    return os.path.join(project_root, 'i18n')


# ---------------------------------------------------------------- 换行/空白转义
# 唯一写法 = **XML 字符引用**（官方 i18n 文档原文用 `&#x000A;`；任何 XML 解析器都会解成真实 LF）：
#   写(_write_tr)：`\n`→`&#x000A;`、`\t`→`&#x0009;`、`\r`→`&#x000D;` —— 单一口径，不再有第二种写法。
#   读(_unescape_tr)：字符引用由 XML 解析器解开；**额外**容忍历史字面 `\n`/`\t`/`\\`
#     （旧版本工具写出过的文件）→ 老工程零迁移；但这只是向后兼容，不是鼓励写法。
# .json（设备读）必须是真实换行符。
# 实证（2026-09-10 反汇编 v85x easyui 2.9.0 libeasyui.so）：
#   LanguageManager::getValue 直接 Json::Value::asString() 返回，不做反斜杠还原；
#   分行发生在 zk_gdi_draw_text，按字节 0x0A(LF) 切行（strchr(p, '\n')）。
#   ⇒ .json 里留字面 `\n`（JSON 写作 \\n）设备会原样显示 "\n" 文字，不换行。
# 本地同源脚本：<项目>/tools/tr2json.py。
_ESCAPE_MAP = {'n': '\n', 'r': '\r', 't': '\t', '\\': '\\', '"': '"', "'": "'"}   # 仅用于“读”兼容
_UNESCAPE_MAP = {'\n': '&#x000A;', '\r': '&#x000D;', '\t': '&#x0009;'}            # 写：XML 字符引用


def _unescape_tr(text):
    """读兼容：历史字面 `\\n`(2 字符) -> 真实换行;`\\t` -> TAB;`\\\\` -> 反斜杠。其余 `\\x` 原样保留。

    ⚠️ 字符引用（`&#x000A;`）不在这里处理 —— 它们由 XML 解析器（ElementTree）解开；
    本函数只兜旧版本工具写出的字面反斜杠形式，写回时会被 `_write_tr` 归一成字符引用。
    """
    if '\\' not in text:
        return text
    out, i, n = [], 0, len(text)
    while i < n:
        c = text[i]
        if c == '\\' and i + 1 < n and text[i + 1] in _ESCAPE_MAP:
            out.append(_ESCAPE_MAP[text[i + 1]])
            i += 2
        else:
            out.append(c)
            i += 1
    return ''.join(out)


def _escape_tr(text):
    """真实换行/TAB/回车 -> XML 字符引用（`&#x000A;` / `&#x0009;` / `&#x000D;`），保证 .tr 单行可读。

    反斜杠**不再转义**（它在 XML 里是普通字符），所以 `C:\\new` 这类字面内容能原样保留。
    """
    return ''.join(_UNESCAPE_MAP.get(c, c) for c in text)


def _list_tr_files(project_root):
    """返回 [(语言标识, 文件路径)]，按文件名排序。语言标识=文件名去 .tr（含三段式 xx_XX-语言名）。"""
    d = _i18n_dir(project_root)
    if not os.path.isdir(d):
        return []
    out = []
    for f in sorted(os.listdir(d)):
        if f.endswith('.tr'):
            lang = f[:-3]
            out.append((lang, os.path.join(d, f)))
    return out


def _tr_display_name(lang_id):
    """语言标识 → 显示名：'fr_FR-法语' → '法语'；'zh_CN' → 'zh_CN'。"""
    if '-' in lang_id:
        return lang_id.split('-', 1)[1]
    return lang_id


def _parse_tr(path):
    """解析 .tr 文件 → {key: text}。多行文本保留（去首尾空白与公共缩进）。"""
    out = {}
    try:
        tree = ET.parse(path)
        root = tree.getroot()
        for s in root.findall('string'):
            name = s.get('name')
            if name:
                text = s.text or ''
                # 多行文本：去首尾换行/空白
                if '\n' in text:
                    lines = text.split('\n')
                    # 去空首行
                    while lines and not lines[0].strip():
                        lines.pop(0)
                    while lines and not lines[-1].strip():
                        lines.pop()
                    # 去公共缩进
                    indents = [len(l) - len(l.lstrip()) for l in lines if l.strip()]
                    if indents:
                        cut = min(indents)
                        lines = [l[cut:] if len(l) >= cut else l for l in lines]
                    text = '\n'.join(lines)
                out[name] = _unescape_tr(text)
    except Exception:
        # 容错：正则兜底（XML 实体需手动还原）
        try:
            t = io.open(path, encoding='utf-8').read()
            for m in re.finditer(r'<string name="([^"]+)">(.*?)</string>', t, re.S):
                out[m.group(1)] = _unescape_tr(_xml_unescape(m.group(2).strip()))
        except Exception:
            pass
    return out


def _write_tr(path, entries):
    """写 .tr 文件。entries: {key: text}，保持插入序；换行写 XML 字符引用 `&#x000A;`、XML 转义特殊字符。"""
    lines = [TR_HEADER]
    for k, v in entries.items():
        text = (v or '').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        # 真实换行 -> `&#x000A;`（唯一写法；保证单行可读。设备端 .json 才用真实换行）
        text = _escape_tr(text)
        lines.append(f'\t<string name="{k}">{text}</string>\n')
    lines.append(TR_FOOTER)
    io.open(path, 'w', encoding='utf-8', newline='\n').write(''.join(lines))


def _collect_layout_keys(project_root):
    """扫描 ui/**/*.json 里的 @key 引用 → set。"""
    keys = set()
    ui_dir = os.path.join(project_root, 'ui')
    if not os.path.isdir(ui_dir):
        return keys
    for p in glob.glob(os.path.join(ui_dir, '**', '*.json'), recursive=True):
        try:
            t = io.open(p, encoding='utf-8').read()
        except Exception:
            continue
        for m in re.finditer(r'"text"\s*:\s*"@([^"]+)"', t):
            keys.add(m.group(1))
    return keys


# ========== 1. scan：诊断 i18n 现状 ==========
def flythings_i18n_scan(project_root: str) -> str:
    """诊断项目多语言（i18n）现状：语言文件、key 对齐、布局 @key 引用完整性。
项目根目录下应有 i18n/*.tr 翻译文件；布局文本控件用 text:"@key" 引用。
返回 JSON：languages/keysPerLanguage/对齐检查/布局引用检查/缺失建议。
    """
    try:
        files = _list_tr_files(project_root)
        if not files:
            return json.dumps({
                'ok': True,
                'hasI18n': False,
                'message': '项目无 i18n/ 目录或 .tr 文件，尚未做多语言。可先 flythings_i18n(action="export") 导出待翻译清单生成首个语言文件。',
                'languages': [],
            }, ensure_ascii=False)

        all_maps = {}       # lang -> {key: text}
        all_keys = {}       # key -> set(lang)
        for lang, path in files:
            m = _parse_tr(path)
            all_maps[lang] = m
            for k in m:
                all_keys.setdefault(k, set()).add(lang)

        # key 对齐检查
        missing = {}        # lang -> [缺失的 key]
        for lang in all_maps:
            miss = [k for k, langs in all_keys.items() if lang not in langs]
            if miss:
                missing[lang] = sorted(miss)

        # 布局引用检查
        layout_keys = _collect_layout_keys(project_root)
        base_map = all_maps.get(files[0][0], {})
        ref_missing = sorted(layout_keys - set(base_map.keys()))
        unused = sorted(set(base_map.keys()) - layout_keys)

        return json.dumps({
            'ok': True,
            'hasI18n': True,
            'languages': [lang for lang, _ in files],
            'languageDisplayNames': {lang: _tr_display_name(lang) for lang, _ in files},
            'keysPerLanguage': {lang: len(m) for lang, m in all_maps.items()},
            'keyAligned': not missing,
            'missingKeysPerLanguage': missing,
            'layoutRefCount': len(layout_keys),
            'layoutRefMissingInTr': ref_missing,
            'trKeysUnusedByLayout': unused,
            'suggestion': 'key 对齐或引用有缺时：export 导出 → 翻译 → import 写回；新增语言用 add_language。',
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({'ok': False, 'error': str(e)}, ensure_ascii=False)


# ========== 2. export：导出待翻译清单 ==========
def flythings_i18n_export(project_root: str, lang: str = 'zh_CN', keys: str = '', context: str = '') -> str:
    """导出指定语言（缺省 zh_CN）的 key→文本清单（JSON），供翻译后 import 写回。
    keys 参数可选：逗号分隔的 key 子集，缺省导出全部。
    context 参数可选：项目语境描述（如"车载充电桩项目"），返回 translationGuide 提示 AI 专业翻译
    （术语如 CAN BUS 保持行业译法，不直译公共汽车）。
    """
    try:
        files = _list_tr_files(project_root)
        maps = {lang_: _parse_tr(p) for lang_, p in files}
        base = maps.get(lang, {})
        if keys.strip():
            wanted = [k.strip() for k in keys.split(',') if k.strip()]
            base = {k: base.get(k, '') for k in wanted}
        guide = _translation_guide(context)
        return json.dumps({
            'ok': True,
            'lang': lang,
            'count': len(base),
            'entries': base,
            'translationGuide': guide,
            'hint': '翻译 entries 的 value 后，调用 flythings_i18n(action="import", translations=<翻译结果JSON>) 写回生成/更新 .tr 文件。',
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({'ok': False, 'error': str(e)}, ensure_ascii=False)


def _translation_guide(context: str) -> str:
    """生成专业翻译提示（结合项目语境）。"""
    parts = [
        '翻译要求：',
        '1. 术语必须结合项目行业语境（不要按字面直译）；',
        '2. 单位/编号/占位符（%d、%s、CAN、OBD、TCP、MQTT 等）保持原样；',
        '3. 译文长度控制：德文等语言会比中文长 30-50%，避免超控件溢出；',
        '4. 状态/操作类短词用行业惯例（如 Start/Stop/OK/Cancel）。',
    ]
    if context.strip():
        parts.insert(1, f'项目语境：{context.strip()}。专业术语按该行业标准译法（如车载项目 CAN BUS 不译成公共汽车）。')
    return '\n'.join(parts)


# ========== 2.5 add_language：添加新语言 ==========
def flythings_i18n_add_language(project_root: str, lang: str, lang_name: str, base_lang: str = 'zh_CN', context: str = '') -> str:
    """添加新语言：从基础语言（缺省 zh_CN）复制 key 骨架，生成 i18n/<lang>-<lang_name>.tr 待翻译文件。
    lang 为语言代码（如 fr_FR，2 小写+2 大写），lang_name 为语言名（如 法语，显示在切换列表）。
返回待翻译清单（key→基础语言原文）+ 专业翻译提示；翻译后调用 flythings_i18n(action="import") 写回。
    ⚠️ 新语言文件名必须 xx_XX-语言名.tr 三段式（官方规范），勿用两段式。
    """
    try:
        # 校验语言代码格式 xx_XX
        if not re.fullmatch(r'[a-z]{2}_[A-Z]{2}', lang or ''):
            return json.dumps({'ok': False, 'error': f'语言代码格式应为 xx_XX（如 fr_FR），收到: {lang}'}, ensure_ascii=False)
        if not lang_name or not lang_name.strip():
            return json.dumps({'ok': False, 'error': 'lang_name 必填（如 法语/俄语，显示在语言切换列表）'}, ensure_ascii=False)

        files = _list_tr_files(project_root)
        maps = {lang_: _parse_tr(p) for lang_, p in files}
        if lang not in maps:
            base = maps.get(base_lang, {})
            if not base:
                return json.dumps({'ok': False, 'error': f'基础语言 {base_lang} 不存在，无法复制 key 骨架'}, ensure_ascii=False)
            # 复制骨架：值先用基础语言原文占位，待 AI 翻译
            entries = dict(base)
        else:
            entries = maps[lang]
            return json.dumps({'ok': False, 'error': f'语言 {lang} 已存在（{lang_name}），如需更新请用 import'}, ensure_ascii=False)

        file_name = f'{lang}-{lang_name.strip()}.tr'
        d = _i18n_dir(project_root)
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, file_name)
        if os.path.exists(path):
            return json.dumps({'ok': False, 'error': f'文件已存在: {file_name}'}, ensure_ascii=False)

        # 先写出占位文件（值=基础语言原文），AI 翻译后 import 覆盖
        _write_tr(path, entries)
        guide = _translation_guide(context)
        return json.dumps({
            'ok': True,
            'action': '新建',
            'lang': f'{lang}-{lang_name.strip()}',
            'file': path,
            'count': len(entries),
            'baseLang': base_lang,
            'entries': entries,
            'translationGuide': guide,
            'nextHint': f'翻译 entries 的 value 为{lang_name.strip()}后，调用 flythings_i18n(action="import", lang="{lang}-{lang_name.strip()}", translations=翻译结果JSON) 写回；'
                        '注意：新语言需将内置界面翻译文本（docs.flythings.cn/src/zh_CN.tr）并入并翻译，内置界面才能正常显示。',
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({'ok': False, 'error': str(e)}, ensure_ascii=False)


# ========== 3. import：写回翻译生成/更新 .tr ==========
def flythings_i18n_import(project_root: str, lang: str, translations: str, merge: bool = True) -> str:
    """将翻译结果写回项目 i18n/<lang>.tr（生成新语言文件或更新已有）。
    translations 为 JSON 对象字符串 {"key": "翻译文本"}。
    merge=True（缺省）：与已有内容合并（仅更新/新增传入的 key，保留未传 key）；
    merge=False：以传入内容整体覆盖该语言文件。
    """
    try:
        if not lang or '/' in lang or '\\' in lang:
            return json.dumps({'ok': False, 'error': f'非法语言代码: {lang}'}, ensure_ascii=False)
        try:
            entries = json.loads(translations)
            if not isinstance(entries, dict):
                raise ValueError('translations 必须是 JSON 对象')
        except Exception as e:
            return json.dumps({'ok': False, 'error': f'translations 解析失败: {e}'}, ensure_ascii=False)

        d = _i18n_dir(project_root)
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, f'{lang}.tr')
        existed = os.path.exists(path)

        if merge and existed:
            merged = _parse_tr(path)
            merged.update(entries)
            entries = merged

        _write_tr(path, entries)
        return json.dumps({
            'ok': True,
            'lang': lang,
            'file': path,
            'count': len(entries),
            'action': '更新' if existed else '新建',
            'nextHint': '改布局引用 @key、代码 setTextTr("key") 或 LANGUAGEMANAGER->getValue() 后重新编译部署；'
                        '切换语言用 EASYUICONTEXT->updateLocalesCode("code")。',
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({'ok': False, 'error': str(e)}, ensure_ascii=False)


# ========== 4. 布局文本 → @key 化（可选增强） ==========
def flythings_i18n_refactor(project_root: str, lang: str = 'zh_CN', dry_run: bool = True) -> str:
    """把布局 json 里写死的非空文本控件替换为 @key 引用（多语言改造辅助）。
生成 key（caption 去空格或 text 前 4 字符）+ 写入指定语言 .tr；dry_run=True 只预览不改文件。
返回 JSON：改动清单（json 文件、caption、原文本、生成 key）。
    ⚠️ 仅建议在确认布局文本均为界面文案时使用；纯数字/时间占位文本会跳过。
    """
    try:
        ui_dir = os.path.join(project_root, 'ui')
        if not os.path.isdir(ui_dir):
            return json.dumps({'ok': False, 'error': '无 ui/ 目录'}, ensure_ascii=False)
        changes = []
        skip = 0
        used_keys = {}  # key -> 已用次数，冲突自动加后缀
        for p in sorted(glob.glob(os.path.join(ui_dir, '**', '*.json'), recursive=True)):
            try:
                data = json.load(io.open(p, encoding='utf-8'))
            except Exception:
                continue
            modified = False
            for key, ctrl in data.items():
                if not isinstance(ctrl, dict):
                    continue
                if key.startswith('textview__') or key.startswith('button__'):
                    text = ctrl.get('text', '')
                    if not isinstance(text, str) or not text.strip():
                        continue
                    if text.startswith('@'):
                        continue  # 已是引用
                    if re.fullmatch(r'[\d\s:./\-]+', text):
                        skip += 1
                        continue  # 数字/时间占位
                    cap = ctrl.get('caption', key)
                    gkey = re.sub(r'[^A-Za-z0-9_]', '_', cap).strip('_') or f'k_{key}'
                    # 同名 caption 冲突（不同文件/控件）自动去重
                    n = used_keys.get(gkey, 0)
                    if n:
                        gkey = f'{gkey}_{n + 1}'
                    used_keys[gkey] = n + 1
                    changes.append({
                        'json': os.path.relpath(p, project_root),
                        'ctrl': key, 'caption': cap,
                        'oldText': text, 'newKey': gkey,
                    })
                    if not dry_run:
                        ctrl['text'] = '@' + gkey
                        modified = True
            if modified and not dry_run:
                json.dump(data, io.open(p, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
        if not dry_run and changes:
            tr = {c['newKey']: c['oldText'] for c in changes}
            res = json.loads(flythings_i18n_import(project_root, lang, json.dumps(tr, ensure_ascii=False)))
            tr_msg = f"，已写入 i18n/{lang}.tr 新增 {len(tr)} 条"
        else:
            tr_msg = ''
        return json.dumps({
            'ok': True,
            'dryRun': dry_run,
            'count': len(changes),
            'skippedNumeric': skip,
            'changes': changes[:50],
            'message': f'预览 {len(changes)} 处待替换{tr_msg}。确认后传 dry_run=False 执行。',
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({'ok': False, 'error': str(e)}, ensure_ascii=False)


# ========== 6. to_json：tr → json 转换 + 推送设备 ==========
# 关键背景（2026-09-08 实测，V553 项目；详见模块顶部 docstring）：
#   fun launch 只推 ftu/images/font/lib/cfg，不推 i18n。设备 zkgui 加载的是
#   /tmp/tr/<lang>.json（不是 .tr）。改完翻译后必须显式调本工具把 .tr 转 .json
#并 adb push 到设备 /tmp/tr/，否则设备仍跑旧翻译。
#本地开发脚本版见 E:\AICODE\trae\V553\tools\tr2json.py（V553 项目），逻辑同源。

def _tr_to_json(tr_path):
    """解析 .tr（XML）→ 有序 dict {key: value}。XML 实体与字符引用（含 `&#x000A;`）由 ElementTree 解码；
    之后再把**历史**字面 `\\n` / `\\t` 兼容还原为真实字符（设备端按 0x0A 切行）。"""
    tree = ET.parse(tr_path)
    root = tree.getroot()
    out = {}
    for s in root.findall('string'):
        name = s.get('name')
        if name:
            out[name] = _unescape_tr(s.text or '')
    return out


def _dump_json(data):
    """序列化为 json 文本（tab 缩进+无空格冒号+末尾无换行），与设备端格式逐字节一致。"""
    items = list(data.items())
    lines = ['{']
    for i, (k, v) in enumerate(items):
        comma = ',' if i < len(items) - 1 else ''
        lines.append('\t%s:%s%s' % (
            json.dumps(k, ensure_ascii=False),
            json.dumps(v, ensure_ascii=False),
            comma))
    lines.append('}')
    return '\n'.join(lines)


def _push_to_device(local_path, device, target_dir='/tmp/tr/'):
    """adb push 单文件到设备指定目录。返回 (success, detail)。
    ⚠️ v0.27.84 起 adb 一律走 adb_tools.resolve_adb()（不再写死 'adb' 字面量）。"""
    target = os.path.join(target_dir, os.path.basename(local_path)).replace('\\', '/')
    try:
        import adb_tools as _at
        adb = _at.resolve_adb()
        if not adb:
            return False, _at.adb_missing_hint()
        r = subprocess.run([adb, '-s', device, 'push', local_path, target],
                           capture_output=True, text=True, timeout=30,
                           stdin=subprocess.DEVNULL, encoding='utf-8', errors='replace')
        ok = r.returncode == 0 and '1 file pushed' in (r.stdout or '')
        detail = (r.stdout or r.stderr or '').strip()[-200:]
        return ok, detail
    except subprocess.TimeoutExpired:
        return False, 'adb push 超时（30s）'
    except FileNotFoundError:
        return False, 'adb 不可执行（请检查 ADB 环境变量/随包 tools/adb/）'
    except Exception as e:
        return False, f'adb push 异常: {e}'


def flythings_i18n_to_json(project_root: str, langs: str = '', push: bool = True, device: str = '') -> str:
    """把 i18n/*.tr 转为 i18n/*.json（设备 zkgui 实际加载格式），并可推送到设备 /tmp/tr/。

    ⚠️ 关键背景：**fun launch 不推 i18n**（只推 ftu/images/font/lib/cfg）。
改完翻译（import / add_language / refactor）后必须显式调本工具，
否则设备仍跑旧翻译（logcat 刷 'not found value' 警告）。
本工具生成的 json 与设备端 zkgui 加载格式**逐字节一致**（tab 缩进+无空格冒号+末尾无换行）。

    Args:
        project_root: 项目根目录（含 i18n/）
        langs: 逗号分隔的语言列表（如 'zh_CN,en_US'，默认全部 .tr）；支持三段式 'fr_FR-法语'
        push: True 转换后自动 adb push 到设备 /tmp/tr/（设备 DEBUG 模式 /tmp 路径；
生产固件把 json 打包到 /res/，设 False 只生成不推送）
        device: 设备 IP/序列号（多设备时指定；不传则用 adb 唯一可见设备；多设备未指定则报错）

    Returns:
        JSON {ok, converted[{lang, trPath, jsonPath, count}], pushed[{lang, success, detail, target}],
              skipped[{lang, reason}], adbStatus, device, nextHint}
        ok=True 仅当所有 requested 转换/推送均成功；adbStatus 描述 adb 子系统状态。
    """
    try:
        d = _i18n_dir(project_root)
        if not os.path.isdir(d):
            return json.dumps({'ok': False, 'error': f'i18n/ 目录不存在: {d}'}, ensure_ascii=False)

        wanted = None
        if langs.strip():
            wanted = set(x.strip() for x in langs.split(',') if x.strip())
        trs = [(lang, path) for lang, path in _list_tr_files(project_root)
               if wanted is None or lang in wanted]
        if not trs:
            return json.dumps({
                'ok': False,
                'error': f'没有匹配的 .tr 文件（langs={langs!r}，i18n 目录有 {_list_tr_files(project_root)}）',
            }, ensure_ascii=False)

        # 1. 转换
        converted = []
        for lang, tr_path in trs:
            data = _tr_to_json(tr_path)
            json_path = tr_path[:-3] + '.json'
            with io.open(json_path, 'w', encoding='utf-8', newline='') as f:
                f.write(_dump_json(data))
            converted.append({'lang': lang, 'trPath': tr_path, 'jsonPath': json_path, 'count': len(data)})

        # 2. 推送
        pushed = []
        adb_status = 'skipped'
        device_used = device
        if push:
            # adb 设备检测（v0.27.84：走 adb_tools.resolve_adb()）
            try:
                import adb_tools as _at
                adb_bin = _at.resolve_adb()
                if not adb_bin:
                    raise FileNotFoundError('adb not found')
                r = subprocess.run([adb_bin, 'devices'], capture_output=True, text=True, timeout=10,
                                   stdin=subprocess.DEVNULL, encoding='utf-8', errors='replace')
                if r.returncode != 0:
                    adb_status = 'adb_failed'
                    for c in converted:
                        pushed.append({'lang': c['lang'], 'success': False, 'detail': f'adb 不可用: {(r.stderr or "")[:200]}'})
                else:
                    lines = r.stdout.strip().splitlines()
                    devs = [l.split('\t')[0] for l in lines if '\tdevice' in l and not l.startswith('List')]
                    if not devs:
                        adb_status = 'no_device'
                        for c in converted:
                            pushed.append({'lang': c['lang'], 'success': False,
                                           'detail': '无可用 adb 设备（adb devices 为空）——'
                                                     '检查 ADB 驱动/USB 调试授权，或用 device=\'<设备IP>:5555\' 走网络'})
                    elif device and device not in devs:
                        adb_status = 'device_not_found'
                        for c in converted:
                            pushed.append({'lang': c['lang'], 'success': False,
                                           'detail': f'指定设备 {device!r} 不在 adb 列表: {devs}'})
                    else:
                        device_used = device or devs[0]
                        if len(devs) > 1 and not device:
                            adb_status = 'multi_device_ambiguous'
                            for c in converted:
                                pushed.append({'lang': c['lang'], 'success': False,
                                               'detail': f'检测到多设备 {devs}，未指定 device；请传 device=IP'})
                        else:
                            adb_status = 'ok'
                            for c in converted:
                                ok, detail = _push_to_device(c['jsonPath'], device_used)
                                pushed.append({
                                    'lang': c['lang'], 'success': ok, 'detail': detail,
                                    'target': f'/tmp/tr/{os.path.basename(c["jsonPath"])}',
                                })
            except FileNotFoundError:
                adb_status = 'adb_not_found'
                for c in converted:
                    pushed.append({'lang': c['lang'], 'success': False,
                                   'detail': 'adb 不可用（设环境变量 ADB 或用随包 tools/adb/adb.exe）'})
            except subprocess.TimeoutExpired:
                adb_status = 'adb_timeout'
                for c in converted:
                    pushed.append({'lang': c['lang'], 'success': False, 'detail': 'adb devices 超时（10s）'})

        # 总体 ok：转换默认全成功；推送看是否全成功
        all_pushed_ok = (not push) or all(p['success'] for p in pushed)
        next_hint = ''
        if push and all_pushed_ok:
            next_hint = ('json 已推送到设备 /tmp/tr/，DEBUG 模式下需重启 zkswe 服务才会重新加载：'
                         'adb shell "setprop ctl.stop zkswe && setprop ctl.start zkswe"。'
                         '生产固件把翻译打包到 /res/，升级固件时生效。')
        elif push and not all_pushed_ok:
            next_hint = '部分推送失败：检查 adbStatus/各 lang 的 detail；修复后重跑本工具。'
        else:
            next_hint = '仅生成本地 json，未推送（push=False）。生产固件走 /res/ 路径，无需推送。'

        return json.dumps({
            'ok': all_pushed_ok,
            'converted': converted,
            'pushed': pushed,
            'adbStatus': adb_status,
            'device': device_used,
            'nextHint': next_hint,
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({'ok': False, 'error': str(e)}, ensure_ascii=False)

