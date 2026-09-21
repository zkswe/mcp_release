# blur — 高斯模糊（铺底 / 封面背景）v0.1.0

**能吃就用的东西**：一张 4 字节位图 -> 一张模糊图。专治「音乐播放器封面高斯模糊铺底」这类
需求：**切歌时算一次**，平时只是显示那张图，绝不每帧重算。

- 对外命名空间：`zk::`（头文件 `include/zk/zk_blur.h`，纯 C ABI，`extern "C"`），**源码型**
  （`include/ + src/ + example/`，整目录拷进工程即用，无包依赖）
- 依赖：**无第三方库**。只用 libc 的 malloc/memcpy/expf 与 POSIX `clock_gettime`
- 平台：见 `platforms.md`（F133/C906 已实测，其它平台标注未验证）
- 落地来源：`projects/iOSStyle-F133` 播放页铺底（"封面高斯模糊铺底"真实业务），
  真机整链路数据见 `platforms.md` §2.4 与本模块 `platforms.md` 的实测表

**版本记录**
- **v0.1.0（2026-09-21）** 首批入库：`zk_blur.h` + 档位 0~4（NAIVE2D / SEP_FLOAT / SEP_FIXED /
  BOX3 / RVV 0.7.1）+ `prep` / `darken` / `bench_once`；F133 真机实测矩阵见 `platforms.md`
  （BOX3 缩图铺底 320x200 = 59~88 ms；SEP_FIXED 查表档在本平台**反而最慢**，原因见 §4 限制）。

## 1. 用法（能直接抄）

```c
#include "zk/zk_blur.h"

/* 铺底：把 320x320 的封面 -> 320x200 的模糊背景图（显示层拉伸到 1280x800）
 * 一次算完，切歌才算；真机 F133 实测 71~88 ms */
static void makeBg(const uint8_t *coverBGRA, int cw, int ch, uint8_t **out, int *ow, int *oh) {
    const int DW = 320, DH = 200;
    uint8_t *bg = (uint8_t *) malloc((size_t) DW * DH * 4);
    zk_blur_opts_t o;
    zk_blur_opts_default(&o);      /* AUTO = RVV(有则用) / 退回 BOX3；down=4；upBack=1 */
    o.down = 1;                    /* 输出已经是缩图，内部不再二次降采样 */
    if (zk_blur_prep(coverBGRA, cw, ch, 0, /*radius=*/8, bg, DW, DH, 0, &o, ow, oh) != 0) {
        free(bg);                  /* 失败：保留上一张铺底图，别黑屏 */
        return;
    }
    zk_blur_darken(bg, *ow, *oh, 0, 84);   /* 压到 33%，保证前景文字可读（实测口径见 platforms.md） */
    *out = bg;                             /* 交给 setBackgroundBmp / 写 PNG 上屏 */
}
```

一次性「只糊不缩、输出就是屏幕尺寸」也可以（更贵，真机 1280x800 ≈ 450 ms）：

```c
zk_blur_opts_t o; zk_blur_opts_default(&o);
o.mode = ZK_BLUR_BOX3; o.down = 4; o.upBack = 1;   /* 先缩到 1/4 再糊，内部再放大回 dw x dh */
zk_blur_prep(src, w, h, 0, 32, dst, 1280, 800, 0, &o, NULL, NULL);
```

同尺寸模糊（不过缩放）最短一行：

```c
zk_blur_opts_t o; zk_blur_opts_default(&o);
o.mode = ZK_BLUR_BOX3; o.down = 1;
zk_blur_bgra(src, w, h, 0, 24, dst, 0, &o);        /* dst 可与 src 同块 */
```

## 2. API

| 函数 | 作用 |
|------|------|
| `void zk_blur_opts_default(zk_blur_opts_t *o)` | 推荐默认：AUTO / down=4 / upBack=1 / passes=3 |
| `int zk_blur_bgra(src,w,h,srcStride,radius,dst,dstStride,opts)` | 同尺寸模糊 |
| `int zk_blur_prep(src,w,h,srcStride,radius,dst,dw,dh,dstStride,opts,outW,outH)` | **铺底专用**：cover 裁切 -> 缩放 ->（可降采样）模糊 ->（可放大）-> 输出；`outW/outH` 回真实尺寸 |
| `void zk_blur_darken(buf,w,h,stride,factor256)` | 定点压暗（256 = 不变）；铺底可读性用 |
| `int zk_blur_mode_recommended(void)` / `int zk_blur_mode_active(int)` | 平台推荐档 / 实际生效档（RVV 不可用自动退回 BOX3） |
| `const char *zk_blur_mode_name(int)` | 档位名（ASCII，日志用） |
| `int zk_blur_has_rvv(void)` | 本编译产物是否带 RVV（0 = 没带） |
| `void zk_blur_set_log(zk_blur_log_fn)` | 装日志回调（`opts.logTime=1` 时打印耗时） |
| `int zk_blur_bench_once(...)` | 单档计时 + 与高精度参考的误差（bench 工具用） |

参数（`zk_blur_opts_t`）：`mode` 档位 / `down` 下采样倍率 / `upBack` 是否放大回目标 /
`passes` 盒式趟数 / `threads`（预留，当前单线程）/ `logTime`。

档位：`ZK_BLUR_NAIVE2D`(基线) / `SEP_FLOAT`(分离式 float) / `SEP_FIXED`(定点核+乘积查表+移位) /
`BOX3`(三次盒式，整数滑窗 O(1)/像素) / `RVV`(BOX3 的 RVV 0.7.1 向量化版) / `AUTO`。

## 3. 线程与内存

- **纯计算、无全局状态、可重入**；但**别在 UI 线程调大图**（1280x800 一档几十~几百 ms，
  会卡界面）——放工作线程（如工程的 `cmcore::TaskRunner`）。
- 内存峰值（1280x800、down=4 推荐档）：平面池 2×4MB + 缩放缓冲 4MB×2 + 临时 1MB×2
  ≈ **18 MB 峰值**（标量 float 档同量级；可用 REPORT 里的估算式核对）。
- 反复调用不泄漏：所有缓冲在函数返回前释放（`zk_blur_bench_once` 的参考图除外，它自己 free）。

## 4. 口径与限制

- **只吃 4 字节/像素的 BGRA**（本机 `image_load`/screencap 的字节序）。3 字节 RGB / RGB565
  请先自己转（转一次比在这里加分支便宜）。
- `radius` 上限 128；`down` 支持 1/2/4/8；alpha 当普通通道一起模糊（铺底图不透明，无副作用）。
- 边缘一律 clamp（复制边）：铺底不会出现暗角。
- 质量：`BOX3` 是高斯近似（3 趟盒式），与「分离式 float 真高斯」实测最大误差 ≤ 18/255、
  平均 ≤ 1/255（真机 F133，见 `platforms.md` 实测表）；**推荐档（BOX3 + 320x200 缩图）最大 9/255、平均 0**。
- 性能速记（真机 F133/C906）：1280x800 铺底若**输出 320x200** 只要 **71~88 ms**；
  输出全尺寸 1280x800 要 447~516 ms；`SEP_FIXED` 查表档在 C906 上**反而最慢**（核表 33KB 打爆 L1）。
- 除法用「倒数乘 + 移位」（Q16）与 `vmulhu`，不用浮点除法；定点核为 Q8（sum=256）+ 乘积查表。

## 5. 排错

| 症状 | 原因 / 处理 |
|------|------------|
| 输出全黑 | `zk_blur_*` 返回 <0（内存不足 / 参数非法）；返回值一定要看，失败就保留上一张图 |
| 结果和 PC 不一样 | 检查是否 RVV 版（`vmulhu` 截断 vs 标量「+0.5 舍入」，差 1 LSB）；`zk_blur_mode_active()` 打日志确认 |
| `zk_blur_has_rvv()==0` | 编译没带 `-march=rv64gcv0p7`（整工程级，不是单文件）；这是自动退回 BOX3，不是错误 |
| 明显糊不动 | 铺底场景用 radius ≈ 屏幕短边/25（1280x800 全尺寸输出 → 28~32；**缩图口径 320x200 → 8**） |

## 6. 文件

```
components/blur/
├─ include/zk/zk_blur.h      # 唯一对外的头
├─ src/zk_blur.cpp           # 档位 0~3 + 调度 + prep/darken
├─ src/zk_blur_rvv.cpp       # 档位 4（RVV 0.7.1；无向量编译时整体为桩）
└─ example/zk_blur_bench.cpp # 真机各档耗时/误差实测（int main，直接编成 bin 跑）
```
