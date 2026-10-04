---
id: devflow-ftu-json-pipeline
title: ftu 是什么：ftu 开发 / ftu 编辑 / ftu 修改 / ftu 格式 / ftu 逆向（ftu 转 json / unpack）（UI 文件 main.ftu 与 json 的关系）
category: devflow
status: review
confidence: manual
verified_at: 2026-09-29
stale_days: 180
origin: total
source: 2026-09-29 front-matter 迁移（P1：先显式登记"待补可执行判据"）
needs_evidence: true
platforms: []
tags: [ftu 能不能手写手改, main, 改了 json 设备上没变, 时命中, 不要手写, 手改 ftu, FlyThings IDE, 双击打开 ftu, 拖控件, 是另一套, 工作流, 两者不冲突但不能混用, §4]
evidence: []
---
# ftu 是什么：ftu 开发 / ftu 编辑 / ftu 修改 / ftu 格式 / ftu 逆向（ftu 转 json / unpack）（UI 文件 main.ftu 与 json 的关系）

> 检索导引：客户或 AI 问「**ftu 如何开发** / ftu 怎么改 / **怎么修改 ftu 布局文件** / ftu 是什么格式 /
> ftu 能不能手写手改 / ftu 能不能逆向成 json / **UI 文件**和 json 什么关系 / `main.ftu` 在哪 /
> 改了 json 设备上没变」时命中。
> **一句话口径：ftu 是 json 布局的编译产物**——要改界面就改 `ui/*.json` 再 `pack` 成 ftu，
> **不要手写、手改 ftu**。这是本 MCP 的代码工作流口径；FlyThings IDE「双击打开 ftu、拖控件」是另一套
> 工作流，两者不冲突但不能混用（见 §4）。

## 1. ftu 是什么

| 问 | 答 |
|----|----|
| ftu 是什么 | `<项目>/ui/*.ftu` = **设备实际加载的布局文件**（FlyThings 的 UI 二进制/打包格式） |
| 能直接看吗 | **不能当文本看**：实测文件头带 `ZKSW` 标记、内容是二进制（`git diff`、文本编辑器都读不懂） |
| 谁读它 | 设备侧 zkgui 读 **ftu**，不读 json；`fun launch` 把 `ui/main.ftu` 推到设备 `/tmp/ui/main.ftu`（实测设备侧与本文件字节数 + md5 完全一致） |
| 一个 ftu 顶什么 | **一个 ftu = 一个 Activity = 一个独立编译单元**（IDE 按 ftu 生成 `<name>Activity` + `<name>Logic.cc`）；但**页面 ≠ ftu**：一个 ftu 里通常放**多个整屏 window（= 多个页面）**，用 `showWnd()/hideWnd()` 切换。**默认单 Activity**（`main.ftu` + `mainActivity` + `mainLogic.cc`），只有跨业务域/需独立返回栈才拆新 ftu（口径见 `knowledge/devflow/page-architecture-spec.md` §0/§2） |
| ftu 从哪来 | 由**同目录同名 json** `pack` 而来：`ui/main.json` --fui pack--> `ui/main.ftu` |
| 模板里就有 json 吗 | **有**（2026-10-02 起）。7 个平台模板 `templates/HelloWord_<平台>/ui/` 同时带 `main.json` 与 `main.ftu`：json 由随包 `fui unpack` 从模板 ftu 反解析入库（实测 round-trip：pack 回 ftu 再 unpack 与源 json 逐字段等价），改布局直接改 json 再 pack 即可；从零起新界面仍走 `flythings_html_to_json` 生成 json，之后 json 才是源 |

## 2. 生成链路（单向，不要反过来）

```
ui/*.json  ← 唯一事实来源（唯一源）
   │  fui pack <ui目录>            # 或 op flythings_fui_pack(json_path)
   │  flythings_build_ui_flow      # 第②步会按需自动 pack
   │  flythings_ui_visual(action="edit_apply")   # 改 json 后写回 + pack
   ▼
ui/*.ftu  ← 设备实际加载的是它
   │  fun launch -p <平台> [-s <设备>]   # 调试：推到 /tmp/ui/*.ftu（掉电即失）
   │  fun pack                          # 固化：进 update.img（掉电保留）
   ▼
设备（zkgui 读 /tmp/ui/*.ftu 或只读分区里的同一份）
```

口径要点（别脑补）：

- **`fun build` 自己不做 json→ftu**。它只编译 C++（出 `libzkgui.so`），json→ftu 是 `fui pack` 干的活；
  MCP 里 `flythings_build_ui_flow` 的顺序是 **① 时间戳检查 → ② fui pack（仅当 json 比 ftu 新/缺 ftu）→
  ③ fun install → ④ fun build → ⑤ 默认到此为止**（`project_tools.flythings_build_ui_flow`）。
- **产物路径口径**：ftu 与 json **同目录同名**（`ui/main.json` → `ui/main.ftu`）；
  `fui pack <目录>` 会打包该目录下**所有** json。编译中间产物在 `<项目>/.fun/<平台>/`
  （`libzkgui.so`、生成的 UI 头、`launch/EasyUI.cfg` 等），**不是交付物，可以删**。
- 由此推出一条硬规则：**改了 json 不 pack，设备上永远是旧界面**（"改了 json 设备没变"的头号原因）。

## 3. 正确改法（改布局 = 改 json → pack → 推）

| 场景 | 做什么 |
|------|--------|
| 让用户自己拖（可视化微调） | `flythings_ui_visual(action="editor")` 出可拖拽编辑器 → 用户点「复制变更 JSON」→ `flythings_ui_visual(action="edit_apply")`（**写回 json + pack ftu**） |
| 直接改 json / 批量改 | 改完 `flythings_fui_pack(json_path="<项目>/ui/main.json")`；要连编译部署一起走 → `flythings_build_ui_flow(project_root, with_launch=True)` |
| 只改一个属性/文本（走 op） | `flythings_edit_ftu(ftu_path, operations=...)`：它**把变更应用到 json 再 pack 回 ftu**（见 §5） |
| 客户不用 MCP、纯命令行 | `fui pack <项目>/ui` → `fun build -p <平台>` → `fun launch -p <平台> -s <设备>`（工具随项目：`<项目>/ui/fui.exe`、`<项目>/fun.exe`） |
| 新界面从零开始 | 先 `flythings_html_to_json`（HTML 原型 → `ui/main.json`）→ pack → 预览 `flythings_ui_preview` → 真机验收 |

不要做的事：**不要绕过 pack 直接改设备上的 `/tmp/ui/*.ftu`**（下次 launch 全量推送就覆盖，且本地与设备对不上，
见 `knowledge/devflow/ui-layout-verify.md` §9 红线）。

## 4. ⚠️ IDE 工作流 vs 本 MCP 代码工作流（客户最常混的地方）

官方 wiki 有几篇讲 ftu 的文档（`wiki/flythings/devflow/project_structure.md`「ftu 是 UI 文件的后缀名、双击打开、
编辑完必须主动编译一次」、`wiki/flythings/devflow/new_ui_file.md`「新建 → FlyThings UI 文件」、`uicontrols/*.md` 的控件面板），
**它们讲的全是 FlyThings IDE 的可视化工作流**：在 IDE 里 ftu 是你直接编辑的对象，IDE 负责管理它与代码的对应关系。

本 MCP 的实践口径**不是**这一套：这里 ftu 是 **json 的编译产物**，布局以 `ui/*.json` 为源，改 json 后 pack。
两套流程各自自洽，但**别混用**：混用会出现「IDE 里改完 ftu，AI 又改 json 覆盖掉」的互相打架（工具已埋检查，见 §5）。
若检索命中 wiki 那几篇，请按"IDE 说明"理解，布局改动的落地仍按本文 §3。

## 5. 为什么禁止手改 ftu（以及 `flythings_edit_ftu` 的正确姿势）

1. **json 是唯一事实来源**：预览、编辑器、像素验收（`knowledge/devflow/ui-layout-verify.md` §1/§2）全部从 json 渲染，
   ftu 只是产物；手改 ftu 等于在产物上打补丁，下一次 pack 就没了。
2. **会被覆盖**：任何一次 `fui pack`（`flythings_fui_pack` / `build_ui_flow` 第②步 / `edit_apply`）
   都会用 json 重新生成 ftu，手改内容静默丢。
3. **没有版本管理价值**：ftu 是二进制，`git diff` 看不懂、评审看不出来、冲突没法合。
4. **格式不对外公开**：ftu 的字段/编码没有公开文档，手写等于逆向猜（要读 ftu 走 §6 的正规逆向路径，不要手写）。
5. **`flythings_edit_ftu` 不是"改二进制"**：它是「给变更 → 应用到同目录 json → 再 pack 回 ftu」，
   默认 `overwrite=False`（生成 `<name>.edited.ftu` 且留 `.bak`，不覆盖原文件）；**同目录没有 json 就报错**
   ——这正是"json 为源"的强制约束。
6. 工具已埋一致性检查（**ftu→json 只在两种情形自动做**，2026-09-18 口径）：
   - **只有 ftu 没有同名 json**（纯 IDE 工程/老工程）→ 直接 `unpack` 转出 json；
   - **ftu 比 json 新「分钟级」**（≥60 秒 = 用户/IDE 直接编辑过 ftu，pack 正常时两者差 <1s）→ 先
     `unpack ftu → 同步 json` 再继续（以 ftu 为真源）；
   - 其余情况**不做** ftu→json（json 是布局源，只需 json→ftu）。
   - ⚠️ **异常 ftu（不是合法 ftu/已损坏）反解析失败 → 明确报错并告知用户**（错误里带 `hint`：请提供对应 json 或重新导出该 ftu），**不静默跳过**、也不继续构建。`flythings_validate_project` 会分别报
   `ftu_without_json` / `dev_modified_ftu` 警告；json 比 ftu 新则报 `stale_ftu`（"改了 json 没重新 pack，
   设备仍跑旧版布局"）。

## 6. 逆向/解析：ftu → json（v0.27.91 起可用）

- 随包 `fui.exe` 自 **v0.27.91** 起**含 `unpack`**（`fui help` 里 pack/unpack 都在）：
  `fui unpack <in.ftu> [out.json]`（不给输出就解到同目录同名 json），也可以传**目录**批量解。
  工具代码按能力探测：`project_tools._fui_supports_unpack()` 跑 `fui help` 看有没有 `unpack`
  —— 用旧版 fui（只含 pack）时会明确报「不能 unpack」并**带上是哪个二进制 + 具体原因**；
  ⚠️ **「探测失败」与「能力缺失」分开报**（2026-10-03 修）：找不到/不可执行/超时属于**探测失败**
  （该修路径），不会被说成"版本不支持"（那会把人送去换 fui，方向是错的）；
  且**探测失败不缓存**（一次超时不会让整个会话从此认定不能 unpack）。
- **正道走 op**：`flythings_fui_unpack(ftu_path, output_json='', overwrite=True)`
  - 默认**覆盖**同目录同名 json（ftu 为真源）；要保留原 json 传 `overwrite=False` → 写 `<name>.unpacked.json`（已存在则追加序号）；
  - 也可以 `output_json` 指定别的落盘路径；
  - 返回 `jsonPath`（+ `controlsCount` / `resolution` / `overwritten` / `affectedFiles`），可直接交给 `flythings_read_json`。
- 用在：只有 ftu 没 json 的老工程接手 / 核对设备侧布局 / IDE 直接改过 ftu 要回写到 json。
- ⚠️ **逆向不等于改法**：改布局仍以 json 为源（改 json → pack），别养成「改 ftu → unpack → pack」的循环。
- `flythings_read_json` 读的是 **json**；只给 ftu 时它会明确指路 `flythings_fui_unpack`（不再说「加密无法解析」）。

### 6.1 ⚠️ 谁在调**哪个** `fui.exe`（三处查找顺序不一致 —— 已知不一致，2026-10-03 逐份代码实测登记）

工程里可能同时存在**两份 `fui.exe`**：随包 `toolchain/fui.exe`（MCP 用的），以及
`flythings_attach_cli_tools` 复制进 `<项目>/ui/fui.exe` 的那份（**给客户脱离 MCP 独立用**）。
三处代码的查找顺序**并不相同**：

| 谁 | 查找顺序 | 实际用哪份 |
|---|---|---|
| **`project_tools`（MCP 的 op 走这条）** | `$FLYTHINGS_FUN_DIR` → 本包 `toolchain/` → 上级 `toolchain/` → `D:\zkswe\fun` → `C:\zkswe\fun` | **工具链那份**（**完全不看项目内**） |
| `ui_tools/check_all.py` | 模块级 `toolchain/` → `../../projects/fui.exe` → PATH；**但 CLI 入口一旦发现 `<项目>/ui/fui.exe` 就用它覆盖**（v0.27.172 补回该优先级） | **项目那份优先** |
| `ui_tools/ui_edit_apply.py` | `$FUI_EXE` → `<项目>/ui/fui.exe` → `<项目>/fui.exe` → `../../projects/fui.exe` → 本目录 → PATH | **项目那份优先** |

**后果（什么时候会咬人）**：工程自带那份若与工具链**版本不同**（老工程 + 后来升级过 MCP，
就会这样），用 `flythings_fui_pack`（工具链那份）与用 `check_all.py --pack`（项目那份）
**产出的 ftu 可能不同** —— 「同一份 json → 同一份 ftu」这条确定性，只在**同一个 fui** 内成立。

**为什么没有统一**（不是疏忽，是约束）：① `ui_tools/` 是**可整目录复制出去**的
（`scripts/sync_ui_tools.py` 维护 `D:\flythings\ui_tools` 那份双份），那边取不到 `project_tools`，
共享不了一份解析器；② `attach_cli_tools` **必须**用工具链那份（它就是"复制进项目"的来源），
所以 `FUI_EXE` 也不能一律改成项目优先。
→ 现状分工 = **MCP op 用工具链、独立 CLI 用项目**；**这条不一致是登记在案的**，不是没发现。

**规避（发现两份不一致时）**：① 让它们一致 —— 删掉/替换 `<项目>/ui/fui.exe`；
② 或者**全程只走一条路径**（都用 op，或都用 `check_all.py`）。**别一半一半。**

## 7. 和 resources / 图片资源的关系（哪个进 ftu，哪个不进）

- json 里的图片写**相对 resources 的路径**（`images/xxx.png`），**不要写绝对路径、不要带 `resources/` 前缀**
  （`knowledge/devflow/ui-asset-rules.md` 铁律 #6）。
- `resources/` 目录**不是塞进 ftu**，而是**随程序一起打包/推送**；设备侧资源根 = `EasyUI.cfg` 的 `resPath`
  （launch 调试时为 `/tmp/ui/`），所以 `images/xxx.png` 落到设备 `/tmp/ui/images/xxx.png`
  （调试时可用 `adb shell /tmp/busybox ls -l /tmp/ui/images` 核对图有没有推上去，见 `knowledge/devflow/busybox-debug-library.md`）。
- 因此**改图 ≠ 改 ftu**：图片换新只要资源推上去就生效；但**图片路径/尺寸写错**（含 `thumb.size` 与图不符）
  会被 `flythings_verify_assets` / `check_all` 判 FAIL（`knowledge/devflow/ui-asset-rules.md` 铁律 #1）。
- 部署体积与内存预算（Z20/Z21 这类 36MB 内存板尤其看）见 `knowledge/devflow/device-deploy-budget.md`：launch 的产物全落
  `/tmp`（tmpfs = 吃内存），字库是最大头。

## 8. FAQ（客户原话 → 结论）

| 客户这么问 | 一句话结论 |
|------------|------------|
| ftu 如何开发 / 怎么修改 ftu 布局文件 | **不需要"开发 ftu"**：改 `ui/*.json` 再 pack 成 ftu。改法见 §3 |
| ftu 要怎么编辑 / ftu 修改流程是什么 | 同上；可视化拖拽走 `flythings_ui_visual(action="editor")` → `edit_apply` |
| 要不要学 ftu 文件格式 | **不用**。格式不对外公开、是二进制，业务上只需要知道"它是 json 的产物"（§1） |
| 能不能手写 ftu / 能不能直接改 ftu | **不能**。会被下次 pack 覆盖、无版本管理价值，见 §5 五条理由 |
| ftu 能逆向成 json 吗 | **能**（v0.27.91 起）：`flythings_fui_unpack`（默认覆盖同目录同名 json，ftu 为真源），详见 §6 |
| main.ftu 是什么文件 / UI 文件和 json 什么关系 | `main.ftu` = `main.json` 编译出来的界面文件，设备加载它；一对一同名（§1、§2） |
| 改了 json 为什么设备上没变 | 三连查：**没 pack**（`fui pack`）→ **没推**（`build_ui_flow(with_launch=True)` / `fun launch`）→ **设备在读旧 ftu / 推错了设备**（多设备必传 `-s`，见 `knowledge/devflow/cli-fun-toolchain.md` §6） |
| 我在 IDE 里直接改了 ftu，AI 再改 json 会不会冲突 | 不会丢：ftu 比 json 新「分钟级」时 build_ui_flow 会先 unpack 同步 json（以 ftu 为真源）；要么统一走 json，要么统一走 IDE（§4） |

## 9. 验证（实测记录）

检索覆盖实测（本地索引重建后，走与客户端同一条分发器路径 `mcp_server.flythings_kb`）：

```bash
python rebuild_index_local.py                 # 重建 rag_index.json（新文档进索引）
# 检索实测（同 _util.jcall 路径）
flythings_knowledge_search("ftu 如何开发 怎么修改 ftu 布局文件", k=5)
flythings_knowledge_search("ftu 可以手写吗")
flythings_knowledge_search("main.ftu 是什么文件")
```

| 问法 | 改前 | 改后（2026-09-17 实测） |
|------|------|------|
| ftu 如何开发 怎么修改 ftu 布局文件 | `low_confidence`（coverage 0.248；top5 里 3 条 wiki 镜像：`wiki/flythings/devflow/project_structure.md`、`wiki/flythings/uicontrols/textview.md`、`wiki/flythings/uicontrols/button.md`） | **`ok`（coverage 1.0）**，top5 中 4 条 = 本文档，top1 = `knowledge/devflow/ftu-json-pipeline.md` |
| ftu 可以手写吗 | `low_confidence`（top1 = wiki `wiki/flythings/devflow/project_structure.md`） | `ok`（1.0），top1/top3 = 本文档 §5 |
| main.ftu 是什么文件 | `low_confidence`（top1 = wiki `wiki/flythings/uicontrols/common_props.md`） | `ok`（1.0），top1 = 本文档 §1 |
| ftu 开发 / ftu 格式 逆向 / ftu 能逆向成 json 吗 | `ok`/`low_confidence` 混杂，命中多为 wiki 镜像 | `ok`（1.0），top5 全为本文档 |
| 改了 json 设备没变 | `ok`（命中 `knowledge/devflow/upgrade-pack-image.md` / `knowledge/devflow/ui-layout-verify.md`，无专门讲 ftu 的文档） | `ok`（1.0），top1 = 本文档 §8 FAQ |

> 数字来自 2026-09-17 本地实测（开发机；索引含本机 wiki 官方镜像，1412 chunks / 194 篇）。
> 复现口径：`python rebuild_index_local.py` 后跑 `tests/_util.jcall('flythings_knowledge_search', {'query': '<问法>', 'k': 5})`
> （与客户端 `flythings_knowledge_search` 同一条分发器路径）。

## 10. 相关文档

- `knowledge/devflow/ui-layout-verify.md`：三段式验收、像素 diff、§9 红线（json 为源）
- `knowledge/devflow/ui-editor-usage.md`：可视化编辑器（`ui_visual(action="editor")`）
- `knowledge/devflow/cli-fun-toolchain.md`：fun / fui 命令表、多设备陷阱、`/tmp/ui` 核对判据
- `knowledge/devflow/page-architecture-spec.md`：一个界面该用独立 ftu 还是同 ftu 内多 window
- `knowledge/devflow/ui-asset-rules.md`：图片资源铁律（路径、尺寸、`thumb.size`）
- `knowledge/devflow/device-deploy-budget.md`：部署体积与内存预算（launch 产物落 `/tmp`）
