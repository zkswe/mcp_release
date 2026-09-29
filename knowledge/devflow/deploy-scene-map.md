---
id: devflow-deploy-scene-map
title: 部署/调试场景 → 工具动作映射（禁止自造部署命令）
category: devflow
status: review
confidence: manual
verified_at: 2026-09-29
stale_days: 180
origin: total
source: 2026-09-29 front-matter 迁移（P1：先显式登记"待补可执行判据"）
needs_evidence: true
platforms: []
tags: [内部 fun launch, deploy_debug, sh, sh 之类的额外部署脚本, AI 在任意客户端里收到, 调试, 全量推送, 部署, 类请求时, 必须调用 MCP 工具]
evidence: []
---
# 部署/调试场景 → 工具动作映射（禁止自造部署命令）

> 检索导引：问「调试/部署/全量推送/跑一下该调哪个工具 / 有没有 deploy_debug.sh / 固化升级算不算调试」→ 本文（用户话语→唯一动作映射）；固化出包见 `devflow/upgrade-pack-image.md`。
> 铁律：FlyThings 全量部署/推送的唯一入口是 **`flythings_build_ui_flow`（内部 fun launch）**，
> **不存在任何 `tools/deploy_debug.sh` / deploy_debug.sh 之类的额外部署脚本**。
> AI 在任意客户端里收到「调试/全量推送/部署」类请求时，必须调用 MCP 工具，禁止自创 shell 脚本或命令路径。

## 用户话语 → 唯一动作

⚠️ **不限触发入口**：以下映射对**任何入口**都成立——用户口语、客户端自定义功能按钮（如「AI 应用调试」「自定义编译」）、AI 写完/改完代码后自主编译验证调试。
只要意图是「把项目编译并部署到真机调试」，一律调 `flythings_build_ui_flow`，禁止自造脚本。

| 用户说（口语/场景） | AI 应调用的工具 | 说明 |
|---|---|---|
| 编译 / 构建 / 编译推送 | `flythings_build_ui_flow` | fui pack → fun install → fun build |
| **调试 / 应用调试** | `flythings_build_ui_flow`（with_launch 默认 true） | 编译后直接推送真机看效果 |
| **全量推送 / 部署 / 部署到设备 / 推送到设备** | `flythings_build_ui_flow` | fun launch = 程序+资源+ftu **全量**推送并启动 |
| 跑一下 / 运行到真机 / 更新到设备 | `flythings_build_ui_flow` | 同上 |
| **AI 自定义编译功能调试**（客户端按钮/动作/自动化流程） | `flythings_build_ui_flow` | 功能入口无论叫什么，落地动作仍是它 |
| **AI 自主编译验证**（改完代码主动编译调试看效果） | `flythings_build_ui_flow` | 同上 |

⚠️ 没有「增量推送 vs 全量推送」两种模式：**fun launch 本身就是全量推送**（程序+资源+ftu 一起部署），
不需要 adb push 单文件、不需要 kill zkgui、不需要中间脚本。

> **应用侧重启应用进程时的姿势**（仅限脚本/示例要自己重启应用的场合，**不是**正常部署流程）：
> **走 setprop 让 init 控制，不 kill 程序** —— 应用由类 init 服务托管（`/etc/init.rc`:
> `service zkswe /bin/zkgui`），控制程序 = `setprop ctl.restart zkswe`（厂商 `fun launch`
> 内部也是 `ctl.restart`，不用 kill）。MCP 侧单一实现 `adb_tools.restart_app()`
> （setprop → 轮询等新 pid；`kill` 仅在 `allow_kill=True` 时才作兜底）。
> ⚠️ 历史坑：早期临时脚本/示例大量 `kill -9 zkgui` / `busybox killall zkgui`，
> 反复 kill 之后现场出现过「触摸注入不响应」「整板掉网」→ 现在统一口径：**不 kill**。
> 口径与背景见 `device-deploy-budget.md` §5。

## ⚠️ 反例：固化升级**不是**本工具（另一条唯一入口）

「部署」这个词有两种语义，**必须按意图分流**，别都塞给 `build_ui_flow`：

| 用户说（口语/场景） | AI 应调用的工具 | 说明 |
|---|---|---|
| 调试 / 跑一下 / 看效果 / 全量推送（**临时**） | `flythings_build_ui_flow`（with_launch=True） | `fun launch` 推送到设备运行，**掉电即失，不固化** |
| **固化 / 固化升级 / 升级进设备 / 出升级包 / 生成 update.img / 出货版本 / 量产版本 / 发布版本 / 烧到机器里 / TF卡升级包 / OTA 包** | **`flythings_pack_upgrade`** | `fun pack` 出 `update.img`，刷进设备**掉电保留**；返回 TF卡/ADB/自动升级/远程批量四种刷法 |

判据一句话：**掉电后还要在 → 固化（pack_upgrade）；只是看效果 → 调试（build_ui_flow）**。
完整流程（含 TF 卡 FAT32、ADB setprop、zkautoupgrade、批量升级、刷机卡区别）见
`knowledge/devflow/upgrade-pack-image.md`。

## 为什么会有这个文档（坑源）

2026-09-08 沛哥反馈：客户端 AI 收到「AI 应用调试全量推送」时，工具列表里没有叫「调试/部署」的工具，
`build_ui_flow` 描述又只写「UI 构建流程」，AI 检索不到映射 → **自造了 `tools/deploy_debug.sh` 动作**（幻觉）。
结论：用户话语与真实动作的绑定必须**显式写进工具描述 + 知识库**，否则模型会发明不存在的命令。

- 工具描述侧的绑定：`flythings_build_ui_flow` docstring 头部已加「场景别名」段落（v0.25.x 起）。
- 检索侧本文件即答案：搜「调试」「全量推送」「部署」「deploy」都能命中这里，命中即指向 build_ui_flow。

## 历史依据

- v0.7.15-open (2026-09-02) FT-007 废弃（沛哥定规）：删除「手动 adb push images + kill zkgui」部署顺序规则，
  **部署统一只用 fun launch**（fun launch 内部已正确部署程序+资源+ftu 并启动）。
- fun launch 设备选择自动完成；无 adb 设备时 build_ui_flow 返回 needDeviceInput=true，
  询问用户 USB/网络接入方式，**禁止替用户猜测 IP、禁止绕开工具手写 adb 命令**。
