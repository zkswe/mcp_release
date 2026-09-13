# -*- coding: utf-8 -*-
"""FlyThings_mcp_open: 全套 MCP 工具定义（stdio 本地部署，完全开放）。

每个工具都是普通函数，返回 str/JSON 字符串；由 mcp_server.py（stdio）注册。
✅ 开源版：检索完全本地化（内置 bge-small-zh 向量模型，免 API Key，
不可用时自动降级 BM25），不依赖任何远程 MCP 服务。
"""
import html.parser  # PyInstaller 打包需要（html2json 运行时导入，静态分析漏收）
import inspect
import io
import json, math, os, re, shutil, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import platforms as _platforms   # 平台唯一来源：默认值/平台清单/包生态键都从这里取
import rag_search as rs
import project_tools as pt
import package_tools as pkgtools
import hardware_tools as hw
UI_TOOLS = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ui_tools')
if getattr(sys, 'frozen', False):  # PyInstaller 打包：ui_tools 随包进 _MEIPASS
    UI_TOOLS = os.path.join(sys._MEIPASS, 'ui_tools')
if UI_TOOLS not in sys.path:
    sys.path.insert(0, UI_TOOLS)
import html2json as h2j
import json2html as j2h
import gen_res as h2j_genres
import i18n_tools as itx
import test_tools as tt
# UI 可视化编辑 / 像素验收（2026-09-10 起）：缺依赖时降级为对应工具报错，不影响其它工具
try:
    import ui_editor as uied
except Exception:
    uied = None
try:
    import ui_edit_apply as uia
except Exception:
    uia = None
try:
    import ui_diff as udf
except Exception:
    udf = None
try:
    import check_all as chk_all
    from check_all import verify_assets as _verify_assets
    if not callable(_verify_assets):
        raise ImportError('verify_assets missing')
except Exception:
    chk_all = None

try:
    import device_screenshot as dss
except Exception:
    dss = None

# ========== MCP 版本号（每次发布递增，AI/用户可查询确认是否最新）==========
MCP_VERSION = '0.27.44-open'
MCP_BUILD = '2026-09-12'
MCP_FEATURES = [
    '2026-09-13: RTL8733BS 蓝牙 bring-up 实践入库 v0.27.44-open（沛哥转交 AI 长跑验收记录，要求「按实际情况确认处理」）——新增 `knowledge/hardware/bt-rtl8733bs-bringup.md`：①**两个前置条件**：BT 必须先在 sysfs 上电（`state_bt` 0→50ms→1→300ms ×2 轮，且被 `persist.wifi.module==8733bs` 前置门挡住，不匹配就走 AIC 分支=完全静默）+ **必须先跑 Realtek hciattach 预初始化**（H5 同步握手 → 读 ROM → 下补丁固件 → 115200 切 1500000），做完才应答标准 HCI ②**电源控制流程与接口单列一节（硬件关联，沛哥特别点名）**：节点与语义（`state_bt` / `state_wifi`，combo 模组上两个独立开关；多候选路径 + `access()` 存在性判断；纯 sysfs 文件读写，不走 ioctl/gpio）+ 调用时机与链路（btstack 初始化前、同一 BT 线程内；前置门不匹配走 AIC 分支=不碰电源不下固件）+ 写后**回读确认 on/off**（100×30ms）+ 失败必须返回 -1 由上层退出（否则一路静默，日志要往前找 rtk 报错）+ 现场排查 6 步 + 复用注意（路径随枚举变、无独立 reset GPIO、断电后等待要秒级）——实测曾卡在 `state_bt` 几小时，必须留档 ③**传输必须是 H5 + 偶校验 8E1 + 无流控**，H4/8N1 必失败；预初始化前判活看厂商命令 `0xFC6D`，判"芯片有没有回"只看事件码 `0x01~0x5F`（`0x6E` 是 btstack 本地的 TRANSPORT_PACKET_SENT，不算回应）④**线程铁律**：btstack 的 run loop init / data source 注册 / TLV / `hci_init` 必须在同一条 BT 线程内做完（违反 = 静默卡 `INITIALIZING`，连 tick 都没有），跨线程走 socketpair data source；`hci_add_event_handler` 必须在 `hci_init` 之后 ⑤**入库前逐条机器核对**并修正三处："必须自研 uart/SLIP" → 改为先查当前 btstack 构建的 frame/parity 能力（v85x btstack 1.7.2 已声明 `set_parity` + 四个 frame 回调 + 自带 slip_wrapper，优先用配置项）；版本锁定在 **Manifest.xml** 不是 fun.json；原稿头注的源工程归属不入库 ⑥固件随应用打包（`src/dependencies/bin/firmware/rtlbt/` → `/res/bin/firmware/rtlbt/`，运行时候选链 /res → /data → /tmp）、TLV 落 `/data`、"抓包重放学遥控器不成立"（BT HID 走加密链路，正解是本机做 hci 主机建映射）⑦未复核项（设备/PC 侧观察）在文档 §7 显式标注，不冒充机检结论。',
    '2026-09-12: check_all 新增 #18 设计令牌漂移检测 v0.27.43-open（沛哥「取」impeccable doctor 思路：让交付物自己变脏能被机器发现）——①**口径**：`DESIGN.md` 是冻结的视觉真相，json 里的颜色/字号应当来自令牌，出现令牌外的值 = 漂移（FAIL）。②**解析**：按 `##` 切节——色彩令牌节取 `#RRGGBB`、字号阶梯节取 8–400 整数、间距梯度节取正整数；另支持全文行内 `hero` 例外与「漂移豁免: #RRGGBB 18」显式豁免（留痕，便于单点例外）。③**结构值例外**：0（透明）/ -1（未设）/ 16777215（纯白）不经令牌。④**兼容存量**：无 `DESIGN.md` 或令牌表未填全 → NOTE 跳过（不 FAIL，老工程不受影响）。⑤**实现**：新增 `verify_design_tokens()`（与 #18 同源），间距梯度外的纵向间距记 WARN（人工确认，不阻断）。⑥**目标**：让「改一处令牌 = 全局一致」可机检，把 impeccable 的 detector/doctor 思路落到嵌入式 json 上。',
    '2026-09-12: 修 `flythings_create_project` 工程名半替换（沛哥：建工程名字怎么都是 Helloword_V85x，没按文件夹命名）v0.27.42——根因：重命名只替换**模板目录名**字符串，而模板内容里的真实工程名与目录名对不上（V85X 目录 .project 写 Helloword_V85x、.cproject 残留 template_z20_smarthome；Z20 写 Helloword_Z20；T113 写 HelloWord_T113Nor → 半替换剩 Nor 尾）→ 改为先从模板内容读真实旧名（.project `<name>` + .cproject 工作区路径 `name="/XXX(/Release|/Debug)"` + `<project id="XXX.` 前缀）再替换，`<name>` 兜底写死新名；6 平台实测（app_name 优先，不传用文件夹名）0 残留；v0.27.42-open',
    '2026-09-12: 滑动/拖拽手感规范入库 v0.27.42（沛哥：列表 dragMaxDis 按列表高度填 → 一次拖拽把整屏列表拽出去，交互不好）——①**字段语义定死**：listview 的 `dragMaxDis` = **越界拖拽上限（overscroll）**，不是「列表行程」（行程 = max(0, 项数×行高−可视高)，运行期由数据决定）；同名字段在 scrollwindow/pagewindow/slidewindow 上是「行程」（200 / 内容尺寸），两种用法禁止混填 ②**取值规范**（基准 1024×600）：listview 硬约束 `dragMaxDis` < 控件可视高（≥ 即不合格）、≤ 一行高；无回弹 = `0 + edgeEffect:0`，要回弹 = `1 + 50`（`1 + 0` 自相矛盾）；循环列表用 50；分辨率换算 `round(scale×50)` 下限 24 ③**实机手感验收**：边界 1-2 帧内拽不动带阻尼、松手 200-300ms 回弹、禁止整屏拖离后长时间露底 ④新增 `knowledge/uicontrols/scroll-drag-interaction-spec.md`（唯一权威口径 —— 官方站/wiki 未收录该字段语义），listview-fields / slidewindow-fields / pagewindow-fields / json-field-mandatory 四处字段表补语义行 + 互链 ⑤证据：SampleUI-New + 4 个官方 Demo + 真实工程统计（取值只落 0/50/200/内容尺寸 4 档）；v0.27.42-open',
    '2026-09-12: 平台判定收成「按真实条件」单一入口 v0.27.41（沛哥：检讨 pause-touch 那类「按状态/代理信号判定，而非按真实条件判定」的问题）——①**平台真相由三套收成一套**：`platforms.py` 新增包生态命名空间 `PACKAGE_KEYS`/`PACKAGE_ALIASES`（f136->F135、v85xemmc、t113stdcxx、历史 v853/v552/v553）+ 仅包生态平台 `PACKAGE_ONLY`（z6s/z261/z235x/h500s/a33nor），并新增 `package_key()`/`resolve()`/`package_keys()`；`package_tools.PLATFORM_ALIAS`（原来只认 v85x 家族，F133EMMC/F136/T113STDCXX 全不认）与 `test_tools.SUPPORTED_PLATFORMS`（手抄元组）改为引用 platforms.py ②**不再按平台名字符串白名单拦能力**：`test_tools._platform_elf` 改为解析后**按 bin_tools 目录里真实存在的文件**判定；`hardware_tools` 区分「真实平台但硬件库未登记」（新错误码 PLATFORM_NOT_IN_HARDWARE_LIB）与「完全不认识」（旧行为一律回「未知平台」，把 z6s/f136emmc 这类真平台说成不存在）③**建工程报错不骗人**：`validate()` 对仅包生态平台明确回「有依赖包、无 IDE 模板/工具链，无法建工程」+ 可建工程清单；未知名字补「相近的已知平台」④**默认平台可见化**：新增 `DEFAULT_BIN_PLATFORM="Z21"`（原 create_bin_project/gen_ui_test 签名里写死的 z21），其余默认值统一引用 `DEFAULT_PLATFORM`；docstring/提示里手写的「F133/F135/Z21」枚举改为运行时由 supported() 生成 ⑤**去静默**：`hardware_tools._known_platform` 校验器不可用时返回 None 并写进 warnings（原 `except Exception: return True` 属静默矞报）⑥**闸门加防回归**：`check_consistency` 新增平台单一来源校验（副本身份 + package_catalog 键全覆盖 + 源码里禁止再出现手写平台枚举），`gen_manifest` 平台表带 packageKey/buildable；新增 `tests/test_platform_resolution.py` 契约用例；v0.27.41-open',
    '2026-09-12: 统一触摸注入工具 `touch` v0.27.40（沛哥实测反馈：老 input 单点协议写死 + 节点要人工传 + IC/节点一变就注入不了，AI 只能反复 try）——新增 `bin_tools/{平台}/touch`（f133/f135/z20/z21/t113/v85x 全平台静态 ELF，源码 `tools/touch_inject/`）：①自动扫 /dev/input/event*，按 EVIOCGBIT 能力位挑触摸节点（名字含 touch/ts/gt9/panel 加分，keyboard/button/accel 扣分）②自动判协议：ABS_MT_SLOT=MT-B / ABS_MT_POSITION_X=MT-A / 否则单点，`--proto` 可手动覆盖 ③命令 tap/swipe/long/monkey/run/record/play + list/info（`list` 一次看清节点+协议，彻底替代「试注入看是否恒 0」的 try 流程）④MT 屏若同时声明 ABS_X/Y 就一并上报（兼容读单点轴的上层）、压力值按 EVIOCGABS 量程取中、tap 默认 down→up 间隔 40ms ⑤重编 `scripts/touch_build_all.sh`（WSL 全平台，静态 strip：RISC-V 66KB / musl 61KB / glibc 470KB）+ x86 自测脚本；MCP 侧 `flythings_gen_ui_test` 优先选 touch、deployHint 去掉硬编码 /dev/input/event1、平台矩阵补 f135、ui_test/mt_test 降为兼容保留；知识库 `knowledge/devflow/touch-inject-autotest.md` 与 bin_tools/README 改写为 touch 首选；v0.27.40-open',
    '2026-09-12: 固化升级出包 v0.27.39（沛哥：用户意图是「升级进设备」而不是调试时，要能打 update.img 刷进去）——新增 `flythings_pack_upgrade(project_root, out_path, release_version, ab, with_build, dry_run)`（工具数 33 → 34）：fun install →（可选）fun build → fun pack 出 update.img（默认 .fun/<平台>/update.img，-o 可改；--release-version 版本号；--ab 出 AB 系统 OTA 包），返回产物路径/大小/时间 + 四种落地刷法（TF卡 FAT32 根目录 / ADB setprop sys.zkupgrade.* / zkautoupgrade 插卡自动升级 / HTTP OTA 与局域网批量升级）；**意图分流**：调试=build_ui_flow（fun launch 临时推送，掉电即失），固化=pack_upgrade（update.img 掉电保留），deploy-scene-map.md 与两个 docstring 双向绑定防幻觉；已实测根因级坑：`FATAL sign error: exit status 0xc0000135` = fsimg.exe 是 32 位、系统缺 32 位 VC++ 运行时（msvcp140.dll/vcruntime140.dll），`package xxx not found in local` = 依赖未装需先 fun install —— 工具据此返回可执行 hint；⚠️ 打包需 Windows 装 VC++ x86 运行库（本机待装，故未跑通端到端出包）；知识库补 knowledge/devflow/upgrade-pack-image.md（CLI 出包全流程 + 与 IDE「路径配置→编译」对照）；v0.27.39-open',
    '2026-09-12: 硬件型号库（`flythings_hardware_info`）v0.27.38（沛哥：加个硬件文档模块，用户能快速选到自己手上的硬件，按平台/型号区分）——①新增唯一事实来源 `hardware_catalog.json`（平台 → 型号 → 屏幕/按键/接口规格 + 平台与型号差异化 + dataStatus/待补字段），工具只读它；配套 `scripts/gen_hardware_doc.py` 生成可检索文档 `knowledge/hardware/hardware-models.md`（带 --check，进一致性闸门，防「json 改了文档没跟」）②新增只读 op `flythings_hardware_info(model, platform)`：model 留空=列平台+已登记型号（platform 可过滤）；给型号=回 screen（分辨率/方向，可直接喂 create_project）/keys（按键值=/dev/input code，如 PocketDisplay4 的 105/103/108 = KEY_LEFT/UP/DOWN）/specs/differences（型号级差异，如 86 盒 Z6/Z20/Z21 三平台对比、价签 SSD201 vs SSD202 单双屏）/missing/source；**未收录型号回 MODEL_NOT_FOUND + 近似候选 + 平台型号清单，明确禁止按同系列外推规格**（查不到不编造）③型号匹配宽松（忽略大小写/连字符/下划线，支持别名）④首批入库：V85X=PocketDisplay4（4 寸 480×800 + 3 键值），Z21=SV50PD/SW80480070D_C/SW10600070D_C/SW48854050E1/SW48480040E，Z20=SW48480040D1/SW8001280101D-JQ/D1-JQ；工具数 32 → 33；⑤**定位（沛哥 2026-09-12 17:42 明确）：这是「预设参数」库，目的是让后期开发少问少核** —— 有具体型号就按返回的 `preset`（平台/分辨率/方向/按键）直接开工；**没有具体型号则确认平台 + 分辨率即可**，不必等数据补全；缺参数不叫「待补警告」而是 `optional[]`（非阻塞）；未收录型号回 `MODEL_NOT_FOUND` 时额外给 `fallback`（平台 + 分辨率就够开工），不卡流程、也不拿同系列外推填坑；v0.27.38-open',
    '2026-09-12: UI 可视化组收口为单入口 v0.27.37（沛哥：ui-visual 做个 action 入口）——`flythings_ui_editor` + `flythings_ui_edit_apply` + `flythings_ui_diff` → **`flythings_ui_visual(action, ...)`**（工具数 34 → 32）：action="editor" 出可拖拽编辑器网页、action="edit_apply" 把变更 JSON 写回 json、action="diff" 出截图像素差异清单；每个 action 只收自己的参数，**传了别家参数回 `visualNote` 明确提醒（不静默忽略）**，缺必填参数回 BAD_PARAMS + 本 action 正确参数清单，action="list" 回三动作参数表；三个旧名调进分发器回 OP_RENAMED，hint 里带「该用哪个 action」（RENAMED_HINT）；文档（README/knowledge/ui_tools 的「复制 AI 指令」文案/意图闸门）与契约用例同步；v0.27.37-open',
    '2026-09-12: 第五批（P2 收尾）v0.27.36——①**工具直接合并（36 → 34 个，旧名不再提供）**：`search`→`knowledge_search`、`search_package`→`package_search`（区分语料）；`generate_ui_preview` + `json_to_html` → **`ui_preview(target)`**（target 传项目目录或单个 json，同一实现）；`recommend_manifest` + `generate_manifest` → **`manifest(features, platform, project_root, dry_run=True)`**（默认只推荐不写盘；写盘要 project_root + dry_run=False，写前 .bak 并回显 affectedFiles）；调旧名回 `OP_RENAMED` + 新名（**只是错误提示，不执行，不留隐性别名**）②**新增 MCP 原生原语（`mcp_extras.py`，默认入口与 flat 入口共用）**：4 个 resources（`flythings://catalog/knowledge` 知识库目录 / `flythings://knowledge/<分类>/<文件>.md` 与 `/<文件>.md` 读整篇文档（白名单校验防穿越）/ `flythings://tools` 工具清单+风险分级 / `flythings://version`）+ 5 个 prompts（new-project / ui-from-prototype / ui-verify / deploy-debug / package-deps，均自带「确认前不 pack、不推真机」安全默认）；⚠️ FastMCP 的 URI 模板只匹配单段路径，所以分类文档与根目录文档用两个模板 ③**顺手修**：json2html 项目模式只扫扁平 `ui/*.json` → 分层 `ui/<分辨率>/*.json` 工程预览**静默出 0 页**（基准 SampleUI-New 就中招；与 v0.27.33 修的 check_all 同类问题，这次是预览侧）——现改为两种布局都扫（分分辨率不串页）；dispatcher 未知 op 的候选打分改进（合并/改名的旧名直接给新名）④契约用例 70 → 78 项（新增工具合并契约与 resources/prompts 契约）；v0.27.36-open',
    '2026-09-12: 多整屏 window 预览切页 v0.27.35（AI 反馈实测复现：官方推荐的「整屏 window + showWnd() 切页」架构下，.preview.html 把所有 visible=false 窗口 display:none，客户确认稿只能看到首页 → 等于失效）——json2html 预览页新增：①**页面切换条**：列出全部整屏 window 的 caption，点页签 = 显示该页/隐藏其余整屏窗口（默认页 = json 里首个 visible!=false 的整屏窗口，与 logic.cc 首屏对齐）②**hash 直达** `xxx.preview.html#window__29`（也认 `#29` 简写），便于把具体页面链接单发给客户 ③**「显示隐藏」开关**：visible=false 的控件/窗口以 35% 透明 + 橙色虚线幽灵框叠显，与 flythings_ui_editor 的 .ed-ghost 行为对齐 ④同一项目多 json 时额外出「项目页面」跳转行（单文件模式只链已有 .preview.html 的邻居，不出死链接）⑤左右方向键翻页；整屏判定 = 顶层 window 尺寸 ≥ 分辨率（±4px）；只在「有 ≥2 个整屏窗口 / 有 visible=false 控件 / 同项目多 json」时出条，单页无隐藏工程预览零变化；ui_editor（edit=True）不受影响；⑥**工具描述带上这条提示**（防 AI 选错/看漏）：`flythings_generate_ui_preview` 与 `flythings_json_to_html` 的 docstring 首行+提示行写明「整屏 window 多页工程自带页面切换条 + `#window__N` 直达 + 显示隐藏幽灵框」，并说明「只看到首页 = 该 json 确实只有一个整屏窗口」（不再建议改用 ui_editor 绕路）；双份 ui_tools 已同步；v0.27.35-open',
    '2026-09-11: 第四批（P2 上下文与检索质量）v0.27.34——①**docstring 瘦身 38%**（16,595 → ~10,200 字符）：长尾细节全部搬进可检索的知识库（新增 `knowledge/devflow/html-subset-quickref.md` 原型规范、`device-screenshot.md` 抓屏实现要点与踩坑、`ui-asset-rules.md` 图片资源铁律与抗锯齿管线、`ui-editor-usage.md` 编辑器用法），docstring 只留要点 + 检索关键词；**字数预算进门禁**（单 op ≤ 900 字符、全体 ≤ 12,000，超了 check_consistency 直接 FAIL） ②**工具面三模式**（`FLYTHINGS_MCP_MODE`）：默认 `dispatcher` 只暴露 1 个 `flythings_kb`（schema 开销最小，省 ~1 万 token/session），`all` = 分发器 + 36 独立工具（老配置兼容），`flat` = 只要 36 独立工具（新增 `mcp_server_flat.py`，给 Trae/Cursor/Claude Desktop 这类需要独立 schema 的客户端）；⚠️ 默认票是**行为变更**，受影响设 `FLYTHINGS_MCP_MODE=all` 恢复 ③**device_screenshot 参数分层**：fb/pixel/width/height/offset_y/flip/rotate/crop/name/timeout 可统一走 `advanced` JSON（已显式传的同名参数优先，旧客户端零影响；未知键/非法 JSON 回 BAD_ARGS + 可选项清单） ④**BM25 中文检索实质提升**：原实现把整段连续中文当一个 token（『Z20 屏幕截图怎么抓』→ 超长 token 只靠原文命中，降级时召回差）→ 改**字级 bigram**（与覆盖率判定共用同一套切词，单一实现）+ IDF + 长度归一 + 路径/标题加权；实测（10 条真实问法）top1 5→9、top3 7→10 ⑤**检索返回质量标记**：hits 带 `source`（实践/官方镜像），返回体带 `retrieval` / `degraded` / `quality`（ok | low_confidence | no_hit），**低置信也带上「禁其他 GUI 框架类推 + 查官方站」的检索边界提醒**（否则 AI 拿沾边片段当依据或转身去 web 猜）；覆盖率改 IDF 加权（否则中文 bigram 全是常见二字组合，会把未收录误判成命中） ⑥新增 `tests/test_search_quality.py`（切词/召回/质量标记）与工具面模式用例，契约用例 38 → 50 项；v0.27.34-open',
    '2026-09-11: 第三批（P1 架构与交付纪律）v0.27.33——①**单一事实来源**：新增 `tools_manifest.json`（工具/平台/知识规模快照）+ `scripts/gen_manifest.py`（op/参数取自 OP_NAMES+签名；风险分级 read/write/device 与分类表是唯一一处人工维护，缺登记直接报错）；`--check` 进闸门防漂移 ②**发布前置闸门 `scripts/check_consistency.py`（首次真正存在——此前 pyproject/requirements.lock/platforms.py 都在引用它但文件缺失）**：版本四方一致（MCP_VERSION / pyproject×2 / README）、工具数六方一致（OP_NAMES / mcp_server / README×3 / 闸门 catalog / manifest）、平台矩阵对着真实模板与 bin_tools 目录、rag_index 覆盖+新鲜度（顺手查出 README 篇数漂移 118 → 实际 128）、委派 smoke/sync_ui_tools/gen_manifest（不重复造检测）；无本地完整 wiki 的机器自动跳过 wiki 相关项，可进 CI ③**tests/ 契约用例 38 项（离线）**：分发器/错误码/每个 op envelope、平台矩阵、布局安全（pack 确定性、**edit_ftu 默认不覆盖**、ui_edit_apply dry_run 不写盘/默认不 pack）、html2json **黄金样例 1:1**（v0.27.30 阴影三连防回归）、verify_assets 真假阳性、fui 能力声明与实际一致 + json↔ftu 往返 ④**CI**：`scripts/ci.sh` / `ci.bat` / `.github/workflows/ci.yml`（compileall + 用例 + 闸门；CI_DEVICE 可选真机抓屏）⑤**修 verify_assets 三个真问题（v0.27.32 加的产物核对器实际不可用）**：a) 只认扁平 `ui/*.json` → 分层 `ui/<分辨率>/*.json` 工程（基准 SampleUI-New 42 页 / ShowcaseAlbum-F133 / WebViewDemo）pages=0 却 ok=true（**静默假阴性**）；b) 把「手绘图尺寸 != 控件盒」当 FAIL → 官方基准工程 149 处误报（引擎本就会拉伸：navi/fh.png 44×26 放 72×40 按钮里），改按铁律 #9 只对 `resources/images/` 自动生成图强校验 1:1，手绘图归 `stretched[]` 仅提示；c) 0 页时补 warnings（不静默）⑥**html2json 误导提示修正**：能自动转图的效果（线性渐变/阴影+圆角/loading 动画）不再喊「无法硬转、请切图」（实测会把 AI 送去白做一轮手工切图），改说「已自动转成图片（尺寸 == 控件盒，json 已引用 images/*.png）」；真转不了的（径向渐变/文字阴影/变换/滤镜/透明度）保留原指引 ⑦**参数写错回 BAD_PARAMS + 正确签名**（原被 _envwrap 归成 TOOL_RAISED，AI 拿不到签名只能猜）；check_all 同样修分层布局扫描（`ui/<分辨率>/` 工程不再以「ui/ 下没有 json 布局」直接退出）⑧工具链名词口径（fun / fui / fyx / fuse）写进 manifest 与 README，写明**当前内置 fui.exe 只支持 pack、unpack 是空壳**；顺手修 project_tools 里 Windows 路径提示文案的非法转义（SyntaxWarning，路径写作正斜杠或双反斜杠）；v0.27.33-open',
    '2026-09-11: 第二批（P0 收尾）v0.27.32——①**新增 op flythings_verify_assets(project_root)**：把「json 声明 vs 磁盘产物」机器化核对（图片引用是否存在 + PNG 尺寸是否 == 控件 position，.9.png 除外），返回 missing/mismatch/unresolved 明细；同一实现接进 check_all 第 17 项（把原先靠人肉跑的 temp/verify_demo_assets.py 固化——v0.27.30 阴影丢图事故就是「产物没人核对」）②**新增 scripts/lint_silent_except.py**：AST 扫描 except...pass 静默吞异常，历史基线 + 白名单（必须写理由）两层，未登记的新站点即 FAIL；smoke 第 9 项改为调用本脚本（单一实现，不再两处各写一套）③**破坏性默认值收口**：flythings_ui_edit_apply 默认 pack=False（要 pack 显式传 true）并新增 dry_run（只回变更预览、不写盘）；flythings_build_ui_flow 默认 with_launch=False（不再默认推真机）；写操作统一回显 affectedFiles 与 .bak 路径 ④隐私脱敏补漏：重建 rag_index.json（旧索引残留真机内网 IP）、CHANGELOG.md 内真机 IP 改 <设备IP> 并重新纳入 smoke 隐私扫描范围；v0.27.32-open',
    '2026-09-11: 第一批设计检讨修复（P0）v0.27.31——①**get_version 瘦身**：原默认返回 MCP_FEATURES 全部 39 条 20,045 字符（约 1.25 万 token，问一句「版本多少」被迫吃掉整部变更史）→ 改为默认 compact=True 只回 mcpName/version/build/toolCount/近期 3 条，全量需显式 compact=False；同时删掉 checkHint 里写死的过期文案「与 0.3.0 比对」②**flythings_search 未命中带检索边界**：原回裸文本 "no results found"（AI 最容易转身去 web 猜、混入其它框架用法）→ 改回 JSON envelope {ok,hits:[],notice,warnings}，notice 明确「知识库未收录该主题，禁止用 Qt/Android/LVGL/emWin/AWTK 等其它 GUI 框架类推，请查官方文档 developer.flythings.cn 或转人工确认」；docstring 去掉写死的「wiki 118 篇」（实际 129 篇，数字不再手写）；向量模型不可用时在 warnings 里显式声明已降级 BM25 ③**统一返回契约 envelope**：35 个工具返回值在注册前统一经 _envwrap 归一化为 {ok, op, warnings[], error{code,msg,hint,retryable}}（保留原键向后兼容；非 JSON 文本收进 data.text），不再「有的回 success 有的回 ok、错误只有一句字符串」④**edit_ftu 默认不覆盖原 ftu**：原默认原地覆盖 → 新参数 overwrite=False 缺省生成 <name>.edited.ftu 并还原原文件，改动的 json 与原 ftu 都留 .bak，返回 overwriteOriginal/backup/affectedFiles/hint，要覆盖必须显式 overwrite=true 或 output_ftu ⑤**写操作回显 affectedFiles**（edit_ftu / ui_edit_apply / fui_pack / i18n_import）⑥**发布前置检查进 smoke.py**：新增双份 ui_tools 哈希一致性、本机路径/内网 IP/真实 accessKey 泄露扫描、静默 except 基线、意图闸门 catalog 参数漂移 4 项检查 ⑦**隐私清理**：撤掉 check_duplicate.py / rebuild_index_local.py / package_tools.py 里写死的本机绝对路径（形如 C:/Users/<用户>/...）与文档中的真机内网 IP 改占位符 ⑧**CHANGELOG.md 自本版起冻结为历史归档**（沛哥 2026-09-11：「changelog 不需要提交」）——不再追加新节、不进提交/发布，版本史唯一来源 = MCP_FEATURES（compact=False 全量）+ README，smoke 也不再校验 CHANGELOG；v0.27.31-open',
    '2026-09-11: html2json 阴影转图三连修（沛哥实测反馈「这是什么错误？」→ 挖出三个叠加真 bug）v0.27.30——①**box-shadow 单位解析**：原 `int(float(parts[1]))` 遇 `4px` 抛 ValueError 且被 `except Exception: pass` 静默吞掉 → 阴影图一张不生成、只甩一句「含 CSS 效果…请切图用 data-pic」（误导提示）；改为 `_px_num/_shadow_spec`（px/em/rem/%/无单位、inset 忽略、4 值 spread、色值任意位置）+ 失败写明确 warning（不再静默）②**图==控件 1:1**：`gen_res.gen_shadow_card` 新增 `crop=False` 保留完整画布（尺寸恒 = 卡体 + 2*pad，pad=max(2,blur+max(|ox|,|oy|))，卡体恒在 (pad,pad)，不再 getbbox 裁到 234×154）；html2json 检测到 pad → 自动 `_grow` 控件盒 + `_pos()` 给子控件补偿 +pad（遇 listview 行内 subItem 停止累加）+ **window 底色改回页面底色**（否则外扩透明阴影区被控件底色填满，阴影渐变与圆角都读不出来）③**阴影 alpha 必须与圆角 mask 相乘**（`ImageChops.multiply`）：原 `putalpha(mask)` 覆盖把 10% 透明黑压成不透明 → 卡片四周一圈硬黑描边（视觉模型判为「粗黑描边」，阴影柔化全丢）。实测：农历 demo 7 图全 OK（png 尺寸 == 控件尺寸，0 mismatch / 0 missing），阴影边缘 alpha 4~6/255 柔和渐变；`HTML_SUBSET.md` 四处同步（单位容错 / 1:1 规则 / mask 相乘 / 文档修正）；v0.27.30-open',
    '2026-09-10: 抓帧读图与像素级坑入库 v0.27.29（沛哥：“必要的做好入库就好了”；来源=外部 skill `flythings-device-screenshot` 与知识库逐条比对 30 条：已覆盖 27 / 真缺 3 / 弱覆盖若干，只补必要的）——①新增 `knowledge/devflow/pixel-analysis-ai.md`：**省 token 四层阶梯**（结构化读数→程序化读图→ui_diff→视觉模型只裁差异区小图）；**方法一 1 字符=1 像素分类图**（8×16 块降采样，背景="." 亮=“#” 高饱=R/G/B/Y/C/M，整片 "."=没内容、意外白块=丢图）；**方法二 文字暗带 bands 检测**（逐行非背景像素计数→band 数=行数，判换行/溢出裁字/空文本，与 check_all `_text_min_size()` 静态校验互补）；**坐标换算缺省不用**（rotate=\'auto\' 输出已是逻辑方向；要换算就用同一个 rotate 函数，不手推矩阵；触摸注入按 `rotateTouch` 换算）；**像素级渲染坑表**（滑块被裁扁=控件高<图高、暗环=图自带描边环、半透明图贴纯色底发脏=烘底或 button+picTab、圆角四角发黑=烘页面底色、listview/item 黑块=删 backgroundColor+bgColorTab）②`busybox-debug-library.md` 新增「设备端没有的常用命令 → busymbox applet」：grep/sed/head/tail/dd/md5sum/df/find/wc/xxd/vi 都不是“设备不支持”而是没装；抓帧三条纪律（df -h /tmp 防静默截断 / md5sum 校验图部署 / fun launch 会清 /tmp）③`touch-inject-autotest.md` 新增「抓帧时机」：注入+抓帧同一次 adb 调用、多档 sleep 差分、hasScrollbar 滚动条~0.6s 淡出且颜色逐帧变、静止单帧不足以判定交互；另 ui-layout-verify.md §2-1-1（上一版）提供方向权威来源；v0.27.29-open',
    '2026-09-10: 抓屏方向按**项目工程**的 rotateScreen 取图，不猜 v0.27.28（沛哥定规：“入库的 B 方案根据实际项目旋转角度取图就可以了。不用猜。”）——flythings_device_screenshot 的 `rotate` 缺省改为 **`auto`**：读项目工程 `<项目>/.fun/<平台>/launch/EasyUI.cfg`（设备上 = `/res/etc/EasyUI.cfg`）的 `rotateScreen`（0/90/180/270）自动转正，拿不到才退化 `fb0/rotate`；返回值新增 `rotateSource` 可自证，screenInfo 带 `rotateScreen`/`rotateTouch`（触摸角度可不同）。新增 `crop=''|auto|x,y,w,h`（auto=按 disp 图层 frame 裁逻辑分辨率）。实测（V85X DVR 板，rotateScreen=270）：rotate=0 → 文字侧躺（错）；rotate=auto → 1600×600 文字正立（✅）。❌反例：不拿 fb0/rotate 当首选（本机它=0 与工程角度不一致）、不硬编某台设备的转置/翻转组合、不从 disp 图层几何反推方向（本机 480×800 层是视频/DVR 层）；knowledge/devflow/ui-layout-verify.md 新增 §2-1-1；v0.27.28-open',
    '2026-09-10: check_all #15 新增「故意遮挡」评估 v0.27.27（沛哥：“方案一也要评估一种可能就是故意遮挡”）——WARN 分两类：**[可能有意遮挡]**（线索任一命中：modal=true / 遮挡件是容器类 window·painter·scrollwindow·pagewindow / 几乎完全覆盖被压控件≥90% / 遮挡件整屏尺寸）与 **[疑似误压]**（以上都不满足，小装饰件压住可触摸控件一角）；可能有意→提示“确认是故意挡（禁用态/蒙层/防盗点）则忽略本条”，不再无差别要求改代码；一律仍只 WARN（不入 failures、不影响 PASS/FAIL 与退出码）。新内部函数 `_deco_hint`。实测 175 个真实 json 17 处命中 → 可能有意 7 / 疑似误压 10；v0.27.27-open',
    '2026-09-10: check_all #15/#16 WARN 升级为“可粘贴修复代码” v0.27.26（沛哥确认扫描命中真实存在、修复方案就是代码补 setTouchPass）——#15 的 WARN 现在给出装饰件 caption 推导出的指针名与完整修复行（`m<Caption>Ptr->setTouchable(false); m<Caption>Ptr->setTouchPass(true);`）并提示写在 onUI_init；#16 直接列出 `m<X>->setTouchPass(true);`；修完再跑即 WARN 消失（已用 fixture 正/负向用例实测）；v0.27.26-open',
    '2026-09-10: 遮挡自动审计入库 v0.27.25（沛哥定规：check_all 自检清单第五条，“报 warning 让用户审批”）——**check_all.py 新增 #15/#16，两顶均只报 WARN**（不计入 failures、不影响 PASS/FAIL 与退出码，交用户逐条审批）：①**#15 json 静态**：同层中后定义（z 更高）且 touchable=false 的控件压在 touchable=true 控件之上 → WARN（提示装饰件需运行期 setTouchable(false)+setTouchPass(true)，见 touch-events.md §1；重叠<4px 的微小交叠不计以障噪；上层为 modal 容器时提示“拦截可能是有意的”）②**#16 代码静态**：logic.cc 里 X->setTouchable(false) 但同对象无 setTouchPass(true) → WARN；局限：#15 查不到运行期才设的 setTouchPass，最终仍需实机验证；实测噪声（175 真实 json）=14 文件/17 处命中，负向用例（装饰件移开+补穿透）0 命中；双份同步（MCP 内 + tools/ui_tools/）；v0.27.25-open',
    '2026-09-10: 触摸/遮挡知识定稿 v0.27.24（沛哥提供实机验证全文，替换墨羽草稿）——knowledge/uicontrols/touch-events.md（V85X + EasyUI 2.9.0 实机逐条验证）：①**touchable=false ≠ 触摸穿透**（只表示自己**不响应点击**，照样挡住矩形范围内的下层控件：下层收不到 DOWN → 既不能拖也不触发点击；症状=列表能看但拖不动/点行没反应；最容易犯=压住可触摸控件上的**装饰件**：渐隐/渐变遮罩、选中高亮色带、徽标红点、纯图标层、半透明蒙层）②正解=运行期 `pCtrl->setTouchable(false); pCtrl->setTouchPass(true);`（ZKBase 触摸穿透，事件落到下层），onUI_init 里统一设置最省事；⚠**touchPass 不是 json 键、没有 json 字段，必须写代码**③radiogroup 等**交互容器** touchable 必须 true——非触摸容器会把**整棵子树**从触摸分发里剪掉（子项写 true 也没用；实测 radiogroup=false → radiobuttons 全部点不动）④`ZKListView::setSelection()` 只改**滚动位置**、不触发重排+重绘 → 必须跟 `refreshListView()`，否则“行位置与选中样式错位”（高亮画到相邻行=像没选中；定位线索=进页面对/交互后错→比对两条路径哪条漏了 refresh）⑤排查顺序：**先日志**（事件到没到控件/回调进没进，只到页面级全局监听不算）**再像素**（抓屏要按 pan 取当前显示页缓冲，读错帧会得出相反结论），两者都可能骗人⑥实测对照表（渐隐层拖动：穿透关=0% 像素变化/穿透开=正常滚动）；另 widget-code-api.md 新增 ZKBase 通用段（setTouchable/setTouchPass/监听器注册）；v0.27.24-open',
    '2026-09-10: 触摸语义修正 v0.27.23（沛哥：项目 UI 实现发现的问题，前两项会产生错误代码优先改）——①**radiogroup touchable 必须 true**（`json-field-mandatory.md` 第 12 行口径补例外 + radiogroup 行改 true；`html2json.py` `_open_radiogroup` 模板 False→True；**它是「容器显式 false」通用口径的例外**（radiogroup 是交互集合不是背景容器），写 false 会让整组收不到触摸=单选按钮点了没反应）②新增 `knowledge/uicontrols/touch-events.md`（触摸事件与 touchable 语义 /「点了没反应」排查手册）：**touchable≠穿透开关**（只管收不收触摸，不靠它实现穿透）、交互控件必 true、容器/纯显示 false、层叠顺序决定谁收到触摸、「点了没反应」六步排查顺序（touchable→上层遮挡→是否在当前 window→回调名是否匹配 caption→状态类是否漏 refresh→真机截图+logcat）③`listview-fields.md` 铁律 7：`setSelection(idx)` 后**必须** `refreshListView()`（只改选中态不重绘，漏刷新界面不更新）④`json-layer-rules.md` 第 7 条：层叠顺序决定谁收到触摸（上层 touchable:true 先截走）⑤`radiogroup-checkbox-fields.md` touchable 单独拎出说明；v0.27.23-open',
    '2026-09-10: 真机抓屏工具入库 v0.27.22（沛哥：从设备取图的能力 AI 不知道，直接给明确指令）——新增 flythings_device_screenshot：把设备当前显示的画面抓成 png/jpg/bmp 给 AI 看（视觉分析）或给 ui_diff 做像素验收。要点：①设备 rootfs 裁剪版**没有 screencap/dd/head**，`adb exec-out` 也不可用（patched adbd 无 shell v2 → error: closed），唯一链路=设备侧 `busybox dd ... | busybox gzip -1 > /tmp/x` + `adb pull`（实测 600x1600 裸 raw 7.68MB 经 WiFi pull 要 4 分钟+，gzip 后只有 37KB、0.3 秒）（无 busybox 时退化 cat + pull 并提示）②fb 参数必须问 sysfs（modes=可见分辨率 / virtual_size 可能是 2 倍 OVERALLOC / stride / bits_per_pixel），可见高≠文件行数，必须按 stride 逐行取 ③**双缓冲页翻转坑**：palette 必须读 `/sys/class/graphics/fb0/pan` 的 yoffset 并 `dd skip=<yoffset>`，否则抓到的是上一帧旧画面（本机实测 pan=0,1600，pan 取值靠前一半就是旧屏）④32bpp 内存序 BGRA（小端 ARGB8888），按 alpha 字节位置自动判通道序，红蓝互换可传 pixel=rgba ⑤输出支持 fmt=png/jpg/bmp + scale 缩放 + quality；v0.27.22-open',
    '2026-09-10: UI 布局可视化编辑 + 像素验收工作流入库 v0.27.21（knowledge/devflow/ui-layout-verify.md；配套 v0.27.20 的 flythings_ui_editor / ui_edit_apply / ui_diff）——要点：json 是唯一真相（设备加载 ftu，ftu 由 json pack，手写 HTML 预览=第二份真相必然漂移；json2html 也只是近似，像素真相只有真机截图）；三段式验收（预览→真机截图→像素 diff）；编辑器指哪打哪（Alt+点穿透下层、✥绿块拖遮罩下控件、属性栏按原 json 动态出字段、id 只读、visible:false 幽灵框）；变更写回三条安全（.bak / 格式自检 / 边界钳制）；像素 diff 默认容差±2+抖动补偿+模糊+噪声块过滤，主力是回归对比（改前截图 vs 改后截图），分层省钱 L1 像素(0 token)→L2 只裁差异区小图给模型→L3 人工看标注图；图片引用是相对 resources 可带子目录的路径（audio/horn.png），只按 basename 找 resources/images 会大面积丢图；现象→根因排查表（锯齿/位置/切图/丢图/裁字）；v0.27.21-open',
    '2026-09-10: UI 可视化编辑 + 像素验收入 open 版 v0.27.20（沛哥：布局调整要「指哪打哪」，预览里的文字/属性都要能改，图片资源要能加载）——新增 3 个工具：① flythings_ui_editor：ui/*.json → 单文件可拖拽编辑器（拖/缩放/Alt+点穿透选中下层/属性栏列出全部字段含 text·fontSize·colorTab·picTab 四状态图，改完画布即时生效，id 只读；内置图片尺寸≠控件尺寸红黄标）② flythings_ui_edit_apply：变更 JSON（changes 几何 + props 属性）写回 ui/*.json（自动 .bak + 格式自检）并 pack ftu ③ flythings_ui_diff：像素 diff 0 token，容差±2 + ±1px 抖动补偿 + 高斯模糊 + 噪声块过滤，输出差异清单/标注图（回归对比专治改 A 碰坏 B）；顺带修 json2html 图片路径解析（支持 audio/xxx.png 这类带子目录的相对 resources 引用，之前只按 basename 找 resources/images/ 导致预览丢图、尺寸预检形同虚设）；v0.27.20-open',
    '2026-09-09: package API 识别规则定规 v0.27.19（沛哥 21:42：AI 对 FlyThings package 只允许通过头文件识别 API，不要猜也不要反编译二进制浪费时间，不会就是不会；标准 C/C++/Linux 开发按标准+开源社区参考）——retrieval-boundary.md 新增「Package API 识别规则」：package C++ API（类/方法/枚举/注释）只读包内头文件（aw-dvr mpi/*.h、easyui control/*.h）；禁猜（读不出标未收录问官方）/禁反编译（objdump 禁止，readelf 仅排障用）；两层区分：头文件能确认的（签名/枚举/注释）读头文件、表达不了的（控件 json 字段/回调语义）走 wiki/knowledge（与 09-01 easyui 条款不冲突）；标准 C/C++/Linux（socket/pthread/v4l2/std 等非 FlyThings 私有 API）按标准+开源社区参考不受限；v0.27.19-open',
    '2026-09-09: MCP 知识库结构化整理 v0.27.18（沛哥确认：平台化/结构化治理，消重复啰嗦）——①content 唯一化：删除 wiki/flythings 下 44 篇 knowledge 实践文档副本（28 字节相同双命中 + 16 漂移），实践知识唯一放 knowledge/（随 Gitee+检索主源），wiki 只留官方镜像 129 篇；rag 去重重建 ②MCP_FEATURES 精简 70 条 25.8KB → 近期精华+能力概括（完整史在 CHANGELOG）③治理机制固化：knowledge/README.md 治理规范（新增文档只改 knowledge 禁复制 wiki/命名/流程红线）+ scripts/check_duplicate.py 双份检测工具',
    '2026-09-09: 异步资源释放反模式入库 v0.27.17（⑥ V553 实证：UI 回调固定 sleep 等媒体资源释放=空等永不释放资源，浪费 4 小时）——cross-thread-ui-rule.md 新增「异步资源释放反模式」：UI 回调（onUI_quit/hide/Timer）禁止固定 sleep 等资源释放（卡 UI 线程+时序脆弱）；先确认资源会不会释放/由谁释放，再选三选一：①官方回调/轮询确认（stop 完成回调/线程退出标志/资源可用轮询）②raw 层强制回收（AW_MPI_VO_Disable 拿返回码，见 v85x/display-layer-debug.md §4）③接受重建（确认不需要就重建通路不空等）；实例=播放页退出→预览 VO 冲突 0xa00f8042（错误 sleep 等让位，正确 raw VO_Disable 或 enable 轮询重试）；固定 sleep 仅已知释放时长上限+无回调可用时兜底且注释；v0.27.17-open',
    '2026-09-09: 部署可靠性 v0.27.16（④ V553 踩坑：fun launch 网络超时静默/推送中断误推旧固件；沛哥指示 timeout 就 retry 5 次、不自写 push 脚本校验、信任 fun 差分）——_run_fun 加 retries 参数（失败/超时自动重试间隔 2s，返回含 retried）；flythings_build_ui_flow 的 fun launch 传 retries=5（网络抖动自愈），5 次仍失败才 needDeviceInput 询问设备接入；未自写任何 push/校验脚本；kb_tools 工具描述同步；v0.27.16-open',
    '2026-09-09: V553 踩坑 ②③ 入库 v0.27.15（沛哥要求先检讨正确性：②缺口属实 ③主体属实且揪出旧策略误导——"直接用最新版 aw-dvr"致 V553 选 4.0.1 踩 dlopen 坑，已修正）——②activity-code-skeleton.md 新增 §3-1 导航×回调触发矩阵：**goBack/返回销毁只走 onUI_quit、不经 onUI_hide**（日志实证；释放放 onUI_hide=永不执行=VO 残留事故代码根因）；openActivity 覆盖→onUI_hide；铁律=媒体/硬件资源释放放 onUI_quit、hide 只做被覆盖暂停 ③新增 v85x/aw-dvr-runtime-compat.md：版本×runtime 矩阵（3.13.12↔aw-mpp 2.0.2 ✅ 全适配当前实测组合 / 4.0.1 需 aw-mpp 3.0.0-pre2 ❌ runtime 2.0.2 装不上 / 3.9.12 ⚠️能跑不能录 UVC 待复核）；勿加 aw-middleware（旧包头冲突+无 UVC backend）；libmpp_uvc.so 由 aw-mpp-uvc 提供；dlopen 失败 SOP=readelf -d NEEDED→比对设备库→readelf -Ws UND 找版本专属符号→换 SDK 或升 runtime；dvr-recorder-guide Manifest 示例/版本策略/自检清单同步修正；v0.27.15-open',
    '2026-09-09: VO dev0 抢占冲突排障知识入库 v0.27.14（V553 UVC 相机项目实证：从独立播放页返回预览页图像出不来，logcat 反复 0xa00f8042 AW_MPI_VO_Enable error；此坑全库 0 命中——disp 层知识只到 layer 级没到 VO dev 级）——①错误码实锤 0xa00f8042=EN_ERR_VO_DEV_HAS_ENABLED（aw-mpp mm_comm_vo.h，VO 设备已被 enable；0x41=DEV_NOT_ENABLE 常态忽略）②架构事实：easyui ZKVideoView(zkmedia/CedarX) 与 mpi 预览(aw-dvr RearCamera) **共用 VO dev0**，播放器退出/播放页销毁后 VO dev0 不自动释放 → mpi enable 报 HAS_ENABLED；触发条件=播放页独立 Activity 走销毁路径，videoview 常驻同页无此问题 ③解法：mpi 预览启动前 **raw AW_MPI_VO_Disable(0)** 强制让位拿返回码（⚠️ mpi::VO 包装类 disable 吞异常/不返回真实码，必须 raw API）；Disable 失败 sleep 300-500ms 重试 2-3 次（播放器异步释放~400ms）；兜底 enable 失败 Disable+延时重试循环 ④排查顺序 disp 层(releaseLayer)→VO dev(0xa00f8042→raw Disable)→UI 透出(videoView visible)；display-layer-debug.md 新增 §4 VO dev0 抢占冲突（§4-7 顺延 §5-8）；v0.27.14-open',
    '2026-09-09: demos 案例库上线 v0.27.13（沛哥拍板方案 B：验证全功能 demo 带着走，AI 照抄避免反复 try 浪费 token；后续可批量做）——①新增 demos/README.md 案例库规范：demo=已真机验证可编译可运行的功能闭环（源码级 <100KB）；命名 <功能>-<形态>-<平台>；必备 Manifest/ui json+ftu/src 只写 logic/package.properties/README 三件套；红线：accessKey 占位 REPLACE_WITH_ACCESS_KEY_FROM_ZKSWE 禁止真实 key 进公开仓库、不提交 .fun/exe/.vscode、去工程化、闭环宁缺毋滥；knowledge 头部加 demo 指引 ②首个案例 demos/dvr-uvc-recorder-v85x/：V85X+1600x600 竖装屏(rotateScreen270)+USB UVC(JPEG/MJPEG) DVR 全链路参考工程（探测协商/预览/拍照/录像/停止/回放 + releaseLayer + 保活 + videoView 透明窗 rotation:3），真机全链路验证过，内置 AHD/TVI 双路改法见 README ③dvr-recorder-guide.md 头部加 demo 指引；v0.27.13-open',
    '2026-09-09: DVR 录制功能端到端 Playbook v0.27.12（沛哥：外部开发者同步 MCP 要能准确无误开发 DVR 类录制功能、AI 不走弯路）——盘点确认知识碎片化缺功能链串联 + TF 卡格式化要求未入库；新增 ①knowledge/v85x/dvr-recorder-guide.md（12 节端到端：文档地图防漏环节/前置 4 问/Manifest aw-dvr accessKey 最新版策略/屏幕方向 rotateScreen 硬件适配/UI videoView 可见透明窗+rotation 枚举 3=270°/摄像头内置 mpi+UVC JPEG 双形态/录像产品级+UVC 简化两套参数（frame_rate 15~60、size=实际分辨率）/拍照回放 VO 延迟初始化/存储/排障日志判据表（黑屏 fps、绿屏=0字节文件、一直提示格式化=卡被电脑格过）/8 项自检清单）②knowledge/v85x/tfcard-format-requirement.md（V85X TF 录制卡专属格式 FAT32+64KB 簇 65536+OEM=zkswe；statfs f_bsize==65536 校验，不符弹「文件系统不符合要求」；挂载失败 5 次自动强制重格；电脑 FAT32≤32KB/exFAT/NTFS 判不符=录不了像头号原因；formatTfcardProcess 统一流程；双介质探针）；v0.27.12-open',
    '2026-09-09: V85X 显示分层调试入库 v0.27.11（竖屏 600x1600 + 横 UI + UVC 摄像头实测：错屏/无图像/回放方向三连坑闭环）——①**错屏=UI 布局超出屏幕**（横 UI 1600×600 在竖装屏 600×1600，不旋转时 1600 宽 > 600 物理宽，内容溢出屏外）；rotateScreen 是**硬件物理方向适配**（值由屏幕安装方向决定，非 UI 分辨率/代码决定）→ package.properties 写 EasyUI.cfg={"rotateScreen":270}（触摸不转=不写 rotateTouch），改后必 fun clean 全量重编（ninja 不感知 package.properties），EasyUI.cfg 由 fun launch 合并生成 ②**无图像根因=UI 层(z=16 最顶)不透明盖住 disp 视频层(z=1)**：摄像头 fps 30 正常+视频层 enable 也没画面，UI 必须有 **visible:true 的 videoView 透明窗口**（visible:false 是最常见坑，不透出=视频层白跑；position=画面区域，自维护出图零关联代码）③**ZKVideoView rotation 是枚举 0/1/2/3=0°/90°/180°/270° 顺时针，写 270 无效被忽略**，竖屏回放写 rotation:3（同平台产品 DvrPlay 同款）④releaseLayer 释放残留 disp 层工具代码（保留 UI 层 ch2/layer0；include 坑：直接 <video/sunxi_display2.h> 缺 s32/u32 编译错，用 aw-mpp <vo/hwdisplay.h>）；新增 knowledge/v85x/display-layer-debug.md + 无 screencap/input 设备调试技巧（fb0 alpha 分析/静态 tap 工具/触摸节点 gt9xx 可能 event0）；v0.27.11-open',
    '2026-09-08: JPEG UVC 实测证据入库 v0.27.10（CV201PND 板 1280x720 JPEG UVC 六步验证全通：探测/预览/拍照/录像/停止/回放；对比旧 AI 工具失败现场，绿屏/黑屏根因实锤）——①**绿屏直接原因=录像文件 0 字节**（取流断：get video frame timeout / rear camera fps 0.2 → VENC no stream → 0 字节 mp4 → 播放器解不出=绿屏），排查先 ls -la 看文件大小 ②**黑屏=取流/保活断**（REAR FPS≈0）；边录边看正常时 rear camera fps≈29 + venc fps≈25 ③**RecordingSettings.frame_rate 必须 15~60**（设 0 抛 frame rate must be betwen 15~60）④录像成功日志判据：MPP_EVENT_RECORD_DONE+done 路径/文件 12s 720p≈29MB/回放 media play ok（demux/vdec/vo/clock 全 success）；uvc-usb-camera.md 新增 §8 六步验证法表（每步成功日志判据），jpeg-decode-record.md 坑 7~10；v0.27.10-open',
    '2026-09-08: UVC 知识分层 v0.27.9（沛哥定规：V85X 平台 UVC/USB 摄像头统一按通用形态；通用 UVC 层沉淀为跨平台知识，可适配 T113/F133/Z20/Z21）——新增 knowledge/hardware/uvc-camera-generic.md（平台无关通用 UVC 层：前置条件 USB Host+uvcvideo / inotify 发现 / V4L2 格式协商 ENUM_FMT+S_FMT / 取流保活 / 状态机 / JPEG(MJPEG) 落地必查清单 / 平台绑定对照表 V85X 已收录、T113/F133/Z20/Z21 绑定层未实测不编造）；v85x/uvc-usb-camera.md 改「V85X 平台绑定实现」+ 检索导引分流（未指定平台→通用篇）；v85x/jpeg-decode-record.md 头部补通用篇引用；v0.27.9-open',
    '2026-09-08: UVC 摄像头知识去工程化 v0.27.8（沛哥定规：更新后不体现内部工程名，只保留通用 UVC 摄像头知识；外部 AI 落地 JPEG UVC 时出现录制绿屏/录制中黑屏，根因=格式协商缺失/录像尺寸错配/录像预览互斥顺序/保活缺失）——uvc-usb-camera.md 新增 §7 通用 JPEG(MJPEG) UVC 落地必查清单（①ENUM_FMT+S_FMT 锁 MJPEG，摄像头默认可能 YUYV，不协商=绿屏 ②RecordingSettings.size(REAR)=UVC 实际分辨率，不照抄 1080P/720P 档 ③开始录像不停预览/保活，切流/拔插/进回放前才 Recorder::stop+RearCamera::stop ④SharedVideoDevice(REAR) 保活录像期间不停 ⑤录像仅 mp4/ts，JPEG 仅照片场景 Snapshot→JpegViewer）；jpeg-decode-record.md 去除全部工程路径引用改职责描述；v0.27.8-open',
    '2026-09-08: PNG 生成管线规范显式化 v0.27.7（方案 A，沛哥定规：新 AI 客户端按规范转 png 仍默认锯齿，根因=抗锯齿只做在 gen_res 内部，规范没显式约束 AI 生成方式）——HTML_SUBSET 切图铁律新增 #8（PNG 生成只走三条路：html2json 自动转图 / generate_ui_assets / gen_res 公开函数，禁止 AI 自绘 1x 直画/外部生图直出小图交付）+ #9（防锯齿五要素：尺寸==position、≥4x 超采样 LANCZOS 或 α 羽化 sigma≈0.5、端点 round cap、圆角四角 alpha=0、check_all 校验）；generate_ui_assets 描述同步加 ⑦；v0.27.7-open',
    '2026-09-08: 全控件深度阅读 v0.27.6（沛哥要求：深度读基础 Demo 形成对 FlyThings 所有控件的深度理解）——basedemo-new_z20_1024_600 35 工程源码逐行精读（5 子代理并行，产出 130KB 原始笔记归档 workspace/references/demo-read-2026-09-08/）→ 新增 2 篇知识：①devflow/activity-code-skeleton.md（生成器骨架：activity 壳+#include logic/回调分发表语义 true=吞 false=默认（模板注释写反）/生命周期/定时器静态表+动态 register-unregister-reset/串口协议模板（UartContext 读线程 16KB 拼接+帧头对齐粘包处理+listener 订阅）/SysApp 三槽位（STATUSBAR/SCREENSAVER/IME）/多语言/平台编译宏）②uicontrols/widget-code-api.md（21 控件代码 API 速查：回调签名/触发时机/坑——自定义 ISeekBarChangeListener 三回调拿拖拽起止、ZKVideoView vs ZKMediaPlayer 两套消息枚举、camera 拍照四回调+jpg、pointer/clock 角度坐标系+浮点回绕坑、diagram setData/addData 双刷新、painter 绘图 API 全集、IME 集成范本、wifi/lte/softap/ethernet Manager+Listener、listview 删除漏 refresh 官方坑）；v0.27.6-open',
    '2026-09-08: Button 长按/循环重复机制收录 v0.27.5（沛哥确认学习：长按触发时间/循环重复时间通过 UI 属性表可配）——json 字段 longClickTimeOut（长按事件触发时间 ms，>0 启用，默认 -1 不启用）+ longClickIntervalTime（长按循环触发间隔 ms，>0 长按期间反复触发，-1 单次）；实测：ButtonDemo LongButton 1000/1000（1s 触发+1s 循环连发）、ImeDemo 删除键 600/-1（快启单次）；代码 ZKBase::ILongClickListener::onLongClick + setLongClickListener（onUI_init 注册/onUI_quit 注销，匿名 namespace）；新增 knowledge/uicontrols/button-fields.md（button 全字段频率表 + 长按三件套 + 图片按钮铁律）；v0.27.5-open',
    '2026-09-08: 控件层级检讨 v0.27.4（沛哥问“控件层级有检讨吗”——此前只有零散结论（Z序/window嵌套/pagewindow叠放/listview结构），缺系统矩阵）——扫描 86 json（SampleUI 1024x600 + basedemo-new_z20_1024_600）容器→子内容矩阵实证零越界：window 万能容器（可深嵌 window）；pagewindow/scrollwindow 只装 window；listview/radiogroup/slidewindow/diagram 只走结构键（item/radiobuttons/items/infos）禁止平铺控件键；叶子 14 类不得生子；数组子结构归属固定；新增 knowledge/uicontrols/json-layer-rules.md；check_all #2 升级层级合法性检查（_layer_problems：缺 window 子页/平铺/叶子生子/数组错位 4 类非法全拦截，86 真实 json 0 误报）；v0.27.4-open',
    '2026-09-08: json 字段全集显式化 v2.1（沛哥定规：字段缺省省略→引擎版本默认漂移→版本不匹配异常；以 SampleUI-New/ui/1024x600 每类型 100% 交集=必选，basedemo-new_z20_1024_600 交叉复验+补缺）——口径：beepEnable 不强制（废除恒带 true）/交互控件 touchable 显式 true（容器纯显示 false）/qrcode 恒写 padding 10/videoview 按 SampleUI/-1=0xFFFFFFFF 有意义非噪音；新增 knowledge/uicontrols/json-field-mandatory.md（21 类必写键全集表 + 子结构模板：listview.item 17 键含 position/subItem/diagram.infos 含 visible/slidewindow.items/radiobuttons）；⚠️ item.position 必写，行高公式 itemH=int(lv高/rows)-rowSpacing（basedemo 验证 164/4-5=36 等）；html2json 全部控件按全集输出+item 行高自动算；check_all #14 模板 v2.1（listitem 含 position + checkbox/radiogroup/radiobutton/imageanim 升级 + item/subItem/infos[]/items[]/radiobuttons[] 子结构检查）；v0.27.3-open',
    '2026-09-08: 补 MT Type-A 触摸注入工具 mt_test + 协议速判坑位（沛哥 V85X 实测 ui_test 单点协议在 gt9xx 注入坐标恒 0）——根因：设备 MODALIAS ra30,32,35,36,39=ABS_MT_*，不订阅单点 ABS_X/Y → 新增 bin_tools/{v85x,t113,z20,z21}/mt_test（ARMv7 musl 72KB + ARMv7 glibc 4.5MB，接口对齐 ui_test：tap/swipe/long/monkey/run；RISC-V 暂缓待 WSL）；bin_tools/README 加 mt_test 工具表行+「触摸协议速判」节（EVIOCGABS 能力位/getevent -p/试注入判据+协议用错→坐标恒0）；touch-inject-autotest.md 分列 ui_test(单点) vs mt_test(MT) 工具表+关键坑点破+协议铁律加 MT 序列+坐标恒0判据；v0.27.2-open',
    '2026-09-08: 补触摸注入/UI 自动化测试检索缺口（沛哥反馈：AI 调试没调用现成 input/ui_test 工具干活）——根因：references/kb/adb-input-autotest.md 最新版（含现成 input 工具说明）不在 MCP 索引范围，MCP 检索命中的 wiki 版是 8-31 老原理 → 新增 knowledge/devflow/touch-inject-autotest.md（首选 flythings_gen_ui_test + bin_tools/{平台}/ui_test 现成 ELF：tap/swipe/long/monkey/run + 部署命令；event.c 原理降为定制/移植参考；协议铁律 EV_SYN/逐像素/时间戳；判定闭环 logd>raw fb）；wiki/test/adb-input-autotest.md 同步 9-08 最新版消旧误导；v0.27.1-open',
    '2026-09-08: i18n 翻译推送工具入库（沛哥：V553 实测 fun launch 不推 i18n 盲点）——新增 flythings_i18n_to_json（.tr→.json 序列化与设备逐字节一致 + adb push /tmp/tr/；设备 DEBUG 实际加载 /tmp/tr/<lang>.json，生产固件 /res/ 用 push=False）；flythings_build_ui_flow 描述顶部加「fun launch 不推 i18n」警告；AI 改完翻译必须调本工具否则设备跑旧翻译；v0.27.0-open',
    '2026-09-08: BusyBox 调试工具库入库（沛哥：设备系统没 busybox/ifconfig 等工具，要预编译分发）——新增 bin_tools/{f133,f135,z20,z21,t113,v85x}/busybox（v1.36.1 全静态 ELF，网络工具 ifconfig/ip/ping/netstat/route/telnet/nc/wget 全开，adb push 即用，与 ui_test 同架构）；bin_tools/README 工具表+调用方法；新增 knowledge/devflow/busybox-debug-library.md 检索导引；v0.26.0-open',
    '2026-09-08: 部署/调试场景别名映射（沛哥反馈：客户端 AI 收「AI 应用调试全量推送」时检索不到 build_ui_flow 描述而自造 deploy_debug.sh）——flythings_build_ui_flow docstring 头部加「场景别名」段（编译/构建/调试/全量推送/部署/部署到设备/跑一下/AI 自定义编译/自主编译验证 一律本工具，禁止自创脚本路径）；新增 knowledge/devflow/deploy-scene-map.md（用户话语→唯一动作表 + 坑源说明）；v0.26.0-open',
    '2026-09-07: 自研帧动画知识移出 open 版（沛哥指示：ImageAnimView/FrameImageView ZKBIN+QOI+region 机制依赖自研 ZKBIN 工具链，open 用户缺工具无法使用）——删除 knowledge/devflow/frame-image-anim-bin.md，知识保留本地 references/kb/frame-image-anim-bin.md（125 行完整原版）；dashboard-can-arch.md 还原 v0.22.1 无 ImageAnimView 版（6 处引用全清，CAN 架构保留）；v0.25.2-open',
    '2026-09-07: 清理冗余（沛哥要求整理 open 版多余反复内容）——删除 knowledge/ 与 wiki 字节完全相同的 3 个重复副本（esl/tag-esl.md、uicontrols/image-path-rule.md、uicontrols/scrollwindow-layout.md），wiki 保留唯一一份，检索不再双份命中；layout-audit.md 两版非字节相同（knowledge 含实测校准 edittext id 51000/imageanim 无 frameInterval）保留 knowledge 版；wiki 官方源自身重复不动；v0.25.1-open',
    '2026-09-07: 冷门控件字段文档批量入库（git.com 全库学习产出，沛哥确认 3 点：listview 点击 id=被点 subitem 的 ID / slidewindow cols×rows=每页格数 11 项=1页8+3 翻页 / 所有控件支持跨线程操作）——新增 uicontrols 文档 11 篇：pointer（双坐标定圆心+animatable 自动动画）、circlebar（有效图扇形裁剪+触摸监听）、digitalclock（纯属性+TimeHelper 改系统时间）、slidetext（输入法候选词条）、qrcode（loadQRCode 传 JSON）、radiogroup-checkbox（pic2 选中图+子项 ID 宏）、diagram（统一 SZKPoint+setData/addData 双模式）、videoview（轮播 loopPlayback 读 UI名_video_list.txt / API 双模式）、pagewindow（多页容器）、listview（三回调+无 subitem 数量限制）、cross-thread-ui-rule；全部 fui unpack 实测 + f133 easyui 2.9.0 SDK 头文件校准，非猜测；v0.25.0-open',
    '2026-09-01: SlideWindow 布局定规修正（沛哥 21:59 纠正）——json 坐标来自 HTML 原型绝对定位，确认好即无需微调；若交付后还要调位置 = 前期 HTML 效果没确认好（正确流程：HTML → 预览确认 → 才 pack/交付）；删掉 v0.7.8 错误的「绝对布局需微调」表述',
    '早期迭代（0.27.10 之前，完整史传 compact=False 取全量）：基础控件字段/代码 API 全覆盖（uicontrols 22 篇：button/listview/window/slidewindow/pagewindow/cameraview/videoview/circlebar/diagram/edittext 等，字段全集显式化+层级规则）；devflow 工程机制（package.properties/EasyUI.cfg rotateScreen、自定义字库/控件、i18n 多语言工具链、原型流程、自动化测试 touch-inject/ui_test）；RAG 检索基建（bge-small-zh 本地向量+BM25 混合、检索边界定规、去工程化）',
    '平台知识分层：通用层（hardware/uvc-camera-generic 跨平台 UVC、usb-otg-switch 跨平台 OTG）与平台绑定层分离；V85X 深度知识（aw-dvr 版本兼容、VO/disp 层调试、UVC JPEG 链路）仅内部版；方案类（车载/涂鸦/SIP/ESL）仅内部版',

]


def _tool_names() -> list:
    """本模块内已注册的工具函数名（单一来源，禁止手写数量）。"""
    import inspect as _i
    return sorted(n for n, _ in _i.getmembers(sys.modules[__name__], _i.isfunction)
                  if n.startswith('flythings_') and n != 'flythings_kb')


def flythings_get_version(compact: bool = True) -> str:
    """返回 MCP 版本号、工具数量与近期关键特性。用户问「MCP 版本是多少 / 是不是最新的」时调用。
    compact=True（默认）只回版本摘要 + 近期 3 条；要看完整能力史才传 compact=False（较长，勿默认拉取）。
    """
    tools = _tool_names()
    out = {
        'mcpName': 'flythings-kb-open',
        'version': MCP_VERSION,
        'build': MCP_BUILD,
        'toolCount': len(tools),
        'tools': tools,
        'checkHint': 'version 即当前安装版本；与官方最新发布号 vX.Y.Z-open 比对即可确认是否最新',
    }
    if compact:
        out['recent'] = MCP_FEATURES[:3]
        out['note'] = '完整能力史传 compact=False（默认只回近期 3 条以省 token）'
    else:
        out['features'] = MCP_FEATURES
    return json.dumps(out, ensure_ascii=False)


# 检索边界（对应 knowledge/uicontrols/retrieval-boundary.md）：未命中时必须明确告知，
# 否则 AI 会转身用通用 web 搜索 / 其它 GUI 框架类推，导致 FlyThings 知识错乱。
NO_HIT_NOTICE = (
    '知识库未收录该主题。禁止用其它 GUI 框架（Qt/Android/Flutter/emWin/AWTK/LVGL 等）'
    '的控件用法类推 FlyThings；请查官方文档 developer.flythings.cn，或转人工/沛哥确认后入库。'
)


def _query_tokens(q):
    """查询词元：英文/数字词（≥2）+ 中文二元组（BM25 的整串切词对中文几乎不命中）。"""
    q = (q or '').lower()
    return rs.query_tokens(q)      # 单一实现：切词口径与 BM25 完全一致（v0.27.34）


def _best_coverage(q, texts):
    """命中片段对查询词元的最大覆盖率（**IDF 加权**，0 = 完全没沾边）。

    为什么要它：rag_search 的向量路总是返回 top-40 再融合，任何 query（包括
    完全不相关）都会有“命中”——仅靠空列表判不出未命中，必须看词覆盖度。

    为什么 IDF 加权（v0.27.34）：中文改用字级 bigram 后，「不存在」「主题」这类常见
    二字组合在语料里到处都是，不加权会让任何 query 都显得“高覆盖”，把「知识库未收录」
    误判成命中（→ AI 转身去 web 猜，正是检索边界规则要防的）。
    口径：df ≥ 30% 语料的过泛词元权重记 0；分母 = 词元 IDF 和，分子 = 命中词元 IDF 和。
    """
    toks = _query_tokens(q)
    if not toks:
        return 1.0
    n = len(rs.CHUNKS) or 1
    weights = {}
    total = 0.0
    for t in toks:
        df = rs._df_of(t)
        w = 0.0 if df >= 0.3 * n else math.log(1.0 + (n - df + 0.5) / (df + 0.5))
        weights[t] = w
        total += w
    if total <= 0:
        return 1.0        # query 全是过泛词元（无判别力）→ 无从判定，不误报「未收录」
    best = 0.0
    for t2 in texts:
        tl = (t2 or '').lower()
        best = max(best, sum(w for t, w in weights.items() if w > 0 and t in tl))
    return best / total


def flythings_knowledge_search(query: str, k: int = 3) -> str:
    """在 FlyThings 知识库（wiki 官方镜像 + knowledge 实践文档）中检索相关文档片段（完全本地，零 Key）。
    遇到 FlyThings 开发问题（控件/API/布局/FTU/回调/编译/平台差异等）时调用。query 用中文描述。
    内置 bge-small-zh 本地模型做向量检索，模型不可用时自动降级 BM25（返回里会显式提示）。
    （v0.27.36 由 flythings_search 改名：与 flythings_package_search 区分语料）
    """
    kk = max(1, min(int(k), 8))
    warnings = []
    try:
        degraded = rs._get_embedder() is None
    except Exception:
        degraded = True
    if degraded:
        warnings.append('本地向量模型不可用，已降级 BM25 关键词检索（召回可能变差）')
    try:
        top = rs.search(query, kk)
    except Exception as e:
        return json.dumps({'ok': False, 'op': 'flythings_knowledge_search', 'query': query,
                           'error': {'code': 'SEARCH_FAILED', 'msg': str(e),
                                     'hint': '重试一次；仍失败检查 rag_index.json 与模型文件是否完整',
                                     'retryable': True},
                           'warnings': warnings}, ensure_ascii=False)
    hits = [{'path': c['path'], 'score': round(float(s), 4), 'text': c['text'],
             'source': 'knowledge（实践）' if (c.get('path') or '').startswith('knowledge/')
                       else 'wiki（官方镜像）'}
            for s, c in top]
    cover = _best_coverage(query, [c['text'] for _, c in top])
    out = {'ok': True, 'op': 'flythings_knowledge_search', 'query': query, 'count': len(hits),
           'hits': hits, 'coverage': round(cover, 3), 'warnings': warnings,
           'retrieval': 'bm25' if degraded else 'vector+bm25(RRF)',
           'degraded': bool(degraded)}
    if not hits or cover < 0.1:
        # 空命中，或查询词元（IDF 加权后）几乎没沾到 → 按「知识库未收录」处理
        out['quality'] = 'no_hit'
        out['notice'] = NO_HIT_NOTICE
    elif cover < 0.4:
        # 低置信：向量路对任何 query 都会返回 top-N，必须标出来，并同样带上检索边界提醒
        # （否则 AI 会拿着「沾边但不对」的片段当依据，或转身去 web 猜其他框架用法）
        out['quality'] = 'low_confidence'
        out['notice'] = ('低置信命中（查询词元加权覆盖率 %.2f）：片段可能只是话题相近；'
                         '结论前请打开 path 对应文档核对，或换更具体的问法。'
                         '若确认未收录：禁止用 Qt/Android/LVGL/emWin/AWTK 等其它 GUI 框架类推，'
                         '请查官方文档 developer.flythings.cn 或转人工确认。' % cover)
    else:
        out['quality'] = 'ok'
    return json.dumps(out, ensure_ascii=False)


def flythings_hardware_info(model: str = '', platform: str = '') -> str:
    """查硬件型号库：按平台/型号拿到分辨率、按键值、接口规格与平台差异化。

    用户说「我这台是 PocketDisplay4 / SW80480070D_C」时先查这里，别按同系列型号外推。
    **有具体型号 → 按返回的 preset 直接开工**（平台/分辨率/方向/按键，不用再问）；
    **没具体型号 → 确认平台 + 分辨率就能建工程**（缺参数不阻塞）。
    - model 留空：列平台 + 各平台已登记型号（platform 可过滤，如 'V85X'）
    - model 给值：回 preset、screen（分辨率/方向）、keys（按键值 = /dev/input 事件 code）、
      specs、differences（型号/平台差异）、optional（可选补充，非阻塞）、source
    - 未收录：回 MODEL_NOT_FOUND + fallback（平台 + 分辨率即可开工）+ 近似候选（不猜规格）
    完整型号表另见知识库 knowledge/hardware/hardware-models.md。
    """
    return json.dumps(hw.query(model, platform), ensure_ascii=False)


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
    isEmptyProject=true；此时直接询问用户平台与分辨率（平台清单用 supported() 取，
    不要在文案里手写枚举）后调用 create_project，禁止去其他目录检索 json/ftu。
    ⚠️ 若 projectInfo.platform/resolution 为 null，必须先向用户询问，禁止猜测。
    """
    return json.dumps(pt.flythings_validate_project(project_root), ensure_ascii=False)


def _with_files(obj, *paths):
    """给写操作返回体补 affectedFiles（去重、去空、绝对路径）。"""
    if not isinstance(obj, dict):
        return obj
    files = []
    for p in list(obj.get('affectedFiles') or []) + list(paths):
        if not p:
            continue
        ap = os.path.abspath(p)
        if ap not in files:
            files.append(ap)
    if files:
        obj['affectedFiles'] = files
    return obj


def flythings_fui_pack(json_path: str) -> str:
    """将 json 布局打包为 ftu（设备实际加载的是 ftu）。返回 ftu 路径、控件数、分辨率。"""
    r = pt.flythings_fui_pack(json_path)
    return json.dumps(_with_files(r, r.get('ftuPath')), ensure_ascii=False)




def flythings_edit_ftu(ftu_path: str, operations: str, output_ftu: str = '',
                       overwrite: bool = False) -> str:
    """编辑 ftu 布局：自动应用编辑到 json 后 pack 回 ftu。
    ⚠️ 默认 **不覆盖**原 ftu（overwrite=False）→ 生成同目录 <name>.edited.ftu 并还原原文件；
    确认效果后再传 overwrite=True 覆盖原 ftu（或 output_ftu 指定目标）。原 ftu 与 json 都会留 .bak。
    operations 为 JSON 数组字符串，支持：
    set      {"op":"set","target":"caption或key","props":{"x":100,"y":200,"text":"新文本"}}
    remove   {"op":"remove","target":"caption或key"}
    add      {"op":"add","template":"caption或key","newKey":"textview__4","props":{...}}
    set_root {"op":"set_root","props":{"backgroundColor":"#FFFFFF"}}
    客户说「把这个按钮往右移/改文本/换颜色/删掉某控件/复制一个控件」时调用。
    布局修改以 ftu 为目标（json 为内部中间文件自动处理）；改界面布局也可直接编辑 HTML 原型后重新转换。
    ⚠️ 布局以 json 为源：优先直接编辑同目录已有 json 再 pack 回 ftu；无 json 时报错。"""
    r = pt.flythings_edit_ftu(ftu_path, operations, output_ftu, overwrite)
    return json.dumps(_with_files(r, r.get('ftuPath'), r.get('jsonPath'), r.get('backup')),
                      ensure_ascii=False)


def flythings_build_ui_flow(project_root: str, with_launch: bool = False, device: str = '') -> str:
    """⚠️ 场景别名（编译部署类意图一律本工具，禁止自造命令；不限触发入口）：
    ① 用户口语：「编译/构建/调试/全量推送/部署/部署到设备/推送到设备/跑一下」；
    ② 客户端按钮/自动化流程（「AI 应用调试」「自定义编译」等）凡意图是「编译并部署到真机调试」→ 一律调本工具；
    ③ AI 自主决策：写完/改完代码后主动编译验证、调试看效果，同样调本工具。
    ⚠️ 固化/升级/出 update.img/交付/量产 → 用 flythings_pack_upgrade（本工具=调试推送，掉电即失）。
    内部 fun launch 完成程序+资源+ftu 全量推送并启动；⚠️ 不存在 deploy_debug.sh 之类额外脚本，禁止自造命令。
    UI 构建流程：① json/ftu 时间戳一致性检查（以 json 为源，改过 json 自动重新 pack）
    ② fui pack ③ fun install 同步依赖 ④ fun build ⑤ **默认到此为止（不推真机）**；
    要推设备必须显式 with_launch=True（用户明确说「推到设备/跑一下」时才传）。
    ⚠️ fun launch 网络推送失败/超时会**自动重试 5 次**（间隔 2s，覆盖网络抖动；信任 fun 差分推送，不自写 push 脚本校验）；
    5 次仍失败（无 adb 设备/网络中断）返回 needDeviceInput=true，必须询问用户接入方式：
    1) USB 接入：设备 USB 连电脑，确认 adb devices 可见后重试；2) 网络接入：
    先在电脑执行 adb connect <设备IP> 完成配对再重试。
    ⚠️ fun launch 不支持 -s 参数，设备选择由 fun 自动完成，禁止猜 IP。
    传入项目根目录。改过 json 必须 pack，否则设备仍跑旧 ftu。
    ⚠️⚠️ src/activity/ 目录（mainActivity.cpp/h）由 IDE 编译时自动生成，构建流程已自动处理；
    禁止手动创建/修改该目录文件，业务代码只写 src/logic/*.cc。
    """
    return json.dumps(pt.flythings_build_ui_flow(project_root, with_launch, device), ensure_ascii=False)


def flythings_pack_upgrade(project_root: str, out_path: str = '', release_version: str = '',
                           ab: bool = False, with_build: bool = False,
                           dry_run: bool = False) -> str:
    """⚠️ 场景别名（固化升级类意图一律本工具，禁止自造命令；不限触发入口）：
    ① 用户口语：「打包升级包/出升级包/生成 update.img/固化/固化升级/刷进设备/烧到机器里/
       出货版本/量产版本/发布版本/TF卡升级包/OTA 包/整机升级」；
    ② 与「调试/跑一下/推送到设备」**语义不同**：那是 flythings_build_ui_flow（fun launch
       临时推送，掉电即失）；要**固化到设备、掉电保留**，必须本工具出 update.img；
    ③ AI 自主决策：用户说要交付/发布/量产一份可升级的版本时，调本工具，不要调 launch。
    流程：① fun install 同步依赖 → ②（可选 with_build=True）fun build → ③ fun pack
      （out_path→-o；release_version→--release-version；ab=True→--ab 出 AB 系统 OTA 包）。
    产物默认 `.fun/<平台>/update.img`，返回路径/大小/时间 + 三种刷法（TF卡/ADB/远程批量）。
    dry_run=True 只回命令计划不执行（写操作默认安全）。
    ⚠️ Windows 常见坑：`FATAL sign error: exit status 0xc0000135` = 缺 32 位 VC++ 运行时
      （fsimg.exe 是 32 位，装 VC++ 2015-2022 Redistributable x86）；
      `package xxx not found in local` = 依赖未装，先 fun install。
    传项目根目录；细节见 knowledge/devflow/upgrade-pack-image.md。
    """
    return json.dumps(pt.flythings_pack_upgrade(project_root, out_path, release_version,
                                                ab, with_build, dry_run),
                      ensure_ascii=False)



def flythings_ui_preview(target: str, output_dir: str = '') -> str:
    """json 布局 / 整个项目 → HTML 预览稿（客户确认 UI 用；只交付 .preview.html，不产图片/截图）。
    target 可以是项目根目录（全部 ui/*.json）或单个 json 文件路径 —— 合并了原 generate_ui_preview 与 json_to_html。
    ⚠️ 整屏 window 多页工程（visible=false + showWnd() 切页）自带「页面切换条」+ `#window__N`（简写 `#N`）
    直达某页 + 「显示隐藏」幽灵框（默认页 = 首个 visible!=false 的整屏窗口）；只看到首页 = 该 json 确实只有一个整屏窗口。
    ⚠️ 流程：布局出来后必须先出预览给用户确认，确认 OK 才允许 fui pack / 写逻辑 / 交付（未确认禁止开工）。
    """
    is_dir = os.path.isdir(target)
    r = j2h.json2html(target, output_dir)
    if is_dir and isinstance(r, dict) and r.get('success'):
        for f in r.get('files', []):
            jp = os.path.join(target, 'ui', f.get('json', ''))
            if os.path.isfile(jp):
                try:
                    with open(jp, encoding='utf-8-sig') as fh:
                        data = json.load(fh)
                    f['controls'] = sum(1 for k, v in data.items()
                                         if isinstance(v, dict) and '__' in k)
                except Exception:
                    pass
        r['projectRoot'] = target
        r['outputDir'] = output_dir or os.path.join(target, 'ui')
        r['note'] = 'html 为客户预览稿；设备端仍用 fui pack 生成的 ftu，两者同源于 json'
    return json.dumps(r, ensure_ascii=False)


def flythings_html_to_json(input_html: str, output_json: str = '', res: str = '') -> str:
    """受限 HTML 交互原型 → ui/*.json 布局（CSS 效果自动转图，产物尺寸 == 控件盒）。

    ⚠️ 写原型前先读知识库「HTML_SUBSET 原型规范」（检索：HTML_SUBSET / 控件映射 / data-icon 图标 /
    CSS 效果转图 / JS 交互稿）：控件映射表、data-* 属性、46 个内置图标词、文本与布局铁律、
    自动转图清单、JS 交互稿做法都在那里；这里只留要点——
    根节点 <div class="screen" data-res="WxH" data-bg="#RRGGBB">；定位 data-x/y/w/h；字号 data-fs；
    data-caption 命名；data-pic 自备图；**图标优先**（常用操作必须用图标，禁止「按钮+文字」糊弄）；
    文本只用汉字+ASCII+基础符号（禁 emoji）；Z 序 = 书写顺序。

    ⚠️ 工作流红线：客户说明书/参考照片不能直接转 json（先提炼 UI 需求清单给用户确认）；
    转换后必须先出预览稿给用户确认（只交付 .preview.html 本身），确认 OK 才允许 pack / 写逻辑 / 交付。
    ⚠️ 效果一律转图片 + 控件组合：渐变/阴影+圆角/emoji/loading 自动出图到 <项目>/resources/images/，
    json 引用写 images/xxx.png；**禁止 AI 自绘 1x png 或外部生图直出小图**。
    output_json 缺省 html 同名 .json；res 可覆盖分辨率（如 "800x480"）。
    """
    return json.dumps(h2j.html2json(input_html, output_json or None, res or None), ensure_ascii=False)


def flythings_list_packages(platform: str = '') -> str:
    """列出依赖包生态（platform 如 F133/Z20，留空列全部），含功能描述与版本。写代码前调用。"""
    return json.dumps(pkgtools.flythings_list_packages(platform or None), ensure_ascii=False)


def flythings_query_package(package: str, platform: str = _platforms.DEFAULT_PLATFORM) -> str:
    """查询依赖包在指定平台的可用版本。传入包名（如 mqtt-cxx）与平台。"""
    return json.dumps(pkgtools.flythings_query_package(package, platform), ensure_ascii=False)


def flythings_manifest(features: str, platform: str = _platforms.DEFAULT_PLATFORM, project_root: str = '',
                       dry_run: bool = True) -> str:
    """按功能需求准备 Manifest.xml 依赖配置（**默认只推荐、不写盘**）。
    features 为逗号分隔关键词（如 'mqtt,json,蓝牙'）。
    - dry_run=True（默认，= 原 recommend_manifest）：只回推荐与递归补齐建议，不动任何文件
    - dry_run=False（= 原 generate_manifest 的写盘形态）：把生成的 Manifest.xml 写入
      <project_root>/Manifest.xml（原文件先备份 .bak，返回 affectedFiles）
    已知包名要直接加进项目时用 flythings_add_package。
    """
    flist = [f.strip() for f in str(features).split(',') if f.strip()]
    if dry_run:
        r = pkgtools.flythings_generate_manifest(flist, platform)
        if isinstance(r, dict):
            r['dryRun'] = True
            r['hint'] = ('dry_run=True 只推荐不写盘；确认后用 dry_run=False + project_root 写入 Manifest.xml，'
                         '或逐个用 flythings_add_package 追加并 fun install')
        return json.dumps(r, ensure_ascii=False)
    if not project_root:
        return json.dumps({'ok': False, 'op': 'flythings_manifest',
                           'error': {'code': 'BAD_PARAMS',
                                     'msg': 'dry_run=False 时必须提供 project_root',
                                     'hint': '先 dry_run=True 看推荐，确认后传 project_root 写入',
                                     'retryable': True}, 'warnings': []}, ensure_ascii=False)
    gen = pkgtools.flythings_generate_manifest(flist, platform)
    if not (isinstance(gen, dict) and gen.get('success') and gen.get('manifest')):
        return json.dumps({'ok': False, 'op': 'flythings_manifest',
                           'error': {'code': 'GENERATE_FAILED',
                                     'msg': '生成 Manifest 失败: %s' % (gen.get('error') if isinstance(gen, dict) else gen),
                                     'hint': '', 'retryable': False}, 'warnings': []}, ensure_ascii=False)
    root = os.path.abspath(project_root)
    if not os.path.isdir(root):
        return json.dumps({'ok': False, 'op': 'flythings_manifest',
                           'error': {'code': 'NO_PROJECT', 'msg': '项目目录不存在: %s' % root,
                                     'hint': '', 'retryable': False}, 'warnings': []}, ensure_ascii=False)
    target = os.path.join(root, 'Manifest.xml')
    backup = ''
    if os.path.isfile(target):
        backup = target + '.bak'
        shutil.copy2(target, backup)      # 写前必备份（破坏性默认值收口）
    io.open(target, 'w', encoding='utf-8', newline='\n').write(gen['manifest'])
    out = dict(gen)
    out.update({'dryRun': False, 'manifestPath': target, 'backup': backup,
                'affectedFiles': [target] + ([backup] if backup else []),
                'hint': 'Manifest 已写盘；依赖拉取请接着调 flythings_add_package（with_install=True）'
                        '或项目内 fun install'})
    return json.dumps(out, ensure_ascii=False)
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




def flythings_package_search(keyword: str, platform: str = _platforms.DEFAULT_PLATFORM) -> str:
    """按功能关键词搜索可用 package（mqtt/json/http/ssl/ble/ota/audio 等）。"""
    return json.dumps(pkgtools.flythings_search_package(keyword, platform), ensure_ascii=False)


def flythings_get_package_api(package_id: str, platform: str = _platforms.DEFAULT_PLATFORM, version: str = '') -> str:
    """获取 package 的头文件路径、类方法签名、使用示例。传入包名与可选版本。"""
    return json.dumps(pkgtools.flythings_get_package_api(package_id, platform, version or None), ensure_ascii=False)


def flythings_resolve_dependencies(packages: str, platform: str = _platforms.DEFAULT_PLATFORM) -> str:
    """递归解析 package 依赖树并检测冲突。packages 为 JSON 数组字符串，
    如 '[{"id":"mqtt-cxx","version":"3.2.0"}]'。返回依赖树、解析结果与冲突建议。
    """
    return json.dumps(pkgtools.flythings_resolve_dependencies(packages, platform), ensure_ascii=False)


def flythings_create_bin_project(project_root: str, project_name: str = '', platform: str = _platforms.DEFAULT_BIN_PLATFORM,
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
                          platform: str = _platforms.DEFAULT_BIN_PLATFORM, with_build: bool = True,
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
    传入目标项目根目录、平台（可建工程的口径，由 platforms.py 统一提供）与分辨率（如 800x480）。
    ⚠️ platform/resolution 必填且必须来自用户明确提供，未指定时先询问，禁止猜测或用默认值。
    ⚠️⚠️ src/activity/ 目录（mainActivity.cpp/h）由 IDE 编译时根据 ftu 自动生成，
    禁止创建/修改/覆盖该目录任何文件！业务代码只能写 src/logic/*.cc；
    mXXXPtr 控件指针 / ID_MAIN_* 宏 / 回调表 / findControlByID 初始化全部由 IDE 自动生成，禁止手写。
    """
    return json.dumps(pt.flythings_create_project(project_root, platform, resolution,
                                                  app_name, with_cli, force), ensure_ascii=False)


def flythings_check_project_deps(project_root: str, platform: str = _platforms.DEFAULT_PLATFORM) -> str:
    """扫描项目 include 的三方库与 Manifest 声明对比，返回缺失依赖。
    需要三方能力（MQTT/HTTP/JSON/蓝牙/SSL 等）时先调用。
    """
    return json.dumps(pkgtools.flythings_check_project_deps(project_root, platform), ensure_ascii=False)


def flythings_generate_ui_assets(project_root: str, assets: str) -> str:
    """生成 UI 图片资源（图标/牌面/按钮背景等）→ <项目>/resources/images/（json 引用写 images/xxx.png）。

    assets 为 JSON 数组字符串，每项：{name, size, prompt, emoji, color, kind}
    —— name 必填（自动补 .png）；prompt 有则优先 AI 生图，失败用 emoji，再不行用 color/kind 线条兜底；
    kind 可选 check/charging/wifi/alert/circle/square/star/heart；返回每项实际方式 method(ai/emoji/line)。
    三级降级（AI 生图 → 本地 emoji → 线条兜底）保证客户无 AI 能力也能出图。

    ⚠️ 图片资源铁律（尺寸 == 控件盒、圆角四角 alpha=0、透明角图不配 bgColorTab、功能按钮用 picTab 两态、
    生成后查四角 alpha、PNG 防锯齿五要素、**禁止 1x 直画/外部生图直出小图**）+
    三条合法出图路径见知识库「UI 图片资源铁律与 PNG 抗锯齿管线」，检索：图片资源铁律 / 抗锯齿 /
    圆角四角发黑 / 走哪条路出图。
    """
    return json.dumps(h2j_genres.gen_ui_assets(project_root, assets), ensure_ascii=False)


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
    r = itx.flythings_i18n_import(project_root, lang, translations, merge)
    try:
        r2 = json.loads(r) if isinstance(r, str) else r
    except Exception:
        return r if isinstance(r, str) else json.dumps(r, ensure_ascii=False)
    if isinstance(r2, dict):
        _with_files(r2, r2.get('path'), r2.get('trPath'))
    return json.dumps(r2, ensure_ascii=False)


def flythings_i18n_refactor(project_root: str, lang: str = 'zh_CN', dry_run: bool = True) -> str:
    """把布局 json 里写死的非空文本控件替换为 @key 引用（多语言改造辅助）。
    dry_run=True 只预览不改文件；False 执行替换并写入指定语言 .tr。
    纯数字/时间占位文本自动跳过。"""
    return json.dumps(itx.flythings_i18n_refactor(project_root, lang, dry_run), ensure_ascii=False)


def flythings_i18n_to_json(project_root: str, langs: str = '', push: bool = True, device: str = '') -> str:
    """把 i18n/*.tr 转为 i18n/*.json（设备 zkgui 实际加载格式），并可推送到设备 /tmp/tr/。

    ⚠️ **fun launch 不推 i18n**（只推 ftu/images/font/lib/cfg）—— 改完翻译后必须显式调本工具，
    否则设备仍跑旧翻译（logcat 刷 'not found value' 警告）。本工具生成 json 与设备端逐字节一致
    （tab 缩进+无空格冒号+末尾无换行），默认自动 adb push 到 /tmp/tr/；多设备需传 device=IP。
    生产固件翻译打包到 /res/，无需推送（push=False）。

    完整流程：flythings_i18n_import / add_language / refactor 改 .tr → 本工具转 json + push →
    adb shell "setprop ctl.stop zkswe && setprop ctl.start zkswe"（DEBUG 模式重启加载）。
    """
    return json.dumps(itx.flythings_i18n_to_json(project_root, langs, push, device), ensure_ascii=False)


# ── UI 可视化三合一（v0.27.37，沛哥：ui-visual 组做成一个带 action 的入口）──────────────
# 旧 op flythings_ui_editor / flythings_ui_edit_apply / flythings_ui_diff 已并入
# flythings_ui_visual(action=...)（见 RENAMED）；下面是三个动作的内层实现，不再单独注册。
def _ui_editor(project_root: str, output_dir: str = '') -> str:
    """把 ui/*.json 生成「可视化编辑器」网页：拖控件就改布局（输出 <项目>/ui/_edit/<name>.edit.html）。

    闭环第二步：AI 出/改 json → 本工具出编辑器给用户拖 → 用户点「复制 AI 指令」
    （自带工程路径 + 目标 json + 变更 JSON 的一段话）直接粘给 AI，或「复制变更 JSON」拿纯 json →
    flythings_ui_visual(action="edit_apply") 写回 json + pack ftu。页面是本地静态文件、无回传通道，只能复制粘贴。
    预览与设备同源（都来自 json），改完即所得。

    页面能力（点选/拖动/8 手柄缩放、方向键微调、网格吸附、Alt+点穿透选中下层、被遮罩控件也能拖、
    控件列表搜索、visible:false 幽灵框、属性栏列出全部字段、图片尺寸预检红黄标、深链接 #button__2）
    见知识库「UI 可视化编辑器 用法与能力」，检索：可视化编辑器 / Alt 点穿透 / 属性栏 / 拖完怎么回 json。
    output_dir 缺省 <项目>/ui/_edit。
    """
    if uied is None:
        return json.dumps({'success': False, 'error': 'ui_editor 不可用（缺 ui_tools/ui_editor.py 或 Pillow）'},
                          ensure_ascii=False)
    try:
        r = uied.make_editor(project_root, output_dir)
    except Exception as e:
        return json.dumps({'success': False, 'error': str(e)}, ensure_ascii=False)
    if isinstance(r, dict) and r.get('success'):
        r['projectRoot'] = project_root
        r['note'] = ('在浏览器打开 *.edit.html 拖动/改属性；改完点「复制 AI 指令」，把指令（自带工程路径 + '
                     '目标 json + 变更 JSON）直接粘给 AI，AI 用 flythings_ui_visual(action="edit_apply") 写回 json'
                     '（默认不动 ftu，要 ftu 就说 pack）；只想要纯 json 就点「复制变更 JSON」/「下载变更 JSON」。'
                     '⚠️ 页面是本地静态文件、没有回传通道，必须复制粘贴给 AI')
        for f in r.get('files', []):
            if f.get('html'):
                f['open'] = f['html']
    return json.dumps(r, ensure_ascii=False)


def _ui_edit_apply(project_root: str, changes: str, pack: bool = False,
                   dry_run: bool = False) -> str:
    """把 ui_editor 导出的「变更 JSON」写回 ui/*.json（**默认不 pack、可先 dry_run 预览**）。

    changes：可直接传 JSON 文本（用户从编辑器复制过来的），也可传文件路径。
    结构：
        {"file": "main.json", "resolution": "1600x600",
         "changes": {"button__1": {"left": 130, "top": 60, "width": 150, "height": 54}},
         "props":   {"textview__4": {"text": "新文字", "fontSize": 22,
                                     "colorTab": {"color0": 16711680}}}}
    控件路径：顶层 "button__1"；嵌套 window 内 "window__2/button__3"。
    changes = 几何（position 四项）；props = 其它属性（深合并写回）；两者都可省。
    ⚠️ 破坏性默认值收口（v0.27.32）：pack 默认 False（确认布局无误后再显式传 pack=True）；
    dry_run=True 只回「将要改什么」的预览（不写盘、不 pack）。

    安全：① 写回前自动备份 <name>.json.bak；② 格式一致性自检（原文件必须能被
    json.dumps(indent=2, ensure_ascii=False) 无损还原，否则拒绝写入以免整文件重排）；
    ③ 坐标取整 + 不越出屏幕；④ 返回 affectedFiles 与 .bak 路径，便于回滚/审计。
    """
    if uia is None:
        return json.dumps({'success': False, 'error': 'ui_edit_apply 不可用'}, ensure_ascii=False)
    text = (changes or '').strip()
    tmp = ''
    try:
        if not text:
            return json.dumps({'success': False, 'error': 'changes 为空'}, ensure_ascii=False)
        if not text.startswith('{'):
            if not os.path.isfile(text):
                return json.dumps({'success': False, 'error': 'changes 既不是 JSON 文本也不是文件路径'},
                                  ensure_ascii=False)
            with open(text, encoding='utf-8-sig') as f:
                ch = json.load(f)
        else:
            ch = json.loads(text)
        r = uia.apply_changes(ch, project=project_root, dry_run=bool(dry_run))
        if r.get('success') and pack and not dry_run:
            r['pack'] = uia.pack(r['json'], project_root)
        if dry_run:
            r['note'] = ('dry_run：仅预览，未写盘；确认后传 dry_run=False 写回' +
                         '（要接着 pack 再传 pack=True）')
        else:
            r['note'] = '变更已写回 json' + ('（含 ftu 重新打包）' if r.get('pack') else
                                             '（未 pack：布局确认后传 pack=True）') + \
                        '；备份在同目录 <name>.json.bak'
        return json.dumps(_with_files(r, r.get('json'), r.get('backup')), ensure_ascii=False)
    except Exception as e:
        return json.dumps({'success': False, 'error': str(e)}, ensure_ascii=False)
    finally:
        if tmp and os.path.isfile(tmp):
            try:
                os.remove(tmp)
            except Exception:
                pass


def _ui_diff(image_a: str, image_b: str, tolerance: int = 2, shift: int = 1,
             min_area: int = 4, blur: float = 0.7, noise_bbox: int = 10,
             out_png: str = '', out_json: str = '', show_noise: bool = False) -> str:
    """两张同尺寸截图的像素级对比（0 token，纯本地算法）——UI 验收 / 回归对比。

    输出的**是差异清单（数字）不是图**，所以不吃 token：区域坐标 / 尺寸 / 面积 / 最大色差。
    典型用法：改布局前截一张、改后截一张，两张丢进来 → 只有预期差异才算过；
    「改 A 碰坏 B」会被逐块列出来。跨渲染器（HTML 预览 vs 设备截图）只当骨架参考，
    字体磨边噪声靠下面的阈值压。

    抑制假报警的默认参数（沛哥 2026-09-10 定）：
    - tolerance=2：单通道 |Δ|<=2 视为相同
    - shift=1：±1px 抖动补偿（每像素在邻域找最优匹配，"看着像差异其实只是抖动"不算）
    - blur=0.7：对比前高斯模糊，抹掉字体抗锯齿噪声
    - min_area=4 + noise_bbox=10：小于 4px 的斑点和 bbox<=10x10 的小碎块归入 noise 不计入主清单
      （要连小碎块一起看，传 show_noise=True）
    out_png 给出标注图路径（红框=主差异，黄框=噪声）；out_json 存差异清单；缺省只返回清单。
    """
    if udf is None:
        return json.dumps({'success': False, 'error': 'ui_diff 不可用（缺 numpy/Pillow）'},
                          ensure_ascii=False)
    try:
        for p in (image_a, image_b):
            if not os.path.isfile(p):
                return json.dumps({'success': False, 'error': f'图片不存在: {p}'}, ensure_ascii=False)
        r = udf.diff_images(image_a, image_b, tol=int(tolerance), shift=int(shift),
                            min_area=int(min_area), open_k=3, out_png=out_png,
                            out_json=out_json, blur=float(blur),
                            noise_bbox=int(noise_bbox), show_noise=bool(show_noise))
        r['note'] = ('identical=true 表示无差异；regions 为真实差异块（坐标/面积/最大色差），'
                     'noise 为已忽略的抗锯齿/文字磨边小碎块')
        return json.dumps(r, ensure_ascii=False)
    except Exception as e:
        return json.dumps({'success': False, 'error': str(e)}, ensure_ascii=False)


# ── 合并后的唯一入口（v0.27.37）──────────────────────────────────────────
# 三动作合一：editor（原 ui_editor）/ edit_apply（原 ui_edit_apply）/ diff（原 ui_diff）。
# 每个 action 只接受自己的参数；传了别家的参数会回 visualNote 提醒（不静默忽略）。
UI_VISUAL_ACTIONS = ('editor', 'edit_apply', 'diff')
UI_VISUAL_ARGS = {
    'editor': ('project_root', 'output_dir'),
    'edit_apply': ('project_root', 'changes', 'pack', 'dry_run'),
    'diff': ('image_a', 'image_b', 'tolerance', 'shift', 'min_area', 'blur',
             'noise_bbox', 'out_png', 'out_json', 'show_noise'),
}
UI_VISUAL_REQUIRED = {'editor': ('project_root',),
                      'edit_apply': ('project_root', 'changes'),
                      'diff': ('image_a', 'image_b')}
_UI_VISUAL_DEFAULTS = {'project_root': '', 'output_dir': '', 'changes': '', 'pack': False,
                       'dry_run': False, 'image_a': '', 'image_b': '', 'tolerance': 2,
                       'shift': 1, 'min_area': 4, 'blur': 0.7, 'noise_bbox': 10,
                       'out_png': '', 'out_json': '', 'show_noise': False}


def _ui_visual_bad(msg, hint):
    """三合一入口的参数错误：给可机读 BAD_PARAMS + 本 action 的正确参数清单。"""
    return json.dumps({'ok': False, 'op': 'flythings_ui_visual',
                       'error': _err_obj('BAD_PARAMS', msg, hint, True),
                       'warnings': []}, ensure_ascii=False)


def _ui_visual_note(raw, note):
    """给内层结果补一条 visualNote（不改内层语义；解析不了就原样回）。"""
    if not note:
        return raw
    try:
        d = json.loads(raw)
    except ValueError:
        return raw
    if isinstance(d, dict):
        d['visualNote'] = note
        return json.dumps(d, ensure_ascii=False)
    return raw


def flythings_ui_visual(action: str = 'list', project_root: str = '', output_dir: str = '',
                        changes: str = '', pack: bool = False, dry_run: bool = False,
                        image_a: str = '', image_b: str = '', tolerance: int = 2,
                        shift: int = 1, min_area: int = 4, blur: float = 0.7,
                        noise_bbox: int = 10, out_png: str = '', out_json: str = '',
                        show_noise: bool = False) -> str:
    """UI 可视化三合一入口（action 选动作；旧 ui_editor / ui_edit_apply / ui_diff 已并入本 op）。

    - action="editor"：ui/*.json → 可拖拽编辑器网页（<项目>/ui/_edit/<name>.edit.html）。必填
      project_root；可选 output_dir。用户拖完点「复制 AI 指令」粘给 AI——页面是本地静态文件、
      无回传通道，只能复制粘贴。控件/页面能力见知识库「UI 可视化编辑器 用法与能力」。
    - action="edit_apply"：编辑器导出的变更 JSON 写回 ui/*.json。必填 project_root、changes
      （JSON 文本或文件路径）；pack 默认 False（不动 ftu）；dry_run=True 只预览不写盘。
      结构 {"file","resolution","changes":{控件路径:{left,top,width,height}},"props":{控件路径:{...}}}；
      控件路径顶层 "button__1"、嵌套 "window__2/button__3"；写回前自动 .bak，格式不一致拒绝写。
    - action="diff"：两张同尺寸截图像素级对比（0 token 差异清单，不是图）。必填 image_a、image_b；
      tolerance=2 / shift=1（±1px 抖动）/ blur=0.7（字磨边）/ min_area=4 / noise_bbox=10 压假报警，
      show_noise 连小碎块一起看，out_png 出标注图、out_json 存清单。跨渲染器（HTML 预览 vs 真机截图）
      只当骨架参考。

    action 传 list（或省略）只回各 action 的必填参数。
    """
    act = str(action or '').strip().lower().replace('-', '_')
    if act in ('', 'list', 'help', '?'):
        return json.dumps({'success': True, 'op': 'flythings_ui_visual',
                           'actions': {k: {'args': list(v),
                                           'required': list(UI_VISUAL_REQUIRED[k])}
                                       for k, v in UI_VISUAL_ARGS.items()},
                           'hint': ('action 取 editor / edit_apply / diff；'
                                    '旧 ui_editor / ui_edit_apply / ui_diff 已并入本 op')},
                          ensure_ascii=False)
    if act not in UI_VISUAL_ACTIONS:
        return _ui_visual_bad('unknown action: %s' % action,
                              'action 取 editor / edit_apply / diff（传 action="list" 看参数）')
    given = {'project_root': project_root, 'output_dir': output_dir, 'changes': changes,
             'pack': pack, 'dry_run': dry_run, 'image_a': image_a, 'image_b': image_b,
             'tolerance': tolerance, 'shift': shift, 'min_area': min_area, 'blur': blur,
             'noise_bbox': noise_bbox, 'out_png': out_png, 'out_json': out_json,
             'show_noise': show_noise}
    miss = [k for k in UI_VISUAL_REQUIRED[act] if not str(given[k] or '').strip()]
    if miss:
        return _ui_visual_bad('action=%s 缺必填参数: %s' % (act, ', '.join(miss)),
                              '本 action 参数: %s(%s)' % (act, ', '.join(UI_VISUAL_ARGS[act])))
    ignored = [k for k in given
               if k not in UI_VISUAL_ARGS[act] and given[k] != _UI_VISUAL_DEFAULTS[k]]
    note = ('action=%s 用不到这些参数，已忽略: %s（各 action 参数见 action="list"）'
            % (act, ', '.join(ignored))) if ignored else ''
    if act == 'editor':
        return _ui_visual_note(_ui_editor(project_root, output_dir), note)
    if act == 'edit_apply':
        return _ui_visual_note(_ui_edit_apply(project_root, changes, pack, dry_run), note)
    return _ui_visual_note(_ui_diff(image_a, image_b, tolerance, shift, min_area, blur,
                                    noise_bbox, out_png, out_json, show_noise), note)


def flythings_verify_assets(project_root: str) -> str:
    """核对「json 声明 vs 磁盘产物」：图片引用是否存在 + 自动生成图 PNG 尺寸是否 == 控件 position。

    ⚠️ 生成/改完图片资源后必跑（v0.27.30 阴影丢图事故就是「产物没人核对」）。
    布局支持 ui/*.json 与 ui/<分辨率>/*.json 两种真实工程布局（v0.27.33 前只认扁平一层，
    分层工程会「0 页却报 ok」）。
    返回：
      - missing[]  引用了但文件不存在 → 真问题
      - mismatch[] 自动生成图（resources/images/，铁律 #9）尺寸 != position → 真问题
      - stretched[]手绘图尺寸 != 控件盒 → 仅提示（引擎会拉伸，导航图标/背景图常态）
      - unresolved[]运行时格式化引用 / 读图失败等跳过项
      - warnings[] 0 页等「其实没核对到东西」的情况
    与 check_all 第 17 项同一实现。
    """
    if chk_all is None:
        return json.dumps({'ok': False, 'error': 'check_all 模块不可用（缺 ui_tools/check_all.py）'},
                          ensure_ascii=False)
    try:
        r = chk_all.verify_assets(project_root)
    except Exception as e:
        return json.dumps({'ok': False, 'error': 'verify_assets 失败: %s' % e}, ensure_ascii=False)
    r['hint'] = ('missing → 补图或改 json 引用（自动生成图片放 resources/images/，引用写 images/xxx.png）；'
                 'mismatch → 重新出图，使 PNG 尺寸严格 == 控件 position；'
                 'stretched 一般无需处理（手绘图由引擎拉伸到控件盒）')
    return json.dumps(r, ensure_ascii=False)


# device_screenshot 的进阶参数默认值（v0.27.34：这些键也可统一走 advanced JSON，
# 已显式传的同名参数优先 —— 参数分层的判定基准）
_DSS_ADV_DEFAULTS = {'fb': '/dev/fb0', 'pixel': 'auto', 'width': 0, 'height': 0, 'offset_y': -1,
                     'flip': '', 'rotate': 'auto', 'crop': '', 'name': '', 'timeout': 180}


def flythings_device_screenshot(device: str = '', out: str = '', fmt: str = 'png', scale: float = 1.0,                               quality: int = 90, fb: str = '/dev/fb0', pixel: str = 'auto',
                               width: int = 0, height: int = 0, offset_y: int = -1,
                               flip: str = '', rotate: str = 'auto', crop: str = '', name: str = '',
                               timeout: int = 180, advanced: str = '') -> str:
    """从**设备真机**抓当前屏幕 → PNG / JPG / BMP，交给视觉模型看或用 flythings_ui_visual(action="diff") 做像素验收。

    何时用：要确认设备上实际显示成什么样（布局对不对、图标锯齿、切图、颜色/文字、改完验收、
    用户说"我屏幕上看到的是..."而你没有截图）。三段式验收第二步：预览 → 本工具（像素真相）→ ui_diff 比对。

    常用（默认参数就够）：默认即抓一张；scale=0.5 或 fmt='jpg', quality=85 省 token；
    多设备传 device='<设备IP>:5555'（先 adb connect）；方向缺省 rotate='auto' 会读项目工程 EasyUI.cfg
    的 rotateScreen 自动转正（rotateSource 可自证；触摸角度看 screenInfo.rotateTouch，可与显示不同）；
    只要应用画面（去黑边）用 crop='auto'。⚠️ 抓完把返回的 path 交给看图能力，不要把 raw/文件本身丢给模型。

    ⚠️ 进阶参数（fb / pixel / width / height / offset_y / flip / rotate / crop / name / timeout）
    **推荐统一走 advanced**（JSON 字符串，如 advanced='{"crop":"auto","pixel":"rgba"}'）；
    同名显式参数优先于 advanced（旧客户端不受影响）。

    ⚠️ 实现要点（设备没有 screencap/dd、必须按 stride 取、双缓冲 pan 页翻转抓错帧、
    32bpp BGRA 通道序、角度只认工程配置 + 三个反面做法）见知识库「真机抓屏 实现要点与踩坑」，
    检索：抓屏 / 双缓冲 pan / 颜色红蓝互换 / 取图角度 rotateScreen。
    """
    if dss is None:
        return json.dumps({'success': False, 'error': 'device_screenshot 不可用（缺 ui_tools/device_screenshot.py 或 Pillow）'},
                          ensure_ascii=False)
    # 参数分层（v0.27.34）：fb/pixel/width/height/offset_y/flip/rotate/crop/name/timeout 可统一走 advanced
    # （JSON 对象字符串）；**已显式传的同名参数优先**（旧客户端不受影响）。
    params = {'fb': fb, 'pixel': pixel, 'width': width, 'height': height, 'offset_y': offset_y,
              'flip': flip, 'rotate': rotate, 'crop': crop, 'name': name, 'timeout': timeout}
    if advanced and str(advanced).strip():
        try:
            adv = json.loads(advanced)
        except Exception as e:
            return json.dumps({'ok': False, 'op': 'flythings_device_screenshot',
                               'error': {'code': 'BAD_ARGS', 'msg': 'advanced 不是合法 JSON: %s' % e,
                                         'hint': 'advanced 传 JSON 对象字符串（如 {"crop": "auto"}）',
                                         'retryable': True}, 'warnings': []}, ensure_ascii=False)
        if not isinstance(adv, dict):
            return json.dumps({'ok': False, 'op': 'flythings_device_screenshot',
                               'error': {'code': 'BAD_ARGS', 'msg': 'advanced 必须是 JSON 对象',
                                         'hint': '可选键: %s' % ', '.join(sorted(params)),
                                         'retryable': True}, 'warnings': []}, ensure_ascii=False)
        unknown = sorted(k for k in adv if k not in params)
        if unknown:
            return json.dumps({'ok': False, 'op': 'flythings_device_screenshot',
                               'error': {'code': 'BAD_ARGS',
                                         'msg': 'advanced 含未知键: %s' % ', '.join(unknown),
                                         'hint': '可选键: %s' % ', '.join(sorted(params)),
                                         'retryable': True}, 'warnings': []}, ensure_ascii=False)
        for k, v in adv.items():
            if params[k] == _DSS_ADV_DEFAULTS[k]:     # 未显式指定 → advanced 生效
                params[k] = v
    try:
        r = dss.capture(device=device, out=out, fmt=fmt, scale=scale, quality=quality, **params)
    except Exception as e:
        return json.dumps({'success': False, 'error': str(e)}, ensure_ascii=False)
    return json.dumps(r, ensure_ascii=False)


# ===== 统一返回契约（v0.27.31）=====
# 所有工具返回值统一为 {ok, op, warnings[], error{code,msg,hint,retryable}}；
# 保留原有键（success / error 文本 / 业务字段）向后兼容，非 JSON 纯文本收进 data.text。
# 目的：宿主 AI 能机读判定「成功/失败/是否可重试」，不再出现有的回 success、有的回 ok、
# 错误只有一句字符串（MCP isError 永为 false）的情况。

def _err_obj(code, msg, hint='', retryable=False):
    return {'code': code or 'ERROR', 'msg': str(msg), 'hint': hint, 'retryable': bool(retryable)}


def normalize_result(op, raw):
    """把任意工具返回值归一化为统一 envelope（幂等，重复归一不再变）。"""
    if not isinstance(raw, str):
        try:
            raw = json.dumps(raw, ensure_ascii=False, default=str)
        except Exception:
            raw = json.dumps({'data': str(raw)}, ensure_ascii=False)
    try:
        obj = json.loads(raw)
    except Exception:
        return json.dumps({'ok': True, 'op': op, 'data': {'text': raw}, 'warnings': []},
                          ensure_ascii=False)
    if not isinstance(obj, dict):
        return json.dumps({'ok': True, 'op': op, 'data': obj, 'warnings': []}, ensure_ascii=False)
    out = dict(obj)
    ok = out.get('ok')
    if not isinstance(ok, bool):
        if 'success' in out:
            ok = bool(out['success'])
        else:
            ok = not any(k in out for k in ('error', 'errors', 'fail'))
        out['ok'] = ok
    err = out.get('error')
    if not ok:
        if isinstance(err, dict):
            out['error'] = _err_obj(err.get('code'), err.get('msg') or err.get('message') or err,
                                    err.get('hint', ''), err.get('retryable', False))
        elif isinstance(err, str):
            out['error'] = _err_obj(out.get('code'), err, out.get('hint', ''),
                                    out.get('retryable', False))
        elif err is None:
            out['error'] = _err_obj(out.get('code'),
                                    out.get('message') or out.get('msg') or 'unknown error',
                                    out.get('hint', ''), out.get('retryable', False))
    elif isinstance(err, str):
        out.pop('error', None)  # ok=True 时的残留错误字符串清掉，避免误判
    out.setdefault('warnings', [])
    out.setdefault('op', op)
    return json.dumps(out, ensure_ascii=False)


def _sig_args(fn) -> list:
    """函数签名参数名（给 BAD_PARAMS 回显用）。"""
    import inspect as _i
    try:
        return [p.name for p in _i.signature(fn).parameters.values()
                if p.name not in ('ctx', 'self')]
    except (TypeError, ValueError):
        return []


def _envwrap(name, fn):
    """工具级包装：统一 envelope + 内部异常不再静默（转为可机读 error 返回）。

    参数绑定错误（少传/写错参数名）单独识别为 **BAD_PARAMS** 并附正确签名：
    否则会被下面的 except 归成 TOOL_RAISED，AI 拿不到签名就得猜参数（v0.27.33 修）。
    """
    import functools

    @functools.wraps(fn)
    def wrapper(*a, **kw):
        try:
            inspect.signature(fn).bind(*a, **kw)      # 只做绑定校验，不执行
        except TypeError as e:
            return json.dumps(
                {'ok': False, 'op': name,
                 'error': _err_obj('BAD_PARAMS', '%s: %s' % (type(e).__name__, e),
                                   '本 op 正确签名: %s(%s)'
                                   % (name, ', '.join(_sig_args(fn))), True),
                 'warnings': []}, ensure_ascii=False)
        try:
            return normalize_result(name, fn(*a, **kw))
        except Exception as e:
            return json.dumps(
                {'ok': False, 'op': name,
                 'error': _err_obj('TOOL_RAISED', '%s: %s' % (type(e).__name__, e),
                                   'v0.27.31 起工具内部异常不再静默；请把本消息连同 op 反馈给官方',
                                   False),
                 'warnings': []}, ensure_ascii=False)
    return wrapper


# 注册前统一包装（两条路径——flythings_kb 分发器与独立工具——返回同一契约）
for _n in _tool_names():
    globals()[_n] = _envwrap(_n, globals()[_n])


# ── op 注册清单（唯一来源）──────────────────────────────────────────────
# register_all 与 mcp_server 的分发器共用本清单；新增 op 只需：
#   ① 在 kb_tools 里定义 flythings_xxx 函数  ② 把名字加进 OP_NAMES
#   ③ 跑 scripts/check_consistency.py（校验 OP_NAMES == 模块内全部 flythings_* 函数）
OP_NAMES = (
    'flythings_get_version',
    'flythings_knowledge_search',
    'flythings_hardware_info',
    'flythings_read_json',
    'flythings_get_project_spec',
    'flythings_validate_project',
    'flythings_fui_pack',
    'flythings_edit_ftu',
    'flythings_build_ui_flow',
    'flythings_pack_upgrade',
    'flythings_ui_preview',
    'flythings_html_to_json',
    'flythings_ui_visual',
    'flythings_verify_assets',
    'flythings_device_screenshot',
    'flythings_attach_cli_tools',
    'flythings_create_project',
    'flythings_create_bin_project',
    'flythings_gen_ui_test',
    'flythings_check_project_deps',
    'flythings_generate_ui_assets',
    'flythings_i18n_scan',
    'flythings_i18n_add_language',
    'flythings_i18n_export',
    'flythings_i18n_import',
    'flythings_i18n_refactor',
    'flythings_i18n_to_json',
    'flythings_list_packages',
    'flythings_query_package',
    'flythings_manifest',
    'flythings_add_package',
    'flythings_package_search',
    'flythings_get_package_api',
    'flythings_resolve_dependencies',
)

# 已合并/改名的 op（v0.27.36 起，沛哥：工具直接合并，不留别名）——
# 分发器遇到它们时回 OP_RENAMED + 新名字（**只是错误提示，不执行**，不会变成隐性别名）。
RENAMED = {
    'flythings_search': 'flythings_knowledge_search',
    'flythings_generate_ui_preview': 'flythings_ui_preview',
    'flythings_json_to_html': 'flythings_ui_preview',
    'flythings_recommend_manifest': 'flythings_manifest',
    'flythings_generate_manifest': 'flythings_manifest',
    'flythings_search_package': 'flythings_package_search',
    'flythings_ui_editor': 'flythings_ui_visual',
    'flythings_ui_edit_apply': 'flythings_ui_visual',
    'flythings_ui_diff': 'flythings_ui_visual',
}

# 合并后带 action 的入口：旧名 → 该用哪个 action（分发器把它拼进 OP_RENAMED 的 hint）。
RENAMED_HINT = {
    'flythings_ui_visual': ('action 取 editor（原 ui_editor）/ edit_apply（原 ui_edit_apply）'
                            '/ diff（原 ui_diff）'),
}


def register_all(mcp):
    """把全部 op 注册到 MCP server；返回已注册函数列表（smoke / 一致性检查用）。"""
    fns = []
    for name in OP_NAMES:
        fn = globals().get(name)
        if callable(fn) is False:
            raise RuntimeError('OP_NAMES 里的 op 未定义: ' + name)
        mcp.tool()(fn)
        fns.append(fn)
    return fns
