# platforms.md —— WheelPicker（滚轮选择器）平台说明

> 口径：**没实测的写"未验证"**，不写"应该可以"。
> 本包只依赖 easyui 自带 `painter` + `textview`，无第三方库、无平台分支（业务层代码里不出现平台名）。

## 1. 逐平台

| 平台 | 可用性 | 前置条件 | 实测值 | 已知限制 |
|---|---|---|---|---|
| **Z21**（1024×600，36MB RAM，无 GPU） | ✅ **可用（真机验收）** | ① 工程 `Manifest.xml` 声明 easyui/log/base-utility；② 宿主提供 **≥ visibleRows 个 `textview`** 承载文字；③ `onUI_init` 里 `INIT_UI_TIMERS` + `REGISTER_ACTIVITY_TIMER_TAB = {{0,16}}`；④ `onmainActivityTouchEvent` 转发 `MotionEvent`；⑤ **滚轮放进带偏移的容器时必须 `setTouchOrigin(容器left, 容器top)`** | 两轮合计 `tick()` **avg 8~10 µs / max 12~26 µs**；单轮 avg 1~2 µs / max 4~6 µs；进程 CPU **0.7%**（静止）/ **18.4%**（连续甩动 10 次/5s，单核口径；0.2.0 加 36fps 布局上限后，优化前 26.2%）；`VmRSS 5824 kB`（26 控件工程）；**5 列同帧 tick（TDesign 案例，页面 window 内）**：整页 35 控件，联动/滚动/回填均验证 | ⚠ 触摸坐标是**父相对**（`getPosition()`）而事件是**屏幕绝对**：装在带偏移容器里必须 `setTouchOrigin()`，否则 hitTest 整列偏移、拖不动（0.1.0 阶段 4 真实踩到并已提供接口）；⚠ `setIndex(animate=true)` 不跟踪目标（“甩一下”语义）；多列同帧同步未做（联动仍是「停下后重建」） |
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
- **触摸坐标系**（§2 符号之外的另一条实测结论）：本包用 `painter->getPosition()`（**父相对**）做命中判定与「点某行选中」的计算；
  事件坐标是**屏幕绝对**。两者只在「滚轮直接挂根节点」时相等 —— 这也是 example 能跑的原因。
  放进页面 `window`（本例 y=56）后必须 `setTouchOrigin(winPos.mLeft, winPos.mTop)`，否则整列命中区偏 56px（真机现象：看得见、拖不动）。
  设备端 `ZKBase::getAbsolutePosition()` 未导出（D20 同族），包内不能自己换算，只能由宿主告知。
- 字库：行文字走**设备字体**，受裁剪字库限制（不支持 emoji/特殊符号）→ 建议只放汉字/ASCII。
- 帧循环是宿主定时器（16ms）；静止时 `tick()` 走快路径（实测可忽略），宿主也可按 `tick()` 返回值决定是否停表省电。
- **内存（Z21 36MB 总内存，真机实测）**：滚轮本身不占大内存（painter 自绘 + 池里 textview），
  但**宿主的底图别用整屏大 PNG**：本案例首版给 3 个弹层各出一张 1024x392 的卡片图，
  解码 RGBA 各要 1.6MB/1.1MB/1.6MB -> 启动时连续 `MMA Alloc ... fail` 然后进程被 OOM kill
  （现象：部署后 zkgui 不在了、屏幕黑）。改法：大底图一律走 **.9.png**（解码只占几十字节，引擎拉伸）。

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
