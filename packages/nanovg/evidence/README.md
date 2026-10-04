# evidence/ —— 本包的真机证据

> 别的包（`zkhardware`、`zknet`…）在这里放**真机截图 + logcat 摘录**。本包现在**也有**了。

## 有什么

| 证据类型 | 在哪 | 说明 |
|---|---|---|
| **V85X 真机证据**（2026-10-03） | **`v85x-device/`** | 功能矩阵 12/12、上屏截图 + 离屏对照（±2，max\|Δ\|=0）、帧耗时、`VmRSS`、5 个可复现探针源码 |
| 档位凭据（体积/md5/ELF 属性/NEEDED/节表） | `../lib/v85x/BUILD.md` §1–§2 | `readelf` 实测，命令在 §6 |
| 符号审计（头文件 105 vs 导出 85，脏导出 0） | `../lib/v85x/BUILD.md` §3 | 脚本逻辑：解析两份头 + `readelf --dyn-syms` |
| 已知缺口（20 条字体 API 未编） | `../lib/v85x/BUILD.md` §4 | 同上 |
| F133 侧性能/质量（**借**组件证据） | `components/vinyl/platforms.md`、`components/vinyl/README.md` | 同一后端调用路径，320×320 约 23~44 ms/帧 |

## V85X 真机这一轮的关键结论

1. **库本身能用**：`nvgCreateAGG` 在 V85X（ARMv7 musl）上跑通，无缺符号；路径/描边/AA/变换/裁剪/
   alpha 合成/贴图 1:1 **12 项全 PASS**，采样 `|Δ| = 0`；**2.48 ms/帧 @320×240**、`VmRSS` 1668 kB。
2. **上屏链路逐像素一致**：`setBackgroundBmp` 交出去的位图与 fb0 上屏像素 **440×440 = 193,600 px
   `max|Δ| = 0`**（两路独立采集）。
3. ⛔ **两处实测落差（原标注 ✅）**：**渐变全族失效**（退化纯内色）、**`nvgImagePattern` 不平铺**。
   详见 `v85x-device/README.md` 与 `../platforms.md §1.4`。

## 还没有的

1. **F133 本包自跑**：F133 数字仍是借 `components/vinyl` 的（同 `.so` 等价调用，但非本包链路）。
2. **T113EMMC / F136 真机**：只有注册表存在性。
3. **上游 nanovg 与厂家 AGG 后端的行为差异未穷举**：已确认渐变/平铺两项，其余 API 未逐条对拍。
