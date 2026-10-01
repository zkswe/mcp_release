# platforms.md —— components/blend2d 平台矩阵与前置条件

> 规则：**在这里出现的每个平台都必须有"可用性 + 前置条件 + 实测值 + 已知限制 + 真机验收命令"**。
> 没实测的一律标 **未验证**，不写"应该可以"这类话。
> 本轮（2026-10-01）**没有新增真机动作**：真机数值全部引用前两轮证据
> （`temp/b2d_dev/REPORT.md` 原厂基线、`temp/blend2d_neon/REPORT.md` NEON 复测），来源逐条标注。

---

## 0. 总表

| 平台 | 可用性 | 依据 | 库从哪来 | 备注 |
|---|---|---|---|---|
| **Z20**（SSD201/202D/203，ARMv7-A + NEON，glibc） | ✅ **可用（已验）** | 真机跑通 + 性能/效果复测两轮 | 原厂档：注册表 `blend2d 0.11.1`；性能档：`lib/z20-neon/` | 详见 §1 |
| **Z21**（ARMv7，glibc，同族工具链） | ⚠️ **未验证** | 无实测 | 无注册表包；**理论上**可复用同一份 `.so` | 详见 §2 |
| **T113EMMC**（ARMv7，glibc） | ⚠️ **未验证** | 无实测 | 同上 | 详见 §2 |
| **V85X / T113（musl）** | ❌ **不可直接用** | `.so` 的 `NEEDED` 是 glibc + `libstdc++.so.6`；musl 平台没有 | 需 musl 重编（**未做**） | 详见 §3 |
| **F133 / F135 / F136（RISC-V64 musl）** | ❌ **不可用** | 架构不同（ELF32 ARM vs RISC-V） | 需另编（**未做**） | 详见 §3 |
| PC（x86_64，仅自测/预烘） | ✅ 可用（自测） | 上游官方支持 JIT | 上游自编 | 本组件不负责 |

---

## 1. Z20 —— ✅ 可用（**已验**）

### 1.1 前置条件

| 项 | 要求 | 说明 |
|---|---|---|
| SoC / CPU | SSD201 / SSD202D / SSD203，Cortex-A7 双核 | ARMv7-A，无 64 位；**无 JIT**（官方口径：只有 x86/AArch64 有 JIT，其他走 C++ 参考管线） |
| libc / 工具链 | **glibc**；应用构建 `arm-pc-linux-gnueabihf-gcc 8.3.0` | 与包内 `.so`（GCC 8.2.1 构建）同族，链接/ABI 无障碍（已实测） |
| 运行库 | `libstdc++.so.6`（原厂档与性能档都要）；**性能档另需 `libgcc_s.so.1`** | Z20 真机两者都有（实测跑通） |
| 头文件 | 编译期可用（≈821 KB，只吃编译机；消费侧 `-std=c++11` 可编，实测过 c++11 与 c++17） | 进固件的只有 `.so` |
| 依赖包 | `<package id="blend2d" version="0.11.1"/>`（**注册表只有 z20 有**） | 包内只有 `include/` + `lib/libblend2d.so` + 2 行 README（**无源码、无构建脚本**） |
| 固件预算 | `res` 分区（`update.img`）上限 **7,470,080 B** | 见 §1.4 体积账 |

### 1.2 实测值（真机，Z20 / 480×480 与 800×1280）

单位 ms/帧 = 「完整绘制 + `ctx.flush(SYNC)`」，**不含上屏 blit**；三组数分别来自
`temp/b2d_dev/REPORT.md`（原厂基线，另一会话）与 `temp/blend2d_neon/REPORT.md`（同会话 A/B 对照）。

| 用例（画布 / 配方） | 原厂档 | 性能档（NEON） | 变化 |
|---|---|---|---|
| 480×480 同步（默认 threadCount=0） | 28.005 | 23.707 | **−15.3%** |
| 480×480 + `threadCount=2` | 14.154 | 12.222 | −13.6% |
| 800×1280 同步 | 109.439 | 89.696 | **−18.0%** |
| 480×480 阴影 8 层 | 25.164 | 20.966 | −16.7%（−4.20 ms） |
| 480×480 阴影 2 层 | 10.442 | 9.170 | −12.2% |
| 480×480 阴影 2 层 + `t=2` | 5.693 | **5.171** | **−78.2%（vs 各自基线）→ 达标** |
| 分项 `fillAll` 纯填充 | 0.706 | 0.331 | **−53.1%** |
| 分项 文本段（3 行） | 2.44 | 2.62 | ⚠️ **未见加速** |

**帧预算口径**：40 ms 帧（25 fps）的 1/3 = 13.3 ms。
→ 原厂档 27.8 ms **不达标**；NEON 后 23.7 ms **仍不达标**；**`t=2` + 阴影 2 层 5.17 ms 达标（留 2.5× 余量）**。

### 1.3 内存 / 编解码 / 效果（实测）

- 画布：`PRGB32` = 4 B/px → 480×480 = 0.88 MB，800×1280 = 4.10 MB。
- `VmRSS`（性能档）：启动 5,708 KB → 建画布后 8,100 KB；800×1280 基准峰值 **12,516 KB**（板 total 67,916 KB / available ≈23 MB），**未见 OOM**。
- 效果：**逐字节相同**（5 个产件 md5 全等，含 800×1280 与 alpha 探针帧）；真机抓屏 vs 设备端直出 PNG 的 diff 与上一轮**数字完全相同**（1 个差异块＝透明带的非预乘 alpha 语义，与库无关）。
- 字节序/alpha：`BL_FORMAT_PRGB32` 在 ARM32 = **BGRA**（内存序 B,G,R,A，预乘）== easyui 32 位位图 → **零转换直传**；
  **配方：不透明底 + `SRC_COPY` 直传**；画布含透明时必须 `unpremultiply`（门面 `Config.unpremultiply=true`）。

### 1.4 固件体积账（实测）

```
无 blend2d                        647,720 B
原厂 .so 进 update.img           1,143,336 B   → +495,616 B
NEON  .so 进 update.img          1,262,120 B   → +614,400 B（比原厂多 +118,784 B ≈ 116 KB）
```

### 1.5 部署通道（**写死，少一步就 `initLib error`**）

| 通道 | 实测 | 适用 |
|---|---|---|
| `fun launch` | **不推**第三方包 `.so`（只推 `libzkgui.so`+`ftu`+`font`）；设备 `LD_LIBRARY_PATH` 含 `/tmp` 但**不含 `/tmp/lib`** | 只能当"推 App"用 |
| **手推 `/tmp`** | `adb push <so> /tmp/libblend2d.so` + `setprop ctl.restart zkswe` → 跑通（md5 两侧一致、无 `initLib error`） | **调试 / 换库 A-B 唯一干净通道** |
| **`src/dependencies/lib/` + `fun pack`** | 实测出 `update.img`（见 §1.4） | **量产/交付必须走这条** |

### 1.6 已知限制（Z20）

- **不是"2D 加速器"**：无 JIT、不走硬件合成（上屏仍靠框架 blit/α/旋转）；官网 x86 性能数字**不可引用**。
- 逐帧全屏（800×1280）即便 NEON 化也 **89.7 ms/帧**，**不适合逐帧动画**；定位 = 静态/低频刷新 + 小画布逐帧 + PC 侧预烘。
- 阴影靠多层半透明叠加实现（**无内建高斯模糊快捷键**）：8 层能吃掉 480×480 整帧 83% → 用 ≤2 层，或预烘成 PNG 贴图。
- 路径几何/字形轮廓**不吃 SIMD**：文本段 NEON 无收益。
- 原厂档 `.so` 已 strip（无 `.debug`、无 `.symtab`），strip 无收益；不裁剪特性（无源码/构建脚本）。
- 性能档代价：`.so` +27.2% 体积、固件 +116 KB、多一个 `libgcc_s.so.1` 依赖、**且要自己锁 commit 维护构建**。

### 1.7 真机验收命令（照抄可跑）

```powershell
# ① 建工程 + 加依赖 + 编（本组件的 example 就是现成的工程）
copy -r tools\FlyThings_mcp_open\components\blend2d\example\* C:\work\B2dCardZ20\
cd C:\work\B2dCardZ20 ; fun build -p Z20

# ② 推 App + 手推库（第三方包 .so 不会随 launch 走）
fun launch -p Z20 -s <设备IP>:5555
adb push src\dependencies\lib\libblend2d.so /tmp/libblend2d.so
adb shell setprop ctl.restart zkswe

# ③ 抓屏看效果（用 MCP 工具，别手搓 adb 截屏）
#   flythings_device_screenshot(device="<设备IP>:5555", ...)
# ④ 逐像素验收（±2 容差）
#   flythings_ui_visual(action="diff", image_a=..., image_b=..., tolerance=2)
```

---

## 2. Z21 / T113EMMC —— ⚠️ **未验证**（理论可用）

| 项 | 结论 | 依据 |
|---|---|---|
| 可用性 | **未验证**（**不写"应该可以"**） | 本机注册表**没有**这两个平台的 `blend2d` 包（`package_catalog.json` 里只有 z20） |
| 为什么"理论可用" | 都是 **ARMv7 + glibc**，与 Z20 同族工具链；`.so` 的 `NEEDED` 是 glibc 系 | 结构性判断，**不是实测** |
| 要怎么用 | 把 `lib/z20/libblend2d.so`（或 NEON 档）放进 `<工程>/src/dependencies/lib/`，Manifest 里**不要**声明 blend2d 包（没有），但需自己提供 `<blend2d.h>`（可取注册表 z20 包的头，或在工程内固定一份） | 需自证 |
| 要验什么 | ① `libstdc++.so.6`（+性能档 `libgcc_s.so.1`）在设备上存在；② 一帧卡片能上屏不崩；③ `VmRSS` 增量；④ 抓屏 vs 离屏 PNG 的 ±2 diff | 建议照 Z20 §1.7 流程 |
| 风险 | 头文件 ABI 是否与 Z21/T113 的 glibc/libstdc++ 版本兼容（Z21 真机实测 `/lib/libstdc++.so.6.0.26`） | 未取证 |

> **别拿别的平台的头凑库**（组件的通用纪律）：这里反过来 —— 库一样、头取 z20 包，**也要真机验一遍**再写结论。

---

## 3. V85X / T113(musl) / F13x —— ❌ **不可用**（别照抄）

| 平台 | 为什么不行 | 想用得做什么 |
|---|---|---|
| **V85X**（ARMv7 **musl**） | 包内 `.so` 的 `NEEDED` = `libstdc++.so.6 / libm / libdl / libc(glibc) / ld-linux-armhf.so.3 / libpthread` —— **musl 平台没有这套** | 用 musl 工具链**重编** Blend2D（`-DBLEND2D_NO_JIT=ON`；musl 下还要注意 `libstdc++` 依赖）—— **未做** |
| **T113（musl 变体）** | 同 V85X（libc 不匹配） | 同上 —— **未做** |
| **F133 / F135 / F136**（**RISC-V64 musl**） | 架构不同（本组件给的是 ELF32 ARM），根本加载不了 | 用 RISC-V musl 工具链重编（RISC-V 同样**无 JIT**，走参考管线；文本/路径性能同理）—— **未做** |

---

## 4. ⚠️ 未验证事项（引用本文时**不得**当结论）

1. **Z21 / T113EMMC** 上的任何使用（本组件所有真机数字**只属于 Z20**）。
2. **本组件形态的真机回归**（Z20 上的真机证据来自 `temp/b2d_dev/` 与 `temp/blend2d_neon/` 两个基准工程，
   用的是等价的直接调用代码；`zk::b2d` 门面本身的真机跑通**待做**）。
3. **`setInvalid(!isInvalid())` 在"高频逐帧 800×1280 全屏"下**的表现（480×440 已在真机跑过；全屏逐帧本来也不推荐）。
4. 性能档在**其它 glibc ARMv7 板**上的 `libgcc_s.so.1` 存在性（Z20 有，别板未查）。
5. 上游 master 与 0.11.1 的行为差异（本组件**只对 0.11.1 / commit `a7f9476`** 负责）。
6. 包的服务端元数据（发布者 / 构建脚本）—— 包里没有，SPA 页面抓不到。
