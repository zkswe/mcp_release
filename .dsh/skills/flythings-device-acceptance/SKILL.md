---
name: flythings-device-acceptance
description: FlyThings 改完代码/界面后的真机验收流程（编译 → 推送 → 抓屏 → 像素比对 → 结论）。用户说「跑一下看看 / 上机验证 / 界面不对 / 效果确认 / 验收 / 真机测试」或任何改动需要确认在设备上真的生效时加载。给出逐步判据链与常见"看起来好了"的假通过。
---

# 真机验收

## 为什么必须上机

FlyThings 的**编译通过 ≠ 功能正确**。实测过的假通过：

- 界面**布局对但视觉错**（圆角被 `backgroundColor` 回填成直角、AA 边缘发白）；
- **逻辑没跑**（`onUI_init` 里抛异常 → 页面空白，但编译 0 错误）；
- **设备上跑的还是旧版**（推送没成功/推错设备）；
- **平台差异**（A 平台验过的写法在 B 平台不成立）。

所以验收判据是"**设备上抓到的画面 + 日志**"，不是"我改完了"。

## 步骤（按顺序，每步都有判据）

### ① 静态自检（不连设备，先排掉低级错）

| op | 查什么 |
|---|---|
| `flythings_validate_project(project_root)` | 工程结构与必填项 |
| `flythings_check_project_deps(project_root, platform)` | include 与 Manifest 声明是否对得上 |
| `flythings_verify_assets(project_root)` | 图片/资源是否都在、尺寸是否合规 |
| `flythings_layout_audit(project_root)` | 纯几何判定（z 序=json 书写顺序；同层更早的 touchable 先拿触摸；遮挡） |
| `flythings_device_preflight(project_root, device=...)` | 设备侧体检：**字库覆盖**（缺字显示方块）/ 体积 / 能力适配 |

### ② 编译 + 推送

```
fun.exe build                 # rc 必须为 0；产物在 .fsc/<平台>/
fun.exe launch                # 推到设备（UI 资源 → /tmp/ui/，库 → /tmp/lib/）
```

⚠️ **三个硬失败点**（都真发生过）：

1. **多台设备 → `fun launch` 硬失败**（`FATAL more than one device/emulator`，带不带 `-s` 都一样）
   → 先 `adb devices` 确认只剩目标机，或用 `-s <serial>` 并确认 fun 自带的 Go adb 客户端
   （直连 `127.0.0.1:5037`）也能看到同一台。
2. **设备与工程平台必须一致**，否则 `FATAL platform not match`。
3. **adb 看不到板子**：先查 ADB 驱动 + USB 调试授权（随包带 adb，**不需要**装 Android SDK）。

只编译不上机时用 `with_launch=False`（见 `knowledge/devflow/adb-and-device-selection.md`）。

### ③ 抓屏（验收的证据）

```
flythings_device_screenshot(device='', layer='ui', ...)
```

- 默认抓 UI 层；`layer` 可选其它层（画面黑/花时先确认抓的是哪一层）。
- 抓下来的图**存进工程/临时目录**，别只留在内存里 —— 结论要能被别人复验。
- 已有基线时用 **op `flythings_ui_visual`** 做像素比对（`action='diff'`，可给
  `tolerance` / `min_area` / `allow_regions`），它比"我肉眼看差不多"可靠得多。

### ④ 比对与结论

| 场景 | 判据 |
|---|---|
| 有基线图 | `flythings_ui_visual` 的差异率 + 差异**区域**是否只在预期处（别把整屏都算成"噪声"） |
| 没基线图 | 出图给用户确认（**不要自己宣布通过**）；顺手把这次定为基线 |
| 只有单页改动 | 先离线渲染看布局（`flythings_ui_preview` / `flythings_build_ui_flow`），再上机看**视觉** |

### ⑤ 出问题 → 留证据

```
flythings_bugreport(title, project_root, device, symptom, steps, expected, actual, evidence)
```

把**抓屏 + logcat 摘录**一起留档。只写"不行"的结论没有复用价值。

## 假通过清单（自查，别自己骗自己）

| 假通过 | 真相 | 怎么识破 |
|---|---|---|
| "编译 0 错误" | 运行期可能异常 | 上机看画面 + 日志 |
| "界面出来了" | 视觉可能错（圆角/颜色/字体） | 像素比对或放大看边缘 |
| "跟上次一样" | 设备上可能是旧版 | 确认推送成功（时间戳/版本号） |
| "在 A 平台验过了" | B 平台可能不成立 | 按平台实测表逐平台确认 |
| "我肉眼看没问题" | 差异可能只有几个像素 | 用 `flythings_ui_visual` 量 |

## 记录回写（仓库约定）

- 新发现的坑/平台结论 → 回写到权威文档（`packages/<包>/platforms.md`、组件 `platforms.md`、
  或 `knowledge/` 下对应页），带**证据**（截图/log 摘录）；
- **没实测的不写结论**；实测过的必留证据。这是仓里"待补证据 98 篇"被逐篇消掉的方式。
- 用 op `flythings_knowledge_capture` 落盘，别只在对话里说。
