# 证据说明（2026-09-16 21:2x **更正**）

> **更正前一版结论**：早前曾判定 `01/02/03/04/05` 与 `10/11/12` 是「另一个案例的画面」而作废。
> **该判定是错的**，已撤回、文件已移回。经视觉复核，这些帧**就是本 example 的演示页**
> （画面里是 `HARD r=4/8/14` 与 `AA r=4/8/14` 三档半径对照 + 「四态」区 + 状态日志行），
> 且日志文本与 `README.md` §7 记录的 step1/step2/step5 序列一一对应。

真实发生的事（也是上一轮另一任务证据失效的原因）：**Z21 被本 example 顶掉了** ——
另一个任务的 25 张「重复帧」（hash `ead1067b37…`）正是这个演示页的静止画面，
所以那次才出现「抓了一堆图其实都是同一张」。**根因是设备排队，不是本包证据造假。**

## 现状

| 文件 | 结论 |
|---|---|
| `01_initial_full.png` | 首帧：三档半径上下对照 + 四态盒 + 探针 + `.9.png` 按钮 —— **有效** |
| `02_state_pressed.png` / `03_toggle_selected.png` | step1/step2 状态帧（日志行可核对）—— **有效** |
| `04_press_held_true.png` / `05_press_rolled_back_and_radius28.png` | 按住态 + 回落 + `setRadius(28)` —— **有效** |
| `10/11/12_*diff*.png` | 基于上述帧的像素 diff —— **有效** |
| `06/07/08/09_zoom8x_*.png` | 8x 放大对照（HARD vs AA / 三条路线）—— **有效**（来自上面这些帧的裁切） |

⚠️ 唯一仍需注意的：`platforms.md` §1.1 的**数字**建议在做完「§7.1 重测」后引用；
在重测之前，它们是这一轮实测的结果（脚本 `tools/aa_ideal.py` / `tools/aa_measure.py` 可复现）。

---

## 追加：0.1.1 「药丸圆钮外露方角」修复轮（2026-09-16 22:0x，同一台 Z21）

与上面 01–12 是**同一台设备、同一个 example**，只是包版本从 0.1.0 升到 0.1.1（钮从「铺底盒 + 圆角矩形」
改成**图层叠加**，`P == 0` 的像素不画）。文件名 13–19 续编，另加 `FIX_*` 两个日志。

| 文件 | 结论 |
|---|---|
| `13/14_pill_corner_before_after_zoom8x_*.png` | 8× LANCZOS 左右对照（Team on/off）：左方角 / 右圆滑 —— **有效**（主证据） |
| `15_pill_corner_after_zoom8x_all_four.png` | 修后四帧放大总览 —— **有效** |
| `16_diff_before_after_team_on.png` | 默认口径 diff：整帧原始差 24 px（被默认降噪算子抹平，看图不看数字） —— **有效** |
| `17_diff_STRICT_before_after_team_off.png` | 严格口径 `--open 0 --min-area 1 --shift 0`：4 处 / 66 px —— **有效**（要数字看这张） |
| `18_local_render_zoom8x_before_after_on.png` | 上机**前**本地渲染桩 + 独立 16× 参考模型 —— **有效**（修前复现 PURE=6，位置与设备逐点一致） |
| `19_device_after_switch_team_on.png` | 修后设备帧，md5 `5b8a03e6f3b6` —— **有效** |
| `FIX_metric.log` | 修前/修后同一口径：PURE 6/钮 → **0**；NEAR 6 → 0；LOOSE 18 → 16 —— **有效** |
| `FIX_local_check.log` | 本地 8 项自检（含 `fillRect` 542→496） —— **有效** |

⚠️ 本轮的诚实标注（避免以后误引用）：

- **修前帧不在本目录**：在案例工程 `projects/translate/lvgl-widgets-uiv1/z21/evidence/zzb_*`（`zzc_*` 全量 20 张 + `STATUS.md` §12 也在那里）；
- `MODE_HARD` 路径**未修**（按要求保留对照）→ 13/14/15 里的 HARD 档仍会露方角，**这是有意为之**；
- 设备 `main.ftu` 5858 → 5953 B 是 `fsc build` 重打包所致，UI 内容未变；
- 第一轮上机曾把钮写坏（SDF 末项 `max(...,0)` 写成 `min(...,0)`）→ 钮被侵蚀；**当时 PURE 也是 0**，
  靠与修前帧逐像素比（差 756 px）才发现。已改为「先本地桩 + 参考模型验证再上机」。
