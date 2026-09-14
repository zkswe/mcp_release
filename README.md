<div align="center">

# 🦅 FlyThings MCP Open

**让所有 AI 助手直接获得 FlyThings 完整开发能力，一句话部署，一句话开发FlyThings OS人机交互产品**

**flythings-mcp | FlyThings MCP | FlyThings OS | FlyThings AI 助手 | 中科世为 MCP |FlyThings HMI**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![MCP](https://img.shields.io/badge/MCP-Compatible-green.svg)](https://modelcontextprotocol.io/)
[![FastMCP](https://img.shields.io/badge/FastMCP-Powered-orange.svg)](https://github.com/jlowin/fastmcp)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

</div>

---

## 🌟 项目亮点

一个功能强大的 [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) 服务器，让 **Trae / Cursor / Kimi / Claude Desktop ** 等 AI 编程工具直接调用 FlyThings 全套开发能力。

🔥 **核心优势**：
- 🚀 **FlyThings 专属配置**：内置本地向量模型（bge-small-zh），知识检索完全离线，AI开发效率及Token消耗极低
- 🏭 **全流程开箱即用**：编译工具链（fui/fun）与项目模板已内置，创建项目 → 布局 → 编译 → 推送一气呵成
- 🧠 **34 个工具**：知识检索、硬件型号库、项目创建、布局转换、依赖管理、规范校验、自动修复、多语言、自动化测试、UI 可视化编辑、真机截图与产物核对全都有
- 📦 **一条命令安装**：`pip install -r requirements.lock`（已锁定实测通过的版本组合），AI 工具指一下路径就能用
- ✅ **发布前置闸门**：133 项契约用例 + 30 项冒烟 + 一致性校验（版本/工具数/平台/索引/隐私）一键跑，见 [`tests/`](tests/README.md)
- 🪶 **schema 集约**：工具 docstring 合计 ≤ 12,000 字符（单个 ≤ 900），长尾细节全放可检索的知识库——不拿上下文烧钱

🎯 **适用场景**：
- ✅ Trae/Cursor /Kimi AI + FlyThings IDE：人机共创，AI负责整体开发，FlyThings IDE 可视化实现人工调优细节调整。       
- ✅ Trae/Cursor /Kimi AI+ FlyThings：AI 读懂需求后直接生成可编译的 FlyThings 工程 并且完成UI-代码-编译-下载一条龙搞定。
- ✅ Kimi / Claude Desktop ：知识检索 + 开发辅助
- ✅ 任何支持 MCP 协议的 AI 开发工具

🎮 **使用样例（直接复制给 AI 即可）**：

> **示例 1：从零创建项目（俄罗斯方块）**
> 帮我用 FlyThings 创建一个 Z21 平台、1024x600 分辨率的俄罗斯方块项目
>
> AI 会引导你：确认平台/分辨率 → `flythings_create_project` 创建项目骨架 → 出布局预览 → 写逻辑代码 → `flythings_build_ui_flow` 编译推送

> **示例 2：技术问题咨询**
> FlyThings 里 ZKListView 怎么用 adapter 模式做列表数据绑定？
>
> AI 会调用 `flythings_knowledge_search` 检索内置知识库（本地向量模型），给你官方文档答案

> **示例 3：布局原型到界面**
> 帮我画一个俄罗斯方块的游戏主界面 HTML 原型，生成 HTML 预览确认
>
> AI 会调用 `flythings_ui_preview` 出预览稿供你确认（也可以直接用 FlyThings IDE 预览/编辑 ftu 文件）

> **示例 4：编译交付**
> 布局改好了，帮我编译并推送到设备
>
> AI 会调用 `flythings_build_ui_flow`：fui pack → fun install → fun build → fun launch 一键完成

---

## 📑 目录

- [快速开始](#-快速开始)
- [核心特性](#-核心特性)
- [可用工具列表](#-可用工具列表)
- [可复用组件（components/）](#-可复用组件components)
- [项目结构](#-项目结构)
- [常见问题](#-常见问题)
- [开源协议](#-开源协议)

---

## 🚀 快速开始

> 💡 **小白用户？** 直接对 AI 说 **"帮我克隆并安装 https://gitee.com/Kwolve/fly-things-os_-mcp 项目"**，AI 会引导你完成所有步骤！

### 方式一：让 AI 帮你安装（推荐！！！）

直接对你的 AI 说：

```
帮我克隆并安装 https://gitee.com/Kwolve/fly-things-os_-mcp 项目
```

AI 会自动完成：克隆项目 → 安装依赖 → 引导配置 → 完成。

### 方式二：手动安装

**1. 获取代码**

```bash
git clone https://gitee.com/Kwolve/fly-things-os_-mcp.git
# 或直接下载 ZIP：https://gitee.com/Kwolve/fly-things-os_-mcp/repository/archive/master.zip
```

**2. 安装依赖**

```bash
pip install -r requirements.lock      # 已锁定实测通过的组合（含 mcp / onnxruntime / tokenizers / Pillow）
```

> 需要 Python 3.10+。Windows 用户也可以双击 `install.bat` 一键安装（装完自动跑一次离线自检）。
> 想自己拉最新版也行：`pip install mcp onnxruntime tokenizers Pillow`（不锁定，风险自负）。

**3. 配置到 AI 工具（stdio）**

在**你的项目根目录**创建 `.mcp.json`（Trae / Cursor / Kimi 均识别）：

```json
{
  "mcpServers": {
    "flythings-kb-open": {
      "type": "stdio",
      "command": "python",
      "args": ["C:/你的路径/flythings-mcp-open/mcp_server.py"]
    }
  }
}
```

各工具放置位置：

| 工具 | 配置文件位置 |
|------|-------------|
| Trae | 项目根 `.trae/mcp.json` 或 `.mcp.json` |
| Cursor | 项目根 `.cursor/mcp.json`，或 Cursor Settings → MCP → Add |
| Kimi（Kimi for Coding） | 项目根 `.mcp.json` 或 `.kimi/mcp.json` |
| Claude Desktop | `claude_desktop_config.json` 的 mcpServers 节点 |

> 如果 `python` 不在 PATH，用完整路径（如 `C:/Users/<你>/AppData/Local/Programs/Python/Python313/python.exe`）。

**工具面三模式（按客户端选一个，别同时配）**

| 模式 | 怎么配 | 客户端看到什么 | 何时用 |
|------|--------|----------------|--------|
| `dispatcher`（默认） | 就指 `mcp_server.py` | **1 个工具** `flythings_kb`（op="list" 取目录） | 推荐：schema 开销最小；配合意图闸门/README 工具表 |
| `all` | `FLYTHINGS_MCP_MODE=all` | 1 个分发器 + 34 个独立工具 | 你的提示词/客户端直接调 `flythings_knowledge_search` 这类名字（旧配置兼容） |
| `flat` | 指 `mcp_server_flat.py`（或 `FLYTHINGS_MCP_MODE=flat`） | 34 个独立工具（无分发器） | 需要每个工具独立 schema/参数提示的客户端（Trae / Cursor / Claude Desktop） |

> ⚠️ 默认从“全注册”改为“只分发器”是 v0.27.34 的**行为变更**；受影响就设 `FLYTHINGS_MCP_MODE=all` 恢复。
> `flat` 模式的代价：34 份 schema 常驻上下文（≈1 万 token/session）。

**4. 验证**

在 AI 工具中问：

> **MCP 版本是多少？**

应返回：`flythings-kb-open 0.27.59-open`，包含 34 个工具。

---

## ✨ 核心特性

### 🧠 完全本地知识检索
- **内置 bge-small-zh 向量模型**（22MB），随包分发 128 篇 wiki 官方镜像 + 51 篇实践知识（`knowledge/`，共 179 篇去重索引）
- 检索**不需要任何 API Key**，完全离线
- 向量 + BM25 双路 **RRF 融合**（中文按**字级 bigram** 切词 + IDF + 路径/标题加权，实测 top-3 命中 10/10）
- 返回体带 `retrieval` / `degraded` / `quality`（ok | low_confidence | no_hit）/ `source`（实践 or 官方镜像），低置信与未收录会给明确提示
- 模型不可用时自动降级 **BM25**（并在 `warnings` 里显式说明），永不失联

### 🏭 全流程开发
- **创建项目**：从内置 HelloWord 模板（F133/F135/Z21/T113/V85X/Z20）一键创建
- **布局设计**：HTML 原型 → FTU 布局 → 一键打包
- **预览确认**：HTML 预览稿，或直接用 FlyThings IDE 预览/编辑 ftu 文件（多整屏 window 工程自动出「页面切换条」+ `#window__N` hash 直达 + 「显示隐藏」幽灵框）
- **编译交付**：内置 fui/fun 工具链，`build_ui_flow` 一键编译推送
- **规范校验**：`validate_project` 全量检查工程规范性

### 📦 依赖包管理
- 检索 FlyThings 依赖包生态（MQTT/JSON/HTTP/蓝牙/SSL/OTA 等）
- 自动生成 Manifest.xml、递归解析依赖、冲突检测

---

## 🛠 可用工具列表

| 工具 | 能力 |
|------|------|
| `flythings_knowledge_search` | 知识库检索（本地向量 + BM25 双模式，带 quality/source 标记） |
| `flythings_hardware_info` | **硬件型号库**（platform/model → 屏幕分辨率·方向、按键值（/dev/input code）、接口规格、型号/平台差异化、待补字段；未收录只给候选不猜规格；表见 `knowledge/hardware/hardware-models.md`） |
| `flythings_get_version` | 版本信息 |
| `flythings_create_project` | 从模板创建项目（平台/分辨率） |
| `flythings_build_ui_flow` | fui pack → fun install → fun build → fun launch 一键交付 |
| `flythings_pack_upgrade` | **固化升级出包 update.img**（fun install → 可选 fun build → fun pack；默认 `.fun/<平台>/update.img`，可指定 `out_path`/`release_version`/`ab`；返回路径·大小·四种刷法：TF卡 / ADB setprop / zkautoupgrade / HTTP OTA 与批量升级。⚠️ 与 `build_ui_flow` 语义不同：那是调试推送掉电即失，**要固化必须本工具**） |
| `flythings_validate_project` | 项目规范全检（时间戳防呆/依赖/框架约定） |
| `flythings_html_to_json` / `flythings_ui_preview` | HTML 原型 ↔ json 布局（转换 / 预览确认稿；预览支持整屏 window 多页工程的页面切换条 + `#window__N` 直达） |
| `flythings_read_json` | 布局文件解析（json；ftu 需提供同目录 json） |
| `flythings_package_search` / `flythings_query_package` / `flythings_get_package_api` | 依赖包检索 / 版本 / 头文件级 API |
| `flythings_manifest` | Manifest 依赖配置（**默认 dry_run 只推荐**；给 project_root + dry_run=False 才写盘） |
| `flythings_add_package` / `flythings_resolve_dependencies` / `flythings_check_project_deps` | 加包 + fun install / 递归解析依赖 / 代码 include 对账 |
| `flythings_attach_cli_tools` | 附带 fui/fun 到项目 |
| `flythings_edit_ftu` | 布局编辑（set/remove/add/set_root） |
| `flythings_i18n_*` | 多语言（scan/add_language/export/import/refactor/to_json） |
| `flythings_gen_ui_test` | 自动化测试（traverse/monkey/custom） |
| `flythings_ui_visual` | **UI 可视化三合一**（action="editor" 可拖拽编辑网页 / action="edit_apply" 变更写回 json + pack ftu / action="diff" 截图像素对比 0 token 验收；传 action="list" 看各动作参数） |
| `flythings_verify_assets` | **产物核对**（json 引用的图片是否存在 + 自动生成图 PNG 尺寸 == 控件 position；支持 `ui/*.json` 与 `ui/<分辨率>/*.json`；与 check_all #17 同源） |
| （仅 check_all） | **#18 设计令牌漂移检测**（`DESIGN.md` 令牌 vs json 实际色值/字号；令牌外的值 = FAIL；无 DESIGN.md / 令牌表未填 → NOTE 跳过；单点例外写「漂移豁免: #RRGGBB 18」） |
| `flythings_device_screenshot` | **真机抓屏 → PNG/JPG/BMP**（裁剪设备免 adb 摸索，直接出图给 AI 分析；进阶参数可统一走 `advanced` JSON） |
| `flythings_generate_ui_assets` | 生成 UI 图片资源（AI/emoji/线条三级降级） |
| `flythings_create_bin_project` | 创建可执行程序项目（ELF 二进制） |

### 📦 resources / prompts（MCP 原生原语）

除工具外，服务端还暴露：

| 原语 | 地址 / 名称 | 用途 |
|------|-------------|------|
| resource | `flythings://catalog/knowledge` | 知识库目录（分类 → 文档清单） |
| resource | `flythings://knowledge/<分类>/<文件>.md` | 直接读整篇知识文档（如 `devflow/device-screenshot.md`） |
| resource | `flythings://tools` | 工具清单 + 风险分级（read/write/device） |
| resource | `flythings://version` | 版本 / 构建日 / 工具数 / 近期特性 |
| prompt | `flythings-new-project` / `ui-from-prototype` / `ui-verify` / `deploy-debug` / `package-deps` | 常用流程模板（自带安全默认提醒） |

> 工具合并（v0.27.36 起，旧名不再提供）：`search`→`flythings_knowledge_search`、`search_package`→`flythings_package_search`、
> `generate_ui_preview`+`json_to_html`→`flythings_ui_preview`、`recommend_manifest`+`generate_manifest`→`flythings_manifest`；
> v0.27.37 起 ui-visual 组收口为单入口：`ui_editor` + `ui_edit_apply` + `ui_diff` → **`flythings_ui_visual(action=editor|edit_apply|diff)`**；
> 调旧名会收到 `OP_RENAMED` 错误并直接告诉你新名字（带 action 提示，不是隐式别名）。

---

## 🔧 可复用组件（components/）

`components/` 里放**能直接拿进工程用的代码/资产**（随本 MCP 一起发布，AI 可直接取用）：

| 模块 | 是什么 | 怎么用 |
|---|---|---|
| `components/ble/` | BLE 门面 `zk::ble`（用法像微信 `wx.*`）：`openAdapter / startDiscovery / onDeviceFound / connect / getServices / readValue / writeValue / subscribe / getDiag` | 把 `include/ + src/` 拷进工程 `src/`，工程声明 `btstack` 依赖（见模块 `Manifest.xml`）；上电/预初始化/H5/线程/TLV 全在组件内部 |
| `components/fonts/` | 思源黑体三版（常用中文 872KB / 全中文 7.39MB / 多国语言 10.5MB）+ 设备字体自检 | 体检：`python components/fonts/scripts/device_font_check.py`；缺中文就 `--apply --project <工程>` 自动投递 |

模块规范（四件套、代码尺子、package 引用）见 `components/README.md`；
详细口径可检索：`knowledge/devflow/reusable-components.md`。

---

## 📁 项目结构

```
flythings-mcp-open/
├── mcp_server.py          # 入口（stdio MCP server，单入口分发器）
├── kb_tools.py            # 工具定义与注册（34 个）+ OP_NAMES 清单（唯一来源）
├── project_tools.py       # 项目/编译/交付
├── package_tools.py       # 依赖包生态
├── platforms.py           # 平台矩阵唯一来源（模板/bin_tools/别名）
├── hardware_tools.py      # 硬件型号库读取/查询/文档生成（单一来源 = hardware_catalog.json）
├── hardware_catalog.json  # 硬件型号库（平台 → 型号 → 屏幕/按键/规格 + 平台差异化，人工维护）
├── rag_search.py          # 知识库检索（本地向量 + BM25）
├── embed_local.py         # 本地向量模型封装（bge-small-zh）
├── rag_index.json         # 知识库索引（本地模型预计算）
├── package_catalog.json   # 包版本目录
├── tools_manifest.json    # 工具/平台/知识规模快照（机器可读，由 scripts/gen_manifest.py 生成）
├── pyproject.toml         # 打包/依赖声明 + console_scripts 入口
├── requirements.lock      # 已验证依赖组合（pin）
├── CHANGELOG.md           # 历史迭代记录（截至 v0.27.30，已冻结；版本史见 MCP_FEATURES）
├── scripts/               # 自检与闸门（smoke / check_consistency / gen_manifest / lint_silent_except / sync_ui_tools / ci）
├── tests/                 # 契约用例（离线，129 项；见 tests/README.md）
├── models/bge-small-zh/   # ★ 本地向量模型（onnx + tokenizer）
├── toolchain/             # ★ 编译工具链（fui.exe + fun.exe）
├── templates/             # ★ 项目模板（HelloWord_F133/F135/Z21/T113/V85X/Z20）
├── ui_tools/              # 布局转换/预览工具（html2json/json2html/check_all/gen_res）
├── components/            # ★ 可复用组件（随 MCP 一起发布，AI 可直接取用）
│   ├── README.md          #   组件规范：四件套 + 两种形态 + 代码规范
│   ├── ble/               #   BLE 门面 zk::ble（扫描/连接/GATT/诊断；底层脏活全在组件内）
│   └── fonts/             #   思源黑体三版 + 设备字体自检（缺中文自动投递）
├── install.bat            # 一键安装依赖（装完跑离线自检）
└── README.md              # 本文档
```

> ⚠️ `ui_tools/` 在本机工作区另有一份副本（给非 MCP 流程/人肉用的 `tools/ui_tools/`）。
> **唯一来源是仓库内的 `flythings-mcp-open/ui_tools/`**；改完跑 `python scripts/sync_ui_tools.py --apply` 同步，
> `scripts/check_consistency.py` 会校验两份哈希一致。

---

## 🧰 CLI 名词表（别搞混 fun / fui / fyx / fuse）

| 名字 | 是什么 |
|------|--------|
| `fun` | FlyThings 工程工具：`create / install / build / launch`，状态与产物在 `<项目>/.fun/<平台>/` |
| `fui` | FTU 布局工具：**当前内置版本只支持 `pack`（json → ftu）**；`unpack` 是空壳（调用报通用错误），别依赖 |
| `fyx` | 旧版打包/发布 CLI 名（历史遗留，等价于 `fun` 的早期名） |
| `fuse` | 本机工作区的引擎 CLI（`projects/fuse.exe`），**不在本仓库内**，与本 MCP 无关 |

---

## ❓ 常见问题

| 问题 | 解决 |
|------|------|
| `ModuleNotFoundError: mcp / onnxruntime / tokenizers` | 执行 `pip install -r requirements.lock` |
| 工具列表 < 34 | 检查配置文件 command/args 路径是否正确 |
| 抓屏工具报“找不到 adb” | 装 Android platform-tools 或设环境变量 `ADB`（抓屏需要 adb；编译/预览不需要） |
| 检索结果不准 | 本地模型首次使用会自动加载；确认 `models/bge-small-zh/` 存在 |
| 返回体里出现 `warnings` | 正常，**要看**：降级（BM25）、自动转图、手绘图被拉伸等信息都在里面，不是报错 |
| 改动后想自检 | `python scripts/check_consistency.py --with-tests`（版本/工具数/平台/索引/隐私 + 133 项契约用例） |
| 想换知识库/重建索引 | `python rebuild_index_local.py <wiki目录>` 重新生成 rag_index.json |
| 杀毒软件拦截 | 添加信任（内含可执行文件 toolchain/） |

---

## 📄 开源协议

MIT License，详见 [LICENSE](LICENSE)。

---

FlyThings Team · 深圳中科世为科技有限公司 · [developer.flythings.cn](https://developer.flythings.cn/)
