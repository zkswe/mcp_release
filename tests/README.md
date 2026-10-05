# tests/ — 契约用例（离线，零真机依赖）

> 为什么有：35+ 个 op 此前**没有任何契约测试**，参数写错、envelope 变形、清单漂移、
> 破坏性默认值被人改回去，都只能等用户在真机上撞到（见 `../REVIEW-2026-10-03.md` §1.2）。

## 跑法

```bash
python scripts/run_tests.py                 # 推荐：带**逐用例看门狗**的全量运行
python -m unittest discover -s tests -q     # 等价裸跑（无看门狗）
python scripts/check_retrieval.py           # 检索回归（16 条真实问法 + 11 条对照组；模型缺失时自动降级 BM25）
python scripts/ci.sh                        # CI 前置：compileall + 一致性 + 用例 + 冒烟 + 检索回归
python scripts/check_consistency.py --with-tests
```

> ⚠️ **「离线」是有守卫的，不是靠自觉**：`_util.py` 在 import 时把 `adb_tools._run`
> （全部 adb 调用的唯一子进程出口）默认拦掉 —— 语义等价于「本机没有 adb」，
> 于是任何漏了 mock 的设备调用都会**快速退化**而不是去连真机。
> 确实要起真进程的用例，用 `with U.allow_subprocess():` 显式开口。
>
> 为什么加它（2026-10-03 实测）：以前是「按调用点逐个 mock」，`flythings_build_ui_flow`
> 内部新加的 `device_probes.clear_logcat` 就漏了 mock —— fake 序列号被拿去**真 adb** 上跑，
> 本机挂设备时直接阻塞：单模块 78s/91s，全套 >900s，把 `--with-tests` 自己的 900s 超时撞爆。

> 依赖：只用标准库 + 仓库已有依赖（Pillow 缺失时图像相关用例自动 skip）。**不连真机**。
>
> **耗时画像（2026-10-03 实测，676 条）** —— 慢的不是"某个卡点"，是**一批真做事的用例**；
> 且**总时长随机器负载/文件系统大幅漂移：实测同一份代码 1036s ~ 2192s（≈17~37 分钟）**。
> 各模块：`test_ui_visual_merge`(83s) / `test_asset_pipeline`(78s) / `test_toolchain_capability`(68s) /
> `test_deps_install_guard`(63s) / `test_project_state`(51s) / `test_runtime_setpic`(50s) /
> `test_font_autoscan`(44s) / `test_preflight`(36s)。
> 单条最贵的 8~11s（`render_check` 真渲染、`preflight --scale` 真缩图、字体 cmap 真扫描、真 `fui.exe`）。
> 稳态单次 op 调用只要 **6ms**（实测），所以**不要**去优化分发器/`asyncio` —— 要压时间只能压这些真实工作。
>
> 因此**不要**用"一个全局墙钟超时"去守整套 —— 实测**同机同代码**，全套一次 1036s 跑完、
> 一次 >1800s 未结束（随机器负载漂移）。紧超时会把"机器慢"误判成"挂死"，真挂死它又定位不到是哪条。
>
> 正确守法是 `scripts/run_tests.py` 的**逐用例看门狗**：每条用例起跑时重置计时，超过
> `--per-test-timeout`（默认 120s，实测最贵一条 ~11s）就 dump 全线程栈并结束进程 ——
> 于是"慢"和"挂"是两回事。
>
> **最终形态：不用墙钟当判据。** 实测同代码三次全量 = `1036s 通过` / `>1800s 超时` / `>2700s 超时`
> —— "能不能跑完"取决于机器负载与文件系统，是环境属性。所以发布闸门**默认不给外层墙钟**：
> 判"挂"靠看门狗，判"慢"不判。CI 想兜底可设 `FLYTHINGS_TEST_TIMEOUT=<秒>`。
> 一句话：**慢没关系，挂必须被逮到并带栈。**
当前规模：**1129 项**（这个数由 `check_consistency.py --with-tests` 对着真实 `Ran N tests` 核对 —— 不许手写。
2026-10-03 实测：本条此前写的是 443，而真实值是 676，**脱节 233 条**；这也是「易漂移的数字必须派生」的又一个例子）。

> 2026-09-27（v0.27.115-open）：`test_device_screenshot_probe.py` 新增 7 项（+22 → 共 18）——
> 视频层抓帧的 **vdec 通道口径**：默认必须是 chn 0（`zkshot ... vdec 0 0`，向后兼容）、
> 显式 `vdec_chn=1` 要真的传进 zkshot 命令行且返回体回显 `vdecChn` + `zkshotCmd`、
> 取帧失败/空帧必须回带实际通道号 + 指路 hint（不静默）、`vdec_chn` 传垃圾要明确报错、
> `capture(layer='video')` 必须透传 `vdec_chn`、CLI 必须有 `--layer`/`--vdec-chn`。

> 2026-09-21（v0.27.101-open，需求方口径 A「没给设计稿不许直接建工程」）：新增 `test_design_first_gate.py`（16 项）——
> 设计产物检测口径（`design/` / `*.html` / `*.preview.html` 算、构建产物目录不算、目录不存在不提示）、
> `create_project` / `build_ui_flow` 的**软闸门只加 warnings**（失败路径不加、有设计稿不加、success 与业务键逐字段不变）、
> `create_project` / `get_project_spec` docstring 必须点出「先出设计稿」、docstring 预算仍守住、
> `tools_manifest.json` 每个 op 带 `stage` 且与意图闸门 `catalog.json` 同步。
> 同时 `test_deps_install_guard.py` / `test_font_autoscan.py` 的「零 warnings」正例改为**剔除该条设计提示后**再断言（不是放宽：原本要钉的是流程噪音）。

> 2026-09-19（v0.27.96-open，A1/A3）：	est_gen_res_aa.py 的参考真值改为 **Image.BOX 面积平均**，并新增/改写契约：_ss_down 必须走 BOX（0 脏边）、旧 LANCZOS 口径复现（反面教材）、描边整像素带无亚像素混色、边界像素必须纯描边色、gen_btn9 按下态描边跟随按下色、has_straight_alpha() 判据；	est_html2json_ss.py 真值同步改 BOX。
> 2026-09-21（v0.27.100-open，需求方口径反转）：`test_html2json_multiscreen.py` 重写 —— html2json 多屏缺省从「合成多整屏 window」改为「**每屏一个 json**」（一个 .screen = 一个页面 = 一个 Activity = 一个 ftu），合成多整屏 window 变显式 `--merge-windows`；并新增 `jsonsProduced` / `pages[]` 逐页列全 / 嵌套 `.screen` 降为 warning。

## 用例分布

| 文件 | 钉住什么 |
|------|----------|
| `test_baseline_testrun.py` | **像素基线库 + 多设备测试跑批**（v0.27.124）：基线存/比/刷/list（容差档案随基线存、replace=False 不覆盖、revision 递增）；**判据不许静默**——比不到基线 → `no-baseline`（**不是**pass）、尺寸变了 → `size-mismatch`（不硬比）、索引坏了 → `error`、索引在文件丢 → `listing.missingCount`；plan 解析（空/错 action 回可用清单 + planDoc、文件路径、缺省名）；多设备选择（**多台在线 `auto` 不猜**、`all`、显式/裸 IP、不存在要报、无设备给 installHint）；`_one_step`（注入 rc≠0 → error、日志断言不过 → fail、抓屏失败 → error、run 缺 script → error）；JUnit XML（tests/failures/errors/skipped 计数 + XML 转义） |
| `test_dispatch_contract.py` | op 清单（分发器 = manifest = kb_tools.OP_NAMES）、未知 op 候选、`BAD_ARGS`/`BAD_PARAMS`（参数写错必须回正确签名）、每个非真机 op 空参调用必须回可解析 envelope、**工具面三模式**（默认只 1 个分发器 / `all` 兼容 / `flat` 与 `mcp_server_flat.py` 均 32 个）、`get_version` compact 不膨胀、manifest 新鲜度 |
| `test_control_map.py` | **跨框架控件映射**（v0.27.73 / 滚轮族 v0.27.93 / **TimePicker 全族 v0.27.94**）：`mcp_control_map.json` 完整性（六源 / 条数 / 级别取值 / 片段可解析 / L1·L2 必给可粘 json）、op `flythings_map_control` 契约（命中形状 / 模糊大小写 / `source` 限定 / `NO_HIT` / `BAD_SOURCE` / `BAD_PARAMS`）、tab 类指向 `_mapping/TabView`、**滚轮族 + `TimePicker`（含时钟盘）/`NumberPicker`/`LISTWHEEL`/`QTimeEdit`/`picker mode=time` → `listview`+L2**、`targets.wheelpicker` 无悬空引用、**表里不许再有「时间/时钟盘无对应能力」类旧表述**|
| `test_search_quality.py` | 检索：中文**字级 bigram**切词（整段中文不得成为一个 token）、kb_tools 与 rag_search 共用同一套切词、8 条真实问法 BM25 top-3 命中、hits 带 `source`、返回体带 `retrieval`/`degraded`/`quality`、未收录与低置信必须带检索边界提醒、`k` 上限夹紧 |
| `test_platform_matrix.py` | 平台唯一来源：模板/bin_tools 目录真实存在、别名归一、未知平台报错且列出全部支持项、默认平台有效；`test_platform_resolution.py` 另有 **V85x 芯片别名**（v0.27.87）：`V851/V851S/V851S3/V853S`（含 `v851s` 这类大小写混写）必须 `resolve`→`V85X` + `package_key`→`v85x`，且它们**不得**出现在 `package_keys()`/`PACKAGE_KEY_ALIASES`（芯片名不是包键）；`package_catalog` 的 `v85x`/`v85xemmc.chips` 与 `hardware_catalog.V85X`（含 `chipEntries`，无实测的如实 `pending`）都已收齐这 6 个主控 |
| `test_layout_flow.py` | fui pack 确定性 + affectedFiles；**edit_ftu 默认不覆盖原 ftu**（原文件字节不变、留 .bak、产 `.edited.ftu`）；`flythings_ui_visual(action="edit_apply")` dry_run 不写盘 / 默认不 pack / 写盘留 .bak |
| `test_asset_pipeline.py` | html2json **黄金样例**（渐变/圆角/阴影/emoji/loading 必须真出图且 PNG 尺寸 == 控件盒 = v0.27.30 三连 bug 防回归）；**`div.text` 的 `data-bgpic` 必须落成 backgroundPic**（v0.27.90：正例 + 裸名补 `images/` + 反例「无 bgpic / 只有 data-bg 的 text 不受影响」+ 有图去底色 + 该图必须与盒 1:1）；已自动转图的效果不许再喊「请切图」；`verify_assets`：分层 `ui/<res>/*.json` 必须扫到、自动生成图尺寸不符 = FAIL、手绘图被拉伸 = 仅提示、缺图 = FAIL、0 页必须 warning；**thumb 自有尺寸子盒**（v0.27.75）：thumb.size 一致 → ok / 31 vs 30 → mismatch FAIL / pressedPic 也核 / 手绘 thumb 只 stretched / 无 size → `skippedNoBox`+warning 不误报 |
| `test_gen_res_aa.py` | **切图抗锯齿档位**（v0.27.75）：FT-008 契约（`rounded_rect` 的 α≥128 轮廓 == 1x 直画，默认行为钉死）/ `rounded_rect_ss` 在强曲率上必须比 FT-008 准一半（对 16x 超采样理想值）/ ss 越高不更差 / 尺寸·四角透明·半径钳制 / 半透明底无暗边（alpha 预乘） |
| `test_html2json_multiscreen.py` | **多屏 = 一个 `.screen` 一页一个 json（v0.27.100 需求方口径）+ 页数 = 屏数，一屏不许丢**：单屏产物**逐字段+键序**与改动前黄金样例一致（口径调整不得动单屏）/ 单屏返回 `screensDetected=pagesProduced=jsonsProduced=1`、pages 1 条、不多加多屏 warning / 无 `.screen` 时回 0/0 + error / **缺省 2 屏 → 2 个 json**（`home.json`/`detail.json`，文件名取 data-page；无整屏 window 包裹；每份与该屏**单独转逐字段一致**）+ `pages[]` 逐页列全（页名 + 各自 json 路径）+ output 写目录 / 缺省 `page_k` 命名 / warnings 讲清「window / dialog 属于屏内部」 / **`merge_windows=true`（CLI `--merge-windows`）→ 1 个 json + `window__1..window__2`**（连续编号、整屏、首屏 visible 其余 false、caption=data-page、屏内控件挂自己窗口、各屏自己的底色）+ pages 逐页列全且都指向同一 json + warnings 回显「本次按 merge-windows 合成」/ **嵌套 `.screen` 降为 warning**（只取最外层、点名嵌套屏 data-page、屏内控件不丢）/ **反例**：`data-page` 重复 → `success:false`（屏数核对，不静默丢页）；同重名在 merge 形态下两窗全在 / op 面签名暴露 `merge_windows` 且**不含**退役的 `split_per_page`；CLI `--merge-windows` 与 API 等价、`--split-per-page` **明确报错（退役）**|
| `test_html2json_ss.py` | **html2json CSS 出图一律 SS**（v0.27.76）：`SS_DEFAULT`/`_CSS_SS` == 4；渐变药丸与阴影片在 SS 下必须显著优于老路（对 16x 理想值，阴影片比 α 最大偏差）；SS mask 不许引入暗边（边界 RGB 对列内基准）；`crop=False` 「图 == 控件盒」尺寸不受 SS 影响；`border-radius` 解析（`px`/无单位/`%`/多值/无声明默认）+ 端到端 `50%` 真出正圆（覆盖率 ≈ π/4） |
| `test_ui_visual_merge.py` | ui-visual 三合一（`flythings_ui_visual(action)`）：action="list" 参数目录、未知 action / 缺必填参数 = BAD_PARAMS、editor/edit_apply/diff 三路路由、别家 action 的参数必须回 `visualNote`（不静默忽略）、三个旧名回 OP_RENAMED 且 hint 带该用哪个 action；**2026-10-01 新增 render / render_check**（离线所见即所得接线）：`render` 出 PNG + `pages[]` + `unsupported[]`（降级项必须透出）、`scale=2` 尺寸翻倍、缺 `project_root` = BAD_PARAMS；`render_check` 自渲染路径 / 与自身渲染图比 → `nonTextConsistencyPct=100` PASS / **不一致 → `ok=false` + `WYSIWYG_MISMATCH`（不静默）**/ 真机图缺失明确报错 |
| `test_toolchain_capability.py` | `fui unpack` 能力声明与实际一致（声称能用必须真解出 json；声称不能用必须真解不出）、json→ftu→json 往返语义等价、无 unpack 且缺 json 源时 edit_ftu 必须明确报错；**`flythings_fui_unpack`（v0.27.91）**：默认**覆盖**同目录同名 json（ftu 为真源）、`overwrite=False` 保留 json 源（写 `.unpacked.json`、再解换序号）、非 `.ftu`/文件不存在报错、`output_json` 指定路径（父目录自动建）、`edit_ftu` 在缺 json 时自动 unpack 出编辑源（`unpackedSource`）；**ftu→json 自动同步三条规则**（09-18 口径）：只有 ftu 没 json → 直接转、ftu 比 json 新「分钟级」≥60s → 转同步、新几秒或 json 更新 → **不做**反向（阈值钉住 ≥60）；**异常 ftu（不能反解析）→ 必须报错并带 `hint` 告知用户**（不静默跳过） |
| `test_deps_install_guard.py` | **依赖/install 诊断**（v0.27.83）：代码或 fun 生成的 `generated/*.h` 引用 `base/…` ＋ Manifest 未声明 `base-utility` → `check_project_deps`（`kind="framework"`）/ `validate_project`（`missing_framework_dependency`）必须报出并带可照做的 fix；**声明过或已被传递依赖解析（.fun-lock.json）→ 不许报**；UI 工程无 base 引用也要报、bin 工程（fun.json type=executable）不报；`base/http_*.h`（base-http-client）不算 base-utility；`build_ui_flow`：install 失败 → 顶层 warnings 且**不阻断**build、缺包 → build 前 `check_framework_deps` 直接点明、ninja 的 `base/function.h` 报错被翻译成「依赖未装/缺包」（本文件只盯依赖诊断，离线跑显式传 `with_launch=False`） |
| `test_adb_resolve.py` | **adb 单一入口 + launch 默认推设备**（v0.27.84）：`resolve_adb()` 优先级（env `ADB`/`FLYTHINGS_ADB` > 随包 `tools/adb/adb.exe`（三件齐备）> PATH > 空串+提示）；`FLYTHINGS_ADB` 与 `ADB` 等价；`devices -l` 解析（带 model / 网络设备无 model / unauthorized）；网络设备用 `getprop` 补 model 并判平台；型号表口径（实测三条 → Z21/Z20/V85X 且必须带 `source`；F133/F136 串 **platform 留空 + todo，不许猜**；表里不许出现 IP）；`match_platform` 三态（未知 ≠ 不匹配）；0 台 → `needDeviceInput`+`installHint`（含 ADB 驱动 / USB 调试 / 网络接入）；多设备提示**不替你选机器**；`staleOnDevice` 判据（设备侧字节/md5 vs 本地，无 md5 时退化比字节；三个真机坑：`ls -l` 第 5 列才是字节 / 裁剪 rootfs 的 `wc -c` 返回空 / 缺 md5sum 走随仓 busybox 兜底）；`fun` 多设备硬失败（`more than one device/emulator`）hint 识别；`build_ui_flow` 默认 `with_launch=True`（两处签名）、1 台匹配 → `fun launch -s <serial>`、`with_launch=False` **不探测不推设备**|
| `test_runtime_setpic.py` | **`check_all` 第 20 项「运行期 set...Pic 的图 vs 控件盒」**（v0.27.90）：尺寸相等 → ok；`images/` 自动生成图不等 → `mismatch` FAIL（钉住真机事故：48×16 图进 48×26 盒 → 正圆变竖椭圆）；手绘图（`navi/fh.png` 44×26 进 72×40）→ 仅 `stretched`；`.9.png` 豁免；文件不存在 → `missing`；变量映射不到控件 → `unresolved`（不静默跳过）；`setBackgroundPic(path)` / `snprintf` 拼路径 → 只计 `dynamic`；注释里的调用不算；三元式两个字面量都比；同一 caption 多页且有任一盒子对应就不报 |
| `test_font_autoscan.py` | **字体自动扫描接线 + 缺中文自动投递**（v0.27.86）+ **cmap 硬判据**（v0.27.87）：`flythings_build_ui_flow` **默认**（`font_check='auto'`）就扫字体并把 `common` 档投进工程 `font/`（step 必须在 `fun build` **之前**、返回体写清写入了哪些文件）；`font_check='off'` → **零字体 step 且不写盘**；无设备退化工程侧 self-scan（`note` 写清「未连设备，仅工程侧检查」、**不碰 adb**）；prefs 的 `font` 指向缺失文件 → 报「引用是断的」；`check_project_deps` 默认**只报不投**（`font_apply=True` 才投）+ `fontCheck` 字段（`missingChinese`/`maxFontBytes`/`advisedTier`/`delivered`/`deviceFonts`）+ `fontIssues` 带一键修复命令；阈值/三版清单/投递动作**单一来源**= `device_font_check`（改 `CJK_SIZE_MIN_KB` 结论跟着变）；设备分支（假设备）扫到 `deviceFonts` 并自动投递、且**不重复探 adb**。**硬判据部分**（离线：仓库自带 ttf + fontTools 现场造字体当假设备数据）：基准集 = GB2312 一级 **3755 字**、阈值 90/50 边界、三条 verdict（真字体 100%→`ok` 不投 / 53.3%→`low` 投 / 拉丁 0%→`missing` 投）+ warning 写明覆盖率、缓存命中不再拉（键随体积变即失效）、**超限 12MB / fontTools 不可用 / 拉取失败 → 退回体积判据且 warnings 写明原因**、只探最大字体、临时目录用完即删、部署后复查 `deviceAfterDeploy`（不一致 → 明说 `pack_upgrade` 才生效） |
| `test_design_first_gate.py` | **设计先行软闸门**（v0.27.101）：设计产物检测口径（`design/` 目录 / `*.html` / `*.preview.html` 算设计产物，`.fun/Release` 构建产物不算，目录不存在不提示）、`create_project` / `build_ui_flow` 缺设计产物时**只加一条 warnings**（`未检测到设计确认稿…` 带 prototype-flow）且**不改 success / 不改其它键**、失败路径不加、有设计稿不加；`create_project` / `get_project_spec` docstring 必须含「先出设计稿」+ `prototype-flow`；docstring 预算（单 op ≤900 / 全体 ≤12000）仍守住；`tools_manifest.json` / 闸门 `catalog.json` 每个 op 的 `stage` 同步 |
| `test_selfcheck_bugreport.py` | **整机自检 + 缺陷单**（v0.27.123）：`selfcheck` 十一分区结构（每区 ≥2 采集项、`{ok,hint,data}` 齐备、**读不到必须给 hint**、缺 busybox 的采集项必须带 note）、无设备/多台在线**优雅报错 + hint 不猜机**（`NO_DEVICE`）、`diff_against`（同快照全 same / 改读数报 changed+before·after / 基线缺失 `DIFF_BASE_MISSING` 且**不丢本次快照**）；`bugreport` 段落齐备（标题·元信息·现象·复现步骤·期望 vs 实际·真机判据·证据·影响面）+ 真机判据含最近 logcat + 前 20 行预览、默认落 `<项目>/temp/bugreports/`、**evidence 不存在 → `EVIDENCE_MISSING`（不写单子）**、`title` 空 → `BAD_PARAMS`、采不到真机数据时写明原因不伪造；六方登记（manifest 的 risk=device/write + category + stage）+ `list` 签名 + 知识文档检索导引 |

> 工具 docstring 有字数预算（单 op ≤ 900 字符、全体 ≤ 12,000）——由 `scripts/check_consistency.py` 卡；
> 长尾细节请写进 `knowledge/`（可检索），别塞回 docstring。

## 约定

- 临时工程一律建在系统临时目录（`_util.project()`），用例结束清理，不污染仓库。
- 夹具优先复用 `ui_tools/examples/`（`effects_test.html` = CSS 效果黄金样例、`main.json` = 布局样例）。
- 新增 op / 改平台 / 改破坏性默认值时，**先补用例再改代码**（这些契约正是事故留下的钉子）。
