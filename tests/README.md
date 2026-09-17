# tests/ — 契约用例（离线，零真机依赖）

> 为什么有：35+ 个 op 此前**没有任何契约测试**，参数写错、envelope 变形、清单漂移、
> 破坏性默认值被人改回去，都只能等用户在真机上撞到（见 `reports/flythings-mcp-review-2026-09-11.md` §3.5）。

## 跑法

```bash
python -m unittest discover -s tests -q     # 全部（约 2 秒）
python scripts/ci.sh                        # CI 前置：compileall + 用例 + 一致性 + 冒烟
python scripts/check_consistency.py --with-tests
```

依赖：只用标准库 + 仓库已有依赖（Pillow 缺失时图像相关用例自动 skip）。**不连真机**。
当前规模：**239 项**（1 项按环境 skip）。

## 用例分布

| 文件 | 钉住什么 |
|------|----------|
| `test_dispatch_contract.py` | op 清单（分发器 = manifest = kb_tools.OP_NAMES）、未知 op 候选、`BAD_ARGS`/`BAD_PARAMS`（参数写错必须回正确签名）、每个非真机 op 空参调用必须回可解析 envelope、**工具面三模式**（默认只 1 个分发器 / `all` 兼容 / `flat` 与 `mcp_server_flat.py` 均 32 个）、`get_version` compact 不膨胀、manifest 新鲜度 |
| `test_search_quality.py` | 检索：中文**字级 bigram** 切词（整段中文不得成为一个 token）、kb_tools 与 rag_search 共用同一套切词、8 条真实问法 BM25 top-3 命中、hits 带 `source`、返回体带 `retrieval`/`degraded`/`quality`、未收录与低置信必须带检索边界提醒、`k` 上限夹紧 |
| `test_platform_matrix.py` | 平台唯一来源：模板/bin_tools 目录真实存在、别名归一、未知平台报错且列出全部支持项、默认平台有效；`test_platform_resolution.py` 另有 **V85x 芯片别名**（v0.27.87）：`V851/V851S/V851S3/V853S`（含 `v851s` 这类大小写混写）必须 `resolve`→`V85X` + `package_key`→`v85x`，且它们**不得**出现在 `package_keys()`/`PACKAGE_KEY_ALIASES`（芯片名不是包键）；`package_catalog` 的 `v85x`/`v85xemmc.chips` 与 `hardware_catalog.V85X`（含 `chipEntries`，无实测的如实 `pending`）都已收齐这 6 个主控 |
| `test_layout_flow.py` | fui pack 确定性 + affectedFiles；**edit_ftu 默认不覆盖原 ftu**（原文件字节不变、留 .bak、产 `.edited.ftu`）；`flythings_ui_visual(action="edit_apply")` dry_run 不写盘 / 默认不 pack / 写盘留 .bak |
| `test_asset_pipeline.py` | html2json **黄金样例**（渐变/圆角/阴影/emoji/loading 必须真出图且 PNG 尺寸 == 控件盒 = v0.27.30 三连 bug 防回归）；已自动转图的效果不许再喊「请切图」；`verify_assets`：分层 `ui/<res>/*.json` 必须扫到、自动生成图尺寸不符 = FAIL、手绘图被拉伸 = 仅提示、缺图 = FAIL、0 页必须 warning；**thumb 自有尺寸子盒**（v0.27.75）：thumb.size 一致 → ok / 31 vs 30 → mismatch FAIL / pressedPic 也核 / 手绘 thumb 只 stretched / 无 size → `skippedNoBox`+warning 不误报 |
| `test_gen_res_aa.py` | **切图抗锯齿档位**（v0.27.75）：FT-008 契约（`rounded_rect` 的 α≥128 轮廓 == 1x 直画，默认行为钉死）/ `rounded_rect_ss` 在强曲率上必须比 FT-008 准一半（对 16x 超采样理想值）/ ss 越高不更差 / 尺寸·四角透明·半径钳制 / 半透明底无暗边（alpha 预乘） |
| `test_html2json_ss.py` | **html2json CSS 出图一律 SS**（v0.27.76）：`SS_DEFAULT`/`_CSS_SS` == 4；渐变药丸与阴影片在 SS 下必须显著优于老路（对 16x 理想值，阴影片比 α 最大偏差）；SS mask 不许引入暗边（边界 RGB 对列内基准）；`crop=False` 「图 == 控件盒」尺寸不受 SS 影响；`border-radius` 解析（`px`/无单位/`%`/多值/无声明默认）+ 端到端 `50%` 真出正圆（覆盖率 ≈ π/4） |
| `test_ui_visual_merge.py` | ui-visual 三合一（`flythings_ui_visual(action)`）：action="list" 参数目录、未知 action / 缺必填参数 = BAD_PARAMS、editor/edit_apply/diff 三路路由、别家 action 的参数必须回 `visualNote`（不静默忽略）、三个旧名回 OP_RENAMED 且 hint 带该用哪个 action |
| `test_toolchain_capability.py` | `fui unpack` 能力声明与实际一致（声称能用必须真解出 json；声称不能用必须真解不出）、json→ftu→json 往返语义等价、无 unpack 且缺 json 源时 edit_ftu 必须明确报错 |
| `test_deps_install_guard.py` | **依赖/install 诊断**（v0.27.83）：代码或 fun 生成的 `generated/*.h` 引用 `base/…` ＋ Manifest 未声明 `base-utility` → `check_project_deps`（`kind="framework"`）/ `validate_project`（`missing_framework_dependency`）必须报出并带可照做的 fix；**声明过或已被传递依赖解析（.fun-lock.json）→ 不许报**；UI 工程无 base 引用也要报、bin 工程（fun.json type=executable）不报；`base/http_*.h`（base-http-client）不算 base-utility；`build_ui_flow`：install 失败 → 顶层 warnings 且**不阻断** build、缺包 → build 前 `check_framework_deps` 直接点明、ninja 的 `base/function.h` 报错被翻译成「依赖未装/缺包」（本文件只盯依赖诊断，离线跑显式传 `with_launch=False`） |
| `test_adb_resolve.py` | **adb 单一入口 + launch 默认推设备**（v0.27.84）：`resolve_adb()` 优先级（env `ADB`/`FLYTHINGS_ADB` > 随包 `tools/adb/adb.exe`（三件齐备）> PATH > 空串+提示）；`FLYTHINGS_ADB` 与 `ADB` 等价；`devices -l` 解析（带 model / 网络设备无 model / unauthorized）；网络设备用 `getprop` 补 model 并判平台；型号表口径（实测三条 → Z21/Z20/V85X 且必须带 `source`；F133/F136 串 **platform 留空 + todo，不许猜**；表里不许出现 IP）；`match_platform` 三态（未知 ≠ 不匹配）；0 台 → `needDeviceInput`+`installHint`（含 ADB 驱动 / USB 调试 / 网络接入）；多设备提示**不替你选机器**；`staleOnDevice` 判据（设备侧字节/md5 vs 本地，无 md5 时退化比字节；三个真机坑：`ls -l` 第 5 列才是字节 / 裁剪 rootfs 的 `wc -c` 返回空 / 缺 md5sum 走随仓 busybox 兜底）；`fun` 多设备硬失败（`more than one device/emulator`）hint 识别；`build_ui_flow` 默认 `with_launch=True`（两处签名）、1 台匹配 → `fun launch -s <serial>`、`with_launch=False` **不探测不推设备** |
| `test_font_autoscan.py` | **字体自动扫描接线 + 缺中文自动投递**（v0.27.86）+ **cmap 硬判据**（v0.27.87）：`flythings_build_ui_flow` **默认**（`font_check='auto'`）就扫字体并把 `common` 档投进工程 `font/`（step 必须在 `fun build` **之前**、返回体写清写入了哪些文件）；`font_check='off'` → **零字体 step 且不写盘**；无设备退化工程侧 self-scan（`note` 写清「未连设备，仅工程侧检查」、**不碰 adb**）；prefs 的 `font` 指向缺失文件 → 报「引用是断的」；`check_project_deps` 默认**只报不投**（`font_apply=True` 才投）+ `fontCheck` 字段（`missingChinese`/`maxFontBytes`/`advisedTier`/`delivered`/`deviceFonts`）+ `fontIssues` 带一键修复命令；阈值/三版清单/投递动作**单一来源** = `device_font_check`（改 `CJK_SIZE_MIN_KB` 结论跟着变）；设备分支（假设备）扫到 `deviceFonts` 并自动投递、且**不重复探 adb**。**硬判据部分**（离线：仓库自带 ttf + fontTools 现场造字体当假设备数据）：基准集 = GB2312 一级 **3755 字**、阈值 90/50 边界、三条 verdict（真字体 100%→`ok` 不投 / 53.3%→`low` 投 / 拉丁 0%→`missing` 投）+ warning 写明覆盖率、缓存命中不再拉（键随体积变即失效）、**超限 12MB / fontTools 不可用 / 拉取失败 → 退回体积判据且 warnings 写明原因**、只探最大字体、临时目录用完即删、部署后复查 `deviceAfterDeploy`（不一致 → 明说 `pack_upgrade` 才生效） |

> 工具 docstring 有字数预算（单 op ≤ 900 字符、全体 ≤ 12,000）——由 `scripts/check_consistency.py` 卡；
> 长尾细节请写进 `knowledge/`（可检索），别塞回 docstring。

## 约定

- 临时工程一律建在系统临时目录（`_util.project()`），用例结束清理，不污染仓库。
- 夹具优先复用 `ui_tools/examples/`（`effects_test.html` = CSS 效果黄金样例、`main.json` = 布局样例）。
- 新增 op / 改平台 / 改破坏性默认值时，**先补用例再改代码**（这些契约正是事故留下的钉子）。
