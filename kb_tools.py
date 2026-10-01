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
MCP_VERSION = '0.27.170-open'
MCP_BUILD = '2026-10-01'
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
    '2026-10-01: **配色对比度标准入库（深底文字档定版 + 22 处 FAIL 归零）** v0.27.170-open（钟工「用改后的做标准，老项目不修改了」）—— ① **新增 `knowledge/devflow/color-contrast-standard.md`**（门面收口：字看不清/灰底白字/副文本太暗/深色界面文字档/4.5:1 边缘试探 一律先读它）：阈值表（fs<24 → 4.5、fs≥24 → 3、图标描边 3、禁用豁免；设备裁剪字库不试 4.5、留 5.0 余量）+ **深底三类底（页底 #17171B / 卡片底 card.9.png ≈#27272F / 芯片底 sschip141x40.png ≈#23242E）的文字档**：主文字 `#ECECF0`（15.17/12.57/13.07x）、**副文本·说明行·英文小标题 = `#9A9AA2`（6.40/5.30/5.51x，本标准档）**、禁用豁免；**明确禁用 `#5F5F68` 一类中灰压深底**（2.83/2.34/2.44x 不达标，旧工程遗留）；浅底档速查（`#010101/#666666/#6E6E6E/#0052D9`、浅底禁白字、主题色当字降档）+ 6 条硬规则（字色跟底走 / 半透明先合成再算 / 同屏同义色一套 / 深底只用两档灰 / 改完必跑 check_all / **老工程不回头改**）+ 工具用法。② **实测案例（SmartPanel_HA 480x480）**：check_all 第 34 项 **FAIL 22 → 0**（改前 = 20 处 #5F5F68 on #17171B 2.83x + 卡片底 2.34x + 芯片底 2.44x；改法 = 副文本色 `#5F5F68 → #9A9AA2`，**工程内既有色不是新造色**，14 个 ui json / 50 处 color0；改后 219 个可判文本全达标、临界带与不可信底降级均 0）。③ 工作区侧同步：`references/kb/color-standard.md` 增 §2.3 深底文字档 + 硬规则第 7 条。**老工程（SmartPanel_HA 本体）按钟工口径不改**，标准只对新工程生效。v0.27.170-open',
    '2026-10-01: **Blend2D 组件入库（离屏矢量出图，原厂档 + 自编 NEON 性能档）** v0.27.170-open —— `components/blend2d/`（30 文件）：门面 **`zk::b2d`**、唯一对外头 `include/zk/zk_blend2d.h`（**零 `BL*` 类型泄漏**，要原生 API 自己 include `<blend2d.h>` 与门面共存）；定位 = **「离屏矢量出图」不是「2D 加速器」**（圆角/阴影/渐变/OpenType 文本 → 导出位图给 easyui）。**两档库**：`lib/z20/`（官方注册表包 `blend2d 0.11.1`，1,472,816 B，md5 E07458D8…）= 默认/兼容档；`lib/z20-neon/`（自编，1,874,056 B，+27.2%，md5 C1E9DCCE…）= 性能档。**自编必须锁 commit `a7f9476`**（上游无 v0.11.1 tag，判据 `BL_MAKE_VERSION(0,11,1)`），构建 `-march=armv7-a -mfpu=neon -mfloat-abi=hard -O2 -DBLEND2D_NO_JIT=ON`（`scripts/build-neon.sh` 写死原文）。**自检 `scripts/verify_libs.py` 16 项 PASS**：两档 defined 动态符号 **787:787 集合完全相等**、ELF 属性同为 7-A/v7/VFPv4/NEONv1+FMAC、老档 `q` 命中 0 / NEON 档 >0、NEON 档 NEEDED 含 `libgcc_s.so.1`。**默认配方（写进 README）**：不透明底 + `SRC_COPY` 直传（`BL_FORMAT_PRGB32` 在 ARM32 = BGRA == easyui，**字节序零转换**；画布含透明必须 unpremultiply）＋ `threadCount=2` ＋ 缓冲复用 ＋ 阴影少层（8→2）。**性能（真机 Z20，含 flush(SYNC)）**：480×480 单线程 28.005→**23.707 ms**（NEON −15.3%）、480×480 双线程 14.154→**12.222 ms**、800×1280 109.439→**89.696 ms**（−18.0%）；**双线程 + 阴影 8→2 层 → 5.171 ms（−78.2%）**；分项 `fillAll` −53%、阴影段 −16.7%、**文本段无加速**（ARM32 无 JIT，路径/字形几何向量化不了）——**NEON 是配角，胜负手是 `threadCount=2` + 阴影减层**；**效果零行为改变**（5 个产件新旧库 md5 全等、真机抓屏 diff 与基准一致）。**部署通道写死**：`fun launch` 不推第三方包 `.so`（调试手推 `/tmp`，量产放 `src/dependencies/lib/` + `fun pack`）；`update.img` 账 = NEON 版 1,262,120 B / 原厂版 1,143,336 B / 无 blend2d 基线 647,720 B（**+116 KB**）。**平台**：z20 已验；z21 / t113emmc 理论可用**未验**；v85x / t113-musl（缺 glibc·libstdc++）、f13x（RISC-V）**不可用**。`example/` 真编译通过（`fun build -p Z20` exit 0、`libzkgui.so` 301,892 B、NEEDED 含 libblend2d.so），**示例未上真机**（如实标注）。v0.27.170-open',
    '2026-10-01: **Blend2D 组件入库（离屏矢量出图，原厂档 + 自编 NEON 性能档）** v0.27.170-open —— `components/blend2d/`（30 文件）：门面 **`zk::b2d`**、唯一对外头 `include/zk/zk_blend2d.h`（**零 `BL*` 类型泄漏**，要原生 API 自己 include `<blend2d.h>` 与门面共存）；定位 = **「离屏矢量出图」不是「2D 加速器」**（圆角/阴影/渐变/OpenType 文本 → 导出位图给 easyui）。**两档库**：`lib/z20/`（官方注册表包 `blend2d 0.11.1`，1,472,816 B，md5 E07458D8…）= 默认/兼容档；`lib/z20-neon/`（自编，1,874,056 B，+27.2%，md5 C1E9DCCE…）= 性能档。**自编必须锁 commit `a7f9476`**（上游无 v0.11.1 tag，判据 `BL_MAKE_VERSION(0,11,1)`），构建 `-march=armv7-a -mfpu=neon -mfloat-abi=hard -O2 -DBLEND2D_NO_JIT=ON`（`scripts/build-neon.sh` 写死原文）。**自检 `scripts/verify_libs.py` 16 项 PASS**：两档 defined 动态符号 **787:787 集合完全相等**、ELF 属性同为 7-A/v7/VFPv4/NEONv1+FMAC、老档 `q` 命中 0 / NEON 档 >0、NEON 档 NEEDED 含 `libgcc_s.so.1`。**默认配方（写进 README）**：不透明底 + `SRC_COPY` 直传（`BL_FORMAT_PRGB32` 在 ARM32 = BGRA == easyui，**字节序零转换**；画布含透明必须 unpremultiply）＋ `threadCount=2` ＋ 缓冲复用 ＋ 阴影少层（8→2）。**性能（真机 Z20，含 flush(SYNC)）**：480×480 单线程 28.005→**23.707 ms**（NEON −15.3%）、480×480 双线程 14.154→**12.222 ms**、800×1280 109.439→**89.696 ms**（−18.0%）；**双线程 + 阴影 8→2 层 → 5.171 ms（−78.2%）**；分项 `fillAll` −53%、阴影段 −16.7%、**文本段无加速**（ARM32 无 JIT，路径/字形几何向量化不了）——**NEON 是配角，胜负手是 `threadCount=2` + 阴影减层**；**效果零行为改变**（5 个产件新旧库 md5 全等、真机抓屏 diff 与基准一致）。**部署通道写死**：`fun launch` 不推第三方包 `.so`（调试手推 `/tmp`，量产放 `src/dependencies/lib/` + `fun pack`）；`update.img` 账 = NEON 版 1,262,120 B / 原厂版 1,143,336 B / 无 blend2d 基线 647,720 B（**+116 KB**）。**平台**：z20 已验；z21 / t113emmc 理论可用**未验**；v85x / t113-musl（缺 glibc·libstdc++）、f13x（RISC-V）**不可用**。`example/` 真编译通过（`fun build -p Z20` exit 0、`libzkgui.so` 301,892 B、NEEDED 含 libblend2d.so），**示例未上真机**（如实标注）。v0.27.170-open',
    '2026-10-01: **Z20 视频链路规格入库（H.264 必须去 B 帧）+ 块库第 4 批收齐 31 块** v0.27.169-open —— ① **新增知识 `knowledge/devflow/z20-video-pipeline-spec.md`**（钟工 2026-10-01 新增关键要素：**Z20 的 H.264 必须去 B 帧 `-bf 0`，否则卡顿类问题**，配套 `has_b_frames=0` 判据与 `split_wall.py` 默认 `bf:0` 取证）；统一规划「素材编码 → 解码 → 上屏」8 条硬约束速查表：**去 B 帧**／**素材属性必须与 MI VDEC 通道属性一致**（块状花屏根因，块度 1.53~1.81 → 1.08~1.17）／通道属性**固化在预编译 `libmi-module.a` 的 `h264_player.o`**（改错地方=白跑）／`yuv420p`·不超屏·`cfr`·`faststart`·首帧 IDR／码率给足／AAC 160k 44.1k 2ch／**H.265 交付不支持**（包内 0 解码器、无 HEVC parser/BSF，`0xa008200f`）／**GOP 内不能丢包**（丢一片 = P 帧花屏一片，看 `dropGop=0` 与块度 ≈1.0）。含**标准素材编码命令 baseline**（钟工给定命令 + `-bf 0`）与**未取证清单 8 条**（B 帧卡顿缺 A/B 量化、DPB 关系、码率阶梯等），逐条标出处、不猜。工作区全文 `references/kb/z20-video-pipeline-spec.md`（229 行，含现象→根因→做法→判据）。② **块库第 4 批收齐**：`toolbar`／`loading`（骨架 + 转圈两变体）／`time_row`／`form_section` 核实并接入两个 complex 示例，修 `loading.json` 骨架素材口径（`rounded_rect_cov` → `gen_res.rounded_rect_ss(ss=8)`），README 块清单与禁止项补齐 → **共 31 块**；**8/8 示例 compose + check_all exit 0（0 FAIL）**。v0.27.169-open',
    '2026-10-01: **块库第 4 批前 3 块 + tabs 倒角/指示条修正 + 语义色对比度收口 + check_all #33/#34** v0.27.168-open —— ① **新增块**：`chart_card`（柱状/折线 + 刻度 + 右下轴注）、`image_gallery`（等距宫格 + 右下「共 N 张」脚注带）、`keypad`（3×4，键面图==键盒；退格/确认走 brand 态）+ 新示例 `complex_{1024x600,320x240}`。② **tabs 修正**（钟工：「左边倒角和右边倒角不一样」）：新 `clip_shape()` —— 选中底/指示条**从整条药丸形状裁切**（同半径、同 ss=8、**像素级同缘**），指示条盒**改取 tab 项盒**（原左右各缩 6px）；条半径改为**只按带高算** `h//2`（与宽度无关）。客观量：左右端内缩之差 1024 **44 行不齐 → 6 行 1~2px**（残差为 AA 对比度差，装饰件与容器 alpha 逐像素相等）、320 **22 → 2 行**。③ **语义色对比度**（#34 判 FAIL 后）：success/warn/danger 由 TDesign -6 档改 **-7 档**（`#006C45` / `#954500` / `#AD352F`），浅底不动 → 2.82~3.85:1 提升到 **5.63~6.08:1**，与 `info=brand`（5.93）同一视觉重量；**未用 allow-list 豁免**（-6 档 4.09~4.11 落在 0.9× 临界带会降级 NOTE，故取 -7）。④ **check_all 新增 #33 层级三件套（WARN）/ #34 文本对比度（FAIL，委派 `tools/qa/contrast_check.py`）**：#34 背景按「绘制顺序 + 几何覆盖」取（底图均色/半透明按父底合成），阈值 WCAG 2.1 AA（<24px ≥4.5 / ≥24px ≥3），临界带只 NOTE；#33 查同页字号档 >5 与「大字号配更浅色」倒挂。判据结果**是参考工具结果的严格子集**（无新增误报），官方 `SampleUI-New` #34 **0 FAIL**。⑤ **实测**：**8/8 示例 compose+check_all exit 0（0 FAIL、nav 由 5 FAIL 归零）**；tabs 修前/修后差异 bbox 全落在 tabs 条内、条外 0 像素；全渲染图内旧语义色 **0 像素**残留。⑥ **待决**：`SmartPanel_HA` 22 条 #34 FAIL（secondary `#5F5F68` 压暗底 2.83:1）由业务侧决定提亮或豁免；`components/icons` 的 24px `more` 过不了 AA 审计（换 `settings` 绕开，根治需重出库产物）。v0.27.168-open',
    '2026-10-01: **`list_item` 支持逐行内容（列表终于显示文字）+ 行内容宽度自检** v0.27.167-open（钟工：「现在就是列表显示不出来了」→ 查明根因：`list_item` 规范要求 `item.text` 空串、内容走 `subItem`，而示例 spec 没给逐行内容 → 渲染图只有行与箭头）—— ① **spec 新增 `items[]`**：`{"type":"list_item","rows":4,"items":[{"icon":"wifi","title":"客厅面板","value":"在线"},…]}`；组装器把行内容落成 **`subItem`**（图标走 `components/icons` 的 `iconlib`、标题/值 textview、可选箭头），**`item.text` 仍为空串**、行高仍 `itemH = int(lv高/rows) − rowSpacing`（#37 继续核）。② **口径（写进块定义与 README）**：`items[0]` = 行模板（引擎只有一份模板 → 静态图各行相同，**真机必须 `obtainListItemData` 逐行覆盖**）；**列表高只由 `rows` 算**（items 少于 rows → 其余行在真机上是空行）；**每行都过宽度自检**（`#13/#36` 遍历不到 subItem → 块库自己核，超宽报 `[X] 文本装不下`）；极小屏（320）行高 24 容不下图标列 → 整块省图标并打 NOTE。③ **实测**：6/6 示例 `compose exit 0` + `check_all exit 0（0 FAIL）`；1024 列表 `960×162` / 模板 `960×40`（itemH 40 = int(162/4)−0，余 2px）行内 `SubIcon 24×24 / SubTitle 804×24 / SubValue 52×20(右对齐) / SubChevron`；320 列表 `272×24`（itemH 24 = int(98/4)−0，余 2px、无图标列）；渲染报告从「模板无行文本」变为「**8 处文本已画**」。④ **回归**：settings×2 / nav×2 长图与单屏图**逐字节一致**；interactive 差异 bbox 全部落在列表块内（4272px / 1324px）。v0.27.167-open',
    '2026-10-01: **修「底部固定条压住内容」+ 渲染器补数组子项（列表/单选/复选）** v0.27.166-open（钟工看图：「列表依旧没有刷新出来」「高分辨率的客厅面板底下有东西被覆盖住了」）—— ① **缺陷 A（组装器口径）**：底栏 y 用 `H − bar_bot` 定位，而**内容视口没扣底栏高** → `ButtonRowDeviceCard9`(508..568) 与 `FooterBg12`(528..600) **重叠 992×40px**（正是「客厅面板的值被盖住」）。修：钉成**唯一令牌 `content_bottom = H − bar_bot`**（底栏 y / 底导 y / 视口全部由它派生）+ 新增 **`assert_no_bar_overlap()`**（不变式 `bar_top+viewport ≤ H−bar_bot`；固定带与**裁剪后有效矩形**逐对判相交；内容实际底 ≤ 声明内容高）→ 相交直接报错不出产物。反例实证：改回旧口径即报「视口伸进底部固定条」并精确复现 40px 压盖。顺带修出真缺陷：`empty_state` 块高在 320×240 上 72 < 需要 104（滑到底也看不到最后一段）→ 改为按内容反算（320 内容 372→404，长图 444→476；1024 版零变化）。② **缺陷 B（离线渲染器盲区）**：`json2img` 新增 `draw_radiogroup`（逐项画圆点 + 文本，选中走 `colorTab.color2`）、`draw_listview`（按 rows/rowSpacing/itemH 铺行 + subItem 图/文本；缺 rows 时反算）、`draw_checkbox`（按 `checked` 切图；模板缺 `pic2` 时叠 `components/icons` 的 `control.check_on`，勾色按盒底亮度二选一），并修掉旧路径把勾选图**拉伸铺满控件盒**的问题。unsupported 清单相应收敛（去掉 checkbox/radiogroup/item 四条，改为如实的 `runtimeState`/`runtimeRows`）。③ **如实报告**：`item/subItem` 画法**原本已实现**（真实工程 listViewDemo 改前改后渲染逐字节相同）；ui_blocks 示例里「列表是空的」真正原因是 `list_item` 块**规范明令禁写占位文本**（`item.text` 为空串）→ 示例的长图里列表**有行有箭头但无文本**，文本能力用夹具 + 真实工程证明。④ **实测**：6/6 示例 compose/check_all/full_render 全 exit 0（0 FAIL）；**屏幕图与 HEAD 逐字节相同**（可见区零回归），长图差异仅三类（固定带让位 / 新增数组内容 / 空态块长高）。v0.27.166-open',
    '2026-10-01: **块库图标来源改接 `components/icons`（禁 emoji/线框兜底）** v0.27.165-open（钟工：「这些网络，设备的 icon 图标怎么来源。效果差异和实际差异太大」→「这个整体风格比较正常了。按照建议修改」）—— ① **根因**：块库 `glyph()` 原走 `gen_res.glyph_icon()` 兜底（emoji 映射表 + 本地 emoji 字体；缺字体退简笔线框），与真机/产品实际使用的 `components/icons`（Tabler 3.46.0 单色烘焙 PNG，203 语义 / 305 产物，22/24/56 档，`_off`=outline /`_on`=filled）不同源 → 效果图与真机差异大。② **修**：新增 `templates/ui_blocks/iconlib.py`（语义名 → 库条目，复用库自带 `resolve_target`，不另建名字表；档位 ≥44px→56 / ≥26px→24 / 否则 22，**盒 == 档位直接取库产物**（换色与重渲逐像素一致，maxdiff=0），缺档按盒尺寸现出；查不到 → 回退线框并**明说 + 汇总计数**）；`compose.py` `glyph()` 改走库 + 新增 `libicon` 出图 kind + 「图标来源/档位」报告段；新增 `blocks/_icons.json`（**203 语义名允许清单**）。③ **保留的例外**：箭头（chevron）**刻意不走库**（库 chevron 是 24 网格细描边，12×16 盒会退 1px 硬斜边被 aa_audit 判缺陷）→ 仍用箭头专属口径；checkbox 勾选符号改走库 `control.check._on`。④ **实测**：6/6 示例 `compose exit 0` + `check_all exit 0（0 FAIL）`、**回退线框 0 处**；图标产物尺寸全部 == 控件盒；新旧长图逐像素比：nav_1024 差异仅 0.36%（只有图标与勾选符号变了）。⑤ 新增 `full_render.py`（整页展平长图，人工验收用，不参与 check_all；修掉「展平 json 落临时目录会丢全部底图」的陷阱）。⑥ 相关坑入库：`star` 描边态 @24px 会被 aa_audit 判真缺陷 → 用 `state:"on"` 实心；`glyph_min_px` 与档位对齐（24px 盒 → 24 档）。v0.27.165-open',
    '2026-10-01: **界面块库第 3 批（结构/导航/提示 7 块，块库达 24 块）** v0.27.164-open（钟工：「先不离线渲染器」→ 先扩块）—— 新增：`tabs`（等分 tab + 选中底 + **指示条直角实条且写在所有 tab 之前**；选中底高度 = tab_h − ind_h 避重叠）/ `bottom_nav`（固定带高 = max(屏高10%，…)，**项宽 = 屏宽/N**；与 bottom_actions 同页叠置时**视口 = 屏高 − 标题 − nav − 底栏**）/ `banner`（4 语义色 info/success/warn/danger，关闭盒写在最上层）/ `toast`（根层整屏 window、**最后定义=最上层**、默认 visible:false）/ `status_pill`（药丸：盒宽 = 文本盒向上取 4px 栅格 + 2×pill_pad，圆角 = 带高/2）/ `divider_label`（两侧等长 1px 线 + 中间小字）/ `grid_icons`（**格盒 == 格底图**、末列吃余数、可选整格 button）。新增令牌：语义色 info/success/warn/danger + mask + tab/pill/banner/divider/nav/toast 比例 + **`glyph_min_px=24`**。组装器新增 builder：`build_tabs/build_nav/build_banner/build_pill/build_divider_label/build_grid/build_toast` + `r4up`（4px 向上栅格）。**实测**：`nav_1024x600`（124 控件 / 44 图 / 行程 528）与 `nav_320x240`（116 控件 / 43 图 / 行程 552）均 `exit 0 / check_all 0 FAIL / 0 待审批 WARN`；**旧 4 版示例重跑均 exit 0 且产物逐字节一致**（零回归）。**重要发现**：`aa_audit` 不看未登记资产白名单→**小图标会被当真缺陷**（wifi@12/home@16/settings@16/bell@20 全 FAIL）→ 引入 `glyph_min_px=24`（图标不随屏降档，极小屏靠「省图标」降级）。**未支持（如实）**：底导仅图标+文字一种呈现、宫格无跨列 span、toast 单行、新切图未登记 `asset_audit_rules.json`（#22/#23/#25 只出 NOTE）、toast/dialog 静态渲染默认 visible:false 看不到。v0.27.164-open',
    '2026-10-01: **界面块库第 2 批（交互类 7 块）+ 两版示例（20m 级交付）** v0.27.163-open（钟工：「你交付后可以截图给我验收下」）—— 新增：`slider_row`（标题+滑块+值，thumb.size==滑块图）/ `progress_row`（同几何、只读样式）/ `input_row`（edittext，自动生成 `onEditTextChanged_*`）/ `checkbox_row`（**自身 touchable=true，不给整行 button**）/ `radio_row`（radiogroup 竖排、组 touchable=true、子项相对组坐标）/ **`list_item`**（lv 高 = rows×(模板高+rowSpacing)+余数，**itemH = int(lv高/rows) − rowSpacing 且模板高 == 它**，余数=有意的可滑动提示）/ **`wheel_picker`**（listview 组合，**选中条挂静态层且写在 listview 之前**，整除数 0）。组装器新增 builder：seekbar / edittext / checkbox / radiogroup+radiobuttons / listview+subItem，并新增 `row_boxes()`（行族文本盒全页族预留）。**实测**：新两版 `interactive_1024x600`（64 控件 / 22 图 / 行程 914）与 `interactive_320x240`（62 控件 / 22 图 / 行程 690）均 `compose exit 0` + `check_all exit 0（0 FAIL/0 WARN）`；**#37 给出** `ListListItem13 item 高 40 = int(162/4)−0 ✓ 余 2px = 可滑动提示（预期）`、`ListWheelPicker14Col1/2 item 高 36 = int(180/5)−0 ✓ 余 0px`（320 版 24 / int(98/4)、 int(120/5)）。**回归**：旧两版示例重跑仍 exit 0，顺手把旧示例 2 条 **#27 同族 WARN 修成 0**（行族文本盒改全页族预留）。**未支持（如实，渲染图为准）**：json2img v0 对 `radiogroup`（数组子项→选项区空白）、`checkbox`（只画未选）、`listview item/subItem`、`subitem picTab`、`seekbar defProgress`（近似而非横向裁剪）均为降级；滑轨/标记盒阈值（可见条 ≥10px、<24px 不给内点、不用 1px 描边环）均 aa_audit 实测逼出。v0.27.163-open',
    '2026-10-01: **listview item 高口径定死（余数=有意的「可滑动提示」）+ check_all #37** v0.27.162-open（钟工：「拿竖向刷新来说…系统会自动用 (400/6)-5=61.66，实际每个项目高度会被设成 61，加间隔 66×6=396，**多出来 4 个像素就会显示一部分下一个内容**——所以不一定要完全等于高度，多出时就是故意设计让用户知道可以继续滑」）—— ① **知识**：`knowledge/uicontrols/json-field-mandatory.md` 的 `listview.item` 段补上 **公式 `itemH = int(lv高/rows) − rowSpacing`** 的**设计意图**：**除不尽的余数是有意的**（底部露出下一项一小块 = 「还能继续滑」的提示），**不要求 `rows×(itemH+rowSpacing)` 恰好等于板高，也不要把「底部露出下一条」当缺陷**；附钟工算例（100 高 / rows 6 / spacing 5 → 61，66×6=396 → 余 4px）。反向错法才拦：**比公式大 → 挤爆/裁切；比公式小 → 每项底部多空带**。② **工具**：`ui_tools/check_all.py` 新增 **#37 listview item 高核对**（读 lv 高/rows/rowSpacing 与 item 模板高；不等 → WARN 并区分挤爆/空带；相等 → NOTE 出「余 N px = 可滑动提示（预期）」）。③ **实测**：官方 `basedemo…/listViewDemo-New` → `CityListView 36 = int(164/4)−6`（余 0px）、`ListView1 140 = int(437/3)−5`（余 **2px** 提示），**0 WARN**；blocklib 两版/ SmartPanel 无 listview → 跳过。④ **与 #11/#17「图 == 盒」的边界**：那条只管「图 vs 控件盒」（盒子由公式决定），**不适用**于「底部露出下一条」。v0.27.162-open',
    '2026-10-01: **B 观感判据第一批（check_all #31/#32/#35/#36）：把「不好看 / 会溢出」变成设计期机读结论** v0.27.161-open（钟工「按顺序执行」）—— ① **#31 行族对齐轴（WARN）**：同页、同角色（caption Label/Value）、同对齐（**只比左缘**；右缘因「本行右端控件不同（箭头 vs 开关）」天然不同 → 不报）的文本左缘必须收敛到众数轴；族内 <3 不报（无基准）。误报面：SmartPanel 14 页 **0**、blocklib 两版 **0**、官方 SampleUI-New **0**。② **#32 垂直间距节奏（降级为 **NOTE**）**：同一容器内「行命中区（ButtonRow*）」的垂直步进 >3 种则提示。**首版口径在 SmartPanel settings 仍有 1 处噪声（ButtonRow* 里混了非行命中区的小按钮，步进出现 0/2/6/7/12/29）→ 主动降为 NOTE（只提示不拦），口径稳定后再升 WARN**。③ **#35 箭头盒下限（WARN）**：`*Chevron*` 盒 < 12×16 → WARN（更小的盒会把笔画压成 1px）；4 个工程 0 报。④ **#36 文本盒余量（NOTE）**：盒宽 < 估算宽 ×1.05 → 提示「运行期长值易撑破」（#13 只管「装不下」）；SmartPanel 报 10 条，均为「余量 1~3px」的真提示。⑤ 下一批：**#33 层级三件套**（字号档 ≤5 + 大字号不得配更浅色）、**#34 文本对比度（FAIL，委派 `tools/qa/contrast_check.py`）**。⑥ 过程如实记：本条初版派给子代理执行体，**它在落盘前中断**，父级接手实现，并按「上判据前先扫误报面」收紧两轮口径（同一坑当日第二次）。v0.27.161-open',
    '2026-10-01: **行族图标「同页统一」自检（钟工口径：同一页面统一设计）** v0.27.160-open（钟工：「1. 同一页面统一设计；2. 按照顺序执行」）—— ① **为什么**：图标列一旦被某行占用，**所有行的文本左缘都会右移一个列宽**（全页对齐）；此时只有个别行真画图标 → 观感上像「那几行多长了一块」（实测 1024 版只有多屏拼接/客厅面板两行有图标）。② **加自检**：`compose.py` 新增 `assert_icon_uniform()`——**同页行族图标要么都有、要么都没有**，混用直接报错退出并列出「哪几行有图标」；在两个示例里**统一为无图标模式**（`icon_row`/`device_card` 去掉 icon 字段；要演示图标模式就把 icon 补全整页）。③ 两版示例重生成后 `check_all exit 0`。④ **下一步（按钟工定的顺序）**：B 观感判据补齐（对齐轴 / 间距节奏 / 层级三件套 / 对比度 / 图标盒下限 / 文本余量，接为 check_all #31~#36）→ C 真机基线库 + 挂进确认闸门 → D HTML↔json 对照库。v0.27.160-open',
    '2026-10-01: **行内「值 → 右端控件」间距修正：按屏比例 + 锚定本行控件（修 320 上「已连接离箭头太远」）** v0.27.159-open（钟工：「320*240 上已连接到右箭头的效果比例不对…为更美观已连接应该靠着箭头，这个在设计规范/样式/AI 原生 UI 设计上没考虑吗」）—— ① **根因（两条）**：`right_edge = 行右缘 − pad_r − (reserve + text_chev_gap)` 里的 `reserve` 是**全页最宽右端控件**（如开关 78px）→ **只有箭头的行也按最宽预留，白多留一截死区**（实测 320 上「已连接」右缘 252 → 箭头左缘 284，**间隙 32px = 10% 屏宽**）；而 `text_chev_gap` 又是 **token 绝对像素（8）**、没随屏缩放。② **修**：值文本右缘改为**锤定本行实际右端控件**（箭头/开关，两者取更左）左缘 − 间隙；间隙改为 **`clamp(r4(屏高×0.013), 4, 10)`**（600→8 / 240→4）；`blocks/_tokens.json` 新增 `text_chev_gap_min/max/of_h`。③ **自检**：`compose.py` 新增 `assert_row_gaps()`——同页行族该间隙必须一致（防「有的行贴箭头、有的行留死区」），不一致直接报错退出。④ **实测（修后）**：1024 各行间隙恒 **8**、320 恒 **4**（含开关行）；两版 `check_all exit 0`；渲染图重生。⑤ 诚实回答：设计规范层面这是**真缺口** —— 我们有「同族口径全页统一」的规则，但漏了「值文本右缘→本行右端控件」这条锚定口径，TDesign 的 `gap` 本来随 rpx→px 缩放，我们的 token 没做这个换算。v0.27.159-open',
    '2026-10-01: **修「白框底色与文本列表区错位」（容器子节点用绝对坐标 → 父子双计）+ compose 自检** v0.27.158-open（钟工：「白框底色和文本列表区域错位了…之前好像出现过这个问题」）—— ① **根因**：`build_card` 里卡底图节点 `CardBg<N>` 传的是**卡片的绝对 x/y**（`self.box(x, y, cw, ch_)`），而它是 `Card<N>` window 的**子节点**（子节点坐标是相对父容器的）→ **父子双计** → 白卡底色整体右下各偏一个 margin（实测 1024 版偏移 +16 x / +28 y，992 宽从 x=32 起 → 右缘 1024 溢出屏外）；同类事故在 SmartPanel 也出现过（卡片底图/装饰件用绝对坐标、白卡盖住圆角）——这是「错位」这类问题的通用根因。② **顺带**：行间分割线宽 `cw - pad_l` → 右端贴边（不对称），改 `cw - 2*pad_l`（左右各内缩 pad_l）。③ **防复发**：`compose.py` 新增 `assert_children_fit()`（容器子节点盒必须落在容器盒内）并在 build_card 末尾断言 —— 同类「绝对坐标当子节点坐标」当场报错退出、不出产物。④ **实测**：修后 `CardBg1` 与 `Card1` **同盒**（16,104 992×180）、`RowSep2` = 32..992 对称；两版示例 `check_all exit 0`。v0.27.158-open',
    '2026-10-01: **修「产物 caption 唯一性」缺陷（生成的回调重定义 → C++ 编译不过）+ check_all 新增 #30** v0.27.157-open（我按钟工要求复核块库产物时发现）—— ① **缺陷**：块库/组装器生成的 caption **跨卡重复**（`_name` 按卡内序号、每卡重置）→ `ui/main.json` 里 `ButtonRowSettingRow1` / `ImageRowSettingRow1Chevron` / `TextRowSettingRow1Label`/`Value` / `RowSep1` 等 **13 个值重名** → `mainLogic.cc` 里 `onButtonClick_ButtonRowSettingRow1` **定义两次**（行 45/57）⇒ **编译必失败**。② **为什么一路 PASS**：`check_all` #5 只查「回调**是否存在**」、**不查唯一**（判据缺口）。③ **修**：组装器命名改**全页全局递增 + 按块类型前缀**（`SettingRow4`/`IconRow7`/`ToggleRow6`/`DeviceCard9`/`Card5`/`SectionHeader10`，子控件继承父序号、`RowSep<上文序号>`），并在**出产物前自检**（重名直接报错退出、`ui/main.json` 不落地）+ `emit_logic` 二道闸；`ui_tools/check_all.py` 新增 **#30 caption 唯一性**（同 json 内 caption ≥2 次 → FAIL，逐条列「页面 / caption / 次数 / 控件 key / 后果」）。④ **实测**：两版示例重生成后 **0 重复 caption / 0 重复回调**、`check_all exit 0` + `[PASS] 1 页 caption 全部唯一`；**反例**（git HEAD 修前那份 json+cc 还原成工程）→ **exit 1 + 5 条 FAIL**（逐条点名重名 caption 与控件）；同页多实例（2 卡+2 空态+2 底栏+2 弹窗）42 控件 0 重复；渲染像素无回归（与修前差集 `bbox=None`）。v0.27.157-open',
    '2026-10-01: **界面块片段库 + 组装器 MVP（`templates/ui_blocks/`）：AI 从「手算坐标」变「选块 + 填值」** v0.27.156-open（钟工：「按照你的建议做」）—— 对标 web 的 Bootstrap/组件库，把设计决策预制：① **10 个块**（`page_title`/`section_header`/`setting_row`/`toggle_row`/`icon_row`/`card`/`device_card`/`empty_state`/`bottom_actions`/`dialog`），每块含字段、**相对约束**（不写死某屏绝对像素）、需要素材与尺寸推导、caption 命名、能否滚动、**禁止项**；② **唯一数值源** `blocks/_tokens.json`（TDesign v1.17.0 令牌 + 定版比例）；③ **组装器** `compose.py`（~1000 行）：`spec.json → ui/<res>/main.json + 切图 + logic 骨架 + 渲染图 + check_all`，**一条命令出全套产物**；④ **两版示例同一套块**（1024×600 基准屏 / 320×240 边界屏）：**两版 `check_all` exit 0 / 0 WARN**、渲染 PNG == resolution、#26 行程与 #27 同族口径全过；⑤ 关键口径：`setting_row` 用**两行式**（单行式是返工第一名）、极小屏整页降单行式禁同页混用、容器/次按钮素面（1px 描边环会让弧线 AA 退化成硬阶梯）、箭头走专属口径自绘、**切图全部走 `gen_res`**；⑥ 自测：1024 版 10 块/7 行/**66 控件**/19 张图，320 版 **59 控件**/15 张图，`json2img --report` 仅 `bold` 一类未支持（渲染器无 Bold 变体，真机由字库承担）；⑦ 用法：`python templates/ui_blocks/compose.py <spec.json> --project <项目根> --render --check`。v0.27.156-open',
    '2026-10-01: **离线所见即所得接成 op：`ui_visual` 新增 `render` / `render_check`（设计流向 HTML 体验靠拢）** v0.27.155-open（钟工：「接着做，做成 op，我希望接近 html 的设计… html 我只是为了让你更好的适应 PC 端的各种适配」）—— 设计流闭环：`AI 写 HTML/CSS（PC 侧适配优势）` → `flythings_html_to_json` → `ui/*.json` → **离线渲染图（引擎等价）** → **一致性判据** → 确认稿 → pack/推真机。① **`action="render"`**：项目 json → PNG（离线所见即所得）。参数 `project_root`(必填)/`page`/`scale`(NEAREST)/`out`(缺省 `<项目>/ui/_render/<page>.png`)/`all`；返回 `pages[{page,png,size}]` + **`unsupported`（逐条原样透出不吞）** + `missingAssets/stretched`。② **`action="render_check"`**：渲染图 vs 真机截图 → 一致性判据。参数 `device`/`json`(必填)/`render`(可自动渲染)/`tol`/`max_ratio`；返回 `nonTextConsistencyPct`/`runtimeTextRatioPct`/`maxBlock`/`pass`/`attribution[]`；**不一致时 `ok=false` + `code=WYSIWYG_MISMATCH` + message 写明差在哪**（绝不静默）。③ 实现只做**单一实现调用**（子进程调 `ui_tools/json2img.py` / `wysiwyg_diff.py`，不复制逻辑）；工具数保持 **43**。④ **docstring 硬预算**（单 op ≤900 / 全体 ≤12000）：`ui_visual` 429→687 字符，靠精简 11 个 op 文案腾出，全体 **11999→11937**。⑤ 契约同步：`tests/test_ui_visual_merge.py` +8 用例（422→430）、`op_seealso.json` 加 `devflow/wysiwyg-render-spec`指针。⑥ **实测（SmartPanel_HA）**：`render` wall 页出 480×480；`render all=true` 14 页全出；`render_check`（真机基线 s03_wall_page.png）→ **`nonTextConsistencyPct=100.0` / `pass=true`**、`maxBlock 0x0`、attribution 30 条；缺参回 BAD_PARAMS+本 action 参数清单、传别家参数回 visualNote。v0.27.155-open',
    '2026-10-01: **离线「所见即所得」：渲染语义规格 + 引擎等价渲染器 + 一致性校验（实测非文字区 100%）** v0.27.154-open（钟工：「json 布局清晰…为什么做不到直接预览还需要上机，这不符合 AI 的逻辑」→「所见即所得上面应该是可以做到 100%」）—— ① **新增 `knowledge/devflow/wysiwyg-render-spec.md`（渲染语义单点真相）**：R1 绘制顺序=json 树序（父先子后、后定义在上）/ R2 单节点顺序=底色→背景图→文字→子控件 / **R3 图 != 矩形＝拉伸填充** / R4 颜色（-1 透明、0 不透明黑）/ R5 子控件相对父矩形、无 flex 无层叠 / R6 滚动容器按 rect 裁剪 / R7 文字字段 / **R8 字体必须与设备同款 TTF** / R9 九宫格 / R10 控件专有绘制；并划清边界（运行期数据文本、滚动位置、动画/视频/屏保/旋转、系统栏＝**不做承诺，需上机**）。② **对齐位模型定案（真机基线）**：`alignment` 是位模型（低 2 位水平 0 左/1 中/2 右，次 2 位垂直 0 顶/1 中/2 底），**`4/5/6 ≡ 36/37/38`**、`1≡33`、`9≡41` —— 旧文档只记了 36/37/38，而工程里 **91% 的文字控件用 4/5/6/0/1**（只按「36=左」处理会把右对齐的值摆到左边）；证据＝真机基线二选一：多屏拼接页 **1690 px（位模型）vs 8608 px（一律 36）**，设置页 3456 vs 4778。③ **新增 `ui_tools/json2img.py`**（引擎等价 PIL 渲染器，~1100 行：树序/拉伸填充/纯色/设备字体/视口裁剪/9-patch/控件专有绘制，`--align-mode measured|task36` 可切换、`--report` 如实列未支持项）。④ **新增 `ui_tools/wysiwyg_diff.py`**（渲染图 vs 真机截图：非文字区一致率 + 逐控件归因 + 连通块结构性差异检测 + 自动排除运行期文字盒）。⑤ **首例实测（projects/SmartPanel_HA，真机基线 480×480）**：**非文字区（几何/图/纯色/层级）0 px 超容差 = 100.00%**、无结构性差异；差异只在文字字形（同字体、同位置、边缘 ±2px 的栅格化差异），运行期值/状态文本已单独排除（25.6%/12.5% 属设备 live 值）。⑥ 交叉链：`ui-layout-verify` §5 加离线所见即所得指针；工作区 `references/kb/controls.md` 对齐行补等价族。⑦ 工具侧仍为 CLI（op 接线下一版）；**动态效果一律不承诺**。v0.27.154-open',
    '2026-10-01: **引擎图像语义更正：图 != 盒子时是「拉伸填充」** v0.27.153-open（钟工：「图不等于 rect 区域的时候 easyui 采用的方式是拉伸填充」）—— 之前知识库内部**自相矛盾**：#11 的文案写「FlyThings 不缩放普通 PNG，图与盒子不等即错位/裁切」，而 #17/verify_assets 同一份代码里又写「引擎会拉伸」（基准工程 SampleUI-New 的 navi/fh.png 44×26 放 72×40 按钮就是合法拉伸）。现按实际引擎行为统一为：**普通 PNG 一律拉伸填充到控件矩形，尺寸不等不报错**；「图 == 盒」是**质量纪律**（非整数缩放必糊/变形、正圆变椭圆），不是引擎贴不上 —— 也是本仓 #11/#17 FAIL/提示分级的真正理由。改动：`ui_tools/check_all.py`（#11 打印头 + `verify_assets` docstring）、`ui_tools/HTML_SUBSET.md`（五要素 ①）、`knowledge/devflow/ui-layout-verify.md`（内置预检表红项）、`knowledge/devflow/ui-asset-rules.md`（铁律 1 补引擎行为）、`knowledge/uicontrols/scrollwindow-layout-checklist.md`（行条/图标「引擎不缩放」→「会拉伸填充，非 1:1 就糊」）。未改判据逻辑（FAIL/提示分级不变），只改「为什么」的表述。v0.27.153-open',
    '2026-10-01: **撤下 check_all「坐标越界/负值」（json 负值合法）+ 顺延编号为 #28/#29** v0.27.152-open（钟工：「坐标负值不是什么问题呀。怎么会报 warn」）—— 上一版（v0.27.151）我把 SmartPanel 真机问题单里的**运行期**语义直接做成了 **json 静态判据**，属越界使用，当日纠正：① **json 里 `left/top` 负值是合法写法** —— 官方 wiki `scrollwindow-layout.md` §2 明写「left/top 可为负值：内容 window 的 left:-175 是初始偏移」，官方 `ScrollWindowDemo-New` 事实就是 `window__2 left=-175`；`-1` 表未设置（`SampleUI-New/1024x600/ad.json`）、装饰件越界（`button top=-7`、`textview left=-12`、分隔线宽 1157 超出 1024 屏）都在用。② 实测误报面：官方/存量工程里「非滚动内层越界」控件 **26 个**（textview 15 / window 4 / edittext 4 / button 1 / listview 1 / painter 1）→ 静态 WARN 会常年清单噪音。③ **处置**：`ui_tools/check_all.py` 删除 `check_coord_sanity` 及其接线，原 #29/#30 顺延为 **#28 UTF-8 文本陷阱（src 静态扫描）** 与 **#29 显示件吃掉下层触摸**（发布当晚即时更正，避免断号；docstring 写明撤下原因与编号变化）。④ **知识层重新定界**：`knowledge/uicontrols/json-layer-rules.md` 「坐标负值 = 从右/下算」开头加「适用范围」块——只约束**运行期算出的绝对坐标**（拖动夹取 / 落盘回读 / `setPosition`），json 负值不告警；「一眼发现」改为看**运行期落盘的业务坐标**（prefs），不是看 `ui/*.json`。真实教训保留：夹取到绝对 0 + 右下留 40px/1/3 + 读回 `-1`/越界当未设置。v0.27.152-open',
    '2026-10-01: **SmartPanel_HA 复盘第一批入库：5 篇通用经验 + check_all #28/#29/#30** v0.27.151-open（钟工：「这些哪些是可以做一个通用的知识库入库的，去解决以后在做的时候消费时间和反复去试的一些问题」→「做第一批」）—— 从真机工程 `projects/SmartPanel_HA` 挖出「不写下来就得靠试」的通用经验，按「现象 → 根因 → 做法 → 怎么一眼发现」落库，每条带 `文件:行号` 证据（子代理实读+父级抽查核对）。① `knowledge/uicontrols/json-layer-rules.md` 新增 **「坐标负值 = 从右/下算」**：`LayoutPosition` 里负的绝对坐标被当成 bottom/right（不是负偏移）→「重启后控件跑位」，当次看不出来；做法=拖动夹取夹到绝对 0（右下至少留 40px/1/3）、落盘 -1/越界一律当未设置（真机问题单 09251751-8，`mainLogic.cc:598-635`）。② `knowledge/uicontrols/text-box-height-rule.md` 新增 **§7 UTF-8 文本三件套**：按前导字节在字符边界截断 / 限宽按单位估算（汉字 1.0·ASCII 0.55，不用字节数）/ **禁用 `find_first_of("：")`**（按单字节匹配会切进汉字中间，实测「回家模式」被切坏 → 用 `find("整串")`）+ 可直接抄的 `utf8CharLen`/`fitUnits`/`textUnits`。③ `knowledge/devflow/activity-code-skeleton.md` 新增 **§3-2~§3-4**：`onUI_hide` 后本页定时器照跑 → 空闲/超时判定必须加可见性门控（否则子页待 15s 被拽回屏保）；**计时禁用墙钟**（NTP 拨钟跳变 → 永不推进或瞬间触发）改心跳 tick；`static` 缓存与控件同生命周期（QR「切一下才显示」的根因）+ `onUI_quit` 清理清单。④ 新增 `knowledge/devflow/mqtt-client-lifecycle.md`（291 行口径、10 节）：单一重连真源 + 建连前回收旧 client + 代次(gen)作废旧回调 + 指数退避（否则同 `client_id` 互踢风暴）/ **retained 回放 ≠ 命令**（只认精确 topic + payload 恰为 ON/OFF，否则一重连就关灯）/ 回调线程纪律 / 上行顺序 availability→discovery / LWT 主题四处逐字一致 / 板内 broker(MiniBroker) 回退能力边界；`packages/mqtt-cxx/README.md` 与 `dependency-package-docs.md` 加交叉指针。⑤ `knowledge/devflow/video-wall-sync.md` 新增 §7（原 §7→§8）+ 工作区主源 §13 改写为 **NTP 口径换代**：**网关踢出 NTP 列表**（实测网关不跑 NTP，每次白等 ~3s）/ 内置公网 IP 列表直连 / 库样本 4 个取最小交换耗时 / 偏移 ±20ms 内不拨钟 / **每 10 分钟刷新**（旧文档写「每 30 分钟」）/ 在飞保护 + 30s 最小间隔 / groupFollow 死区 15ms·>1s 步进·1ms/s 慢爬（无比例增益）。⑥ `ui_tools/check_all.py` 新增 **#28 坐标越界/负值**（负值不分层都报；right/bottom 越界报，但滚动宿主内层内容允许超出）、**#29 UTF-8 陷阱静态扫描**（src/lib 里多字节 `find_first_of/find_last_of`，先剥注释保行号）、**#30 显示件吃掉下层触摸**（补 #15 的反方向：显示件该关 `touchable` 没关 → 整块点不动/只剩缝隙能点；容器/整屏/近全覆盖/modal 视为故意不报）；自测=UISpec-Demo + SmartPanel_HA 共 16 页 **0 误报**，构造反例（负坐标 / 越界 / 多字节 find_first_of / 显示件 touchable=true）**必报**。v0.27.151-open',
    '2026-10-01: **修 json2html 预览漏渲染 scrollwindow / pagewindow 的子控件** v0.27.150-open（钟工验收 UISpec-Demo 时发现客户确认稿里滑动区一片空白）—— 根因：`ui_tools/json2html.py` 的 `_render_control` **只给 `window` 写了递归分支，`scrollwindow`/`pagewindow` 落到兜底分支** → 生成的 `*.confirm.html` 只剩容器壳（`data-caption="ScrollSet"`），**里面的行控件全部缺失**；而这两类容器按层级铁律只能装 `window`，等于**所有用滑动窗口的页面，客户确认稿都会漏掉滑动区内容**。修法：补 `scrollwindow`/`pagewindow` 分支，递归渲染子控件（视口裁剪由 `.ctrl` 的 `overflow:hidden` 提供，与引擎一致：内层 window 高于视口时多出部分被裁）。实测同一份 UISpec-Demo：确认稿 `class="ctrl"` 计数 **4 → 63**，行控件 `TextRowWifiLabel` / `ImageGrpDeviceCard` / `ButtonRowWall` 全部出现。注：MCP 服务进程内已加载旧模块，**需重启 Gateway/MCP 后 `flythings_ui_preview` 才生效**（CLI 路径已生效）。v0.27.150-open',
    '2026-10-01: **设置行口径改回“相对约束 + 规则”（不订具体尺寸）+ #27 补无基准提示** v0.27.149-open（钟工：「给相对约束和规则。不要订具体尺寸。屏幕实际分辨率从 320*240 到 1920*1080」）—— ① 纠正上一版（v0.27.148）把某块 480×480 面板的绝对像素写进“设置行模板”的做法（**跨分辨率会直接失效**，且与 `scroll-drag-interaction-spec.md` §2 R6 的 1024×600 基准**相互打架**）：`knowledge/uicontrols/scrollwindow-layout-checklist.md` §2.1 重写为 **相对约束表**（行条宽 = 内容区宽 − 外边距；行高 = 步进 − 间隙；图标底/图标在行条内左侧垂直居中且高 ≈ 行高 × 0.6~0.7 / 0.4；标题与值 **同左缘**、值在标题**正下方**；箭头贴行条右缘 − 右内边距且**与文本盒留间隙**；同族 alignment 一致；**图 == 盒**）+ **两条纪律**（加行照抄同页口径禁自创形态 / 文本禁止为避让控件改宽挪位）；新增「无既有行可照抄时」以 **1024×600 为唯一基准屏**（与 R6 对齐）的比例区间与换算式 `v′ ≈ v × 目标屏高/600`（取整偶数、不破可辨识下限）；新增 **分辨率边界**（320×240 极小屏优先保文本两行、图标可省；≥1280×800 行高按可用高反算、字号走阶梯档位不线性放大）；480×480 的实测数字降级为「仅作量级参考，不是规范」。② `ui_tools/check_all.py` **#27** 补：族内成员 <3（无同页基准可对比）时给出 **提示**（按同页其它行口径或按基准屏比例换算），不再静默跳过。判据本身本来就只看**页内自洽**、不依赖任何绝对尺寸（未变）。v0.27.149-open',
    '2026-10-01: **设置行模板口径 + check_all #27（同族口径离群 / 文本×图标重叠）+ 工程实证修复** v0.27.148-open（钟工：「希望以后在设计的时候就可以解决」「你当时添加箭头的时候把文本和箭头混合到一起了」）—— ① **纪律（知识层）**：`knowledge/uicontrols/scrollwindow-layout-checklist.md` 新增 **§2.1 设置行模板（照抄不许自创）**：行条 (14,rowTop) 452×50 步进 56 / 图标底 (28,+8) 34×34 / 图标 (35,+15) 20×20 / 标题 (75,+6) 300×22 a=0 / 值 (75,+27) 300×20 a=0 / 箭头 (424,+15) 26×20；两条纪律 =「**加行照抄同页口径，禁自创形态**」「**文本禁止为避让控件改宽/挪位（不许挤文本去让位）**」；§1 第 6 条重写为「箭头与文本挤在一起」的双根因（引擎先画背景图后画文字 + 自创单行式）。② **工具层**：`ui_tools/check_all.py` 新增 **#27 同族口径离群 + 文本×图标重叠**（同页同父同角色按 caption 归族，取 (left,width,height,alignment) 众数，偏离即 WARN；众数占比 <0.6 的族跳过防误报；文本盒 ∩ 图标/箭头盒相交也报）。自测：修前 1 条（正是那个值框离群）、修后 0 条。③ **工程实证（SmartPanel_HA）**：「多屏拼接」行按模板改齐——值框 `300,780 118×22 a=6` → `75,787 300×20 a=0`；行条 452×46 → 452×50（换 `srow452x50.png`，撤掉 09-27 那个“收窄值框躲箭头”的 hack）；icon/iconBg/label/chevron 偏移校准；行距 64 → 56。推 .71 真机像素复核：行条 pitch 全 **56**、该行墨迹 **77..149** 与同族一致（修前 77..416）。v0.27.148-open',
    '2026-10-01: **scrollwindow 布局异常清单 + 部署一致性自检（selfcheck 第⑪区）** v0.27.147-open（钟工：「问题整理更新到 mcp 里面，确保问题不会再出现」）—— 把 SmartPanel_HA 反复返工的那批问题落成**知识 + 判据**三层。① **新增 `knowledge/uicontrols/scrollwindow-layout-checklist.md`**：结构模板（scrollwindow=视口 → 内层 window=内容，固定件外置）+ **十类反复异常表**（加行忘加高内层 window→末尾滚不到 / 新控件直挂 scrollwindow→整块不显示 / 固定件被滚走 / 把 dragMaxDis 当行程 / 滚到底后触摸坐标忘叠偏移→点错行 / 行内图标被数值文字盖住（引擎先画背景图后画文字）/ 同行切图口径混用→倒角看粗 / 缺 touchable→拖不动 / 部署层混搭 + ftu 回退→「改了像没改」/ 设计期没算总高→堆叠），每条给「现象→根因→修→机读判据」；含**建/改页流程**与**上机五条复核判据**（10-01 真机实测口径）。② **新增 `knowledge/devflow/deploy-consistency-check.md`**：`resPath` 与 `startupLibPath` 必须同源（只换 lib 不换 resPath = 「新库 + 旧界面」，症状恰是“改了像没改”，10-01 真机实测）+ 四步部署后自检 + 处置表 + 两条纪律（tmpfs 余量、脚本 ASCII）。③ **工具层新增 `flythings_selfcheck` 第⑪区「部署一致性」**（分区 10→11）：读三处 EasyUI.cfg 判生效源、比 `/tmp` 与 `/res` 的 lib/UI 两代 md5、`mixed=true` 报“新库旧界面”；契约用例同步（10→11）。④ 交叉链：`scroll-drag-interaction-spec` / `json-layer-rules` / `package-properties-easyui-cfg` / `selfcheck-and-bugreport`（九→十一分区）。⑤ 检索回归新增 2 组（21 条真实问法，top-1 6/7、top-3 8/9，未命中的泛问法已如实登记 max_miss）。v0.27.147-open',
    '2026-10-01: **dragMaxDis 语义修正（= 越界拖拽上限，不是行程）+ check_all #26 scrollwindow 行程核对** v0.27.146-open（钟工：「dragmaxdis 是可以拖出去多长像素的意思吧」→「按照你的建议改」）—— ① **语义修正**：`dragMaxDis` 在四个滑动控件（listview/scrollwindow/pagewindow/slidewindow）**语义一致 = 越界拖拽上限（overscroll）**，**不是行程**；行程由内容决定、引擎自算（scrollwindow = 内层 window 尺寸 − 视口；pagewindow/slidewindow = (页数−1)×页宽；listview = 项数×行高 − 可视高，运行期）。旧口径「scrollwindow/pagewindow/slidewindow 上填行程值（200/内容尺寸）」**作废** —— 双反例：① 官方 `ScrollWindowDemo-New` 视口 450 / 内层 window 800（行程 350）而 dragMaxDis=200（既非行程也非内容尺寸）② SmartPanel_HA `ui/settings.json` 视口 418 / 内层 832（行程 414）而 dragMaxDis=60，真机点 (240,438) 可进「多屏拼接」页（实际滚 ≈302px 到底）→ 证明 60 只管越界拖拽。**误读来源**：UIlayoutDemo 那份 dragMaxDis=2400 恰好 = 内层 window 尺寸、且 edgeEffect=0（越界本就不生效）。② **工具层**：`ui_tools/check_all.py` 新增 **#26 scrollwindow 行程核对**（行程 = 内层 window − 视口，**不读 dragMaxDis**）：每处 NOTE 打「视口/内容/行程/dragMaxDis」；WARN-A 行程≤0 但内层内容已超出 → 内层 window 没跟上（末尾控件被裁/滚不到，SmartPanel 反复踩的那类）；WARN-B `edgeEffect` 生效且 `dragMaxDis ≥ 控件可视尺寸` → 一次拖出整屏（露底），改手感值（基准 50~200；480×480 取 40~60）。③ **文档同步**：`knowledge/uicontrols/scroll-drag-interaction-spec.md`（§0/§1/§2 的 R1·R2/§3/§4/§5 + 新增 §5-1 双反例与 R10）、`json-layer-rules.md`、`pagewindow-fields.md`、`slidewindow-fields.md`、`json-field-mandatory.md`、`ui_tools/HTML_SUBSET.md`、`ui_tools/html2json.py` 注释；工作区 `references/kb/controls.md`·`design.md` 同步。v0.27.146-open',
    '2026-10-01: **ha_bridge 组件形态真机验收通过（Z20 · zkgui 工程）** v0.27.145-open（钟工：「ha 验证下」；wall_sync 明确不验）——按钟工口径「带界面的功能验收必须走 FlyThings zkgui 工程，不能拿 bin 交付」，新建 zkgui 工程（Z20 / 480×480）接入 `components/ha_bridge`（`include/`+`src/` **原样拷入零改动**），真依赖真编译（`fun install` + `fun build -p Z20`：mqtt-cxx 3.2.0 + paho-mqtt3as + openssl 1.1.1-w + base-json + base-utility + log + easyui）后上机真机。**五条判据全过且留原始证据**：① 设备连上 broker（设备日志 + broker `emqx ctl clients list` 两侧）② 上行 availability/state/status **retained**（发完后新订阅回放，5 条全 `RETAIN=1`）③ 连接后**自动发 HA Discovery**（3 条 `homeassistant/switch/…/config` retained，字段与 RelayBank 语义一致）④ 下行 `…/switch/relay_<n>/command` ON/OFF → `onCommand` + RelayBank 状态 + **继电器真实动作**（过零 IO `zeroIoNum=4`，`sp_relay_state` 1→7→6→0）+ UI 截图 ⑤ `start()/stop()` + broker kick 重连（`old client dropped (gen=6)` → 回连 ≈0.56 s；同 client_id 计数恒 **1**，无互踢风暴）。实测：连上→发完 discovery/state/status ≈0.14 s；重启后 `restored mask=0x7` 恢复硬件并回发 retained。**未取证（如实标注）**：QoS1 全链路 / LWT 异常断线 / MQTTS+鉴权 / 吞吐时延 / `clearDiscovery` retained 撤销 / `extraSubscriptions` / 哨兵 -1 分支 / 物理灯肉眼观察 / 其它平台（registry 无 `mqtt-cxx`·`paho-mqtt3as`）。**设备零残留**：`/tmp/ui` **131/131 逐文件 md5 相等**、`/tmp/lib/libzkgui.so` 与 `/tmp/EasyUI.cfg` == 备份、prefs 未变、**`sp_relay_state=0`（三路继电器全关）**、临时文件已清、broker 上 retained 已清空。组件文档回写（platforms.md 新增「§6 组件形态真机验收记录」+ 平台总表 + README 验证状态），内网 IP 已脱敏。v0.27.145-open',
    '2026-09-30: **album_upload 组件形态真机验收通过（Z20）+ 两条验收判据修正** v0.27.144-open（钟工：「用1.71验收…只能烧录进去后确认可以用就可以了」）——按 FlyThings 框架做法新建 **zkgui 工程**（480x480，二维码控件页）接入组件，**四条判据全过且留原始证据**：① 二维码渲染上屏 ② **从截图解出码内容 == `qrInfo()` 兜底值**（`decode_qr_url.py --expect` 通过）③ TCP 9000 `LISTEN` + UDP 8899 广播（**接收端抓到广播**证明）④ PC 发 205 B 图 → 落盘（设备侧 md5 == PC 侧、无 `.tmp` 残留）+ 组件 `onFileAdded` 回调日志 + 页面计数 4→5。**判据修正（值得记住）**：UDP 广播是「未 bind 的 socket + `SO_BROADCAST` + `sendto 255.255.255.255`」→ **`netstat` / `/proc/net/udp` 里查不到 8899**，判据必须换成接收端抓广播；`fun launch` 多设备硬失败时改用 MCP 自己的 adb 层（全程带 `-s`）复刻部署约定。**未取证（如实标注）**：手机微信真扫（用协议等价 PC 客户端代跑）、配置分支（设备 prefs 无 `sp_qr_url`，只走了兜底分支）、其它平台（Z21/T113/V85X/F135/F136）与吞吐数字。**设备零残留还原**：`/tmp` 三件 md5 与原样一致（`/tmp/ui` 131/131 逐文件相同）、prefs 未变、继电器全关、增删文件已复原。组件文档（platforms/README/example）已回写验收记录。v0.27.144-open',
    '2026-09-30: **mp_transfer 收口成「拿进去就能编」（自带 mp_config.h + 弱符号解析钩子）+ 71 真机验收记录** v0.27.143-open（钟工：「用1.71验收。验收后记得还原回去哦」）——① **去工程私有依赖**：`tcp_receive.cpp` 原来 `#include "config.h"`（MP_PATH）与 `mtp_monitor/file_parse_manager.h`（`FileParseManager::parseFile`）都是来源工程私有件，照抄编不过。现在组件自带 `src/mp_transfer/mp_config.h`（`MP_PATH` 默认 `/mnt/sdnand/album/`，可 `-DMP_PATH=` 覆盖）+ **弱符号解析钩子** `mp_parse_file()`（默认只填 path/name/size/mtime，不做媒体解析）；要宽高/时长就写强符号覆盖，或 `-DMP_TRANSFER_HAVE_FILE_PARSER=1` 走原工程那条路。② **验收实测（一台 Z20 面板）**：baseline 全量取证（props / prefs / /tmp / fb0 截图）→ 把组件形态编成 `bin` 工程上机时**卡在 `base-utility` 头要 SDK 的 `os/MountMonitor.h`（在 easyui 包里），强行链 easyui 又带一堆未解析符号（jpeg/freetype/nanovg/MI_*）** → 结论：**本组件属 zkgui 工程，验收须接进 zkgui 工程**（该限制已写进 mp_transfer README「编译前置」一节）。③ 设备侧另发现：该面板的**触摸注入能唤醒屏幕但点不进 UI**（点卡片后 `sp_relay_state` 仍 0、logcat 无 relay 动作），需先核对 touch 的坐标/量程口径 —— 已停手；设备**零改动**还原（未推包 / 未写 prefs / 继电器 0 / 临时文件已删）。v0.27.143-open',
    '2026-09-30: **album_upload 收口：二维码只用 URL 现场生成（去掉「图片」那条路）** v0.27.142-open（钟工：「二维码直接用 url，不要图片」）——① **API 收口**：`QrMode` 收成 `QR_FROM_CONFIG` / `QR_LOCAL_UPLOAD_FALLBACK`；`QrInfo` 只留 `mode + content（永远非空）+ local_url`；`Config` 删 `qr_image_url`/`qr_image_local_path`；删 `setQrImageUrl` / `notifyQrImageDownloaded` / `resetQrCache`——上屏口径统一成一句 `ZKQRCode::loadQRCode(qrInfo().content)`。② **删图片链条**：128×37 模块的 `album_qr_mp128.png`（3.46 px/模块 非整数 → 边缘发糊）与出位图的 `make_qr_asset.py` 删除（进回收站可恢复），改成 `assets/qr_url.txt`（一行扫码 URL，注明换成自己的链接、AppID 不写死）+ 离线解链接工具 `scripts/decode_qr_url.py`（`--src/--write/--expect`，实测解出我方链接且 `--write` 逐字节一致）。③ **依赖收口**：Manifest 去掉 `curl-cxx`（图片下载不再需要），接线样板改 `setQrUrl(prefs) → qrInfo().content → loadQRCode`（UI 线程 + 定时器消费）。④ 组件 README/platforms/example 与 `components/README.md`、`knowledge/devflow/reusable-components.md` 总览行同步（三态 → 一条路 + 一个兜底）。⑤ PC 侧 `g++ -fsyntax-only -Wall -Wextra` 0 warning（顺手清掉一个未使用变量告警）。v0.27.142-open',
    '2026-09-30: **三个组件包入库：wall_sync（多屏拼接同步）+ ha_bridge（HA/MQTT 桥与继电器语义）+ album_upload（相册传图，配套小程序码）** v0.27.141-open（钟工：「这个打入进去，并把相册传图这个组件搭进去，配套我们的小程序码」）—— 三个都是**源码型四件套**（README + platforms.md + Manifest.xml + include/zk/*.h（唯一对外头）+ src/ + example/），代码从来源工程现网抽，**去掉工程私有依赖**（ConfigStore / UI / logic → 配置结构体 + 回调/接口注入），头文件零底层类型泄漏；默认值一律安全（broker / 凭据 / 前缀 **全空**，不写死任何地址或 AppID）。① **`components/wall_sync/`（`zk::wall`）**：Sync = UDP 自组网 + 主机 epoch + 从机双向测时 RTT/2 钟差 + 绝对墙钟**整边界栅格** + playlist 多 clip 时间轴 + 失联/时钟守卫；Player = 按栅格挑本机那一格 + 边界踩点起播 + 交**注入的 Engine** 送流（`simple-player` 授权码不入库，Manifest 只留占位）；配套知识 `knowledge/devflow/video-wall-sync.md`。② **`components/ha_bridge/`（`zk::ha::Bridge` + `RelayBank`）**：配置全空默认、HA Discovery 自动发、上行 availability/state/status（retained）、下行只认 `<prefix>/switch/relay_<n>/command` 的 ON/OFF、retained 撤销原语、**重连只留一个真源**（库自带 automatic reconnect + 应用看门狗各自 new client 的互踢风暴根治）+ 代次作废旧回调；RelayBank 把「覆盖式 setListener 抹掉上报」从接口上消灭。③ **`components/album_upload/`（`zk::album`）**：相册传图**业务接线层**，协议与落盘**引用**既有 `components/mp_transfer/`（不复制一行）；**二维码三态** = 远端小程序码图（原生小程序码只能远端下载） / `ZKQrcode` 控件现场生成 / 本机上传地址兜底；**附我们的小程序码素材 + 生成脚本**（重跑逐字节一致）+ 三态口径文档。④ `components/README.md` 与 `knowledge/devflow/reusable-components.md` 总览表同步（11 个组件）。⑤ **如实标注**：三个组件的**形态未上机**（x86 语法自检 0 warning + 同源逻辑在 Z20 真机跑通的旁证），platforms.md 各自写明「未取证」清单。v0.27.141-open',
    '2026-09-30: **UI 确认闸门 + 客户确认稿 + 出图内联审计 + 三条知识入库（SmartPanel 检讨落地）** v0.27.140-open（钟工：「按照你的建议改。旋转倒装可以入知识库，不需要入 component」）——① **确认闸门（P0，返修点）**：`flythings_ui_visual(action="edit_apply")` 与 `flythings_fui_pack` 返回体新增 `confirmNeeded/confirmDraft/confirmHint` —— 项目 `ui/` 下没有比本次改动**更新**的确认稿（`.confirm.html`/`.preview.html`/`_edit/*.edit.html`）时提示「先出确认稿给需求方确认再 pack/推真机」（**只提醒不阻塞**；闸门自身异常也如实回报）。起因 = SmartPanel 项目 UI 布局多次来回对齐、全程没提醒用可分享 HTML 版跟客户确认（该工程 81 个 `_gen` 脚本 / 只 3 份 preview / 编辑器 0 次）。② **客户确认稿（P0）**：`flythings_ui_preview(target, for_customer=True)` → 单文件 `<name>.confirm.html`（图 base64 内联、手机可打开可转发），带「标注」开关（控件名+尺寸+坐标叠加层）、窄屏自动等比缩放、抬头带分辨率/控件数/生成时间；`ui_tools/json2html.py` 的 `json2html(target, output_dir, for_customer)` 与命令行 `--customer` 同步。③ **出图内联审计（P0）**：`flythings_generate_ui_assets` 返回体新增 `assetAudit`（自动跑 `check_all` 的抗锯齿 + 弧线过渡 + 倒角 + 透明底四项审计，DEFECT 计数点名；工具缺失/跑挂如实回报，不静默）—— 倒角线变粗那类问题不该等客户先看出来。④ **流程条款（P0）**：`knowledge/devflow/ui-layout-verify.md` 新增 **§0 确认闸门**（改完布局 → 出确认稿 → 确认 → 才 pack/推真机，含成本账）；`prototype-flow.md` 补「**已有工程的布局迭代同样走确认稿**」（原先只管新项目的线框/美化）。⑤ **知识入库**：新增 `knowledge/devflow/video-wall-sync.md`（多屏拼接跨设备同步：epoch/相位/整边界起播/校时/验收判据，实测数字逐条注明出处）、`knowledge/hardware/z20-display-rotate-flip180.md`（倒装 180°：UI+触摸 `setScreenRotate/setTouchRotate` + 视频层 `MI_DISP_SetVideoLayerRotateMode` + 用 `mi_disp` 的 `rotatemode` 自证；**只入知识库、不入组件**，钟工口径）、`knowledge/devflow/easyui-version-capability.md`（easyui 版本→能力三步判定 + Z20 实测矩阵；`scrollwindow` 不是版本问题、面板机型常见运行库 2.4.0）。⑥ **口径更正**：`z20-86panel-upgrade.md` §11.1 明确 **`umount /mnt/extsd` 失败（`Invalid argument` 或 `Device or resource busy`）都不是硬门槛**（写入面是 mtd3，两次实测照样升级成功）；`packages/mqtt-cxx` 补「**重连只能有一个真源**」（库自带 automatic reconnect + 应用看门狗各自 `new client` → 同 client_id 互踢风暴，实测 1 分钟 143 connected/123 disconnected）。⑦ docstring 预算内收（11972→11963/12000：长尾下沉 knowledge/）。v0.27.140-open',
    '2026-09-30: **bin_tools 去 mt_test（9.7MB）+ 引用口径统一（438 处）** v0.27.139-open（钟工：「3-4 也处理」）——① **mt_test 下线**：`bin_tools/{z20,z21,t113,v85x}/mt_test` 四个二进制（9.7MB）移入工作区归档 `archive/mcp_mt_test_20260930/`（`touch` 自动扫节点 + 判协议，已覆盖单点/MT-A/MT-B）；`BIN_TOOL_BRIEF` / 入口文档 / 用例同步（binTools 只剩 touch / busybox / ui_test / zkshot）；`bin_tools/README.md`、`bin_tools/z235x/README.md`、`hardware_catalog.json`（型号表源头）+ 6 篇知识文档同步；**MT-A / MT-B / 单点协议铁律（事件序列、`SYN_MT_REPORT`、`TRACKING_ID=-1`、恒 0 坐标判据）一字未删**。② **引用口径统一**：定规「knowledge 内互引一律 `knowledge/<分类>/<文件名>.md`；官方镜像写 `wiki/flythings/…`；仓库内其它文件写仓库相对路径；工作区文件写 `workspace/…`；禁裸文件名」，脚本批量落地 **438 处**（含 20 个原先解析不到的定向修复：gap-list / control-map / THIRD-PARTY / DESIGN / 案例侧报告等），复核「解析不到的引用 = 0」。门禁 `check_consistency --with-tests` 全绿。v0.27.139-open',
    '2026-09-30: **op→知识「去哪找」+ 版本史归档（钟工：「12 做了」）** v0.27.138-open——① **新增 `op_seealso.json`（43 op 全覆盖）**：35 个 op 有 seeAlso（仓库内知识文档，随包分发）+ 8 个显式登记 none 并写理由（如 `flythings_create_bin_project` 按 MCU 口径单独维护、i18n 家族在官方文档/wiki 镜像）；`kb_tools.normalize_result` 把 `seeAlso` 统一注入返回体（**不占 docstring 预算**——预算 12000 已顶格），AI 拿到工具结果就知道去哪看细节；`scripts/gen_seealso.py --check` 进发布闸门（覆盖 + 路径存在），新增契约用例 `tests/test_seealso.py`。② **MCP_FEATURES 老条目搬家**：`kb_tools.py` 只留近期 28 条（>= v0.27.121-open），更早 116 条归档到仓库根 `VERSION_HISTORY.md`（168KB）→ `kb_tools.py` **313KB → 144KB**；`flythings_get_version` 新增 `historyFile` / `historyMax` 字段（compact 与全量都回）；口径文档（knowledge/README、PUBLISH、demos/README、smoke 注释）同步；release 不带 VERSION_HISTORY.md。门禁 `check_consistency --with-tests` 全绿。v0.27.138-open',
    '2026-09-30: **知识库章节断号修复：编号连续化 + 全仓 §引用联动** v0.27.137-open（钟工：「修复3」）——① 7 篇顶层编号断号/乱序归为连续：`v85x/h264-player-usage`（12/13→11/12）、`hardware/z20-86panel-upgrade`（10/11/12→8/9/10）、`v85x/display-layer-debug`（8→7）、`uicontrols/touch-events`（7→6）、`uicontrols/layout-audit`（3/4/5→2/3/4）、`devflow/cli-fun-toolchain`（7/8→6/7）；② `devflow/package-properties-easyui-cfg.md` 顶层小节补编号 1..9（原先只有孤立的「## 8. 取图角度」，现为 §9，样式与其它篇一致）；③ 联动全仓章节引用：文档内自引用 + `xxx.md` §N 跨文件引用（含 `§11/§12` 链式）共 **26 处 / 13 个文件**（含 `adb_tools.py` / `kb_tools.py` 活指针与 6 篇知识文档）；复核「仍指向旧号的引用 = 0」；`kb_tools` 的 MCP_FEATURES 历史长串不动。门禁 `check_consistency --with-tests` 全绿。v0.27.137-open',
    '2026-09-30: **知识库治理 2 / 3 / 1（结构收口 → 元数据清理 → 正文压缩）** v0.27.136-open（钟工：「按着这个 231 收」）——① **结构收口**：USB OTG 三篇收口成 `hardware/usb-otg-switch.md` 跨平台正文（V85X/Z21 节点路径表 + 差异；另两篇改指针，`usb-gadget-storage.md` 的 configfs 序列与 `lun.0/file` 块设备细节保留在本地）；UVC 必查清单两篇去重（正文 `v85x/uvc-usb-camera.md`）；`base-utility 缺失 / 改 Manifest 必重跑 fun install` 四处重复收口到 `devflow/cli-fun-toolchain.md`；`rotateScreen / 取图角度 / 坐标旋转` 口径由 **7 篇**收口到 `devflow/package-properties-easyui-cfg.md`（其余 6 篇 ≤2 行指针）。② **tags 清理**：`kb_frontmatter --retags` 重抽 70 篇 tags，清掉 **117 个非检索词碎片**（「找不到 adb」「fun 流程不适用」「注册表均双向兼容」这类句子/版本号 tag）。③ **正文压缩 Top-15**：9 篇正文压缩（touch-inject-autotest 365→149、ui-asset-rules 342→188、upgrade-pack-image 299→206、prototype-flow 224→157、html-subset-quickref 241→206、listview-wheel-picker 288→222、h264-player-usage 333→300、touch-events 152→124、high-frequency-callback-perf 158→94），**机读判据/阈值/命令/序号铁律逐条保住**（如 ui-asset-rules 13/13 条铁律仍在）。④ 账：knowledge 13,028 行 → **11,763 行**；`rag_index.json` 3.8 MB / 1876 chunks；门禁 `check_consistency --with-tests` 全绿（检索 18 组 127 问法 / 417 用例 / smoke 29 项）。v0.27.136-open',
    '2026-09-30: **open 版全身检查（啰嗦清理 + RAG 索引瘦身）** v0.27.135-open（钟工：「对 mcp open 版本做一个全身检查，去掉不需要的啰嗦的废话…RAG 相关的内容优化，让 MCP 运行效率更高」）——① **RAG 索引瘦身**：`rag_index.json` 向量由「每 chunk 内联明文浮点数组」改为 **float16 拼接 + base64 单文件**（22.2 MB→**3.9 MB**；加载解析 0.4s→**0.1s**；向量检索由纯 Python cos 全扫 42ms→**numpy 点积 3ms**；行归一化后余弦=点积），旧格式仍可读、`rebuild_index_local.py --repack` 可原地重编码；等价性实测 12 条真实问法 **top-5 集合零差异**（f16 vs f32 最大绝对误差 1.3e-4），`check_retrieval` 18 组 127 问法仍全绿。② **知识库瘦身（批次 A：已修复/已被实测取代/自我否认）**：28 篇共删 **545 行**（touch-inject 附录源码、z20 失联记录与待填表、touch-events 重复的 `setInvalid` 话题、各文 changelog 段等）；**「真坑」一律保留**（时序/路径/平台差异/必填参数）；7 处悬空交叉引用改指 `custom-view-refresh.md`。③ 修 `kb_tools.py` 两处非法转义（SyntaxWarning）；清 workspace `tools/ui_tools/` 双份 CRLF 漂移（门禁 2 项 FAIL 归零）。v0.27.135-open',
    '2026-09-30: **批次 C：selfcheck 第⑩区「库清单」+ 返回体 pathHint（不开新 op）** v0.27.134-open（钟工：「批次 C」）——① **C1 `flythings_selfcheck` 新增第⑩分区「库清单」**（不新开 op，正因 docstring 预算只剩 6 字符）：新探针 `ls -l /lib` + `ls -l /res/lib`（busybox），新后处理 `_post_libs` 归出 `libs/libCount/resLib/focus（nanovg·libpng·freetype·jpeg·mad·libz·libgomp·libstdc++）/borrowable`；`ok` = 至少读到 `/lib` 清单；`hint` = 「注册表没有 ≠ 平台没有（自带 nanovg/libpng/freetype/jpeg/mad/zlib 可 dlopen 免编译）；借库前先 `readelf -d` 看 NEEDED/SONAME、`--dyn-syms` 对头文件核签名；清单见 `knowledge/devflow/device-preinstalled-libs.md`；`libmi_*` 属框架内部不要用」；notes 自动报“可借库”命中项。② **C2 返回体提示（不占 docstring 预算）**：新 `_render_path_hint()`/`_ui_visual_hint()`；`flythings_html_to_json` 与 `flythings_ui_visual(action=editor/edit_apply)` 命中关键词（旋转/矢量/半透明/alpha/3D/模糊/仪表/图表/粒子）时，返回体多一行 `pathHint`——“先答三问（静态/逐帧？面积？硬件层？）+ 查 `uicontrols/extension-surface.md`；任意角度旋转位图平台没有（先例 components/vinyl）”。③ docstring 总量 11994→**11999**/12000（九分区→十分区 + ⑩库清单，仍在红线内）；selfcheck 文档同步“十分区”。v0.27.134-open',
    '2026-09-30: **批次 B：docstring 腾预算 + 补“去哪找”描述（净零预算）** v0.27.133-open（钟工：「批次 B 处理」）——硬约束：docstring 总量 ≤12000（现 **11994**，即只剩 6 字符）⇒ **不新增 op，先腾后加**。① **B1 腾预算**：`flythings_ui_visual` 663→**470**、`flythings_device_screenshot` 550→**≈450**，把长尾细节**下沉到知识文档**：`knowledge/devflow/ui-layout-verify.md` 新增 **§5-1 像素基线库**（`action=baseline`：`<项目>/ui_baseline/`、mode=save/compare/update/list、**容差档案随基线存**、比不到基线报 `no-baseline` 不静默放过）与 **§5-2 edit_apply 写盘开关**（`pack` 默认 False / `dry_run` 只预览 / 写回留 `.bak`）；device_screenshot 的 advanced/layer/vdec_chn 细节本就在 `device-screenshot.md`。docstring 现在只留**要点 + 指向知识文档**。② **B2 加描述**（每条都直接指向知识文档）：`flythings_get_package_api` **39→194**——「**注册表没有 ≠ 平台没有**：设备 `/lib` 自带 nanovg/libpng12/freetype/jpeg/mad/zlib，可 dlopen 免编译；清单见 `knowledge/devflow/device-preinstalled-libs.md`（先 `adb shell ls /lib`）」；`flythings_build_ui_flow` 416→524——「链本地/第三方库放 `src/dependencies/lib/`（fun 自动链接）；**libc 必须匹配**：Z20/Z21=glibc、V85X/T113=musl、F133=RISC-V64 musl」；`flythings_html_to_json` 443→517——「做差异化效果前先答三问（静态/逐帧？面积？有无硬件层？）并查 `uicontrols/extension-surface.md`」。③ **净零验证**：总量仍为 **11994/12000**（腾出与加入基本持平），单 op 上限 900 仍有大量余量；门禁 `check_consistency` 全绿。v0.27.133-open',
    '2026-09-30: **`libmi_*` 降为“框架内部库，应用不需关注”** v0.27.132-open（钟工：「mi_gfx 不需要用户关注」）——① `knowledge/devflow/device-preinstalled-libs.md` §2.2 从“芯片侧能力入口（待逐符号核 API）”改写为 **框架/系统内部模块**：**明确⛔ 应用层不需关注、不要去 dlopen/链接**（接口不对外、随固件变），要图层/合成能力时走**框架高层 API**（videoview/cameraview/disp 纪律、`setBackgroundBmp`+`setInvalid`、`button+picTab` α 路径）；② 同步摘掉“悬而未决”的 `libmi_gfx API 未核”★待办项（不再追踪）与 tags 里的 mi_gfx / 2D 加速；③ `open-source-stack-integration.md` 与 `custom-render-paths.md` 的“设备自带可借用”清单里**移除 `libmi_*`**（只留 nanovg/libpng12/freetype/libjpeg/libmad/zlib），并注明 libmi 系列属框架内部。v0.27.132-open',
    '2026-09-30: **设备自带库入库 + 扩展点总表入库（先审核再处理）** v0.27.131-open（钟工：「我给你发的稿子你要审核后在处理。哪些是真实存在」）——① **先审核**：钟工四份稿逐条取证。**真机复核通过（Z21 / Zkswe_SSD21X_SPINOR）**：`/lib` 约 80 项，`libnanovg.so`=50,984 B、`libpng12.so.0.56.0`、`libfreetype.so.6.11.4`=137,120 B、`libjpeg.so.9.1.0`=177,488 B、`libmad.so.0.2.1`=83,224 B、`libmi_gfx/libmi_disp` 等在位，`/res/lib`=libzkgui.so。**纠正一处与事实不符**：稿子写“nanovg 四个平台注册表里都没有包”——本机实测 **f133 注册表有 `nanovg/1.0.0`**（z20/z21/v85x/f136 无，但设备 `/lib` 都有）。**降级一处**：`libmi_gfx` API 仍未核（只到库名+体积）。② **A1 入库** `knowledge/devflow/device-preinstalled-libs.md`：设备自带可 dlopen 库清单 + 两条采集命令（busybox ls / readelf）+ 三条纪律（注册表没有≠设备没有 / 头文件不在设备上 / libc 必须匹配）+ 明说 Z21 只做静态复核。③ **A2 入库** `knowledge/uicontrols/extension-surface.md`：六个扩展点总表（E1 组合/E2 自绘/E3 canvas/E4 disp 图层/E5 系统窗口/E6 进程外，含“明确不能做什么”、生命周期、性能档、最小示例、支持平台）+ §缺失表；E3 按代码修正字库档位口径（clampN 夹上限 + 跨档 1:1 回退 + 无放大插值）。④ **A3/A4 修订**：`open-source-stack-integration.md` §1/§3 增“设备已自带免编译”一条（nanovg/libpng12/freetype/libjpeg/libmad/zlib/`libmi_*`）；`custom-render-paths.md` ②b 选件表 nanovg 从“源码”改为“**设备已带 .so**”。⑤ **A5 已落**：`render-extension-boundary.md` §3 改为两段口径并引沛哥 2026-09-30 口径（内存画布→屏幕 = 硬件合成：拷贝/blit、透明 α 混合、90° 旋转），同时标明**芯片侧通道名未取证**。⑥ A6：`check_retrieval.py` 新增两组（设备自带库 6 问法 top-1 5/6；扩展点总表 10 问法 top-1 6/10、显式 `max_miss: 2` 并注明两条待改写的泛问法）。v0.27.131-open',
    '2026-09-30: **审核钟工修订稿（逐条取证）：一处与代码不符已修正、一处降级为待核** v0.27.130-open（钟工：「我给你发的稿子你要审核后再处理。哪些是真实存在」——我先前的毛病是照单全收，本版起改为**先取证再入库**）——审核方式：对每条断言找**代码/文件锚点**（不靠记忆、不靠措辞）。**结论（§写进 `custom-render-paths.md` 脚注 + `render-extension-boundary.md` §3/§5）**：① **成立**——`misc::bitmap_rotate` 第三参是 `ui::ERot` 枚举（`ext_widgets/2.12.0/include/misc/bitmap_utility.h:29`）⇒ “只支持 90° 整数倍”真实；`components/vinyl` 真机跑通 ⇒ “平台没有任意角度旋转位图”真实；`PgDisplay.cpp:59/77` 确实是 `setBackgroundBmp()`+`setInvalid()` 刷帧；`PgFontData.h` 确实是 `tools/genfont.py` 预烘多档（`PG_FONT_MAX_N=5`/`BIG=3`）；`448` 确在工程 json 里成片出现（27 处，480 宽屏内容区宽）。② **与代码不符（已修正）**：稿子里“超档位会走位图放大 = 拉伸”——代码是 **`clampN()` 夹到上限 + 缺字跨档 1:1 回退 + 全程不做放大/插值**（`PgCanvas.cpp:478-497` 注释明写“没有任何放大/插值”）。⇒ 真约束 = **档位预烘且档数固定**，不是画布限制、也不会拉伸。③ **降级为待核**：稿子列的“bitblt / 透明 α 混合 / 90° 旋转三种硬件能力”只核到 **G2D 存在 + 缩放/格式转换**（`g2d_scale.h`/`EPIXELFORMAT_g2d_format_convert.h`），逐项能力**未取证**（已标 `needs_evidence`，不许当定论引用）。v0.27.130-open',
    '2026-09-30: **真根因入库：「软渲染」要说清哪一段 + 两条旧限制的出处（字库预烘档位 / 内容区宽）** v0.27.129-open（钟工回传修订稿：`scale` 限制源自我方**自研字库只预烘有限档**；数值是**某工程 UI 的内容区宽**；**内存画布→屏幕是硬件合成**）——① `knowledge/devflow/custom-render-paths.md` §0-3 重写：**绘制进内存画布**那段代价取决于实现/面积（我方 `src/core/PgCanvas.*` 自研软件实现），但**内存画布→屏幕是硬件合成**（平台有 bitblt / 透明 α 混合 / 90° 旋转能力，实证 `ZKTextView::setBackgroundBmp()`+`setInvalid()`；`misc::bitmap_rotate` 只支持 90° 整数倍）⇒ **不要把“我们的实现是软件”说成“平台只能软渲染”**；平台真做不到的是**任意角度旋转位图**（先例 `components/vinyl`）。② 脚注三条旧说法给出**真根因**：`scale` 那条 = **自研字库预烘档位需编译期常量，超档位走位图放大=拉伸**（资源侧约束，**画布对 scale 无限制**）；宽度数值 = **某工程 UI 内容区宽（屏宽−2×16 的布局值），不是任何限制**；动画计时用绝对时间基准（原话“绝对时钟”）。③ `render-extension-boundary.md` §3/§5 同步：限制表新增「平台做不到的事（任意角度旋转位图）」与「资源侧约束 vs 平台限制」的分离。④ 检索组重测保持全绿（16 组 / 111 问法）。v0.27.129-open',
    '2026-09-30: **撤回误测数值：视频图层只保留定性口径（不超过屏幕区域）** v0.27.128-open（钟工：「448 限制你去掉，这个应该是误测。全志平台就只有一个视频图层尺寸不能超过屏幕区域的问题」——第三次校准，把数值彻底拿掉）——① `knowledge/devflow/render-extension-boundary.md` §5 改为**定性口径**：GUI 层缩放无限制（已定论）+ **视频图层尺寸不能超过屏幕区域**（全志平台唯一相关限制，**不挂具体数值**；早期具体数值系误测已撤回）+ 动画计时用绝对时间基准；§4 消歧同步（“canvas 宽度有上限”说法不成立）。② `custom-render-paths.md` 脚注同口径（保留「数值系误测已撤回」一句，防重入）。③ `v85x/videoview-transparent-window.md` §2 同步。④ `check_retrieval.py` 边界组把带过时数值的问法换成「视频图层超过屏幕区域会怎样」（12 条问法）。⑤ **知识纪律**：误测数值**不写成新口径的注释余留**，只留一句撤回标记（防止日后又被当作实测值抄回去）。v0.27.128-open',
    '2026-09-30: **修正：GUI 层缩放无限制，448 是视频图层上限（钟工口径）** v0.27.127-open（钟工：「scale 在 GUI 层没有限制。是视频图层不能超过屏幕的宽度导致的」——接上一条渲染边界入库后的当场校准）——① `knowledge/devflow/render-extension-boundary.md` §5 重写：**删掉「画布文字 scale 只认编译期常量」的错误归因**（GUI 层缩放/文字绘制**无限制**），**把 448 归位到「视频图层不能超过屏幕宽度（V851s 屏宽 480 → 实测上限 448）」**；§4 术语消歧同步修正（「canvas 宽 ≤448px」说法本身不成立）。② `custom-render-paths.md` 脚注与总表同口径改写。③ `v85x/videoview-transparent-window.md` §2 在「位置/尺寸即画面显示区域」直接标上视频层超屏宽不对的实测值+出处。④ `check_retrieval.py` 边界组扩到 12 条问法（新增「视频图层尺寸上限」「GUI 层缩放有上限吗」，top-1 实测 9/12 → 阈值 8）。v0.27.127-open',
    '2026-09-30: **渲染扩展能力边界入库（三层模型）+ 修正「scale / 绝对时钟」类不当表述** v0.27.126-open（钟工：「回到 MCP 里面的描述，canvas 自定义画布和自定义控件这个知识库里面了解多少。MCP 是否存在一些描述问题，比如 scaler、绝对时钟之类的表述不当」→「修」）——① **新增权威口径篇 `knowledge/devflow/render-extension-boundary.md`**（能力边界的唯一表述）：FlyThings UI 三层 = **① 基础控件**（21 内置 + 自研 8，纯 json/ftu 配置）→ **② canvas 画布扩展**（`ZKTextView`/`ZKButton` + `setBackgroundBmp` 挂内存位图当画布：**只调一次** + `setInvalid(!isInvalid())` 交替刷帧；或 `ZKPainter` 在控件画布上直绘）→ **③ 自定义控件**（继承 `ZKBase`，组合基础控件或重写 `onDraw`）；结论 = **可覆盖任意不需要 3D GPU 的效果；GPU 风格效果可用软件模拟（软渲染/软光栅）达成；只有「必须真 3D GPU 实时管线（着色器/实时光栅化）」超出边界**（F133/Z21 无 GPU → 伪 3D / 软模拟；真 3D 仅 V85X disp 分层验证过）；附 `canvas` **三义消歧**（布局画布 / 内存画布 / 控件画布）。② **修不当表述**：`custom-render-paths.md` 脚注原写「文字绘制的 scale 必须是常量（变量不生效）、画布宽 ≤448px、动画计时必须用**绝对时钟**」——无 API 主体、无平台、单点外推，且「绝对时钟」与 `digitalclock` 数字时钟**控件**撞名 → 改写为可核对口径（`scale` 只认编译期常量＝V851s 单点线索；**内存画布**宽 ≤448px＝单点、成因未查、非平台规格；动画计时用**绝对时间基准（单调时钟 / 时间戳差值）**，不用帧计数或相对累加），并标 `needs_evidence: true` 待补判据。③ 联动修正：`framework-control-mapping.md` §3「3D」一行补「**或软件模拟（软渲染/软光栅）**」半句 + 指向边界篇；`custom-widget.md` 把 canvas 画布口径挂进「控件显示位图」一节并链到边界篇。④ 门禁：`scripts/check_retrieval.py` 新增「渲染扩展能力边界（三层模型）」组（10 条真实问法，含错说法「动画计时必须用绝对时钟吗」，top-1 实测 8/10 → 阈值 7）；`rag_index.json`/`kb_index.json` 重建；`kb_frontmatter --check` / `check_kb` / `kb_verify` / `check_retrieval` 全绿。v0.27.126-open',
    '2026-09-29: **知识库改造 P1：自动生长 + 可检索 + 可验证（骨架与门禁，工具数 40→42）** v0.27.125-open（钟工：「改造到后续用户基于这个开发后可以做到自动生长 + 可检索可验证」→「开工 P1」）——① **结构化元数据**：83 篇 knowledge 全补 front-matter（id/title/category/platforms/tags/status/confidence/verified_at/stale_days/evidence/origin/source）；历史文档先认成 `verified + confidence=manual + needs_evidence=true`，**第一次把「有多少结论其实没有可执行判据」显式记下来**；`scripts/kb_frontmatter.py`（幂等迁移 + `--check` 门禁）。② **机读清单** `knowledge/kb_index.json`（`scripts/gen_kb_index.py` + `--check`）：带 `meta{source_hash,doc_count,built_at,mcp_version}`（**不再靠 mtime 判新鲜**）+ summary（verified / 带证据 / 待补证据 / 无问法登记 / 超期 / inbox）+ 逐篇字段（sha256/fingerprint/hasQueries/ageDays）。③ **采集（增长入口）**：新 op `flythings_knowledge_capture`（风险 write）写**用户本地层**（`~/.flythings/kb_local/`，`FLYTHINGS_KB_DIR` 可改）或项目层（`<项目>/docs/kb/`）——**绝不写 MCP 安装目录**（版本物，升级会覆盖）；指纹去重（归一化标题+命令+平台）命中同主题 → 回 `duplicateOf` 提示**合并而非新建**。④ **回流（脱敏补丁包）**：新 op `flythings_knowledge_export`（kb-contrib-<时间>.json；IP/本机路径/凭据/主机名强制占位化，未脱敏须 `internal=True`）；总账只收过「去重 + 复验 + 问法登记」三关并由人签字的条目（**AI 不能自评通过**）。⑤ **检索闭环**：未命中/低置信落**用户本地层**日志（`_logs/no_hit.jsonl`）+ 返回体带 `gapLogged/gapHint`；`scripts/kb_gaps.py` 聚合出 `kb_gaps.md`（**用户真的问不到的东西 = 下一批写作清单**）。⑥ **验证闭环骨架**：`scripts/kb_verify.py` 按 evidence 真跑判据（`offline` 进 CI / `real-device` 走 `--device` / `manual` 显式不算通过），失败写回 `status=stale`。⑦ 门禁加 4 项（front-matter 合规 / kb_index 新鲜 / verified 必须有证据或显式待补 / inbox 不计入索引）+ 契约用例 `tests/test_kb_growth.py`；知识 `knowledge/devflow/kb-growth.md` 入库。v0.27.125-open',
    '2026-09-29: **自动化测试第二轮：多设备并行跑批 + 机读报告 + 像素基线库（工具数 39→40）** v0.27.124-open（钟工「先按照你的方案优化一轮，然后再复检」——这三项是我自己反查 open 版 MCP 时列出的测试侧 P0）——① **新 op `flythings_test_run(plan, devices, project_root, out, platform, parallel, baseline, allow_regions)`（风险 device）**：一份用例 JSON 在**多台设备并行**跑（此前多设备在线时工具一律「不猜」，只能逐台手敲 adb），每步结果**机器可判**：注入命令 rc / `logcat -d -s zkgui` 日志断言（expectLog/expectNoLog）/ 与像素基线逐像素对比；产出 `<out>/report.json` + **`<out>/report.xml`（JUnit，能直接进 CI）**；每台设备各自落 `shots/*.png` + `logcat.txt` 取证；`parallel` 控制并发度；**比不到基线记 no-baseline 并进 warnings，不算通过**（不静默放过）② **新模块 `ui_baseline.py`（像素基线库）** + **`flythings_ui_visual(action="baseline")`**：把「上一次验收通过的那张图」版本化存到 `<项目>/ui_baseline/`（`baseline.json` 索引 + 基线图 + 容差档案随基线存 + `_diff/*.diff.png`）；mode=save/compare/update/list；比不到基线报 `no-baseline`、尺寸变了报 `size-mismatch`（不许拿旧分辨率基线硬比）；判据与 ui_diff 完全同源（±2 容差 + ±1px 抖动补偿 + 噪声块归并）——此前只有「两张临时图比一比」，回归验收没有基线概念 ③ **`adb_tools` 补 `push()` / `shell_rc()`**（原来只有 `sh()` 只回文本、判不出 rc，无法做「注入失败=失败」的硬判据）④ 知识：`knowledge/devflow/device-test-run.md`（用例 schema/首次建基线流程/多设备并发注意/报告字段）+ `knowledge/devflow/capability-boundaries.md`（**能力边界清单**：open 版覆盖什么、哪些知识只在内部版、未覆盖怎么处置）⑤ 六方同步 + 契约用例 `tests/test_baseline_testrun.py`；真机验证：多台在线**并行**跑同一用例（含基线与报告）v0.27.124-open',
    '2026-09-29: **新增整机自检快照 + 缺陷单生成器（工具数 37→39）** v0.27.123-open（审查报告 P2-⑧⑨ / 钟工「1-3 按顺序做」第 3 项）——① **`flythings_selfcheck(device, diff_against, out)`（风险 device）**：一条命令出**整机快照九个分区**（设备信息/应用状态/显示/存储/网络/蓝牙/输入/外设/时间），每分区给 `{ok, hint, data}` —— **「读不到」本身是结论**：ok=false 时 hint 写明「需要什么条件 / 去哪查」，绝不静默吞掉；采集容忍设备缺工具（优先随仓 `bin_tools/<平台>/busybox` → 设备 /tmp/busybox，否则纯 adb shell + getprop/cat）；`diff_against=<上次快照.json>` 出逐分区逐项差异，`out=<json>` 落盘可复用为基线；设备参数带端口（`<serial|IP>:5555`），**多台在线不猜**（回 NO_DEVICE + 在线清单）② **`flythings_bugreport(title, project_root, device, symptom, steps, expected, actual, evidence, severity, out)`（风险 write）**：把「AI 产出的缺陷清单 + 真机判据」落成可提交 markdown，**格式对齐 2026-09-27 html2json A1~A8 那批**（标题 / 元信息 / 现象 / 复现步骤 / 期望 vs 实际 / 真机判据 / 证据 / 影响面）；真机判据自动附 型号·固件·build.fingerprint·应用状态（init.svc.zkswe / sys.zkapp.state / zkgui pid / uptime）·最近 `logcat -d -s zkgui` 末 40 行，采不到就写明原因；**evidence 里文件不存在 → 直接 EVIDENCE_MISSING 报错（不静默跳过）**；默认落 `<项目或MCP仓库>/temp/bugreports/<yyyymmdd-HHMM>-<slug>.md`，返回 path + 前 20 行预览 ③ 六方同步：`OP_NAMES` / `scripts/gen_manifest.py` 的 RISK·CATEGORY·STAGE / `mcp_server` 与 `README` 工具数 37→39 / `tools_manifest.json` / 意图闸门 `catalog.json`；新增 `knowledge/devflow/selfcheck-and-bugreport.md`（含检索导引）+ 契约用例 `tests/test_selfcheck_bugreport.py` ④ docstring 预算：长尾细节搬 knowledge/（html_to_json / build_ui_flow / ui_visual / device_screenshot / edit_ftu / pack_upgrade 六个 op 瘦身），总体仍 ≤12000。v0.27.123-open',
    '2026-09-29: **审查报告（MCP 更新审查-2026-09-29）P0 修复：包卡接进工具返回 + 门禁健壮性 + CHANGELOG 口径定死** v0.27.122-open —— ① **P0① 包卡进返回**：`package_tools` 新增 `package_card()`（读仓库 `packages/<包>/package.yaml`，yaml 缺失自动降级），`flythings_get_package_api` 返回体加 `card`（summary/entry/api/usage_cpp/gotchas/verified_* + cardPath/readmePath）、`list_packages` 加 `hasCard`、`query_package` 加 `cardSummary`/`hasCard` —— 之前 11 张卡 AI **取不到**（只读 registry），现在工具里直接可见；② **P0③ 门禁健壮性**：`lint_silent_except` 的 SKIP_DIRS 补 `.venv/venv/.fsc/.fun/toolchain`（原先扫到 .venv 报 650 条假红）、`check_consistency`/`smoke` 里「意图闸门 catalog 不在仓库内」「ui_tools 双份副本不存在」两条环境依赖检查**降级为 skip + 提示**（不再误报红）；③ **CHANGELOG 口径定死**：文件头改为「已冻结归档 ≤ v0.27.30」，版本史唯一来源指向 `MCP_FEATURES` + README（不再两套并存）；④ `packages/README.md` 补**包卡完整度状态表**（platforms.md/example/evidence 谁缺、谁待补，显式标注不许静默）；⑤ 新增契约用例 `tests/test_package_cards.py`（卡可解析 + 已接进工具返回）。v0.27.122-open',
    '2026-09-29: **依赖包「用法文档」体系 + 网络类包 Z20 真机全流程验证** v0.27.121-open（钟工：用这个面板把网络相关的 API 做好验证，就用平台上面的组件包；说明不完整的在本地 mcp 目录下做好 yaml 说明；源码可在本地 git 搜 lib-<包名>）——① **新增 `packages/<包>/` 文档体系**：机器可读 `package.yaml`（头文件 / API 签名与出处 / 依赖 / 可直接粘的用法 / 坑 / `verified_*` 真机结果）+ 人读 `README.md`（+ `platforms.md` / `example/` / `evidence/`）；首轮覆盖 `zkhardware`(3 路继电器 by zeroOutput + 背光)、`zknet`、`curl-cxx`、`ntp`、`mqtt-cxx`、`paho-mqtt3as`、`cares`、`mbedtls`、`openssl`、`rapidjson`、`curl`（未上真机的一律 `verified: null`，不冒充实测）；② **验证工程**：`projects/pkg_zknet`（WiFi 九键 + 自检 AUTO）、`pkg_netstack`（HTTP/HTTPS/NTP/MQTT）、`pkg_netstack2`（MQTTS/LWT/Downloader/WebSocket/热点/以太网/4G）、`pkg_netdir`（c-ares/mbedTLS/OpenSSL 直调）——全部「脚本注入触摸 + `logcat -d -s zkgui` 取证 + fb 截图」自动跑；③ **Z20(108) 真机结论**：WiFi 开关/扫描/连接/断开 6/6、HTTP GET/POST/HTTPS、Downloader 双任务(进度回调,307200B+81B)、WebSocket 回显、MQTTS(TLS test.mosquitto.org:8883)、LWT 遗嘱（`kill -9` 异常断线后 **~2s broker 代发**）、异常断线自动重连（cause=automatic reconnect，≈10.5s）、c-ares 解析(5 域名 30~88ms)、mbedTLS/OpenSSL 直调 TLS+GET(200 OK)、Ethernet configure/setAutoMode、SoftAp setEnable 开关、4G=本板无模块；④ **新坑入档**：`cacert.pem` 只认 **资源目录(resPath)** 下（放别处报 `not correctly signed by the trusted CA`，那是没找到 CA 不是证书坏）、Z20 的 `paho-mqtt3as` **必须配 openssl**（否则链接报 BIO_read/RAND_bytes/SHA1_* undefined）、**别连续快速 `setprop ctl.restart zkswe`**（旧实例没退干净 → MI 全局 init 锁被占 → 黑屏 + 进程 D 状态 kill -9 无效，只能断电）、取证用 `logcat -d -s zkgui`（zknet 事件线程刷屏会把我方日志挤出缓冲）、MQTT 见证端连 `127.0.0.1:1883`（宿主访问自身 LAN IP 会被拦）；⑤ **Z21（SSD21X / 1024×600 / 192.168.x.x）复验**：HTTP GET/POST、NTP 校时、HTTPS、Downloader 双任务、WebSocket、SoftAp、Ethernet 全通 —— **新增两条 Z21 专属坑**：**Z21 上电 RTC = 1970** → 带证书校验的 HTTPS 会报 `certificate validity starts in the future`（**必须先校时再 HTTPS**，Z20 时钟本来就对所以没暴露）；**Z21 没有 `/mnt/sdnand`**（只有 `/mnt/extsd`、`/mnt/usb1`）→ 落盘走 `/data/`。**Z21 registry 无 mqtt-cxx/paho-mqtt3as，MQTT 两项在 Z21 上无法验**；⑥ **同批入 `demos/` 六个真机验证工程**（`net-stack-verify-z20` / `net-stack-advanced-z20` / `net-wifi-verify-z20` / `net-stack-verify-z21` / `net-direct-tls-z20` / `hw-relay-verify-z20`，源级交付、IP 脱敏）+ `knowledge/devflow/package-verify-playbook.md`（验证套路：worker 线程 + 自检 AUTO 键 + 触摸注入 + `logcat -d -s zkgui` 取证 + framebuffer 截图 + 部署纪律 + 主机侧测试设施） v0.27.121-open',
    '2026-09-17: **字体判定升级为 cmap 硬判据 + V85x 芯片别名补齐** v0.27.87-open（钟工拍板：用硬判据，比体积判据好；并问「V851/V851S/V851S3/V853S 这几个你适配了吗」）——**A 字体硬判据**：①`device_font_check.py` 新增 cmap 覆盖率判据（基准 = **GB2312 一级 3755 字**，用标准库 `gb2312` codec 现场推出；阈值 `CMAP_OK_MIN_PCT=90` / `CMAP_LOW_MIN_PCT=50`，拉取上限 `PROBE_MAX_BYTES=12MB`）；②`font_tools.hard_probe()`：挑设备最大 ttf/ttc **拉回 PC 临时目录（用完即删）** → fontTools 读 cmap → **≥90% → `ok`（不投）/ 50–90% → `low`（投 + warning 写明覆盖率）/ <50% → `missing`（投）**，字段 `source`(`cmap`|`size`)/`cmapCoverageGB2312L1`/`cmapCoveredChars`/`checkedFont`(路径+体积+mtime+md5)/`probe.cacheHit`；③兜底**不许静默**：体积超限 / fontTools 不可用 / 拉取或解析失败 → **退回体积判据**（`source="size"` + `warnings` 写明原因）；④结论按 `serial+目录/文件名+体积+ls 时间` 缓存到 `~/.fun/font-probe.json`（`FLYTHINGS_FONT_CACHE` 可覆盖）→ 不每次 build 都拉；⑤`fun launch` 成功后若刚投递过字体 → `fontCheck.deviceAfterDeploy` 回报设备侧字库现状与一致性（**要 `pack_upgrade` 固化才生效**，故只核名字/体积不重拉）；⑥`fontTools==4.65.0` 锁进 `requirements.lock`；⑦口径文档 `knowledge/devflow/custom-font-config.md` §0.2 + `components/fonts/README.md` §0/§3。**B V85x 别名**：⑧`platforms.PACKAGE_INPUT_ALIASES` 补 `v851 / v851s / v851s3 / v853s`（→ V85X）——修前 `resolve("V851S")=None`（当未知平台）且 `package_key("V851S")` 回 `v851s` 这种 **catalog 里不存在的键（查包必空）**；⑨`hardware_catalog.json` V85X 收齐 6 个主控（V553/V851/V851S/V851S3/V853/V853S）+ 新增 `chipEntries` 芯片级登记（有实测标 `partial` 并给依据来源；**无实测的 V851S3/V853S 如实标 `pending`+「待确认」，不臆造规格**）+ `chipsNote` 写死「V85x 家族统一归一到 V85X 平台，包键走 `v85x`/`v85xemmc`」；⑩`package_catalog.json` 的 `v85x`/`v85xemmc.chips` 补 `V851`；⑪`hardware_tools.normalize_platform` 补 `platforms.resolve` 兜底（修「芯片名查包认、hardware_info 却回 BAD_PLATFORM」的双口径；仅包生态平台仍走 `PLATFORM_NOT_IN_HARDWARE_LIB`）；⑫真机实测（V85X SPINOR 整机，网络 adb；多设备时 fun launch 硬失败 → 先 disconnect 另两台再跑）：`source=cmap` / `cmapCoverageGB2312L1=100.0`（3755/3755）/ `verdict=ok` / `checkedFont=/res/font/pocketgame.ttf`（1,093,608 B）/ 拉回耗时 1294 ms；同设备再跑 `probe.cacheHit=true` + `elapsedMs=6` + `pulledBytes=0`（缓存真生效）；设备字库只有 302 个一级汉字时（81,188 B 字体）→ `coverage=8.0%` / `verdict=missing` / 自动投递；完整 `flythings_build_ui_flow`：`ok/launched/pushed=true` + `staleOnDevice=false` + `deviceAfterDeploy.consistent=false`（明说需 `pack_upgrade` 固化）；另补一个诚实提醒：扫描结果为空时不把结论说得像板上真没字库（进 scanNote/warnings）。⑬用例 214→**239**（新增 `TestFontCmapHardProbe` 18 项 + `TestV85xFamilyAliases` 7 项，全部离线：仓库自带 ttf + fontTools 现场造字体当「假设备数据」），门禁全绿。',
    '2026-09-17: **ADB 随包 + launch 默认推设备 + 设备探测/安装提示** v0.27.84-open（钟工三项）——①`tools/adb/`（adb.exe 1.0.41/31.0.3-7562133 + 两个 WinApi DLL，≈6.1MB）+README；新增根 `adb_tools.py`：`resolve_adb()` = env ADB/FLYTHINGS_ADB → 随包 → PATH，**全仓 adb 硬编码 6 处→1 处**（project_tools、device_screenshot、i18n_tools×2、device_font_check 等）；②`build_ui_flow(with_launch)` 默认 **True**（build→探测→推送/运行，`with_launch=False` 只编译）；返回 `launched/pushed/device/model/platformMatch/deviceSync`（设备侧 ftu+so 字节/md5 vs 本地）+`staleOnDevice`（true ⇒ 设备上跑的还是旧版）；③探测不猜：0 台 → `needDeviceInput`+`installHint`（ADB 驱动 / USB 调试授权 / 网络 device=<IP>:5555）；多台 → 列 serial+model+匹配并要显式 device=；1 台且匹配 → 自动 `fun launch -s`；新增 `device_models.json`（Z21/Z20/V85X 实测；F133/F136 待确认）；④实测（三台真机 + 单台 Z21）：三台在线 → 多设备清单（不猜）；**单台自动选机 launch 成功**、设备侧 ftu 186B / libzkgui.so 277340B **字节+md5 与本地一致**；本地改过未推 → staleOnDevice=true；0 台 → installHint 到位；顺带修 3 个 adb 实测坑（`ls -l` 第 5 列才是字节 / 缺 md5sum 时用随仓 busybox 兜底取 md5 / **fun 多设备必 FATAL more than one device/emulator**，→ 修正「fun 静默取第一个」旧结论，见 cli-fun-toolchain.md §6）；用例 176→200，门禁全绿；细节 knowledge/devflow/adb-and-device-selection.md。',
    '2026-09-17: **Z235X 平台入库（IDE 模板 + platforms 登记 + bin_tools 占位）** v0.27.78-open（钟工给 IDE 工程 HelloWord_z235x，要求入库）——①**新增模板 `templates/HelloWord_Z235X`**（22 文件，与 HelloWord_Z21 同构：.cproject / .project / .settings×4 / Manifest.xml / .deps.lock / .gitignore + src/{Main.cpp, activity, logic, uart} + ui/main.ftu）；源工程里的 `Release/`（libzkgui.so / *.o / *.d / makefile 等构建产物）**不入库**；工程名规范化为 HelloWord_Z235X；依赖 easyui 2.9.0 / log 1.0.0 / zkhardware 1.1.0 / zknet 1.1.0。②**`platforms.py` 单一真相**：`PLATFORMS` 新增 `Z235X`（arch=arm，template=HelloWord_Z235X，binTool=z235x；SSD2355），并从 `PACKAGE_ONLY` **移除**（不再只是包生态平台）；包生态键 `z235x` 与 package_catalog 不变（17 个包）。③**设备端预编译工具缺口（如实标注、不伪造）**：`bin_tools/z235x/` 暂只有 README 说明占位——touch / busybox / ui_test / mt_test / zkshot **尚未编译**（需 Z235X 样机 + 该平台工具链；架构与现平台可能不同，禁止拿其他平台 ELF 顶替）→ `flythings_gen_ui_test` 在该平台会**明确报「未预编译触摸注入工具」**并列出可用平台，不静默。④顺带收口：bin_tools 发现入口（get_version 的 binTools / flythings://tools）不再把目录里的 README.md 当设备端工具。',
        '2026-09-16: 平台通用性三坑入库 v0.27.70-open（均实机核实）——①**双缓冲/pan 偏移 → 抓屏抓到上一帧**（平台通用，重点）：应用已重绘但抓到的是**上一帧**；判据 = `device_screenshot` 返回 `screenInfo.virtualHeight ≈ 2 × height` 且 `pan` 非 0（实测 Z21 = 1024x600/virtual 1200、F133 = 800x1280/virtual 2560）；对策 = 抓屏前后读 `fb0/pan`（或连抓两次比 md5，不一致重抓）、触摸 `touch long x y 250` 触发重绘后再抓、像素 diff 前先确认拿的是新帧；**这是抓图/验收侧问题，不要为此改应用逻辑**；②`html2json` 把 `#000000` 当「未设置」（`data-color`/`data-bg` 走 `to_dec(...) or 默认值`，0 是 falsy）→ **要纯黑请写 `#010101`**；③ZKPainter `drawArc` 实参口径存疑（既有文档写「外接矩形+起止角」，本次按 `(cx,cy,rx,ry,start,sweep)` 在 Z21(easyui 2.6.0) 真机渲染正确）→ 标「待官方/沛哥确认」，用前小图自证。落点：`knowledge/devflow/device-screenshot.md` §3.3-1、`devflow/html-subset-quickref.md` §4、`uicontrols/widget-code-api.md` §ZKPainter。',
    '2026-09-16: 多设备设备选择修正 + 知识入库 v0.27.68-open（沛哥报「fun launch 在同时连着 WiFi adb 时静默失败：adb 看到 2 个设备就报 more than one device/emulator、fun 把输出吞了 → 资源没推上去、设备仍跑旧 ftu；改了 ui 加控件、build 通过、launch 看着成功但界面不变，极易误判成框架不支持该控件」；验收后**现象方向成立、机制描述要改**）——①**实测机制（扫 fun.exe 字符串 + 伪造 adb host server 抓包）**：fun launch 走 fun 自带 Go adb 客户端（`pkg/adb` → 直连 adb host server `127.0.0.1:5037`：`host:version`/`host:devices`/`host:transport <serial>`/`shell:`/`sync:`），**不 shell 出 adb 二进制**（全二进制只有 `adb -s %s shell chmod 777 %s` 与 `adb -s %s shell %s` 两处，**都带 `-s`**）→ fun **根本不会**报 adb 的 `more than one device/emulator`，也就没有「吞 adb 输出」；②**真实行为：多设备时 fun 不报错/不警告/不询问，按 `adb devices` 列表顺序取第一个**（实测两种顺序各跑一次：WiFi 在前推 WiFi、把另一台放前面就推那台；pty 交互模式一样），唯一拦点是平台校验（`shell:getprop \'ro.product.model\'` 对比项目平台，不匹配才 `FATAL platform not match`；push 真出错也 `FATAL` + exit 1）；③**MCP 侧真 bug 修复**：`project_tools._run_fun` 原先**把 device 参数丢掉**（注释「fun launch 不支持 -s」），而 `build_ui_flow` docstring 又叫 AI「传 device=IP 重试（走 fun launch -s）」→ 文档与实现不符，多设备时会静默推错设备；现改：`cmd==\'launch\'` 且 device 非空时**追加 `-s <serial|IP>`**（实测可用），device 为空且检测到 **>1 台在线设备**时在返回体里给 `warnings`（不静默）；`kb_tools.flythings_build_ui_flow` docstring 同步改正「不支持 -s」；④**判据实测**：单设备 `fun launch` 后设备 `/tmp/ui/main.ftu` 与本地 `ui/main.ftu` **字节+md5 完全一致**（1419 B / `FDC802FF232328DD5395EB433F8BA223`；launch 前是旧 app 的 1755 B），设备侧无 md5sum 用已推 /tmp/busybox、`ls` 不认 `head`；⑤**知识入库**：`knowledge/devflow/cli-fun-toolchain.md` 新增 §7「多设备（USB + WiFi adb）时的设备选择陷阱」（机制/危害/正确做法/判据命令/WiFi adb 用法）+ §3 命令表改正 `-s` 行 + 检索词补充；⑥**复现手法留档**：真机只有单台可达时，可用**伪造 adb host server（127.0.0.1:5037，报 2 台设备）**抓 fun 发的每条请求（注意 Windows `SO_REUSEADDR` 允许多进程同绑 5037 → 排查前先 `netstat -ano | findstr 5037` 杀干净）。',
    '2026-09-14: V85X 硬件 H264 播放器用法入库 v0.27.65-open（钟工：把 V85X 扩展屏 AP+P2P 工程 result 下的 H264 解码库实践，结合 awh264player@1.0.0 包与 V85X 工程检讨后入库，避免重复踩坑）——新增 `knowledge/v85x/h264-player-usage.md`，入库前做了现场核对并纠正一处 P0 口径：①**两套 API 不可混用（本次最贵的坑）**——官方包 `awh264player`（v85x 1.0.0，包内仅 CHANGELOG + `include/h264_player.h` + `lib/libawh264player.so`）提供的是 **`h264_player_*`**（13 个，含三参 `h264_player_init` 与四参 `h264_player_init_ex`）+ `h264_multi_player_*`（10 个）**没有 `zk_h264_player_*`**；`zk_*` 是厂商参考工程给的**静态库门面**（`libzkmedia.a` 内同时含 `zk_*`+`h264_player_*` 符号与 `dlopen("libawh264player.so")` 字符串，实测符号表）——原稿整篇按 `zk_*` 写却引用包，直接照抄会在 V85X 上 `undefined reference`（V85X 也**没有 `zkmedia` 包**，F133/F136 才有），本篇把两条路线分开写并给选路判据；②**`fun.json` 优先于 `Manifest.xml`**：只把 `<package id="awh264player">` 写进 Manifest.xml 时 `fun install` 报成功但 `.fun-lock.json` 里 `"v85x": {}`（**静默不装**），依赖必须写 `fun.json` 的 `dependencies`；③**`lib-no-link` 部署矩阵**：不参与编译、`fun launch` 不推（调试期手推）、`fun pack` 进镜像 `lib/`→设备 `/res/lib/`（ld 路径已含，固化后免推），⚠️ **同名库长期留在 `/data` 会遮蔽 `/res/lib` 的固化版**（ld 路径最前，升级了库却跑旧的且 0 日志异常）；④保留真机实测干货：`ZKMEDIA_H264_VBVSIZE` 未设 → **起播静默退出**（头号坑，必须在库加载前 setenv，改完重启应用）、`MemAvailable<3MB` 必挂且 OOM 后不自己回来（要重启板子）、720p 缩放档位内存三档（不缩放 2.6MB / 1/2 4.1MB / 1/4 6.5MB）、`get_picture_count` **不是队列长度**（背压用媒体时间）、`set_rot` 后必须重发 `set_crop`、与 MPP 互斥；⑤显示层/透明窗口/图层释放**不复制正文**，只交叉引用 `v85x/display-layer-debug.md`（避免双份漂移）；⑥**如实标注未验证项**（路线 A 在 V85X 上未做真机播放验收、多实例 API 未实测、固化后 /res/lib 自加载待验收）；⑦附可编译示例工程 `demos/h264player-v85x/`（bin 工具：env + init_ex + 回调 + 喂 AU，`fun build -p v85x` 通过）。',
    '2026-09-14: BLE 组件改为「头文件 + 静态库」发布（不释放源码）v0.27.59-open（钟工：「验证好了后把你的程序做成静态库+头文件发布给到 open 版本 MCP 里面。不释放源码了」）——①`components/ble` 交付物收成三件：`include/zk/zk_ble.h`（唯一对外头）+ `lib/{f133,v85x,z20,z21}/libzkble.a` + `lib/BUILD_INFO.md`（构建凭据：每平台工具链/libc/依赖包版本/公开符号数/大小/sha256）；**`src/` 与源码侧脚本已移出仓库**（内部私有 `private/components-ble/`）；②新增 **`scripts/verify_lib_symbols.py`**：纯 Python 解析 `ar`+ELF 符号表核对每个平台库是否导出全部 30 个公开 API，**不用 `nm`**（Windows 版 binutils 的 `nm` 缺 `liblto_plugin-0.dll` 一调就报错）；实测 4 平台全 30/30；③两个后端保持一套 API：btstack（f133 408KB / v85x 118KB）+ gatt（z20/z21 各 179KB，主从双角色）；④口径写进 `components/ble/platforms.md` §0.6 + README §4：**工具链/libc 必须与库一致**（f133/v85x=musl、z20/z21=glibc）、**不许拿别的平台的头凑库**（`gatt/hci.h`、`gatt-db.h` 含 ABI 相关结构体）——因此 T113/T113EMMC 库本轮**不发布**（本机无该平台 `gatt 1.0.0` 包），如实标注待补；⑤z20 与 z21 的库 sha256 相同（两平台 gatt 17 个头 md5 逐一相同，已核）；v85x 库用本地 `btstack 1.7.2` 头构建（包站为 1.8.0，装包后重跑脚本即可）；⑥`components/README.md` 新增「二进制型」模块形态规范（必须给构建凭据 + 机器可跑的符号自检）。',
    '2026-09-14: BLE 统一门面 v0.2（一个 API 面 + 两个后端，组件级真机跑通）v0.27.58-open（钟工：「蓝牙部分都统一按照昨天定义的新 API，参考微信的方式」）——①`components/ble` 收口：对外只有 `zk/zk_ble.h`（`zk::ble`），**中心侧照微信 wxapi**（openAdapter/startDiscovery/onDeviceFound/connect/getServices/readValue/writeValue/subscribe/onValueChange）、**外设侧照 Android GattServer**（`peripheral::start(PeripheralConfig)` + `onWriteRequest` + `notify` + `setDeviceName`），平台差异一律走 `getCapabilities()`/`backendName()` 能力门控 + `ERR_UNSUPPORTED` 人话 hint（不假装能用）；②**两个后端**：btstack（F133 1.7.2 / V85X 1.8.0，串口 HCI+H5）与 **gatt（Z20/Z21/T113/T113EMMC，AIC USB 模组 + BlueZ 用户态 GATT 1.0.0，主从双角色）**；`src/zkble_backend.h` 自动判定（显式 `-DZKBLE_BACKEND_GATT` / `-DZKBLE_BACKEND_BTSTACK` 优先），两个 `.cpp` 用 `#if` 互斥、同平台只编一个；公共层 `src/zkble_common.h`（日志/AD 解析/扫描过滤/DeviceCache/回调/Waiter）+ 公共 TU `zkble_public.cpp`；③新增能力：`Config.connect_retry` / `reset_before_retry`（Z20/Z21 控制器残留链路 → 自动重试 + 重试前复位，实测第 1 次 ETIMEDOUT、复位后第 2 次成功）；④**组件级真机验证**（不用 demo 代码，只用公开 API 的 bin 工程 `projects/zkble_comp_srv`(Z20 外设) / `zkble_comp_cli`(Z21 中心)）：扫描 → 连接 → `svc fff0` / `chr fff1(0x09)` / `chr fff2(0x06)` → 订阅 ok → `readValue len=5` → `writeValue code=0` → `notify_count=4`；外设 `peripheral::start code=0` + 收 `WRITE char=fff2 data=50494e47`(PING) + `NOTIFY`×4 + 断开后广播自动恢复；⑤真机拓出并修掉的三个 bug（知识性，已写进 platforms.md §0.5）：BlueZ `bt_uuid_to_string()` **成功时返回 0**（原判 `<=0` 当失败 → uuid 全空）、`gatt_db_service_add_characteristic()` 返回的是**特征值属性**而非声明属性 0x2803（取 value_handle 要用 `gatt_db_attribute_get_handle()`）、**控制器已在广播 enable 状态时改参数返 status=12 Command Disallowed**（处置：设参数前恒发一次 `LE Set Advertise Enable(0)`，被拒则复位控制器 + 重试一次，不静默）；⑥编译自检双脚本（`compile_check.sh`=F133/btstack、`compile_check_gatt.sh`=Z20/Z21/gatt）均 rc=0，并叠了一层链接校验（只依赖 gatt + pthread + libc）。未覆盖项（128 位非 base uuid 折回、改名路径、二次重连闭环）在组件 platforms.md §0.5 如实标注。',
    '2026-09-14: 纠正「Z20/Z21 没有中心侧包」——`gatt` 包 **主从双角色** v0.27.57-open（钟工指路 `git.com/AppGroup/Sample`，本仓核对）——①`components/ble/platforms.md` §0.2 表补 `gatt 1.0.0`（Z20/Z21/T113/T113EMMC/V85X 均有；本机 `fun install` 实测拉到 z21 那份，19 头含 `gatt-client.h`+`gatt-server.h`）；②新增 §0.3「主从双角色」：`BleClientDemo`（中心：scan_start/connect + 事件回调，含私有协议测距机）/ `BleServerDemo`（外设：server_start + `_char*_read/write_cb` 自定义 GATT 表），共同前置=Manifest 声明 `gatt` + 把 `hciconfig`/`hcitool` 放进 `src/dependencies/bin/`（BT 走 AIC USB 模组 `aic_btusb.ko`，非串口 HCI）；③实测：两 demo 复制后 `fun install`+`fun build -p Z21` **均出 libzkgui.so**（需把 demo 老依赖 `easyui 2.2.0`/`base-utility 10.1.3` 提到 `2.6.0`/`10.9.3`，否则新模板报 `hasTimerRegistration` 缺失）；④结论修正：Z20/Z21 后端**可做双角色**，`ble` 包 = 开箱外设服务，`gatt` = 底层库（中心+外设）；⑤**已用两台整机（Z20 做外设 × Z21 做中心）跑通主从对传**：扫描→连接→服务发现→订阅 CCCD→断开自动恢复广播全程有日志（bin 工具 `projects/zbble_srv` / `projects/zbble_cli`，因 `fun launch` 在多设备下报 `more than one device/emulator` 而改 adb push 跑；Z21 `/res` 只读无 `/res/bin` 需工具路径兜底）。',
    '2026-09-14: 动态旋转/运行时换布局（relayout）v0.27.51-open（沛哥指路 RelayoutDemo）——新增 `knowledge/devflow/dynamic-screen-rotation.md`：`CONFIGMANAGER->setScreenRotate(rot)` + `setTouchRotate(rot)` + `Activity::relayout("xxx.ftu")` 运行时换布局不重启应用；两套 ftu 挂同一 Activity、**控件 ID 必须一一对应**；**需 easyui ≥ 2.9.0**（实测 F133 2.8.0 无 / 2.9.0 有、V85X 2.9.0 有；Z20 3.0.0、Z21/T113 2.6.0 无 → **找 FlyThings 厂家**）；`setScreenRotate` 老版本就有，**只有 relayout 是新的**。',
    '2026-09-13: RTL8733BS 蓝牙 bring-up 实践入库 v0.27.44-open（沛哥转交 AI 长跑验收记录，要求「按实际情况确认处理」）——新增 `knowledge/hardware/bt-rtl8733bs-bringup.md`：①**两个前置条件**：BT 必须先在 sysfs 上电（`state_bt` 0→50ms→1→300ms ×2 轮，且被 `persist.wifi.module==8733bs` 前置门挡住，不匹配就走 AIC 分支=完全静默）+ **必须先跑 Realtek hciattach 预初始化**（H5 同步握手 → 读 ROM → 下补丁固件 → 115200 切 1500000），做完才应答标准 HCI ②**电源控制流程与接口单列一节（硬件关联，沛哥特别点名）**：节点与语义（`state_bt` / `state_wifi`，combo 模组上两个独立开关；多候选路径 + `access()` 存在性判断；纯 sysfs 文件读写，不走 ioctl/gpio）+ 调用时机与链路（btstack 初始化前、同一 BT 线程内；前置门不匹配走 AIC 分支=不碰电源不下固件）+ 写后**回读确认 on/off**（100×30ms）+ 失败必须返回 -1 由上层退出（否则一路静默，日志要往前找 rtk 报错）+ 现场排查 6 步 + 复用注意（路径随枚举变、无独立 reset GPIO、断电后等待要秒级）——实测曾卡在 `state_bt` 几小时，必须留档 ③**传输必须是 H5 + 偶校验 8E1 + 无流控**，H4/8N1 必失败；预初始化前判活看厂商命令 `0xFC6D`，判"芯片有没有回"只看事件码 `0x01~0x5F`（`0x6E` 是 btstack 本地的 TRANSPORT_PACKET_SENT，不算回应）④**线程铁律**：btstack 的 run loop init / data source 注册 / TLV / `hci_init` 必须在同一条 BT 线程内做完（违反 = 静默卡 `INITIALIZING`，连 tick 都没有），跨线程走 socketpair data source；`hci_add_event_handler` 必须在 `hci_init` 之后 ⑤**入库前逐条机器核对**并修正三处："必须自研 uart/SLIP" → 改为先查当前 btstack 构建的 frame/parity 能力（v85x btstack 1.7.2 已声明 `set_parity` + 四个 frame 回调 + 自带 slip_wrapper，优先用配置项）；版本锁定在 **Manifest.xml** 不是 fun.json；原稿头注的源工程归属不入库 ⑥固件随应用打包（`src/dependencies/bin/firmware/rtlbt/` → `/res/bin/firmware/rtlbt/`，运行时候选链 /res → /data → /tmp）、TLV 落 `/data`、"抓包重放学遥控器不成立"（BT HID 走加密链路，正解是本机做 hci 主机建映射）⑦未复核项（设备/PC 侧观察）在文档 §7 显式标注，不冒充机检结论。',
]
# ========== 版本史归档（2026-09-30）==========
# 更早的版本史（< v0.27.121-open）搬到仓库根 VERSION_HISTORY.md；kb_tools 只留近期条目，
# 避免「问版本号」类调用与仓库阅读成本随时间线性膨胀。get_version(compact=False) 会回 historyFile。
MCP_FEATURES_ARCHIVE = 'VERSION_HISTORY.md'
MCP_FEATURES_ARCHIVE_MAX = 'v0.27.121-open'



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
    另回 `binTools` 字段（设备端预编译工具：touch / busybox / ui_test / zkshot；mt_test 已移除），
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
    out['historyFile'] = MCP_FEATURES_ARCHIVE          # 更早版本史归档位置（仓库根）
    out['historyMax'] = MCP_FEATURES_ARCHIVE_MAX        # 本文件保留到哪个版本
    if compact:
        out['recent'] = [_clip_feature(f) for f in MCP_FEATURES[:3]]
        out['note'] = ('默认只回近期 3 条、每条 ≤ %d 字以省 token；近期全量传 compact=False；'
                       '更早版本史（< %s）见 %s'
                       % (COMPACT_FEATURE_CHARS, MCP_FEATURES_ARCHIVE_MAX, MCP_FEATURES_ARCHIVE))
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


# ========== op → 知识文档「去哪找」（2026-09-30；不占 docstring 预算的另一种「指路」）==========
# 数据唯一来源：op_seealso.json（人工维护）。返回体统一加 seeAlso 字段（list[str]），
# 让 AI 拿到工具结果后**直接知道去哪看细节**，不必再自己检索一遍（docstring 预算仅 12000 已顶格）。
# 覆盖度进闸门：scripts/gen_seealso.py --check（每个 op 要么有 seeAlso、要么登记 none + 理由）。
_SEEALSO_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'op_seealso.json')
if getattr(sys, 'frozen', False):          # PyInstaller 打包：随包进 _MEIPASS
    _SEEALSO_PATH = os.path.join(sys._MEIPASS, 'op_seealso.json')
_SA_CACHE = {}


def _seealso_table():
    """读 op_seealso.json（带缓存）。缺失/坏掉 → ({}, 原因)，不静默。"""
    if 'err' in _SA_CACHE:
        return {}, _SA_CACHE['err']
    if 'data' in _SA_CACHE:
        return _SA_CACHE['data'], ''
    try:
        data = json.loads(io.open(_SEEALSO_PATH, encoding='utf-8').read())
    except Exception as e:
        _SA_CACHE['err'] = 'op_seealso.json 读取失败（%s: %s）' % (type(e).__name__, e)
        return {}, _SA_CACHE['err']
    _SA_CACHE['data'] = data.get('ops') or {}
    return _SA_CACHE['data'], ''


def _seealso_for(op):
    """该 op 的「去哪找」列表；未登记或登记为 none 时回 None。"""
    ops, _err = _seealso_table()
    ent = ops.get(op) or {}
    refs = ent.get('seeAlso')
    if isinstance(refs, list) and refs:
        out = [str(x) for x in refs]
        out += ['wiki:' + str(w) for w in (ent.get('wiki') or [])]
        return out
    return None


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
    - query：源控件名（或别名），忽略大小写与下划线/连字符（如 lv_slider / QCalendarWidget）
    - source：可选，只在该框架内找（lvgl / qt / android / miniprogram / emwin / mfc）
    命中返回：target（我们控件）/level（L1~L5）/notes/json（可直接粘的片段）/ref/control。
    未命中回 NO_HIT + candidates + 缺口五级处置（有对应控件用映射；平台真缺才做 components/ui_v1/ 包）。
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
    """
    将 json 布局打包为 ftu（设备实际加载的是 ftu）。返回 ftu 路径、控件数、分辨率。
        ftu 是 json 布局的**编译产物**：改布局一律改 json 后 pack，不要手写/手改 ftu
        （详见 knowledge/devflow/ftu-json-pipeline.md；返回体带 confirmNeeded 确认闸门）。
        
    """
    r = pt.flythings_fui_pack(json_path)
    if isinstance(r, dict):
        r.update(_confirm_gate(_project_root_of(json_path), json_path))
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
    （只编译传 with_launch=False）→ 字体体检 + 设备侧 md5 比对
    （staleOnDevice=true ⇒ 设备上还是旧版）。探测不猜：0 台→needDeviceInput；多台→列 serial 要 device=。
    ⚠️ src/activity/ 由 IDE 生成（禁手改），业务只写 src/logic/*.cc。
    链库放 src/dependencies/lib/（fun 自动链接）；**libc 必须匹配**：Z20/Z21=glibc，其余=musl 系。
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
    流程：fun install →（with_build 可选）fun build → fun pack（out_path→-o；--release-version；ab=True→--ab OTA）。
    产物 `.fsc/<平台>/update.img`；刷法 TF卡/ADB/远程批量；换开机 logo → MISC；dry_run=True 只回命令计划。
    ⚠️ `sign error 0xc0000135`=缺 32 位 VC++；`package not found in local`=先 fun install。
    详情：knowledge/devflow/upgrade-pack-image.md。
    """
    return json.dumps(pt.flythings_pack_upgrade(project_root, out_path, release_version,
                                                ab, with_build, dry_run),
                      ensure_ascii=False)



def _project_root_of(json_path):
    """从 ui/*.json 反推项目根（找包含 ui/ 或 Manifest.xml 的最近上级）。"""
    p = os.path.abspath(json_path or '')
    d = os.path.dirname(p)
    for _ in range(4):
        if os.path.isdir(os.path.join(d, 'ui')) or os.path.isfile(os.path.join(d, 'Manifest.xml')):
            return d
        nd = os.path.dirname(d)
        if nd == d:
            break
        d = nd
    return os.path.dirname(p)


def _newest(paths, errs=None):
    """[(mtime, path)] → (最大 mtime, 对应 path)；空列表 → (0.0, '')。

    errs 传 list 时，把「读 mtime 失败」的文件名记进去（上层回给调用方，不静默吞）。
    """
    mt, who = 0.0, ''
    for p in paths:
        try:
            m = os.path.getmtime(p)
        except OSError as e:
            if errs is not None:
                errs.append('%s (%s)' % (os.path.basename(p), type(e).__name__))
            continue
        if m > mt:
            mt, who = m, p
    return mt, who


def _confirm_gate(project_root, json_path=''):
    """确认闸门（2026-09-30 钟工 SmartPanel 检讨）：布局改完 → 项目里有没有**更新**的确认稿？

    只提醒、不阻塞（与「写操作默认安全」同一纪律）：回 confirmNeeded + confirmHint。
    确认稿 = flythings_ui_preview(for_customer=True) 的 `.confirm.html`（或 .preview.html / _edit/*.edit.html）。
    """
    out = {'confirmNeeded': None, 'confirmDraft': '', 'confirmHint': ''}
    try:
        root = os.path.abspath(project_root or '') or _project_root_of(json_path)
        uroot = os.path.join(root, 'ui')
        if not os.path.isdir(uroot):
            return out
        drafts, jsons, skipped = [], [], []
        for dp, _dn, fn in os.walk(uroot):
            for f in fn:
                p = os.path.join(dp, f)
                if f.endswith(('.confirm.html', '.preview.html', '.edit.html')):
                    drafts.append(p)
                elif f.endswith('.json'):
                    jsons.append(p)
        if json_path and os.path.isfile(json_path):
            jsons.append(os.path.abspath(json_path))
        t_json, jm = _newest(jsons, skipped)
        t_draft, dm = _newest(drafts, skipped)
        out['confirmDraft'] = dm
        out['confirmNeeded'] = bool(t_json and (not dm or t_draft < t_json))
        if out['confirmNeeded']:
            out['confirmHint'] = (
                '布局已改（%s）但没有**更新**的确认稿 → 先出确认稿给需求方确认，再 pack / 推真机：'
                'flythings_ui_preview(target="%s", for_customer=True)（单文件 .confirm.html，'
                '手机可打开、带控件标注）；口径见 knowledge/devflow/ui-layout-verify.md §0'
                % (os.path.basename(jm or ''), root))
        else:
            out['confirmHint'] = ('已有确认稿 %s，可直接 pack/推真机（再改布局记得重出确认稿）'
                                  % os.path.basename(dm or ''))
        if skipped:
            out['confirmWarnings'] = skipped
    except Exception as e:                                # noqa: BLE001
        out['confirmHint'] = '确认闸门未跑成：%s' % e
    return out


def _asset_audit(project_root):
    """出图后自动跑资产审计（抗锯齿 / 弧线过渡 / 倒角 / 透明底）；缺工具如实回报，不静默。"""
    out = {'ran': False, 'status': 'skip', 'hint': '', 'checks': []}
    if chk_all is None:
        out['hint'] = ('ui_tools/check_all.py 不可用，审计没跑；手跑 tools/qa/{aa_audit,corner_audit}.py')
        return out
    jobs = (('aa', lambda: chk_all.check_aa_assets(project_root)),
            ('arc', lambda: chk_all.check_arc_quality(project_root)),
            ('corner', lambda: chk_all.check_shape_audit(project_root, 'corner')),
            ('alphaBg', lambda: chk_all.check_shape_audit(project_root, 'alpha')))
    for name, fn in jobs:
        try:
            r = fn() or {}
        except Exception as e:                            # noqa: BLE001
            out['checks'].append({'check': name, 'status': 'error', 'reason': str(e)})
            continue
        item = {'check': name, 'status': r.get('status') or 'skip',
                'defect': len(r.get('defect') or []), 'warn': len(r.get('warn') or [])}
        if item['status'] == 'skip':
            item['reason'] = r.get('reason', '')
        out['checks'].append(item)
    ran = [c for c in out['checks'] if c['status'] not in ('skip', 'error')]
    out['ran'] = bool(ran)
    if any(c.get('defect') or c['status'] == 'fail' for c in out['checks']):
        out['status'] = 'fail'
        out['hint'] = ('有 DEFECT（逐条看 checks 的 defect 数）→ 按 knowledge/devflow/ui-asset-rules.md '
                       '#11~#13 修图后重出；⚠️ 纯二值资产（二维码/条形码那种只有两种颜色的图）会被抗锯齿'
                       '审计判 hard_diag，属预期，需在审计规则里登记豁免而不是改图')
    elif ran:
        out['status'] = 'ok'
        out['hint'] = '抗锯齿/弧线过渡/倒角/透明底审计通过（WARN 逐条列在 checks，不阻塞但别忽略）'
    else:
        out['hint'] = ('审计脚本没找到（tools/qa/*.py 不在搜索路径）→ 手跑 '
                       'python tools/qa/aa_audit.py <项目>/resources/images --fail')
    return out


def _with_confirm_gate(r, json_path='', project_root=''):
    """把确认闸门结果合进返回体（解析不了/不是 dict 就原样回）。"""
    if not isinstance(r, dict):
        return r
    if not project_root:
        p = os.path.abspath(json_path) if json_path else ''
        if p and os.path.isdir(p):                    # 传的是项目根/目录
            project_root = p
        elif p and os.path.isdir(os.path.join(os.path.dirname(p), 'ui')):
            project_root = os.path.dirname(p)
    r.update(_confirm_gate(project_root, json_path))
    return r


def flythings_ui_preview(target: str, output_dir: str = '', for_customer: bool = False) -> str:
    """
    json 布局 / 整个项目 → HTML 预览稿（客户确认 UI 用；只交 html，不产图片/截图）。
        target = 项目根目录（全部 ui/*.json）或单个 json 路径。
        for_customer=True → **客户确认稿** `<name>.confirm.html`：单文件（图内联）、手机可打开/转发、
        带「标注」开关（控件名 + 尺寸 + 坐标）与窄屏自适应；只出预览，不动 json/ftu。
        ⚠️ 多整屏 window 工程自带「页面切换条」+ `#window__N`（简写 `#N`）直达 + 幽灵框看隐藏窗。
        ⚠️ 确认闸门：改完布局先出确认稿给需求方确认，OK 才 pack / 写逻辑 / 推真机
        （口径见 knowledge/devflow/ui-layout-verify.md §0）。
        
    """
    is_dir = os.path.isdir(target)
    r = j2h.json2html(target, output_dir, for_customer=bool(for_customer))
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
        r['forCustomer'] = bool(for_customer)
        r['note'] = ('html 为客户预览稿；设备端仍用 fui pack 生成的 ftu，两者同源于 json' +
                     ('；**客户确认稿**：单文件可发微信/手机打开，点「标注」看控件名与尺寸'
                      if for_customer else ''))
    return json.dumps(_with_confirm_gate(r, target), ensure_ascii=False)


def flythings_html_to_json(input_html: str, output_json: str = '', res: str = '',
                           merge_windows: bool = False) -> str:
    """受限 HTML 交互原型 -> ui/*.json（CSS 效果自动转图；产物尺寸 == 控件盒）。

    ⚠️ 动手前先读《HTML_SUBSET 原型规范》（检索 HTML_SUBSET / data-icon / 自动转图清单）：
    控件映射表、全部 data-* 属性、铁律都在那里，本 docstring 只留最低限度。
    多屏（div.screen，data-page）：每屏一个 json = 一页 = 一个 Activity = 一个 ftu；
    **仅当同属一个 Activity** 时才用 merge_windows 合成同 json 的 N 个整屏 window。
    返回 screensDetected/pagesProduced/jsonsProduced/pages[]；**不等一律 success:false**（不静默丢页）。
    红线 / 确认闸门 / 差异化三问 → knowledge/devflow/html-subset-quickref.md。
    """
    out = h2j.html2json(input_html, output_json or None, res or None,
                        merge_windows=bool(merge_windows))
    hint = _render_path_hint(input_html)
    if hint and isinstance(out, dict):
        out['pathHint'] = hint
    return json.dumps(out, ensure_ascii=False)


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
    """获取 package 的头文件路径、类方法签名、使用示例。传入包名与可选版本。

    注册表没有 ≠ 平台没有：设备 /lib 自带 nanovg/libpng12/freetype/jpeg/mad/zlib，可 dlopen 免编译；
    清单与采集命令见 knowledge/devflow/device-preinstalled-libs.md（先 adb shell ls /lib）。
    """
    return json.dumps(pkgtools.flythings_get_package_api(package_id, platform, version or None), ensure_ascii=False)


def flythings_resolve_dependencies(packages: str, platform: str = _platforms.DEFAULT_PLATFORM) -> str:
    """递归解析 package 依赖树并检测冲突。packages 为 JSON 数组字符串，
    如 '[{"id":"mqtt-cxx","version":"3.2.0"}]'。返回依赖树、解析结果与冲突建议。
    """
    return json.dumps(pkgtools.flythings_resolve_dependencies(packages, platform), ensure_ascii=False)


def flythings_create_bin_project(project_root: str, project_name: str = '', platform: str = _platforms.DEFAULT_BIN_PLATFORM,
                                 app_version: str = '1.0.0', description: str = '',
                                 with_build: bool = True) -> str:
    """
    创建「可执行程序」项目（fun create --type bin）并编译为直接可运行的 ELF 二进制。

        - 项目类型 4 选 1：zkgui / bin（可执行程序）/ staticLibrary / sharedLibrary
        - bin 结构极简：fun.json（"type": "executable"）+ src/main.cpp
        - 编译 fun build → 产物 .fun/{platform}/{项目名}，ELF 魔数验证
        - 部署 adb push + chmod +x 直接跑（无 zkgui 宿主，不能启 UI 应用）
        - 非交互：自动传 --app-version/--description；目录非空直接报错
        用户要「编译出可直接执行的二进制（非 UI 应用）」时调用；platform 默认 z21
        （支持 z20/t113/f133 等）；project_name 缺省取目录名。
        
    """
    return json.dumps(pt.flythings_create_bin_project(
        project_root, project_name, platform, app_version, description, with_build),
        ensure_ascii=False)


def flythings_gen_ui_test(project_root: str, test_type: str = 'ask', output_dir: str = '',
                          platform: str = _platforms.DEFAULT_BIN_PLATFORM, with_build: bool = True,
                          monkey_count: int = 500) -> str:
    """根据 UI json 布局生成自动化测试项目（纯代码，不依赖 AI，省 token）。

    ui/*.json 已含全部控件坐标与可交互信息（touchable/visible），直接解析生成可编译的 bin 测试项目：
      ask      - 询问用户验收方式（默认，返回选项让用户选）
      traverse - 遍历控件：所有可交互控件逐个点击+滑动 + 图片资源缺失检查 + logcat 配合
      monkey   - 压测 MonkeyTest：随机 tap/swipe 指定次数
      custom   - 自定义验收（差异化逻辑走 AI，此模式仅返回提示）

    用户提「自动化测试 / 验收 / 遍历控件 / 压测 / Monkey」时调用；默认先问用户选哪种（省 token）。
    """
    return json.dumps(tt.flythings_gen_ui_test(
        project_root, test_type, output_dir, platform, with_build, monkey_count),
        ensure_ascii=False)


def flythings_test_run(plan: str = '', devices: str = 'auto', project_root: str = '',
                       out: str = '', platform: str = '', parallel: int = 4,
                       baseline: str = 'auto', allow_regions: int = 0,
                       per_device_keys: str = 'auto') -> str:
    """多设备**并行**跑一份 UI 用例（触摸注入+日志断言+像素基线），出 JSON + JUnit 报告。

    plan 是用例 JSON（文本或路径）：steps[].action 取 tap/long/swipe/wait/monkey/run/shot/log；
    每步可带 shot=<基线 key>、expectLog/expectNoLog、allowRegions、wait(ms)。devices="auto"
    （**恰好 1 台才自动选**）/"all"/"<IP>:5555,..."；project_root 给基线库位置；
    baseline=auto/compare/save/off；报告落 out：report.json + report.xml（可进 CI）。
    **比不到基线记 no-baseline，不算通过**。写法见 knowledge/devflow/device-test-run.md。
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
    ⚠️⚠️ src/activity/（mainActivity.cpp/h）由 IDE 按 ftu 生成，**禁止创建/修改/覆盖**；业务只写
    src/logic/*.cc（mXXXPtr / ID_MAIN_* / 回调表 / findControlByID 都由 IDE 生成，禁手写）。
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
    """
    生成 UI 图片资源（图标/牌面/按钮背景等）→ <项目>/resources/images/（json 引用写 images/xxx.png）。

        assets 为 JSON 数组字符串，每项 {name,size,prompt,emoji,color,kind}；name 必填（自动补 .png），
        prompt 优先 AI 生图、失败用 emoji、再不行用 color/kind 线条兜底；kind 取
        check/charging/wifi/alert/circle/square/star/heart。
        **返回体自动带 assetAudit**（抗锯齿/弧线过渡/倒角/透明底审计；有 DEFECT 就修图重出）。
        ⚠️ 铁律（尺寸==控件盒、四角 alpha=0、禁 1x 直画）与三条合法出图路径见知识库
        「UI 图片资源铁律与 PNG 抗锯齿管线」（检索：图片资源铁律 / 抗锯齿 / 走哪条路出图）。
        
    """
    res = h2j_genres.gen_ui_assets(project_root, assets)
    if isinstance(res, dict):
        res['assetAudit'] = _asset_audit(project_root)
    return json.dumps(res, ensure_ascii=False)


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

    完整流程（改 .tr → 本工具转 json + push → 重启加载）见 knowledge/devflow/i18n.md。
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
        if r.get('success') and not dry_run:
            r.update(_confirm_gate(project_root, r.get('json') or ''))
        if dry_run:
            r['note'] = ('dry_run：仅预览，未写盘；确认后传 dry_run=False 写回' +
                         '（要接着 pack 再传 pack=True）')
        else:
            r['note'] = '变更已写回 json' + ('（含 ftu 重新打包）' if r.get('pack') else
                                             '（未 pack：布局确认后传 pack=True）') + \
                        '；备份在同目录 <name>.json.bak；布局改完先出确认稿给需求方确认' \
                        '（flythings_ui_preview for_customer=True）再 pack/推真机（见 confirmHint）'
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


def _render_report_dir(project_root='', json_path=''):
    """清单目录：<项目>/temp/render/ —— **绝不能放 ui/ 下**（json2img 会把 ui/*/*.json 当页面 json）。

    没给工程根时从页面 json 反推；两者都取不到→临时目录（不污染工程）。
    """
    root = str(project_root or '').strip()
    jp = str(json_path or '').strip()
    if not root and jp:
        cand = os.path.dirname(os.path.dirname(os.path.abspath(jp)))
        if os.path.isdir(os.path.join(cand, 'ui')):
            root = cand
    if root:
        return os.path.join(root, 'temp', 'render')
    import tempfile
    return os.path.join(tempfile.gettempdir(), 'ft_render')


def _ui_render(project_root, page='', scale=1, out='', all_pages=False):
    """离线「所见即所得」：ui/*.json → 引擎等价 PNG（子进程调 ui_tools/json2img.py）。

    清单走 --json-report 读回，unsupported（未支持/待校准降级）**原样透出、绝不静默吞**。
    渲染语义（树序 / 拉伸填充 / 对齐位模型 / 裁剪）见 knowledge/devflow/wysiwyg-render-spec.md。
    """
    import subprocess
    script = os.path.join(UI_TOOLS, 'json2img.py')
    if not os.path.isfile(script):
        return json.dumps({'success': False, 'error': 'json2img.py 不可用: %s' % script},
                          ensure_ascii=False)
    root = str(project_root or '').strip()
    if not os.path.isdir(os.path.join(root, 'ui')):
        return json.dumps({'success': False, 'error': 'project_root 下没有 ui/ 目录: %r' % root},
                          ensure_ascii=False)
    pg = str(page or 'main').strip() or 'main'
    try:
        sc = max(1, int(scale or 1))
    except (TypeError, ValueError):
        return json.dumps({'success': False, 'error': 'scale 必须是整数: %r' % scale},
                          ensure_ascii=False)
    rd = os.path.join(root, 'ui', '_render')
    rjd = _render_report_dir(root)            # 清单不进 ui/（否则被当页面 json 扫到）
    outp = str(out or '').strip()
    if all_pages:                       # --all：out 视作输出目录
        dst = outp or rd
        rj = os.path.join(rjd, '_all.report.json')
    else:
        dst = outp or os.path.join(rd, pg + '.png')
        rj = os.path.join(rjd, pg + '.report.json')
    try:                                # json2img 只自建清单目录，产物目录这里保证
        os.makedirs(dst if all_pages else os.path.dirname(os.path.abspath(dst)), exist_ok=True)
        os.makedirs(os.path.dirname(os.path.abspath(rj)), exist_ok=True)
    except OSError as e:
        return json.dumps({'success': False, 'error': '创建输出目录失败: %s' % e},
                          ensure_ascii=False)
    cmd = [sys.executable, script, root, '--scale', str(sc), '--json-report', rj]
    cmd += ['--all', '--out', dst] if all_pages else ['--page', pg, '--out', dst]
    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=900)
    except Exception as e:                      # 解释器/脚本异常也不静默
        return json.dumps({'success': False, 'error': 'json2img 执行失败: %r' % e},
                          ensure_ascii=False)
    log = (proc.stdout or b'').decode('utf-8', 'replace')
    rep = {}
    if os.path.isfile(rj):
        try:
            with open(rj, encoding='utf-8') as f:
                rep = json.load(f)
        except (ValueError, OSError) as e:
            return json.dumps({'success': False, 'error': '清单读取失败: %r' % e,
                               'stdout': log[-1200:]}, ensure_ascii=False)
    pages = rep.get('renders') or []
    if proc.returncode != 0 or not pages:
        return json.dumps({'success': False,
                           'error': 'json2img 失败 rc=%s（页面名/项目路径是否正确？）'
                                    % proc.returncode,
                           'stdout': log[-1500:]}, ensure_ascii=False)
    return json.dumps({'success': True,
                       'pages': [{'page': r.get('page'), 'png': r.get('out'),
                                  'size': r.get('size')} for r in pages],
                       'unsupported': rep.get('unsupported') or [],
                       'missingAssets': rep.get('missing_assets') or [],
                       'stretched': rep.get('stretched') or [],
                       'report': rj}, ensure_ascii=False)


def _ui_render_check(render='', device='', page_json='', tol=2, max_ratio=1.0,
                     project_root='', page='', scale=1):
    """渲染图 vs 真机截图 → 一致性判据（子进程调 ui_tools/wysiwyg_diff.py）。

    render 不给就用 project_root+page 自渲染。pass=false ⇒ 返回体 ok=false +
    error.code=WYSIWYG_MISMATCH（不一致明说，不静默）；判据口径见 wysiwyg-render-spec.md §5。
    """
    import subprocess
    script = os.path.join(UI_TOOLS, 'wysiwyg_diff.py')
    if not os.path.isfile(script):
        return json.dumps({'success': False, 'error': 'wysiwyg_diff.py 不可用: %s' % script},
                          ensure_ascii=False)
    dev = str(device or '').strip()
    pj = str(page_json or '').strip()
    for p in (dev, pj):
        if not p or not os.path.isfile(p):
            return json.dumps({'success': False, 'error': 'device/json 文件不存在: %r' % p},
                              ensure_ascii=False)
    rimg = str(render or '').strip()
    if not rimg:                                # 没给渲染图 → 自己渲染（同 op 内复用）
        root0 = str(project_root or '').strip()
        if not root0:
            return json.dumps({'success': False,
                               'error': 'render 与 project_root 至少要给一个'},
                              ensure_ascii=False)
        r0 = json.loads(_ui_render(root0, page, scale, '', False))
        if not r0.get('success'):
            return json.dumps(r0, ensure_ascii=False)
        pg = str(page or 'main').strip() or 'main'
        hit = [p for p in r0['pages'] if len(r0['pages']) == 1 or p.get('page') == pg]
        rimg = hit[0].get('png', '') if hit else ''
    if not rimg or not os.path.isfile(rimg):
        return json.dumps({'success': False, 'error': '没有可用的渲染图: %r' % rimg},
                          ensure_ascii=False)
    try:
        t, mr = int(tol), float(max_ratio)
    except (TypeError, ValueError):
        return json.dumps({'success': False, 'error': 'tol 需整数 / max_ratio 需数字'},
                          ensure_ascii=False)
    rj = os.path.join(_render_report_dir(project_root, pj),
                      os.path.splitext(os.path.basename(rimg))[0] + '.wysiwyg.json')
    cmd = [sys.executable, script, rimg, dev, pj, '--tol', str(t), '--max-ratio', str(mr),
           '--json', rj]
    root = str(project_root or '').strip()
    if root:
        cmd += ['--project', root]              # 显式给工程根（运行期文字盒识别用）
    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=900)
    except Exception as e:
        return json.dumps({'success': False, 'error': 'wysiwyg_diff 执行失败: %r' % e},
                          ensure_ascii=False)
    log = (proc.stdout or b'').decode('utf-8', 'replace')
    if proc.returncode not in (0, 1) or not os.path.isfile(rj):
        return json.dumps({'success': False,
                           'error': 'wysiwyg_diff 失败 rc=%s（尺寸不一致？看 stdout）'
                                    % proc.returncode,
                           'stdout': log[-1500:]}, ensure_ascii=False)
    with open(rj, encoding='utf-8') as f:
        d = json.load(f)
    pct = d.get('nonTextConsistencyPct')
    mb = d.get('maxBlock') or {}
    ok = bool(d.get('pass'))
    res = {'success': True, 'ok': ok, 'pass': ok, 'render': rimg, 'device': dev,
           'pageJson': pj, 'nonTextConsistencyPct': pct,
           'runtimeTextRatioPct': d.get('runtimeTextRatioPct'),
           'runtimeTextControls': d.get('runtimeTextControls'),
           'maxBlock': d.get('maxBlock'), 'attribution': d.get('attribution') or [],
           'tol': t, 'maxRatio': mr, 'report': rj}
    base = ('非文字区超容差 %.2f%%（判据 ≤ %.2f%%），运行期文字区 %.2f%%，最大差异块 %sx%s'
            % (100.0 - float(pct or 0.0), mr, float(d.get('runtimeTextRatioPct') or 0.0),
               mb.get('w', 0), mb.get('h', 0)))
    if ok:
        res['message'] = '一致（PASS）：' + base
    else:
        res['code'] = 'WYSIWYG_MISMATCH'
        res['message'] = ('渲染图与真机截图不一致（FAIL）：' + base
                          + '；逐控件归因见 attribution，口径见 '
                            'knowledge/devflow/wysiwyg-render-spec.md §5')
    return json.dumps(res, ensure_ascii=False)


# ── 合并后的唯一入口（v0.27.37）──────────────────────────────────────────
# 三动作合一：editor（原 ui_editor）/ edit_apply（原 ui_edit_apply）/ diff（原 ui_diff）。
# 每个 action 只接受自己的参数；传了别家的参数会回 visualNote 提醒（不静默忽略）。
UI_VISUAL_ACTIONS = ('editor', 'edit_apply', 'diff', 'baseline', 'render', 'render_check')
UI_VISUAL_ARGS = {
    'editor': ('project_root', 'output_dir'),
    'edit_apply': ('project_root', 'changes', 'pack', 'dry_run'),
    'diff': ('image_a', 'image_b', 'tolerance', 'shift', 'min_area', 'blur',
             'noise_bbox', 'out_png', 'out_json', 'show_noise'),
    # baseline（2026-09-29）：像素基线库 —— 把「上一次验收通过的那张图」版本化存下来
    'baseline': ('project_root', 'image_a', 'mode', 'baseline_key', 'name', 'allow_regions',
                 'tolerance', 'shift', 'min_area', 'blur', 'noise_bbox', 'out_png'),
    # render / render_check（2026-10-01，钟工：设计流要像写 HTML，离线所见即所得要闭环）
    'render': ('project_root', 'page', 'scale', 'out', 'all'),
    'render_check': ('render', 'device', 'json', 'tol', 'max_ratio', 'project_root',
                     'page', 'scale'),
}
UI_VISUAL_REQUIRED = {'editor': ('project_root',),
                      'edit_apply': ('project_root', 'changes'),
                      'diff': ('image_a', 'image_b'),
                      'baseline': ('project_root',),
                      'render': ('project_root',),
                      'render_check': ('device', 'json')}
_UI_VISUAL_DEFAULTS = {'project_root': '', 'output_dir': '', 'changes': '', 'pack': False,
                       'dry_run': False, 'image_a': '', 'image_b': '', 'tolerance': 2,
                       'shift': 1, 'min_area': 4, 'blur': 0.7, 'noise_bbox': 10,
                       'out_png': '', 'out_json': '', 'show_noise': False,
                       'mode': '', 'baseline_key': '', 'name': '', 'allow_regions': 0,
                       'page': '', 'scale': 1, 'out': '', 'all': False, 'render': '',
                       'device': '', 'json': '', 'tol': 2, 'max_ratio': 1.0}


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


def _render_path_hint(text):
    """按关键词给一行「走哪条路」（返回体提示，不占 docstring 预算）。"""
    s = str(text or '').lower()
    keys = ('旋转', '矢量', '半透明', 'alpha', '3d', '模糊', '仪表', '图表', '粒子')
    if not any(k in s for k in keys):
        return ''
    return ('检测到可能涉及矢量/旋转/透明/差异化绘制 → 先答三问（静态还是逐帧？面积多大？'
            '有无硬件层？），再查 knowledge/uicontrols/extension-surface.md 选扩展点；'
            '任意角度旋转位图平台没有（先例 components/vinyl）')


def _ui_visual_hint(raw, hint):
    """把 pathHint 塞进返回体（解析不了就原样回）。"""
    if not hint:
        return raw
    try:
        d = __import__('json').loads(raw)
    except ValueError:
        return raw
    if isinstance(d, dict):
        d['pathHint'] = hint
        return __import__('json').dumps(d, ensure_ascii=False)
    return raw


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


def _jvis(o):
    """json.dumps 的本地别名：flythings_ui_visual 有名为 json 的参数，会遮蔽模块名。"""
    return json.dumps(o, ensure_ascii=False)


def flythings_ui_visual(action: str = 'list', project_root: str = '', output_dir: str = '',
                        changes: str = '', pack: bool = False, dry_run: bool = False,
                        image_a: str = '', image_b: str = '', tolerance: int = 2,
                        shift: int = 1, min_area: int = 4, blur: float = 0.7,
                        noise_bbox: int = 10, out_png: str = '', out_json: str = '',
                        show_noise: bool = False, mode: str = '', baseline_key: str = '',
                        name: str = '', allow_regions: int = 0,
                        page: str = '', scale: int = 1, out: str = '', all: bool = False,
                        render: str = '', device: str = '', json: str = '',
                        tol: int = 2, max_ratio: float = 1.0) -> str:
    """
    UI 可视化/像素验收入口（action 选动作；旧编辑器三 op 已并入）。

        - editor：ui/*.json → 可拖拽编辑器网页（<项目>/ui/_edit/<name>.edit.html）。
        - edit_apply：变更 JSON 写回 ui/*.json（pack 默认 False；dry_run 只预览；写回留 .bak）。
        - diff：两张同尺寸截图逐像素对比，出 0 token 差异清单。
        - baseline：像素基线库（<项目>/ui_baseline/），mode=save/compare/update/list。
        - render：ui/*.json → 引擎等价 PNG（离线所见即所得；out 缺省 <项目>/ui/_render/<page>.png；
          all=true 全页；scale 放大走 NEAREST）；返回 pages[]+unsupported[]（降级项不吞）。
        - render_check：渲染图 vs 真机截图 → 一致性判据（缺 render 则用 project_root+page 自渲染）；
          回 nonTextConsistencyPct/runtimeTextRatioPct/maxBlock/pass/attribution[]；pass=false⇒ok=false。

        渲染语义真相见 knowledge/devflow/wysiwyg-render-spec.md；action 传 list 看参数。
    """
    act = str(action or '').strip().lower().replace('-', '_')
    if act in ('', 'list', 'help', '?'):
        return _jvis({'success': True, 'op': 'flythings_ui_visual',
                      'actions': {k: {'args': list(v),
                                      'required': list(UI_VISUAL_REQUIRED[k])}
                                  for k, v in UI_VISUAL_ARGS.items()},
                      'hint': ('action 取 editor / edit_apply / diff / baseline / render / '
                               'render_check；旧 ui_editor / ui_edit_apply / ui_diff 已并入本 op')})
    if act not in UI_VISUAL_ACTIONS:
        return _ui_visual_bad('unknown action: %s' % action,
                              'action 取 editor / edit_apply / diff / baseline / render / '
                              'render_check（传 action="list" 看参数）')
    given = {'project_root': project_root, 'output_dir': output_dir, 'changes': changes,
             'pack': pack, 'dry_run': dry_run, 'image_a': image_a, 'image_b': image_b,
             'tolerance': tolerance, 'shift': shift, 'min_area': min_area, 'blur': blur,
             'noise_bbox': noise_bbox, 'out_png': out_png, 'out_json': out_json,
             'show_noise': show_noise, 'mode': mode, 'baseline_key': baseline_key,
             'name': name, 'allow_regions': allow_regions,
             'page': page, 'scale': scale, 'out': out, 'all': all, 'render': render,
             'device': device, 'json': json, 'tol': tol, 'max_ratio': max_ratio}
    miss = [k for k in UI_VISUAL_REQUIRED[act] if not str(given[k] or '').strip()]
    if miss:
        return _ui_visual_bad('action=%s 缺必填参数: %s' % (act, ', '.join(miss)),
                              '本 action 参数: %s(%s)' % (act, ', '.join(UI_VISUAL_ARGS[act])))
    ignored = [k for k in given
               if k not in UI_VISUAL_ARGS[act] and given[k] != _UI_VISUAL_DEFAULTS[k]]
    note = ('action=%s 用不到这些参数，已忽略: %s（各 action 参数见 action="list"）'
            % (act, ', '.join(ignored))) if ignored else ''
    if act == 'editor':
        return _ui_visual_hint(_ui_visual_note(_ui_editor(project_root, output_dir), note),
                              _render_path_hint(changes))
    if act == 'edit_apply':
        return _ui_visual_hint(_ui_visual_note(_ui_edit_apply(project_root, changes, pack, dry_run), note),
                              _render_path_hint(changes))
    if act == 'baseline':
        prof = {'tolerance': tolerance, 'shift': shift, 'minArea': min_area, 'blur': blur,
                'noiseBbox': noise_bbox}
        return _ui_visual_note(_ui_baseline(project_root, image_a, mode, baseline_key,
                                            name, allow_regions, out_png, prof), note)
    if act == 'render':
        return _ui_visual_note(_ui_render(project_root, page, scale, out, all), note)
    if act == 'render_check':
        return _ui_visual_note(_ui_render_check(render, device, json, tol, max_ratio,
                                               project_root, page, scale), note)
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
    """从**设备真机**抓当前屏幕 → PNG / JPG / BMP（给视觉模型看，或给 ui_visual(action="diff") 验收）。

    三段式验收第二步。常用：scale=0.5 或 fmt='jpg', quality=85 省 token；rotate='auto' 按工程
    EasyUI.cfg 转正；只要应用画面 crop='auto'。进阶参数（fb/pixel/宽高/offset_y/flip/rotate/crop/layer/
    vdec_chn/name/timeout）走 advanced(JSON)；layer="video"（仅 SigmaStar）抓视频层，多路/
    拼墙必须给 vdec_chn（默认 0，**拼墙在 chn 1**）。⚠️ 抓完把返回 path 交看图能力。
    检索词与踩坑见 knowledge/devflow/device-screenshot.md。
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
    """整机快照（十一个分区），每分区给 {ok, hint, data}；`ok=false` **不是错误而是结论**。

    分区：设备信息/应用状态/显示/存储/网络/蓝牙/输入/外设/时间/库清单/部署一致性（第⑪区治「改了像没改」）。
    采集容忍设备缺工具：优先随仓 bin_tools/<平台>/busybox（→设备 /tmp/busybox，缺则推），否则纯 adb shell。
    device='<serial|IP>:5555'（可省；**多台在线不猜**，回 NO_DEVICE + 在线清单）；
    diff_against=<上次快照.json> 出逐分区差异；out=<json 路径> 落盘（可复用作基线）。
    检索词：整机自检/selfcheck/十分区/快照/与上次对比（knowledge/devflow/selfcheck-and-bugreport.md）。
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
    """
    缺陷单生成器：缺陷清单 + 真机判据 → 可提交 markdown（格式对齐 html2json A1~A8 那批）。

        只给 title 也能出框架稿；steps/evidence 支持 JSON 数组或换行/分号/逗号分隔。
        真机判据自动附：型号·固件·fingerprint·应用状态（init.svc.zkswe / pid / uptime）·
        `logcat -d -s zkgui` 末 40 行；采不到就写明原因。
        ⚠️ evidence 文件不存在 → 直接报 EVIDENCE_MISSING（不静默）。severity ∈ blocker…trivial。
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
    sa = _seealso_for(op)          # 「去哪找」：不占 docstring 预算（见 op_seealso.json）
    if sa:
        out.setdefault('seeAlso', sa)
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
