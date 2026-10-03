# platforms.md —— TabView 逐平台说明

> 口径：**没实测的一律写 `未验证`**，不写「应该可以」。**本组件例外**：2026-10-03 口径「UI 控件只做 **V85X 单平台代表验收**」→ 其余平台标 `➖ 不逐平台验`（见 `platform_capabilities.json` 的 `verificationPolicy`）。实测值都给出命令与结果。
> 组件本质只用到 `easyui` 的 `ZKPageWindow / ZKButton / ZKTextView`，这三样在下列平台都存在；
> 差异主要在 **easyui 版本**（`IPageChangeListener` 与 `getPageSize()` 的可用性）和**设备上的 .so 行为**。
>
> ⚠️ 文档里的设备地址（`192.168.1.100:5555`）是**通用示例**，不是真机 IP；真机清单在开发工作区
> （`references/kb/devices.md`），**不进发布包**。

## Z21（1024×600 横屏）

| 项 | 值 |
|---|---|
| 可用性 | ✅ **可用（已真机验收）** |
| 实测 easyui | 设备 `/lib/libeasyui.so`（805,680 B，2024-07-10）；开发侧链接 registry 的 **easyui 2.6.0** |
| 前置条件 | 设备 adb-over-network（`192.168.1.100:5555`）；`/tmp` 可写（rootfs `/res` 是 **squashfs 只读**，应用只能部署到 `/tmp/{lib,ui}` + `/tmp/EasyUI.cfg`）；⚠️ `/data` **已满**，别往 `/data` 推文件 |
| 分辨率/rotate | 1024×600，`rotateScreen=0 / rotateTouch=0` |
| 触摸 | `/dev/input/event0` = `gt9xx`，**MT-B** 协议（`touch` 工具自动判协议，直接 `swipe/tap`） |
| 实测值 | 滑动阈值 `dragMaxDis=200` 下，`swipe 900 300 150 300` 一次即翻页；下划线重算耗时不可测（同帧完成） |
| 已知限制 | ① fb 双缓冲：`virtualHeight=1200 ≈ 2×600`；实测应用**固定渲染到 offsetY=600 那一半**（offsetY=0 那半是黑的、`pan` 恒为 `0,600`）→ 抓屏必须按读到的 `pan` 偏移取帧，否则拿到黑屏/旧帧；② `zkshot`（视频层抓帧）留在后台会**卡住 zkgui（D 状态）**，抓屏请只用 framebuffer 通道；③ **【已勘正 2026-09-28】�回重启后触摸不响应 = 当时 `kill -9 zkgui` 的后果** —— 改 `setprop ctl.restart zkswe`（框架口径：init 托管、不能 kill）后，**Z20 108 实测 10 轮重启：pid 每轮换新、触摸每轮都有响应（帧差 230400 px）**，不用重启板子，也不是组件问题（详见 `knowledge/devflow/device-deploy-budget.md` §5） |
| 真机验收命令 | `fun build -p Z21` → `fun launch -p Z21 -s 192.168.1.100:5555` → `/tmp/touch swipe 900 300 150 300` → 抓屏对比 |

## F133（1280×800，rotate 270/270）

| 项 | 值 |
|---|---|
| 可用性 | ➖ **不逐平台验**（仅编译通过）—— 2026-10-03 口径：UI 控件只做 V85X 单平台代表验收 |
| 依据 | 同代 `easyui 2.9.0` 头文件里 `ZKPageWindow` 的公开面与 2.6.0 **一致**（`getPageSize / getCurrentPage / setCurrentPage / setPageChangeListener / turnToNextPage / turnToPrevPage` 全在），组件源码无平台宏 |
| 前置条件 | `package.properties` 要写 `{"rotateScreen":270,"rotateTouch":270}`（设备 fb 是 800×1280 竖）；SD 部署 `/mnt/extsd/{lib,ui}` |
| 未验证项 | 真机滑动切页手感、下划线像素位置、触摸协议 |

## Z20 / T113 / V85X

| 平台 | 可用性 | 依据 |
|---|---|---|
| Z20 | ➖ 不逐平台验（口径：UI 控件只做 V85X 单平台代表验收，2026-10-03） | registry 有 `z20/easyui/2.6.0` 与 `3.0.0`，`ZKPageWindow.h` 公开面与 Z21 同名同签名；组件无平台分支 |
| T113 | ➖ 不逐平台验（口径：UI 控件只做 V85X 单平台代表验收，2026-10-03） | registry `t113emmc/easyui/2.9.0` 头文件一致；`bin_tools/t113/touch` 已有（触摸注入可用） |
| V85X | ✅ **可用（真机已验收 2026-10-03）** | registry `v85x/easyui/2.3.0`（较老）与 `2.9.0` 都含 `IPageChangeListener + getPageSize + turnTo*`（**已逐个核对头文件**）；组件无平台宏；**V85X 实测（2026-10-03）**：`fun build` + `fun launch` 通过、launch 后 `onUI_show` 确认、抓屏有内容（证据 `example/evidence/v85x_20261003_full.png`）。口径：示例为 1024×600、面板 480×1600，验的是**组件可用性**，不是版式 |

## 跨平台注意事项（平台通用）

1. **不要用 `ZKBase::getAbsolutePosition()`**：设备端 `libeasyui.so` **未导出该符号**（也没有 `getParent`）——
   编译链接能过，运行时 `dlopen` 失败 → **应用黑屏、无任何日志**（极易误判成驱动问题）。本组件全程只用
   「父相对 `getPosition()`」，就是因为这条。
2. **分辨率无关**：下划线几何按页签矩形实时算（`高/13`、最小 2px），1024×600 与 1280×800 共用一份代码，
   不需要平台宏。
3. **easyui 版本**：以下版本的 `ZKPageWindow.h` **已逐个核对**，都含 `IPageChangeListener / getPageSize / getCurrentPage / setCurrentPage / setPageChangeListener / turnToNextPage / turnToPrevPage`：
   `z21/2.2.0`、`z21/2.6.0`、`z20/2.6.0`、`z20/3.0.0`、`v85x/2.3.0`、`v85x/2.9.0`、`f133/2.9.0`、`t113emmc/2.9.0`、`f136/2.10.0`。
