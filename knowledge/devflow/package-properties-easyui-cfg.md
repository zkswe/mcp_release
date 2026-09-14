# ⚙️ package.properties / EasyUI.cfg 工程配置机制（屏幕旋转等）

> 2026-09-03 沛哥讲解机制（定规）+ mark_cv201 实测校准（CV201_PND rotateScreen 270 / CV201_PND_1024_600 不转，同代码双屏方向适配案例）。

## 核心机制（沛哥 2026-09-03 定规）

1. **编译工具会自动生成完整的 EasyUI.cfg**（默认 JSON，包含下方字段表中的全部参数，路径分 debug=/mnt/extsd 与 release=/res 两套）
2. 工程根目录 `package.properties` 里的 **`EasyUI.cfg={...}` 是覆盖层**：写了哪个字段就**优先采用**哪个（覆盖编译默认值）；**不需要特殊处理的字段不用写**
3. 所以 `.settings/com.zksw.flythings.easyui.prefs`（IDE 属性，debug/release 两份）里 rotateScreen=0、而 package.properties 里 270 不矛盾——**package.properties 优先**
4. `enable.font.location=true`：另一独立开关，启用工程内 font/ 目录自定义字体（配合 `setFontFamily`，见 wiki `font/font_setting.md`）

## EasyUI.cfg 完整字段（沛哥提供标准格式，debug 版示例）

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
  "touchDev": "/dev/input/event0",
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
| `rotateTouch` | int | 触摸坐标旋转；**正常与 rotateScreen 同值成套；若硬件屏幕需转、触摸不需转则留默认不配** |
| `screensaverTimeOut` | int | 屏保超时秒，-1 = 禁止屏保 |
| `startupLibPath` | string | GUI 运行库路径（libzkgui.so） |
| `startupTouchCalib` | bool | 启动是否做触摸校准 |
| `touchDev` | string | 触摸设备节点 |
| `uart` | string | 串口设备名（ttyS1） |
| `zkdebug` | bool | 调试开关 |
| `watchDogEnable` | bool | 看门狗开关（F133 工程普遍 false，mark_cv201 也配 false）——完整默认以编译工具生成为准，需要改才在 package.properties 覆盖 |

## ⚠️ 何时用 package.properties 覆盖（沛哥 2026-09-03 补充定规）

- **正常情况（屏幕与触摸方向一致 / 都不转）→ 发 IDE 配置 .prefs 即可，不用写 package.properties**
- **需要特殊处理覆盖时才用 package.properties**：典型场景 = **某些硬件屏幕需要旋转、而触摸不需要旋转**
  （两者方向不一致），这时只覆盖 rotateScreen 写旋转值，rotateTouch 不写/保持默认，触摸坐标不跟着转
  —— mark_cv201 CV201_PND 正是此例：只配 `rotateScreen:270` 不配 rotateTouch
- 同值成套的常规旋转（F133 工程 rotateScreen:270+rotateTouch:270）走 .prefs 就够，不必进 package.properties

## mark_cv201 实测案例（同代码双屏方向适配）

- `CV201_PND`（UI 1600×600）：`EasyUI.cfg={"rotateScreen": 270, "watchDogEnable":false}` → 设备屏幕坐标方向与 UI 差 270°，旋转适配
- `CV201_PND_1024_600`（UI 1024×600）：`EasyUI.cfg={ "watchDogEnable":false}` → 屏幕方向正常，**不需要写 rotateScreen**
- 结论：**屏幕旋转是跟着设备物理安装方向走的，不是 UI 决定的**；同 1600×600 UI 的 lib_uav_camera 不转、CV201_PND 转 270
- 同类先例：T113 车载 PND「竖装横显」= 1024×600 横 UI + `rotateScreen: 270`（references/kb/t113-car-link.md）
- F133 系工程（AirPlayF133/CycleComputer 等）惯例成套：`rotateScreen:270 + rotateTouch:270 + gfxMode:1 + ninePatchAccel:true`

## 代码消费链

```cpp
CONFIGMANAGER->getScreenRotate();   // 读 rotateScreen（ConfigManager.h 注释 rot: 0 90 180 270）
enum disp_rot_e rot = (disp_rot_e)(CONFIGMANAGER->getScreenRotate() / 90);  // link 投屏方向
ERotation rot = (ERotation)(CONFIGMANAGER->getScreenRotate() / 90);          // V85X 摄像头 setRotation 跟随
```
- `ConfigManager.h` 接口：`setScreenRotate(int)` / `setTouchRotate(int)` / `getScreenRotate()`；宏 `CONFIGMANAGER`
- mark_cv201 倒车画面 reverse 页的 `get_camera_rot()` 是**另一路**（摄像头画面自身旋转参数，来自 `_s_camera_info`，非屏幕旋转），别混淆

## 常见坑 / 使用规则

- **想改设备显示方向 → 只改 package.properties 的 rotateScreen，不要动 .ftu/代码**（编译工具自动合并生效）
- **屏幕转、触摸不转的硬件 → package.properties 只配 rotateScreen，不写 rotateTouch**；
  **两者同值成套的常规旋转走 .prefs 即可**（F133 工程成套 270+270 存 .prefs）
- **只需要覆盖用到的字段**，其余不写（自动用编译默认），不要整段 JSON 照抄覆盖
- 改完重新编译打包，设备上生成/更新的 EasyUI.cfg 在 resPath 对应目录（boot_from_sd 升级包同样携带 EasyUI.cfg）
- 调字体 → package.properties 加 `enable.font.location=true` + 工程 font/ 目录放字体 + 代码 `setFontFamily`（不是 EasyUI.cfg 覆盖层的事，注意区分）

## 相关

- `devflow/dynamic-screen-rotation.md`：**运行时**旋转（`setScreenRotate` + `Activity::relayout` 换两套 ftu），与本文的编译期静态旋转互补；要 easyui ≥ 2.9.0
- wiki `font/font_setting.md`：enable.font.location + 多字体完整流程
- wiki `devflow/new_project.md`：创建项目时"屏幕旋转"选项（IDE 向导对应字段）
- references/kb/t113-car-link.md：T113 PND 竖装横显先例
