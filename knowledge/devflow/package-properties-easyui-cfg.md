---
id: devflow-package-properties-easyui-cfg
title: ⚙️ package.properties / EasyUI.cfg 工程配置机制（屏幕旋转等）
category: devflow
status: review
confidence: manual
verified_at: 2026-09-29
stale_days: 180
origin: total
source: 2026-09-29 front-matter 迁移（P1：先显式登记"待补可执行判据"）
needs_evidence: true
platforms: [F133, Z20, T113]
tags: [定规, 同代码双屏方向适配案例]
evidence: []
---
# ⚙️ package.properties / EasyUI.cfg 工程配置机制（屏幕旋转等）

> 检索导引：问「EasyUI.cfg 怎么写 / package.properties 覆盖了哪份 cfg / rotateScreen 配在哪 / 推上去没效果（extsd 卡里的旧 cfg 劫持）/ 字体资源怎么真进 /res」→ 本文。
> 口语/错说法（用户原话）：推了个新包上去屏幕还是旧的没变化 / 改了配置没生效 / 字体文件放在哪个目录才能打进包里生效 / 自定义字体设了没反应 / 改了 rotateScreen 编译却提示 no work to do（没事可做）/ 屏幕旋转的配置写在哪个文件里。
> 2026-09-03 需求方讲解机制（定规）+ mark_cv201 实测校准（CV201_PND rotateScreen 270 / CV201_PND_1024_600 不转，同代码双屏方向适配案例）。

## 1. 核心机制（2026-09-03 定规）

1. **编译工具会自动生成完整的 EasyUI.cfg**（默认 JSON，包含下方字段表中的全部参数，路径分 debug=/mnt/extsd 与 release=/res 两套）
2. 工程根目录 `package.properties` 里的 **`EasyUI.cfg={...}` 是覆盖层**：写了哪个字段就**优先采用**哪个（覆盖编译默认值）；**不需要特殊处理的字段不用写**
3. 所以 `.settings/com.zksw.flythings.easyui.prefs`（IDE 属性，debug/release 两份）里 rotateScreen=0、而 package.properties 里 270 不矛盾——**package.properties 优先**
4. `enable.font.location=true`：另一独立开关，启用工程内 font/ 目录自定义字体（配合 `setFontFamily`，见 wiki `wiki/flythings/font/font_setting.md`）

## 2. ⚠️ 查找优先级：设备上生效的**可能不是这一份**cfg（SD 卡会「劫持」程序）

> 2026-09-27 Z20 现场入规。检索词：**推上去没效果 / 改了像没改 / 新包看不到效果 /
> 加载了 SD 卡旧 lib / startupLibPath 指到 extsd / EasyUI.cfg 劫持 / remount rw extsd**。

启动器按**优先级**加载 cfg（高 → 低）：

```
/tmp/EasyUI.cfg        ← fun launch 的调试态（tmpfs，重启即清）
/mnt/extsd/EasyUI.cfg  ← SD 卡（厂商 App / SD 调试包路线）   ★ 现场最常见的“没效果”原因
/res/etc/EasyUI.cfg    ← 内置固件（release 态）
```

- **典型现象**：包推上去了、md5 回了、`getprop sys.zkapp.state=running`，但**屏幕/行为还是旧的**（改了像没改）。
- **根因**：SD 卡那份 cfg 里 `"startupLibPath":"/mnt/extsd/lib/libzkgui.so"`（`resPath` 同理可指向
  `/mnt/extsd/ui/`）→ 应用**实际加载的是 SD 卡上那份旧 lib/旧 ui**；新包这两份都在，跑的是 SD 那份。
- **判定（两条）**：
  1. `cat /mnt/extsd/EasyUI.cfg`（有则看 `startupLibPath` / `resPath` 指哪）；
  2. 看**真正被加载**的那份：`cat /proc/$(pidof zkgui)/maps | busybox grep libzkgui`（无 busybox 就比
     `/res/lib/libzkgui.so` 与 `/mnt/extsd/lib/libzkgui.so` 的 md5，哪个 == 本地产物）。
- **处置**：改名即立即失效（回落下一优先级）；该分区**默认 ro**，要先 remount：

```bash
adb shell "mount -o remount,rw /mnt/extsd"
adb shell "mv /mnt/extsd/EasyUI.cfg /mnt/extsd/EasyUi.cfgbak"
adb shell "mount -o remount,ro /mnt/extsd"     # 改完回 ro
adb shell "setprop ctl.restart zkswe"          # 重启应用生效
```

- `rotateScreen` / `rotateTouch` 也在这份 cfg 里（“方向怎么改都不对”同源排查）；
静态旋转 vs 运行时旋转详见 `knowledge/devflow/dynamic-screen-rotation.md`。
- 另：**编译期 easyui 版本 ≠ 设备运行库版本**（设备看 `getprop ro.easyui.version`；控件类由运行库提供）
  → 能力存在性判定与矩阵见 `knowledge/devflow/dynamic-screen-rotation.md` §4.1。

## 3. EasyUI.cfg 完整字段（提供标准格式，debug 版示例）

```json
{
  "baud": "115200",
  "defBrightness": -1,
  "font": "/mnt/extsd/ui/PingFang.ttf",
  "languageCode": "zh_CN",
  "languagePath": "/mnt/extsd/tr/",
  "resPath": "/mnt/extsd/ui/",
  "rotateScreen": 0,
  "rotateTouch": 0,
  "screensaverTimeOut": -1,
  "startupLibPath": "/mnt/extsd/lib/libzkgui.so",
  "startupTouchCalib": false,
  "uart": "ttyS1",
  "zkdebug": true
}
```

| 字段 | 类型 | 含义 |
|------|------|------|
| `baud` | string | 串口波特率（"115200"） |
| `defBrightness` | int | 默认背光亮度，-1 = 不干预 |
| `font` | string | 默认字体文件路径（可覆盖默认字体） |
| `languageCode` | string | 语言代码（zh_CN 等，i18n 用） |
| `languagePath` | string | 多语言翻译 .tr 文件路径（debug=/mnt/extsd/tr/，release=/res/tr/） |
| `resPath` | string | UI 资源路径（debug=/mnt/extsd/ui/，release=/res/ui/） |
| `rotateScreen` | int | **屏幕旋转 0/90/180/270**（内容旋转到正常方向） |
| `rotateTouch` | int | 触摸坐标旋转；**正常与 rotateScreen 同值成套；若硬件屏幕需转、触摸不需转则留默认不配**|
| `screensaverTimeOut` | int | 屏保超时秒，-1 = 禁止屏保 |
| `startupLibPath` | string | GUI 运行库路径（libzkgui.so） |
| `startupTouchCalib` | bool | 启动是否做触摸校准 |
| `uart` | string | 串口设备名（ttyS1） |
| `zkdebug` | bool | 调试开关 |
| `watchDogEnable` | bool | 看门狗开关（F133 工程普遍 false，mark_cv201 也配 false）——完整默认以编译工具生成为准，需要改才在 package.properties 覆盖 |

## 4. ⚠️ 何时用 package.properties 覆盖（2026-09-03 补充定规）

- **正常情况（屏幕与触摸方向一致 / 都不转）→ 发 IDE 配置 .prefs 即可，不用写 package.properties**
- **需要特殊处理覆盖时才用 package.properties**：典型场景 = **某些硬件屏幕需要旋转、而触摸不需要旋转**
  （两者方向不一致），这时只覆盖 rotateScreen 写旋转值，rotateTouch 不写/保持默认，触摸坐标不跟着转
  —— mark_cv201 CV201_PND 正是此例：只配 `rotateScreen:270` 不配 rotateTouch
- 同值成套的常规旋转（F133 工程 rotateScreen:270+rotateTouch:270）走 .prefs 就够，不必进 package.properties

## 5. mark_cv201 实测案例（同代码双屏方向适配）

- `CV201_PND`（UI 1600×600）：`EasyUI.cfg={"rotateScreen": 270, "watchDogEnable":false}` → 设备屏幕坐标方向与 UI 差 270°，旋转适配
- `CV201_PND_1024_600`（UI 1024×600）：`EasyUI.cfg={ "watchDogEnable":false}` → 屏幕方向正常，**不需要写 rotateScreen**
- 结论：**屏幕旋转是跟着设备物理安装方向走的，不是 UI 决定的**；同 1600×600 UI 的 lib_uav_camera 不转、CV201_PND 转 270
- 同类先例：T113 车载 PND「竖装横显」= 1024×600 横 UI + `rotateScreen: 270`（references/kb/t113-car-link.md）
- F133 系工程（AirPlayF133/CycleComputer 等）惯例成套：`rotateScreen:270 + rotateTouch:270 + gfxMode:1 + ninePatchAccel:true`

## 6. 代码消费链

```cpp
CONFIGMANAGER->getScreenRotate();   // 读 rotateScreen（ConfigManager.h 注释 rot: 0 90 180 270）
enum disp_rot_e rot = (disp_rot_e)(CONFIGMANAGER->getScreenRotate() / 90);  // link 投屏方向
ERotation rot = (ERotation)(CONFIGMANAGER->getScreenRotate() / 90);          // V85X 摄像头 setRotation 跟随
```
- `ConfigManager.h` 接口：`setScreenRotate(int)` / `setTouchRotate(int)` / `getScreenRotate()`；宏 `CONFIGMANAGER`
- mark_cv201 倒车画面 reverse 页的 `get_camera_rot()` 是**另一路**（摄像头画面自身旋转参数，来自 `_s_camera_info`，非屏幕旋转），别混淆

## 7. 常见坑 / 使用规则

- **想改设备显示方向 → 只改 package.properties 的 rotateScreen，不要动 .ftu/代码**（编译工具自动合并生效）
- **屏幕转、触摸不转的硬件 → package.properties 只配 rotateScreen，不写 rotateTouch**；
  **两者同值成套的常规旋转走 .prefs 即可**（F133 工程成套 270+270 存 .prefs）
- **只需要覆盖用到的字段**，其余不写（自动用编译默认），不要整段 JSON 照抄覆盖
- 改完重新编译打包，设备上生成/更新的 EasyUI.cfg 在 resPath 对应目录（boot_from_sd 升级包同样携带 EasyUI.cfg）
- 调字体 → package.properties 加 `enable.font.location=true` + 工程 font/ 目录放字体 + 代码 `setFontFamily`（不是 EasyUI.cfg 覆盖层的事，注意区分）

## 8. 字体/资源如何真的进 `/res`（2026-09-24 实测校准）

- **字体要放工程 `resources/`**（如 `resources/fzcircle.ttf`）→ 打出的包才有 `/res/ui/fzcircle.ttf`；
  **放 `ui/` 会被忽略**，`fun pack` 只会吐一句 `no any font`（无报错、无声失败）。
- 实测判据（真机）：不带字体时 Z20 包 payload = **86,016 B**<!-- design-spec:evidence 历史实测记录（判据以设备实测为准，见 DESIGN_SPEC.md 第 2 条） -->；把 1.9 MB 字体放进 `resources/` 后 payload = **1,236,992 B**（确实进包）。
- EasyUI.cfg 里把字体指过去（覆盖层即可）：

```properties
EasyUI.cfg={"font":"/res/ui/fzcircle.ttf"}
```

- 参考实现：`gitcom/AppGroup/PublicTuyaSwitch`（字体 + 各页面图都在 `resources/`），
正常在跑的 Z20 板上 `/res/etc/EasyUI.cfg` 确实带 `"font":"/res/ui/fzcircle.ttf"`。【实测】

## 9. 取图角度 / 触摸坐标旋转口径（唯一事实来源 = 工程 EasyUI.cfg）

> 本节是「屏幕/取图角度 + 触摸坐标旋转口径」的**唯一收口处**（2026-09-30 收口）：
> `knowledge/devflow/ui-layout-verify.md` §2-1-1、`knowledge/devflow/device-screenshot.md` §3.6、`knowledge/devflow/pixel-analysis-ai.md` §3、
> `knowledge/devflow/dynamic-screen-rotation.md` §1、`knowledge/v85x/dvr-recorder-guide.md` §4、`knowledge/v85x/display-layer-debug.md` §5 均已压成指向本节的指针。

**判据（唯一权威来源）**：取图/屏幕角度只有一个来源 = **项目工程自己的 `EasyUI.cfg`**（字段 `rotateScreen` / `rotateTouch`），
**不是设备 sysfs 状态、也不是「看起来该转多少」**：

| 东西 | 位置 / 字段 |
|---|---|
| 工程内 | `<项目>/.fun/<平台>/launch/EasyUI.cfg`（打包时进 `.fun`/`imgout`，设备上 = `/res/etc/EasyUI.cfg`） |
| 取图 / 屏幕角度 | `"rotateScreen"`（0 / 90 / 180 / 270） |
| 触摸角度 | `"rotateTouch"`（**可与 `rotateScreen` 不同**；注入触摸测试要按它换算） |

**错屏机制（为什么必须转）**：UI 逻辑分辨率（如 1600×600 横）与物理屏方向（600×1600 竖装）不匹配时，
不旋转则 UI 宽 1600 > 物理宽 600 → 布局/视频内容溢出屏外 = 错屏/花屏；`rotateScreen` 把 UI 转回屏内。
**取值跟随硬件物理安装方向**（同代码双屏工程：横装屏 0/不写、竖装屏 270），与 UI 分辨率、代码无关。

**实测角度对应关系（V85X DVR 板，设备 `/res/etc/EasyUI.cfg` → `rotateScreen=270, rotateTouch=0`）**：不转 → fb 里的内容**侧躺/倒立**（文字方向错）；按 **270 转**→ 文字正立。代码 `img.rotate(-rotateScreen, expand=True)`
（PIL 逆时针为正）。⇒ **角度值直接决定变换**，不是某台设备的固定组合。

**验证做法（都可自证）**：

- 抓图工具缺省 `rotate='auto'` 就是读它（返回值带 `rotateSource: 'EasyUI.cfg rotateScreen'` 可自证）；
触摸注入收到的是 **UI 逻辑坐标**→ 注入前按 `rotateTouch` 换算（`rotateTouch=0` 时不用换）。
- 静态旋转**生效的硬指标**：`cat /sys/class/disp/disp/attr/sys` 里 UI 层 crop 由异常（如 `[0,1600,...]`）
恢复为 `[0,0,600,1600]` 全屏正常值；设备端 `cat /tmp/EasyUI.cfg` 可核对 `rotateScreen: 270 / rotateTouch: 0`。
- **时序铁律**：改完 `package.properties` 后 `fun build` 会 `ninja: no work to do` —— **必须 `fun clean` 全量重编**；
  EasyUI.cfg 由 `fun launch` 本地准备阶段合并生成（`.fun/<平台>/launch/EasyUI.cfg`），launch 时随部署推送。
- ⚠️ **动态旋转 `setScreenRotate()` 只改进程内 `CONFIGMANAGER`，不回写工程 `EasyUI.cfg`**
  → 「取图 / 换算角度」的基准仍是工程 cfg（见 `knowledge/devflow/dynamic-screen-rotation.md` §1）。

**❌ 不要做的事（3 条）**：

1. 不要拿 `/sys/class/graphics/fb0/rotate` 当首选 —— 本机它 = `0`，与工程角度**不一致**
   （看着像不用转，实际要转 270）；只在拿不到 EasyUI.cfg 时退化用。
2. 不要把某台设备的「转置 / 翻转」组合硬编成通则（如“某型号必须 TRANSPOSE+FLIP_TOP_BOTTOM”）——
那是**那台设备那个角度**的结果，换角度/换板子就不对；也不要手推旋转矩阵，统一用同一个旋转函数。
3. 不要从 disp 图层几何**反推**方向 —— `/sys/class/disp/disp/attr/sys` 只告诉你 UI 图层占哪块，
不给屏幕角度（例：480×800 那个图层是**视频/DVR 层**，不是应用 UI 层）。

**注意区分（不是同一回事，别混）**：`ZKVideoView` 布局里的 `"rotation"` 是**枚举**`0/1/2/3`
（= 0°/90°/180°/270° 顺时针，**不是角度值**，写 `270` 无效被忽略），属**控件级视频画面旋转**，
与本节的 `rotateScreen` 屏幕旋转无关 → 细节见 `knowledge/v85x/display-layer-debug.md` §6 / `knowledge/v85x/dvr-recorder-guide.md` §5-1。

## 相关

- `knowledge/devflow/dynamic-screen-rotation.md`：**运行时**旋转（`setScreenRotate` + `Activity::relayout` 换两套 ftu），与本文的编译期静态旋转互补；要 easyui ≥ 2.9.0
- ★ **`resPath` 与 `startupLibPath` 必须同源**（只换 lib 不换 resPath = 「新库 + 旧界面」，症状就是“改了像没改”）→ `knowledge/devflow/deploy-consistency-check.md`
- wiki `wiki/flythings/font/font_setting.md`：enable.font.location + 多字体完整流程
- wiki `wiki/flythings/devflow/new_project.md`：创建项目时"屏幕旋转"选项（IDE 向导对应字段）
- references/kb/t113-car-link.md：T113 PND 竖装横显先例
