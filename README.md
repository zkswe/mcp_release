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
- 🧠 **35 个工具**：知识检索、项目创建、布局转换、依赖管理、规范校验、自动修复、多语言、自动化测试、UI 可视化编辑与真机截图全都有
- 📦 **一条命令安装**：`pip install mcp onnxruntime tokenizers`，AI 工具指一下路径就能用

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
> AI 会调用 `flythings_search` 检索内置知识库（本地向量模型），给你官方文档答案

> **示例 3：布局原型到界面**
> 帮我画一个俄罗斯方块的游戏主界面 HTML 原型，生成 HTML 预览确认
>
> AI 会调用 `flythings_generate_ui_preview` 出预览稿供你确认（也可以直接用 FlyThings IDE 预览/编辑 ftu 文件）

> **示例 4：编译交付**
> 布局改好了，帮我编译并推送到设备
>
> AI 会调用 `flythings_build_ui_flow`：fui pack → fun install → fun build → fun launch 一键完成

---

## 📑 目录

- [快速开始](#-快速开始)
- [核心特性](#-核心特性)
- [可用工具列表](#-可用工具列表)
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
pip install mcp onnxruntime tokenizers
```

> 需要 Python 3.10+。Windows 用户也可以双击 `install.bat` 一键安装。

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

**4. 验证**

在 AI 工具中问：

> **MCP 版本是多少？**

应返回：`flythings-kb-open 0.27.22-open`，包含 35 个工具。

---

## ✨ 核心特性

### 🧠 完全本地知识检索
- **内置 bge-small-zh 向量模型**（22MB），118 篇 wiki 文档索引随包分发
- 检索**不需要任何 API Key**，完全离线
- 模型不可用时自动降级 **BM25 关键词检索**，永不失联

### 🏭 全流程开发
- **创建项目**：从内置 HelloWord 模板（F133/F135/Z21/T113/V85X/Z20）一键创建
- **布局设计**：HTML 原型 → FTU 布局 → 一键打包
- **预览确认**：HTML 预览稿，或直接用 FlyThings IDE 预览/编辑 ftu 文件
- **编译交付**：内置 fui/fun 工具链，`build_ui_flow` 一键编译推送
- **规范校验**：`validate_project` 全量检查工程规范性

### 📦 依赖包管理
- 检索 FlyThings 依赖包生态（MQTT/JSON/HTTP/蓝牙/SSL/OTA 等）
- 自动生成 Manifest.xml、递归解析依赖、冲突检测

---

## 🛠 可用工具列表

| 工具 | 能力 |
|------|------|
| `flythings_search` | 知识库检索（本地向量 + BM25 双模式） |
| `flythings_get_version` | 版本信息 |
| `flythings_create_project` | 从模板创建项目（平台/分辨率） |
| `flythings_build_ui_flow` | fui pack → fun install → fun build → fun launch 一键交付 |
| `flythings_validate_project` | 项目规范全检（时间戳防呆/依赖/框架约定） |
| `flythings_html_to_json` / `json_to_html` | HTML 原型 ↔ FTU 布局 |
| `flythings_generate_ui_preview` / `json_to_html` | HTML 预览稿（或 FlyThings IDE 预览/编辑 ftu） |
| `flythings_read_json` | 布局文件解析（json；ftu 需提供同目录 json） |
| `flythings_*package*` | 依赖包查询/版本/API/Manifest/依赖解析 |
| `flythings_attach_cli_tools` | 附带 fui/fun 到项目 |
| `flythings_edit_ftu` | 布局编辑（set/remove/add/set_root） |
| `flythings_i18n_*` | 多语言（scan/export/import/refactor） |
| `flythings_gen_ui_test` | 自动化测试（traverse/monkey/custom） |
| `flythings_ui_editor` / `ui_edit_apply` | UI 可视化拖拽编辑 → 变更写回 json + pack ftu |
| `flythings_ui_diff` | 截图像素对比（0 token 验收 / 回归对比） |
| `flythings_device_screenshot` | **真机抓屏 → PNG/JPG/BMP**（裁剪设备免 adb 摸索，直接出图给 AI 分析） |
| `flythings_generate_ui_assets` | 生成 UI 图片资源（AI/emoji/线条三级降级） |
| `flythings_create_bin_project` | 创建可执行程序项目（ELF 二进制） |

---

## 📁 项目结构

```
flythings-mcp-open/
├── mcp_server.py          # 入口（stdio MCP server）
├── kb_tools.py            # 工具定义与注册（35 个）
├── project_tools.py       # 项目/编译/交付
├── package_tools.py       # 依赖包生态
├── rag_search.py          # 知识库检索（本地向量 + BM25）
├── embed_local.py         # 本地向量模型封装（bge-small-zh）
├── rag_index.json         # 知识库索引（本地模型预计算）
├── package_catalog.json   # 包版本目录
├── CHANGELOG.md           # 版本迭代记录（每次发布在此追加）
├── models/bge-small-zh/   # ★ 本地向量模型（onnx + tokenizer）
├── toolchain/             # ★ 编译工具链（fui.exe + fun.exe）
├── templates/             # ★ 项目模板（HelloWord_F133/F135/Z21/T113/V85X/Z20）
├── ui_tools/              # 布局转换/预览工具（html2json/json2html/check_all/gen_res）
├── install.bat            # 一键安装依赖
└── README.md              # 本文档
```

---

## ❓ 常见问题

| 问题 | 解决 |
|------|------|
| `ModuleNotFoundError: mcp / onnxruntime / tokenizers` | 执行 `pip install mcp onnxruntime tokenizers` |
| 工具列表 < 35 | 检查配置文件 command/args 路径是否正确 |
| 抓屏工具报“找不到 adb” | 装 Android platform-tools 或设环境变量 `ADB`（抓屏需要 adb；编译/预览不需要） |
| 检索结果不准 | 本地模型首次使用会自动加载；确认 `models/bge-small-zh/` 存在 |
| 想换知识库/重建索引 | `python rebuild_index_local.py <wiki目录>` 重新生成 rag_index.json |
| 杀毒软件拦截 | 添加信任（内含可执行文件 toolchain/） |

---

## 📄 开源协议

MIT License，详见 [LICENSE](LICENSE)。

---

FlyThings Team · 深圳中科世为科技有限公司 · [developer.flythings.cn](https://developer.flythings.cn/)
