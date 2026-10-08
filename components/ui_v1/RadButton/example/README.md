# example —— RadButton 最小可跑示例（Z21 1024×600）

> 这个目录就是一个**能编、能跑、能复现证据**的 FlyThings 工程（只留必要文件，没有 `fsc.exe`/`fui.exe`/`.fun/` 产物）。
> 真机截图与数字在 `evidence/`，测量脚本在 `tools/aa_ideal.py` / `tools/aa_measure.py`。

## 文件清单

| 文件 | 作用 |
|---|---|
| `Manifest.xml` | 依赖声明（easyui ^2.2.0 + log/zkhardware/zknet/base-utility） |
| `.deps.lock` | 依赖解析结果快照（实际落到 easyui 2.6.0） |
| `.project` | IDE 工程描述（`fsc build` 不需要） |
| `ui/main.html` | **本示例的手写源（原型稿）**：两排 painter（HARD / AA 各 r=4/8/14）、四个状态盒、四个交互按钮、探针、`.9.png` 按钮 |
| `ui/main.json` / `ui/main.ftu` | `html2json` / `fui pack` 产物 |
| `src/Main.cpp` | 应用入口 |
| `src/logic/mainLogic.cc` | **示例逻辑**：10 个 painter 绑定 + 四态 + 按下/选中 + 换半径 + **自动演示定时器** |
| `src/uart/*` | 工程模板自带，本示例不改 |
| `src/zk/zk_radbutton.{h,cpp}` | **组件本体**（= `../include/zk/zk_radbutton.h` + `../src/zk_radbutton.cpp` 原样拷贝，md5 一致） |
| `resources/images/rad_9p.9.png` | 切图路线对照用资产（`rounded_rect_ss(200,56,14)` + 9-patch 标记） |
| `aa_ideal.py` | **主判据**：圆角边缘 vs 16×16 超采样理想覆盖率的误差（0 token、纯像素） |
| `aa_measure.py` | 辅助判据：中间档像素数 / 档数 / 占边界像素比例 |
| `evidence/*.png` | 真机截图 + 8× LANCZOS 放大 + 像素 diff（见下表） |

## 从零跑起来

```powershell
mkdir C:\work\RadButtonDemo
copy -r tools\FlyThings_mcp_open\components\ui_v1\RadButton\example\* C:\work\RadButtonDemo\

python tools\ui_tools\html2json.py C:\work\RadButtonDemo\ui\main.html C:\work\RadButtonDemo\ui\main.json
cd C:\work\RadButtonDemo\ui ; <fui.exe> pack .
cd C:\work\RadButtonDemo
fsc build -p Z21
```

## 屏上有什么（对着截图看）

```
① HARD 行   PtHard4/8/14   平台原生 fillRect(radius)  ← 对照组（r=8 会看到台阶）
② AA 行     PtAa4/8/14     本包 MODE_AA             ← 与上一行同尺寸同色，只看边缘
③ 状态行    PtStCur         四态/按下/选中           ← 由下面四个按钮 + 自动演示定时器驱动
            PtStToggle / PtStPress / PtStDisabled
④ 探针      PtProbe         fillRect 直角 + fillArc 圆环 + drawRect 圆角描边（painter 原生能力）
⑤ 切图      BtnImg          .9.png 九宫格拉伸（资产 200×56 → 盒子 300×56）
```

**两条驱动路径（都走同一批 API）**：

- **按钮路径**（真实交互）：`BtnCycle`/`BtnToggle`/`BtnPress`/`BtnRadius` 四个 `button__N` 当热区，
  `onButtonClick_*` 里调 `setState/setSelected/press/setRadius` + `refresh()`。
  RadButton **不接管触摸**，命中交给业务（这就是「业务侧 0 行手写命中」的写法）。
- **自动演示定时器**（不依赖触摸，抓图可复现）：`REGISTER_ACTIVITY_TIMER_TAB = {{1, 2000}}`，
  每 2s 走一步 → 1 `setState(PRESSED)` / 2 `setSelected(true)` / 3 `press(true)` / 4 `press(false)` /
  5 `setRadius(28)`（5 步后停表）。**证据图就是这条路径抓的**（把定时器去掉不影响组件功能）。

## 证据索引（Z21 1024×600，2026-09-16）

| 文件 | 一句话 |
|---|---|
| `01_initial_full.png` | 首帧：① HARD r=4/8/14 ② AA r=4/8/14 ③ 四态（当前 NORMAL）④ 探针 ⑤ `.9.png` 拉伸按钮，全部正常显示（状态行 `ready：AA 模式 = 逐像素覆盖率 + 混底色`） |
| `02_state_pressed.png` | 状态行 `step1 setState(PRESSED) -> PRESSED（填充 0x1976D2）`；③ 左盒变深蓝 |
| `03_toggle_selected.png` | 状态行 `step2 setSelected(true) -> SELECTED`；② 号盒（选中/取消）变最深蓝 |
| `04_press_held_true.png` | 状态行 `step3 press(true) -> PRESSED（记住按下前状态）`；③「按住（2px 边框）」盒按下态 + 边框 |
| `05_press_rolled_back_and_radius28.png` | 状态行 `step5 setRadius(28) -> 200x56 药丸（无资产）`；② 行变成药丸（r=28），且 ③ 按下盒已回落（`press(false)` 幂等） |
| `06_zoom8x_r14_hard_vs_aa.png` | 8× **LANCZOS**：上 HARD r=14 / 下 AA r=14（同盒同色） |
| `07_zoom8x_r8_hard_vs_aa.png` | 8× LANCZOS：上 HARD r=8（**肉眼可见台阶**）/ 下 AA r=8（平滑）—— 最直观的一张 |
| `08_zoom8x_three_routes.png` | 8× LANCZOS 五格：HARD r=14 / AA r=14 / HARD r=8 / AA r=8 / 切图 `.9.png` |
| `09_zoom8x_state_corner.png` | ③ 状态盒圆角放大（确认状态色切换不影响边缘质量） |
| `10_diff_initial_vs_pressed.png` | `ui_diff(01,02)`：31 处差异 / 19,110 px（差异集中在状态盒 + 日志/状态行） |
| `11_diff_pressed_vs_selected.png` | `ui_diff(02,03)`：15 处差异 / 11,238 px（只多变了切换盒） |
| `12_diff_initial_vs_radius28.png` | `ui_diff(01,05)`：33 处差异 / 29,622 px（②行半径 + ③两盒状态） |

### 追加：0.1.1「药丸圆钮外露方角」修复对照（Z21 同一台，2026-09-16 22:0x）

| 文件 | 一句话 |
|---|---|
| `13_pill_corner_before_after_zoom8x_team_on.png` | 8× LANCZOS 左右对照（56×28 药丸钮）：左「修前=钮外露方角」/ 右「修后=圆滑无角」 |
| `14_pill_corner_before_after_zoom8x_team_off.png` | 同上，开关 OFF 档 |
| `15_pill_corner_after_zoom8x_all_four.png` | 修后四帧（Team/Hard × on/off）8× 总览 |
| `16_diff_before_after_team_on.png` | `ui_diff(修前, 修后)` 默认口径：整帧原始差 **24 px**（每个钮 12 px = 6 个方角 + 6 个钮缘 AA 基准修正 Δ≤10/255） |
| `17_diff_STRICT_before_after_team_off.png` | 严格口径 `--open 0 --min-area 1 --shift 0`：**4 处 / 66 px**——默认降噪会把它抹成「0 处差异」，看这个 |
| `18_local_render_zoom8x_before_after_on.png` | 上机**前**的本地渲染桩（WSL）+ 独立 16× 参考模型：修前复现 PURE=6（位置与设备逐点一致）→ 修后 PURE=0 |
| `19_device_after_switch_team_on.png` | 修后设备帧（Team ON），md5 `5b8a03e6f3b6` |
| `FIX_metric.log` | 修前/修后**同一口径**指标：PURE（主判据）**6/钮 → 0**、NEAR 6 → 0、LOOSE 18 → 16（16 = 12 个药丸自身 AA + 4，逐像素已解释） |
| `FIX_local_check.log` | 本地自检：桩渲染 / 参考模型 / `fillRect` 调用数 542→496（无性能退化）/ `aa_ideal` / `check_all` 全 PASS |
| `FIX_diff_strict_team_on.json` | 严格口径 diff 的机读结果 |

> 修前帧（`zzb_*`）与 `zzc_*` 全量 20 张在案例工程 `projects/translate/lvgl-widgets-uiv1/z21/evidence/`（`STATUS.md` §12 是同轮逐项报告）；
> 本目录只留对外证据。`MODE_HARD` 路径**未修**（按要求保留对照，该档仍会露方角）。

> 放大图**必须用 LANCZOS**（`PIL`），NEAREST 放大必然看着有台阶、会误判。

## 复现数字

```powershell
python aa_ideal.py 01_initial_full.png --box 456,88,200,56  --radius 14 --corner tl --label HARD_r14
python aa_ideal.py 01_initial_full.png --box 456,198,200,56 --radius 14 --corner tl --label AA_r14
python aa_ideal.py 01_initial_full.png --box 240,88,200,56  --radius 8  --corner tl --label HARD_r8
python aa_ideal.py 01_initial_full.png --box 240,198,200,56 --radius 8  --corner tl --label AA_r8
python aa_ideal.py 01_initial_full.png --box 701,345,300,56 --radius 14 --corner tl --label NINE_r14
# 期望（实测）：HARD_r14 mean 8.2 / HARD_r8 mean 19.6（36% >30）/ AA_r14 2.0 / AA_r8 1.8 / NINE 10.0
```

## 上机姿势（Z21 只有一个任务能用，别抢）

```powershell
adb reboot ; 等 35s ; adb connect 192.168.1.100:5555
adb push tools\FlyThings_mcp_open\bin_tools\z21\touch /tmp/touch ; adb shell chmod 777 /tmp/touch
python temp\uiv1\deploy.py <本工程>        # 同一 boot 内只部署一次
# 之后：抓图（本示例有自动演示定时器，不依赖 touch 注入；若要验证按钮路径再注入 tap）
```

## 排错

见 `../README.md` §8。与本示例有关的两个坑：

1. **`.9.png` 内容内缩 1px**：设备上渲染的内容区在 `(x+1,y+1)` —— 用 `aa_ideal.py` 比对时
   `--box` 要按 701,345 写（不是 700,344），否则会得到假的大误差（129 vs 真实的 10.0）。
2. **touch 注入**：`/tmp/touch check` 通过 ≠ 应用一定收得到；本示例把状态机做成**不依赖 touch** 也能举证。
