# -*- coding: utf-8 -*-
"""FlyThings_mcp_open: 全套 MCP 工具定义（stdio 本地部署，完全开放）。

每个工具都是普通函数，返回 str/JSON 字符串；由 mcp_server.py（stdio）注册。
✅ 开源版：检索完全本地化（内置 bge-small-zh 向量模型，免 API Key，
不可用时自动降级 BM25），不依赖任何远程 MCP 服务。
"""
import html.parser  # PyInstaller 打包需要（html2json 运行时导入，静态分析漏收）
import json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rag_search as rs
import project_tools as pt
import package_tools as pkgtools
UI_TOOLS = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ui_tools')
if getattr(sys, 'frozen', False):  # PyInstaller 打包：ui_tools 随包进 _MEIPASS
    UI_TOOLS = os.path.join(sys._MEIPASS, 'ui_tools')
if UI_TOOLS not in sys.path:
    sys.path.insert(0, UI_TOOLS)
import html2json as h2j
import json2html as j2h
import gen_res as h2j_genres
import fix_tools as ftx
import i18n_tools as itx
import test_tools as tt

# ========== MCP 版本号（每次发布递增，AI/用户可查询确认是否最新）==========
MCP_VERSION = '0.7.9-open'
MCP_BUILD = '2026-09-01'
MCP_FEATURES = [
    '2026-09-01: SlideWindow 布局定规修正（沛哥 21:59 纠正）——json 坐标来自 HTML 原型绝对定位，确认好即无需微调；若交付后还要调位置 = 前期 HTML 效果没确认好（正确流程：HTML → 预览确认 → 才 pack/交付）；删掉 v0.7.8 错误的「绝对布局需微调」表述',
    '2026-09-01: SlideWindow 图标布局补充（沛哥 21:52 定规）——①同一 slidewindow 所有图标尺寸必须一致（html2json 已加 items 尺寸一致性检查，不一致 warning）②默认 padding 值没问题，但 FlyThings 绝对布局需按实际显示微调 padding/iconTextPadding/iconSize 位置',
    '2026-09-01: SlideWindow 图标布局铁律（沛哥定规）——iconSize 必须按实际图片尺寸（非平分格子大小，默认 128 会导致图标位置不对）；padding=图标相对平分格子边界，iconTextPadding=配套文字 padding；入库 knowledge/uicontrols/slidewindow-fields.md；html2json 自动读首张图标图实际尺寸回填 iconSize（显式 data-icon-w/h 不覆盖，读不到 warning）',
    '2026-09-01: validate_project 去噪（沛哥确认）——删 3 处：①activity 目录缺失 warning（新建模板项目未编译时正常，误报）②cacert.pem 已就位 warning（正常配置噪音，缺证书已报 error 足够）③defined_cbs 死代码（赋值后从未读取）',
    '2026-09-01: 移除 flythings_read_ftu（沛哥确认）——新版 fui.exe 仅支持 pack 不支持 unpack，read_ftu 无 json 时必失败，只是 read_json 的包装；只保留 read_json，传 .ftu 时友好提示（提供同目录 json / 重新设计 / IDE 另存 json）；工具数 32→31',
    '2026-09-01: 控件用法检索边界定规（沛哥）——AI 检索控件用法/字段/API 只允许 MCP 内置知识库（flythings_search/knowledge）或官方 developer.flythings.cn，禁止从其他渠道/其他 GUI 框架（Qt/Android/Flutter/emWin 等）检索，防知识错乱；入库 knowledge/uicontrols/retrieval-boundary.md',
    '2026-09-01: EditText JSON 字段规范入库（knowledge/uicontrols/edittext-fields.md，沛哥要求，MCP 原先查不到）——完整字段表（text/hintText/hintTextColor/textType/isPassword/passwordChar/fontSize/colorTab/bgColorTab/beepEnable/bold/italic/roll*）+ onEditTextChanged 回调 + html2json HTML 写法（data-hint/data-num/data-password/data-password-char）+ 常见坑；修正 layout-audit id 段笔误（edittext 51000 不是 60000）',
    '2026-09-01: 圆角抗锯齿方案重做（沛哥反馈超采样导致倒角变宽）——弃用 SS 超采样+LANCZOS 缩回（像素网格取整偏移 1px，radius 接近钳制上限时校准也救不回）；改「1x 直画 + α 高斯羽化（sigma=0.5）」：几何轮廓（α>=128）与 1x 直画逐像素一致（倒角宽度不变），弧线 α 平滑过渡（抗锯齿）；实验 r=2..20×4 组尺寸全过',
    '2026-09-01: 圆角抗锯齿修复（FT-008 落地到 gen_res.py）——rounded_rect/rounded_card/gen_gradient/gen_gradient_stops/gen_shadow_card 全部改 SS=2 超采样 + LANCZOS 缩回（新增 _aa_rounded_rect/_aa_mask/_aa_outline），消除 1x 二值 α 圆角锯齿；边缘 α 过渡值验证通过；to_9patch 四边 marker 规则（FT-009）不受影响',
    '2026-09-01: FT-009 .9.png 生成规则入库（knowledge/uicontrols/nine-patch-rule.md）——①marker 纯黑不透明 (0,0,0,255) ②top/left 只画中间拉伸段排除倒角 ③right/bottom 黑线与拉伸区同宽 ④1px 贴边 ⑤marker 最后绘制不被 alpha 覆盖；gen_res.to_9patch 修复（补 right/bottom 黑线）',
    '2026-09-01: UI 控件 Layout 全量检查——basedemo 35 个官方 demo 抽取 21 种控件逐字段核对，html2json 修复 circlebar/cameraview/videoview/listview/slidewindow/文字滚动 6 处缺口；报告入库 knowledge/uicontrols/layout-audit.md',
    '2026-09-01: 图片资源路径铁律——自动生成图片统一输出 <项目>/resources/images/，json 引用 images/xxx.png（相对 resources，与设备加载一致）；gen_ui_assets 返回相对路径',
    '2026-09-01: ESL 电子价签方案入库（esl/tag-esl.md）——一套代码多平台（enableOnPlatforms+accessKey+#ifdef 三件套）、HTML 渲染体系、BlueZ GATT Server 思路、OTA 要点',
    '2026-09-01: html2json 文本清洗——剥离 emoji/特殊符号，纯 emoji 自动转 PNG；模拟器开放版不支持（fun sim 禁止，真机 fun build+launch 交付）',
    '2026-08-31: 自动化测试闭环——flythings_gen_ui_test（traverse/monkey/custom）+ adb 触摸注入（/dev/input 协议）+ logcat/fb 抓屏分析；预编译 ui_test ELF 随包分发（bin_tools/{平台}/）',
    '2026-08-31: 修复 .cc 误用规范——手写 .cc 不参与编译（Makefile 只编 %.cpp %.c），新增业务代码一律 .cpp/.h；validate_project 新增 manual_cc_file 检查',
    '2026-08-31: 方案库扩充——游戏机+Knob 旋钮、Z20 语音（AIUI）、T113 车载互联、Z20 SIP 对讲等方案知识入库（关键词触发）',
    '2026-08-29: 控件能力实测校准 + i18n 多语言工具（scan/export/import/refactor）+ fix_project 自动修复（FT-001~024）+ HTML 原型 JS 交互与自动转图',
    '2026-08-28: 包检索离线 catalog + 版本 semver 取最新 + manifest 依赖递归补齐',
    'open 版：完全本地部署零远程依赖——内置 bge-small-zh 向量模型（免 Key，不可用自动降级 BM25）+ fui/fun 工具链 + HelloWord 模板 + 32 个工具全家桶（项目创建/布局转换/预览/包管理/规范校验/修复/i18n/测试）',
]


def flythings_get_version() -> str:
    """返回 MCP 版本号、工具数量与关键特性。用户问「MCP 版本是多少 / 是不是最新的」时调用。
    """
    import inspect as _i
    tools = [n for n, _ in _i.getmembers(sys.modules[__name__], _i.isfunction)
             if n.startswith('flythings_')]
    return json.dumps({
        'mcpName': 'flythings-kb-open',
        'version': MCP_VERSION,
        'build': MCP_BUILD,
        'toolCount': len(tools),
        'tools': sorted(tools),
        'features': MCP_FEATURES,
        'checkHint': '在 AI 工具中问 AI：MCP 版本是多少？返回 version 与 0.3.0 比对即可确认是否最新',
    }, ensure_ascii=False)


def flythings_search(query: str, k: int = 3) -> str:
    """在 FlyThings 知识库（wiki 118 篇文档）中检索相关文档片段（完全本地，零 Key）。
    遇到 FlyThings 开发问题（控件/API/布局/FTU/回调/编译/平台差异等）时调用。query 用中文描述。
    内置 bge-small-zh 本地模型做向量检索，模型不可用时自动降级 BM25 关键词检索。"""
    kk = max(1, min(int(k), 8))
    try:
        top = rs.search(query, kk)
        if not top:
            return "no results found"
        parts = []
        for s, c in top:
            parts.append(f"===== {c['path']} (similarity {s:.3f}) =====\n{c['text']}")
        return '\n\n'.join(parts)
    except Exception as e:
        return f"search error: {e}"


def flythings_read_json(json_path: str) -> str:
    """解析 .json 布局文件为 JSON（分辨率、控件列表、caption→id 映射）。传入 json 完整路径。
    ⚠️ 传入 .ftu 时返回错误提示：ftu 为加密文件无法解析，可提供设计文件 / AI 重新设计界面 / 采用 HTML 布局。
    （flythings_read_ftu 已移除——无 unpack 能力时它只是 read_json 的包装）"""
    return json.dumps(pt.flythings_read_json(json_path), ensure_ascii=False)


def flythings_get_project_spec() -> str:
    """返回 FlyThings 项目结构化规范（目录规则、生成规则、注意事项）。编写/修改项目代码前调用。"""
    return json.dumps(pt.flythings_get_project_spec(), ensure_ascii=False)


def flythings_validate_project(project_root: str) -> str:
    """检查项目是否符合 FlyThings 规范，返回 errors/warnings。生成代码后调用。
    空白项目判定：工作目录 ui/ 下无 .ftu 即视为空白（无需再去读 json），返回
    isEmptyProject=true；此时直接询问用户平台（F133/F135/Z21）与分辨率后调用
    create_project，禁止去其他目录检索 json/ftu。
    ⚠️ 若 projectInfo.platform/resolution 为 null，必须先向用户询问，禁止猜测。
    """
    return json.dumps(pt.flythings_validate_project(project_root), ensure_ascii=False)


def flythings_fui_pack(json_path: str) -> str:
    """将 json 布局打包为 ftu（设备实际加载的是 ftu）。返回 ftu 路径、控件数、分辨率。"""
    return json.dumps(pt.flythings_fui_pack(json_path), ensure_ascii=False)




def flythings_edit_ftu(ftu_path: str, operations: str, output_ftu: str = '') -> str:
    """编辑 ftu 布局：自动应用编辑到 json 后 pack 回 ftu（默认覆盖原文件，或 output_ftu 指定新文件）。
    operations 为 JSON 数组字符串，支持：
    set      {"op":"set","target":"caption或key","props":{"x":100,"y":200,"text":"新文本"}}
    remove   {"op":"remove","target":"caption或key"}
    add      {"op":"add","template":"caption或key","newKey":"textview__4","props":{...}}
    set_root {"op":"set_root","props":{"backgroundColor":"#FFFFFF"}}
    客户说「把这个按钮往右移/改文本/换颜色/删掉某控件/复制一个控件」时调用。
    布局修改以 ftu 为目标（json 为内部中间文件自动处理）；改界面布局也可直接编辑 HTML 原型后重新转换。
    ⚠️ 布局以 json 为源：优先直接编辑同目录已有 json 再 pack 回 ftu；无 json 时报错。"""
    return json.dumps(pt.flythings_edit_ftu(ftu_path, operations, output_ftu), ensure_ascii=False)


def flythings_build_ui_flow(project_root: str, with_launch: bool = True, device: str = '') -> str:
    """UI 构建流程：① json/ftu 时间戳一致性检查（以 json 为源，改过 json 自动重新 pack）
    ② fui pack ③ fun install 同步依赖 ④ fun build ⑤ build 通过后直接 fun launch 推送启动（with_launch=False 可跳过）。
    ⚠️ launch 失败（无 adb 设备）时返回 needDeviceInput=true，必须询问用户接入方式：
    1) USB 接入：设备 USB 连电脑，确认 adb devices 可见后重试；2) 网络接入：
    先在电脑执行 adb connect <设备IP> 完成配对再重试。
    ⚠️ fun launch 不支持 -s 参数（带参数有其他问题），设备选择由 fun 自动完成，禁止替用户猜测 IP。
    传入项目根目录。改过 json 必须 pack，否则设备仍跑旧 ftu。
    ⚠️⚠️ src/activity/ 目录（mainActivity.cpp/h）由 IDE 编译时自动生成，构建流程已自动处理；
    禁止手动创建/修改该目录文件，业务代码只写 src/logic/*.cc。
    """
    return json.dumps(pt.flythings_build_ui_flow(project_root, with_launch, device), ensure_ascii=False)


def flythings_generate_ui_preview(project_root: str, output_dir: str = '') -> str:
    """将项目 ui/*.json 生成 HTML 预览页（客户确认 UI 用，每个 json 生成同名 .preview.html）。
    ⚠️ 流程约束：HTML 布局出来后必须先本工具出预览给用户确认（只交付 .preview.html 文件，
    不生成图片/截图），确认 OK 后才允许 fui pack / 写逻辑 / 交付（未确认禁止开工）。
    无 UI 设计稿时：先建 json 布局 → 预览确认 → pack。
    """
    r = j2h.json2html(project_root, output_dir)
    if isinstance(r, dict) and r.get('success'):
        for f in r.get('files', []):
            jp = os.path.join(project_root, 'ui', f.get('json', ''))
            if os.path.isfile(jp):
                try:
                    with open(jp, encoding='utf-8-sig') as fh:
                        data = json.load(fh)
                    f['controls'] = sum(1 for k, v in data.items()
                                         if isinstance(v, dict) and '__' in k)
                except Exception:
                    pass
        r['projectRoot'] = project_root
        r['outputDir'] = output_dir or os.path.join(project_root, 'ui')
        r['note'] = 'html 为客户预览稿；设备端仍用 fui pack 生成的 ftu，两者同源于 json'
    return json.dumps(r, ensure_ascii=False)


def flythings_html_to_json(input_html: str, output_json: str = '', res: str = '') -> str:
    """受限 HTML 交互原型 → ui/*.json 布局。

    ⚠️ 规范内嵌（HTML_SUBSET，无需另找文档）：
    - 结构：<div class="screen" data-res="WxH" data-bg="#RRGGBB"> 为根（也可用 data-width/data-height 或 style 宽高替代 data-res；
      data-background 与 data-bg 互为别名；缺省分辨率 480x272，建议显式传 res 参数或写 data-res）。
    - 控件映射：div.text/p/span→textview；div.btn/button→button；div.input/input→edittext；
      div.bar/seekbar→seekbar；div.card/window/panel→window 容器（子控件相对坐标）；div.modal/dialog→弹窗（modal+隐藏）；
      div.list/listview→listview（子项见下）；div.checkbox→checkbox；div.radio/radiogroup→radiogroup；div.icon/img→图标 textview。
    - 定位：data-x/data-y/data-w/data-h（或 data-left/top/width/height、style left/top/width/height）。
    - 字号：data-fs / data-font-size / data-fontSize / 内联 style="font-size:NNpx" 都认。
    - 颜色：data-color 文字色、data-bg 或 data-background 背景色（textview/button/edittext 均支持背景）。
    - 命名：data-caption 指定控件名（C 标识符）；缺省自动 TextView1/Button1...。
    - listview 子项：子控件直接写在 list 容器内即生成 subItem；若用 <div class="item"> 包裹，
      转换器会展开包裹层、逐个生成 subItem（不会吞掉内部控件）。
    - 铁律：Z 序=书写顺序（弹窗最后）；文本只用汉字+ASCII+基础符号（/ % # - _ 空格），禁 emoji；
      进度条用 div.bar；输入框用 div.input（系统键盘）；颜色一律 #RRGGBB 6 位。
    - ⚠️ CSS 效果不硬转：HTML 原型允许任意效果（emoji/iconfont/CSS 渐变阴影圆角/粒子/3D 动效），
      但 FlyThings 无 CSS 引擎，转 json 时效果一律转图片 + 控件组合实现：
      渐变/复杂背景/阴影/描边 → 切 PNG 或 .9.png 用 data-pic 引用；emoji/iconfont → 转 PNG 图标；
      loading/旋转/粒子动效 → 序列帧 PNG 或 GIF（imageanim 动图控件，循环次数 ≤0 无限循环）；
      按钮两态 normal+pressed（_p 后缀）→ picTab{pic0,pic1}。
      转换器对 style 中的效果属性（linear-gradient/box-shadow/border-radius/animation 等）
      自动输出 warning 提示转图，不会硬转。
    - ✅ JS 交互设计（2026-08-29 沛哥建议）：第一套 HTML 效果稿建议直接写 JS 交互——
      点击弹窗/页面切换/tab 切换/列表滚动/数据模拟/动效触发等，让客户在浏览器里直接"点得动"，
      前期效果确认和修改效率翻倍。转换器自动忽略 <script> 标签和 onclick 等交互属性（实测验证），
      JS 只服务于浏览器预览确认，不转 json；FlyThings 端交互逻辑由 logic.cc 实现（json 布局 + 回调）。
    - ✅ CSS 效果自动转图（2026-08-29 沛哥要求 + 2026-09-01 路径修复）：style 里出现 linear-gradient/box-shadow/border-radius/
      animation 等效果时自动生成图片资源（不再只 warning）——渐变→grad_*.png（backgroundPic）、
      阴影+圆角→shadow_*/gradshadow_*.png（渐变阴影自动合成）、emoji 文本→emoji_*.png 图标、
      class=loading/spinner 或 animation:spin→loading_*.gif（12 帧）+ imageanim 控件（warning 提示
      logic.cc 里 mXXXPtr->play()）。图片自动输出到 <项目>/resources/images/（output_json 在 <项目>/ui/ 下时自动识别；
      json 引用路径 images/xxx.png 相对 resources 目录，与设备加载一致；非 ui/ 目录结构回退 json 同目录 images/ 并警告）。
      返回 generatedAssets 计数 + assetDir 实际输出目录。

    ⚠️ 客户发说明书/参考照片/需求文档时不能直接转 json：先按 skill §7.0 引导分析
    提炼 UI 需求清单 → 用户确认 → 再写受限 HTML → 才调本工具。
    ⚠️ 转换后必须先 json2html/generate_ui_preview 出预览稿给用户确认（只交付 .preview.html
    文件本身，不生成图片/截图），确认 OK 后才允许 fui pack / 写逻辑 / 交付（未确认禁止开工）。
    output_json 缺省为 html 同名 .json；res 可覆盖分辨率（如 "800x480"）。
    """
    return json.dumps(h2j.html2json(input_html, output_json or None, res or None), ensure_ascii=False)


def flythings_json_to_html(target: str, output_dir: str = '') -> str:
    """json 布局 → HTML 预览稿（客户确认 UI 用，只交付 .preview.html 文件本身，不生成图片/截图）。
    target 为项目根目录（全部 ui/*.json）或单个 json 文件路径。
    ⚠️ HTML 布局出来后必须先调本工具出预览稿给用户确认，确认后才开工（pack/写逻辑）。
    """
    return json.dumps(j2h.json2html(target, output_dir), ensure_ascii=False)


def flythings_list_packages(platform: str = '') -> str:
    """列出依赖包生态（platform 如 F133/Z20，留空列全部），含功能描述与版本。写代码前调用。"""
    return json.dumps(pkgtools.flythings_list_packages(platform or None), ensure_ascii=False)


def flythings_query_package(package: str, platform: str = 'F133') -> str:
    """查询依赖包在指定平台的可用版本。传入包名（如 mqtt-cxx）与平台。"""
    return json.dumps(pkgtools.flythings_query_package(package, platform), ensure_ascii=False)


def flythings_recommend_manifest(features: str, platform: str = 'F133') -> str:
    """按功能需求推荐 Manifest.xml 依赖配置。features 为逗号分隔关键词，如 'mqtt,json,蓝牙'。"""
    flist = [f.strip() for f in str(features).split(',') if f.strip()]
    return json.dumps(pkgtools.flythings_recommend_manifest(flist, platform), ensure_ascii=False)
def flythings_add_package(project_root: str, package: str, version: str = '',
                          platform: str = '', with_install: bool = True) -> str:
    """把 package 添加进项目 Manifest.xml 并执行 fun install 拉取依赖（添加包闭环流程）。

    - 版本解析顺序：本地 registry → 离线 catalog → 在线（semver 取最新，不依赖包实体是否存在）
    - 已声明同包则更新版本；未声明则追加 <package id version/>；保留原 Manifest 格式
    - with_install=True（默认）执行 fun install 同步依赖（Manifest 变更后自动拉取）
    用户说「给项目加个 XXX 包 / 项目要用 MQTT/JSON/蓝牙需要加依赖」时调用。
    """
    return json.dumps(pkgtools.flythings_add_package(project_root, package,
                                                     version or None,
                                                     platform or None,
                                                     with_install), ensure_ascii=False)




def flythings_search_package(keyword: str, platform: str = 'F133') -> str:
    """按功能关键词搜索可用 package（mqtt/json/http/ssl/ble/ota/audio 等）。"""
    return json.dumps(pkgtools.flythings_search_package(keyword, platform), ensure_ascii=False)


def flythings_get_package_api(package_id: str, platform: str = 'F133', version: str = '') -> str:
    """获取 package 的头文件路径、类方法签名、使用示例。传入包名与可选版本。"""
    return json.dumps(pkgtools.flythings_get_package_api(package_id, platform, version or None), ensure_ascii=False)


def flythings_resolve_dependencies(packages: str, platform: str = 'F133') -> str:
    """递归解析 package 依赖树并检测冲突。packages 为 JSON 数组字符串，
    如 '[{"id":"mqtt-cxx","version":"3.2.0"}]'。返回依赖树、解析结果与冲突建议。
    """
    return json.dumps(pkgtools.flythings_resolve_dependencies(packages, platform), ensure_ascii=False)


def flythings_generate_manifest(features: str, platform: str = 'F133') -> str:
    """按功能需求生成完整 Manifest.xml（依赖递归补齐）。features 为逗号分隔关键词，
    如 'mqtt,json,http_download,ssl_mqtt'。
    """
    flist = [f.strip() for f in str(features).split(',') if f.strip()]
    return json.dumps(pkgtools.flythings_generate_manifest(flist, platform), ensure_ascii=False)


def flythings_create_bin_project(project_root: str, project_name: str = '', platform: str = 'z21',
                                 app_version: str = '1.0.0', description: str = '',
                                 with_build: bool = True) -> str:
    """创建「可执行程序」项目（fun create --type bin）并编译为直接可运行的 ELF 二进制。

    - 项目类型 4 选 1：zkgui（UI应用）/ bin（可执行程序）/ staticLibrary / sharedLibrary
    - bin 项目结构极简：fun.json（"type": "executable"）+ src/main.cpp（标准 int main()）
    - 编译：fun build → 产物 .fun/{platform}/{项目名}，ELF 魔数验证
    - 部署：adb push + chmod +x 直接跑（无 zkgui 宿主，不能启动 UI 应用）
    - 非交互：自动传 --app-version/--description 跳过向导；目录非空直接报错（防覆盖询问卡死）

    用户要「编译出可直接执行的二进制/bin 程序/执行程序（非 UI 应用）」时调用。
    platform 默认 z21（支持 z20/t113/f133 等）；project_name 缺省取目录名。
    """
    return json.dumps(pt.flythings_create_bin_project(
        project_root, project_name, platform, app_version, description, with_build),
        ensure_ascii=False)


def flythings_gen_ui_test(project_root: str, test_type: str = 'ask', output_dir: str = '',
                          platform: str = 'z21', with_build: bool = True,
                          monkey_count: int = 500) -> str:
    """根据 UI json 布局生成自动化测试项目（纯代码，不依赖 AI，省 token）。

    ui/*.json 已含全部控件坐标（position left/top/width/height）与可交互信息
    （touchable/visible），直接解析生成可编译的 bin 测试项目：
      ask      - 询问用户三种验收方式（默认，返回选项让用户选）
      traverse - 遍历控件验收：所有可交互控件逐个点击+滑动 + 图片资源缺失检查 + logcat 配合
      monkey   - 压测 MonkeyTest：随机 tap/swipe 指定次数，发现潜在隐患
      custom   - 自定义验收：按用户输入要求生成（差异化逻辑走 AI，此模式仅返回提示）

    用户提出「自动化测试 / 验收 / 遍历控件 / 压测 / Monkey」等需求时调用；
    默认先问用户选哪种验收方式，避免 AI 参与重复生成（省 token）。
    """
    return json.dumps(tt.flythings_gen_ui_test(
        project_root, test_type, output_dir, platform, with_build, monkey_count),
        ensure_ascii=False)


def flythings_attach_cli_tools(project_root: str, with_fyx: bool = True) -> str:
    """复制 fui.exe（→项目 ui/）与 fun.exe（→项目根目录）到项目，随项目交付。
    生成后用 fun.exe build 编译、launch 推送，无需客户导入 IDE。
    ⚠️⚠️ src/activity/ 目录（mainActivity.cpp/h）由 IDE 编译时自动生成，禁止创建/修改；
    业务代码只写 src/logic/*.cc。
    """
    return json.dumps(pt.flythings_attach_cli_tools(project_root, with_fyx), ensure_ascii=False)


def flythings_create_project(project_root: str, platform: str, resolution: str,
                             app_name: str = '', with_cli: bool = True, force: bool = False) -> str:
    """从 HelloWord Demo 复制骨架创建 FlyThings 项目，自动替换工程名/分辨率/平台。
    传入目标项目根目录、平台（F133/F135/Z21）与分辨率（如 800x480）。
    ⚠️ platform/resolution 必填且必须来自用户明确提供，未指定时先询问，禁止猜测或用默认值。
    ⚠️⚠️ src/activity/ 目录（mainActivity.cpp/h）由 IDE 编译时根据 ftu 自动生成，
    禁止创建/修改/覆盖该目录任何文件！业务代码只能写 src/logic/*.cc；
    mXXXPtr 控件指针 / ID_MAIN_* 宏 / 回调表 / findControlByID 初始化全部由 IDE 自动生成，禁止手写。
    """
    return json.dumps(pt.flythings_create_project(project_root, platform, resolution,
                                                  app_name, with_cli, force), ensure_ascii=False)


def flythings_check_project_deps(project_root: str, platform: str = 'F133') -> str:
    """扫描项目 include 的三方库与 Manifest 声明对比，返回缺失依赖。
    需要三方能力（MQTT/HTTP/JSON/蓝牙/SSL 等）时先调用。
    """
    return json.dumps(pkgtools.flythings_check_project_deps(project_root, platform), ensure_ascii=False)


def flythings_generate_ui_assets(project_root: str, assets: str) -> str:
    """生成 UI 图片资源（图标/牌面/按钮背景等），输出到 <项目>/resources/images/。

    ⚠️ 三级降级策略（任何环境都能出图）：
      ① AI 生图（配置了 OPENAI_API_KEY 且网络可达 → gpt-image-2 透明底，最精致）
      ② 本地 emoji 渲染（Windows seguiemj.ttf / Linux NotoColorEmoji → 卡通风，羊了个羊同款）
      ③ 线条/几何兜底（Pillow 画圆/方/星/心/对勾等 → 无 AI 无 emoji 字体也能出）
    最终用户（客户）没有 AI 能力时自动降级，无需任何外部依赖。

    ⚠️ 图片资源铁律（2026-08-29 羊了个羊实战，务必遵守）：
      ① 图片尺寸必须与 json 控件尺寸一致（瓦片 76×76 控件 → 76×76 图；槽位 72×72 → 72×72 图），
         不要生成大图让控件缩放，也不要小图拉伸。
      ② 圆角卡片图四角必须真透明（alpha=0）：渐变/填充底是整矩形画的，圆角只是描边轮廓，
         必须用圆角 mask 裁剪（putalpha）清掉弧线外角落；阴影模糊（GaussianBlur）会溢出到弧线外，
         最后整体再裁一次圆角清掉残影。
         通用函数 gen_res.rounded_card()（渐变+圆角+描边+高光）已内置裁剪；
         gen_res.gen_gradient(..., radius=r) 也已修复（radius>0 自动裁圆角）。
      ③ 用透明角图片的按钮不要设 bgColorTab：透明角会透出按钮底色而不是窗口背景，
         需要透背景的图片按钮（瓦片/槽位/图标钮）不放 bgColorTab；纯文字按钮才用底色。
      ④ 功能按钮尽量用图片按钮：picTab{pic0: normal, pic1: pressed(_p 后缀)} 两态图。
      ⑤ 生成后必须检查四角 alpha：img.getpixel((2,2))[3] == 0 才算合格。
      ⑥ 路径规范（2026-09-01 沛哥要求）：自动生成的图片一律放 <项目>/resources/images/，
         json 布局引用路径写 images/xxx.png（相对 resources 目录，与设备/ftu 加载一致）；
         返回的 path 字段就是 images/xxx.png，直接填 json 的 backgroundPic / picTab.pic0 / picTab.pic1，
         不要写绝对路径，也不要带 resources/ 前缀。

    assets 为 JSON 数组字符串，每项：
      {"name": "icon_ok.png", "size": 128,
       "prompt": "cute white cartoon sheep, game icon",   ← 有则优先 AI 生图
       "emoji": "🐑",                                      ← AI 失败后用它
       "color": "#42C9FF" 或 [r,g,b,a], "kind": "check"} ← 线条兜底参数
    kind 可选：check/charging/wifi/alert/circle/square/star/heart。
    name 必填（自动补 .png）；返回每项实际生成方式（method: ai/emoji/line）。
    """
    return json.dumps(h2j_genres.gen_ui_assets(project_root, assets), ensure_ascii=False)


def flythings_fix_project(project_root: str, kb_id: str = '', apply: bool = False) -> str:
    """按修复知识库（fix.log FT-001~FT-009）自动诊断并修复 FlyThings 项目。

    9 条规则覆盖：二维码控件(FT-001)/SeekBar 9-patch 黑框(FT-002)/SeekBar 尺寸匹配(FT-003)/
    fui generated 缓存(FT-004)/INIT_UI_TIMERS 宏(FT-005)/多 Window 可见性(FT-006)/
    部署顺序(FT-007)/Pillow 超采样抗锯齿(FT-008)/TextView 最小尺寸(FT-009)。

    传入项目根目录完整路径。
    - kb_id 传 'FT-001' 等只处理该条；留空处理全部 9 条；
    - apply=False（默认）仅诊断（dry-run），返回每个规则命中/未命中与修复计划；
    - apply=True 执行修复，并逐条 verify 验证。
    遇到「二维码没显示/SeekBar 黑边/进度条对不齐/新控件指针缺失/定时器不触发/
    多窗口堆叠/随机加载图片失败/圆角锯齿/文字截断」等问题时调用。
    """
    return json.dumps(ftx.flythings_fix_project(project_root, kb_id, apply), ensure_ascii=False)


def flythings_i18n_scan(project_root: str) -> str:
    """诊断项目多语言（i18n）现状：i18n/*.tr 语言文件、key 对齐、布局 @key 引用完整性。
    项目做多语言时先调用；返回 JSON：languages/keysPerLanguage/缺失 key/引用缺失。
    多语言机制：翻译文件 i18n/<语言>.tr（文件名三段式 xx_XX-语言名，Android strings.xml 同款），
    布局 text 写 @key，代码 setTextTr("key") 或 LANGUAGEMANAGER->getValue("key")。"""
    return json.dumps(itx.flythings_i18n_scan(project_root), ensure_ascii=False)


def flythings_i18n_add_language(project_root: str, lang: str, lang_name: str, base_lang: str = 'zh_CN', context: str = '') -> str:
    """添加新语言：从基础语言（缺省 zh_CN）复制 key 骨架，生成 i18n/<lang>-<lang_name>.tr 待翻译文件。
    lang 为语言代码（如 fr_FR），lang_name 为语言名（如 法语，显示在切换列表）。
    返回待翻译清单（key→基础语言原文）+ 专业翻译提示（结合项目语境，如车载项目 CAN BUS 不译公共汽车）；
    翻译后调用 flythings_i18n_import 写回。"""
    return json.dumps(itx.flythings_i18n_add_language(project_root, lang, lang_name, base_lang, context), ensure_ascii=False)


def flythings_i18n_export(project_root: str, lang: str = 'zh_CN', keys: str = '', context: str = '') -> str:
    """导出指定语言（缺省 zh_CN）的 key→文本清单（JSON），供翻译后 import 写回。
    keys 可选：逗号分隔的 key 子集；缺省导出全部。context 可选：项目语境描述，
    返回 translationGuide 提示 AI 专业翻译（术语如 CAN BUS 保持行业译法）。"""
    return json.dumps(itx.flythings_i18n_export(project_root, lang, keys, context), ensure_ascii=False)


def flythings_i18n_import(project_root: str, lang: str, translations: str, merge: bool = True) -> str:
    """将翻译结果写回项目 i18n/<lang>.tr（生成新语言文件或更新已有）。
    translations 为 JSON 对象 {"key": "翻译文本"}；merge=True 与已有内容合并，False 整体覆盖。"""
    return json.dumps(itx.flythings_i18n_import(project_root, lang, translations, merge), ensure_ascii=False)


def flythings_i18n_refactor(project_root: str, lang: str = 'zh_CN', dry_run: bool = True) -> str:
    """把布局 json 里写死的非空文本控件替换为 @key 引用（多语言改造辅助）。
    dry_run=True 只预览不改文件；False 执行替换并写入指定语言 .tr。
    纯数字/时间占位文本自动跳过。"""
    return json.dumps(itx.flythings_i18n_refactor(project_root, lang, dry_run), ensure_ascii=False)


# 注册辅助：把上面全部工具注册到任意 FastMCP 实例
def register_all(mcp):
    mcp.tool()(flythings_get_version)
    mcp.tool()(flythings_search)
    mcp.tool()(flythings_read_json)
    mcp.tool()(flythings_get_project_spec)
    mcp.tool()(flythings_validate_project)
    mcp.tool()(flythings_fui_pack)
    mcp.tool()(flythings_edit_ftu)
    mcp.tool()(flythings_build_ui_flow)
    mcp.tool()(flythings_generate_ui_preview)
    mcp.tool()(flythings_html_to_json)
    mcp.tool()(flythings_json_to_html)
    mcp.tool()(flythings_attach_cli_tools)
    mcp.tool()(flythings_create_project)
    mcp.tool()(flythings_create_bin_project)
    mcp.tool()(flythings_gen_ui_test)
    mcp.tool()(flythings_check_project_deps)
    mcp.tool()(flythings_generate_ui_assets)
    mcp.tool()(flythings_fix_project)
    mcp.tool()(flythings_i18n_scan)
    mcp.tool()(flythings_i18n_add_language)
    mcp.tool()(flythings_i18n_export)
    mcp.tool()(flythings_i18n_import)
    mcp.tool()(flythings_i18n_refactor)
    mcp.tool()(flythings_list_packages)
    mcp.tool()(flythings_query_package)
    mcp.tool()(flythings_recommend_manifest)
    mcp.tool()(flythings_add_package)
    mcp.tool()(flythings_search_package)
    mcp.tool()(flythings_get_package_api)
    mcp.tool()(flythings_resolve_dependencies)
    mcp.tool()(flythings_generate_manifest)
