# example —— Calendar 最小可跑示例（Z21 1024×600）

> 这个目录就是一个**能编、能跑的 FlyThings 工程**（只留必要文件，没有 `fun.exe`/`fui.exe`/`.fun/` 产物）。
> 真机验收证据在 `evidence/`。原样搬到开发工作区即可跑。

## 文件清单

| 文件 | 作用 |
|---|---|
| `Manifest.xml` | 依赖声明（easyui ^2.2.0 + log/zkhardware/zknet/base-utility） |
| `.deps.lock` | 依赖解析结果快照（实际落到 easyui 2.6.0） |
| `.project` | IDE 工程描述（`fun build` 不需要） |
| `ui/main.html` | **唯一手写源**：顶栏 + 主页面（打开日历/输入框/跳到今天）+ 日历弹窗（42 个日号 textview） |
| `ui/main.json` / `ui/main.ftu` | `html2json` / `fui pack` 产物 |
| `src/Main.cpp` | 应用入口 |
| `src/logic/mainLogic.cc` | **示例逻辑**：attach + 容器原点 + 命中反算 + 回填 + 翻月 + 跳到今天 |
| `src/uart/*` | 工程模板自带，本示例不改 |
| `src/zk/zk_calendar.{h,cpp}` | **组件本体**（= `../include/zk/zk_calendar.h` + `../src/zk_calendar.cpp` 原样拷贝） |
| `evidence/*.png` | 真机截图 + 像素 diff（见 README §7 验收表） |

## 布局要点（改布局前必读）

1. **42 个日号格**在 `WinCal` 里按 `x = 28 + col*88`、`y = 100 + row*44`、`88×38` 摆（行优先 7 列 × 6 行）；
   `mainLogic.cc` 里 `s_cells[0..41]` 的顺序**必须与这里的摆放顺序完全一致**。
2. **`>` 或窗口里必须放一张铺满的「卡片按钮」当白底**（`BtnCalCard`）：modal 窗口不画自己的底色
   （Z21 实测）。该按钮在代码里 `setTouchable(false) + setTouchPass(true)`，只当背景、不抢事件。
   注意：因为网格挂在 `WinCal` 上（不是卡片按钮里），容器原点 = `WinCal.getPosition()`；
   如果把它嵌进更深的容器，记得用 `setContainerOrigin(各层 getPosition() 之和)`。
3. 表头（一…日）是业务摆的静态文本，组件不管。

## 从零跑起来

```powershell
# 0) 准备一个工作副本（别在仓里 build）
mkdir C:\work\CalendarDemo
copy -r tools\FlyThings_mcp_open\components\ui_v1\Calendar\example\* C:\work\CalendarDemo\

# 1) 改原型（可选）：ui/main.html 改完重新生成 json + 打包（先 pack 再 build）
python tools\ui_tools\html2json.py C:\work\CalendarDemo\ui\main.html C:\work\CalendarDemo\ui\main.json
cd C:\work\CalendarDemo\ui ; <fui.exe> pack .        # fui.exe 在工具箱/仓库 projects\fui.exe

# 2) 编译（fun build 自动收 src\**\*.cpp）
cd C:\work\CalendarDemo
fun build -p Z21

# 3) 全检（必须全 PASS）
python tools\ui_tools\check_all.py C:\work\CalendarDemo
```

部署说明（Z21 特有）：`/res` 是 **squashfs 只读**，`/data` **已满** —— 把
`libzkgui.so` / `main.ftu` / `EasyUI.cfg` 推到 **`/tmp/{lib,ui}`** 再重启应用（本示例用开发工作区里
`projects/translate/lvgl-widgets/deploy_direct.py` 那套直连部署脚本，约 5 秒）。

## 真机验收步骤（复现 README §7 的证据）

```powershell
# 触摸注入工具（bin_tools/z21/touch，自动判 MT 协议）
adb push tools\FlyThings_mcp_open\bin_tools\z21\touch /tmp/touch ; adb shell chmod 777 /tmp/touch

# ① 打开日历（当月 2026-09；今天 16 浅灰；标记 5/12/18/25 橙棕）
adb shell "/tmp/touch tap 180 208"          # 主页面「打开日历」按钮
# ② 翻到下一月（2026-10）
adb shell "/tmp/touch tap 806 78"           # 弹窗右上「>」
# ③ 翻回 9 月并点 18 号（命中反算 -> pickDay -> 回调回填输入框）
adb shell "/tmp/touch tap 218 78"           # 弹窗左上「<」
adb shell "/tmp/touch tap 586 247"          # 18 号格中心
# ④ OK 关窗（输入框显示 2026-09-18）
adb shell "/tmp/touch tap 322 480"
# ⑤ 跳到今天（setToday + setMarkedDays：标记换成 3/11/20）
adb shell "/tmp/touch tap 180 414"
```

坐标口径：这些坐标 = 弹窗位置 `(162,40)` + 控件在弹窗里的位置（`ui/main.json` 里能直接读到）。

抓屏（**必须按 pan 偏移**，否则抓到上一帧/黑屏）：

```powershell
python tools\FlyThings_mcp_open\ui_tools\device_screenshot.py --device 192.168.1.100:5555 --out C:\work\shot.png
```

像素判据（0 token，程序化）：

```powershell
python tools\ui_tools\ui_diff.py C:\work\a.png C:\work\b.png --out C:\work\diff.png
# 期望：01（初始）vs 03（点中 18 号）→ 实测 16 处差异 / 25,541 像素，
#       差异块只有四处：18 号格、顶部状态行、弹窗内状态行、主页面输入框（没有整屏乱刷）
```

## 预期结果

- ① 弹窗出现，标题 `2026-09`，1 号在**周二**列；16 号浅灰（今天）、5/12/18/25 橙棕（标记）。
- ② 标题变 `2026-10`，1 号在**周四**列，标记日跟着移到 10 月；顶部状态行 `下一月：2026-10（未选日）`。
- ③ 回到 9 月后点 18 号 → **18 号变深蓝加粗**，弹窗状态行 `已选：2026-09-18（弹窗内即时可见）`，
  主页面输入框同步出现 `2026-09-18`。
- ④ 点 OK → 弹窗关闭，顶部 `OK：已确认 2026-09-18（输入框已回填）`。
- ⑤ 点「跳到今天」→ 弹窗再次打开，标记改成 3/11/20，18 号仍是深蓝加粗。

> ✅ **【已勘正 2026-09-28】设备坑已消除**：当时写“连续多次 `kill -9 zkgui` 后触摸不响应” —— 根因就是那些 `kill`（应用由
> 类 init 服务托管，kill 不是框架认可的重启方式）。现在重启应用统一走 **`setprop ctl.restart zkswe`**，
> Z20（108）实测 **10 轮重启：pid 每轮换新、触摸注入每轮都有响应**（帧差 230400 px，无需重启板子）。
> 口径见 `knowledge/devflow/device-deploy-budget.md` §5；验收脚本与证据见工作区 `temp/setprop_accept/`。
