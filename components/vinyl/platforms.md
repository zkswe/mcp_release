# platforms.md —— `zk::VinylSpin` 平台实测

> 口径规矩：**没实测的写「未验证」，禁止写「应该可以」**。每格给前置条件与真机读数。

## 依赖与前置条件

| 依赖 | 必需 | 说明 |
|---|---|---|
| `easyui` | ✅ | `ZKBase::setBackgroundBmp` / `bitmap_t` / `misc::image_load` / `misc::bitmap_scale`（2.9.0 实测） |
| `log` | ✅ | `LOGD/LOGW` |
| `nanovg 1.0.0` | ⭕ 仅 nanovg 后端 | **只支持 BGRA 目标**；设备 `/lib/libnanovg.so` 与注册表包同为一份构建（F133 实测符号逐条相同） |
| 线程 | ✅ | 组件内自带单线程任务队列（`zk_vinyl_worker`，pthread） |

- **无浮点**：定点后端为纯整数 Q16 反向映射；覆盖率表为 SS=8 整数面积平均 → 符合「SW15x/SW202x 禁浮点」口径。
- 宿主控件必须**正方形**（`attach()` 校验）；建议 240~400px（320 为实测档）。

## 实测表

| 平台 | 定点后端 | nanovg 后端 | 每帧耗时（定点 / nanovg） | 备注 |
|---|---|---|---|---|
| **F133**（C906 / musl，1280×800，rotate=270） | ✅ 实测（`projects/iOSStyle-F133` 播放页） | ✅ 实测 | **6~12ms / 23~44ms**（320×320） | 定点 12.3~12.6fps、CPU 42~50%；nanovg 11~12fps、CPU 60~69%；两者均无方角/暗边 |
| F135 | 未验证 | 未验证 | — | 与 F133 同核（C906 RISC-V），预期一致（待测） |
| Z20 / Z21 | 未验证 | 未验证（注册表有 nanovg 包则可用） | — | 待测 |
| T113 | 未验证 | 未验证 | — | 待测 |
| V85X | 未验证 | 未验证 | — | 待测（若是 MCU Lite 平台，本组件**不适用**：那是 `.form`/`zkres.bin` 体系） |

## 刷新口径（各平台一致，务必照做）

位图只 `setBackgroundBmp` 交一次 → 之后每帧 `host->setInvalid(!host->isInvalid())` 翻转刷新。
**不要** `invalidate(&getAbsolutePosition())`：该 rect 是**控件本地坐标系**，传绝对矩形会被裁成"右下角一块"
（F133 实测：20° 步进下采样点位移 **0px**，改翻转后 **35px**，理论 34.7px）。

## 真机验收命令（F133 举例）

```bash
# 部署后进播放页，看日志里的每帧耗时与帧率
adb -s <设备IP>:5555 shell "logcat -d -v time | grep 'vinyl:' | tail -n 5"
# 功能判据（静态走 20°，采样点位移应 ≈34.7px）
touch /tmp/vinyl_marker /tmp/vinyl_nomask && echo 20 > /tmp/vinyl_step
python temp/mu_vinyl/inv_sweep_marker.py 0
```

## 未做/已知限制

- 目前只有 **f133** 走完整验收；其余平台是「同一份源码 + 同一套 easyui 接口」，但**未实测**。
- nanovg 后端在 320×320 下约 23ms/帧；实测 `NEAREST` 采样 / 去 memset / pattern-angle **都省不下来**，
  只有**降分辨率**（160×160 ≈ 5.4ms）或**降帧率**有效（见 README §5 坑 5）。
