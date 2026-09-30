# Z235X 设备端预编译工具（暂缺，占位说明）

> 状态：**本目录目前没有任何可执行工具**。请不要把它当成「Z235X 设备端工具已就绪」。
> 为什么要放这个文件：`platforms.py` 把 Z235X 登记为可建工程平台（`templates/HelloWord_Z235X` 已入库），
> 门禁 `scripts/check_consistency.py::stage_platforms()` 要求 `bin_tools/<平台>/` 目录真实存在，
> 而 Z235X 的设备端工具**还没编译**——这里如实说明，不伪造二进制。

## 缺什么

`bin_tools/<平台>/` 的标准内容（其它平台都有）在 Z235X 上**尚未提供**：

| 工具 | 用途 | Z235X 现状 |
|---|---|---|
| `touch` | 触摸注入（tap / swipe / long / monkey / raw） | 缺 |
| `busybox` | 设备端调试（ps / ifconfig / ping / dd / hexdump…） | 缺 |
| `ui_test` | UI 自动化（tap / swipe / monkey / run script） | 缺 |
| ~~`mt_test`~~ | **2026-09-30 已移除**：能力由 `touch` 覆盖（自动判协议） | — |
| `zkshot` | 设备端抓屏 | 缺 |

## 为什么缺

- Z235X 此前只做「依赖包生态」登记：`package_catalog.json` 有 `z235x` 键（17 个包，chip = SSD2355），
  但 MCP 侧既没有 IDE 模板、也没有设备端工具（当时口径：`platforms.PACKAGE_ONLY`）。
- 本次入库的是**IDE 模板**（`templates/HelloWord_Z235X`，来自钟工给的 `HelloWord_z235x` 工程）
  \+ `platforms.py` 登记（`PLATFORMS['Z235X']`，`arch: arm`）。
- 设备端工具需要 **Z235X 样机 + 该平台的工具链**才能编译；Z235X 的架构/ABI 与现有平台不一定相同，
  **禁止拿其它平台的 ELF 顶替**（会静默失败或打崩应用）。

## 怎么补

1. 拿到 Z235X 工具链与样机（找钟工/厂家）；
2. 按仓库既有口径重编静态工具：busybox 见 `scripts/bb_build_all.sh`（输出 `tools/busybox/bin/<平台>/busybox`），
   `touch` / `ui_test` / `zkshot` 见 `tools/touch_inject/`、`tools/zkshot/` 的构建脚本；
3. 产物放进本目录 → 跑 `python scripts/gen_manifest.py`（刷新 `tools_manifest.json` 的平台/工具面）
   → 跑 `python scripts/check_consistency.py --with-tests` 确认门禁全绿。

## 影响（对使用者）

- `flythings_create_project(platform="Z235X")`：**可用**（模板已入库）。
- `flythings_gen_ui_test` / 设备端抓屏 / 触摸注入等**依赖设备端工具**的能力：在 Z235X 上会**明确报缺**
  （列出当前可用平台），不会静默降级或误用别平台工具。
