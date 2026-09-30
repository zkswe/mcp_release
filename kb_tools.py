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
# 整机自检 + 缺陷单（2026-09-29）：实现层单列（采集/渲染长逻辑不在本文件），kb_tools 只做工具面封装
try:
    import selfcheck_tools as sc
except Exception as _e:
    sc = None
    _SC_ERR = repr(_e)
else:
    _SC_ERR = ''
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
MCP_VERSION = '0.27.129-open'
MCP_BUILD = '2026-09-30'
# compact 模式下每条特性截断长度（v0.27.87）：条目越写越长，不截断就会把默认返回体撑成 token 炸弹
# （契约用例 test_compact_default 盯 6000 字上限）；完整条目仍能通过 compact=False 拿到。
COMPACT_FEATURE_CHARS = 700


def _clip_feature(text, limit=None):
    """compact 用：把长特性条目截断到 limit 字（尾巴标「…」+ 指路 compact=False）。"""
    limit = COMPACT_FEATURE_CHARS if limit is None else limit
    s = str(text or '')
    if len(s) <= limit:
        return s
    return s[:limit] + '…（完整见 compact=False）'
MCP_FEATURES = [
    '2026-09-30: **真根因入库：「软渲染」要说清哪一段 + 两条旧限制的出处（字库预烘档位 / 内容区宽）** v0.27.129-open（钟工回传修订稿：`scale` 限制源自我方**自研字库只预烘有限档**；数值是**某工程 UI 的内容区宽**；**内存画布→屏幕是硬件合成**）——① `knowledge/devflow/custom-render-paths.md` §0-3 重写：**绘制进内存画布**那段代价取决于实现/面积（我方 `src/core/PgCanvas.*` 自研软件实现），但**内存画布→屏幕是硬件合成**（平台有 bitblt / 透明 α 混合 / 90° 旋转能力，实证 `ZKTextView::setBackgroundBmp()`+`setInvalid()`；`misc::bitmap_rotate` 只支持 90° 整数倍）⇒ **不要把“我们的实现是软件”说成“平台只能软渲染”**；平台真做不到的是**任意角度旋转位图**（先例 `components/vinyl`）。② 脚注三条旧说法给出**真根因**：`scale` 那条 = **自研字库预烘档位需编译期常量，超档位走位图放大=拉伸**（资源侧约束，**画布对 scale 无限制**）；宽度数值 = **某工程 UI 内容区宽（屏宽−2×16 的布局值），不是任何限制**；动画计时用绝对时间基准（原话“绝对时钟”）。③ `render-extension-boundary.md` §3/§5 同步：限制表新增「平台做不到的事（任意角度旋转位图）」与「资源侧约束 vs 平台限制」的分离。④ 检索组重测保持全绿（16 组 / 111 问法）。v0.27.129-open',
    '2026-09-30: **撤回误测数值：视频图层只保留定性口径（不超过屏幕区域）** v0.27.128-open（钟工：「448 限制你去掉，这个应该是误测。全志平台就只有一个视频图层尺寸不能超过屏幕区域的问题」——第三次校准，把数值彻底拿掉）——① `knowledge/devflow/render-extension-boundary.md` §5 改为**定性口径**：GUI 层缩放无限制（已定论）+ **视频图层尺寸不能超过屏幕区域**（全志平台唯一相关限制，**不挂具体数值**；早期具体数值系误测已撤回）+ 动画计时用绝对时间基准；§4 消歧同步（“canvas 宽度有上限”说法不成立）。② `custom-render-paths.md` 脚注同口径（保留「数值系误测已撤回」一句，防重入）。③ `v85x/videoview-transparent-window.md` §2 同步。④ `check_retrieval.py` 边界组把带过时数值的问法换成「视频图层超过屏幕区域会怎样」（12 条问法）。⑤ **知识纪律**：误测数值**不写成新口径的注释余留**，只留一句撤回标记（防止日后又被当作实测值抄回去）。v0.27.128-open',
    '2026-09-30: **修正：GUI 层缩放无限制，448 是视频图层上限（钟工口径）** v0.27.127-open（钟工：「scale 在 GUI 层没有限制。是视频图层不能超过屏幕的宽度导致的」——接上一条渲染边界入库后的当场校准）——① `knowledge/devflow/render-extension-boundary.md` §5 重写：**删掉「画布文字 scale 只认编译期常量」的错误归因**（GUI 层缩放/文字绘制**无限制**），**把 448 归位到「视频图层不能超过屏幕宽度（V851s 屏宽 480 → 实测上限 448）」**；§4 术语消歧同步修正（「canvas 宽 ≤448px」说法本身不成立）。② `custom-render-paths.md` 脚注与总表同口径改写。③ `v85x/videoview-transparent-window.md` §2 在「位置/尺寸即画面显示区域」直接标上视频层超屏宽不对的实测值+出处。④ `check_retrieval.py` 边界组扩到 12 条问法（新增「视频图层尺寸上限」「GUI 层缩放有上限吗」，top-1 实测 9/12 → 阈值 8）。v0.27.127-open',
    '2026-09-30: **渲染扩展能力边界入库（三层模型）+ 修正「scale / 绝对时钟」类不当表述** v0.27.126-open（钟工：「回到 MCP 里面的描述，canvas 自定义画布和自定义控件这个知识库里面了解多少。MCP 是否存在一些描述问题，比如 scaler、绝对时钟之类的表述不当」→「修」）——① **新增权威口径篇 `knowledge/devflow/render-extension-boundary.md`**（能力边界的唯一表述）：FlyThings UI 三层 = **① 基础控件**（21 内置 + 自研 8，纯 json/ftu 配置）→ **② canvas 画布扩展**（`ZKTextView`/`ZKButton` + `setBackgroundBmp` 挂内存位图当画布：**只调一次** + `setInvalid(!isInvalid())` 交替刷帧；或 `ZKPainter` 在控件画布上直绘）→ **③ 自定义控件**（继承 `ZKBase`，组合基础控件或重写 `onDraw`）；结论 = **可覆盖任意不需要 3D GPU 的效果；GPU 风格效果可用软件模拟（软渲染/软光栅）达成；只有「必须真 3D GPU 实时管线（着色器/实时光栅化）」超出边界**（F133/Z21 无 GPU → 伪 3D / 软模拟；真 3D 仅 V85X disp 分层验证过）；附 `canvas` **三义消歧**（布局画布 / 内存画布 / 控件画布）。② **修不当表述**：`custom-render-paths.md` 脚注原写「文字绘制的 scale 必须是常量（变量不生效）、画布宽 ≤448px、动画计时必须用**绝对时钟**」——无 API 主体、无平台、单点外推，且「绝对时钟」与 `digitalclock` 数字时钟**控件**撞名 → 改写为可核对口径（`scale` 只认编译期常量＝V851s 单点线索；**内存画布**宽 ≤448px＝单点、成因未查、非平台规格；动画计时用**绝对时间基准（单调时钟 / 时间戳差值）**，不用帧计数或相对累加），并标 `needs_evidence: true` 待补判据。③ 联动修正：`framework-control-mapping.md` §3「3D」一行补「**或软件模拟（软渲染/软光栅）**」半句 + 指向边界篇；`custom-widget.md` 把 canvas 画布口径挂进「控件显示位图」一节并链到边界篇。④ 门禁：`scripts/check_retrieval.py` 新增「渲染扩展能力边界（三层模型）」组（10 条真实问法，含错说法「动画计时必须用绝对时钟吗」，top-1 实测 8/10 → 阈值 7）；`rag_index.json`/`kb_index.json` 重建；`kb_frontmatter --check` / `check_kb` / `kb_verify` / `check_retrieval` 全绿。v0.27.126-open',
    '2026-09-29: **知识库改造 P1：自动生长 + 可检索 + 可验证（骨架与门禁，工具数 40→42）** v0.27.125-open（钟工：「改造到后续用户基于这个开发后可以做到自动生长 + 可检索可验证」→「开工 P1」）——① **结构化元数据**：83 篇 knowledge 全补 front-matter（id/title/category/platforms/tags/status/confidence/verified_at/stale_days/evidence/origin/source）；历史文档先认成 `verified + confidence=manual + needs_evidence=true`，**第一次把「有多少结论其实没有可执行判据」显式记下来**；`scripts/kb_frontmatter.py`（幂等迁移 + `--check` 门禁）。② **机读清单** `knowledge/kb_index.json`（`scripts/gen_kb_index.py` + `--check`）：带 `meta{source_hash,doc_count,built_at,mcp_version}`（**不再靠 mtime 判新鲜**）+ summary（verified / 带证据 / 待补证据 / 无问法登记 / 超期 / inbox）+ 逐篇字段（sha256/fingerprint/hasQueries/ageDays）。③ **采集（增长入口）**：新 op `flythings_knowledge_capture`（风险 write）写**用户本地层**（`~/.flythings/kb_local/`，`FLYTHINGS_KB_DIR` 可改）或项目层（`<项目>/docs/kb/`）——**绝不写 MCP 安装目录**（版本物，升级会覆盖）；指纹去重（归一化标题+命令+平台）命中同主题 → 回 `duplicateOf` 提示**合并而非新建**。④ **回流（脱敏补丁包）**：新 op `flythings_knowledge_export`（kb-contrib-<时间>.json；IP/本机路径/凭据/主机名强制占位化，未脱敏须 `internal=True`）；总账只收过「去重 + 复验 + 问法登记」三关并由人签字的条目（**AI 不能自评通过**）。⑤ **检索闭环**：未命中/低置信落**用户本地层**日志（`_logs/no_hit.jsonl`）+ 返回体带 `gapLogged/gapHint`；`scripts/kb_gaps.py` 聚合出 `kb_gaps.md`（**用户真的问不到的东西 = 下一批写作清单**）。⑥ **验证闭环骨架**：`scripts/kb_verify.py` 按 evidence 真跑判据（`offline` 进 CI / `real-device` 走 `--device` / `manual` 显式不算通过），失败写回 `status=stale`。⑦ 门禁加 4 项（front-matter 合规 / kb_index 新鲜 / verified 必须有证据或显式待补 / inbox 不计入索引）+ 契约用例 `tests/test_kb_growth.py`；知识 `knowledge/devflow/kb-growth.md` 入库。v0.27.125-open',
    '2026-09-29: **自动化测试第二轮：多设备并行跑批 + 机读报告 + 像素基线库（工具数 39→40）** v0.27.124-open（钟工「先按照你的方案优化一轮，然后再复检」——这三项是我自己反查 open 版 MCP 时列出的测试侧 P0）——① **新 op `flythings_test_run(plan, devices, project_root, out, platform, parallel, baseline, allow_regions)`（风险 device）**：一份用例 JSON 在**多台设备并行**跑（此前多设备在线时工具一律「不猜」，只能逐台手敲 adb），每步结果**机器可判**：注入命令 rc / `logcat -d -s zkgui` 日志断言（expectLog/expectNoLog）/ 与像素基线逐像素对比；产出 `<out>/report.json` + **`<out>/report.xml`（JUnit，能直接进 CI）**；每台设备各自落 `shots/*.png` + `logcat.txt` 取证；`parallel` 控制并发度；**比不到基线记 no-baseline 并进 warnings，不算通过**（不静默放过）② **新模块 `ui_baseline.py`（像素基线库）** + **`flythings_ui_visual(action="baseline")`**：把「上一次验收通过的那张图」版本化存到 `<项目>/ui_baseline/`（`baseline.json` 索引 + 基线图 + 容差档案随基线存 + `_diff/*.diff.png`）；mode=save/compare/update/list；比不到基线报 `no-baseline`、尺寸变了报 `size-mismatch`（不许拿旧分辨率基线硬比）；判据与 ui_diff 完全同源（±2 容差 + ±1px 抖动补偿 + 噪声块归并）——此前只有「两张临时图比一比」，回归验收没有基线概念 ③ **`adb_tools` 补 `push()` / `shell_rc()`**（原来只有 `sh()` 只回文本、判不出 rc，无法做「注入失败=失败」的硬判据）④ 知识：`knowledge/devflow/device-test-run.md`（用例 schema/首次建基线流程/多设备并发注意/报告字段）+ `knowledge/devflow/capability-boundaries.md`（**能力边界清单**：open 版覆盖什么、哪些知识只在内部版、未覆盖怎么处置）⑤ 六方同步 + 契约用例 `tests/test_baseline_testrun.py`；真机验证：多台在线**并行**跑同一用例（含基线与报告）v0.27.124-open',
    '2026-09-29: **新增整机自检快照 + 缺陷单生成器（工具数 37→39）** v0.27.123-open（审查报告 P2-⑧⑨ / 钟工「1-3 按顺序做」第 3 项）——① **`flythings_selfcheck(device, diff_against, out)`（风险 device）**：一条命令出**整机快照九个分区**（设备信息/应用状态/显示/存储/网络/蓝牙/输入/外设/时间），每分区给 `{ok, hint, data}` —— **「读不到」本身是结论**：ok=false 时 hint 写明「需要什么条件 / 去哪查」，绝不静默吞掉；采集容忍设备缺工具（优先随仓 `bin_tools/<平台>/busybox` → 设备 /tmp/busybox，否则纯 adb shell + getprop/cat）；`diff_against=<上次快照.json>` 出逐分区逐项差异，`out=<json>` 落盘可复用为基线；设备参数带端口（`<serial|IP>:5555`），**多台在线不猜**（回 NO_DEVICE + 在线清单）② **`flythings_bugreport(title, project_root, device, symptom, steps, expected, actual, evidence, severity, out)`（风险 write）**：把「AI 产出的缺陷清单 + 真机判据」落成可提交 markdown，**格式对齐 2026-09-27 html2json A1~A8 那批**（标题 / 元信息 / 现象 / 复现步骤 / 期望 vs 实际 / 真机判据 / 证据 / 影响面）；真机判据自动附 型号·固件·build.fingerprint·应用状态（init.svc.zkswe / sys.zkapp.state / zkgui pid / uptime）·最近 `logcat -d -s zkgui` 末 40 行，采不到就写明原因；**evidence 里文件不存在 → 直接 EVIDENCE_MISSING 报错（不静默跳过）**；默认落 `<项目或MCP仓库>/temp/bugreports/<yyyymmdd-HHMM>-<slug>.md`，返回 path + 前 20 行预览 ③ 六方同步：`OP_NAMES` / `scripts/gen_manifest.py` 的 RISK·CATEGORY·STAGE / `mcp_server` 与 `README` 工具数 37→39 / `tools_manifest.json` / 意图闸门 `catalog.json`；新增 `knowledge/devflow/selfcheck-and-bugreport.md`（含检索导引）+ 契约用例 `tests/test_selfcheck_bugreport.py` ④ docstring 预算：长尾细节搬 knowledge/（html_to_json / build_ui_flow / ui_visual / device_screenshot / edit_ftu / pack_upgrade 六个 op 瘦身），总体仍 ≤12000。v0.27.123-open',
    '2026-09-29: **审查报告（MCP 更新审查-2026-09-29）P0 修复：包卡接进工具返回 + 门禁健壮性 + CHANGELOG 口径定死** v0.27.122-open —— ① **P0① 包卡进返回**：`package_tools` 新增 `package_card()`（读仓库 `packages/<包>/package.yaml`，yaml 缺失自动降级），`flythings_get_package_api` 返回体加 `card`（summary/entry/api/usage_cpp/gotchas/verified_* + cardPath/readmePath）、`list_packages` 加 `hasCard`、`query_package` 加 `cardSummary`/`hasCard` —— 之前 11 张卡 AI **取不到**（只读 registry），现在工具里直接可见；② **P0③ 门禁健壮性**：`lint_silent_except` 的 SKIP_DIRS 补 `.venv/venv/.fsc/.fun/toolchain`（原先扫到 .venv 报 650 条假红）、`check_consistency`/`smoke` 里「意图闸门 catalog 不在仓库内」「ui_tools 双份副本不存在」两条环境依赖检查**降级为 skip + 提示**（不再误报红）；③ **CHANGELOG 口径定死**：文件头改为「已冻结归档 ≤ v0.27.30」，版本史唯一来源指向 `MCP_FEATURES` + README（不再两套并存）；④ `packages/README.md` 补**包卡完整度状态表**（platforms.md/example/evidence 谁缺、谁待补，显式标注不许静默）；⑤ 新增契约用例 `tests/test_package_cards.py`（卡可解析 + 已接进工具返回）。v0.27.122-open',
    '2026-09-29: **依赖包「用法文档」体系 + 网络类包 Z20 真机全流程验证** v0.27.121-open（钟工：用这个面板把网络相关的 API 做好验证，就用平台上面的组件包；说明不完整的在本地 mcp 目录下做好 yaml 说明；源码可在本地 git 搜 lib-<包名>）——① **新增 `packages/<包>/` 文档体系**：机器可读 `package.yaml`（头文件 / API 签名与出处 / 依赖 / 可直接粘的用法 / 坑 / `verified_*` 真机结果）+ 人读 `README.md`（+ `platforms.md` / `example/` / `evidence/`）；首轮覆盖 `zkhardware`(3 路继电器 by zeroOutput + 背光)、`zknet`、`curl-cxx`、`ntp`、`mqtt-cxx`、`paho-mqtt3as`、`cares`、`mbedtls`、`openssl`、`rapidjson`、`curl`（未上真机的一律 `verified: null`，不冒充实测）；② **验证工程**：`projects/pkg_zknet`（WiFi 九键 + 自检 AUTO）、`pkg_netstack`（HTTP/HTTPS/NTP/MQTT）、`pkg_netstack2`（MQTTS/LWT/Downloader/WebSocket/热点/以太网/4G）、`pkg_netdir`（c-ares/mbedTLS/OpenSSL 直调）——全部「脚本注入触摸 + `logcat -d -s zkgui` 取证 + fb 截图」自动跑；③ **Z20(108) 真机结论**：WiFi 开关/扫描/连接/断开 6/6、HTTP GET/POST/HTTPS、Downloader 双任务(进度回调,307200B+81B)、WebSocket 回显、MQTTS(TLS test.mosquitto.org:8883)、LWT 遗嘱（`kill -9` 异常断线后 **~2s broker 代发**）、异常断线自动重连（cause=automatic reconnect，≈10.5s）、c-ares 解析(5 域名 30~88ms)、mbedTLS/OpenSSL 直调 TLS+GET(200 OK)、Ethernet configure/setAutoMode、SoftAp setEnable 开关、4G=本板无模块；④ **新坑入档**：`cacert.pem` 只认 **资源目录(resPath)** 下（放别处报 `not correctly signed by the trusted CA`，那是没找到 CA 不是证书坏）、Z20 的 `paho-mqtt3as` **必须配 openssl**（否则链接报 BIO_read/RAND_bytes/SHA1_* undefined）、**别连续快速 `setprop ctl.restart zkswe`**（旧实例没退干净 → MI 全局 init 锁被占 → 黑屏 + 进程 D 状态 kill -9 无效，只能断电）、取证用 `logcat -d -s zkgui`（zknet 事件线程刷屏会把我方日志挤出缓冲）、MQTT 见证端连 `127.0.0.1:1883`（宿主访问自身 LAN IP 会被拦）；⑤ **Z21（SSD21X / 1024×600 / 192.168.x.x）复验**：HTTP GET/POST、NTP 校时、HTTPS、Downloader 双任务、WebSocket、SoftAp、Ethernet 全通 —— **新增两条 Z21 专属坑**：**Z21 上电 RTC = 1970** → 带证书校验的 HTTPS 会报 `certificate validity starts in the future`（**必须先校时再 HTTPS**，Z20 时钟本来就对所以没暴露）；**Z21 没有 `/mnt/sdnand`**（只有 `/mnt/extsd`、`/mnt/usb1`）→ 落盘走 `/data/`。**Z21 registry 无 mqtt-cxx/paho-mqtt3as，MQTT 两项在 Z21 上无法验**；⑥ **同批入 `demos/` 六个真机验证工程**（`net-stack-verify-z20` / `net-stack-advanced-z20` / `net-wifi-verify-z20` / `net-stack-verify-z21` / `net-direct-tls-z20` / `hw-relay-verify-z20`，源级交付、IP 脱敏）+ `knowledge/devflow/package-verify-playbook.md`（验证套路：worker 线程 + 自检 AUTO 键 + 触摸注入 + `logcat -d -s zkgui` 取证 + framebuffer 截图 + 部署纪律 + 主机侧测试设施） v0.27.121-open',
    '2026-09-28: **fun.exe 换代（fun→fsc）+ MCP 兼容 `.fsc/` 新目录** v0.27.120-open（钟工：fun.exe 需要替代，不然会导致这个说明实际不起作用）——① **换代**：`toolchain/fun.exe` 换成厂家 `v0.0.2+2609281006_e09dc96`（37,757,440 B，sha256 `457F1AB2…`；旧版 `v0.0.2+2609032137_b8f28e3` 备份在工作区 `private/fun_backup/`）；② **新版带来的改名（实测）**：内部包名 `fun`→`fsc`；**产物目录 `<项目>/.fun/<平台>/` → `<项目>/.fsc/<平台>/`**；锁 `.fun-lock.json` → `.fsc-lock.json`；home `~/.fun` → **`~/.fsc`**（注册表/工具链/tools 都在里面，env `FSC_HOME_PATH`）；编译宏新版**同时定义 `FUN_BUILD=1` 与 `FSC_BUILD=1`**（老工程不用改）；③ **MCP 两代都认（只扩兼容、不改行为）**：`project_tools` 新增 `BUILD_DIR_NAMES`（`.fsc`/`.fun` 两代目录）与 `_find_build_artifact()`（bin 产物 / libzkgui.so / update.img 双目录找），设计走查跳过名单加 `.fsc`；`package_tools` 注册表候选加 `~/.fsc/registry/public`（排在 `~/.fun` 前）、`.fsc-lock.json`+`.fun-lock.json` 都读、框架头证据扫两个目录；`font_tools` 探针缓存优先 `~/.fsc`；`.gitignore` 加 `.fsc/`/`.fsc-lock.json`；④ **实测**：新版 `fun build -p z20`（DownloadTimerTest）产出 `.fsc/z20/libzkgui.so`；`flythings_build_ui_flow(with_launch=False)` 全流程 success（install/build/font check/verify 全过）；⑤ **文档**：`knowledge/devflow/cli-fun-toolchain.md` 头部加 09-28 改名块 + §1 表（宏 / 产物目录 / 注册表）按新名改写并保留旧名对照；⑥ **本机待办**：`FLYTHINGS_FUN_DIR` 指向机器级安装 `C:/zkswe/fun`，那份还是 `v0.0.2+2608251010_25e6cc9`（8/25），且被 6 个卡住的 `fun.exe` 进程占着（create/publish/login，非本次流程所起）→ 暂未换，需要时先清进程再换。v0.27.120-open',
    '2026-09-28: **多设备在线时「把工程推到指定设备」三测定稿：fun 新旧版都没修 + 我方垫片走通** v0.27.120-open（钟工：先只测试多设备接入时可以推送到指定设备的功能；可以了后 MCP 也只描述这个问题）——① **三测结论**：多设备在线时 `fun launch`（**09-28 新版 `v0.0.2+2609281006_e09dc96` 与旧版行为一致**）不管带不带 `-s` 都 `FATAL "host:transport <serial>" FAIL: more than one device/emulator`；② **报文级根因**：fun 自带 Go adb 客户端发旧式 `host:transport <serial>`（空格分隔），platform-tools（37.0.1 与 31.0.3 一样）只认 `host:transport:<serial>`（冒号）→ serial 被丢 → 多设备必失败（裸 socket：空格 → FAIL / 冒号 → OKAY；伪 adb host server 抓包脚本 `temp/fake_adb.py` + `temp/_adb_wire_test2.ps1`）；`-s` 本身是生效的（解析/校验 + 纯 IP 自动 adb connect 都有，但不支持序号）；③ **走通路子**：新增 `scripts/adb_transport_shim.py`（在 5037 把空格改写成冒号，转发给另起端口的真 adb），实测 **5 台设备在线**时 `fun launch -p z20 -s 192.168.x.x:5555` → 4.02 s 推完、设备侧 md5 与本地构建产物逐一致（main.ftu / libzkgui.so / images）、另一台在线设备（71）未被触碰；④ 知识库 `knowledge/devflow/cli-fun-toolchain.md` §7 按此重写；`adb_tools.multi_device_hint` / `fun_multi_device_error` 两条 AI 侧提示同步（①垫片 ②让 adb 列表只剩一台）；⑤ 本次**未替换** MCP 里的 fun.exe（新版另有大改：内部包名 fun→fsc、产物目录 `.fun/`→`.fsc/`、lockfile `.fsc-lock.json`，与本问题无关，替换与否待定）。v0.27.120-open',
    '2026-09-28: **setprop 重启方案真机验收（10/10）+ 三个组件的“�回重启后触摸不响应”已知限制勘正** v0.27.120-open（钟工：看着新的 setprop 方案验收）——① **验收做法**（Z20 `192.168.x.x`，480×480，钟工指定主测机）：每轮 `setprop ctl.restart zkswe`（**全程无 kill**）→ 等新 pid → 抓「时钟待机页」→ `/tmp/touch tap 240 240` → 抓「控制面板页」→ 帧差；**结果 10/10 PASS**：pid 每轮换新（1233→…→2332，每轮 0.7–0.8s）、每轮触摸都生效（帧差恒 230400 px = 480×480 整屏），**无一轮“命令成功、应用不响应”，不需要重启板子** ② **勘正三个组件**（`components/ui_v1/Calendar`、`Chart`、`_mapping/TabView`）的 `platforms.md` 已知限制 + `Calendar/example/README.md` 的设备坑：原写“反复 `kill -9 zkgui` 后触摸注入不响应、重启板子才能恢复”→ 现改为“那是 kill 的后果（框架口径：init 托管、不能 kill），改用 setprop 后未复现”，并带本轮 10 轮数据 ③ `knowledge/devflow/device-deploy-budget.md` §5 补实测验收段（含脚本/证据路径）④ 验收脚本与证据：`temp/setprop_accept.py` + `temp/setprop_accept/`（`RESULT.md` + 20 张逐轮截图）⑤ 提醒：三个组件原版验收是 Z21（1024×600，`192.168.x.x/207`），本次 Z21 **离线**，故先做了“重启机制”层验收（组件那条已知限制说的就是本机输入子系统重启后状态）；组件本身逐页像素复验待 Z21 回网再补。v0.27.120-open',
    '2026-09-28: **重启应用统一改 setprop（框架口径：应用由类 init 服务托管，不能 kill）** v0.27.117-open（钟工：框架设计有类 init 服务，不能 kill 程序，用法 setprop 的方式控制程序；让确认异常是不是自造 kill 导致的）——① **工具侧检查结果**：MCP open 本体**没有主动 kill 的调用点**（`adb_tools.restart_app()` 无任何 op 调用），`fun launch`（厂商 CLI，`build_ui_flow` 调它）二进制里只用 `ctl.restart`+`zkswe`+`setprop`（**无 kill**）；真正 kill zkgui 的是工作区早期临时脚本/示例（`temp/` 下 `kill -9 zkgui`、`busybox killall zkgui`、`tools/deploy_f133.py --kill`、旧 `deploy_z21.py`）② **`adb_tools.restart_app()` 重写为 setprop 优先**：默认 `setprop ctl.restart zkswe` → 轮询等新 pid（≈6s），返回 `{found, oldPid, newPid, method, restarted, detail}` 可取证；`kill -TERM` 仅在 `allow_kill=True` 时作兜底（个别板 setprop 静默失败），**永不 -9**（原「温和终止优先」是当时因果未确证的防御性猜测，现按框架口径作废）③ **文档口径升级**：`knowledge/devflow/device-deploy-budget.md` §5 改写为「走 setprop 让 init 控制（不要 kill）」（含 fun launch 内部机制、历史教训、掉网处置）；`deploy-scene-map.md` 指针同步 ④ **组件侧纠偏**：`components/ble/platforms.md` 抢串口改 `setprop ctl.stop zkswe` → 测完 `ctl.start zkswe`（原来写的 `killall zkgui`，而 init 会立刻重生）⑤ `tools/deploy_f133.py` `--kill` → `--restart`（旧名保留但提示废弃，实际走 setprop + 等新 pid）⑥ 口径一句话：**「重启应用」= `setprop ctl.restart zkswe`；要腾串口 = `ctl.stop`/`ctl.start`；kill 不在框架内。** v0.27.117-open',
    '2026-09-27: **html2json 一批静默缺陷修（A1~A8）+ 属性三表入库**（钟工转发 PocketGame《框架缺陷与踩坑清单-2026-09-27》，逐条对源码核实后开修）v0.27.116-open——① **A4 edittext 漏写 `touchable/visible`**（button/seekbar 都写了，唯 edittext 分支漏）→ 输入框可见、有底色与提示词，但**点了完全没反应、IME 不弹**（极易误判成「IME 没注册」）；② **A2 纯黑 `#000000` 被当「未设置」**：`to_dec(...) or 默认值` 共 16 处（data-color/data-color2/data-bg/data-bg2/data-text-bg/data-hint-color/clockColor）→ 新增 `_color_explicit()` **按「属性是否出现」判定**（原来是按「值是否为 0」→ 0 是 falsy，纯黑被换成默认色，实测「绿底白字」对比度 1.44:1；**老工程 `#010101` 绕过写法继续有效，不必回改**）；③ **A6 有图控件的圆角外底色**：新增 `_corner_bg()`，口径 = **`data-bg` > 最近祖先容器底色（window 的 `__bg`）> 引擎缺省 + 告警**（原来有图一律 `pop(bgColorTab)` → 四角取引擎缺省黑底，坐卡片上的圆角图标四角发黑；⚠️ bgColorTab 只管最外 1px，里圆角那几px在图里）；④ **A5 新增 `data-visible`**：直通 json `visible`（支持控件/容器/subItem/window；旧版不认该属性 → 初始隐藏只能靠运行期 patch，控件名要在生成器与 patch 两处同步，漏一处即静默失败）；⑤ **A1/A8 不再静默**：新增 `_Ctx.warn()`（去重），丢字符（emoji/黑名单字）、有图无底色、文本最小宽超容器等全部进返回体 `warnings[]`；⑥ **A7 统计/遍历含嵌套**：`flythings_ui_preview` 的 controls 改全量（另给 `controlsTopLevel`/`controlsNested`，原来 50 控件页面报 `controls: 1`）、`gen_ui_test` 递归收集嵌套控件并**按父偏移累加绝对坐标**（原来只扫根层 → 弹窗/键盘页可测控件为 0）；⑦ **A3 subItem 认 `data-bg`** → `bgColorTab.color0`（不写 = -1）；⑧ **A8 三表入库**：「属性直通 / 丢弃 / 默认值」三张对照表进 `ui_tools/HTML_SUBSET.md` + `knowledge/devflow/html-subset-quickref.md` §4.1（原来只能靠真机反推）；真机验收：108（Z20 板）逐项上屏核对；v0.27.116-open',
    '2026-09-27: **真机视频层抓帧支持指定 vdec 通道（多屏拼接拼墙抓不到视频帧的修复）**（钟工：交付整机说明书时 `layer="video"` 抓不到拼墙画面，只能手工 `zkshot <out.raw> vdec 1 0`）v0.27.115-open——① **缺陷**：`flythings_device_screenshot(layer="video")` 内部把 vdec 通道**写死为 chn 0**，而多屏拼接（SmartPanel_HA）的拼墙播放器（mi-module h264_player 移植版）在 **chn 1** → 取帧失败（另注：Z20 屏保 zkmedia/ssdvideoplayer 是 FFmpeg 软解、**不建 MI VDEC 通道**，所以「chn 0」只是默认取帧口径，chn 0 抓不到不一定是工具问题）② **新增参数 `vdec_chn`（int，默认 0，向后兼容）**：仅 layer="video" 生效，映射到 `zkshot <out.raw> vdec <chn> 0`（多路/拼墙必须指定，**拼墙在 chn 1**）；也可走 advanced（`{"layer":"video","vdec_chn":1}`）③ **报错可诊断（不再静默）**：取帧失败/空帧/pull 失败/解码失败都返回 `vdecChn`（实际用的通道号）+ `device` + `zkshotCmd`（还原后的命令行）+ `hint`（chn 0/1 各是什么、怎么换通道），warnings 里带 zkshot 原始输出 ④ CLI 补齐 `--layer ui|video` + `--vdec-chn N`（原来 CLI 根本没法抓视频层）⑤ 长尾口径入 `knowledge/devflow/device-screenshot.md` §4.1（含 `tools/zkshot` 的 `[vdec|disp] [chn] [port]` 三参口径与实测背景）；v0.27.115-open',
    '2026-09-27: **倒角/描边「变粗」口径 + EasyUI.cfg 劫持 + easyui 版本→控件可用性三件套入库**（钟工：「多屏拼接里面几个图片的倒角线变粗了，这个问题以前 MCP 应该修复过的。你再检查下 MCP 如果说明不够明显就修改」）v0.27.114-open——① **`knowledge/devflow/ui-asset-rules.md` 新增铁律 #13「倒角/描边『变粗』与同族一致性」**：症状词表（倒角线变粗/描边比别的行厚/圆角发糊/弧线粗一档/与相邻行不一致/弧上 2px 实色带）→ 根因三条（整像素描边带的弧上 ~1.41px 已知代价 / FT-008 取整偏移 / 二值 mask 当 α）→ 唯一正确画法（≥4× SS + Image.BOX；`bordered_cov`=要描边、`rounded_rect_cov`=不要描边；禁二值 mask 当 α、禁亚像素混色）→ **同族同口径铁律**（一组行底/按钮底要么全带描边要么全不带，半径同令牌值）→ 自检命令（`corner_audit --arc-only --fail` / `--fail` / `aa_audit --fail` / `check_all` #21#22#25）+ 闸门盲区声明（#21/#25 都抓不到「弧上 2px 观感」与「同族不一致」）+ 图标家族一致性（改宽只平移、零重采样）② **`knowledge/devflow/package-properties-easyui-cfg.md` 新增「查找优先级：生效的可能是另一份 cfg」**：`/tmp` > **`/mnt/extsd`（可劫持程序）** > `/res/etc`；症状「推上去没效果/改了像没改」的判定两条命令 + `remount,rw` 改名处置 ③ **`knowledge/devflow/dynamic-screen-rotation.md` 新增 §4.1**：easyui 能力存在性三步判定（`.deps.lock` revision / registry `include/` / **设备运行库 `strings /lib/libeasyui.so`**）—— Z20 `scrollwindow` 在 2.6.0/3.0.0/设备库**全有**（不是版本问题）、`relayout` 需 ≥2.9.0；「控件看不到」排查顺序 5 步 ④ **`knowledge/devflow/upgrade-pack-image.md` §四点五 新增 6)**：`update.img` 上限 = res 分区（`0x720000` = 7,470,080 B）、无独立 zkupgrade、md5 判据；v0.27.114-open',
    '2026-09-24: **固化升级 update.img 的 Z20 真机实操入库**（钟工：直接采用 update.img 升级——标准 FlyThings 升级方法，同步到 MCP）v0.27.113-open——①**知识补充**：`knowledge/devflow/upgrade-pack-image.md` 新增 §四点五「Z20 真机实操记录」：Z20 的 `/res` = `/dev/block/mtdblock3` **squashfs ro**（`touch` 直接 Read-only）、`fun launch` 推的是 `/tmp/ui` + `/tmp/font` + `/tmp/EasyUI.cfg`（`tmpfs`，**重启即清空**）、`/etc/init.rc` = `service zkswe /bin/zkgui` + `LD_LIBRARY_PATH /tmp:/lib:/mnt/extsd/lib:/mnt/sdnand/lib` ⇒ 重启后屏幕回到 `/res` 旧版 = 「页面不对」的真根因（调试推送 ≠ 固化升级）②**实测固化序列**（Z20，一次成功）：`flythings_pack_upgrade`（内部 `fun install && fun build && fun pack -p Z20 --release-version x -o out/update.img`，本次 1,913,404 B）→ `adb push update.img /tmp/` → `setprop sys.zkupgrade.flag 255` → `setprop sys.zkupgrade.dir /tmp` → `setprop ctl.restart zkswe` → 升级流程**自行整机重启**（~45 s）③**三步验收**：`cat /proc/uptime`（归零=真重启过）+ `ls -l /res/ui`（新工程页全部到位，本次含 album/brightness）+ `ls -l /res/font`（自家 HanSans 两档进了 /res），再 `flythings_device_screenshot` 交视觉模型确认页面 ④**字体要进包**：工程根 `package.properties` 写 `enable.font.location=true` + 工程 `font/*.ttf` ⇒ 写进 EasyUI.cfg 的 `font` 键并打进 update.img，设备侧落 `/res/font/`；工具在「设备无字库」时会**自动往工程投 `font/zkswe-hans-common.ttf`**，自带字体的话用完记得删（本次已删）⑤**反面教材**：`/mnt/sdnand/app/{ui,lib,font,tr}` 与 0 字节 `/mnt/sdnand/EasyUI.cfg` **不是**升级路径（`init.rc` 不从那儿起应用），别自己铺目录猜启动方式，统一走 `update.img` ⑥定位手法：分清设备跑的是哪一份——`/tmp/ui` 有内容=调试态、`/res/ui` 是新页=固化态；v0.27.113-open',
    '2026-09-24: **小程序传图/视频对接方案入库（相册传输模式）** v0.27.112-open（钟工：`小程序传输对接指南.zip` 是相册传输模式下的对接方案，已在其他产品上验证过，先入库、开干后再用）——① **知识文档**：新增 `knowledge/devflow/mp-transfer-miniprogram.md`（协议速查表 / ACK 规则 6 条不可改边界 / 设备端实现要点（广播与 `handleClient` 代码摘录）/ 移植清单（`base::Task`/`MP_PATH`/媒体缓存怎么替）/ PC 模拟验证 / 协议边界 / 12 条联调清单 + 检索词）② **源码归档**：新增 `components/mp_transfer/`（`README.md` 协议速查 + `src/mp_transfer/broadcast_task.{h,cpp}` · `tcp_receive.{h,cpp}` · `runtime_coordinator.h` + `src/system/transfer_type_and_data.h` + `src/python/receiver.py`（PC 模拟设备端，纯标准库）+ `docs/miniprogram-transfer-guide.md` 指南全文；示例 IP 已做占位符化，过隐私闸门）③ **口径要点**：设备主动 UDP 广播 `255.255.255.255:8899`（每 ≈2 s，正文 `zkswe:<设备名>`，无换行）→ 小程序用报文来源 IP 连 TCP `9000`；包头 `type(uint8)+len(uint32 大端)`，文件包再接 `nameLen(uint16)+filename(UTF-8,1..256B)` + 文件体；32 KiB 分块，**非末块**回 `ACK <累计字节>\n`、**末块**校验落盘后回 `OK\n`（≤32768 B 无分块 ACK、整数倍同理）；设备端 socket 阻塞超时 2 s（**不是整文件限时**）；一个连接可连续收多文件；先写 `.tmp` 再校验改名；**无版本协商/认证/CRC/断点续传，仅适合可信局域网**；落地目录 = 原工程 `config.h` 的 `MP_PATH`（移植换自己可写目录、末尾带 `/`）④ 实测依据：`F133UhaleAlbum` 设备端提交 `39c25c1`（2026-09-24），附带 Python 接收端已由项目维护者用**上线小程序**验证通过；v0.27.112-open',
    '2026-09-24: **Z20 升级实跑走通 + 固化后卡 logo 根因入库（钟工：把 Z20 升级跟程序基础的问题入库）** v0.27.111-open——'
    '① **ADB 正常升级 6 步（现行口径）**：`push update.img /tmp` → `setprop sys.zkupgrade.flag 255` → `setprop sys.zkupgrade.dir /tmp` → '
    '`ctl.stop zkswe` → `umount /mnt/extsd`（extsd 没挂时报 `Invalid argument` = 无害）→ `ctl.restart zkswe`；真机：0.23 s 返回 → '
    '~50 s 回网，**写入面 = `mtd3(res)`**（由包名 `update.img` 决定），`mmcblk0p1`/`mtd2`/`mtd5` 全不动；'
    '② **固化后卡开机 logo 的根因**：应用必须设 `sys.zkapp.state=running`（`onUI_init()` 里 `SystemProperties::setString`），'
    '且**别用 `fun create` 的 fv 骨架（无 `Manifest.xml`）——第一个界面不创建、钩子不执行 → 属性必空**；换带 Manifest 的模板风工程'
    '（`flythings_create_project`）立即上屏；③ 字体随包要放**工程 `resources/`**（放 `ui/` 会被忽略，`fun pack` 只吐 `no any font`）'
    '+ `EasyUI.cfg={"font":"/res/ui/fzcircle.ttf"}`；④ 排查手法：`onUI_init` 里附设 `sys.zkapp.dbg` 标记 + `fb0` 纯黑/均匀=应用层没画；'
    '知识 → `knowledge/hardware/z20-86panel-upgrade.md` §11/§12、`knowledge/devflow/package-properties-easyui-cfg.md`',
    '2026-09-23: **Z20 86 面板升级链路入库（钟工：「只用真机验升级功能 + 型号特殊点落 MCP」）** v0.27.110-open——'
    '①**硬件型号库补 Z20/86 面板（SW48480040D1）升级与系统特殊性**（改数据源 `hardware_catalog.json`，不是改生成物）：'
    '升级程序是**系统件**（`/lib/libzkupgrade.so` + `libeasyui` 的 `UpgradeMonitor` + `libinternalapp` 的 `UpgradeActivity`、'
    '`/system/res/internal/zkupgrade.ftu`），app 不用自己写升级逻辑；三条触发正路 = ①卡/U 盘根目录放 `update.img|extupdate.img` + 重上电'
    '②同目录加无后缀 `zkautoupgrade`（默认 2 s 自动开升，配 `zkrebootdelay`，`-1`=不重启）③ADB 三属性 `sys.zkupgrade.dir` + '
    '`sys.zkupgrade.flag 255` + `setprop ctl.restart zkswe`；'
    '**包与机型绑定**（572 B 头 + 魔术 `ZKSWEV1.0-180127`，0x1C=payload 字节数，0x35 起机型 magic：Z20=`0xaa550404`、'
    'Z21=`0xaa550606`、V85X=`0xaa550a0a`、F133=`0xaa550707`，跨机型刷会被 `sys_upgrade_type_no_match_error` 拒）；'
    '数据面 `/dev/block/mmcblk0p2 → /mnt/sdnand`（**app 自挂载** ext4，挂不上就 `make_ext4fs` 整盘重建）、'
    'LOGO/MISC = 本板 mtd5 = 128 KB；'
    '②**新知识条目 `knowledge/hardware/z20-86panel-upgrade.md`**：升级链路 + 包字节结构 + **`release.ext4` A/B 实证**'
    '（`release.ext4=true` → 产物名变 **`extupdate.img`** 且包内 `/res` 是 **ext4** 镜像、出包时自动装 `make-ext4fs`；不写 → `update.img` + squashfs）'
    '+ 8 条坑（含「ADB 触发固化后整板失联」的真机遭遇）+ **不依赖网络的卡/U 盘救援步骤**；'
    '③**`release.ext4` 首次入库**（此前官方 wiki 与本库逐处 0 命中）——它才是「U 盘 extupdate.img / TF 卡 update.img」包名差异的**真正来源**（按介质命名是错的）；'
    '④纪律：写入目标分区/去重记录 `/data/.zkugraderec`/`release.ext4.size`/`release.ext4=false` 后果 等**没验到的点在条目与型号库里显式标「未证实」**，不写成结论；v0.27.110-open',
    '2026-09-23: **列表封面「已解码位图」缓存入库（钟工：「把列表图片 ImageCache 这个方法正式入库 open 版 MCP」）** v0.27.109-open——'
    '①**组件 `components/imagecache/`**（源码型四件套，核心零依赖）：`zk::ImageCache` = 单例 + `acquire()/release()` 引用计数 + 权重 LRU（与 HaishiM9 逐行同义）+ `capacity`/`pathMaxLen` 参数 + 日志钩子 + `hits()/loads()/slots()/evicts()/fails()` 读数；'
    '装载/释放**回调注入**（FlyThings 上是 `BitmapHelper`，别的宿主自己给），于是同一份代码在设备与 PC 上都能编；PC 自测 29 项 0 FAIL（llvm-mingw g++ 与 Linux g++ 双测，含「固定名封面 → 串图」复现与 LRU 淘汰可指名验证），接线样板 `example/flythings_wiring.cc`；'
    '②**知识条目 `knowledge/uicontrols/listview-image-cache.md`**：病症判据（单张解码真机 280x280 圆角封面 26~65ms、64x64 小图 3~4ms，全落在 UI 线程）、机制（`BitmapHelper::loadBitmapFromFile` 把位图登记进框架资源表并持有 → 不 unload 就复用、不再解）、'
    '**两件套修法**（①先降尺寸：取图尺寸严格 == 显示盒 ②再上 ImageCache，缺一不可）、真机数字表（回页重设同一批 **315ms → 1ms**、回页合计 **524 → 206ms**、首解 211→208ms 不加速、拖动 0 解码）、8 条坑、验收口径（`loads()` 增量 = 解码次数）；'
    '③**硬约束**：缓存键 = 路径，**路径必须唯一（含批次/版本）**——固定名封面换内容会命中旧图（串图，真机复现并修）；禁抄 HaishiM9 `releaseAll()` 末尾的 `system("echo 3 > /proc/sys/vm/drop_caches")`（全局副作用 + UI 线程 fork 本身就是卡顿源）；'
    '多页共用要引用计数；容量是内存换速度（`capacity` × 单图解码体积），Z20/Z21 那类 36~128MB 内存板别照抄 128；'
    '④**互链**：`listview-fields.md`（封面卡专节）、`devflow/reusable-components.md` §9、`components/README.md` 模块表；`scripts/check_retrieval.py` 的对照组加 2 条封面缓存问法防检索退化（实测对照组 12/13 → 14/15）；'
    '出处 = HaishiM9 `src/logicSelf/imageCache.h`（上游）+ `projects/iOSStyle-F133/src/core/ImageCache.hpp`（真机验证版）。',
    '2026-09-22: **vinyl 组件补齐「标准示例页」（钟工：「直接补上，不需要单独验证，纯粹标准化的代码」）** v0.27.108-open——'
    '`components/vinyl/example/` 从「代码片段」补成可直接拷用的标准示例：'
    '`example/demo/ui/vinyl_demo.json`（1024x600：320x320 正方形占位控件 + 播放/暂停・切后端・换封面 三按钮 + 诊断行，字段按铁律 #5 显式写全）'
    '\+ `example/demo/src/vinyl_demoLogic.cc`（attach/setCover/定时器 tick/setPlaying/detach + 三按钮回调 + 每秒诊断行，回调名与 json caption 一一对应）；'
    '`example/README.md` 写明「拷进任意工程两步 + fui pack + fun build」与判据（自转/暂停/切后端/换封面/诊断行）。',
    '2026-09-22: **黑胶旋转沉淀为可复用组件 `components/vinyl/`（钟工：「多产品会复用这个功能，我需要把他做成可以复用的功能点」）** v0.27.107-open——'
    '①**源码型模块四件套齐**：`README.md`（用法/API/依赖/8 条真机坑/验收口径）、`platforms.md`（F133 双后端实测：定点 6~12ms、nanovg 23~44ms；其余平台标未验证）、`Manifest.xml`、`example/README.md`（json 占位 + 页面三步 + 定时器驱动片段）；'
    '②**自包含化**三个依赖：旋转本体 `zk::VinylSpin`（`include/zk/zk_vinyl.h` + `src/zk_vinyl.cpp`）、后台单线程队列 `zk_vinyl_worker`、正圆覆盖率表 `zk_vinyl_circle_mask`（SS=8 面积平均，与静态圆封面同源）；'
    '③**工程已切到组件副本并真验证**：`projects/iOSStyle-F133/src/zk_vinyl/`（旧 `src/core/VinylSpin.*` 删除），`fun build -p F133` 0 error、真机跑通（播放页黑胶出帧刷新）；'
    '④登记：`components/README.md` 模块表加 vinyl 行 \+ `knowledge/devflow/reusable-components.md` §8（含“只有降分辨率/降帧率能省 nanovg 成本”与 `setInvalid(!isInvalid())` 刷新口径）。',
    '2026-09-22: **seekbar 滑块口径入库（钟工：「进度条的滑块为什么做成这样扁的？什么关键词影响了你生成 / 需要什么关键词才能生成圆滑块」）** v0.27.106-open——'
    '新增 `knowledge/uicontrols/seekbar-fields.md`：①字段全集（position/max/defProgress/orientation/backgroundPic/progressPic/thumb.size/thumb.normalPic+pressedPic/touchable + 三个回调/API）'
    '②**实测铁律（官方未收录）**：滑块形状**只由图片决定**（json 无“圆/胶囊”关键词），但**渲染高度会被控件盒高度压**——'
    '24×24 正圆图 + 控件 `height=12` → 屏幕上实测 **24×12 扁椭圆**；把控件盒加高到 28（轨道图也 28 高、可见条 12px 居中）→ 实测 **24×24 正圆**（逐行 4/16/20/22/24/22/20/14）'
    '③出图口径：正圆 = `gen_res.rounded_rect_cov(w,h,w/2)`（覆盖率抗锯齿）；禁无 AA 的 flat-圆角画法（原图 alpha 只有 0/255、半径 11 的圆角方块）'
    '④HTML 侧关键词：`data-thumb` / `data-thumb-pressed` / `data-thumb-size`（html2json.py:1732-1744，缺省 24）'
    '⑤反例含「改 json 用 sort_keys 重排 → 控件顺序=图层顺序被改 → 全屏铺底层盖住进度条」（本次踩过并已回滚重排）。',
    '2026-09-22: **自定义 view 刷新口径入库（钟工：「open mcp 优化指的是针对自定义 view、类似 gameview 这个部分的刷新的问题」）** v0.27.105-open——'
    '①新增 `knowledge/uicontrols/custom-view-refresh.md`（本类刷新的唯一权威口径）：`ctrl->setInvalid(!ctrl->isInvalid())` = 自定义 view/自绘帧刷新的**平台惯例** '
    '（gameview/GIF/地图/掌机显示层/WebView 容器全部这么写，逐条给了工程+行号出处）；`setInvalid(true)` = 禁用（会吃触摸，别拿来刷帧）；'
    '`setInvalid(!isInvalid())` vs `invalidate()` 四种写法的语义对照表；正确写法模板（位图只交一次 + 原地改像素 + 翻转 invalid）；省 CPU 优先级（先降帧率）。'
    '②**修掉一条会误导 AI 的真机结论**：`touch-events.md` §6 原来把「setInvalid 交替刷帧」限定为“仅限只读控件场景”，现按实测纠偏 + 补“非必要不碰 getAbsolutePosition”。'
    '③**新事实（真机实测，无参考判据）**：`invalidate(&rect)` 的 rect 是**控件本地坐标系**，传 `getAbsolutePosition()` 绝对矩形 → 被裁成“右下到右下角”那块 → **屏上只刷一块**；'
    '判据：源图半径 100 处放四个纯色方块、静态走 20°（理论位移 34.7px）——绝对矩形/NULL/面板系/+父偏移 = **0px**，整页/本地(0,0,w,h)/**setInvalid 翻转** = **33~35px**。'
    '④回链 `devflow/custom-widget.md`（§6 + 清单 #8）与 `touch-events.md` §6.1/§6.2；rag 索引重建。',
    '2026-09-22: **系统级窗口 / 自定义全局弹框知识入库** v0.27.104-open（钟工：「关于系统级页面 screensave/statusbar/navibar 以及自定义全局弹框（car 相关项目里面的 btcall 页面），这个你要让 AI 可以做到精准命中。**不要自己去创造页面的生命周期和层级关系**」）——'
    '①新增 `knowledge/uicontrols/system-windows.md`：内建 **4 类**系统窗口（statusbar / navibar / screensaver / IME）的'
    '**固定文件名 ↔ APP_TYPE（1/2/3/4）↔ REGISTER_SYSAPP 注册 ↔ 显示隐藏 API** 对照表（出处 = 官方文档 interaction/system_apps.md + app/AppTypeDef.h），'
    '`EasyUIContext.h` API 全集（show/hide/is/get、screensaver 超时与使能、showIME、load/unload 与 perform* 实测行号），'
    '屏保两种配置入口（代码 + EasyUI.cfg 的 screensaverTimeOut），「生命周期与层级只认这些」小节 + 6 条反例（如禁止 openActivity("statusbar")）。'
    '②新增 `knowledge/uicontrols/global-popup-window.md`：全局弹框/浮窗/来电弹框的**真实机制** —— '
    '工程自定义 appType（100/101/POPUPWND，甚至直接写 1000）+ `REGISTER_SYSAPP` 静态注册 + `SYSAPPFACTORY->create()/delete` + '
    '`src/logic/sysapp_context.{h,cpp}` 定时器转发（show/hide 落 UI 线程）+ 触摸命中 `is_hit_xxx`；'
    '含 car 工程两种真实做法：btcall 具名封装（`app::show_btcall_widget()/hide_btcall_widget()`）与「通话 UI 挂进 statusbar 页的 window（showWnd/hideWnd）」，'
    '并标明 `topmost` 等无公开条款处只照抄用法、不扩写解释。'
    '③两文档互链，并回链 `devflow/page-architecture-spec.md`（页面归属）、`touch-events.md`、`cross-thread-ui-rule.md`。'
    '④检索复核（新进程新索引、7 组真实问法）：目标文档 **5 次 top1 / 1 次 top2 / 1 次 top3**（脚本 `temp/verify_syswin_retrieval.py`）。'
    '⑤rag 索引重建 1581 chunks。⚠️ 运行中的 MCP 服务在导入时加载索引 → 需重启服务才会检索到新文档。',
'2026-09-21: **组件入库 `blur`（高斯模糊铺底）+ 播放页黑胶旋转新增 nanovg(AGG) 后端（A/B 实测：定点更快，nanovg 保留为可切换后端）** '
    'v0.27.103-open（钟工：「高斯模糊入库。旋转的可以用库里面的 nanovg 处理旋转」）——'
    '**① `components/blur/`（源码型，无第三方包依赖）**：对外只有 `include/zk/zk_blur.h`（纯 C ABI）：'
    '`zk_blur_bgra`（同尺寸）/ `zk_blur_prep`（铺底专用：cover 裁切+缩放+可降采样模糊+可放大回）/ '
    '`zk_blur_darken`（定点压暗）/ 档位 `AUTO|NAIVE2D|SEP_FLOAT|SEP_FIXED|BOX3|RVV`；'
    '真机 F133 实测：1280x800 铺底输出 320x200 缩图 **88ms**（RVV 71ms）、整链路（解码+模糊+上控件不落盘）**105~141ms**'
    '（对照 PNG 落盘 395ms）；`SEP_FIXED` 查表档在本平台**反而最慢**（33KB 核表打爆 L1，1280x800 实测 40539ms）→ `platforms.md` 写明「别用」。'
    '索引：`components/README.md` 模块表 + `knowledge/devflow/reusable-components.md` §7（API 摘要 / 实测表 / 已知限制）。'
    '**② 旋转双后端（`src/core/VinylSpin.cpp`）**：新增 nanovg 后端 —— `nvgCreateAGG` / `nvgReinitAgge` '
    '**直接渲染到我们自己的 `_bitmap_t` 缓冲**（不落盘、不进 GL），圆裁剪 + `nvgImagePattern` 贴封面 + `nvgRotate`，'
    '抗锯齿走 AGG 自带 edgeAntiAlias。**实测（同封面、12fps、同台板）**：定点 42.6% CPU / 每帧 7~11ms / 12.3~12.6fps；'
    'nanovg 59.8% / 25~42ms / 11.1~11.7fps → **默认仍为定点**（`VS_BACKEND_DEFAULT`；nanovg 一行切换，'
    '运行期建不起来会**自动回退**定点，不报错）。'
    '**格式坑（真机隔离探针实测）**：本包 AGG 后端只支持 `NVG_TEXTURE_BGRA` 目标，纹理格式必须与目标一致'
    '（否则 `Assertion failed: !"not supported format"`），`nvgCreateImageRGBA` 用不了 → 要用 '
    '`nvgCreateImageRaw(ctx,w,h,NVG_TEXTURE_BGRA,0,data)` 直传 BGRA 源（不用做通道交换）。'
    '证据与回滚：`temp/mu_vinyl/REPORT_NANOVG.md`、`temp/blur_component/REPORT.md`。',
'2026-09-21: **新需求「设计先行」硬闸门：没给设计稿就不许直接建工程（钟工口径 A）** '
    'v0.27.102-open（钟工原话：「如果用户没有提供设计的 UI 流程图和 UI 界面，AI 需要先进入原型设计，界面设计这个流程。」）——'
    '**根因**：意图闸门注入的工具目录是**平铺**的，`flythings_create_project` 排在第 6 行，'
    'AI 拿到「帮我开发一个新项目（智能家居面板…）」这类**新需求**最自然的动作就是直接建工程写代码，'
    '「设计稿先行」流程只活在 knowledge（靠 AI 主动检索才可能命中）。'
    '**① 意图闸门（tools/flythings_intent_gate/index.js）新增 `newproject` 模式**：'
    '本地正则判定「动作词（开发/做一个/写一个/实现/新项目/新需求/需求）+ 对象词（面板/界面/UI/App/应用/程序/项目/设备/屏/机）同现」'
    '即为新需求，权重足够单独触发（score 提到 6）；'
    '请求里出现设计图/设计稿/原型/线框图/wireframe/流程图/UI图/html/.ftu/.json/切图/标注/蓝湖/Figma/墨刀/axure 之一即视为已提供设计。'
    '**② 三种情形**：新需求 + 未见设计 -> 注入体**第一段**为「ⓞ 流程前置（硬约束）」，'
    '明确「必须先走完原型设计 -> 界面设计 -> 用户确认，禁止直接创建工程或写业务代码」，'
    '并给出五步（功能拆解+确认清单 -> 页面树+page-id -> 单 HTML 多页线框图 -> ui_preview 确认稿 -> 确认后美化/html_to_json/create_project）；'
    '新需求 + 已带设计 -> **不注入硬约束**，只提醒「先还原 + 出确认稿再 pack / 写逻辑」；非新需求 -> full/slim/meta 行为与改动前**逐字节一致**（零回归）。'
    '**③ 目录按阶段分组**（仅 newproject 模式）：`### 设计阶段（现在就该用）`（knowledge_search / map_control / read_json / layout_audit / '
    'get_project_spec / validate_project / ui_preview / html_to_json / ui_visual / generate_ui_assets）'
    '与 `### 确认后才用（建工程 / 编译部署 / 依赖）`（create_project 等）；'
    '分组数据来自 catalog.json 新增的 `stage` 字段（design/build/other，人工表在 scripts/gen_manifest.py，'
    '由 scripts/gen_gate_catalog.py 生成并纳入 --check 漂移检测），插件侧**不硬编码 op 清单**。'
    '**④ 软闸门（MCP 侧 kb_tools.py）**：`flythings_create_project` / `flythings_build_ui_flow` 只读检测项目目录内有无设计产物'
    '（design/ 目录、*.html、*.preview.html 等），没有就在返回体附 `warnings[]` 指引走 prototype-flow——'
    '**只加 warning，不改 success 语义、不阻断**。'
    '**⑤ 可检索性**：`knowledge/devflow/prototype-flow.md` 头部补检索词与硬口径（新项目/新需求/开发一个/需求拆解/原型设计/界面设计/'
    '设计稿/参考图/线框图/确认稿/智能家居/面板/屏保/温湿度/MQTT/情景联动）；'
    '`flythings_create_project` 与 `flythings_get_project_spec` 的 docstring 各加一句「新需求先出设计稿/原型并确认再建工程」'
    '（docstring 预算内，同时精简约 80 字历史噪音）。'
    '**⑥ 实测**：钟工原话 -> `mode=newproject score=6`，注入体含「流程前置/禁止直接创建工程/wireframe.html/确认稿/页面树/page-id」，'
    '且 create_project 只出现在「确认后才用」组（断言 70 项：`node tools/flythings_intent_gate/test.mjs`，含与改动前逐字节回归对照）。',
'2026-09-21: **口径反转：html2json 多屏缺省改成「每屏一个 json」（一个 .screen = 一个页面 = 一个 Activity = 一个 ftu），合成多整屏 window 变显式 `--merge-windows`** '
    'v0.27.100-open（钟工原话：「不是的，按照客户的设计需求，其实目前已经可以准确的做好了不同的 html 页面分页了。'
    '哪些属于不同的 activity 哪些属于 windows，dialog 其实前期 AI 可以分清楚。分清楚的情况下不同的 activity 做好不同的 json 布局就好了」）——'
    '**① 工具层（`ui_tools/html2json.py`）**：v0.27.99 的缺省（N 屏合成同一 json 的 N 个整屏 window）**做反了**，本条反转：'
    '缺省 = **每屏一个 json**（文件名取 `data-page`，缺省 `page_k`；输出目录 = output 参数所写目录 / html 同目录；'
    '单页仍写 output_json 指定的那个文件，与旧版逐字节一致）；`merge_windows=True`（CLI `--merge-windows`）才是'
    '「N 屏合成同一 json 的 N 个整屏 window」（`window__1..window__N` 连续编号，首屏 `visible:true` 其余 `false`，`caption=data-page`），'
    '**仅当这些屏同属一个 Activity（同 ftu 内整屏 window）**时用；退役的 `--split-per-page` 明确报错（exit 2，不许静默当缺省）。'
    '**同屏内部的 window/dialog（弹窗）不是页**（写在 `.screen` 里的 `div.window`/`div.modal`），工具不再把多个 `.screen` 合并成多窗口；'
    '归属由 AI 在设计阶段（HTML 原型）判定。'
    '**② 返回体**：`screensDetected`/`pagesProduced` 不变（不等一律 `success:false`），新增 `jsonsProduced`；'
    '`mode` 三值 `single-screen`/`per-screen`/`merge-windows`；**`pages[]` 逐页列全**（页名 + 各自 json 路径，修掉上一版 merge 形态只列 1 条的瑕疵）。'
    '**③ 防呆**：嵌套 `.screen` 从 error **降为 warning**（按最外层算页、内层容器忽略但屏内控件保留，warnings 点名）；`data-page` 重复仍 `success:false`（屏数核对）。'
    '**④ 文档三处统一**：`ui_tools/HTML_SUBSET.md`「多屏」节、`devflow/prototype-flow.md`「分页落地清单」（改成 AI 逐屏判定归属：不同 Activity -> 各自 json/ftu；同 Activity 的 window/dialog -> 同 json 内）、'
    '`devflow/page-architecture-spec.md` §0（删掉「默认一个工程一个 Activity」那条相反的默认）。'
    '**⑤ 实测**：2 屏 probe 缺省出 `home.json`/`detail.json`（每份与单独转该屏**逐字段一致**）；`--merge-windows` 出 1 个 json + `window__1/2`（首屏 visible）；'
    '真实 10 屏设计稿出 **10 个 json**；3 个真实单屏工程产物**逐字节 0 差异**。**⑥ 用例**：`tests/test_html2json_multiscreen.py` 重写为 20 项。',
'2026-09-21: **多屏设计稿不再被静默压成一页：html2json 多 .screen = N 整屏 window（默认口径）+ `--split-per-page` + 屏数核对闸门** '
    'v0.27.99-open（钟工：「现在改」；根因：用户的多屏设计稿只生成一个页面）——'
    '**① 工具层（`ui_tools/html2json.py`）**：业版 `_find_screen()` 递归找到**第一个** `div.screen` 就 return、'
    '`convert()` 只遍历该屏子节点 → N 屏产物只有第一屏且**零提示**；现改为收集全部 `.screen`（文档顺序）并按'
    '`page-architecture-spec.md` 默认口径合成**同一个 json 的 N 个整屏 window**（`window__1..window__N` 连续编号，'
    '首屏 `visible:true`、其余 `false`，`caption=data-page`，position = 整屏）；`split_per_page=True`（CLI `--split-per-page`）'
    '→ 每屏一个 json（文件名取 `data-page`）供跨业务域 / 独立返回栈场景。'
    '**② 返回体**：新增 `screensDetected` / `pagesProduced` / `mode` / `jsonPaths`，'
    '**两者不等一律 `success:false` + error**（禁止再静默丢页）；warnings 逐条列「识别到的页 + 对应 window + visible」。'
    '**③ 口径统一**：删掉与 page-architecture-spec 相反的 FT-006 旧告警「页面级页面应拆多个 Activity」，'
    '改写成「同业务域 → 同 ftu 多整屏 window；只有跨业务域 / 需独立生命周期与返回栈 / 超大页面才拆新 ftu」。'
    '**④ 文档**：`ui_tools/HTML_SUBSET.md` 新增「多屏（多个 .screen）」节；`knowledge/devflow/prototype-flow.md` '
    '新增③→⑨「分页落地清单（硬规则）」；`page-architecture-spec.md` §0 改「多屏设计稿 = N 屏必须全部落地」+ 屏数核对项。'
    '**⑤ 用例**：新增 `tests/test_html2json_multiscreen.py`（单屏逐字节回归 / 2 屏合成 / split / 嵌套与重名反例）。'
    '**（注意：本条里的「默认口径 = 合成多整屏 window」已被 v0.27.100 反转 —— 缺省改成每屏一个 json，合成多整屏 window 改为显式 `--merge-windows`；以上一条为准）**',
'2026-09-20: **新增知识 `devflow/ui-asset-rules.md` 铁律 #11/#12 + 随包审计工具 `ui_tools/corner_audit.py` / `ui_tools/alpha_bg_audit.py` / `ui_tools/asset_audit_rules.json`：切图缺倒角 与「图片背景是黑的（烘了底色）」从设计标准 + 自动拦截两层落地** '
    'v0.27.98-open（钟工：「控件里面图片背景是黑色的，应该做成透明的，这个设计不符合 flyThings OS 平台的能力」/'
    '「主界面大量图片依旧存在切图缺倒角问题，这个问题三番五次提出来过的。必须给我从设计标准和拦截上处理好」）——'
    '① **口径**：标准侧（Linux SoC）支持 PNG alpha，形状类资产必须**真透明**（形状外 α=0）；'
    '「形状外填页面背景色」只是 **Lite（RGB565 + colorkey）** 的做法，两套口径不能混；'
    '矩形/卡片/磁贴/药丸**必须有倒角**（半径按工程 `DESIGN.md` 圆角令牌，机读副本 `asset_audit_rules.json`），'
    '抗锯齿走 ≥4× 超采样 + AREA/BOX；② **判据（可复算）**：边起跑距离 `d = r - sqrt(r-0.25)` 反解 `r_est`，'
    '直角残留 = `d≤1`；整图 `min(α)≥250` = `no_alpha`（烘底色），内切/图标族角块不透明率 ≥0.5 = `corner_opaque`，'
    '图标最外 1px 环 ≥0.25（或任一边 ≥0.9）= `edge_bleed`；③ **拦截**：两个审计的 `--fail` 已接进 `check_all`'
    '**第 22 / 23 项**（真缺陷 = FAIL；满幅/底图族按登记理由 EXEMPT；未登记资产只 NOTE，不静默不误判）；'
    '回归样本 `tools/qa/samples/` + `python tools/qa/run_samples.py`（15 条断言：正例不误报 + 反例必须被抓住 + 退出码正确）；'
    '④ **存量实测（ControlTest-F133，153 张）**：缺倒角 4 张（`tile_photos(_p)` / `tile_place(_p)`——'
    '底边不透明图形 `alpha_composite` 把下层圆角抹平 → BL/BR `d=0`/r_est 0.5px、上两角 30.5px）→ 改「同一张 SS 画布一次成图」后'
    '四角 `d=25`（r_est 30.5）与其余 10 张磁贴一致；透明底/贴边 5 张（`sig_1/2/3`、`icon_wifi_40x40`、`icon_wifi_56x56`：'
    '旧 `glyph_icon("wifi")` 描边 2.0 单位 ≈ 弧间距 2.6 单位 → 弧带并合成**实心圆顶**、底部圆点半径按 k² 膨胀贴死底边）'
    '→ 线框重画（弧 + 点，四周留 ≥1px）后角块 0 / 边环 0；`check_all` **40 项全 PASS**（#21/#22/#23 真缺陷 0 张），'
    'preview 像素 diff **20 处差异全部落在 3 个被改磁贴实例内**（其余像素零差异）。',
'2026-09-19: **新增知识 `devflow/canvas-panel-coverage.md`：画布必须盖满面板（未覆盖区露出上一款应用的残留帧 = 伪闪烁）** '
    'v0.27.97-open（钟工 21:10：「总结经验然后上传」；源头 = 钟工真机报障「F133 设备左下角的页标签在页面刷新时总是闪烁第一页内容，'
    '应该是逻辑问题」）——**诊断（零猜测）**：① 设备跑的是 tdesign-f133 包（拉 `/tmp/ui/main.ftu` 反解析后与本地 md5 逐字节一致，'
    '`.so` 里搜到本工程独有格式串）；② 屏上那条「第 N / 8 页　<页名>」**在包/json 里搜不到** ⇒ **不属于本应用**；'
    '**根因 = 两条叠加**：布局画布 **1280×750 < 面板可视区 1280×800**（底部 50px 本应用从不绘制）+ **fb 双缓冲**把前一款部署过的应用'
    '（ControlShowcase）最后一帧留在未绘制区 → 每次刷新换 buffer 就换一次残留画面（实测连抓两帧同一区域分别是 '
    '「第 1 / 8 页　滚轮基础」/「第 8 / 8 页　日历」，与钟工「闪烁第一页内容」完全对上）；'
    '**修法（最小改动、几何零位移）**：`resolution.height` + 根 `position.height` 750→800（控件绝对定位、根背景负责刷底色），'
    '`fui pack` 后**只推 ftu** + 温和重启（`kill -TERM`，不重编/重推 `.so`、不 reboot）；'
    '**验收（机器可判）**：补齐区像素 == 根背景色、同页连抓两帧补齐区 diff bbox = None、强制切页后再抓仍 None（三项实测通过）；'
    '残留 check_all 仅存量 AA 真缺陷 70 张（与本改动无关）。文档含**诊断三步**（拉包比 md5 → 文案丢进 json 搜 → 两帧比补齐区 bbox）、'
    '**平台面板可视区表**（F133/F136 1280×800、Z21 1024×600、Z20 800×1280、V85x 按型号）、**防复发**（生成器别把画布高度写死成'
    '"内容高度"；验收脚本加「画布分辨率 == 目标面板可视区」断言——本缺陷修复前任何几何断言都锚在控件盒内，查不出来）。',
    '2026-09-19: **出图核缩回算子整改（LANCZOS→Image.BOX）+ 9-patch 描边改出图 + check_all 第 21 项** '
    'v0.27.96-open（钟工拍板：「1. 改，出图的锯齿问题必查。必须改掉这个。 2. 改。 3. 改出图」）——'
    '**A1 全链路排查（14 处）**：`gen_res._ss_down`/`_ss_mask` 与所有「带直通 α 的缩回点」'
    '（icon_circle / frames_loading(_gif) / _emoji_img×2 / _ai_img / line_icon / _glyph_render / '
    '_gear / _refresh / _wifi / _heart / _star / _bluetooth / 阴影 mask）一律改 **Image.BOX 面积平均**'
    '（判据 `has_straight_alpha()`：只有整幅不透明才允许 LANCZOS；常量 `_DOWN_OP_ALPHA`/'
    '`_DOWN_OP_OPAQUE`）；`_ss_down` 重写为 float 预乘 + 精确面积平均 + 反预乘。'
    '实测（temp/a1_chain.py，aa_audit 打分）：出图核矩阵 17 类脏边 1671→932（形状/描边/图标类全部归 0）；'
    '`rounded_rect_ss(80,40,20,...)` 直通 α 契约脏边 96→0。'
    '**A3 描边口径（三选一，不登记白名单）**：①新增覆盖率 API `coverage_mask`/`coverage_ring`/'
    '`rounded_rect_cov`/`bordered_cov`/`recolor_ring`，描边走「整像素描边带」（环触达即整像素上描边色，'
    '不做描边↔填充亚像素混色）；②`gen_btn9(border=None)` 按下态描边跟随按下色；③发丝线只画在形状'
    '全覆盖列段（越过圆角弧的线头 = dirty）。案例 19 张 .9.png：WARN 18 张（dirty 172/speck 176）→ '
    '11 张（dirty 0/speck 0，余下全是切点区 hard_diag，ss=16/64/256 同值 = 几何固有）。'
    '**A2**：`check_all` 新增**第 21 项**委派 `tools/qa/aa_audit.py --fail`（0 token、有退出码、JSON 解析；'
    '真缺陷 FAIL、WARN/EXEMPT 逐条理由；`.9.png` marker 环沿用审计内置豁免）——钟工原话是「接进第 19 项」，'
    '#19/#20 已被 V85X 图层释放/运行期设图占用，为不打乱既有编号与知识库引用追加为 #21。'
    '**规范**：`references/kb/image-gen-standard.md` 新增 §1.4（描边/发丝线口径）+ §1.5（缩回算子唯一判据），'
    '§1.2 接进 check_all #21；`knowledge/devflow/ui-asset-rules.md` 铁律 #8/#10 同步（数字复测为 BOX 口径）'
    '+ 检索同义词。**用例**：test_gen_res_aa 新增 6 条契约（含「旧 LANCZOS 口径复现」反面教材）'
    '+ test_html2json_ss 真值改 BOX。CHANGELOG 不追加。',
    '2026-09-19: **AA 审计增强：低对比度边缘不再漏检（选中条圆角锯齿/脏边）** v0.27.95-open（钟工 14:00：「这个选中条的边界有锯齿，也需要检查一下 MCP」）——**A 漏检根因**：`tools/qa/aa_audit.py` v1只读 alpha、判据要求「对角 α≤5 且两正交 α≥250」、且没有对比度概念 → 案例的浅色选中条（#F2F3FF 压 #F3F3F3，**只有 B 通道差 12 级、亮度差仅 ~1.4**）在 56 张证据图上 `hard=0 mid=0`（全盲）；**B 工具增强（v2）**：① `resid_bad` —— 沿 ±4px 剖面取「外侧平台色/内侧平台色」（连续 3 采样互差≤6，抗底色渐变），边界像素必须落在两色连线上，偏离 > max(5, **0.6×该处对比度**) 即脏边（对比度归一化 → 低对比度同样敏感）；② `hard_diag` —— 曲线/圆角 1px 阶梯，结构张量区分斜/弧与轴对齐（轴对齐硬边豁免），占比 ≥60% 才算成片缺陷；③ `dirty`/`speck` —— 直通 α 边界 RGB 污染（可见误差=偏离×α/255）；④ 豁免机制：`*.9.png` marker 环（只豁免环区，本体照审）、像素艺术（降 WARN）、**最近邻放大图拒收**、白名单 `aa_audit_allow.json`，逐条打理由；⑤ 证据：标注图 + 8× 放大 + 坐标 + 计数 + `--fail` 退出码。**C 标定（temp/aa_ab，同一几何两条路）**：旧管线（SS+预乘 LANCZOS）176×36 r18 药丸 → `resid_bad=50（最大残差 13 / 对比度 12）`= DEFECT；覆盖率口径（SS 二值 + Image.BOX）同图 → 0 = CLEAN；案例抓帧 `--region` → `resid_bad=40（最大残差 201 / 对比度 12）`。**D 规范**：`references/kb/image-gen-standard.md` §1 缩回算子改口径（**AREA/BOX 优先；带直通 α 的边界禁用 LANCZOS**，负瓣振铃=暗边/白点）+ §1.3「低对比度边缘是高发区」坑条；`knowledge/devflow/ui-asset-rules.md` 新增铁律 #10 （同口径 + 检索同义词）+ `pixel-analysis-ai.md` 坑条一行；新增 `tools/qa/README.md` + 白名单文件。**E 存量复扫**：components/icons/out 915 张 + icons example 18 张 + ui_v1 RadButton 1 张 → **真缺陷 0**；ControlShowcase z21（案例侧新产物，36 张）→ 真缺陷 1（`tab_off.9.png`，resid 8/对比度 24）+ WARN 19（1px 描边亚像素混色，逐条列理由）+ EXEMPT 3。版本 0.27.94→0.27.95；CHANGELOG 不追加。',
    '2026-09-19: **TimePicker 全族统一收口为 `listview`/L2（含时钟盘形态）+ 检索质量优化（16/16 一次命中）** '
    'v0.27.94-open（钟工：**「TimePicker 通过 listview 这个实现对应。检索质量优化。有发现的遗留问题都处理掉」**）——'
    '**A 映射表口径**：`TimePicker`（**滚轮 + 时钟盘两形态都走 `listview`/L2**，不再留「无对应能力」例外）、'
    '`NumberPicker`（由 `stepper` 改判 `listview`）、小程序 `picker(mode=date/time)` 拆为 `date`(calendar L4)/'
    '`time`(listview L2)；时钟盘的**圆形排列观感**如实写为「需 12 方位按钮组或 ZKPainter 自绘（观感有损）」'
    '= **观感降级说明，不是能力缺失**；表版本 2→3，新增别名 `clock dial`/`时钟盘`（可直接查）。'
    '**B 检索质量**（目标是轮子/选择器类问题一次命中权威文档）：新增 `scripts/check_retrieval.py` 回归 '
    '（16 条真实问法 + 11 条对照组，进闸门）；`listview-wheel-picker.md` 补「速查」节 + 时间选择/时钟盘 §6 + '
    '检索命中条件扩全同义词；`listview-fields.md` 的重复滚轮章节改为指针（单一权威文档）；'
    '检索实现两处最小改动：**专名（rare term）优先重排**（英文控件名向量路不敏感，如 QTimeEdit/LISTWHEEL/NumberPicker）'
    '+ **BM25 中文口语别名扩展**（滚轮→wheel/roller，吃到「命中文件名」权重）。'
    '**实测**（1524→1530 chunks）：滚轮族 12 条主力问法 top-1 **9/12 → 12/12**、全部 16 条 **9/16 → 16/16**、'
    'quality=ok **14/16 → 16/16**；对照组（与滚轮无关 11 条）top-3 **7/11 → 9/11**（专名优先同时修好了别的主题）；'
    '降级 BM25 模式同样 16/16。**C 遗留清零**：映射表/散文/测试全同步，`wheelpicker` 悬空引用 0、'
    '「计划 `TimePicker/`」类旧表述 0；版本 0.27.93→0.27.94；CHANGELOG 不追加。',
    '2026-09-19: **滚轮选择器口径收口：机读映射表 L5 → L2（`listview` 组合）+ 移除自绘包 `ui_v1/WheelPicker/`** v0.27.93-open（钟工 2026-09-19 12:40 拍板：**A1 映射表改 L2**、**A3 去掉自绘包**）——**A1 机读映射口径同步**：`mcp_control_map.json` 的 5 条滚轮族源条目（LVGL `lv_roller`（别名 `wheel`）/ Qt `QTimeEdit` / Android `TimePicker` / 小程序 `picker-view` / emWin `LISTWHEEL`）`target: wheelpicker → listview`、`level: L5 → L2`，`json` 改为**可直接粘的轮子片段**（一列 `listview__N`：`cycleEnable:true` + `edgeEffect:1`/`dragMaxDis:50`/`autoRollback:true` + 行模板 `item.text:""`+ `picTab` 空位 + **listview 之前的静态装饰 `textview` 选中条**），`ref` 指向 `knowledge/uicontrols/listview-wheel-picker.md` + `components/ui_v1/control-map.md` 2.24；`targets.wheelpicker`（旧自绘包占位）**删除**（5 条源条目已全部改指 `listview`，**无悬空引用**）；`targets.listview.note` 补滚轮口径指针。**验证**：`flythings_map_control("picker-view" / "lv_roller" / "wheel")` 均回 `target=listview` + `level=L2`（不再出现 L5 / `wheelpicker`）。**A3 自绘包移除**：删 `components/ui_v1/WheelPicker/`（四件套 + `example/` + 16 张真机证据，共 97 文件，已移入 workspace `/.trash/20260919_mcp_WheelPicker`）；全部引用收口（`components.md` 一行改为「已移除」+ 第 2 段映射项新增第 13 行「滚轮选择器」、`control-map.md` 2.24、`gap-list.md` G-23、`ui_v1/README.md` 目录铁律反例、`control-mapping-capability.md`、`framework-control-mapping.md`、`gui-controls-gap.md` #5、`device-deploy-budget.md`、`touch-events.md`、`adb_tools.py`、`tools/adb/README.md`）；**保留坑条**：自绘轮曾用于逐像素 alpha 渐隐/行内非文字内容，现并入 listview 方案（淡出 = 按行距插值**文字色**；行内小图走行模板 `subItem`）。**文档**：`listview-wheel-picker.md` 新增 **§5.1「机读映射口径」**（源控件 → `target/level` 表 + 验证入口），§5 改写为「与已移除自绘包的关系」；顺手修 `listview-fields.md` §滚轮选择器 坑 1 里残留的旧口径（「行上 `setBackgroundPic(条图)`」→ 改指静态层坑 4）。',
    '2026-09-18: **新增 `flythings_layout_audit`：从 json 静态判定层叠/遮挡/触摸穿透（先看 json 再截图）** v0.27.92-open（钟工：用户说「改东西 / 控件覆盖」时 AI 总去截图，其实 json 就能分析出问题）——①新 op（**read 风险，纯几何 0 token**）：扫 `ui/*.json`（含分层目录，可 page 过滤），递归同层兄弟做盒子几何判定，返回 `pages[].findings[]`：`fullscreen_layer`（整屏层 == resolution，touchable 会吞整屏触摸）/ `touch_steal`（**同层更早定义的 touchable 控件**完整覆盖 → 触摸按定义顺序先被拿走）/ `covered_interactive`（被上层 touchable 盖住）/ `pass_through_missing`（装饰件缺 touchPass）/ `overlap`（盒子相交）；每条带 `by`+`why`+`fix`。②口径：z 序 = json 书写顺序，遮挡/点不到优先本 op；视觉样式仍 device_screenshot + ui_visual(diff)。③文档/入口：`knowledge/uicontrols/json-layer-rules.md` 新增「静态遮挡审计」节 + 检索词，PROJECT_SPEC 与 `flythings-ui-dev` skill 加触发口径。④预算再压（map_control/generate_ui_assets/hardware_info 长尾细节指向 knowledge），用例 +4。',
    '2026-09-18: **fui unpack 能力释放（随包 fui 换代）+ 新增 flythings_fui_unpack** v0.27.91-open（钟工：「mcp 两个版本吧，fui 的 unpack 能力释放出去」）——①**两版随包工具链同步换代**：`toolchain/fui.exe` 4873216B（只含 pack，unpack 是空壳）→ **4915712B**（`help` 里 pack/unpack 都在；`unpack <in.ftu> [out.json]` 与「传目录批量解」两种形态实测可用，pack 同）（open 与 release 两版都换），md5 `BA422F14A8155A377C04C8AE51240661` = 开发机 `C:/zkswe/fun/fui.exe`。②**新增 op `flythings_fui_unpack(ftu_path, output_json=``, overwrite=True)`**（36 个 op）：ftu → json 反解析；**默认覆盖同目录同名 json**（ftu 为真源；要保留原 json 传 `overwrite=False` → 写 `<name>.unpacked.json`，已存在则追加序号），也可 `output_json` 指定落盘路径；返回 ftuPath/jsonPath/overwritten/controlsCount/resolution + affectedFiles（写操作回显）。用在：只有 ftu 没 json 的老工程 / 核对设备侧布局 / IDE 直接改过 ftu 要回写 json。③**口径修正**：`read_json` 传 .ftu 不再回「加密文件无法解析」，改为指路 fui_unpack；`_rewrite_ftu_resolution` / `_sync_ftu_to_json` / validate 的 devModified 提示不再写死「内置 fui 只支持 pack」（统一按 `_fui_supports_unpack()` 能力探测）；`knowledge/devflow/ftu-json-pipeline.md` §6/FAQ/检索词、`cli-fun-toolchain.md` 名词口径、`tools_manifest.json` 的 fui 说明同步改正。④**docstring 预算重新压平**（新增 1 个 op 后仍过闸）：单 op ≤ 900（最大 803）+ 总 **11987/12000**（腾位置时把 device_screenshot/ui_visual/verify_assets/html_to_json/edit_ftu 的长尾细节指向 knowledge/）。⑤**unpack 默认覆盖对应 json**（钟工 08:43 更正）：`flythings_fui_unpack(..., overwrite=True)` —— 默认写回同目录同名 json，要保留原 json 传 `overwrite=False`（写 `<name>.unpacked.json`），`output_json` 指定路径时不动同名 json。⑥**ftu→json 自动同步只两种情形**（钟工 09:06 口径）：只有 ftu 没有 json → 直接转；ftu 比 json 新「分钟级」(≥60s，用户/IDE 编辑过) → 转同步；其余**不做**反向（`_ui_timestamp_check.dev_threshold` 30→60，新增 `ftuOnly` / `ftu_without_json` 警告；`_sync_ftu_to_json` 返回 `syncedDetail/skipped/warnings`；**异常 ftu（不能反解析）→ 明确报错 + 给用户 `hint`（提供 json 或重新导出 ftu），不静默跳过**）。⑦用例 +11（unpack 默认覆盖 / overwrite=false 保留源 / 非 ftu 报错 / 能力声明与实际一致 / 往返 / 自动同步三规则 + 阈值 ≥60 钉住），门禁 `check_consistency --with-tests` 全绿。',
    '2026-09-17: **html2json 原生支持 `div.text` 的 `data-bgpic` + 新增静态检查「运行期设图 vs 控件盒」+ 重启应用改温和终止** v0.27.90-open（钟工拍板：上一条清单的第 1/2/3 项入库，第 4 项 U 盘升级不入库）——**A `div.text` 的 `data-bgpic` 不再丢**：`html2json` 的 textview 分支原**不读** `data-bgpic` → json 里那节点没有 `backgroundPic`（弹窗白卡/药丸/图标压根没画出来），案例只能 `patch_json` 反查 HTML 兜底。现与 button/window/seekbar/circlebar 同口径落地（裸文件名补 `images/` 前缀；有图同样去底色，与 button 的「图片按钮不放底色」同规则）。**实料回归**（案例 `projects/translate/tdesign-miniprogram` 双平台重生成，在临时副本里做、不动案例目录）：HTML 里 `class=text`+`data-bgpic` 共 **87 节点** —— 老转换器落地 **0/87**（`patch_json` 补 87）、新转换器 **87/87**；两条路径的 `caption→backgroundPic` 映射**语义等价（110 条全等）**；`patch_json` 变**幂等兜底**（重跑 md5 不变，报「底图 14」= 只有它自己的卡片/面板表在同值覆写）；重生成物 `check_all` 双平台 **exit 0**（0 FAIL / 9 WARN）、`fun build -p Z21` 仍过。新增用例 5 项（正例 + 反例「无 bgpic 的 text 不受影响」+ 图必须与盒 1:1）。**B 新增静态检查 check_all 第 20 项「运行期 set...Pic 的图 vs 控件盒」**（补上 §5 说的盲区；背景：48×16 三点图进了被抬高的 48×26 盒 → 引擎按盒拉伸 → 正圆变竖椭圆，静态检查当时一路 PASS）：扫 `src/**/*.cc|*.cpp` 的 `mXXXPtr->set...Pic("...")`（含三元式多个字面量、去注释保行号、括号平衡取实参），变量名 → caption（`mXxxPtr` 同第 6 项口径）→ 与 json 控件盒比；**`resources/images/` 自动生成图不等 = FAIL**、手绘图（其它目录）不等 = `stretched` 仅提示（官方基准 `navi/fh.png` 44×26 进 72×40 按钮绝不 FAIL）、`.9.png` 豁免、文件不存在 → `missing`、映射不到/非工程内路径 → `unresolved`（列出来不静默）、实参是变量/拼接 → 只计 `dynamic`（明说判不了）。**零误报核查**：`SampleUI-New`(145 FAIL) / `ShowcaseAlbum-F133`(37) / `WebViewDemo`(3) / 案例双平台 —— 新增项 **0 FAIL**（三基准工程该 0 处静态字面量可比 / 案例 6 处比过全匹配）；**真能抓的证明**：案例副本把 `LdDots` 盒高改回被抬高的 26 + 该调用形态 → **当场 FAIL**（`48x16 != 盒 48x26`）、盒高 16 时 PASS。新增用例 11 项。**C 重启应用改温和终止优先**（防御性，**因果未确证**）：MCP 侧新增 `adb_tools.restart_app()`（`kill -TERM` → 3s 轮询 → 仍在则回退 `kill -KILL`，日志写清用了哪条/是否回退）+ 组件示例 `WheelPicker/example/tools/deploy.py` 与案例侧 `deploy_z21.py` 同步该姿势（后者原来直接 `kill -9`）；现场多次 `kill -9 zkgui` 之后（以及 `adb reboot` 之后）出现过整板掉网、两条现象互相矛盾 → **按未确证口径写进文档**（`device-deploy-budget.md` 新节 + `deploy-scene-map.md` 指针），遇到掉网按现场断电重启处理，**不写成已证实结论**。文档同步：`html-subset-quickref.md` §4 的「会被丢掉」改成「已原生支持（v0.27.90-open），旧工程的 `patch_json` 兜底可保留（幂等）」、`text-box-height-rule.md` §5 的「本次未实现」改成已实现并写口径与边界、`ui-layout-verify.md` / `HTML_SUBSET.md` / `touch-inject-autotest.md` / `platform-translate.md` 相应同步。用例 239→**255**（+5 +11），`scripts/sync_ui_tools.py --apply` 双份一致，门禁全绿。',
    '2026-09-17: **TDesign 竞品样式迁移案例的通用能力入库 + 修掉「setInvalid 当重绘」反口径** v0.27.89-open（沛哥：把今天案例里能复用的口径全部入库，顺手把 kb 里会害人的一条改掉；案例 `projects/translate/tdesign-miniprogram`，报告 SLIDER_PERF.md / DOTS_ROUND.md / DLG_CORNER.md / STAGE3.md / TRANSLATE.md）——**A 反口径修正（最高优先级）**：①`knowledge/devflow/device-screenshot.md` §3.3-1 原写「状态变化时分两帧 `setInvalid()`」当强制重绘手段 → 改为明确「**别拿 setInvalid 当重绘**」（附真机证据：13 个导航键被这样禁掉 → 整屏「点哪都没反应」，一度被误判成「注入坏了 / 面板坏了」）；②`knowledge/uicontrols/touch-events.md` 新增 **§6**：`ZKBase::setInvalid(bool)` = 置为无效状态（`ZK_CONTROL_STATUS_INVALID`），头文件三行对照（`setInvalid(bool)` / `isInvalid()` / `invalidate(...)`，**没有无参版本**）+ **§6.1 解释「为什么示例里拿它刷帧也能用」**——它确实会触发重绘（状态变了要重画外观），但那是依赖旁路行为的技巧：只读 `textview` 看不到副作用、**可交互控件直接被禁用**；**§6.2** `invalidate()` 才是重绘 API，但**旧设备 `libeasyui.so` 可能未导出**（undefined symbol → 整屏黑）；并给「30 秒定位判据：先 grep setInvalid」；③顺带把 `project_tools` 的 PROJECT_SPEC caveat 与 validate 提示里那句「帧刷新用 setInvalid 交替」**加限定语**（仅限 setBackgroundBmp 的只读控件），避免再被误用到按钮上；全库自查（md/py/知识）确认无第二处「把 setInvalid 当通用重绘」的表述。**B 新增 3 篇知识**：①`knowledge/uicontrols/high-frequency-callback-perf.md`（★高频回调性能规范：拖动/触摸回调**禁止全量刷新**；案例一次拖动 ≈**86 次 GUI 调用**（21 setText + 9 setSelected + 4 setVisible + 4 值文本 + updateS3 约 48）→ 工具 95 步滑动**只处理 29 次**（对照条 90 次）；A/B 三指标全在设备侧量：CPU **73.8%→7.3%**（10 连拖 74.4%→6.9%、快拖 91.3%→19.2%）、慢拖响应 **250→135ms**、快拖 **383→134ms**、快拖帧变化率 **0.27→4.13fps**、每 20 步画帧 **0→3**；含量具自制与三个坑、自查清单）②`knowledge/uicontrols/text-box-height-rule.md`（字号下限 ≥18px + **「抬盒高只对有文字的 text 盒有效」**：`h≤4` 装饰线 / 带 `data-bgpic` 纯图盒 / **运行期 `setBackgroundPic` 逐帧换图的图标盒**一律不能抬——实测三点指示器盒 48×26 把 48×16 的图拉成 **10×16 竖椭圆**（ratio 0.625），改后 10×10（1.000）；判据 = 「盒里有没有文字」而非控件名白名单；点明 `html2json` FT-009 的 `if not text: continue` **本来就是同口径**（案例自研 clamp 漏了才踩）；静态检查盲区与「是否内建到 ui_tools」评估结论）③`knowledge/devflow/platform-translate.md`（★跨框架/竞品迁移方法论：**机读索引优先**（`flythings_map_control` / `mcp_control_map.json` 212 条，不抄散文映射表）、视觉换算与铁律（rpx×0.5=px / 字号≥18 / 图==盒 / 零自绘 / 单一手写源）、**四阶段路线**（骨架表单 → 反馈弹层 → 数据展示 → 复杂选择器 + 每阶段固定仪式；案例规模 17 页 / 651 控件 / 236 图）、**D-xx 差异降级登记制**、双平台口径（Manifest 平台键可能与目录名不一致：f133 目录→`-p F136`；未验过的平台如实标注）、`flythings_translate_ui` op **仅规划未实现**）。**C 既有文档补 4 处**：①`touch-events.md` 新增 **§7**「嵌套 `window` 里的子控件点不动——被同层更早定义的 touchable 控件抢走触摸」+ 扁平化修法（顺序 = 遮罩 → 卡片底图(touchable=true) → 卡片内控件）与自检清单；②`nine-patch-rule.md` 新增进阶节「**方块底图刷平卡片底部圆角**」（实测平台事实：`.9.png` 着色区左右下各内缩 1px，普通 PNG 严格 1:1；**做法 = 按按钮位置出带下圆角的动作行底图 + 角区整块挖空**，按钮自画弧会二次 alpha 混合发白（178→217）；实测 8 弹窗 7 中招 / 28 偏差行 / 最大 6px → **0 / 0 / 0px**，面板「取消」同根因一并修）；③`html-subset-quickref.md` 补坑「**`div.text` 上的 `data-bgpic` 会被 html2json 丢掉**」（textview 分支不读该属性，同 JSON 里 seekbar 的 textview 却有；两条处置：换支持承载的类型 / `patch_json` 回填）；④`touch-inject-autotest.md` 补「**系统软键盘是整屏窗口**：套件间不收键盘会让紧接的注入全落键盘上 → 一批导航键假 FAIL 且对脚本来说像『注入坏了』」（收键点 ≈(963,550)、键盘守卫判据、顺序纪律）+ 抓帧时机节补「**瞬态层单抓 / 静态页弹窗双抓**」，`device-screenshot.md` 相应新增 §3.3-2 与检索词。隐私闸门按公开口径（设备 IP 一律写「参数传入」，无内网 IP / 绝对路径）。门禁 `check_consistency --with-tests` 全绿。',
    '2026-09-17: **图标抗锯齿去量化（TDesign 案例徽标页 48×48 图标肉眼看硬阶梯）** v0.27.88-open（钟工拍板「修改」）——**根因**：图标走 SVG（Tabler 原图 → `svgmini.render_svg` 8× 超采样 + BOX 面积平均 = 精确覆盖率），问题在收尾的**「α 对比度整形」**：把覆盖率 <0.40 推成 0、>0.60 推成 255，边缘灰度被量化成个位数级。①`svgmini.render_svg(..., snap=False)` 改为默认：**真实覆盖率** + 只清「覆盖率 <0.08 且 8 邻域无内容」的孤立噪点（`_clean_noise`/`_despeckle`），老口径 `_snap_alpha` 保留为 `snap=True`；②`gen_icons.py` 新增 **`--snap`**（opt-in，帮助文本同步）贯穿 `--out`/`--sheet`/compose 全路径（`--ss` 不变）；③**实测 A/B**（全量 305 产物 × 22/24/56，改前/改后）：中间值**灰度级数中位 22px 7→30、24px 4→17、56px 9→42**（bell@48px 9→44 级，user@48px 5→20 级；alpha 唯一值 48px bell 9→44），孤立噪点两口径都是 **0**，覆盖率区间 1.4%~80.2%（22px）；④selfcheck **C 条口径重标定**（`mid_limit(size) = min(60%, 10.5/边长)` → 22px 47.7%｜24px 43.8%｜56px 18.8%；依据实测 22px max 42.6% / 24px 34.7% / 56px 16.1% —— 原固定 15% 是给「整形后」定的，真实覆盖率下会把**正确**的抗锯齿判死）并**新增 C2 条抗锯齿保真**（抽样 bell/user/settings/wifi × 22/48/56 对拍 **16× 超采样理想覆盖率**：边界带 mean ≤8、p95 ≤32（/255），灰度级数 ≥12；换回硬整形实测当场报 **21 条失败**）；⑤`catalog.json` 新增 `render.antialias` 口径（`gen_catalog.py` 生成，模块版本 → **0.3.1**）；⑥模块文档同步（README §3.1/§6/§9/§10 + platforms.md + `knowledge/devflow/icon-library.md`）；⑦实测：305×3 张 PNG + 7 张 sheet 重生，`python components/icons/scripts/selfcheck.py` **915 张 0 失败**，门禁 39/39 全绿。8× 放大 A/B 图：`components/icons/out/aa_*_ab.png`。（遗留待拍板：`example/app/resources/images/` 里 19 张已入库 PNG 未随本次重生。）',
    '2026-09-17: **字体判定升级为 cmap 硬判据 + V85x 芯片别名补齐** v0.27.87-open（钟工拍板：用硬判据，比体积判据好；并问「V851/V851S/V851S3/V853S 这几个你适配了吗」）——**A 字体硬判据**：①`device_font_check.py` 新增 cmap 覆盖率判据（基准 = **GB2312 一级 3755 字**，用标准库 `gb2312` codec 现场推出；阈值 `CMAP_OK_MIN_PCT=90` / `CMAP_LOW_MIN_PCT=50`，拉取上限 `PROBE_MAX_BYTES=12MB`）；②`font_tools.hard_probe()`：挑设备最大 ttf/ttc **拉回 PC 临时目录（用完即删）** → fontTools 读 cmap → **≥90% → `ok`（不投）/ 50–90% → `low`（投 + warning 写明覆盖率）/ <50% → `missing`（投）**，字段 `source`(`cmap`|`size`)/`cmapCoverageGB2312L1`/`cmapCoveredChars`/`checkedFont`(路径+体积+mtime+md5)/`probe.cacheHit`；③兜底**不许静默**：体积超限 / fontTools 不可用 / 拉取或解析失败 → **退回体积判据**（`source="size"` + `warnings` 写明原因）；④结论按 `serial+目录/文件名+体积+ls 时间` 缓存到 `~/.fun/font-probe.json`（`FLYTHINGS_FONT_CACHE` 可覆盖）→ 不每次 build 都拉；⑤`fun launch` 成功后若刚投递过字体 → `fontCheck.deviceAfterDeploy` 回报设备侧字库现状与一致性（**要 `pack_upgrade` 固化才生效**，故只核名字/体积不重拉）；⑥`fontTools==4.65.0` 锁进 `requirements.lock`；⑦口径文档 `knowledge/devflow/custom-font-config.md` §0.2 + `components/fonts/README.md` §0/§3。**B V85x 别名**：⑧`platforms.PACKAGE_INPUT_ALIASES` 补 `v851 / v851s / v851s3 / v853s`（→ V85X）——修前 `resolve("V851S")=None`（当未知平台）且 `package_key("V851S")` 回 `v851s` 这种 **catalog 里不存在的键（查包必空）**；⑨`hardware_catalog.json` V85X 收齐 6 个主控（V553/V851/V851S/V851S3/V853/V853S）+ 新增 `chipEntries` 芯片级登记（有实测标 `partial` 并给依据来源；**无实测的 V851S3/V853S 如实标 `pending`+「待确认」，不臆造规格**）+ `chipsNote` 写死「V85x 家族统一归一到 V85X 平台，包键走 `v85x`/`v85xemmc`」；⑩`package_catalog.json` 的 `v85x`/`v85xemmc.chips` 补 `V851`；⑪`hardware_tools.normalize_platform` 补 `platforms.resolve` 兜底（修「芯片名查包认、hardware_info 却回 BAD_PLATFORM」的双口径；仅包生态平台仍走 `PLATFORM_NOT_IN_HARDWARE_LIB`）；⑫真机实测（V85X SPINOR 整机，网络 adb；多设备时 fun launch 硬失败 → 先 disconnect 另两台再跑）：`source=cmap` / `cmapCoverageGB2312L1=100.0`（3755/3755）/ `verdict=ok` / `checkedFont=/res/font/pocketgame.ttf`（1,093,608 B）/ 拉回耗时 1294 ms；同设备再跑 `probe.cacheHit=true` + `elapsedMs=6` + `pulledBytes=0`（缓存真生效）；设备字库只有 302 个一级汉字时（81,188 B 字体）→ `coverage=8.0%` / `verdict=missing` / 自动投递；完整 `flythings_build_ui_flow`：`ok/launched/pushed=true` + `staleOnDevice=false` + `deviceAfterDeploy.consistent=false`（明说需 `pack_upgrade` 固化）；另补一个诚实提醒：扫描结果为空时不把结论说得像板上真没字库（进 scanNote/warnings）。⑬用例 214→**239**（新增 `TestFontCmapHardProbe` 18 项 + `TestV85xFamilyAliases` 7 项，全部离线：仓库自带 ttf + fontTools 现场造字体当「假设备数据」），门禁全绿。',
    '2026-09-17: **字体自动扫描接线：缺中文自动投递（设备侧优先，退化工程侧）** v0.27.86-open（钟工「现在做」）——①新增 `font_tools.py` 接线，判定阈值/三版清单/投递动作**单一来源** = `components/fonts/scripts/device_font_check.py`（`judge`/`TIERS`/`collect`/`apply_to_project`），adb 走 `adb_tools.resolve_adb()/ensure_busybox()`、设备门结果**复用**；`flythings_build_ui_flow` 新增 `font_check="auto"|"off"` + `font_tier="common"|"full"|"multi"`，在 **fun build 之前**插 `check_font`：有设备扫设备字体（`/etc/font`、`/res/font`、`/system/font`），无设备退化**工程侧 self-scan**（prefs 的 `font` 指向 + 工程 `font/`），缺中文（无字体 / 最大 < 200 KB）**默认自动投递 `common`** 进工程 `font/`；返回体 `fontCheck`：`missingChinese`/`maxFontBytes`/`advisedTier`/`delivered`（投没投+文件）/`deviceFonts`，无设备时 `note` 写清「未连设备，仅工程侧检查」，投递未完成进 `warnings` + 一键修复命令。②体检项并入 `check_project_deps`（交付前体检、与依赖同返回体）：新增 `device`/`font_check`/`font_tier`/`font_apply` 与 `fontCheck`/`fontIssues`，**默认只报不投**、传 `device=` 才扫设备。③修 `device_font_check.apply_to_project` 的 prefs 正则（真 prefs 转义写法下「改 prefs」以前实际没改成）。④文档口径写死（默认 `common`／生僻字 `full`／多语言 `multi`／自裁字库只在要更小体积或自定义字符集时）：README「② 功能说明」+ `knowledge/devflow/custom-font-config.md` §0.2 + `components/fonts/README.md` §0；检索词：设备字体自检/自动扫描字体/缺中文字库/font tier/投递字体。⑤实测（Z21 真机）：默认参数 `mode=device`、`deviceFonts` 5 条（871.9KB/818.6KB/Poppins×3）、`missingChinese=false`、**未触发投递**、`warnings=[]`，launch 与设备侧 md5 比对照常；`font_check="off"` → 无 `check_font` step；无设备分支自动投递成真、`fun launch` 后设备 `/tmp/EasyUI.cfg` 自动出现 font 键（投递确实生效）。⑥用例 200→**214**，门禁全绿。',
    '2026-09-17: **换开机 logo 入库（`boot_logo.JPG` → `MISC` 分区）** v0.27.85-open（钟工口径：与 `update.img` **同机制**）——①**知识**：`knowledge/devflow/upgrade-pack-image.md` 新增 **§三**（落点 = **MISC 分区**，非 logo 分区也非 `/res`；**上限 = MISC 分区大小**，本板 Z21 实测 `cat /proc/mtd` → `mtd4 MISC 0x80000 = 512 KB`，其它平台待确认；两种触发同 update.img —— TF 卡根目录 `boot_logo.JPG`（可与 update.img 并列）→ FAT32 → 插卡上电勾选，或 ADB `push` + `sys.zkupgrade.flag=255` + `sys.zkupgrade.dir` + `ctl.restart zkswe`，重启后生效；⚠️ 本板 `adb reboot` 后整板掉网需现场断电；「只放 logo 是否不碰 `/res`」**待真机验证**；检索词 开机 logo/boot_logo/MISC 分区/logo 512K/换开机图）；②**工具**：`tools/make_boot_logo.py`（生成 1024x600 深底品牌图，字体 env `FLYTHINGS_LOGO_FONT`+多候选回退，**生成即校验 ≤ MISC 上限**，超了降质/报错）+ `tools/set_boot_logo.py`（推设备触发升级，**默认 dry-run**、`--yes` 才发；前置校验 文件/JPG/体积≤MISC（在线读 `cat /proc/mtd`）/设备在线；adb 走 `adb_tools.resolve_adb()`）；③**接线**：`flythings_pack_upgrade` docstring + README 出包小节各加一行指向文档/脚本；④**实测**（真机 Z21，只读+dry-run，未触发升级）：`make_boot_logo` → 33,070 B（32.3 KB，上限 6.3%）通过；`set_boot_logo` → 设备在线 / 型号 Zkswe_SSD21X_SPINOR / Z21(confirmed) / `MISC=512KB` / 四条 dry-run 命令 / exit 0。',
    '2026-09-17: **ADB 随包 + launch 默认推设备 + 设备探测/安装提示** v0.27.84-open（钟工三项）——①`tools/adb/`（adb.exe 1.0.41/31.0.3-7562133 + 两个 WinApi DLL，≈6.1MB）+README；新增根 `adb_tools.py`：`resolve_adb()` = env ADB/FLYTHINGS_ADB → 随包 → PATH，**全仓 adb 硬编码 6 处→1 处**（project_tools、device_screenshot、i18n_tools×2、device_font_check 等）；②`build_ui_flow(with_launch)` 默认 **True**（build→探测→推送/运行，`with_launch=False` 只编译）；返回 `launched/pushed/device/model/platformMatch/deviceSync`（设备侧 ftu+so 字节/md5 vs 本地）+`staleOnDevice`（true ⇒ 设备上跑的还是旧版）；③探测不猜：0 台 → `needDeviceInput`+`installHint`（ADB 驱动 / USB 调试授权 / 网络 device=<IP>:5555）；多台 → 列 serial+model+匹配并要显式 device=；1 台且匹配 → 自动 `fun launch -s`；新增 `device_models.json`（Z21/Z20/V85X 实测；F133/F136 待确认）；④实测（三台真机 + 单台 Z21）：三台在线 → 多设备清单（不猜）；**单台自动选机 launch 成功**、设备侧 ftu 186B / libzkgui.so 277340B **字节+md5 与本地一致**；本地改过未推 → staleOnDevice=true；0 台 → installHint 到位；顺带修 3 个 adb 实测坑（`ls -l` 第 5 列才是字节 / 缺 md5sum 时用随仓 busybox 兜底取 md5 / **fun 多设备必 FATAL more than one device/emulator**，→ 修正「fun 静默取第一个」旧结论，见 cli-fun-toolchain.md §7）；用例 176→200，门禁全绿；细节 knowledge/devflow/adb-and-device-selection.md。',
    '2026-09-17: **依赖/install 诊断三项修补（A 体检 / B install 不再静默 / C 文档）** v0.27.83-open（钟工：客户只看到 `fatal error: base/functional.h: No such file or directory`，看不出「依赖没装」）——①**A**：`package_tools` 新增 `FRAMEWORK_DEPS`+`framework_dep_status()`，`check_project_deps` 出 `kind:"framework"` 缺失项与 `frameworkDeps`，`validate_project` 新增 `missing_framework_dependency`+fix（`flythings_add_package(...,\"base-utility\",with_install=True)` 或 Manifest 加 base-utility 后重跑 fun install）；**口径修正**：base-utility 移出 `BUILTIN_PKGS`（非模板自带，是 fun 生成的 generated/*.h 必需——旧检查就在这放过）；判定=精确头名（实读 generated/event_dispatcher.h）+前缀排除（base/ 非独占：base-http-client→base/http_*、base-json→base/json_*）；②**防误报**：Manifest 已声明 或 依赖已解析（.fun-lock.json/.deps.lock 有即算，实测 easyui 会带出）就 OK，bin 工程/无 base include 的非 UI 工程不报；③**B**：`build_ui_flow` install 失败→顶层 `warnings`**但不断**；build 前 `check_framework_deps` 缺包直接点「依赖未装/缺包」（含证据+fix），可解析时零 step 零 warning；build 失败含 `base/…No such file` 时翻成「依赖未装，不是代码错误」；④**C**：`cli-fun-toolchain.md` 新增 **§4.7 老工程升级：补 base-utility**（现象/根因/处置），`reusable-components.md` 交叉引用，检索词补 base/functional.h / 找不到 base utils / base-utility 缺失 / fun install 没生效；⑤**回归**：`create_project(Z235X,1024x600)→build_ui_flow` **9/9 成功**+`.fun/z235x/libzkgui.so`+**零 warning**；反例（删 Manifest 的 base-utility+清锁/.fun）真跑→顶层 warnings+step 点明缺包，ninja 实错 `generated/event_dispatcher.h:8:10: fatal error: base/functional.h: No such file or directory`（锁里仅 easyui/log/zkhardware/zknet，INCLUDES 无 base-utility）；用例 164→**176**（+12 条），门禁全绿。',
    '2026-09-17: **图标库改「单归档 + 按需解」（components/icons 6801 文件/6.30 MB → 48 文件/1.63 MB）** v0.27.82-open（沛哥：目标 ≈10 文件 / ~1 MB；方案 A 离线优先）——①**打包**：vendor 的 5777 个 SVG 散件（3.95 MB）打成 `components/icons/vendor/tabler-3.46.0.pack.tgz`（**455,379 B / 0.43 MB**，sha256 `a0ba69f224388e22790f04a0a157fb6207713511f7e308709a0166ebd8ec1c95`，条目 5774 = icons 4754 + icons-filled 1019 + map.json；**确定性写入**同一输入必得同一 sha256），新增 `scripts/make_pack.py`（打归档 / `--verify` 核对 / `--from-npm` 从上游重建，实测与散件版 byte 级同 sha256）；`index.json`/`LICENSE`/`VERSION.txt` 留在归档外（索引 + MIT 合规）；②**读取层**（`gen_icons.py` 新增「图标来源解析」）：逻辑路径 → ① 缓存 `out/.icons-cache/`（env `FLYTHINGS_ICONS_CACHE`）→ ② 归档 tarfile 随机读**只解用到的那几个** → ③ 远方 npm tarball（**默认关闭**，`--fetch-remote` 显式开启，按 catalog 登记的 sha256 校验）；`--vendor-name`/`--svg`/`--set`/`--sheet` 用法与输出**完全不变**，新增 `--list-tabler`（原生名 4754，index.json）与 `--pack-info`（来源状态）；③**入库范围**：`out/` 817 个生成物 `git rm --cached` + 进 `.gitignore`（实测整目录删后 305×3 PNG + 7 sheet 全部重生，selfcheck 915 张 0 失败）；`svg_retired/` 163 文件移出仓库（`author_svg.py` 可逐字节重生，实测 163 文件 sha256 全同）；④`catalog.json` 重生成（0.3.0，203 图标/305 产物/198 条 vendor 语义含 7 条 compose，新增 `sources.vendor.pack` 字段 —— 禁止手写口径不变）；⑤顺带修 `--vendor-name wifi` 被 `system.wifi-full` 别名抢匹配（改为精确名优先，此前文档里的 `--vendor-name wifi` 例子实际会报「匹配到多个」）。模块文档已同步（README/platforms/THIRD-PARTY + `knowledge/devflow/icon-library.md`：不能再 grep 单个 svg，要查用 `--list*`/`catalog.json`）。',
    '2026-09-17: **Z235X 建工程→编译闭环打通（模板补 base-utility + 工具链目录口径）** v0.27.81-open（钟工给了 235x 工具链，实测跑通）——① `templates/HelloWord_Z235X/Manifest.xml` 补 `<package id="base-utility" version="^10.0.0"/>`：fun 生成的 generated/event_dispatcher.h 等会 #include <base/functional.h>，缺这条编译直接 fatal error（对比 Z21 模板本来就带 base-utility，这次是源头 IDE 工程缺）；② `knowledge/devflow/cli-fun-toolchain.md` 新增 §4.6「平台工具链放哪 + 模板依赖最低集」：工具链目录约定 = <fun 安装目录>/toolchains/<平台小写键>/（缺工具链时 fun build 会 panic platform toolchain url must not be empty，工具链不随包分发）；③ `platforms.py` 的 Z235X note 同步该口径。实测闭环：create_project(platform=Z235X) → 工具链解压到 toolchains/z235x → fun install（拉到 base-utility@10.11.0 + ext4@0.0.1）→ fun build -p Z235X 9/9 成功，产出 .fun/z235x/libzkgui.so（217,240 B）。bin_tools/z235x 设备端工具仍未编译（需要样机）。',
    '2026-09-17: **fun 编译单元口径纠偏（activity 不参与 fun 构建；不要改 CMakeLists）** v0.27.80-open（钟工第二次纠偏：AI 去改 CMakeLists 想影响构建）——实测证据：`.fun/<平台>/CMakeLists.txt` 由 fun 自动生成（文件头写明自动生成、勿手改），`add_library(zkgui SHARED ...)` 只收 `../../src/Main.cpp`、`../../src/logic/mainLogic.cc`、`../../src/uart/*.cpp` 与 fun 生成的 `generated/{event,event_dispatcher,ui_main}.cpp`；`.fun/<平台>/compile_commands.json` 共 8 个编译单元，**没有任何 `src/activity/*`**（编译宏 FUN_BUILD=1）。结论：**IDE 体系** activity 参与编译并由它 include logic.cc；**fun build 里 `src/activity/*` 完全不参与编译**，`src/logic/*.cc` 直接当编译单元，业务 `src/**/*.cpp` 由 fun 扫描收编——所以「改 activity / 改 CMakeLists 来修构建」都是错路。已改：① `project_tools.PROJECT_SPEC`（caveats 增两套编译体系 + 明确禁止改 `.fun/<平台>/CMakeLists.txt` + 修正手写 .cc 口径）；② `knowledge/devflow/cli-fun-toolchain.md` 新增 §4.5「编译单元口径（IDE vs fun）」含实测表与纪律；③ `knowledge/devflow/activity-code-skeleton.md` 新增 §0 两套编译体系；④ `knowledge/devflow/page-architecture-spec.md` §4-4 同步该口径。检索词已覆盖「fun 编译 activity / activity 不参与编译 / CMakeLists 要不要改 / 编译单元」。',
    '2026-09-17: **页面架构口径前置（修「多 Activity」误读）** v0.27.79-open（钟工反馈：AI 跑的时候把工程理解成多 Activity —— 正确结构是单 Activity：mainActivity + mainLogic.cc + main.ftu；5 个页面应放进同一个 ftu 的多个整屏 window、用 showWnd/hideWnd 导航，复杂业务拆 src/ 业务域类）——① project_tools.PROJECT_SPEC（get_project_spec 返回值，AI 写代码前必调）页面架构条目改为默认口径前置：一个工程默认只有一个 Activity；多个页面 ≠ 多个 ftu/Activity，同业务域内页面 → 同一个 ftu 内多个整屏 window + showWnd/hideWnd；只有跨业务域、需独立返回栈、超大页面才拆新 ftu；② knowledge/devflow/page-architecture-spec.md §0 增「默认口径（先看这条）」段，检索词补单 Activity / 多 Activity / 一个工程几个 Activity / 多个页面怎么放；③ 修正 knowledge/devflow/ftu-json-pipeline.md 里误导行（一个 ftu = 一个界面 = 一个 Activity）→ftu = Activity = 独立编译单元，页面 ≠ ftu，一个 ftu 通常放多个整屏 window。门禁 check_consistency --with-tests 全绿。',
    '2026-09-17: **Z235X 平台入库（IDE 模板 + platforms 登记 + bin_tools 占位）** v0.27.78-open（钟工给 IDE 工程 HelloWord_z235x，要求入库）——①**新增模板 `templates/HelloWord_Z235X`**（22 文件，与 HelloWord_Z21 同构：.cproject / .project / .settings×4 / Manifest.xml / .deps.lock / .gitignore + src/{Main.cpp, activity, logic, uart} + ui/main.ftu）；源工程里的 `Release/`（libzkgui.so / *.o / *.d / makefile 等构建产物）**不入库**；工程名规范化为 HelloWord_Z235X；依赖 easyui 2.9.0 / log 1.0.0 / zkhardware 1.1.0 / zknet 1.1.0。②**`platforms.py` 单一真相**：`PLATFORMS` 新增 `Z235X`（arch=arm，template=HelloWord_Z235X，binTool=z235x；SSD2355），并从 `PACKAGE_ONLY` **移除**（不再只是包生态平台）；包生态键 `z235x` 与 package_catalog 不变（17 个包）。③**设备端预编译工具缺口（如实标注、不伪造）**：`bin_tools/z235x/` 暂只有 README 说明占位——touch / busybox / ui_test / mt_test / zkshot **尚未编译**（需 Z235X 样机 + 该平台工具链；架构与现平台可能不同，禁止拿其他平台 ELF 顶替）→ `flythings_gen_ui_test` 在该平台会**明确报「未预编译触摸注入工具」**并列出可用平台，不静默。④顺带收口：bin_tools 发现入口（get_version 的 binTools / flythings://tools）不再把目录里的 README.md 当设备端工具。',
'2026-09-17: **ftu 口径收口（新增 knowledge/devflow/ftu-json-pipeline.md）+ 3 op 加指针 + README 精简** v0.27.77-open（钟工：客户检索「ftu 如何开发 / 怎么修改 ftu 布局文件」命中 3 条 wiki 镜像的 **IDE 口径**、quality=low_confidence(0.248)，而全库没有一篇讲 ftu 是什么/能否手改/能否逆向）——①**新文档**：ftu = 设备实际加载的布局（二进制，文件头 `ZKSW`；一 ftu = 一界面 = 一 Activity）；链路 `ui/*.json`（唯一源）→ fui pack → `ui/*.ftu` → fun launch(`/tmp/ui`)/fun pack(update.img)；**`fun build` 自己不做 json→ftu**（pack 由 fui 干，`build_ui_flow` 第②步按需跑）；正确改法四条（edit_apply / fui_pack / build_ui_flow / 命令行）；**区分 IDE 工作流（wiki 那几篇）与本 MCP 代码工作流（json 为源）**；禁手改五条理由 + `edit_ftu` 正确姿势（给变更→落 json→再 pack，不是改二进制）；逆向限制（内置 fui 只 pack、unpack 空壳）；resources 关系（json 写 `images/xxx.png`，落到设备 `resPath`=/tmp/ui）；8 条客户原话 FAQ。②**实测**（索引重建后 1412 chunks/194 篇）：『ftu 如何开发 怎么修改 ftu 布局文件』low_confidence(0.248，top5 里 3 条 wiki) → **ok(1.0)，top1 = 新文档**；『ftu 可以手写吗』『main.ftu 是什么文件』同样 → ok(1.0)。③**3 op 加最短指针**（fui_pack/edit_ftu/build_ui_flow）：「ftu 是 json 编译产物：改布局改 json 后 pack，不要手写/手改 ftu」+ 指向新文档；删掉 `edit_ftu` 里「布局修改以 ftu 为目标」的口径矛盾话并压缩冗余；docstring 11906 → **11987/12000**（单 op 最大 893）。④**README 精简**（钟工要求只留「一键安装 + 功能说明」）：315 行/21KB → 122 行/7.1KB，删目录/工具长表/组件表/项目结构/CLI 表/FAQ/样例，安装命令原样保留。⑤**门禁口径随之改**（check_consistency + smoke）：README 工具数改为「扫全部『N 个工具』提法对齐」，wiki 篇数对 `tools_manifest.json docs.wikiFiles` 核，用例数承载处改 `tests/README.md`；smoke 隐私扫描改为只扫 git 已跟踪 + 未忽略文件（`.fun/` 构建产物不再误报）。',
'2026-09-16: **html2json 的 CSS 出图一律走 SS + 修 `border-radius:50%` 认不出** v0.27.76-open（钟工拍板三条口径）——①html2json 处理 CSS 效果（渐变/圆角/阴影）出图**一律 SS（`ss=4` = 每像素 16 子采样）**，**不再保留 1x + α 羽化那条路**（固定本地脚本的工作，不额外耗 token）：`gen_gradient`/`gen_gradient_stops`/`gen_shadow_card`/`rounded_card`/`gen_btn9` 加可选 `ss=0`（`SS_DEFAULT=4`），新增 `_ss_mask`/`_ss_rounded_rect`/`_ss_outline` + 公开 `ss_shape_mask`（自画合成层用 `ImageChops.multiply` 只缩 alpha，禁 `paste(color,mask)` → 防暗边）。②**`gen_res.rounded_rect` 默认行为不变**（FT-008：1x 直画 + α 羽化 σ0.5）——SS 仅在 ①html2json 出图 ②调用方显式 `rounded_rect_ss`/`ss>0` 时生效；`ss=0` 路径与改动前**逐字节相同**（机器比对）。③**顺带修真 bug**：`border-radius` 旧解析只认「数字+px」→ `50%`/无单位认不出（实测 48×48 圆形 corner α=255 方形）→ 新增 `_radius_px()`（px/无单位/%，按 min(w,h)/2 钳制）。**实测**（理想 = 同算法 16x；边界带 mean/p95，单位 /255）：药丸渐变 80×40 35.4/97.9→**5.3/22.8**、正圆 48×48 31.7/74.0→**4.0/8.0**、圆角渐变卡 r16 43.9/153.0→**10.0/22.0**、阴影片 α-max 170→**20**、阴影药丸 125→**23**；暗边回归 ≤4/255。用例 158→**164**（`tests/test_html2json_ss.py`）；口径入库 `knowledge/devflow/ui-asset-rules.md` #8 + `html-subset-quickref.md` §7.1；证据 `temp/html2json_ss/`。',
'2026-09-16: **切图抗锯齿档位 + thumb 尺寸核对盲区收口** v0.27.75-open（钟工：「滑块圆钮/开关有锯齿，图片和控件尺寸对不上」）——①**强曲率形状出图口径（FT-010）**：`gen_res.rounded_rect_ss(w,h,radius,fill,border=None,border_w=1,ss=4)`（≥4x 超采样 + LANCZOS + alpha 预乘，专给圆/圆钮/药丸/细圆条）；以 16x 超采样覆盖率当理想值实测（边界带 mean/p95，单位 /255）：药丸 35.4/97.9→5.3/22.7、圆 40.9/102→3.7/11、圆钮 42/105→6.3/17、细圆条 21/43→3.2/6，ss=8 时 p95<4；大半径卡片继续 `rounded_rect`（1x+α 羽化，轮廓与 1x 直画逐像素一致）→ **默认行为逐字节未变**（28 组输入 sha256 全同），`_aa_mask`/`gen_gradient`/`to_9patch` 补了分工说明。②**thumb 尺寸核对盲区**：`verify_assets`/`check_all` #11 #17 原先只比控件 position，滑块 `thumb` 子盒（自有尺寸）从不核对 → `sk_thumb.png` 31×31 配 `thumb.size` 30×30 一路 PASS。现盒子来源 = position **+** `thumb.size`：自动生成 thumb 图失配 → `mismatch[]`=FAIL，手绘 thumb（官方基准工程 SampleUI-New 35×34 vs 33×35）→ 仅 `stretched[]`，`thumb` 无 `size` → 跳过 + `skippedNoBox[]`；编辑器预检同口径。③实测：案例 `lvgl-widgets-uiv1` 三平台 check_all 全 PASS、0 mismatch；反例（thumb 改 25×25）#11/#17 双报 FAIL；全仓 95 工程只多 1 处真失配（旧案例 `lvgl-widgets/f133` 待重出图）。④口径入库 `knowledge/devflow/ui-asset-rules.md` 铁律 #8/#9 并同步 `ui-layout-verify.md`；用例 148→158。',
'2026-09-16: **LVGL 案例按 ui_v1 重迁 + 组件包补全（Calendar 新包 / Chart 0.2.1）+ Z21 真机验收** v0.27.74-open（钟工：「lvgl 这套 Demo 再次迁移一次，优先 FlyThings 控件 + 自定义控件补全能力，自定义控件最终落到通用组件包」）——①新案例 `projects/translate/lvgl-widgets-uiv1/`（开发工作区）：TRANSLATE.md 按五级口径重写（每行挂 `mcp_control_map.json` 的 `level/notes/ref`），v1 的 5 处手写自绘全部换成组件包（`Chart` LINE/BAR/RING/SEGMENT/GAUGE、`TabView` 切页、`Calendar` 日历），开关改两态 `button__N`（绕 `checkbox__` 工具链缺陷），logic 826→746 行；双平台 `fun build` + `check_all` 全 PASS；②新包 **`components/ui_v1/Calendar/`**（四件套 + `example/` + 6 张 Z21 证据）：42 textview 日号网格 + 容器原点 + `getPosition()` 触摸反算 + 翻月/选中/标记/今天，不装触摸监听；③`Chart` **0.2.1**：新增**分段环** `setRingSegments()`（权重归一 / 段间 2° / 最多 8 段，`RING` 外返回非 0）+ **修 `drawGrid()` Y 刻度值序 bug**（槽位 0 原本画在最下线却写 max → 数字上下颠倒、图形是对的）；④Z21 九项交互全过：切页/点页签 + 下划线互斥 420px↔0px、滑块跟手 87%、开关两态、调色盘换色（`PtLine` 38,911 px 变红）、性别 modal、日历选中并回填、环/仪表动画；⑤平台事实：`div.modal` **内** textview 底色画不出（`bgColorTab`/`setBackgroundColor`/`setBgStatusColor` 三条路），**普通容器里能画**（反例：顶栏下划线 420 px 实心蓝）——先前「ZKTextView 画不出底色」的结论**已收窄到弹窗内**；painter 与刻度 textview 有 **z 序**要求（json 里 painter 必须写在先，否则整列刻度被不透明底盖住，静态检查发现不了）；⑥`mcp_control_map.json` 里 7 条日历族（lvgl/qt/android/miniprogram/emwin/mfc）`ref` 指向真包路径。⑦新增知识：`knowledge/uicontrols/widget-code-api.md` 的 `ZKPainter` 段补 **z 序**口径（json 后定义 = z 更高，painter 要写在叠加文字之前，否则整列刻度被不透明底盖住；静态检查与本地预览都发现不了）。',
'2026-09-16: **控件映射能力（机读索引 + MCP op）+ ui_v1 口径收口** v0.27.73-open（钟工修正口径：**有一一映射的控件走「映射能力」，不写散文**；`components/ui_v1/` **只放「FlyThings 没有的能力」的自定义控件包**）——①新增仓库根 `mcp_control_map.json`（★跨框架控件映射机读索引，**212 条**：lvgl 32 / qt 40 / android 43 / miniprogram 38 / emwin 29 / mfc 30；每条 = `name/aliases/target/level/json（可直接粘，字段全集显式）/notes/ref`）+ `targets` 41 项（我们侧控件的 caption/指针/片段）；L3 必须给 `ref` 指向 `components/ui_v1/<包>`，L4/L5 在 notes 给替代建议；②新增 MCP op **`flythings_map_control(query, source=\'\')`**（工具数 34→35）：控件名/别名模糊匹配（忽略大小写与下划线/连字符，可限定框架），命中回 `level/notes/json/ref/control`（+`alsoMatched`），未命中回 **`NO_HIT`** + candidates + 「缺口五级」处置与 ui_v1 指针，source 写错回 `BAD_SOURCE`；③口径收口：`TabView` **迁出控件包** → `components/ui_v1/_mapping/TabView/`（此类**有平台对应控件 pagewindow**，只作映射参考：json 片段 + 手感参数 200/1/60/0 + 高亮双向同步 + Z21 证据；带 `_mapping/README.md`）；`components.md` 改**三段**（已实现自定义控件 `Chart` / 映射项 / 计划中的自定义控件 Calendar·TimePicker·WheelPicker·RichText·TableGrid·BadgeToast·Pseudo3D）；`ui_v1/README.md` 目录约定写死「有对应控件的映射项不进 `<源控件名>/`」+ 「建包前先证明平台真缺」；④新增知识 `knowledge/uicontrols/control-mapping-capability.md`（op 用法/覆盖范围/命中不到怎么办/与 ui_v1 分工/「有对应控件就直接用」的 json+代码示例），`framework-control-mapping.md` / `control-map.md` / `gap-list.md` 补机读入口指针。',


    '2026-09-16: **ui_v1 从「映射表」改成「能用的控件包」——首批 2 个包（TabView / Chart），Z21 真机验收** v0.27.72-open（钟工：控件差异做成控件，一源控件一目录）——①`components/ui_v1/<源控件名>/` = 控件包（`README.md` 替代谁/接口/限制/验收 + `platforms.md` 逐平台实测 + `Manifest.xml` + `include/zk/` + `src/` + `example/`（最小可跑工程 + `evidence/*.png`））；基线文档保留作索引；②**TabView**（页签页容器，基于 `pagewindow`）：滑动切页 + 页签高亮/下划线双向同步（真源 = getCurrentPage，幂等）+ onPageChanged + 手感默认值 200/1/60/0（无运行时 setter → 默认值 + 自检）+ 不接管触摸；③**Chart**（ZKPainter 自绘）：LINE/BAR/RING/GAUGE + 网格刻度（textview 池同父）+ 混色近似 alpha；setSeries/appendPoint/setAxisRange/setRingPercent/setGaugeZones/attachLabels/setStyle/refresh（**改数据必须 refresh**）；④**Z21 验收**：TabView 滑动后 `page=1 (当前页=1 OK)`、下划线 x 20-199→212-391、页签蓝/灰互换、页内按钮点 3 次计数 0→3；Chart `ui_diff` 换数据 28 处/39,489 px、追加点只折线变 12,599 px；⑤新平台事实：`fun build` 自动编 `src/**/*.cpp`；Z21 `/res` 只读 + `/data` 满 → 只部署 `/tmp`；**残留 `zkshot` 会把 zkgui 卡在 D 状态（黑屏、kill -9 无效、只能重启）**，抓屏只用 framebuffer；⑥`components.md` 改两段（已实现 2 / 计划 13，目录名用源控件名）。',
        '2026-09-16: 跨框架控件映射对齐 + ui_v1 基线 v0.27.71-open（钟工：对齐一下控件然后入库；把 LVGL 有的控件我们替代的放 components 目录新建 UI 目录）——①新建 `components/ui_v1/`（本代框架基线 = FlyThings IDE + easyui + 受限 HTML→json→ftu；将来新方案另开 `ui_v2/`）：`README.md`/`platforms.md`/**`control-map.md`（★控件映射权威表）**/`logic-map.md`/`gap-list.md`（G-01~G-36 + 五级处置 + 3D 策略 + T1~T12）/`components.md`/`examples/README.md`；②缺口统一五级 `L1 等价/L2 组合/L3 自绘/L4 降级/L5 不支持`（旧案例 A/B/C/D 按换算表逐条映射；并列取差、自绘记 L3）；③★tab 类控件（`lv_tabview`/`ViewPager+TabLayout`/`swiper+tab`/`QTabWidget`）一律走 `pagewindow`（ZKPageWindow，自带滑动切页 + `onPageChange`），**禁止**「多个整屏 window + 按钮」拼（丢手势滑动）；④3D 写死：Z21/F133 无 GPU/无硬解 → 一律伪 3D/2.5D，真 3D 仅 V85X（disp 分层）验证过；⑤工具链/平台事实进表（`fun` 不为 `checkbox__` 生成宏/指针/回调；设备侧 `libeasyui.so` 无 `getAbsolutePosition()`（用了整屏黑）；`fun launch`(Windows) 把 `resources/images/*` 推成字面平铺名；listview 行文本要 `setText("")` 否则与 subItem 叠字；`html2json` 把 `#000000` 当未设置）；⑥知识库只放摘要 + 指针（`knowledge/uicontrols/framework-control-mapping.md`）。',
        '2026-09-16: 平台通用性三坑入库 v0.27.70-open（均实机核实）——①**双缓冲/pan 偏移 → 抓屏抓到上一帧**（平台通用，重点）：应用已重绘但抓到的是**上一帧**；判据 = `device_screenshot` 返回 `screenInfo.virtualHeight ≈ 2 × height` 且 `pan` 非 0（实测 Z21 = 1024x600/virtual 1200、F133 = 800x1280/virtual 2560）；对策 = 抓屏前后读 `fb0/pan`（或连抓两次比 md5，不一致重抓）、触摸 `touch long x y 250` 触发重绘后再抓、像素 diff 前先确认拿的是新帧；**这是抓图/验收侧问题，不要为此改应用逻辑**；②`html2json` 把 `#000000` 当「未设置」（`data-color`/`data-bg` 走 `to_dec(...) or 默认值`，0 是 falsy）→ **要纯黑请写 `#010101`**；③ZKPainter `drawArc` 实参口径存疑（既有文档写「外接矩形+起止角」，本次按 `(cx,cy,rx,ry,start,sweep)` 在 Z21(easyui 2.6.0) 真机渲染正确）→ 标「待官方/沛哥确认」，用前小图自证。落点：`knowledge/devflow/device-screenshot.md` §3.3-1、`devflow/html-subset-quickref.md` §4、`uicontrols/widget-code-api.md` §ZKPainter。',
    '2026-09-16: ListView 两个高频坑 + 设备部署体积预算 知识入库 v0.27.69-open（Z21 真机实测）——① html2json 生成的 listview item.text 默认写死 "ListItem" → 列表每行末尾常显一个 ListItem（已改为默认空串，两份 ui_tools 已同步）；② refreshListView() 不改变滚动位置 → 日志/监控类列表必须 setSelection(count-1) 后再刷新（顺序不能反），否则屏幕永远停在最早那几行、看起来“数据不更新”；另入库「小内存设备部署体积预算」：/tmp 是 tmpfs 吃 RAM（Z21 仅 36MB，撑爆会 OOM 杀 zkgui 导致设备重启）、字库按工程用字裁剪（新增 ui_tools/font_subset_by_project.py，872KB→84KB）、设备重启会清空 /tmp（含 EasyUI.cfg）必须整包 fun launch、adb push 后需 chmod',
    '2026-09-16: 多设备设备选择修正 + 知识入库 v0.27.68-open（沛哥报「fun launch 在同时连着 WiFi adb 时静默失败：adb 看到 2 个设备就报 more than one device/emulator、fun 把输出吞了 → 资源没推上去、设备仍跑旧 ftu；改了 ui 加控件、build 通过、launch 看着成功但界面不变，极易误判成框架不支持该控件」；验收后**现象方向成立、机制描述要改**）——①**实测机制（扫 fun.exe 字符串 + 伪造 adb host server 抓包）**：fun launch 走 fun 自带 Go adb 客户端（`pkg/adb` → 直连 adb host server `127.0.0.1:5037`：`host:version`/`host:devices`/`host:transport <serial>`/`shell:`/`sync:`），**不 shell 出 adb 二进制**（全二进制只有 `adb -s %s shell chmod 777 %s` 与 `adb -s %s shell %s` 两处，**都带 `-s`**）→ fun **根本不会**报 adb 的 `more than one device/emulator`，也就没有「吞 adb 输出」；②**真实行为：多设备时 fun 不报错/不警告/不询问，按 `adb devices` 列表顺序取第一个**（实测两种顺序各跑一次：WiFi 在前推 WiFi、把另一台放前面就推那台；pty 交互模式一样），唯一拦点是平台校验（`shell:getprop \'ro.product.model\'` 对比项目平台，不匹配才 `FATAL platform not match`；push 真出错也 `FATAL` + exit 1）；③**MCP 侧真 bug 修复**：`project_tools._run_fun` 原先**把 device 参数丢掉**（注释「fun launch 不支持 -s」），而 `build_ui_flow` docstring 又叫 AI「传 device=IP 重试（走 fun launch -s）」→ 文档与实现不符，多设备时会静默推错设备；现改：`cmd==\'launch\'` 且 device 非空时**追加 `-s <serial|IP>`**（实测可用），device 为空且检测到 **>1 台在线设备**时在返回体里给 `warnings`（不静默）；`kb_tools.flythings_build_ui_flow` docstring 同步改正「不支持 -s」；④**判据实测**：单设备 `fun launch` 后设备 `/tmp/ui/main.ftu` 与本地 `ui/main.ftu` **字节+md5 完全一致**（1419 B / `FDC802FF232328DD5395EB433F8BA223`；launch 前是旧 app 的 1755 B），设备侧无 md5sum 用已推 /tmp/busybox、`ls` 不认 `head`；⑤**知识入库**：`knowledge/devflow/cli-fun-toolchain.md` 新增 §7「多设备（USB + WiFi adb）时的设备选择陷阱」（机制/危害/正确做法/判据命令/WiFi adb 用法）+ §3 命令表改正 `-s` 行 + 检索词补充；⑥**复现手法留档**：真机只有单台可达时，可用**伪造 adb host server（127.0.0.1:5037，报 2 台设备）**抓 fun 发的每条请求（注意 Windows `SO_REUSEADDR` 允许多进程同绑 5037 → 排查前先 `netstat -ano | findstr 5037` 杀干净）。',
    '2026-09-16: 图标库（Tabler MIT）入库 v0.27.67-open（钟工：「把 UI 设计常用的图标全下进来，免得后期还需要处理」；起因：AI 生成的界面切图风格/比例反复不一致，每次都要人回来确认）——新增资产型模块 `components/icons/`（**随包发布**，其他 AI 可直接取）：①**选型定论**——Apple **SF Symbols 许可禁止再分发**（不能进发布包）、Google Material Symbols 虽 Apache-2.0 但观感偏“谷歌”，最终定 **Tabler Icons（MIT）**为唯一图标源（24 网格 + 2px 圆头圆角线框最接近 iOS，且每图带 `-filled` 成对变体 = 现成 on/off 两态）；②**收录规模**——vendor 全量 `icons/` 4754 outline + `icons-filled/` 1019 filled（4.0MB，**排除 376 个 `brand-*` 品牌 logo**，商标风险不入包）；语义表 198 条（含分级/制式：`wifi-0/1/2`、`signal-1..5`、`cell-signal-1..5`、`2G/3G/4G/4G+/5G/6G/LTE`、`battery-0/25/50/75/100`、竖版电量、蓝牙/路由/网络断开、broadcast/radar/rss/sensor），catalog **203 图标 / 305 产物**；③**唯一入口 `scripts/gen_icons.py`**：`--vendor-name <语义名> --size N|WxH --color R,G,B --out <项目>/resources/images`（**像素尺寸严格 == 控件盒**，颜色**烘焙**进 PNG——FlyThings 无 tint API），名字兜底支持 Tabler 原名（`weather.sun`/`--tabler antenna-bars-3`），另有 `--svg` / `--svg-dir` / `--list-vendor [分类]` / `--vendor-set common|all` / `--sheet`；④**小尺寸策略（实测）**——生成器用“半像素对齐线宽 + α 对比度整形（0.40/0.60）+ 去雀斑”，22px 中间值像素 ≤ 9.7%、不发虚 → **≥22px 用 outline、≤20px 用 filled**；⑤**合规**——唯一第三方义务 = 保留 `vendor/tabler/LICENSE`（MIT，tarball sha256 已登记 `VERSION.txt`），图形只做「单色化 + 等比缩放」未改路径；⑥知识库新增 `knowledge/devflow/icon-library.md`（选型依据 / 命令 / 铁律呼应 / 小尺寸策略 / 合规 / 坑），模块四件套 + `THIRD-PARTY.md` + `selfcheck.py`（命名/尺寸严格/透明度/清单/可渲染）齐备，`selfcheck` PASS 744 张。\n',
    '2026-09-15: 设计稿字体对齐入库 v0.27.66-open（沛哥："字体应该更新为设计一样的，这个应该说明到 MCP 里面，不然做出来的效果跟实际效果差异很大"）——`knowledge/devflow/custom-font-config.md` 新增「设计稿字体对齐」一节，全是 Z21 真机实测：①**还原设计稿前必须先换字体**（布局坐标全对但字形/字重不对，是还原度最大落差）；②多字体**按文件名 ASCII 升序，排最前的是全局默认**——默认字体必须是含中文的那个，否则**汉字全变方框**（实测：Poppins 当默认 → 豆腐块）；个别控件要拉丁几何体用 `setFontFamily("Poppins-SemiBold")`（不含 .ttf）；③**Z21 低内存坑**：投 2.5MB 级中文字体 → 黑屏 + 反复重启，换 872KB 的 `zkswe-hans-common.ttf` 立即恢复；`fun launch` 每换一次字体往 `/tmp/font/` 写一份且旧的不删，tmpfs 到 ~72% 使用率应用就起不来（上传前先 rm 旧字体）；④字号按设计稿给足，塞不下拆行不要缩字号。\n',

    '2026-09-14: V85X 硬件 H264 播放器用法入库 v0.27.65-open（钟工：把 V85X 扩展屏 AP+P2P 工程 result 下的 H264 解码库实践，结合 awh264player@1.0.0 包与 V85X 工程检讨后入库，避免重复踩坑）——新增 `knowledge/v85x/h264-player-usage.md`，入库前做了现场核对并纠正一处 P0 口径：①**两套 API 不可混用（本次最贵的坑）**——官方包 `awh264player`（v85x 1.0.0，包内仅 CHANGELOG + `include/h264_player.h` + `lib/libawh264player.so`）提供的是 **`h264_player_*`**（13 个，含三参 `h264_player_init` 与四参 `h264_player_init_ex`）+ `h264_multi_player_*`（10 个）**没有 `zk_h264_player_*`**；`zk_*` 是厂商参考工程给的**静态库门面**（`libzkmedia.a` 内同时含 `zk_*`+`h264_player_*` 符号与 `dlopen("libawh264player.so")` 字符串，实测符号表）——原稿整篇按 `zk_*` 写却引用包，直接照抄会在 V85X 上 `undefined reference`（V85X 也**没有 `zkmedia` 包**，F133/F136 才有），本篇把两条路线分开写并给选路判据；②**`fun.json` 优先于 `Manifest.xml`**：只把 `<package id="awh264player">` 写进 Manifest.xml 时 `fun install` 报成功但 `.fun-lock.json` 里 `"v85x": {}`（**静默不装**），依赖必须写 `fun.json` 的 `dependencies`；③**`lib-no-link` 部署矩阵**：不参与编译、`fun launch` 不推（调试期手推）、`fun pack` 进镜像 `lib/`→设备 `/res/lib/`（ld 路径已含，固化后免推），⚠️ **同名库长期留在 `/data` 会遮蔽 `/res/lib` 的固化版**（ld 路径最前，升级了库却跑旧的且 0 日志异常）；④保留真机实测干货：`ZKMEDIA_H264_VBVSIZE` 未设 → **起播静默退出**（头号坑，必须在库加载前 setenv，改完重启应用）、`MemAvailable<3MB` 必挂且 OOM 后不自己回来（要重启板子）、720p 缩放档位内存三档（不缩放 2.6MB / 1/2 4.1MB / 1/4 6.5MB）、`get_picture_count` **不是队列长度**（背压用媒体时间）、`set_rot` 后必须重发 `set_crop`、与 MPP 互斥；⑤显示层/透明窗口/图层释放**不复制正文**，只交叉引用 `v85x/display-layer-debug.md`（避免双份漂移）；⑥**如实标注未验证项**（路线 A 在 V85X 上未做真机播放验收、多实例 API 未实测、固化后 /res/lib 自加载待验收）；⑦附可编译示例工程 `demos/h264player-v85x/`（bin 工具：env + init_ex + 回调 + 喂 AU，`fun build -p v85x` 通过）。',
    '2026-09-14: `touch check` 真机验收 + 落点判据收细 v0.27.64-open——①**真机验收（axs_ts/MT-B 板，PocketGame）**：`touch check 58 160` → 应用日志 `PocketGame touch: action=1 x=58 y=160` → `action=2 x=58 y=160`；`check 400 700` → `action=1 x=400 y=700` → `action=2` 逐点相符 ⇒ 判定与注入闭环均通过，**raw==屏幕 1:1 证实**；②落点结论由“两轴差 >2 倍”收细为**三口径**：两轴都在 1±5% → 量程≈屏（直接写屏幕坐标，别 --scale）；两轴比例一致（差≤5%）且≠1 → 需 --scale；**两轴不一致（>5%）→ ⚠ 声明量程跟屏不对应，先按 1:1 注一次看日志、别用 --scale**（axs_ts 1.00 vs 1.20 / SPINOR 2.14 vs 0.75 都落在这一类）；③`--scale` 自身改成**同一口径**（不一致 >5% 即警告并取消换算），使 check 的预测与 --scale 的实际行为完全一致；④README/kb 同步；六平台重编入 bin_tools；闸门 41/41 PASS。',
    '2026-09-14: `touch check` 一条命令自检（把“要不要先 try”变成“读结论”）v0.27.63-open（钟工：两种触摸都存在，这个关于触摸测试的是否需要提前 try 还是本身提供的 touch 就可以支持到位？→ 加入 touch check）——①新子命令 `touch [dev] check [x y]`：一次性输出 **节点 / 协议（带判定依据）/ 坐标轴可用性（声明≠可用）/ 量程 vs 屏幕的落点结论**；给了坐标就再注一次 tap 并告诉你验证命令（`/bin/logcat -d | grep -i -e action -e touch`，应用侧应 `action=1`→`action=2` 且坐标一致）；②**退出码机读**：0=可直接用 · 3=无可用节点（并提示 `-v list` 看每个节点被跳过的原因）· 4=有落点风险或注入失败——AI/脚本可直接分支，不用看自然语言；③落点结论三种口径：量程==屏 → 直接写屏幕坐标（**不要 --scale**）；两轴比例一致且 ≠1 → 需要 --scale；两轴比例差 >2 倍（声明量程跟屏不对应，V85X 实测）→ ⚠ 按 raw==屏 1:1 先注、别用 --scale、确需换算用 `--screen WxH`；④与 0.27.62 一并将 `key`/`sweep`/`raw`、`usable` 判定写进 README 与 kb；六平台重编入 bin_tools；闸门 41/41 PASS。⚠️ 本次设备（adbd over USB）反复掉线，`check` 待板子在线后补真机验收。',
    '2026-09-14: touch 对齐工程内 pginj.c（增能力 + 判据硬化）v0.27.62-open（钟工：S:\\projects\\LearningProject\\input 放了 pginj.c，就是处理这个问题的；稍后给一台对应问题的机器）——①**增能力（对齐 pginj.c 能力面）**：`touch [dev] key <code> [ms]`（物理键注入）、`sweep <from> <to> [ms]`（扫键码区间找真实键值）、`raw t:c:v [t:c:v ...]`（原始事件逃生口，末尾一次 SYN）；键注入不要求触摸节点（gpio-keys 无 ABS 也能用）但必须 `-d` 指定节点（不自动挑触摸节点）·②**判据硬化（转自 pginj.c 的 probe）**：坐标轴"声明≠可用"——`ABS_X/Y` 量程 0..0 的轴写不进任何坐标（V85X/gt9xx 实测就长这样，单点路径会把点击全送成 (0,0)），故新增 `use_abs_xy`/`use_mt_xy`（要求 `maximum > minimum`）参与评分/协议判定/兼容写轴；`touch info` 新增 `usable` 行直现这两项，不再把无效轴当可用；③**真机验收（axs_ts / MT-B 板，event4，USB 20080411）**：`tap 58 160` → 应用日志 `touch action=1 (58,160)` → `action=2 (58,160)`；`swipe 240 600 240 250 24 12` → 一串 `action=3`（240,279→255 插值）+ `action=2 (240,250)`；`raw 3:57:1 … 0:0:0` → `action=1 (100,100)`；`key -d /dev/input/event3 103 60` rc=0。⇒ **MT-B 三铁律 + 量程判定两条对齐后，我们自己的工具在这块屏上也能点**，不必依赖工程内自研注入器；同一 USB 位先后接入过两块板（SPINOR/gt9xx=MT-A、axs_ts=MT-B），`touch list/info` 均自动判对；④知识库 `knowledge/devflow/touch-inject-autotest.md` 补实测验收段 + 工具面差异；六平台重编入 bin_tools；闸门 `check_consistency.py --with-tests` 41/41 PASS。',
    '2026-09-14: 触摸注入 V85X 真机校正（3 修 1 补）v0.27.61-open（钟工：usb 上挂的板子测一下，V85X 触摸模拟不一样）——①**真 bug 修复**：`touch` 的 `if (ioctl(fd, EVIOCGBIT(0,...)) == 0)` 在**成功返回拷贝字节数的内核**上永远为假 → 自动扫描全灭、`touch list` 报 "no input device found"（V85X SPINOR 实测返回 4；改 `>= 0`，**移植任何 evdev 工具都按 `>= 0` 判成功**）；②**MT-B 三铁律落地**：抬起帧 `TRACKING_ID=-1` 与 `BTN_TOUCH=0` 由两帧合并为**同帧**（原写法与 V851s「已验证帧」不一致，可能留"幽灵手指"）；down/up 帧补 `ABS_MT_PRESSURE`（部分驱动要 pressure>0 才认接触，量程取 EVIOCGABS 中值）；③**`--scale` 防护**：改用 `fb0/modes`（可见分辨率）而非 `virtual_size`（V85X/SigmaStar 常 2× 双缓冲 → Y 折半），并在「声明量程与屏两轴比例差 >2 倍」时**警告并取消换算**（SPINOR 实测 mtX 0..1024/mtY 0..600、屏 480×800，但实际 raw==屏幕 1:1）；新增 `--screen WxH`、`-v/--verbose`（`TOUCH_DEBUG=1`）打印探测失败原因；④**知识入库**（`knowledge/devflow/touch-inject-autotest.md`）：V85X 两块屏两种协议实测表（SPINOR/gt9xx=**MT-A 且 ABS_X/Y 不存在**；V851s/axs_ts=**MT-B 且 ABS_X 范围 0..0**）+ 三条坑 + 宿主 adb 陈旧 server 处置（`taskkill /IM adb.exe /F` 比拔插有效）；⑤真机验收：六平台重编入 bin_tools；SPINOR 上 `touch list` 判 MT-A、注入 (437,32) 命中右上角按钮（BLE 扫描状态栏 `已停止扫描`→`扫描中`）、`record` 抓帧确认序列（TRACKING_ID/POS/MAJOR/BTN_TOUCH/SYN，无 SYN_MT_REPORT）。',
    '2026-09-14: 「能力不止 op」——bin_tools 设备端工具补齐发现入口 v0.27.60-open（钟工反馈：其他 AI 数完 34 个 op 就断言「这版没有触摸注入」，实际 touch 自 v0.27.40 起一直在 bin_tools/）——根因不是能力缺失，是**发现性缺失**：工具面没有任何出口暴露 bin_tools（get_version 字段里没有、flythings://tools 资源里 bin_tools 出现 0 次），只看 op 清单的 AI 有理由得出错误结论。三处补口：①`flythings_get_version` 新增 **`binTools` 字段**（note + dir + byPlatform + brief + usage）：按平台扫 `<MCP>/bin_tools/<平台>/` 列出 touch/busybox/ui_test/mt_test/zkshot，并明写「**不是 op、不占 op 名额**」+ 触摸注入用法（push → chmod → `touch list` 看节点与协议）；②MCP 资源 `flythings://tools` 末尾补「## 设备端预编译工具（bin_tools/，不是 op，不占 op 名额）」一节（按平台逐工具 + brief，manifest 缺失回退代码清单时同样补）；③分发器入口 `flythings_kb` docstring 加一条⚠️提醒（能力不止 34 个 op，设备端工具在 bin_tools/）。不新增/不重命名任何 op（仍 34），op 数六方与 manifest 不变。',
    '2026-09-14: BLE 组件改为「头文件 + 静态库」发布（不释放源码）v0.27.59-open（钟工：「验证好了后把你的程序做成静态库+头文件发布给到 open 版本 MCP 里面。不释放源码了」）——①`components/ble` 交付物收成三件：`include/zk/zk_ble.h`（唯一对外头）+ `lib/{f133,v85x,z20,z21}/libzkble.a` + `lib/BUILD_INFO.md`（构建凭据：每平台工具链/libc/依赖包版本/公开符号数/大小/sha256）；**`src/` 与源码侧脚本已移出仓库**（内部私有 `private/components-ble/`）；②新增 **`scripts/verify_lib_symbols.py`**：纯 Python 解析 `ar`+ELF 符号表核对每个平台库是否导出全部 30 个公开 API，**不用 `nm`**（Windows 版 binutils 的 `nm` 缺 `liblto_plugin-0.dll` 一调就报错）；实测 4 平台全 30/30；③两个后端保持一套 API：btstack（f133 408KB / v85x 118KB）+ gatt（z20/z21 各 179KB，主从双角色）；④口径写进 `components/ble/platforms.md` §0.6 + README §4：**工具链/libc 必须与库一致**（f133/v85x=musl、z20/z21=glibc）、**不许拿别的平台的头凑库**（`gatt/hci.h`、`gatt-db.h` 含 ABI 相关结构体）——因此 T113/T113EMMC 库本轮**不发布**（本机无该平台 `gatt 1.0.0` 包），如实标注待补；⑤z20 与 z21 的库 sha256 相同（两平台 gatt 17 个头 md5 逐一相同，已核）；v85x 库用本地 `btstack 1.7.2` 头构建（包站为 1.8.0，装包后重跑脚本即可）；⑥`components/README.md` 新增「二进制型」模块形态规范（必须给构建凭据 + 机器可跑的符号自检）。',
    '2026-09-14: BLE 统一门面 v0.2（一个 API 面 + 两个后端，组件级真机跑通）v0.27.58-open（钟工：「蓝牙部分都统一按照昨天定义的新 API，参考微信的方式」）——①`components/ble` 收口：对外只有 `zk/zk_ble.h`（`zk::ble`），**中心侧照微信 wxapi**（openAdapter/startDiscovery/onDeviceFound/connect/getServices/readValue/writeValue/subscribe/onValueChange）、**外设侧照 Android GattServer**（`peripheral::start(PeripheralConfig)` + `onWriteRequest` + `notify` + `setDeviceName`），平台差异一律走 `getCapabilities()`/`backendName()` 能力门控 + `ERR_UNSUPPORTED` 人话 hint（不假装能用）；②**两个后端**：btstack（F133 1.7.2 / V85X 1.8.0，串口 HCI+H5）与 **gatt（Z20/Z21/T113/T113EMMC，AIC USB 模组 + BlueZ 用户态 GATT 1.0.0，主从双角色）**；`src/zkble_backend.h` 自动判定（显式 `-DZKBLE_BACKEND_GATT` / `-DZKBLE_BACKEND_BTSTACK` 优先），两个 `.cpp` 用 `#if` 互斥、同平台只编一个；公共层 `src/zkble_common.h`（日志/AD 解析/扫描过滤/DeviceCache/回调/Waiter）+ 公共 TU `zkble_public.cpp`；③新增能力：`Config.connect_retry` / `reset_before_retry`（Z20/Z21 控制器残留链路 → 自动重试 + 重试前复位，实测第 1 次 ETIMEDOUT、复位后第 2 次成功）；④**组件级真机验证**（不用 demo 代码，只用公开 API 的 bin 工程 `projects/zkble_comp_srv`(Z20 外设) / `zkble_comp_cli`(Z21 中心)）：扫描 → 连接 → `svc fff0` / `chr fff1(0x09)` / `chr fff2(0x06)` → 订阅 ok → `readValue len=5` → `writeValue code=0` → `notify_count=4`；外设 `peripheral::start code=0` + 收 `WRITE char=fff2 data=50494e47`(PING) + `NOTIFY`×4 + 断开后广播自动恢复；⑤真机拓出并修掉的三个 bug（知识性，已写进 platforms.md §0.5）：BlueZ `bt_uuid_to_string()` **成功时返回 0**（原判 `<=0` 当失败 → uuid 全空）、`gatt_db_service_add_characteristic()` 返回的是**特征值属性**而非声明属性 0x2803（取 value_handle 要用 `gatt_db_attribute_get_handle()`）、**控制器已在广播 enable 状态时改参数返 status=12 Command Disallowed**（处置：设参数前恒发一次 `LE Set Advertise Enable(0)`，被拒则复位控制器 + 重试一次，不静默）；⑥编译自检双脚本（`compile_check.sh`=F133/btstack、`compile_check_gatt.sh`=Z20/Z21/gatt）均 rc=0，并叠了一层链接校验（只依赖 gatt + pthread + libc）。未覆盖项（128 位非 base uuid 折回、改名路径、二次重连闭环）在组件 platforms.md §0.5 如实标注。',
    '2026-09-14: 纠正「Z20/Z21 没有中心侧包」——`gatt` 包 **主从双角色** v0.27.57-open（钟工指路 `git.com/AppGroup/Sample`，本仓核对）——①`components/ble/platforms.md` §0.2 表补 `gatt 1.0.0`（Z20/Z21/T113/T113EMMC/V85X 均有；本机 `fun install` 实测拉到 z21 那份，19 头含 `gatt-client.h`+`gatt-server.h`）；②新增 §0.3「主从双角色」：`BleClientDemo`（中心：scan_start/connect + 事件回调，含私有协议测距机）/ `BleServerDemo`（外设：server_start + `_char*_read/write_cb` 自定义 GATT 表），共同前置=Manifest 声明 `gatt` + 把 `hciconfig`/`hcitool` 放进 `src/dependencies/bin/`（BT 走 AIC USB 模组 `aic_btusb.ko`，非串口 HCI）；③实测：两 demo 复制后 `fun install`+`fun build -p Z21` **均出 libzkgui.so**（需把 demo 老依赖 `easyui 2.2.0`/`base-utility 10.1.3` 提到 `2.6.0`/`10.9.3`，否则新模板报 `hasTimerRegistration` 缺失）；④结论修正：Z20/Z21 后端**可做双角色**，`ble` 包 = 开箱外设服务，`gatt` = 底层库（中心+外设）；⑤**已用两台整机（Z20 做外设 × Z21 做中心）跑通主从对传**：扫描→连接→服务发现→订阅 CCCD→断开自动恢复广播全程有日志（bin 工具 `projects/zbble_srv` / `projects/zbble_cli`，因 `fun launch` 在多设备下报 `more than one device/emulator` 而改 adb push 跑；Z21 `/res` 只读无 `/res/bin` 需工具路径兜底）。',
    '2026-09-14: 「启动首次初始化必须先释放图层」定规 + 崩溃重启残留实测 v0.27.55-open（沛哥：用到视频图层的产品，上来第一次初始化要先释放图层，否则程序崩溃重启后系统级图层没释放 → **屏幕永久性异常**）——①doc §2-0 改成双时机：**首要=启动首次初始化**，其次=视频解码返回后，写清 disp 图层是**系统级状态、不随进程退出而清理** → 不释放则每次重启都残留 = 永久异常；②§2-1-3 真机实测（V851 480×800）：造残留黑层 → kill zkgui（init.rc 自动拉起新进程）→ **黑层仍在** → 释放后恢复（证据链完整）；③`check_all #19` 再增补：释放函数名在 src 里只出现 1 次（疑似只定义未调用 / 没在启动路径调）→ WARN 提醒在启动初始化里调一次。',
    '2026-09-14: V85X 图层释放**真机验证（V851）+ 判据纠错** v0.27.54-open（沛哥：USB 上挂的 V851 先验证再发布）——用 `fun create --type bin` 写小工具在 Zkswe_V85X_SPINOR（480×800）实测：①**口径确认**：残留层真造得出，按 **ch/lyr（跳过 UI ch2/lyr0）** 判定能正确关掉、UI 层无损；②**判据纠错（打破参考工程写法）**：「格式区间 ARGB_8888~BGRA_5551 = UI 层」**会漏关**——`RGB_888(0x08)` 落在该区间被误判、**COLOR 模式层读出的 `fb.format` 就是 color 低字节**，结果黑层留在最上面 = **一直黑屏**；doc §2-1-1 改口径（按 ch/lyr，要保险再限定 `mode == LAYER_MODE_BUFFER`）；③**验收陷阱**：黑屏期间 `device_screenshot`（读 fb0）仍然是正常 UI（黑层在 disp 合成器上，两次抓图 diff 0 差异）→ **不能靠 fb0 判黑屏**，要看 `disp/attr/sys` 层清单；④`check_all #19` 增补：源码用格式区间判据 → WARN 提醒改 ch/lyr（参考工程已命中）。',
    '2026-09-14: V85X 视频解码返回后必须 releaseLayer（防黑屏）v0.27.53-open（沛哥：参考扩展屏 AP+P2P 工程把这个知识点明确下去；平台匹配时开发与 check 验收都必须做）——①`knowledge/v85x/display-layer-debug.md` 新增 §2-0 必做场景：V85X（V853/V851/V553）上**视频解码返回后**（解码结束/播放器退出/返回 UI）必须释放残留 disp 层，否则**黑屏**；参考实现 `sys::hw::init()` 里 `_release_layer()`（**按格式跳过 ARGB_8888~BGRA_5551 的 UI/OSD 层**，比写死 ch/layer 稳；`/tmp/zk_boot_anim` 做开机动画保护）。②`check_all` 第 19 项机器核验：平台 V85X + src 有视频解码用法却无释放实现（`/dev/disp`+`DISP_LAYER_GET/SET_CONFIG`/`releaseLayer`/`hwdisplay.h`）→ FAIL；非匹配平台或未用解码 → NOTE 跳过（不误报）。',
    '2026-09-14: fun 工具链口径纠正（fuse → fun）v0.27.52-open（沛哥：fuse 命令行已换成 fun 了，文档没更新吗？）——新增 `knowledge/devflow/cli-fun-toolchain.md`：命令行统一 **fun.exe**（fuse 是旧名），连带改名：构建宏 `FUSE_BUILD`→**`FUN_BUILD`**、产物 `.fuse/`→**`.fun/平台/`**、注册表 `~/.fuse`→**`~/.fun`**（`FUSE_HOME_PATH` 与生成的 CMake 路径仍用老名）；命令表新增 **`fun sim`**；⚠️ **暂时发布的 MCP 不支持 sim**（`_run_fun` 显式拒绝 + 文档标 CLI-only）。老工程迁移一行：`#if defined(FUSE_BUILD) || defined(FUN_BUILD)`（否则 fun build 跳过 UI 绑定宏 → 满屏未声明错，实测复现）。',
    '2026-09-14: 动态旋转/运行时换布局（relayout）v0.27.51-open（沛哥指路 RelayoutDemo）——新增 `knowledge/devflow/dynamic-screen-rotation.md`：`CONFIGMANAGER->setScreenRotate(rot)` + `setTouchRotate(rot)` + `Activity::relayout("xxx.ftu")` 运行时换布局不重启应用；两套 ftu 挂同一 Activity、**控件 ID 必须一一对应**；**需 easyui ≥ 2.9.0**（实测 F133 2.8.0 无 / 2.9.0 有、V85X 2.9.0 有；Z20 3.0.0、Z21/T113 2.6.0 无 → **找 FlyThings 厂家**）；`setScreenRotate` 老版本就有，**只有 relayout 是新的**。',
    '2026-09-14: 视频层抓帧 zkshot + 抓屏 layer=video v0.27.50-open（沛哥：把视频图层抓出来，Z20 与 USB 的 V85X 一起验证）——①**新增 `zkshot`（SigmaStar MI 平台视频层抓帧）**：这些平台**视频是 MI 硬件图层**、`/dev/fb0` 只是 UI(OSD) 层 → 抓 fb0 时视频区是黑的（Z20 实测 800x1280 只抓到 4KB 全黑，而屏上在播视频）；`MI_DISP_GetScreenFrame()` **跨进程只回空帧**（该 API 归“拥有显示层的进程”，layer 0/1 都试过、补 MI_SYS_Init 也没用），改走 **vdec 输出口取帧**：`MI_SYS_Init` → `MI_SYS_SetChnOutputPortDepth(vdec chn0 port0, user=1, que=2)` → `MI_SYS_ChnOutputPortGetBuf` → `MI_SYS_Mmap(phyAddr)` → dump → `PutBuf`；Z20 实测取到 **384x448 fmt=11(NV12) 的真实视频帧**（转 RGB 后颜色正常）。⚠️ 设备 `libmi_sys.so` **只导出非 Pa 版**（用 `...GetBufPa` 直接 symbol lookup error）。②**工具面**：`flythings_device_screenshot(layer="video")`（仅 SigmaStar）——自动推 zkshot → 取帧 → 按 fmt 解码（NV12/YUYV422/32bit/RGB565）落盘，返回 `frame{width,height,fmt,fmtName,stride}`；缺 zkshot 会自动从 bin_tools 推送，拿不到明确报错（不静默）。③**入仓**：`tools/zkshot/{src/zkshot.c, build/build_all.sh, bin/{z20,z21}/zkshot, README.md}`（照 touch 工具形态），成品同步到 MCP `bin_tools/{z20,z21}/zkshot`。④**配套收口**：抓屏 `_remote_size` 再修一处（V85X 的 `ls -l` 打 ISO 日期 `1970-01-01 01:10`，旧“月份锚点”解成 0 → 误判压缩失败白退化成裸帧）；新增 7 条离线回归（gzip 探测/体积解析/NV12 解码/视频层路由）。⑤范围：V85X 视频层机制不同（Allwinner disp 分层，需 `/dev/disp` ioctl），另排；Z21 无硬解（软解 ffmpeg），暂不处理。',
    '2026-09-13: 抓屏修复第二批（ISO 日期解析）v0.27.49-open——`_remote_size` 解析设备侧 `ls -l` 体积时用“英文月份”做锚点，**V85X 实测其 ls 打的是 ISO 日期**（`-rw-rw-rw- 0 0 69416 1970-01-01 01:10 x.bin`）→ 解成 0 → “gzip 已压到 69KB”被误判为未压缩，白退化成裸帧读取（多传 1.5MB，慢且费流量）。改：`wc -c` → `stat -c %s` → 正则三连（英文月 / ISO 日期 / HH:MM）+ 兜底“文件名前最后一个纯数字字段”；新增 2 条回归用例（ISO 格式、stat 回退）。实测修后 V85X/Z20 均走 `busybox-dd-gzip`（live 工具复验通过）。⚠️ 教训：设备侧 `ls/wc/stat` 的**输出格式与 applet 有无**都因平台而异，解析必须多路兜底、不能只按一种格式写。',
    '2026-09-13: 抓屏在 SSD20X/21X 失败修复 v0.27.48-open（沛哥：Z20/Z21 抓屏失败这个修复掉）——根因（真机插桩定位）：busybox 候选探测只测 `echo ok`，而**设备自带 /bin/busybox 是裁剪版：有 echo、没有 gzip**→ 选到它 → `gzip: applet not found` → 远程文件 0 字节 → 报「raw 数据不足…实际 0 字节」把真因吞了（Z20 800x1280 / Z21 1024x600 均复现）。修法四条：①**探测必须验证 gzip 真能用**（`gzip -1 </dev/null; echo rc=$?`，不再用 echo 当判据）；②**自动推送**：设备上没有带 gzip 的 busybox 时，从本仓 bin_tools/<平台>/busybox 逐个试推到 /tmp/busybox 再用（notes 里说明推了哪版）；③**退化通道**：实在没有压缩通道就只读「可见那一帧」的裸数据（dd skip=oy count=h，按体积放宽 pull 超时），保证必成；④**远程体积解析稳健化**（wc -c 优先，ls -l 用月份锚点兼容 busybox/系统两种字段数）+ 失败不再吞真因。顺带：新增 tests/test_device_screenshot_probe.py（5 条离线回归：有 echo 无 gzip 不许选中 / /tmp/busybox 有 gzip 要选中 / 两种 ls 格式与 wc -c 的体积解析）。实测：修后 Z20(800x1280) 与 Z21(1024x600) 均抓到有效 PNG（method=busybox-dd-gzip）。⚠️ live 工具仍走旧代码，需重启 MCP 服务生效（进程内缓存旧模块）。',
    '2026-09-13: 组件化落地（components 随 MCP 发布）+ 字库自检入库 v0.27.47-open（沛哥定：组件放在随 MCP 发布的代码路径下，其他 AI 才能收到；蓝牙/射频底层经验不入库、旧档已删；字体经验保留；暂不抽依赖包，做成组件代码模块方便 AI 直接用到代码里）——①**新增 `components/` 目录（随 MCP 发布）**：`components/README.md` 定组件规范（一个模块一个目录 + **四件套硬要求**【落地 README / platforms.md 平台说明 / Manifest.xml package 引用 / 可直接调代码】+ 两种形态【代码型 include+src+example，对外 `zk::<模块>`；资产/工具型 README+platforms+scripts+产物】+ 8 条代码规范 + 工程侧两坑【fun.json 优先于 Manifest.xml；type="executable" 才出 ELF】）；②**首两个模块**：`components/ble/`（BLE 门面 `zk::ble` v0.1：openAdapter/扫描/连接/GATT 读写订阅/诊断 getDiag；上电与 Realtek hciattach、H5+偶校验、run loop 线程、TLV 全在组件内部，对外不出现任何 btstack 类型；V85X 真机跑通 20 设备）+ `components/fonts/`（思源黑体三版 common 872KB / full 7.39MB / multi 10.5MB + 设备字体自检 device_font_check.py：getprop + 字体体积 <200KB ⇒ 大概率只有英文 → --apply 自动投递进工程）；③**字库口径入库**（devflow/custom-font-config.md）：项目 font/ 会由工具链自动写进 EasyUI.cfg 的 font 键（launch 与 pack 都做）→ **不要手改 .prefs 的 font 键**；固化会整体替换 /res → 字库必须随包走（否则汉字变方块）；④**知识库瘦身（定位定死：底层过程不入库）**：删除蓝牙/射频底层 bring-up 与 RF 模组电源两篇（用户与 AI 只需上层概念 + 直接用组件；实现细节留在组件自带文档），upgrade-pack-image.md / hardware_catalog 相应行同步收敛；⑤真机证据：V85X SPINOR（8733bs）app 固化后开机自启 → HCI WORKING → 扫描 20 设备（含自家价签），汉字正常。',
    '2026-09-13: 页面架构 + src 业务域目录命名规范入库 v0.27.45-open（沛哥确认判断正确后定规）——①新增 `knowledge/devflow/page-architecture-spec.md`：**ftu vs 同 ftu 内多窗口决策规范**（此前全库只有零散事实描述、检索 low_confidence）——口径：ftu=Activity=独立编译单元（独立生命周期/返回栈），window=同 Activity 内显隐（零切换成本/共享控件指针与状态）→ 决策清单 4 步（跨业务域？需独立生命周期/返回栈/大页面？并列内容区？需盖整屏？）+ 三形态对比表（A 独立 ftu / B 整屏 window+showWnd / C pagewindow·slidewindow·scrollwindow 容器）+ 辅助判据（要不要返回语义 / 要不要共享状态指针 / 媒体硬件资源生命周期按 onUI_quit）+ 5 条常见错法反例（二级页都开新 ftu、跨域硬塞一个 ftu、visible 初值没管、装饰件没穿透、多整屏 window 预览只见首页）+ 自检清单 ②**src 目录命名定规**：按业务域**直接建在 src/ 下**（`src/network/*.cpp .h`、`src/media/*.cpp .h`），**不设 core/modules 中间分层**；域名为小写英文单数名词（禁 core/common/misc 这类无域含义名，真共用才另起 common/）；文件=域内一个职责类（大驼峰、与文件名一致）；一律 .cpp/.h 禁 .cc；include 用相对 src/ 路径 ③`flythings_get_project_spec` 同步改口径：directoryRules 的 `core` 键改 `domain`（业务域目录）、caveats 里「放自建目录（src/core/、src/modules/ 等）」改为业务域目录 + 原文里的 core 分层提法全清，并新增「页面架构」caveat 指向本规范 ④与既有文档互链：activity-code-skeleton §3-1（资源释放走 onUI_quit）、touch-events（装饰件 setTouchable(false)+setTouchPass(true)）、ui-layout-verify §2-2（多整屏 window 预览切页）。',
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


# ========== 设备端预编译工具（bin_tools/，**不是 op**，不占 op 名额）==========
# 2026-09-14（钟工反馈）：外部 AI 数完 34 个 op 就断言「MCP 这版没有触摸注入」——
# 实际 touch 自 v0.27.40 起一直在 bin_tools/<平台>/ 下，只是不占 op 名额、工具面没有任何出口。
# 修法：把 bin_tools 暴露成 flythings_get_version 的 binTools 字段 + flythings://tools 资源一节。
BIN_TOOLS = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'bin_tools')
if getattr(sys, 'frozen', False):          # PyInstaller 打包：随包进 _MEIPASS
    BIN_TOOLS = os.path.join(sys._MEIPASS, 'bin_tools')

BIN_TOOL_BRIEF = {
    'touch': '统一触摸注入：自动扫 /dev/input 节点 + 自动判协议（单点/MT-A/MT-B）；'
             'tap/swipe/long/monkey/run/record/play + list/info；部署不带 /dev/input/eventN',
    'busybox': '设备调试工具箱（网络/系统/Shell applet 全开，静态链接）',
    'ui_test': '触摸注入 / 自动化测试（单点协议，兼容保留，需人工传节点）',
    'mt_test': 'MT-A 协议触摸注入（兼容保留，需人工传节点）',
    'zkshot': 'SigmaStar（z20/z21）视频层抓帧，配合 flythings_device_screenshot(layer="video")',
}


def _bin_tools() -> dict:
    """扫 bin_tools/<平台>/ 下的设备端 ELF → {平台: [工具名,...]}（缺失时返回空 dict，不报错）。"""
    out = {}
    if not os.path.isdir(BIN_TOOLS):
        return out
    for plat in sorted(os.listdir(BIN_TOOLS)):
        d = os.path.join(BIN_TOOLS, plat)
        if not os.path.isdir(d):
            continue
        # 说明文件（README.md）不算设备端工具——bin_tools/z235x 目前只有占位说明
        files = sorted(f for f in os.listdir(d)
                       if os.path.isfile(os.path.join(d, f)) and not f.startswith('.')
                       and not f.lower().endswith('.md'))
        if files:
            out[plat] = files
    return out


def _bin_tools_field() -> dict:
    """binTools 字段（工具面唯一出口：让「数 op」的 AI 也能发现设备端工具）。"""
    by_plat = _bin_tools()
    if not by_plat:
        return {}
    used = {f for fs in by_plat.values() for f in fs}
    return {
        'note': '设备端预编译 ELF（随 MCP 发布，adb push 即用）——**它们不是 op、不占 op 名额**，'
                '所以只数 op 清单会漏掉；触摸注入/自动化测试先看 touch，不要自己造轮子',
        'dir': BIN_TOOLS.replace('\\', '/'),
        'byPlatform': by_plat,
        'brief': {k: v for k, v in sorted(BIN_TOOL_BRIEF.items()) if k in used},
        'usage': '触摸：adb push bin_tools/<平台>/touch /data/touch && chmod 777；再 '
                 '`adb shell /data/touch list` 看节点+协议，tap/swipe/long/monkey/run/play 同工具；'
                 '知识库：knowledge/devflow/touch-inject-autotest.md',
    }


def flythings_get_version(compact: bool = True) -> str:
    """返回 MCP 版本号、工具数量与近期关键特性。用户问「MCP 版本是多少 / 是不是最新的」时调用。
    compact=True（默认）只回版本摘要 + 近期 3 条（每条 ≤700 字，防 token 炸弹）；完整能力史传 compact=False。
    另回 `binTools` 字段（设备端预编译工具：touch / busybox / ui_test / mt_test / zkshot），
    在 bin_tools/<平台>/ 下，**不是 op、不占名额**。
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
    bt = _bin_tools_field()
    if bt:
        out['binTools'] = bt
    if compact:
        out['recent'] = [_clip_feature(f) for f in MCP_FEATURES[:3]]
        out['note'] = ('完整能力史传 compact=False（默认只回近期 3 条、每条 ≤ %d 字以省 token）'
                       % COMPACT_FEATURE_CHARS)
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


_KB_INDEX_CACHE = {}


def _kb_index_map():
    """path → 元数据（status/evidenceLevel/origin），总账索引 + **本地层索引**合并，进程内缓存。

    P0-2：本地层（用户 capture 出来的）必须也能被标注到 origin=local，检索侧才能“本地优先”。
    """
    if 'map' not in _KB_INDEX_CACHE:
        m, err = {}, ''
        try:
            import kb_local as _kbl
            for path, org in ((os.path.join(_kbl.TOTAL_KB, 'kb_index.json'), 'total'),
                              (_kbl.local_index_path(_kbl.kb_dir()), 'local')):
                idx = _kbl.load_json(path)
                for d in (idx.get('docs') or []):
                    if d.get('path'):
                        d.setdefault('origin', org)
                        m[d['path']] = d
                err = err or idx.get('_error', '')
        except Exception as e:                      # 索引读不了不影响检索，只丢标注
            err = repr(e)
        _KB_INDEX_CACHE.update({'map': m, 'err': err})
    return _KB_INDEX_CACHE['map'], _KB_INDEX_CACHE.get('err', '')


_LOCAL_BOOST = 1.15        # 本地层同主题优先（更贴近现场）：仅改排序，不改写分数
_STALE_PENALTY = 0.85     # 过期知识降权（P2 时效）：仅改排序


def _kb_index_entry(path):
    km, _err = _kb_index_map()
    return km.get(path) or {}


def flythings_knowledge_gaps(limit: int = 20, out: str = '', project_root: str = '') -> str:
    """查「知识缺口清单」：用户/AI 反复问但**检索不到**的主题（生长引擎的输入端）。

    数据来自本地层 `_logs/no_hit.jsonl`（不外发）。返回 top-N 问法 + 次数 + `nextActions`；
    out 给路径则同时落 kb_gaps.md。周期看它 = 知道下一批该写什么（缺口驱动写作）。
    """
    import kb_local as _kbl
    g = _kbl.gaps(int(limit or 20), kb_override='')
    if out:
        md = _kbl.gaps_markdown(g)
        try:
            os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
            with open(out, 'w', encoding='utf-8', newline='\n') as f:
                f.write(md)
            g['markdown'] = out
        except OSError as e:
            g['warnings'] = g.get('warnings', []) + ['kb_gaps.md 写不了: %s' % e]
    g['logFile'] = g.get('logFile')
    g['nextActions'] = [
        '挑一条缺口 → flythings_knowledge_capture(...)（落本地层候选）',
        '补 evidence（cmd 或 artifact）→ python scripts/kb_verify.py --apply',
        '登记 ≥5 条问法到 scripts/check_retrieval.py 的 GROUPS，跑 --report 取实测阈值',
        '人工签字（reviewed_by）或机器复验（machine_verified_at）后才 status=verified',
    ]
    return json.dumps(g, ensure_ascii=False)


def _annotate_kb_hits(hits):
    """给命中补 `status / evidenceLevel / verifiedAt`（消费侧要看得出「这条验没验过」）。

    背景（2026-09-29 提报发现 ②）：首轮迁移把 80/85 篇迁成 `verified + needs_evidence`，
    光看 `verified` 会被当成"已验"。`evidenceLevel`: has-evidence（有可执行判据）/ manual-only
    （人工沉淀、无判据）/ none（未验证）。非 verified 或 none 的额外给 `advisory`。
    """
    km, _err = _kb_index_map()
    for h in hits:
        d = km.get(h.get('path'))
        if not d:
            continue
        h['status'] = d.get('status')
        h['evidenceLevel'] = d.get('evidenceLevel')
        h['origin'] = d.get('origin')
        h['verifiedAt'] = d.get('verified_at')
        h['freshness'] = d.get('freshness')
        h['ageDays'] = d.get('ageDays')
        lvl = d.get('evidenceLevel') or ''
        if (d.get('status') or '') != 'verified' or lvl != 'has-evidence':
            h['advisory'] = ('本条状态=%s / 证据等级=%s：可当线索，结论前请核对原文'
                             '或按 evidence 复验（法见 knowledge/devflow/kb-growth.md）'
                             % (d.get('status') or '?', lvl or 'none'))
        if d.get('stale'):
            h['stale'] = True
            h['advisory'] = ('⚠️ 本条已过期（%s 天前验，阈值 %s 天）：结论可能已被版本迭代推翻，'
                             '请先按 evidence 复验' % (d.get('ageDays'), d.get('staleDays') or 180))
        elif d.get('freshness') == 'aging' and not h.get('advisory'):
            h['advisory'] = '本条已接近复验期（%s 天前验），大改前建议复验' % d.get('ageDays')
    return hits


def flythings_knowledge_search(query: str, k: int = 3) -> str:
    """在知识库（wiki 官方镜像 + knowledge 实践文档）检索片段（完全本地，零 Key）。

    遇到 FlyThings 开发问题（控件/API/布局/FTU/回调/编译/平台差异）时调用；query 用中文。
    命中带 status/evidenceLevel/freshness（未验/过期会带 advisory）；未命中会记账（kb_gaps）。
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
    # P0-2：本地层同主题优先（更贴近现场）；P2：**过期降权**（只改排序，不改分数字段）
    _km0, _e0 = _kb_index_map()
    if any(((_km0.get(c.get('path')) or {}).get('origin') == 'local')
           or ((_km0.get(c.get('path')) or {}).get('stale')) for _s, c in top):
        def _w(sc):
            d = _km0.get(sc[1].get('path')) or {}
            f = 1.0
            if d.get('origin') == 'local':
                f *= _LOCAL_BOOST
            if d.get('stale'):
                f *= _STALE_PENALTY
            return float(sc[0]) * f
        top = sorted(top, key=_w, reverse=True)
    hits = _annotate_kb_hits([
        {'path': c['path'], 'score': round(float(s), 4), 'text': c['text'],
         'source': 'knowledge（实践）' if (c.get('path') or '').startswith('knowledge/')
                   else 'wiki（官方镜像）'}
        for s, c in top])
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
    # 知识生长燃料（P1）：未命中/低置信落**用户本地层**日志（绝不写安装目录），
    # scripts/kb_gaps.py 聚合出「用户真的问不到什么」→ 驱动下一批写作。
    if out['quality'] in ('no_hit', 'low_confidence'):
        try:
            import kb_local as _kbl
            logr = _kbl.log_no_hit(query, out['quality'], [h['path'] for h in hits], kk)
        except Exception as _e:                      # 日志失败不能影响检索本身
            logr = {'logged': False, 'error': repr(_e)}
            warnings.append('未命中日志写入失败（不影响检索）：%s' % _e)
        out['gapLogged'] = bool(logr.get('logged'))
        out['gapLog'] = logr.get('file', '')
        out['gapHint'] = ('本条已记入知识缺口清单（scripts/kb_gaps.py 生成 kb_gaps.md）；'
                          '要补这条知识：flythings_knowledge_capture(...) → 补 evidence → '
                          'scripts/kb_verify.py 复验 → 人工签字后才入库')
    return json.dumps(out, ensure_ascii=False)


def flythings_knowledge_capture(title: str, body: str = '', category: str = 'devflow',
                                platforms: str = '', tags: str = '', evidence: str = '',
                                source: str = '', severity: str = 'normal',
                                project_root: str = '', layer: str = 'local') -> str:
    """把一条现场结论落成知识候选（写**用户本地层/项目层**，绝不写 MCP 安装目录）。

    title 一句话说清现象/结论；evidence 传 JSON（[{"kind":"real-device|offline|manual",
    "cmd":"...","artifact":"..."}]）或纯文本；layer=local（~/.flythings/kb_local/）| project。
    命中同主题 → 回 duplicateOf，提示**合并**而非新建。之后：补 evidence → kb_verify → 签字才 verified。
    """
    import kb_local as _kbl
    ev = []
    if str(evidence or '').strip():
        try:
            ev = json.loads(evidence)
            if not isinstance(ev, list):
                ev = [ev]
        except ValueError:
            ev = [{'kind': 'manual', 'cmd': str(evidence)}]
    r = _kbl.capture(title, body, category,
                     [x for x in str(platforms or '').split(',') if x.strip()],
                     [x for x in str(tags or '').split(',') if x.strip()], ev,
                     source=source, layer=layer, project_root=project_root,
                     severity=severity)
    return json.dumps(r, ensure_ascii=False)


def flythings_knowledge_export(out: str = '', scope: str = 'inbox', layer: str = 'local',
                               project_root: str = '', internal: bool = False) -> str:
    """导出**脱敏知识补丁包**（回流总账通道 A：kb-contrib-<时间>.json）。

    scope=inbox（缺省）/verified/all；**强制脱敏**（IP/本机路径/凭据/主机名 → 占位符），
    未脱敏须 internal=True（仅总账维护者自用）。交回：发回文件，或对 open 版仓提 PR（只改 knowledge/inbox/**）。
    总账侧 去重 → 复验 → 问法登记 → 人工签字。
    """
    import kb_local as _kbl
    return json.dumps(_kbl.export_pack(out, scope, layer=layer, project_root=project_root,
                                       internal=internal), ensure_ascii=False)


def flythings_hardware_info(model: str = '', platform: str = '') -> str:
    """查硬件型号库：按平台/型号拿到分辨率、按键值、接口规格与平台差异化。

    用户说「我这台是 PocketDisplay4 / SW80480070D_C」时先查这里，别按同系列型号外推。
    **有具体型号 → 按返回的 preset 直接开工**（平台/分辨率/方向/按键，不用再问）；
    **没具体型号 → 确认平台 + 分辨率就能建工程**（缺参数不阻塞）。
    - model 留空：列平台 + 已登记型号（platform 可过滤）；model 给值：回 preset/screen/keys/specs/
      differences/optional/source；未收录：MODEL_NOT_FOUND + fallback（平台+分辨率即可开工）+ 近似候选
    完整型号表另见知识库 knowledge/hardware/hardware-models.md。
    """
    return json.dumps(hw.query(model, platform), ensure_ascii=False)


# ========== 跨框架控件映射能力（2026-09-16，钟工口径：有一一映射的控件走「映射能力」，不写散文）==========
# 数据唯一来源：mcp_control_map.json（人工维护；来源 = components/ui_v1/control-map.md + gap-list.md
# + knowledge/devflow/gui-controls-gap.md + knowledge/uicontrols/*-fields.md，**冲突以 KB 为准**）。
# 分工：**有平台对应控件 → 本 op（机读索引 + 可粘贴 json 片段）；平台真缺的能力 → components/ui_v1/<包>**。
_CONTROL_MAP_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'mcp_control_map.json')
if getattr(sys, 'frozen', False):          # PyInstaller 打包：随包进 _MEIPASS
    _CONTROL_MAP_PATH = os.path.join(sys._MEIPASS, 'mcp_control_map.json')
_CM_CACHE = {}


def _control_map():
    """读 mcp_control_map.json（带缓存）。文件缺失/坏掉时回 (None, 原因)，不静默。"""
    if 'err' in _CM_CACHE:
        return None, _CM_CACHE['err']
    if 'data' in _CM_CACHE:
        return _CM_CACHE['data'], ''
    try:
        data = json.loads(io.open(_CONTROL_MAP_PATH, encoding='utf-8').read())
    except Exception as e:
        _CM_CACHE['err'] = 'mcp_control_map.json 读取失败（%s: %s）' % (type(e).__name__, e)
        return None, _CM_CACHE['err']
    _CM_CACHE['data'] = data
    return data, ''


def _cm_norm(s):
    """控件名归一：小写 + 去下划线/连字符/点/空格/括号（模糊匹配口径，与用户写法无关）。"""
    s = (s or '').lower()
    for ch in '_-./\\ ()[]（）·':
        s = s.replace(ch, '')
    return s


def _cm_score(q, name, aliases):
    """打分：精确 100 / 前缀 80 / 子串 60 / 词元包含 40；别名按同名列一起算（取最高）。"""
    if not q:
        return 0
    best = 0
    for cand in [name] + list(aliases or []):
        n = _cm_norm(cand)
        if not n:
            continue
        if q == n:
            best = max(best, 100)
        elif n.startswith(q) or q.startswith(n):
            best = max(best, 80)
        elif q in n:
            best = max(best, 60 + min(10, len(q)))
        elif len(q) >= 4 and any(t and t in n for t in [q[:4]]):
            best = max(best, 40)
    return best


def flythings_map_control(query: str, source: str = '') -> str:
    """跨框架控件映射：输入源框架控件名 → 一次对上我们的控件（等价级别 + 可直接粘的 json 片段）。

    什么时候用：拿到 LVGL/Qt/Android/小程序/emWin/MFC 工程或设计稿，要转到 FlyThings 时。
    - query：源控件名（或别名），忽略大小写与下划线/连字符，如 lv_slider / RecyclerView /
      QCalendarWidget / lv_tabview / swiper
    - source：可选，只在该框架内找（lvgl / qt / android / miniprogram / emwin / mfc）
    命中返回：target（我们控件）/level（L1~L5）/notes/json（可直接粘的片段）/ref/control。
    未命中回 NO_HIT + candidates + 缺口五级处置（口径：有对应控件用映射；平台真缺才做 components/ui_v1/ 包）。
    """
    data, err = _control_map()
    if data is None:
        return json.dumps({'ok': False, 'op': 'flythings_map_control',
                           'error': _err_obj('DATA_MISSING', err, '确认 mcp_control_map.json 随包分发', False),
                           'warnings': [err]}, ensure_ascii=False)
    sources = data.get('sources') or {}
    targets = data.get('targets') or {}
    labels = data.get('sourceLabels') or {}
    src = (source or '').strip().lower()
    if src and src not in sources:
        cands = sorted(sources.keys())
        return json.dumps({'ok': False, 'op': 'flythings_map_control',
                           'error': _err_obj('BAD_SOURCE', '未知 source: %s' % source,
                                             'source 取 ' + ' / '.join(cands) + '（留空 = 全框架搜）', True),
                           'sources': cands, 'warnings': []}, ensure_ascii=False)
    q = _cm_norm(query)
    if not q:
        return json.dumps({'ok': False, 'op': 'flythings_map_control',
                           'error': _err_obj('BAD_PARAMS', 'query 为空',
                                             '传源框架控件名，如 query="lv_slider"（可带 source="lvgl"）', True),
                           'warnings': []}, ensure_ascii=False)
    hits = []
    for sname, arr in sources.items():
        if src and sname != src:
            continue
        for e in arr or []:
            sc = _cm_score(q, e.get('name', ''), e.get('aliases'))
            if sc > 0:
                hits.append((sc, sname, e))
    if not hits:
        names = sorted({e.get('name', '') for a in sources.values() for e in (a or [])})
        near = [n for n in names if q[:3] and q[:3] in _cm_norm(n)][:5] if len(q) >= 3 else []
        msg = '映射表里没有「%s」%s' % (query, ('（限定 %s）' % src) if src else '')
        hint = ('先判是不是「平台真缺的能力」：去 components/ui_v1/components.md 看计划/已实现的自定义控件包'
                '（Chart/Calendar/RadButton 已实现；RichText/TableGrid/BadgeToast/Pseudo3D 计划中；'
                '**滚轮/时间/时钟盘族（WheelPicker·TimePicker 含时钟盘·NumberPicker）已改判 L2 → 不建包，'
                '走 `listview` 组合**，见 knowledge/uicontrols/listview-wheel-picker.md），'
                '再按「缺口五级」处置：L1 等价 / L2 组合 / L3 自绘（须在 ui_v1/gap-list.md 登记编号）/ '
                'L4 降级（写明降级点）/ L5 不支持（明说 + 给替代），**不要临场发明**')
        return json.dumps({'ok': False, 'op': 'flythings_map_control', 'query': query,
                           'error': _err_obj('NO_HIT', msg, hint, False),
                           'candidates': near,
                           'gapPolicy': {'levels': data.get('levels') or {},
                                         'mapForExisting': 'platform 有对应控件 → 用本 op（flythings_map_control）',
                                         'packForMissing': 'platform 真缺 → components/ui_v1/<源控件名>/（四件套 + example + 真机证据）',
                                         'docs': 'components/ui_v1/control-map.md（权威表）/ gap-list.md（G-01~G-36 + T1~T12）/ '
                                                 'components.md（状态表）/ knowledge/uicontrols/control-mapping-capability.md'},
                           'warnings': []}, ensure_ascii=False)
    hits.sort(key=lambda x: (-x[0], len(x[2].get('name', '')), x[1]))
    sc, sname, e = hits[0]
    tgt = e.get('target', '')
    meta = targets.get(tgt) or {}
    out = {'ok': True, 'op': 'flythings_map_control', 'query': query, 'score': sc,
           'source': sname, 'sourceLabel': labels.get(sname, sname),
           'name': e.get('name', ''), 'target': tgt, 'level': e.get('level', ''),
           'levelName': (data.get('levels') or {}).get(e.get('level', ''), ''),
           'notes': e.get('notes', ''), 'json': e.get('json', ''), 'ref': e.get('ref', ''),
           'control': {'caption': meta.get('caption', ''), 'ptr': meta.get('ptr', ''),
                       'note': meta.get('note', '')},
           'warnings': []}
    if sc < 100:
        out['warnings'].append('模糊命中（score=%d）——确认是否你要的控件；要精确匹配请用源控件原名' % sc)
    if len(hits) > 1:
        out['alsoMatched'] = [{'source': s, 'name': x.get('name', ''), 'target': x.get('target', ''),
                               'level': x.get('level', '')} for _, s, x in hits[1:5]]
    if e.get('level') in ('L3', 'L4', 'L5'):
        out['gapHint'] = '该控件不是等价映射：先看 components/ui_v1/gap-list.md 的处置与编号，别现场发明'
    return json.dumps(out, ensure_ascii=False)


def flythings_read_json(json_path: str) -> str:
    """解析 .json 布局文件为 JSON（分辨率、控件列表、caption→id 映射）。传入 json 完整路径。
    ⚠️ 传入 .ftu 时不再当「加密无法解析」：先把 ftu 交给 flythings_fui_unpack 反解析成 json，
    再把返回的 jsonPath 传进来（本 op 只读 json）。"""
    return json.dumps(pt.flythings_read_json(json_path), ensure_ascii=False)


def flythings_get_project_spec() -> str:
    """返回 FlyThings 项目结构化规范（目录规则、生成规则、注意事项）。编写/修改项目代码前调用。新需求先出设计稿/原型并确认。"""
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

def flythings_layout_audit(project_root: str, page: str = '') -> str:
    """静态审计 UI 布局的层叠/遮挡/触摸穿透（**纯几何，0 token，先看 json 再截图**）。
    ⚠️ 用户说「控件被盖住 / 点不到 / 位置不对 / 谁挡着谁」时**先调本 op**：json 就能判定谁压谁
    （z 序 = 书写顺序）、谁的触摸被抢、整屏层是否吞触摸；每条带 by + why + fix。
    kind：fullscreen_layer / touch_steal / covered_interactive / pass_through_missing / overlap。
    视觉样式/像素仍走 device_screenshot + ui_visual(diff)。"""
    return json.dumps(pt.flythings_layout_audit(project_root, page), ensure_ascii=False)


def flythings_fui_pack(json_path: str) -> str:
    """将 json 布局打包为 ftu（设备实际加载的是 ftu）。返回 ftu 路径、控件数、分辨率。
    ftu 是 json 布局的**编译产物**：改布局一律改 json 后 pack，不要手写/手改 ftu
    （详见 knowledge/devflow/ftu-json-pipeline.md）。"""
    r = pt.flythings_fui_pack(json_path)
    return json.dumps(_with_files(r, r.get('ftuPath')), ensure_ascii=False)


def flythings_fui_unpack(ftu_path: str, output_json: str = '', overwrite: bool = True) -> str:
    """ftu → json 反解析（fui unpack；随包 fui 自 v0.27.91 起支持）。
    ⚠️ 默认**覆盖**同目录同名 json（ftu 为真源）；要保留原 json 传 overwrite=False（写 <name>.unpacked.json），
    或 output_json 指定路径。用在：只有 ftu 没 json 的老工程 / 核对设备侧布局 / IDE 改过 ftu 要回写 json。
    改布局仍以 json 为源（细节见 knowledge/devflow/ftu-json-pipeline.md）。"""
    r = pt.flythings_fui_unpack(ftu_path, output_json, overwrite)
    return json.dumps(_with_files(r, r.get('jsonPath')), ensure_ascii=False)




def flythings_edit_ftu(ftu_path: str, operations: str, output_ftu: str = '',
                       overwrite: bool = False) -> str:
    """编辑 ftu 布局：自动应用编辑到 json 后 pack 回 ftu（json 是源，ftu 是编译产物）。

    ⚠️ 默认 **不覆盖**原 ftu（overwrite=False）→ 生成同目录 <name>.edited.ftu 并还原原文件；
    确认后再传 overwrite=True 覆盖（或 output_ftu 指定目标）。原 ftu 与 json 都留 .bak。
    operations 为 JSON 数组（set/remove/add/set_root；逐字段见 ftu-json-pipeline.md）。客户说
    「往右移/改文本/换颜色/删控件/复制控件」时调用；无 json 源时自动 unpack 出编辑源。
    """
    r = pt.flythings_edit_ftu(ftu_path, operations, output_ftu, overwrite)
    return json.dumps(_with_files(r, r.get('ftuPath'), r.get('jsonPath'), r.get('backup')),
                      ensure_ascii=False)


def flythings_build_ui_flow(project_root: str, with_launch: bool = True, device: str = '',
                            font_check: str = 'auto', font_tier: str = '') -> str:
    """⚠️ 场景别名（编译/部署类意图一律本工具，禁自造命令）：口语「编译/构建/调试/部署/推送到
    设备/跑一下」；固化升级（update.img）→ flythings_pack_upgrade（掉电保留）。
    流程：json↔ftu 时间戳检查 → fui pack → fun install → fun build → **设备探测 + fun launch**
    （只编译传 with_launch=False）→ 字体体检（缺中文自动投）+ 设备侧字节/md5 比对
    （staleOnDevice=true ⇒ 设备上还是旧版）。探测不猜：0 台→needDeviceInput；多台→列 serial 要 device=。
    ⚠️ src/activity/ 由 IDE 生成（禁手改），业务只写 src/logic/*.cc；细节见
    knowledge/devflow/adb-and-device-selection.md。
    """
    return json.dumps(_with_design_warning(
        pt.flythings_build_ui_flow(project_root, with_launch, device,
                                   font_check, font_tier), project_root),
        ensure_ascii=False)


def flythings_pack_upgrade(project_root: str, out_path: str = '', release_version: str = '',
                           ab: bool = False, with_build: bool = False,
                           dry_run: bool = False) -> str:
    """固化升级包（update.img）——交付/发布/量产走本条：「打包升级包/出升级包/固化/刷进设备/
    出货版本/TF卡升级包」；与「调试推送到设备」不同（那是 build_ui_flow，掉电即失）。
    流程：fun install →（with_build 可选）fun build → fun pack（out_path→-o；--release-version；
    ab=True→--ab OTA）。产物 `.fsc/<平台>/update.img`；刷法 TF卡/ADB/远程批量；换开机 logo → MISC。
    dry_run=True 只回命令计划。⚠️ `sign error 0xc0000135`=缺 32 位 VC++；`package not found
    in local`=先 fun install。详情：knowledge/devflow/upgrade-pack-image.md。
    """
    return json.dumps(pt.flythings_pack_upgrade(project_root, out_path, release_version,
                                                ab, with_build, dry_run),
                      ensure_ascii=False)



def flythings_ui_preview(target: str, output_dir: str = '') -> str:
    """json 布局 / 整个项目 → HTML 预览稿（客户确认 UI 用；只交 .preview.html，不产图片/截图）。
    target = 项目根目录（全部 ui/*.json）或单个 json 路径（合并原 preview + json_to_html）。
    ⚠️ 多整屏 window 工程自带「页面切换条」+ `#window__N`（简写 `#N`）直达 + 幽灵框看隐藏窗。
    ⚠️ 流程：布局出来必须先出预览给用户确认，确认 OK 才允许 fui pack / 写逻辑 / 交付。
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
                    # A7 修（2026-09-27）：递归计数（旧版只数根层 → 50 控件页面报 controls:1）
                    def _count_list(dd, acc):
                        for k, v in dd.items():
                            if k.startswith('__'):
                                continue
                            if isinstance(v, dict) and '__' in k:
                                acc[0] += 1
                                _count_list(v, acc)
                            if isinstance(v, list):
                                for x in v:
                                    if isinstance(x, dict):
                                        _count_list(x, acc)
                        return acc[0]

                    top = sum(1 for k, v in data.items()
                              if isinstance(v, dict) and not k.startswith('__') and '__' in k)
                    total = _count_list(data, [0])
                    f['controls'] = total
                    f['controlsTopLevel'] = top
                    f['controlsNested'] = max(total - top, 0)
                except Exception:
                    pass
        r['projectRoot'] = target
        r['outputDir'] = output_dir or os.path.join(target, 'ui')
        r['note'] = 'html 为客户预览稿；设备端仍用 fui pack 生成的 ftu，两者同源于 json'
    return json.dumps(r, ensure_ascii=False)


def flythings_html_to_json(input_html: str, output_json: str = '', res: str = '',
                           merge_windows: bool = False) -> str:
    """受限 HTML 交互原型 -> ui/*.json（CSS 效果自动转图；产物尺寸 == 控件盒）。

    ⚠️ 动手前先读《HTML_SUBSET 原型规范》（检索 HTML_SUBSET / data-icon / 自动转图清单）：
    控件映射表、全部 data-* 属性、铁律、属性清单都在那里，本 docstring 只留最低限度。
    多屏（div.screen，data-page）：**每屏一个 json = 一页 = 一个 Activity = 一个独立 ftu**；
    **仅当同属一个 Activity** 时才用 merge_windows 合成同 json 的 N 个整屏 window。
    返回 screensDetected/pagesProduced/jsonsProduced/pages[]；**不等一律 success:false**（不静默丢页）。
    红线：先出 .preview.html 确认再 pack/写逻辑；效果一律转图；禁止 AI 自绘 1x png。
    """
    return json.dumps(h2j.html2json(input_html, output_json or None, res or None,
                                    merge_windows=bool(merge_windows)), ensure_ascii=False)


def flythings_list_packages(platform: str = '') -> str:
    """列出依赖包生态（platform 如 F133/Z20，留空列全部），含功能描述与版本。写代码前调用。"""
    r = pkgtools.flythings_list_packages(platform or None)
    if platform and isinstance(r, dict):
        info = _platforms.resolve(platform) or {}
        if info and not info.get('buildable'):
            # 「仅依赖包生态」平台：只能查包/取包，**不能建工程与编译**
            r['packageOnly'] = True
            r['notice'] = ('%s 属「仅依赖包生态」平台：只能查/取依赖包，'
                           '**不支持 create_project / build_ui_flow**（别在这些平台上试建工程）'
                           % (info.get('name') or platform))
    return json.dumps(r, ensure_ascii=False)


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


def flythings_test_run(plan: str = '', devices: str = 'auto', project_root: str = '',
                       out: str = '', platform: str = '', parallel: int = 4,
                       baseline: str = 'auto', allow_regions: int = 0,
                       per_device_keys: str = 'auto') -> str:
    """多设备**并行**跑一份 UI 用例（触摸注入 + 日志断言 + 像素基线），出 JSON + JUnit 报告。

    plan 是用例 JSON（文本或路径）：steps[].action 取 tap/long/swipe/wait/monkey/run/shot/log；
    每步可带 shot=<基线 key>、expectLog/expectNoLog、allowRegions、wait(ms)。devices="auto"
    （**恰好 1 台才自动选**）/"all"/"<IP>:5555,..."；project_root 给基线库位置；
    baseline=auto/compare/save/off；报告落 out：report.json + report.xml（可进 CI）。
    **比不到基线记 no-baseline，不算通过**。写法/建基线流程见
    knowledge/devflow/device-test-run.md。
    """
    return json.dumps(tt.flythings_test_run(plan, devices, project_root, out, platform,
                                            parallel, baseline, allow_regions,
                                            per_device_keys),
                      ensure_ascii=False)


def flythings_attach_cli_tools(project_root: str, with_fyx: bool = True) -> str:
    """复制 fui.exe（→项目 ui/）与 fun.exe（→项目根目录）到项目，随项目交付。
    生成后用 fun.exe build 编译、launch 推送，无需客户导入 IDE。
    ⚠️⚠️ src/activity/ 目录（mainActivity.cpp/h）由 IDE 编译时自动生成，禁止创建/修改；
    业务代码只写 src/logic/*.cc。
    """
    return json.dumps(pt.flythings_attach_cli_tools(project_root, with_fyx), ensure_ascii=False)


# ===== 设计先行软闸门（v0.27.101）=====
# 背景（钟工 2026-09-21 口径 A）：用户没给设计流程/界面时，AI 必须先走「原型设计 -> 界面设计 ->
# 用户确认」再建工程；意图闸门负责在 prompt 侧拦，这里负责在**开干类工具**侧留痕。
# 口径：**只读检测 + 只加 warnings，不改 success 语义、不阻断**（避免破坏既有调用与用例）。
_DESIGN_HINT = (
    '未检测到设计确认稿：若是新需求，请先走原型设计/界面设计流程'
    '（prototype-flow：功能拆解 -> 页面树 -> 线框图 -> 确认稿 -> 确认后再建工程）'
)
# 设计产物识别：design/ 等目录、任意 *.html（线框图/美化稿/确认稿）、*.preview.html 等
_DESIGN_DIRS = ('design', 'designs', 'prototype', 'wireframe', 'mockup')
_DESIGN_WALK_SKIP = {'.git', '.fun', 'Release', '__pycache__', 'node_modules', '.settings'}


def _has_design_artifacts(root):
    """项目目录内是否已有设计产物（design/ 目录 / *.html / *.preview.html / 设计稿类文件）。

    只读、只扫一层浅目录树（跳过构建产物）。任何异常一律当作「有设计」（不提示），
    保证这个提示永远不会变成新的失败点。
    """
    try:
        root = str(root or '').strip()
        if not root or not os.path.isdir(root):
            return True          # 目录还不存在（工具自己会报错）-> 不提示
        for d in _DESIGN_DIRS:
            if os.path.isdir(os.path.join(root, d)):
                return True
        for base, dirs, files in os.walk(root):
            dirs[:] = [x for x in dirs if x not in _DESIGN_WALK_SKIP]
            for f in files:
                low = f.lower()
                if low.endswith(('.html', '.htm', '.wireframe')) or 'preview' in low:
                    return True
        return False
    except Exception:
        return True


def _with_design_warning(res, root):
    """给「开干类」返回值追加设计先行软提示（只 push warnings，不动其它键）。

    失败路径（success/ok 显式为 False）不加：失败原因本身才是要看的，别塞噪音。
    """
    try:
        if (isinstance(res, dict) and res.get('success') is not False
                and res.get('ok') is not False and not _has_design_artifacts(root)):
            w = list(res.get('warnings') or [])
            w.append(_DESIGN_HINT)
            res['warnings'] = w
    except Exception:
        return res
    return res


def flythings_create_project(project_root: str, platform: str, resolution: str,
                             app_name: str = '', with_cli: bool = True, force: bool = False) -> str:
    """从 HelloWord 模板创建 FlyThings 项目，自动替换工程名/分辨率/平台。
    传入项目根目录、平台（口径由 platforms.py 提供）与分辨率（如 800x480）。
    ⚠️ platform/resolution 必填且必须来自用户明确提供，未指定时先询问，禁止猜测或用默认值。
    ⚠️ 页数：创建后按设计稿屏数确认（多屏设计稿 = N 屏必须全部落地，见 page-architecture-spec.md）。
    ⚠️⚠️ src/activity/ 目录（mainActivity.cpp/h）由 IDE 编译时根据 ftu 自动生成，
    禁止创建/修改/覆盖该目录任何文件！业务代码只能写 src/logic/*.cc；
    mXXXPtr 控件指针 / ID_MAIN_* 宏 / 回调表 / findControlByID 初始化全部由 IDE 自动生成，禁止手写。
    ⚠️ 新需求请先出设计稿/原型并确认（见 prototype-flow）再建工程。
    """
    return json.dumps(_with_design_warning(
        pt.flythings_create_project(project_root, platform, resolution,
                                    app_name, with_cli, force), project_root),
        ensure_ascii=False)


def flythings_check_project_deps(project_root: str, platform: str = _platforms.DEFAULT_PLATFORM,
                                device: str = '', font_check: str = 'auto', font_tier: str = '',
                                font_apply: bool = False) -> str:
    """扫描项目 include 的三方库与 Manifest 声明对比，返回缺失依赖。
    需要三方能力（MQTT/HTTP/JSON/蓝牙/SSL 等）时先调用。
    另含框架包体检（base 头文件↔base-utility）与字体体检（缺中文字库就报 fontIssues+
    一键修复；默认只报不投，font_apply=True 才投递；传 device= 才扫设备字体）。
    """
    return json.dumps(pkgtools.flythings_check_project_deps(
        project_root, platform, device, font_check, font_tier, font_apply), ensure_ascii=False)


def flythings_generate_ui_assets(project_root: str, assets: str) -> str:
    """生成 UI 图片资源（图标/牌面/按钮背景等）→ <项目>/resources/images/（json 引用写 images/xxx.png）。

    assets 为 JSON 数组字符串，每项：{name, size, prompt, emoji, color, kind}
    —— name 必填（自动补 .png）；prompt 有则优先 AI 生图，失败用 emoji，再不行用 color/kind 线条兜底；
    kind 可选 check/charging/wifi/alert/circle/square/star/heart；返回每项实际方式 method(ai/emoji/line)。

    ⚠️ 铁律（尺寸==控件盒、四角 alpha=0、禁 1x 直画/外部生图直出小图）与三条合法出图路径见知识库
    「UI 图片资源铁律与 PNG 抗锯齿管线」（检索：图片资源铁律 / 抗锯齿 / 四角发黑 / 走哪条路出图）。
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
UI_VISUAL_ACTIONS = ('editor', 'edit_apply', 'diff', 'baseline')
UI_VISUAL_ARGS = {
    'editor': ('project_root', 'output_dir'),
    'edit_apply': ('project_root', 'changes', 'pack', 'dry_run'),
    'diff': ('image_a', 'image_b', 'tolerance', 'shift', 'min_area', 'blur',
             'noise_bbox', 'out_png', 'out_json', 'show_noise'),
    # baseline（2026-09-29）：像素基线库 —— 把「上一次验收通过的那张图」版本化存下来
    'baseline': ('project_root', 'image_a', 'mode', 'baseline_key', 'name', 'allow_regions',
                 'tolerance', 'shift', 'min_area', 'blur', 'noise_bbox', 'out_png'),
}
UI_VISUAL_REQUIRED = {'editor': ('project_root',),
                      'edit_apply': ('project_root', 'changes'),
                      'diff': ('image_a', 'image_b'),
                      'baseline': ('project_root',)}
_UI_VISUAL_DEFAULTS = {'project_root': '', 'output_dir': '', 'changes': '', 'pack': False,
                       'dry_run': False, 'image_a': '', 'image_b': '', 'tolerance': 2,
                       'shift': 1, 'min_area': 4, 'blur': 0.7, 'noise_bbox': 10,
                       'out_png': '', 'out_json': '', 'show_noise': False,
                       'mode': '', 'baseline_key': '', 'name': '', 'allow_regions': 0}


def _ui_baseline(project_root, image, mode='', key='', name='', allow_regions=0,
                 out_png='', profile=None):
    """像素基线库（ui_baseline.py）：mode=list/save/compare/update（缺省 compare）。"""
    import ui_baseline as ubl
    m = str(mode or 'compare').strip().lower()
    ar = None if int(allow_regions or 0) <= 0 else int(allow_regions)
    if m in ('', 'compare', 'check', 'verify'):
        return json.dumps(ubl.compare(project_root, image, key=key, out_png=out_png,
                                      allow_regions=ar, profile=profile),
                          ensure_ascii=False)
    if m == 'save':
        return json.dumps(ubl.save(project_root, image, key=key, name=name,
                                   profile=profile, allow_regions=ar or 0),
                          ensure_ascii=False)
    if m == 'update':
        return json.dumps(ubl.update(project_root, image, key=key, name=name,
                                     profile=profile, allow_regions=ar or 0),
                          ensure_ascii=False)
    if m in ('list', 'ls'):
        return json.dumps(ubl.listing(project_root), ensure_ascii=False)
    return json.dumps({'ok': False, 'op': 'flythings_ui_visual',
                       'error': _err_obj('BAD_PARAMS', 'baseline mode=%s 不认识' % mode,
                                         'mode 取 list / save / compare / update', True),
                       'warnings': []}, ensure_ascii=False)


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
                        show_noise: bool = False, mode: str = '', baseline_key: str = '',
                        name: str = '', allow_regions: int = 0) -> str:
    """UI 可视化/像素验收入口（action 选动作；旧 ui_editor / ui_edit_apply / ui_diff 已并入）。

    - action="editor"：ui/*.json → 可拖拽编辑器网页（<项目>/ui/_edit/<name>.edit.html）。必填
      project_root；拖完点「复制 AI 指令」粘给 AI（本地静态页）。
    - action="edit_apply"：变更 JSON 写回 ui/*.json。必填 project_root、changes（JSON 文本或路径）；
      pack 默认 False；dry_run=True 只预览不写盘；写回前留 .bak。
    - action="diff"：两张同尺寸截图逐像素对比（0 token 差异清单）。必填 image_a、image_b；
      tolerance/shift/blur/min_area/noise_bbox 压假报警；out_png/out_json 出标注图与清单。
    - action="baseline"：**像素基线库**（<项目>/ui_baseline/）。必填 project_root；mode=
      save/compare/update/list（+image_a）；容差档案随基线存；比不到基线报 no-baseline，不静默放过。

    口径见 knowledge/devflow/ui-layout-verify.md；action 传 list 看各 action 参数。
    """
    act = str(action or '').strip().lower().replace('-', '_')
    if act in ('', 'list', 'help', '?'):
        return json.dumps({'success': True, 'op': 'flythings_ui_visual',
                           'actions': {k: {'args': list(v),
                                           'required': list(UI_VISUAL_REQUIRED[k])}
                                       for k, v in UI_VISUAL_ARGS.items()},
                           'hint': ('action 取 editor / edit_apply / diff / baseline；'
                                    '旧 ui_editor / ui_edit_apply / ui_diff 已并入本 op')},
                          ensure_ascii=False)
    if act not in UI_VISUAL_ACTIONS:
        return _ui_visual_bad('unknown action: %s' % action,
                              'action 取 editor / edit_apply / diff / baseline'
                              '（传 action="list" 看参数）')
    given = {'project_root': project_root, 'output_dir': output_dir, 'changes': changes,
             'pack': pack, 'dry_run': dry_run, 'image_a': image_a, 'image_b': image_b,
             'tolerance': tolerance, 'shift': shift, 'min_area': min_area, 'blur': blur,
             'noise_bbox': noise_bbox, 'out_png': out_png, 'out_json': out_json,
             'show_noise': show_noise, 'mode': mode, 'baseline_key': baseline_key,
             'name': name, 'allow_regions': allow_regions}
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
    if act == 'baseline':
        prof = {'tolerance': tolerance, 'shift': shift, 'minArea': min_area, 'blur': blur,
                'noiseBbox': noise_bbox}
        return _ui_visual_note(_ui_baseline(project_root, image_a, mode, baseline_key,
                                            name, allow_regions, out_png, prof), note)
    return _ui_visual_note(_ui_diff(image_a, image_b, tolerance, shift, min_area, blur,
                                    noise_bbox, out_png, out_json, show_noise), note)


def flythings_verify_assets(project_root: str) -> str:
    """核对「json 声明 vs 磁盘产物」：图片引用是否存在 + PNG 尺寸是否 == 盒子。

    ⚠️ 生成/改完图片后必跑（v0.27.30 阴影丢图事故 = 产物没人核对）。
    盒子来源（图片铁律 #1）：控件 position（backgroundPic/picTab/...）+ thumb 自有尺寸子盒
    thumb.size；支持 ui/*.json 与 ui/<分辨率>/*.json 两种布局。
    返回：missing[]（引用无文件）/ mismatch[]（自动生成图或 thumb 尺寸 != 盒）= 真问题；
    stretched[]（手绘图被拉伸）仅提示；unresolved[]/skippedNoBox[] 跳过项；warnings[] 0 页等。
    与 check_all 第 11/17 项同一实现。
    """
    if chk_all is None:
        return json.dumps({'ok': False, 'error': 'check_all 模块不可用（缺 ui_tools/check_all.py）'},
                          ensure_ascii=False)
    try:
        r = chk_all.verify_assets(project_root)
    except Exception as e:
        return json.dumps({'ok': False, 'error': 'verify_assets 失败: %s' % e}, ensure_ascii=False)
    r['hint'] = ('missing → 补图或改 json 引用（自动生成图片放 resources/images/，引用写 images/xxx.png）；'
                 'mismatch → 重新出图，使 PNG 尺寸严格 == 盒子（position 或 thumb.size）；'
                 'stretched 一般无需处理（手绘图由引擎拉伸到控件盒）')
    return json.dumps(r, ensure_ascii=False)


# device_screenshot 的进阶参数默认值（v0.27.34：这些键也可统一走 advanced JSON，
# 已显式传的同名参数优先 —— 参数分层的判定基准）
_DSS_ADV_DEFAULTS = {'fb': '/dev/fb0', 'pixel': 'auto', 'width': 0, 'height': 0, 'offset_y': -1,
                     'flip': '', 'rotate': 'auto', 'crop': '', 'layer': 'ui', 'vdec_chn': 0,
                     'name': '', 'timeout': 180}


def flythings_device_screenshot(device: str = '', out: str = '', fmt: str = 'png', scale: float = 1.0,                               quality: int = 90, fb: str = '/dev/fb0', pixel: str = 'auto',
                               width: int = 0, height: int = 0, offset_y: int = -1,
                               flip: str = '', rotate: str = 'auto', crop: str = '', name: str = '',
                               timeout: int = 180, advanced: str = '', layer: str = 'ui',
                               vdec_chn: int = 0) -> str:
    """从**设备真机**抓当前屏幕 → PNG / JPG / BMP（给视觉模型看，或给 ui_visual(action="diff") 做验收）。

    要确认设备上实际显示成什么样（布局/锯齿/切图/颜色/文字/改完验收）时用；三段式验收第二步。
    常用（默认参数就够）：scale=0.5 或 fmt='jpg', quality=85 省 token；多设备 device='<IP>:5555'；
    rotate='auto' 按工程 EasyUI.cfg 的 rotateScreen 转正；只要应用画面用 crop='auto'。
    ⚠️ 抓完把返回的 path 交给看图能力，不要把 raw/文件丢给模型。
    进阶参数（fb/pixel/宽高/offset_y/flip/rotate/crop/layer/vdec_chn/name/timeout）统一走 advanced
    （JSON 字符串），同名显式参数优先。layer="video"（仅 SigmaStar）抓**视频层**帧；多路/拼墙必须给
    vdec_chn（默认 0，**SmartPanel 拼墙在 chn 1**；选错=抓不到帧）。检索词与踩坑见
    knowledge/devflow/device-screenshot.md。
    """
    if dss is None:
        return json.dumps({'success': False, 'error': 'device_screenshot 不可用（缺 ui_tools/device_screenshot.py 或 Pillow）'},
                          ensure_ascii=False)
    # 参数分层（v0.27.34）：fb/pixel/width/height/offset_y/flip/rotate/crop/name/timeout 可统一走 advanced
    # （JSON 对象字符串）；**已显式传的同名参数优先**（旧客户端不受影响）。
    params = {'fb': fb, 'pixel': pixel, 'width': width, 'height': height, 'offset_y': offset_y,
              'flip': flip, 'rotate': rotate, 'crop': crop, 'layer': layer, 'name': name,
              'timeout': timeout, 'vdec_chn': vdec_chn}
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

def flythings_selfcheck(device: str = '', diff_against: str = '', out: str = '') -> str:
    """整机快照（九个分区），每分区给 {ok, hint, data}；`ok=false` **不是错误而是结论**。

    九分区：①设备信息 ②应用状态 ③显示 ④存储 ⑤网络 ⑥蓝牙 ⑦输入 ⑧外设 ⑨时间；
    hint 写明「需要什么条件 / 去哪查指令」，不静默。采集容忍设备缺工具：优先随仓
    bin_tools/<平台>/busybox（→设备 /tmp/busybox，缺则推一份），否则纯 adb shell + getprop/cat。
    device='<serial|IP>:5555'（可省；**多台在线不猜**，回 NO_DEVICE + 在线清单）；
    diff_against=<上次快照.json> 出逐分区逐项差异；out=<json 路径> 落盘（可复用作基线）。
    检索词：整机自检/selfcheck/九分区/快照/与上次对比（knowledge/devflow/selfcheck-and-bugreport.md）。
    """
    if sc is None:
        return json.dumps({'ok': False, 'op': 'flythings_selfcheck',
                           'error': {'code': 'MODULE_MISSING',
                                     'msg': 'selfcheck_tools 不可用: %s' % _SC_ERR,
                                     'hint': '恢复仓库里的 selfcheck_tools.py 后重试',
                                     'retryable': False},
                           'warnings': []}, ensure_ascii=False)
    return json.dumps(sc.run_selfcheck(device, diff_against, out), ensure_ascii=False)


def flythings_bugreport(title: str = '', project_root: str = '', device: str = '',
                        symptom: str = '', steps: str = '', expected: str = '',
                        actual: str = '', evidence: str = '', severity: str = '',
                        out: str = '') -> str:
    """缺陷单生成器：把缺陷清单 + 真机判据落成可提交 markdown（格式对齐 2026-09-27 html2json A1~A8 那批）。

    只给 title 也能出框架稿；steps/evidence 支持 JSON 数组或换行/分号/逗号分隔。
    真机判据自动附：型号·固件·build.fingerprint·应用状态（init.svc.zkswe / sys.zkapp.state /
    zkgui pid / uptime）·最近 `logcat -d -s zkgui` 末 40 行；采不到就写明原因（不静默）。
    ⚠️ evidence 文件不存在 → 直接报 EVIDENCE_MISSING。severity ∈ blocker…trivial（缺省 major）。
    默认落 <项目或仓库>/temp/bugreports/<yyyymmdd-HHMM>-<slug>.md（返回 path + 前 20 行预览）。
    细节见 knowledge/devflow/selfcheck-and-bugreport.md。
    """
    if sc is None:
        return json.dumps({'ok': False, 'op': 'flythings_bugreport',
                           'error': {'code': 'MODULE_MISSING',
                                     'msg': 'selfcheck_tools 不可用: %s' % _SC_ERR,
                                     'hint': '恢复仓库里的 selfcheck_tools.py 后重试',
                                     'retryable': False},
                           'warnings': []}, ensure_ascii=False)
    r = sc.build_bugreport(title, project_root, device, symptom, steps, expected, actual,
                           evidence, severity, out, MCP_VERSION)
    return json.dumps(_with_files(r, r.get('path')), ensure_ascii=False)



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
    'flythings_knowledge_capture',
    'flythings_knowledge_export',
    'flythings_knowledge_gaps',
    'flythings_hardware_info',
    'flythings_map_control',
    'flythings_read_json',
    'flythings_layout_audit',
    'flythings_get_project_spec',
    'flythings_validate_project',
    'flythings_fui_pack',
    'flythings_fui_unpack',
    'flythings_edit_ftu',
    'flythings_build_ui_flow',
    'flythings_pack_upgrade',
    'flythings_ui_preview',
    'flythings_html_to_json',
    'flythings_ui_visual',
    'flythings_verify_assets',
    'flythings_device_screenshot',
    'flythings_selfcheck',
    'flythings_bugreport',
    'flythings_attach_cli_tools',
    'flythings_create_project',
    'flythings_create_bin_project',
    'flythings_gen_ui_test',
    'flythings_test_run',
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
