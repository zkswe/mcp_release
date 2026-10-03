# platforms.md —— nanovg 1.0.0 平台矩阵与前置条件

> 口径：**没实测的写「未验证」，不写「应该可以」**。逐条给依据（注册表 / 设备读数 / 符号审计）。
> 本包**没有独立真机证据**：F133 侧的数字来自 `components/vinyl` 的真机 A/B（那是用同一份 .so 的等价调用），
> V85X 档只有**符号级**核对。详见 `evidence/README.md`。

---

## 0. 总表

| 平台 | 可用性 | 依据 | 库从哪来 | 备注 |
|---|---|---|---|---|
| **V85X**（ARMv7 **musl**） | ⚠️ **未上真机**（符号级已核） | 本仓 `lib/v85x/libnanovg.so` 的 `readelf` 实测 | **本仓自带**（服务端无此包，`v85x/nanovg/1.0.0.zip` → 404） | 见 §1 |
| **F133**（RISC-V64 musl） | ✅ 有真机证据（**借** components/vinyl 的） | `components/vinyl/platforms.md`：nanovg 后端 320×320 约 23~44 ms/帧 | 注册表 `public/f133/nanovg/1.0.0` | 见 §2 |
| **T113EMMC**（ARMv7 glibc） | ⏳ 未验证 | 注册表有此包（API 实测 `1.0.0` 存在） | 注册表 `public/t113emmc/nanovg/1.0.0` | 与 Z20 同 libc 族 |
| **F136**（RISC-V64 musl） | ⏳ 未验证 | 注册表有此包 | 注册表 `public/f136/nanovg/1.0.0` | 与 F133 同核 |
| **Z20 / Z21 / T113** | ❌ **不可用** | 服务端与本地注册表**都没有**这个包（API：`package not found`） | — | 想用得自带 `.so` 并自证（无 F133 那类证据） |

---

## 1. V85X（本仓自带档）—— ⚠️ 未上真机

### 1.1 前置条件（实测口径）

| 项 | 要求 | 说明 |
|---|---|---|
| CPU / ABI | ARMv7-A（`Tag_CPU_name "7-A"` / `v7` / `VFPv3` / `NEONv1`） | 与 V85X 工具链同族 |
| libc | **musl**（`NEEDED = libc.so`） | **glibc 板装不了这份** |
| 运行时 | `libgcc_s.so.1` | 本档第二条 `NEEDED` |
| 头文件 | `include/nanovg.h` + `include/nanovg_agg.h` | **本次随包补上**（设备侧 .so 不带头文件） |
| 目标缓冲 | 32 位 **BGRA**、`pitch = w*4` | 与 easyui `bitmap_t` 同位图布局 |

### 1.2 档位信息

```
文件 : packages/nanovg/lib/v85x/libnanovg.so
体积 : 47,552 B
md5  : F5F1157D50AB4A882B464D33804E5B1B
编译器标记 : OpenWrt/Linaro GCC 6.4-2017.11 6.4.1（与 V85X 工具链同源）
符号 : dynsym 193 条，其中 defined 155 / UND 35；导出 nvg* 85 条（含 nvgCreateAGG / nvgReinitAgge / nvgDeleteAGG）
已 strip : 无 .symtab / 无 .debug
```

### 1.3 还差什么才算「可用」

1. 真机跑通一帧（`nvgCreateAGG` 建上下文 → 画 → `setBackgroundBmp` 上屏）并抓屏留证；
2. 与离屏出图做 ±2 逐像素比对；
3. 记每帧耗时与 `VmRSS`。
   → 命令口径照 `components/vinyl/platforms.md`（同一套后端调用）。

---

## 2. F133 —— ✅ 有真机证据（借用，非本包自跑）

- 证据出处：`components/vinyl/platforms.md`（`projects/iOSStyle-F133` 播放页，1280×800 / rotate 270）。
- 关键数字（同一份注册表包 `.so`）：nanovg 后端 **每帧 23~44 ms @320×320**；定点自绘对照 6~12 ms。
- 结论（原文口径）：**默认仍用定点**，nanovg 作为一行可切的后端保留。
- ⚠️ 本包**没有**自己重跑这套，所以 `package.yaml` 里 `verified: null`，状态写 `borrowed-evidence`。

---

## 3. Z20 / Z21 / T113 —— ❌ 不可用（别照抄）

| 平台 | 为什么不行 | 想用得做什么 |
|---|---|---|
| Z20 / Z21 | 服务端**没有** nanovg 包；设备 `/lib` 里 Z21 有一份 `libnanovg.so`（50,984 B，**glibc**）但**没有头文件**，且那是设备自带、不保证随固件版本还在 | 自带头文件 + 用设备那份（风险高），或找厂家要 Z20/Z21 包；**必须先按 §1.3 自证** |
| T113（musl 变体） | 与 V85X 同 libc，但服务端无此包 | 同 V85X 做法（自带头 + `lib/v85x/` 那份，**但 ABI 未证**）→ 得先验 |

---

## 4. 未验证清单（引用本文时不得当结论）

1. **V85X 真机上的任何数字**：本档只有 ELF/符号级读数，没有上屏、没有帧耗时、没有逐像素。
2. **T113（musl）复用 V85X 那份 `.so`**：ABI 族相同但未验（VFPv3 标记、符号集合已核，运行时未跑）。
3. F133 的每帧数字**只属于 `components/vinyl` 那条调用路径**（320×320 圆盘贴图），不是本包的通用性能。
4. 上游 nanovg 与厂家 AGG 后端的**行为差异**未逐项比对（本包只对 1.0.0 这份构建负责）。
