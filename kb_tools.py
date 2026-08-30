# -*- coding: utf-8 -*-
"""FlyThings_mcp_open: 全套 MCP 工具定义（stdio 本地部署，完全开放）。

每个工具都是普通函数，返回 str/JSON 字符串；由 mcp_server.py（stdio）注册。
⚠️ 开源版：检索完全本地化（自备 DASHSCOPE_API_KEY），不依赖任何远程 MCP 服务。
"""
import html.parser  # PyInstaller 打包需要（html2json 运行时导入，静态分析漏收）
import json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rag_search as rs
import project_tools as pt
import package_tools as pkgtools
import ui_preview as up
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

# ========== MCP 版本号（每次发布递增，AI/用户可查询确认是否最新）==========
MCP_VERSION = '0.4.6-open'
MCP_BUILD = '2026-08-29'
MCP_FEATURES = [
    '2026-08-29: 控件能力全面校准（实测校准）——TextView 全能力（charsetTab 字符图/滚动/选中态 color2，text 不支持多行）/ CheckBox padding 三件套+两态图 pic2 选中 / Button 图片按钮自动去底色+五态图+背景图按钮 / CircleBar 圆形进度（clockwise 逆时针/有效图裁剪扇形）/ Diagram 波形（style 0折线1曲线/eraseSpace 刷新间距/region 绘图区）/ DigitalClock 时间格式 HH hh MM SS+冒号闪烁 / EditText 密码掩码 isPassword+提示色 / ImageAnim 动图 playFile+loopCount / ListView 行距+subItem 头像背景图 / Window 模态+自动隐藏+window 嵌套 / SlideWindow 图标滑动（items[] 两态图）/ ScrollWindow 滚动（dragMaxDis=内容尺寸）/ PageWindow 翻页（页面 window 叠放）/ 系统栏 topmost 悬浮+透明背景+局部悬浮块',
    '2026-08-29: 多国语言 i18n 工具升级——add_language 添加新语言（三段式文件名 xx_XX-语言名.tr 官方规范）/ export 带项目语境专业翻译提示（术语如 CAN BUS 不译公共汽车）/ setTextTr+updateLocalesCode API 对齐官方文档',
    '2026-08-29: 新增多国语言 i18n 工具——scan 诊断（语言文件/key 对齐/布局 @key 引用完整性）/ export 导出待翻译清单 / import 写回生成 .tr / refactor 布局硬编码文本转 @key；翻译文件为 i18n/*.tr（Android strings.xml 同款），代码取词 LANGUAGEMANAGER->getValue()',
    '2026-08-29: 新增 flythings_fix_project 自动修复工具——9 条基础规则：二维码控件(FT-001)/SeekBar 9-patch 黑框(FT-002)/SeekBar 尺寸(FT-003)/fui 缓存(FT-004)/INIT_UI_TIMERS 适配 FUN_BUILD(FT-005)/多 Window 可见性(FT-006)/部署顺序(FT-007)/超采样(FT-008)/TextView 尺寸(FT-009)',
    ' 扩充 NTP/包管理(FT-010~014)：semver 版本对齐 registry/新依赖先 install/NTP 不阻塞 UI/TZ 时区/包 id 查 registry；',
    ' 扩充 HTML 转图(FT-020~023)：语义图标转 PNG/渐变圆角背景/资源尺寸匹配/4 阶段自检；',
    ' detect(apply=False) + fix(apply=True) + verify 三阶段',
    '2026-08-29: HTML 原型支持 JS 交互设计——效果稿直接写 JS（点击弹窗/页面切换/tab/数据模拟），浏览器可直接点击预览，转换器自动忽略 script/onclick',
    '2026-08-29: HTML→json 自动转图——style 里 linear-gradient/box-shadow/border-radius/animation 自动生成图片资源（渐变/阴影/emoji/loading GIF），不再仅警告',
    '2026-08-29: 图片资源生成规范——图片尺寸与控件一致/圆角四角真透明/透明角按钮不设底色/picTab 两态图',
    '2026-08-28: 包检索走离线 catalog/版本取最新/manifest 过滤传递依赖/html2json 支持 font-size/背景色/分辨率/列表展开/fun launch 多设备自动连/validate 宏回调校验/cacert.pem 检查',
    'FlyThings_mcp_open: 完全开源版本，本地部署零远程依赖、零 API Key',
    '检索完全本地：内置 bge-small-zh 模型（免 Key），不可用时自动 BM25 关键词兜底',
    'create_project: 从 HelloWord Demo 复制骨架，平台/分辨率必填询问',
    'validate_project: 规范检查 + 平台探测 + json/ftu 时间戳防呆 + 空白项目判定',
    'build_ui_flow: fui pack → fun install → fun build → fun launch 一键交付',
    'html_to_json / json_to_html / generate_ui_preview: HTML 原型 → json 布局 → 预览',
    'package 全家桶: list/query/search/api/resolve/manifest 依赖管理',
    'search: wiki 118 篇文档 RAG 检索（本地向量 + BM25 双模式）',
    'flythings_edit_ftu: 布局编辑——set 改属性/remove 删控件/add 复制新增/set_root 改根',
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


def flythings_read_ftu(ftu_path: str) -> str:
    """解析 .ftu 布局文件为 JSON（分辨率、控件列表、caption→id 映射）。传入 ftu 完整路径。"""
    return json.dumps(pt.flythings_read_ftu(ftu_path), ensure_ascii=False)


def flythings_read_json(json_path: str) -> str:
    """解析 .json 布局文件为 JSON（分辨率、控件列表、caption→id 映射）。传入 json 完整路径。"""
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
    return json.dumps(up.flythings_generate_ui_preview(project_root, output_dir), ensure_ascii=False)


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
    - ✅ CSS 效果自动转图（2026-08-29 沛哥要求）：style 里出现 linear-gradient/box-shadow/border-radius/
      animation 等效果时自动生成图片资源（不再只 warning）——渐变→grad_*.png（backgroundPic）、
      阴影+圆角→shadow_*/gradshadow_*.png（渐变阴影自动合成）、emoji 文本→emoji_*.png 图标、
      class=loading/spinner 或 animation:spin→loading_*.gif（12 帧）+ imageanim 控件（warning 提示
      logic.cc 里 mXXXPtr->play()）。图片输出到 json 同目录 images/，返回 generatedAssets 计数。

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
    mcp.tool()(flythings_read_ftu)
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
