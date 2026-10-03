# evidence/ —— 本包**没有真机证据**（说明为什么，不放伪造日志）

> 本目录存在的意义：别的包卡位（`zkhardware`、`zknet`…）在这里放**真机截图 + logcat 摘录**。
> nanovg 目前**没有**这类东西，就**明说**，而不是凑一段日志充数。

## 现在有什么（可复现、机器可核）

| 证据类型 | 在哪 | 说明 |
|---|---|---|
| 档位凭据（体积/md5/ELF 属性/NEEDED/节表） | `../lib/v85x/BUILD.md` §1–§2 | `readelf` 实测，命令在 §6 |
| 符号审计（头文件 105 vs 导出 85，脏导出 0） | `../lib/v85x/BUILD.md` §3 | `python temp/nvg_audit.py`（脚本逻辑：解析两份头 + `readelf --dyn-syms`） |
| 已知缺口（20 条字体 API 未编） | `../lib/v85x/BUILD.md` §4 | 同上 |
| F133 侧性能/质量（**借**组件证据） | `components/vinyl/platforms.md`、`components/vinyl/README.md` | 同一后端调用路径，320×320 约 23~44 ms/帧 |

## 没有什么（= 待补）

1. **V85X 上屏截图**（`nvgCreateAGG` → 画 → `setBackgroundBmp` → 抓屏）。
2. **逐像素比对**（与离屏出图对照，±2 容差）。
3. **帧耗时 / `VmRSS`**（V85X 真机读数）。
4. 设备侧是否存在 `libgcc_s.so.1`（本档 `NEEDED`）。

## 怎么补（照抄）

```bash
# 1) 工程侧：头文件 + lib/v85x/libnanovg.so 进 src/dependencies/lib/（见 ../README.md §2）
# 2) 真机：fun build -p V85X && fun launch（第三方 .so 手动推 /tmp 或走 fun pack）
# 3) 抓屏：flythings_device_screenshot(device="<V85X 设备>")   # 别手搓 adb screencap
# 4) 比对：flythings_ui_visual(action="diff", image_a=..., image_b=..., tolerance=2)
# 5) 性能：/proc/<pid>/stat 的 utime+stime + VmRSS（组件侧脚本 references/kb/… 有口径）
```

补完把截图/日志放本目录，并把 `../package.yaml` 的 `verified` / `status` 与 `../platforms.md` §1.3 一起改掉。
