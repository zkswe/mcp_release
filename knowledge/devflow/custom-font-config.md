# 🔤 自定义字库配置（单字体默认字库替换 / 多字体）

> 2026-09-03 沛哥讲解 + KlipperF133 实测（.prefs font=KaiTi.ttf）、mark_cv201 对照（font/sans.ttf + enable.font.location）。
> 定位：FlyThings 全局默认字体（内置 fzcircle.ttf 思源黑体裁剪版）不满意时，如何换成客户字库。

## ⚠️ 两条路先分清（别混）

| 需求 | 方案 | 入口 |
|------|------|------|
| **全局默认字库替换**（整个 UI 换一种字体，不用代码） | 改 `.prefs` 的 `font` 字段 | `.settings/com.zksw.flythings.easyui.prefs` 或 package.properties 覆盖 |
| **多字体混排**（不同控件不同字体，代码指定） | `enable.font.location=true` + `font/` 目录 + `setFontFamily` | package.properties + 代码 |

## 方案 A：单字体（替换系统默认字库）—— 沛哥 2026-09-03 定规

**通过修改 `.settings/com.zksw.flythings.easyui.prefs` 实现**：给 `easyui.cfg.debug` 和 `easyui.cfg.release` 两份 JSON 都加 `"font"` 字段，指向自定义 ttf。

实测（KlipperF133）：
```
easyui.cfg.debug={..., "font":"/mnt/extsd/ui/KaiTi.ttf", ...}   // debug 走 TF 卡 /mnt/extsd/
easyui.cfg.release={..., "font":"/res/ui/KaiTi.ttf", ...}        // release 走系统 /res/
resolution=800x480
```
- **font 路径 = 设备上的绝对路径**，与同 JSON 的 `resPath` 对应（debug=`/mnt/extsd/ui/`、release=`/res/ui/`）
- 字体文件（.ttf）放工程 `resources/` 目录 → 编译打包后落在设备 ui 资源目录（如 `/res/ui/KaiTi.ttf`）
- **默认模板的 .prefs 没有 font 字段** → 不写 = 系统内置 fzcircle.ttf（思源黑体裁剪）；**写了 = 整个系统默认字体换成你的字库**
- IDE 对应操作：项目属性 → 字体 → 取消默认、导入新 ttf（wiki font_setting.md；**仅支持 ttf 格式**）
- 平台差异（wiki 原文）：Z6S/A33 内置 fzcircle 加快开机，导入字体改名不为 fzcircle 即作扩展；Z11S 无内置直接用打包字库；Z20/Z21/H500S/T113 及后续内置 fzcircle，导入后完全用新字库、命名不限

也可走 package.properties 覆盖层（EasyUI.cfg 里加 font，F133UhaleAlbum 实测）：
```
EasyUI.cfg={"rotateScreen":270, "rotateTouch":270, ..., "font":"/mnt/extsd/resources/font/font.ttf:/res/font/font.ttf"}
```
> ⚠️ 覆盖层 font 用**冒号分隔 debug:release 两个路径**（.prefs 是两份 JSON 各写一个；package.properties 只有一份 JSON，用冒号并写）。该值格式以实际编译工具接受为准，不确定先查知识库/问沛哥。

## 方案 B：多字体（enable.font.location + setFontFamily）

wiki font/font_setting.md 完整流程（mark_cv201 用此法，font/sans.ttf）：
1. 项目属性字体保持默认
2. package.properties 加 `enable.font.location=true`
3. 工程下建 `font/` 目录，字体 ttf 拷贝进去（如 font/sans.ttf）
4. 代码按控件指定：`mTextView1Ptr->setFontFamily("sans")` —— **参数是文件名不带 .ttf 后缀**

注意：
- easyui 依赖包版本需 **2.2.0+**
- 多个字体时按文件名 ASCII 排序，**排最前的作为默认字体**（不 setFontFamily 的控件用它）
- 参考仓库：gitee oszksw/example-multi-font

## 常见坑

- **要全局换字体却去写 setFontFamily** → 用方案 A（改 .prefs font 字段），一行配置全系统生效
- **要不同控件不同字体却只改 .prefs** → 用方案 B（font/ 目录 + setFontFamily）
- .prefs 改 font 后不生效 → ①debug/release 两份都改 ②ttf 文件是否打包进设备对应目录（resPath）③路径是否设备绝对路径
- setFontFamily 参数写成 "sans.ttf" → 错，**只要文件名不含后缀**
- 只支持 ttf，otf/woff 不支持

## 相关

- wiki `font/font_setting.md`（单/多字体官方说明，方案 A 的 IDE 操作 + 方案 B 全流程）
- knowledge `devflow/package-properties-easyui-cfg.md`（package.properties 覆盖层机制、rotateScreen、font 字段表）
