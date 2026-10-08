---
id: devflow-capability-boundaries
title: 能力边界清单（open 版到底能做什么、不能做什么）
category: devflow
status: review
confidence: manual
verified_at: 2026-09-29
stale_days: 180
origin: total
source: 2026-09-29 front-matter 迁移（P1：先显式登记"待补可执行判据"）
needs_evidence: true
platforms: []
tags: [这个主题知识库没收录怎么办, 未收录, 是不是能力缺失, 为什么查不到, 覆盖范围, 不支持的方案, 该找厂家还是自己写]
evidence: []
---
# 能力边界清单（open 版到底能做什么、不能做什么）

> **检索导引**：MCP 能做什么 / 能力边界 / 哪些知识不在 open 版 / 内部版区别 /
> 这个主题知识库没收录怎么办 / 未收录 / 是不是能力缺失 / 为什么查不到 /
> open 版与 release 版差异 / 覆盖范围 / 不支持的方案 / 该找厂家还是自己写

---

## 0. 为什么要有这份清单

**open 版最危险的不是「能力不足」，而是「AI 和人都不知道边界在哪」**——
于是 AI 会拿沾边片段（甚至别的 GUI 框架的用法）当依据往下写。
本清单把边界**显式写出来**：查到就是查到，没查到就按「未收录」处置，**不猜、不类推**。

---

## 1. 覆盖范围（open 版有，可直接用）

| 维度 | 覆盖 |
|------|------|
| **平台**| F133 / F135 / T113 / V85X / Z20 / Z21 / Z235X（可建工程 + 编译 + 部署 + 设备端工具）；另 4 个**仅依赖包生态**平台（Z6S / Z261 / H500S / A33NOR，只能查包，不能建工程） |
| **UI 全链路**| 原型 HTML → json（`html_to_json`）→ ftu（`fui_pack`）→ 工程（`create_project`）→ 编译部署（`build_ui_flow`）→ 真机截图（`device_screenshot`）→ 像素验收（`ui_visual` diff/baseline）→ 固化升级包（`pack_upgrade`） |
| **控件知识**| `knowledge/uicontrols/` 34 篇：主流控件字段/回调/API + 层级与触摸规则 + 系统窗口（statusbar/navibar/screensaver/IME）+ 全局弹框 |
| **流程/工程**| `knowledge/devflow/` 31 篇：依赖包与 Manifest、i18n、多设备部署、页面架构（单 Activity 多整屏 window）、原型先行流程、测试链路 |
| **硬件事实**| `knowledge/hardware/`：型号库（主控 / 屏 / 联网 / 分区 / 升级通道 / 触点）+ 板级坑（继电器接线、背光、`EasyUI.cfg` 劫持、MIPS 分区上限…） |
| **组件（随仓发布）**| `components/`：ble / fonts / icons / blur / imagecache / vinyl / mp_transfer / ui_v1（含 `_mapping`）——四件套规范，可直接拷进工程。⚠️ 组件里**平台专属**的那几个（如 `ble`）与 `mqtt` 同级：本行只说明“它在仓里”，**平台可用性看 `components/<组件>/platforms.md` 正文**，不进「平台 × 能力」矩阵（登记见 `components_catalog.DECLARED_GAPS`） |
| **依赖包用法**| `packages/<包>/package.yaml`（机器可读卡 + 实测状态）+ README/platforms/example/evidence |
| **设备端预编译工具**| `bin_tools/<平台>/`：`touch`（触摸注入，自动判协议）/ `busybox` / `ui_test`（兼容老屏）/ `zkshot` —— `mt_test` 已于 2026-09-30 移除（能力由 `touch` 自动判协议覆盖） |
| **自动化测试**| `gen_ui_test`（从 json 生成用例）+ `test_run`（多设备并行 + 日志断言 + 像素基线 + JUnit 报告）+ `selfcheck`（整机快照 diff）+ `bugreport`（缺陷单） |

---

## 2. **明确不在 open 版**（查不到 = 正常，不是缺陷）

| 主题 | 为什么不在 | 该怎么做 |
|------|-----------|---------|
| **自研帧动画（ZKBIN/QOI/region）**| 依赖内部工具链，open 用户拿不到工具 | 普通动效走 `imageanim` 控件；需要时问厂家 |
| **V85X 深水区**（平台方媒体包的版本兼容细则、VO/disp 层调优步骤、UVC JPEG 全链路） | 内部版专属 | 通用结论（UVC 接入、OTG 切换）open 版有；深的问厂家 |
| **方案类知识**（车载互联 / 涂鸦 / SIP 对讲 / ESL 价签业务） | 涉及客户方案 | 按对应平台通用能力做，业务细节查厂家资料 |
| **easyui 库源码/头文件语义**| 预编译闭源库；且本仓**明令禁止**解析源码推字段/回调（拿不到语义） | 走知识库 + 官方文档站 `developer.flythings.cn`；**不要**从其它 GUI 框架类推 |
| **网络类非公开接口**（WiFi 嗅探 / monitor mode / 隐藏摄像头探测） | 未收录 | 未收录就标未收录，不要猜 API |

---

## 3. 知识库没收录 / 查不到怎么办 —— 规定动作

1. 看 `flythings_knowledge_search` 的 `quality`：`low_confidence` / `no_hit` → **不许**拿沾边片段当依据。
2. 只允许两个补充来源：**官方文档站**`developer.flythings.cn`、**问需求方/厂家**。
3. **禁止**通用 web 搜索、Qt/Android/Flutter/emWin/AWTK/LVGL 等其它框架类推（口径见 `knowledge/uicontrols/retrieval-boundary.md`）。
4. 真的反复踩同一个空白 → 记为「未收录项」，反馈入库（这是知识库长大的方式）。

---

## 4. 已知的**能力限制**（不是没收录，是当前实现就到这）

| 限制 | 现状 / 说明 |
|------|------------|
| 性能/内存/崩溃分析 | **无**profiler / heap / coredump 类能力；真机变慢变炸只能靠 `logcat` + `selfcheck` + 人 |
| 多设备**同时**跑 | `test_run` 支持并行注入（≤4 台建议）；但**产线级批量**（几十台）需外层编排 |
| 业务断言 | 目前只有**日志断言 + 像素基线**；没有声明式「期望值 DSL」 |
| 像素基线 | 有版本化基线 + 容差档案；**无**跨设备横向基线库比对报告（多机一致性需人工看 summary） |
| 检索 | 按文档分组回归（每篇 ≥5 问法）；**未收录主题必然查不到**——这是设计，不是 bug |
| 依赖包 `example/` | 部分包未附可直接编译的最小示例（见 `packages/README.md` 状态表） |
| 平台工具链 | 不随包分发（需按 `knowledge/devflow/cli-fsc-toolchain.md` 放置）；`Z235X` 设备端工具未预编译 |

---

## 5. 与内部版的关系

- **知识库只更新 open 版**（内部版不再同步）；open 版 = 对外可交付的那份。
- 内部版多出来的，是上面 §2 那些**客户拿不到工具也用不上**的内容。
- 遇到「open 版没有但确实需要」→ 不是自己造轮子，是**提需求入库**（走本仓 PR / 让 AI 记「未收录项」）。
