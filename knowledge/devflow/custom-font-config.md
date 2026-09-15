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

### 0.2 设备字体自检（缺中文就自动投递）

已做成工具（随 MCP 发布）：`components/fonts/scripts/device_font_check.py`

```bash
python components/fonts/scripts/device_font_check.py          # 体检（出口码 1 = 缺中文）
python components/fonts/scripts/device_font_check.py --apply \
       --project projects/ZkBlePanel --tier common                       # 缺就投递进工程 font/
```

判定口径（getprop 拿平台信息 + 读 `/etc/font` `/res/font` 等目录里**字体文件的体积**）：

| 最大字体体积 | 判定 | 动作 |
|---|---|---|
| 无字体文件 | 无字库 | 投 `common` |
| **< 200 KB**（几十K / 100多K） | **大概率只有英文** | 投 `common` |
| 200 KB ~ 1 MB | 疑似只有常用字 | 需生僻字才升 `full` |
| > 1 MB | 已有中文 | 不动 |

实测对照（V85X SPINOR）：`/etc/font/fzcircle.ttf` = **20.7 KB**（命中“只有英文”）；投递后 `/res/font/font.ttf` = 2.5 MB。

### 0.3 思源黑体三个版本（已裁好，直接可用）

| 文件 | 体积 | 覆盖 | 何时用 |
|---|---|---|---|
| `zkswe-hans-common.ttf` | 872 KB | GB2312 一级 3755 + 中文标点 + 全角 + ASCII | **默认** |
| `zkswe-hans-full.ttf` | 7.39 MB | CJK 基本区 20902 + 扩展A 6582 | 需生僻字 |
| `zkswe-hans-multi.ttf` | 10.5 MB | 全中文 + 扩展B + 拉丁/希腊/西里尔/假名/谚文 | 多国语言/日韩 |

文件与重裁脚本：`components/fonts/`（`scripts/gen_font_subset.py`，可复现）。
⚠️ 重裁坑：**CN 变体思源黑体没有谚文**（谚文 0 个）→ 多国语言版必须用完整版源（`--src-multi`）。

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
