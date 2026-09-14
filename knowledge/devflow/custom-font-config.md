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

## 相关

- MEMORY.md 铁律「设备字库是裁剪字库」（emoji/特殊符号不支持）
- wiki `font/font_setting.md`（IDE 视角，仅参考）
- knowledge `devflow/package-properties-easyui-cfg.md`（package.properties 覆盖层机制）
