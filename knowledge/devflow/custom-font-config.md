# 🔤 自定义字库（fun build/launch 流程，非 IDE）— 权威规则

> 2026-09-03 沛哥定规。**fun 流程换字库以本条为准**；font_setting.md 是 IDE 视角，AI 引导用户时禁止先去翻 IDE 项目属性那套。
> ⚠️ 修正记录：v0.13.0 曾按 KlipperF133 案例写入"改 .prefs 的 font 字段"方案——那是 IDE 工程视角，**fun 流程不适用、不需要**，以本条为准。

## ✅ 标准流程（用户说"换字库/换字体"直接照做，禁止绕道 IDE 属性）

1. **项目根目录建 `font/` 文件夹，把 ttf 拷入**（仅支持 ttf 格式）
2. **package.properties 加 `enable.font.location=true`**（新项目模板已内置，没有才补）
3. **单字体 → 自动成为全局默认字体，代码零改动**
   **多字体 → 按文件名 ASCII 排序，最靠前为默认；个别控件用 `setFontFamily("文件名不含后缀")` 指定**（easyui ≥ 2.2.0）
4. 完成。不需要动 .prefs、不需要 IDE 项目属性、不需要写代码

## 机制要点

- **字库是运行时资源，不参与编译**，`fun launch` 随资源一起推送
- 平台：**Z20 / Z21 / H500S / T113 / V85X 及后续平台系统内置 fzcircle.ttf**（思源黑体裁剪版）；**项目 font/ 存在字体后，完全使用项目字体**
- 字库不含 emoji / 特殊符号（■ ● ⌫ ℃ ▲ ▼ 等）→ 布局文本只用**汉字 + ASCII + 基础符号**（/ % # - _ 空格），图标一律转 PNG
- 实测样例：mark_cv201（CV201_PND / CV201_PND_1024_600）根目录 `font/sans.ttf` + package.properties `enable.font.location=true` = fun 流程标准用法

## ⚠️ AI 引导规则（沛哥 2026-09-03 定规）

- 用户说"换库" → **直接按上述 4 步执行**，不要先翻 IDE 项目属性那套
- wiki `font/font_setting.md` 是 **IDE 视角**（单字体走项目属性导入、多字体 setFontFamily），fun 流程**以本条为准**
- "改 .prefs font 字段"（v0.13 记录，KlipperF133 案例）属 IDE 工程做法，fun 流程项目不要用

## 常见坑

- 换 ttf 后不生效 → ①`font/` 目录建在**项目根**、文件名是否 .ttf ②package.properties 有没有 `enable.font.location=true` ③`fun launch` 是否重新推了资源（字库随资源推送）
- 多字体没按预期默认 → ASCII 排序理解错（排最前的是默认）；个别控件要显式 `setFontFamily`
- `setFontFamily` 参数写 "xxx.ttf" → 错，**只要文件名、不含 .ttf 后缀**
- 字库要带 emoji/特殊符号 → 做不到（裁剪字库），图标转 PNG、文本只用基础符号
- 把 IDE 那套（.prefs font 字段）用到 fun 流程项目 → 方向错误，fun 项目看 font/ + enable.font.location

## 设备字库自检 && 思源黑体三版（2026-09-13 新增，真机实测）

> 背景：设备自带字库常是裁剪字库（甚至只有英文）→ **界面汉字全变方块**。
> 特别是**固化/升级会整体替换目标机的 `/res`**，原 app 带的字体会一并消失（真机踩过）。

### 0.1 机制澄清（重要，避免走弯路）

- **项目 `font/` 里的字体会被工具链自动写进 `EasyUI.cfg` 的 `font` 键**（`fun launch` 与 `fun pack` 都做：
  `internal/launch/launcher.go` / `internal/packaging/packaging.go` 里 `cfg.Font = join(项目 font/*.ttf → /res/font/...)`）。
  → **不要为“让字体生效”去手改 `.settings/com.zksw.flythings.easyui.prefs` 的 `font` 键**（多余；实测去掉后照样正常）。
  （注：本文件之前引用的 v0.13.0“改 .prefs font 字段”已在本条里显式排除；那份是 IDE 视角。）
- `package.properties: enable.font.location=true` = 启用工程内字库（配合多字体 `setFontFamily`）；单字体时就是全局默认字体。
- 本机实测：app 工程放 `font/font.ttf` + `enable.font.location=true`，固化后 `/res/etc/EasyUI.cfg` 自动出现
  `"font": "/res/font/font.ttf"`，汉字正常显示 → **这就是 fun 流程的标准姿势**。

### 0.2 设备字体自检（缺中文就自动投递）—— v0.27.86 接成自动动作，v0.27.87 判定升级为**硬判据**

**默认口径（先记这个，别一上来就自己裁字库）**：

- **自动**：`flythings_build_ui_flow` 每次都会做字体体检 —— **有设备**就扫设备
  （`/etc/font`、`/res/font`、`/system/font`、`/usr/share/fonts` 里字体体积）；**没设备**就退化为
  工程侧 self-scan（prefs 的 `font` 指向在不在工程 `font/`、`font/` 里有没有可用字体）。
  判定**缺中文**就**默认把 `common` 档思源黑体投进工程 `font/`**（并在 build **之前**完成，
  本次构建/推送的产物里就有它），返回体 `fontCheck` 写清 `missingChinese`、`maxFontBytes`、
  `advisedTier`、`delivered`（投没投/写了哪些文件）、`deviceFonts`（扫到的路径+体积）。
- **判定用硬判据（v0.27.87，钟工拍板：比体积判据好）**：挑设备上**最大的那个** ttf/ttc →
  **拉回本机**（临时目录，用完即删）→ `fontTools.ttLib` 读它 cmap → 以 **GB2312 一级 3755 字**
  为基准算覆盖率 `cmapCoverageGB2312L1`：

| cmap 覆盖率（GB2312 一级） | verdict | 动作 |
|---|---|---|
| **≥ 90%** | `ok` | 中文字库可用，**不投递** |
| **50–90%** | `low` | **投递** + warning 写明覆盖率 |
| **< 50%** | `missing` | **投递** |

- **兜底（不许静默）**：拉取体积 **> 12 MB**（`PROBE_MAX_BYTES`）、`fontTools` 不可用、
  拉取失败、cmap 解析失败 → **退回体积判据**（`source="size"`，原因写进 `warnings`），
  此时 `verdict` 用旧口径（`no_font`/`no_cjk`/`partial_cjk`/`has_cjk`）。
- **成本控制**：结论按 `设备 serial + 目录/文件名 + 体积 + ls 时间` 缓存到 `~/.fun/font-probe.json`
  （`FLYTHINGS_FONT_CACHE` 可改），命中就不重复拉；返回体 `probe.cacheHit` 能看出是不是缓存。
- **部署后复查**（v0.27.87）：`fun launch` 成功后且本次投递过字体 → `fontCheck.deviceAfterDeploy`
  回看「设备侧字库现状 + 与工程投递是否一致」；字库要 `fun pack_upgrade` 固化才变，
  所以这里如实说「需固化才生效」，**不白花一次拉取**（与应用侧 `staleOnDevice` 凑成一个闭环）。
- **档位**：默认 **`common`**（872 KB，GB2312 一级 3755 + 中文标点 + ASCII）；
  **要生僻字换 `full`**（7.39 MB，CJK 20902 + 扩展A）；**多语言/日韩换 `multi`**（10.5 MB）——
  传 `flythings_build_ui_flow(font_tier='full'|'multi')` 即换。**font tier 就这么选，不用改代码。**
- **「自己裁字库」只在要更小体积 / 自定义字符集时才需要**（§4）；日常用现成三版即可。
- **关掉**：`font_check='off'` —— 不做字体体检/投递（连 step 都不加）；
- **只要结论、不想动工程**：`flythings_check_project_deps`（字段 `fontCheck` / `fontIssues`，
  **默认只报不投** + 给一键修复命令；`font_apply=True` 才真投；传 `device='<ip>:5555'` 才扫设备字体）；
- **命令行兜底**（不走 MCP 时；默认也做硬判据，`--no-probe` 可退回体积判据）：

```bash
python components/fonts/scripts/device_font_check.py --apply --project <工程根> --tier common
```

判定口径（getprop 拿平台信息 + 读 `/etc/font` `/res/font` 等目录里**字体文件的体积**；
阈值与三版清单是**单一来源** = `components/fonts/scripts/device_font_check.py`，不许另写一套）：

| 最大字体体积（**仅作兑底**） | 判定 | 动作 |
|---|---|---|
| 无字体文件 | 无字库 | 投 `common` |
| **< 200 KB**（几十K / 100多K） | **大概率只有英文** | 投 `common` |
| 200 KB ~ 1 MB | 疑似只有常用字 | 需生僻字才升 `full` |
| > 1 MB | 已有中文 | 不动 |

实测对照（V85X SPINOR）：`/etc/font/fzcircle.ttf` = **20.7 KB**（命中“只有英文”）；投递后 `/res/font/font.ttf` = 2.5 MB。

**症状 → 一步**：界面汉字全变方块 → 别手搜着找字体文件，直接 `flythings_build_ui_flow`
（默认就会扫+投触发）；想先看结论就先 `flythings_check_project_deps` 看 `fontCheck.advisedTier`。
检索词：设备字体自检 / 自动扫描字体 / 缺中文字库 / font tier / 投递字体 / 汉字变方块 /
cmap 覆盖率 / GB2312 一级 / 硬判据 / font-probe 缓存。

### 0.2.1 真机实测（v0.27.86，Z21 整机、网络 adb）

| 场景 | 输入 | 返回体关键字段 | 结果 |
|---|---|---|---|
| **设备侧本就够** | `flythings_build_ui_flow(project_root)`（默认参数） | `fontCheck.mode=device`、`verdict=partial_cjk`、`maxFontBytes=892848`（871.9 KB）、`missingChinese=false`、`delivered.applied=false`、`deviceFonts` 5 条（`/res/font/zkswe-hans-common.ttf` 871.9KB、`/etc/font/fzcircle.ttf` 818.6KB、Poppins×3 ≈155KB）、`warnings=[]` | **未触发投递**（设备已有中文）；build/launch 照常（`launched=true`、设备侧 ftu/so md5 与本地一致） |
| **可关** | `font_check='off'` | steps 里**没有** `check_font`、`fontCheck.enabled=false`、`warnings=[]` | 建编译照常，零字体动作 |
| **无设备/工程侧缺字体** | `device='192.0.2.9:5555'`（不存在的 serial） | `mode=project`、`note=未连设备，仅工程侧检查…`、`verdict=project_no_font`、`missingChinese=true`、`delivered.applied=true`、`files=['font/zkswe-hans-common.ttf']`；warning 两条（设备不在线→跳过设备侧 + 已自动投递） | **自动投递生效**；`/tmp/font/zkswe-hans-common.ttf` = 892,848 B 跟工程一致 |

**投递真的生效的证据**（关键，防“投了个没用的字体”）：投递后跑 `fun launch`，设备侧
`/tmp/EasyUI.cfg` 自动出现 `"font": "/tmp/font/zkswe-hans-common.ttf"`（**由工具链从工程 `font/*.ttf`
生成**，不用手改 prefs），且 `/tmp/font/` 下的字体字节与工程一致。

> 口径补丁（本机实测）：**工程 `.settings` prefs 里没有 `font` 键时，投递不去凭空造这个键**（改了也是多余）；
> 有 `font` 键则就指向投递进去的那份（v0.27.86 顺手修了 `device_font_check.apply_to_project`
> 的单引号/转义不匹配 bug：原正则只认 `"font":"..."`，而真 prefs 是转义写法 `"font"\:"..."` → 以前改了等于没改）。

### 0.3 思源黑体三个版本（已裁好，直接可用）

| 文件 | 体积 | 覆盖 | 何时用 |
|---|---|---|---|
| `zkswe-hans-common.ttf` | 872 KB | GB2312 一级 3755 + 中文标点 + 全角 + ASCII | **默认** |
| `zkswe-hans-full.ttf` | 7.39 MB | CJK 基本区 20902 + 扩展A 6582 | 需生僻字 |
| `zkswe-hans-multi.ttf` | 10.5 MB | 全中文 + 扩展B + 拉丁/希腊/西里尔/假名/谚文 | 多国语言/日韩 |

文件与重裁脚本：`components/fonts/`（`scripts/gen_font_subset.py`，可复现）。
⚠️ 重裁坑：**CN 变体思源黑体没有谚文**（谚文 0 个）→ 多国语言版必须用完整版源（`--src-multi`）。

### 0.2.2 真机实测（v0.27.87，V85X SPINOR 整机、网络 adb）

> 环境：本机 adb = 随包 `tools/adb/adb.exe`；**多设备在线时 `fun launch` 硬失败**（fun 的 Go adb 用旧式
> `host:transport <serial>` 空格写——详见 `cli-fun-toolchain.md` §7），本次实测前先 `adb disconnect` 另两台、
> 跑完再 `adb connect` 加回；设备报 `ro.product.model=Zkswe_V85X_SPINOR`（480×800）。
> （本段不写具体内网地址：隐私扫描不允许——设备用 `device='<serial|IP:5555>'` 现查现传。）

| 场景 | 关键字段（实测值） | 结果 |
|---|---|---|
| **设备字库够**（首次探测） | `mode=device`、`source=cmap`、`cmapCoverageGB2312L1=100.0`（3755/3755）、`verdict=ok`、`checkedFont=/res/font/pocketgame.ttf`（1,093,608 B = 1068 KB）、`missingChinese=false`、`delivered.applied=false`、`warnings=[]` | **未投递**；拉回 1 MB 字体耗时 **1294 ms**（`probe.elapsedMs`，正常） |
| **缓存命中**（同设备立即再跑） | `probe.cacheHit=true`、`elapsedMs=6`、`pulledBytes=0`、`probedAt=2026-09-17 20:21:32` | **没再拉**（缓存键=serial+文件+体积+ls 时间，落 `~/.fun/font-probe.json`） |
| **设备字库只有零星中文** | `checkedFont=/res/font/game.ttf`（81,188 B = 79.3 KB）、`cmapCoverageGB2312L1=8.0`（302/3755）、`verdict=missing`、`missingChinese=true` | 投递 `common` 进工程 `font/`（81 KB 的字体里面**真只有 302 个一级汉字**——数字比体积说明问题） |
| **完整构建流程**（build_ui_flow，单设备在线） | `ok=true`、`launched=true`、`pushed=true`、`staleOnDevice=false`；`check_font` step 带 `source=cmap`/`cmapCoverageGB2312L1=8.0`/`checkedFont`；`delivered=[font/zkswe-hans-common.ttf]`；`deviceAfterDeploy.consistent=false` + note「需 `pack_upgrade` 固化才生效」 | 字体投递在 `fun build` **之前**；launch 后 `deviceSync` ftu/so md5 与本地一致；**字库待固化**与应用陈旧分开报 |
| **V851S 入参** | `platforms.resolve('V851S') → {canonical: V85X, packageKey: v85x, buildable: true, template: HelloWord_V85X}`（`v851s3`/`V853S`/`V851` 同） | 修前是 `None`（被当未知平台）且 `package_key` 回 `v851s`（catalog 里不存在 → 查包必空） |

> ⚠️ 实测中发现的一个**不属本轮改动**的现场变化，记下来供排查：同一块 V85X 板子
> `/res/font` 的内容在本次会话中从 `pocketgame.ttf`（1 MB）变成了 `game.ttf`（81 KB，一级汉字仅 302 个）。
> 我们的流程只向 `/tmp/font` 推 app 资源（`fun launch` 不碰 `/res`），且本机与仓库内**没有** `game.ttf`
> 这个文件 → 应是另一路会话/人推上去的；结论：**这块板子当前 /res/font 的中文覆盖只有 8%**，
> 拿它当「设备字库够」基准之前先重跑一次体检（现在 `verdict` 就是 `missing`）。

### 0.4 真机验收

汉字正常 = 无方块；用 `flythings_device_screenshot` 看图确认（不要手搓 fb0）。

## ⭐ 设计稿字体对齐（2026-09-15 沛哥定规：**照设计稿做 UI 必须先换字体**）

> **背景（沛哥原话）**："字体应该更新为设计一样的。这个应该说明到 MCP 里面，不然做出来的效果跟实际效果差异很大。"
> 症状：布局坐标全对，但**字形/字重与设计稿差一大截**（设计稿是几何无衬线粗体，设备默认是普通细体）——这是"还原度"最大的单项落差，比坐标误差显眼得多。

### A. 结论（一句）
**动手还原设计稿（尤其 AI 出的高保真渲染图）前，先把设计字体投进工程 `font/`，再去做布局；字体是地基不是收尾。**

### B. 字体怎么选（本机现成资源）

| 用途 | 文件 | 来源 |
|---|---|---|
| **中文（默认字体必须选它）** | `zkswe-hans-common.ttf`（872 KB，思源黑体常用字 3755 + 标点 + ASCII） | `components/fonts/fonts/` |
| 中文（生僻字/多语言） | `zkswe-hans-full.ttf`（7.4 MB）/ `zkswe-hans-multi.ttf`（10.5 MB） | 同上 |
| 拉丁 / 数字（几何无衬线，接近设计稿数字） | `Poppins-SemiBold.ttf` / `Poppins-Bold.ttf`（GILROY 等几何体同理） | `projects/inSightOS3/app/resources/fonts/` 等 |

### C. 落地 4 步（fun 流程）
1. `<项目>/font/` 放 ttf（**文件名决定默认**，见 §D）
2. `package.properties`：`enable.font.location=true`
3. `fun build -p <平台>` + `fun launch`（字库随资源推送，`/tmp/font/` 或 `/res/font/`）
4. **真机截图 vs 设计图对照验收**（`flythings_device_screenshot` + 视觉对比）；不合就换字重再验

### D. ⚠️ 多字体排序铁律（本机 2026-09-15 实测踩坑）
- 多字体按**文件名 ASCII 升序，最靠前的 = 全局默认字体**。
- **默认字体必须是含中文的那个**：把 2.5 MB 的纯中文名放前面没事，但若让 **Poppins 排在前面当默认 → 汉字全部变方框**；反过来若默认是 CJK 体，拉丁/数字也会用它（字形尚可，但不如几何体贴近设计稿）。
- 想"中文用思源、数字用 Poppins"：**默认放大写靠前的含中文体**（如 `Han-Sans-common.ttf`），再对个别控件 `setFontFamily("Poppins-SemiBold")`（easyui ≥ 2.2.0，当前模板 2.6.0 支持；参数**不含 .ttf 后缀**）。
- 文件名只是资源名，可重命名以控制排序（例：`Han-Sans-common.ttf` < `Poppins-SemiBold.ttf`）。

### E. ⚠️ 低内存平台（Z21 36MB RAM / tmpfs 13.9MB）字体坑（实测）
- 投 **2.5 MB 级中文字体**（如 HarmonyOS_Sans_SC_Medium）后应用**黑屏 + 反复重启**；换成 872 KB 的 `zkswe-hans-common.ttf` 立即恢复。→ **Z21/Z20 优先用 `common` 档思源黑体**，别上 MB 级大字体。
- `fun launch` 每换一次字体就往 `/tmp/font/` 写一份，**旧字体不自动删**：堆到 tmpfs 使用率 ~72%（剩 3.9 MB）时应用起不来。→ 上传前 `adb shell rm -f /tmp/font/<旧字体>`，`df /tmp` 确认余量。
- 排查口径：屏幕全黑 + logcat 里 zkgui 反复换 pid（重启循环）= 资源/内存问题，先查 `/tmp` 余量与字体体积，别急着改 UI。

### F. 字号也要按设计稿给足
- 设计稿数字常是**粗体大号**；设备换了字重后同样的 `fontSize` 观感会偏细/偏窄 → 按设计稿实测字号给值，塞不下就**拆行/放宽盒子**，不要为塞下而缩字号（缩了就没有设计稿的层级感）。

## 相关

- MEMORY.md 铁律「设备字库是裁剪字库」（emoji/特殊符号不支持）
- wiki `font/font_setting.md`（IDE 视角，仅参考）
- knowledge `devflow/package-properties-easyui-cfg.md`（package.properties 覆盖层机制）
