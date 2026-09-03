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

## 相关

- MEMORY.md 铁律「设备字库是裁剪字库」（emoji/特殊符号不支持）
- wiki `font/font_setting.md`（IDE 视角，仅参考）
- knowledge `devflow/package-properties-easyui-cfg.md`（package.properties 覆盖层机制）
