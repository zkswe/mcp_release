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
- 换行转义：\n 或 &#x000A;；多语言需字体支持（默认精简字体，建议 font_cut_tool 自定义字体）

本工具只做文件读写与诊断，翻译内容由调用方 AI 提供（MCP 零远程依赖）；
翻译要求专业：结合项目语境（如车载项目 CAN BUS 保持行业术语，不直译公共汽车）。
"""
import io, os, re, glob, json
import xml.etree.ElementTree as ET

TR_HEADER = '<?xml version="1.0" encoding="utf-8"?>\n<resources>\n'
TR_FOOTER = '</resources>\n'


def _i18n_dir(project_root):
    return os.path.join(project_root, 'i18n')


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
                out[name] = text
    except Exception:
        # 容错：正则兜底
        try:
            t = io.open(path, encoding='utf-8').read()
            for m in re.finditer(r'<string name="([^"]+)">(.*?)</string>', t, re.S):
                out[m.group(1)] = m.group(2).strip()
        except Exception:
            pass
    return out


def _write_tr(path, entries):
    """写 .tr 文件。entries: {key: text}，保持插入序；XML 转义特殊字符。"""
    lines = [TR_HEADER]
    for k, v in entries.items():
        text = (v or '').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        # 多行文本：保留换行与 tab 缩进
        if '\n' in text:
            indented = text.replace('\n', '\n\t\t')
            lines.append(f'\t<string name="{k}">\n\t\t{indented}\n\t</string>\n')
        else:
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
                'message': '项目无 i18n/ 目录或 .tr 文件，尚未做多语言。可先 flythings_i18n_export 导出待翻译清单生成首个语言文件。',
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
            'hint': '翻译 entries 的 value 后，调用 flythings_i18n_import 写回生成/更新 .tr 文件。',
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
    返回待翻译清单（key→基础语言原文）+ 专业翻译提示；翻译后调用 flythings_i18n_import 写回。
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
            'nextHint': f'翻译 entries 的 value 为{lang_name.strip()}后，调用 flythings_i18n_import(project_root, "{lang}-{lang_name.strip()}", 翻译结果JSON) 写回；'
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
