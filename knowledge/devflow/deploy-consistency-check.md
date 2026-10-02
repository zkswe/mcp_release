---
id: devflow-deploy-consistency-check
title: 部署一致性（新库旧界面 / resPath 与 startupLibPath 混搭）
category: devflow
status: review
confidence: manual
verified_at: 2026-10-01
stale_days: 180
origin: partial
source: 2026-10-01 真机部署复核（480×480 Z20 面板：/tmp/lib 新 + resPath 指 /res/ui 旧）
needs_evidence: true
platforms: [Z20]
tags: [改了像没改, 新库旧界面, resPath, startupLibPath, EasyUI.cfg 优先级, 部署后自检, 界面还是旧的, 覆盖层混搭]
evidence:
  - "2026-10-01 实测：设备 /tmp/EasyUI.cfg 的 startupLibPath=/tmp/lib/libzkgui.so（新构建）而 resPath=/res/ui/（旧版）→ 界面是旧的、库是新的"
  - "同机 /tmp/ui 的 14 个 ftu 与本地构建逐文件 md5 全等，但 resPath 不指它 → 推了等于没推"
  - "selfcheck 第⑪区「部署一致性」实测可读出：生效 cfg 源 / resPath / startupLibPath / lib 与 ui 的两代 md5 对比"
---

# 部署一致性（新库旧界面 / resPath 与 startupLibPath 混搭）

> 检索导引：改了像没改 / 界面还是旧的 / 推了没生效 / **新库旧界面** / resPath 与 startupLibPath /
> EasyUI.cfg 优先级 / 覆盖层（/tmp）与固化区（/res）混搭 / 部署后自检 / lib 换了界面没换。
> 用途：**部署/推送后立刻自检**，把「界面没更新」这类误判在源头掐掉。

## 0. 一句话

`EasyUI.cfg` 里 **`startupLibPath`（程序库）与 `resPath`（界面资源）必须指向同一次部署的产物**；
只改一个（最常见：只换 lib、`resPath` 还留在 `/res/ui/`）→ 跑的是 **「新库 + 旧界面」**，
症状与「改了没生效 / 布局不对劲 / 控件没变」完全一样，**极易误判成代码或控件问题**。

## 1. 生效顺序（读设备侧只认这个）

| 优先级 | 路径 | 说明 |
|---|---|---|
| ① | `/tmp/EasyUI.cfg` | 调试/覆盖态（tmpfs，**重启即空**）；`fun launch` 与手工部署都写这里 |
| ② | `/mnt/extsd/EasyUI.cfg` | 外置卡覆盖（**历史事故源**：旧卡会把程序劫持到旧 lib/旧 ui） |
| ③ | `/res/etc/EasyUI.cfg` | 固化态（随 `update.img` 走，这才是量产口径） |

字段对照：`startupLibPath` = 程序库（`.so`）；`resPath` = 界面资源目录（`*.ftu` + `images/`）；
`font` / `languagePath` / `rotateScreen` / `rotateTouch` 同理，**一次部署要成套**。

## 2. 四步部署后自检（照抄）

1. **看生效配置**：`cat /tmp/EasyUI.cfg /mnt/extsd/EasyUI.cfg /res/etc/EasyUI.cfg`（按上表取第一个存在的）
   → 记下 `resPath` 与 `startupLibPath`，**确认两者同源**（都在 `/tmp`，或都在 `/res`）。
2. **对账库**：`md5sum /tmp/lib/libzkgui.so /res/lib/libzkgui.so` + 与本地产物 md5 比 → 生效的那份必须是本次构建。
3. **对账界面**：`md5sum /tmp/ui/*.ftu` vs `/res/ui/*.ftu`，并与本地 `ui/*.ftu` 比 → **`resPath` 指向的那一份**必须与本次 `fui pack` 的产物一致。
4. **对账运行态**：`getprop sys.zkapp.state` = `running`，且进程 maps 里出现 `startupLibPath` 指向的 `.so`
   （`for p in /proc/[0-9]*; do busybox grep -q zkgui $p/cmdline && busybox grep libzkgui $p/maps; done`）。

> 一键版：**`flythings_selfcheck(device=...)` 第⑪区「部署一致性」** —— 直接给
> `effectiveCfg / resPath / startupLibPath / overlay / mixed / 两代 lib 的 md5 / 两代 ui 的 ftu md5 差异页`，
> `mixed=true` 就是混搭（`ok=false` + hint 写清修法）。

## 3. 处置

| 情形 | 修法 |
|---|---|
| 只想调试新界面 | 把 `resPath` 与 `startupLibPath` **一起**指到 `/tmp` 同一次部署的目录，再 `setprop ctl.restart zkswe` |
| 想退回固化态 | `rm -rf /tmp/lib /tmp/EasyUI.cfg /tmp/ui` → `setprop ctl.restart zkswe`（`/tmp` 是 tmpfs，重启也会自动清） |
| 现场「推上去没效果」 | 顺序：① 本表 1-4 步（先排除混搭 / extsd 劫持）② 再查 `fui pack` 产物是否最新 ③ 最后才怀疑代码/控件/版本 |

## 4. 别忘的两条纪律

- **`/tmp` 部署前先看余量**：`/tmp` 是 tmpfs（常见 32MB 量级），推 lib 前 `df -k /tmp`；
  空间不够时**先删旧件再解压**（本次实测：先 `cp` 备份再 `gunzip` 会把 tmpfs 写满，
  解压出半截文件；**解压后必须 md5 对账再 `mv` 覆盖**，不匹配就中止、别动线上件）。
- **脚本 ASCII only**（Windows PowerShell 5.1 按 ANSI 读 `.ps1`，带中文会引号错乱解析失败）。

## 5. 相关

- `EasyUI.cfg` 字段全集与 `package.properties` 覆盖机制：`knowledge/devflow/package-properties-easyui-cfg.md`
- 固化升级包（`update.img`）与 `/res` 分区上限：`knowledge/devflow/upgrade-pack-image.md`
- 抓屏方向只认工程 `EasyUI.cfg` 的 `rotateScreen`：`knowledge/devflow/device-screenshot.md`
- 界面「改了像没改」的另一半原因（ftu/json 自动同步回退）：`knowledge/devflow/ui-layout-verify.md`
- scrollwindow 布局返工清单：`knowledge/uicontrols/scrollwindow-layout-checklist.md`
