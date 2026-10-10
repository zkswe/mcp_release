---
id: devflow-i18n-multilang
title: 多国语言（i18n）机制与落地 —— .tr / @key / setTextTr / 切语言 / .tr→json 部署链路
category: devflow
status: review
confidence: offline
verified_at: 2026-10-05
stale_days: 180
origin: total
source: 2026-10-03 收录：官方文档 developer.flythings.cn/zh-hans/i18n.html（权威口径）+ 逐行读 i18n_tools.py（30KB，6 个 op 的实现）+ 该模块自带的历史实测记录（2026-08-29 SampleUI-New / 2026-09-08 V553 真机 / 2026-09-10 反汇编 v85x easyui 2.9.0 libeasyui.so）；2026-10-05 补：需求方提供真实工程 3 个 `.tr`（`templates/DemoControls_V85X/i18n/`）后做的离线验收（三语对齐 + json 字节格式 + 非 ASCII 不转义）+ **换行写法统一为 `&#x000A;`**（需求方拍板：不要两个说法；代码/文档/用例同批改）+ `fsc.exe`/`fui.exe` 命令面实测（官方工具链无 tr→json 能力面）
needs_evidence: true
platforms: []
tags: [多国语言, i18n, 翻译, 语言切换, tr 文件, key 对齐, 缺 key, 乱码, 字库, locales, 文案, setTextTr, getValue, 本地化, 内置界面, 换行]
evidence:
  - cmd: python -m unittest discover -s tests -p "test_i18n_tools.py"
    expect_rc: 0
    note: 钉住 .tr→json 的换行还原、json 字节格式、@key 收集、scan 对齐检查（本页机制的可执行判据）
---
# 多国语言（i18n）机制与落地

> 检索导引：问「怎么做多语言 / 翻译文件放哪 / 界面文案怎么跟着语言变 / 加了语言不生效 /
> 切了语言界面没变 / 设备显示 not found value / 文案乱码或白块 / key 对不齐 / 缺翻译怎么找 /
> @key 是什么 / setTextTr 怎么用 / 语言切换页在哪 / .tr 和 .json 什么关系」→ 本文。
> 文字控件的**字段语义**（caption 显示名 vs text 内容）→ `knowledge/uicontrols/*-fields.md`；
> 字库能不能显示这些字符 → `knowledge/devflow/custom-font-config.md` 与 `components/fonts/platforms.md`。

## 0. 来源与可信度（**先读**）

本文内容 = **读 `i18n_tools.py` 的实现**（6 个 op 全读）+ **该模块自己记录的历史实测**：

| 记录 | 日期 | 性质 |
|---|---|---|
| **官方文档 `developer.flythings.cn/zh-hans/i18n.html`** | 2026-10-03 取回 | **权威口径**：`.tr` 是 XML、别名唯一、换行用 `&#x000A;`、加语言拷 `.tr` 改名、**内置界面翻译必须并入**、样例 = `TranslationDemo` |
| 官方 i18n 文档 + SampleUI-New 实测 | 2026-08-29 | 机制口径（`.tr` 格式、三段式文件名、`@key`/`setTextTr`、切语言） |
| V553 项目真机 | 2026-09-08 | 设备端**实际加载 `i18n/<lang>.json`**、`fsc launch` **不推** i18n |
| 反汇编 v85x easyui 2.9.0 `libeasyui.so` | 2026-09-10 | **换行转义**的底层依据（`getValue` 不还原反斜杠；`zk_gdi_draw_text` 按 `0x0A` 切行） |

⚠️ **我自己没有上机复验过** —— 所以 `confidence: offline`、`needs_evidence: true`。
能**离线**验的部分已经钉成可执行判据（见 front-matter 的 `evidence`：
`.tr→json` 的换行还原、json 字节格式、`@key` 收集、scan 对齐检查）。
**真机相关的那几条（`/tmp/tr/` 路径、`fsc launch` 不推、not found value）沿用上表记录，本文不冒充实测。**
⚠️ **换行写法只有一条**（`&#x000A;`，见 §6）；此前"两种写法并列"的表述已作废。

## 1. 一分钟速查

| 问题 | 答案 |
|---|---|
| 翻译文件放哪 | 项目根 **`i18n/<语言>.tr`**（Android `strings.xml` 同款 XML） |
| 文件名怎么写 | **三段式 `xx_XX-语言名.tr`**（语言代号 2 小写 + 地区 2 大写 + 显示名），如 `fr_FR-法语.tr` |
| 界面文案怎么写 | 布局 json 的 `text` 写 **`"@key"`**（带 @） |
| 代码里怎么写 | `setTextTr("key")`（**不带 @**）；拼接取词 `LANGUAGEMANAGER->getValue("key")` |
| 怎么切语言 | `EASYUICONTEXT->updateLocalesCode("zh_CN")`；或跳系统页 `openActivity("LanguageSettingActivity")` |
| 改完怎么让设备看到 | **必须 `flythings_i18n`（`action=to_json`）**（默认带 push）—— **`fsc launch` 不推 i18n** |
| 默认有哪几种 | `zh_CN` / `en_US` / `ja_JP` / `ko_KR` |
| 换行怎么写 | **`.tr` 里写 XML 字符引用 `&#x000A;`**（唯一写法，2026-10-05 定案）；json 里必须是**真换行 `0x0A`**（§6） |
| ⚠️ 文件名带显示名时要传全名 | 真实工程是 `zh_CN-简体中文.tr` 这种三段式 ⇒ 调 `add_language` / `export` 的 `lang`/`base_lang` **要传三段式全名**（`zh_CN-简体中文`），传 `zh_CN` 会失败或返回空（§10） |

## 2. 文件格式（`.tr`）

```xml
<?xml version="1.0" encoding="utf-8"?>
<resources>
    <string name="about_me">关于我们</string>
</resources>
```

- 位置固定：`<项目>/i18n/`（工具按此目录发现语言：`_list_tr_files`）。
  官方口径：**IDE 新建向导**建出该目录并生成默认 `.tr`；**编译时把 `.tr` 转成 json**（设备实际加载 json）。
- **语言标识 = 文件名去掉 `.tr`**，可以是 `zh_CN`，也可以是 `fr_FR-法语`；
  显示名取 `-` 之后那段（`fr_FR-法语` → `法语`；`zh_CN` → `zh_CN`），用于语言切换列表。
- ⚠️ 官方明确：**请勿随意修改文件名**（文件名就是语言标识）。
- ⚠️ **同一文件内别名（`name`）不能重复**；各语言之间要用**相同的 `name`**（对齐是关键，见 §9-6）。
- `.tr` 是 **XML 不是 key=value**；写 `&`/`<` 要按 XML 转义（`&amp;` 等）。
- **换行**：官方写法是 **XML 字符引用 `&#x000A;`**（`0x0A` = LF），见 §6。

## 3. 两条引用方式（**带不带 `@` 是最常错的地方**）

| 在哪 | 写法 | 说明 |
|---|---|---|
| 布局 `ui/*.json` | `"text": "@about_me"` | **带 `@`**；工具用正则 `"text"\s*:\s*"@([^"]+)"` 收集（`_collect_layout_keys`），`flythings_i18n(action="scan")` 靠它算「布局引用了但 .tr 里没有」 |
| 代码 | `setTextTr("about_me")` | **不带 `@`** |
| 代码拼接 | `LANGUAGEMANAGER->getValue("about_me")` | 来自 easyui 包 `manager/LanguageManager.h`；**运行时**取当前语言的值 |

## 4. 切语言：两种 API 差别很大

| API | 行为 |
|---|---|
| `EASYUICONTEXT->updateLocalesCode("zh_CN")` | ✅ **立即刷新已打开页面**的文案（内部 = `LanguageManager::setCurrentCode` + **遍历 `ActivityStack` 调各 `BaseApp::updateLocales`**） |
| `LANGUAGEMANAGER->setCurrentCode("zh_CN")` | ❌ **不刷新在屏控件文本** —— 用户要「退出重进」才看到新语言 |
| `EASYUICONTEXT->openActivity("LanguageSettingActivity")` | 跳系统自带的语言设置页 |

> 现象对照：客户说「切了语言，有些地方没变」→ 先问是不是只调了 `setCurrentCode`。

## 5. ⚠️ 部署链路：设备读的是 **json**，不是 `.tr`（最容易踩的一环）

1. **设备端 zkgui 实际加载 `i18n/<lang>.json`**（不是 `.tr`），DEBUG 模式路径 **`/tmp/tr/<lang>.json`**（2026-09-08 真机记录）。
2. **`fsc launch` 只推 `ftu / images / font / lib / cfg`，不推 i18n 的 `.tr`/`.json`** →
   **改完翻译（`import` / `add_language` / `refactor`）后必须调 `flythings_i18n`（`action=to_json`）**，
   否则设备仍跑**旧翻译**，现象是 logcat 刷 **`not found value`**。
3. **生产固件**把 json 打包进 `/res/` → 这时用 `push=False` 只生成不推送。
4. ⚠️ 生成的 `i18n/<lang>.json` 与设备端加载格式**逐字节一致**：
   **tab 制表 + 冒号后无空格 + 文件末尾无空行**（`_dump_json` 的落盘格式，设备按此读）。真源：`op_spec.json` 的 `flythings_i18n（action=to_json）.rules`
   → **手改这个 json 就会破坏字节一致性**；要改文案改 `.tr` 再重新转，别改 json。
5. ⚠️ **加了自定义语言，必须把「内置界面翻译」并进去**（**官方硬要求，容易漏**）：
   官方原文 ——「需将[内置界面翻译文本](https://docs.flythings.cn/src/zh_CN.tr)添加到自定义语言里边，
   并进行相应的翻译，当切换到对应的语言后**内置界面才能正常显示文本**」。
   → 少这一步的现象：**自己页面的文案正常，但系统内置界面（如语言设置页自身、提示框）文案异常**。
   MCP 侧的对应动作：把该文件的内容 `import` 进新语言（或先 `add_language` 再合并）。
6. **两条工作流别混**：官方是 **IDE 编译**把 `.tr` 转 json；MCP 工作流用 `flythings_i18n`（`action=to_json`）
   转 + push。**只要你改了 `.tr`，就得有一步转 json**（走哪条都行，但别以为改了 `.tr` 就完事）。

## 6. 换行：**`.tr` 写 XML 字符引用 `&#x000A;`**（唯一写法），json 里必须是**真换行**

**官方口径（唯一）**——`developer.flythings.cn/zh-hans/i18n.html` 原文：

> 如果希望在字符串中换行，则用`&#x000A;`转义，如下：

```xml
<?xml version="1.0" encoding="utf-8"?>
<resources>
    <string name="new_line_test">第一行&#x000A;第二行</string>
</resources>
```

**2026-10-05 需求方拍板：不要两个说法，全部统一 `&#x000A;`。** 代码（`i18n_tools.py`）、本页、用例**同批**改完 —— 本页此前"两种写法并列/待确认"的表述**全部作废**。

**读写行为（改后，实测）**：

- **写**（`import` / `add_language` / `refactor` 落 `.tr`）：**一律写字符引用** —— `\n`→`&#x000A;`、`\t`→`&#x0009;`、`\r`→`&#x000D;`（`_escape_tr`）。
  反斜杠**不再转义**（它在 XML 里就是普通字符，`C:\new` 能原样保留）。
- **读**：字符引用由 XML 解析器解开；**额外容忍**历史字面 `\n`/`\t`/`\\`（旧版本工具写出的文件）→ **老工程零迁移**。
  但**写回会把它们归一成字符引用** —— 这是有意的形式归一，不是两种写法并存。
- **转 json**（`action="to_json"`）：两种来源落盘字节**完全一致**，均为真换行（见下）。⇒ **换写法不改变设备行为**。

**设备侧的硬要求**：生成的 json 里必须是**真实换行符 `0x0A`**。
底层依据（2026-09-10 反汇编 v85x easyui 2.9.0 `libeasyui.so`）：
`LanguageManager::getValue` 直接 `Json::Value::asString()` 返回，**不做反斜杠还原**；
分行发生在 **`zk_gdi_draw_text`**，按字节 `0x0A` 切行（`strchr(p, '\n')`）。
⇒ **json 里留字面 `\n`（JSON 要写成 `\\n`），设备原样显示「\n」这几个字符，不换行。**

**2026-10-05 真文件实测**（对象 = `templates/DemoControls_V85X/i18n/` 的 3 个真实 `.tr`）：

| 观测 | 结果 |
|---|---|
| 三个语言解析 | `en_US-ENGLISH` / `ru_RU-Русский` / `zh_CN-简体中文`，各 1 个 key `hello_world`，`keyAligned=true` |
| 落盘 json 字节 | `b'{\n\t"hello_world":"Hello world!"\n}'` —— **tab 制表 + 冒号后无空格 + 末尾无空行**，`0x0D` 一个都没有 |
| 非 ASCII 是否被转义 | **不转义**：俄文 `Привет, мир!` 与中文 `你好,世界!` 均原样 UTF-8（`\xd0\x9f…` / `\xe4\xbd\xa0…`） |
| 字符引用 → json | `&#x000A;` 经 to_json 落成 json 里的真 `0x0A`（`tests/test_i18n_tools.py::test_official_xml_char_reference_form`） |

- 本地同源脚本（不依赖 MCP）：`<项目>/tools/tr2json.py`。

## 7. 前提：字库得能显示这些字符

- 多语言需要**字体支持**；默认是**精简字库**，建议用 `font_cut_tool` 自定义。
- ⚠️ **精简字库常缺 `&`、`@` 等 ASCII 符号** → **文案里禁用**（用 `and` / 空格代替），
  否则设备上该字符**空白或乱码**。改完文案建议核对字库 `cmap` 覆盖。
- 细化口径见 `knowledge/devflow/custom-font-config.md`、`components/fonts/platforms.md`。

## 8. 一个入口六个动作（从零到上机的工具链）

> 2026-10-05 起：原来的六个 op（scan / export / import / add_language / refactor / to_json）**收敛成单入口 `flythings_i18n`**，用 `action` 选一步 —— 认知面只留一个名字，细节按需拉契约（`describe section=…`）或读本页。下表即是 `action` 与用途的对应。

| op | 干什么 | 关键返回/参数 |
|---|---|---|
| `flythings_i18n`（`action=scan`） | **诊断现状**：语言清单、key 对齐、布局引用完整性 | `languages` / `languageDisplayNames` / `keysPerLanguage` / `keyAligned` / `missingKeysPerLanguage` / `layoutRefCount` / `layoutRefMissingInTr` / `trKeysUnusedByLayout`；无 i18n 时回 `hasI18n:false` + 指路 `export` |
| `flythings_i18n`（`action=export`） | 导出**待翻译清单**（key → 基础语言原文）+ 专业翻译提示 | `lang`（默认 `zh_CN`）/ `keys`（逗号分隔子集，缺省全部）/ `context`（项目语境描述）；回 `translationGuide` |
| `flythings_i18n`（`action=add_language`） | 加一种新语言 | `lang`（如 `fr_FR`）、`lang_name`（如 `法语`，显示在切换列表）、`base_lang`（默认 `zh_CN`）。官方做法是**拷贝现有 `.tr` 改名 `xx_XX-XXX.tr`**：语言/地区代号**可任取**（两个小写 + 两个大写），只要多个文件的前两段不冲突即可。⚠️ 加完还要并**内置界面翻译**（§5-5） |
| `flythings_i18n`（`action=import`） | 把译文**写回** `.tr` | `translations`（JSON 对象 `{key: 文本}`）、`merge`（True 合并 / False 整体覆盖） |
| `flythings_i18n`（`action=refactor`） | 把布局里**写死的中文**换成 `@key`（多语言改造） | `dry_run`（**默认 True 只预览**）；key 由 caption 生成（非 `[A-Za-z0-9_]` 换成 `_`），同名冲突自动加后缀；**纯数字/时间占位自动跳过**；⚠️ 只在确认布局文本都是界面文案时用 |
| `flythings_i18n`（`action=to_json`） | `.tr` → 设备格式 `.json` + 推送 | `langs`（逗号分隔，默认全部；支持三段式）/ `push`（默认 True）/ `device`（多设备必须指定）；回 `converted[] / pushed[] / adbStatus / device / nextHint`（⚠️ **没有 `skipped[]`** —— 旧文档与 docstring 写错过，以实现为准） |

**标准流程**：`refactor`（先 `dry_run` 预览）或手写 `@key` → `export` 拿待翻译清单 →
（AI 结合语境专业翻译）→ `import` 写回 → `scan` 体检对齐 → `to_json`（带 push）→
设备上切语言验证。

## 9. 硬约束与铁律

1. ⚠️ **改完翻译不调 `flythings_i18n(action="to_json")` = 设备跑旧翻译**（`fsc launch` 不推 i18n）→ logcat `not found value`。
2. ⚠️ **`setCurrentCode` 不刷新在屏文本** → 切语言要用 `updateLocalesCode`（否则"有些地方没变"）。
3. ⚠️ **不要手改 `i18n/<lang>.json`**（必须是 tab 制表/无空格冒号/末尾无空行，设备才认）；改 `.tr` 再转。真源：`op_spec.json` 的 `flythings_i18n（action=to_json）.rules`
4. ⚠️ **布局写 `@key` 带 @，代码 `setTextTr` 不带 @** —— 混了就是"显示成 key 原文"或取不到值。
5. ⚠️ **`.tr` 里换行写 `&#x000A;`**（唯一写法，§6）；json 里必须是真换行，否则设备**原样显示 `\n` 两个字**。
6. ⚠️ **各语言的别名必须对齐**（用相同的 `name`）：漏一种语言 = 该语言下这些文案缺省
   （`scan` 的 `keyAligned`/`missingKeysPerLanguage` 就是查这个）；
   另：**同一个 `.tr` 内别名不能重复**（官方明确）。
7. ⚠️ **文案里别用 `&`、`@` 等精简字库可能没有的字符**（白块/乱码）；改完核对 `cmap`。
8. `.tr` 是 **XML**：`&` 要写 `&amp;`，别当 key=value 文本随便写。
9. `refactor` 会**改写 ui/*.json**（`dry_run=False` 时）—— 先预览再执行；它只看
   `textview__*` / `button__*` 且跳过数字/时间占位。
10. 翻译要**结合项目语境**（车载项目的 `CAN BUS` 保持行业术语，不直译成"公共汽车"）。
11. ⚠️ **换行一律写 `&#x000A;`**（2026-10-05 需求方拍板「不要两个说法，全部统一」）；代码/本页/用例同批已改。
    历史字面 `\n` 仍**读得进**（老工程零迁移），但**写回会被归一成字符引用** —— 形式归一，不是两种写法并存。实测见 §6。
12. ⚠️ **加自定义语言后必须并入「内置界面翻译」**（官方硬要求，见 §5-5）：漏了则自己页面正常、
    **系统内置界面**文案不正常。⚠️ 本模块**没有**取/合并它的动作（零远程依赖），这一步目前要人工取那个文件再 `import`。

## 10. 未收录 / 待补（**如实登记**）

| 项 | 状态 |
|---|---|
| 真机复验（`/tmp/tr/` 路径、`fsc launch` 不推、`not found value`、切语言刷新） | **未做**（本文转述 2026-09-08 的既有记录，标 `needs_evidence: true`） |
| 仓内**已提交树**里没有带 i18n 的示例工程（`git ls-files "*.tr"` = 空） | 但**工作树现有 3 个真实 `.tr`**（`templates/DemoControls_V85X/i18n/`：`zh_CN-简体中文` / `en_US-ENGLISH` / `ru_RU-Русский`，2026-10-05 由需求方提供，未纳管）→ **可做离线验收**：`scan`（三语对齐）/ `to_json --push=False`（对 json 字节格式）。⚠️ 它们各只有 1 个 key（`hello_world`），**不含换行/实体/注释/多行**这类边界写法，别当边界样本用。官方完整样例仍是 **`TranslationDemo`**（官网[样例代码包](https://developer.flythings.cn/zh-hans/demo_download.html)，**不在本仓**） |
| ⚠️ **`.tr` 换行写法** | **已定案 = XML 字符引用 `&#x000A;`**（2026-10-05 需求方拍板「不要两个说法，全部统一」；代码/本页/用例同批改完，§6）；历史字面 `\n` 仅保留**读取**兼容 |
| ⚠️ **`add_language` / `export` 的默认 `lang` / `base_lang`（`zh_CN`）在三段式文件名工程上取不到语言** | **实测缺陷（2026-10-05）**：`i18n_tools.py` 按**完整文件名标识**查语言，而真实工程文件是 `zh_CN-简体中文` ⇒ ① `add_language(base_lang='zh_CN')` **直接失败**（`"基础语言 zh_CN 不存在"`）；② `export(lang='zh_CN')` 返回 `ok:true` 但 `count=0`（**静默空**，与 `to_json` 对未知语言硬报错的口径不一致）。**绕过**：显式传三段式标识（`base_lang='zh_CN-简体中文'`）即可成功。**未修**，登记待办 |
| ⚠️ `scan` 的「基准语言」不是 `zh_CN` | 实测：`layoutRefMissingInTr` / `trKeysUnusedByLayout` 按**文件名排序第一个**语言算（模板上 = `en_US-ENGLISH`），文档与用例都没声明这件事 |
| ⚠️ 官方工作流里"**哪一步**把 `.tr` 转成 json" | **本仓无证据**（2026-10-05 实测）：`fsc.exe` 16 个子命令**没有任何 i18n/locale/tr 开关**、Go 符号表无 i18n 包；`fui.exe` 只有 `pack`/`unpack`（json↔ftu）；隐藏命令 `fun convert` 只处理 `.fv/.ftu/.json`。⇒ 编译器侧转换这条链路**只能在 IDE 里**，本仓不可复现、不可判据化 |
| 固件里 i18n json 的落点 | **部分证据**：IDE `.prefs` 给 `easyui.cfg.release.languagePath = /res/tr/`（debug = `/mnt/extsd/tr/`）；`fsc.exe` 内嵌的设备侧 GUI 库里字符串写死 `.json` 后缀 + `internalLangPath = /system/res/internal/lang/`。**仍缺**：`fsc pack` 是否把 `/res/tr/` 写进 `EasyUI.cfg`（`fsc.exe` 里 `/res/tr` **0 命中**）—— 要真机 `cat` 三处 `EasyUI.cfg` + `ls -l /res/tr /system/res/internal/lang` 才能定案 |
| ⚠️ `import` 可能**静默清库** | **实测缺陷（2026-10-05，见 `temp/` 侦察）**：`_parse_tr` 解析失败时返回 `{}`，`merge=True` 走 `merged.update(...)` 后**整文件覆盖**，只余传入的 key，返回体仍 `ok:true`；单引号属性 `name='k'`、非 UTF-8 文件是最容易触发的输入。**未修**，登记待办 |
| `LanguageManager` 的头文件签名 | 未核（在 easyui **包内** `manager/LanguageManager.h`，不在本仓；官方示例里有 `#include "manager/LanguageManager.h"`） |
| `LANGUAGEMANAGER->setCurrentCode` 不刷新在屏文本 | 来自工具自带的框架级观察（**官方文档未提该 API**）→ 属补充警示，非官方口径 |
| 语言切换控件的 UI 做法（列表/图标） | 未收录（属控件层，见 `knowledge/uicontrols/`） |
| `tr2json.py`（工程侧同源脚本） | 只在实现注释里提到，本仓没有该脚本 |
| 内置界面翻译 `zh_CN.tr`（`docs.flythings.cn/src/zh_CN.tr`） | **未收录内容**（只登记了"必须并入"这条要求与地址） |

## 11. 相关

- **官方权威页**：<https://developer.flythings.cn/zh-hans/i18n.html>（多国语言翻译；样例 `TranslationDemo`
  在[样例代码包](https://developer.flythings.cn/zh-hans/demo_download.html)里）·
  内置界面翻译：<https://docs.flythings.cn/src/zh_CN.tr>
- `knowledge/devflow/activity-code-skeleton.md` §7：多语言在 activity 骨架里的位置（3 行摘要）
- `knowledge/devflow/custom-font-config.md` + `components/fonts/platforms.md`：字库能不能显示这些字符
- `knowledge/uicontrols/button-fields.md`：`text` / `caption` 字段语义（`@key` 写在 `text` 上）
- `knowledge/uicontrols/widget-code-api.md`：控件代码 API 速查（`setTextTr` 等成员方法）
- ⚠️ **注意**：`knowledge/uicontrols/` 下**没有** `textview-fields.md`（文本控件没有独立的字段页，
  字段口径以 `ui_schema.json` 为准）—— 本条是 2026-10-03 被 `check_doc_refs` 抓出来的，
  已登记为缺口候选，别再往这里写指针。
- `knowledge/devflow/package-properties-easyui-cfg.md`：EasyUI.cfg 里与语言/字库相关的键
- `knowledge/devflow/device-deploy-budget.md`：`fsc launch` 推什么（本文第 5 节的对照面）
