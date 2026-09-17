# platforms.md —— WheelPicker（滚轮选择器）平台说明

> 口径：**没实测的写"未验证"**，不写"应该可以"。
> 本包只依赖 easyui 自带 `painter` + `textview`，无第三方库、无平台分支（业务层代码里不出现平台名）。

## 1. 逐平台

| 平台 | 可用性 | 前置条件 | 实测值 | 已知限制 |
|---|---|---|---|---|
| **Z21**（1024×600，36MB RAM，无 GPU） | ✅ **可用（真机验收）** | ① 工程 `Manifest.xml` 声明 easyui/log/base-utility；② 宿主提供 **≥ visibleRows 个 `textview`** 承载文字；③ `onUI_init` 里 `INIT_UI_TIMERS` + `REGISTER_ACTIVITY_TIMER_TAB = {{0,16}}`；④ `onmainActivityTouchEvent` 转发 `MotionEvent` | 两轮合计 `tick()` **avg 8~10 µs / max 12~26 µs**；单轮 avg 1~2 µs / max 4~6 µs；进程 CPU **0.4%**（静止）；`VmRSS 5824 kB`（26 控件工程） | ⚠ **未被触摸的那一列 `setItems()` 后可能残留一行旧像素**（平台按控件标脏、又无区域标脏 API，见 §2）；多列同帧同步未做 |
| **F133** / F135 | ⚠ 仅编译（`fun build -p F136` 平台串 = RISC-V） | 同上 | **未上机** | 未验证 |
| **Z20** | ⚠ 未验证 | 同上 | — | 未验证（Z20 字库/内存更紧，行池过大要评估） |
| **T113** | ⚠ 未验证 | 同上 | — | 未验证 |
| **V85X** | ⚠ 未验证 | 同上 | — | 未验证 |

## 2. 设备端 libeasyui 符号事实（**最容易翻车的地方**）

Z21 设备 `/lib/libeasyui.so` 是 **2024-07-10** 版本，比仓库里的 easyui 头文件**旧**。本包只调用**设备端确实导出**的符号：

| 符号 | 设备端 | 说明 |
|---|---|---|
| `ZKBase::setPosition(const LayoutPosition&)` | ✅ | 行位移动 |
| `ZKBase::setVisible(bool)` | ✅ | 行隐藏/显示 |
| `ZKBase::setInvalid(bool)` | ✅ | 帧刷新/标脏（RadButton 同款路径） |
| `ZKTextView::setText / setTextColor / setAlignment / setTextSize` | ✅ | 行文字 |
| `ZKPainter::erase / fillRect / drawRect` | ✅ | 静态层 |
| `ZKBase::setSourceColor`（painter 取色） | ✅ | 每笔填充前必须设 |
| **`ZKBase::invalidate(const LayoutPosition*)`** | ❌ **未导出** | 用它会 `1.initLib error: undefined symbol: _ZN6ZKBase10invalidateEPK14LayoutPosition` → **整屏黑**；与 D20（`getAbsolutePosition()`）同源，属"设备库比头文件旧"族 |

复核办法（一条命令，别靠猜）：

```bash
adb -s <dev> shell "/tmp/busybox strings /lib/libeasyui.so | /tmp/busybox grep -E '^_ZN6ZKBase|^_ZN10ZKTextView' | sort -u"
```

**本包因这个限制的取舍**：不给移动的 textview 做"按区域标脏"，而是**移动/换字/改色时顺手 `setInvalid(true)`**；对**正在被触摸的列**完全有效（左轮实测干净）。旁列在 `setItems()` 后的残留问题见 README §已知未做（两个收尾方案待选）。

## 3. 与控件面/工具链的关系

- **不需要出图**：无 PNG/.9.png 依赖（选中带/分隔线全自绘，文字走平台字体）。所以 `verify_assets` / 铁律 #9 的图片规则对本包不适用。
- **不做自绘键盘、不接管键盘**；只接管落在滚轮盒内的触摸（`hitTest` 命中才消费，`return true` 让宿主吞掉）。
- 字库：行文字走**设备字体**，受裁剪字库限制（不支持 emoji/特殊符号）→ 建议只放汉字/ASCII。
- 帧循环是宿主定时器（16ms）；静止时 `tick()` 走快路径（实测可忽略），宿主也可按 `tick()` 返回值决定是否停表省电。

## 4. 真机验收命令（Z21）

```bash
cd components/ui_v1/WheelPicker/example
fun build -p Z21                      # 编译
python tools/deploy.py                # reboot + 整包部署 + kill zkgui（init respawn）
# 甩动 / 点击验证
adb -s <设备IP>:5555 shell "/tmp/touch swipe 148 290 148 100"
python tools/deploy.py --no-reboot    # 只换文件（不重启）
```

证据：`example/evidence/*.png`（初始 / 甩动后 / 各次修复后）、`evidence/EasyUI.cfg`（部署配置留档）。
