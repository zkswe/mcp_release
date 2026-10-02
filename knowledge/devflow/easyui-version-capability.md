---
id: devflow-easyui-version-capability
title: easyui 版本 → 控件/API 可用性（三步判定 + 实测矩阵）
category: devflow
status: review
confidence: manual
verified_at: 2026-09-30
stale_days: 180
origin: partial
source: 2026-09-24 现场「设置页只有标题、scrollwindow 不显示」+ 2026-09-27 Z20 逐版本核实（要求查清）
needs_evidence: true
platforms: [Z20]
tags: [easyui版本, 控件不支持, 控件看不到, relayout, 版本不一致, 空页, 控件没渲染]
evidence:
  - "Z20 三层实测：registry 2.6.0 / 3.0.0 的 include/ + 设备 /lib/libeasyui.so 的 40 个 ZKScrollWindow 符号"
  - "设备运行库版本：getprop ro.easyui.version（86 面板实测 2.4.0）"
  - "relayout 版本边界：knowledge/devflow/dynamic-screen-rotation.md §4 逐版本矩阵"
---
# easyui 版本 → 控件/API 可用性（三步判定 + 实测矩阵）

> 检索导引：easyui 版本 / 控件不支持 / 控件看不到 / **scrollwindow 不显示**/ 页面只有标题 / 空页 /
> 控件没渲染 / relayout 不可用 / 要 easyui ≥ x.y.z / 编译期头版本 vs 设备运行库版本 /
> `ro.easyui.version` / `/lib/libeasyui.so` / `.deps.lock` 的 revision / 怎么判某个控件在不在。
> 用途：**「这个控件/API 到底存不存在」的唯一可信判定法**；以及“页面只有标题/改了像没改”的排查顺序。
>
> ⚠️ 边界：本方法**只用于判「类/API 是否存在」**（能力存在性）。**控件用法、json 字段语义、回调行为**
> 只认 MCP 知识库 + 官方文档站（`developer.flythings.cn`）—— 见 `knowledge/uicontrols/retrieval-boundary.md`。

## 1. 三步判定法（别猜、别只读一个地方）

| 步 | 看什么 | 命令 / 位置 |
|---|---|---|
| ① 工程**编译期**解析到哪个版本 | `Manifest.xml` 写的是范围（`^2.2.0` 之类），真正生效的是锁文件 | `<工程>/.deps.lock` → `"id":"easyui"` 的 **`"revision"`**；实际 include：`.fun/<平台>/build.ninja` 里的 `-I…/easyui/<版本>/include` |
| ② 该版本**有没有**这个控件/API | registry 各版本 `include/` grep 类名/函数名 | `<registry>/public/<平台>/easyui/<版本>/include/`（Z20 本机实有 2.6.0 / 3.0.0）<br>`grep -rl ZKScrollWindow <registry>/public/z20/easyui/*/include/` |
| ③ 设备**运行期**那份库有没有 | 控件类由**运行库**提供（工程只编译头） | `getprop ro.easyui.version` + `strings /lib/libeasyui.so \| grep -E 'ZKScrollWindow\|_ControlFactory_ZKScrollWindow'`（设备无 strings 就 pull 回 PC 跑） |

**三条纪律**：① 只读 `Manifest.xml` 会看错版本（范围 ≠ 生效版本）；② 编译期版本 ≠ 设备运行库版本，
不一致本身不报错，风险只在「用到运行库没有的类/API」时**静默不渲染**（无编译错、无运行期报错）；
③ 规避 = `Manifest` 依赖版本 ≤ 目标机 `ro.easyui.version`，或先按步③证明类存在。

## 2. 实测矩阵（Z20，2026-09-27）

| 能力 | registry 2.6.0 | registry 3.0.0 | 设备运行库（`/lib/libeasyui.so`） |
|---|---|---|---|
| `ZKScrollWindow`（滚动窗口） | ✅（头更全：`setScrollbarColor` / `moveTo` / `setScrollStep` / `onBeforeCreateWindow` 等） | ✅（头是**裁剪版**，不含上面那几个） | ✅ **40 个 `ZKScrollWindow*` 符号**，含 `_ControlFactory_ZKScrollWindow::create` → 运行期真能创建 |
| 其余内置控件（ZKPageWindow / ZKSlideWindow …） | ✅ | ✅ | ✅ |
| `ConfigManager::setScreenRotate / setTouchRotate / getScreenRotate` | ✅ | ✅ | ✅ |
| `Activity/BaseApp::relayout`（运行时换布局） | ❌ | ❌ | ❌ **需 easyui ≥ 2.9.0**（见 `dynamic-screen-rotation.md`） |

**结论**：**`scrollwindow` 不是版本问题**—— 2.6.0 / 3.0.0 / 设备库三层都有；“某版本不支持 scrollwindow”
这个假设**不成立**，别往这个方向查。

**两个易混版本号**：设备 `ro.easyui.version`（运行库，如 86 面板实测 **2.4.0**）≠ 工程解析到的
编译期头版本（如 2.6.0）。**面板机型常见 2.4.0**：用新控件/新 API 前先用步① 核对，别只看本机 registry。

## 3. 「控件看不到 / 页面只有标题 / 改了像没改」排查顺序（按命中率）

1. **设备加载的是哪一份 lib/ui？**（现场最高频）—— EasyUI.cfg 优先级 `/tmp` > `/mnt/extsd` > `/res/etc`；
   SD 卡那份 `startupLibPath` 会把程序**劫持**到旧 lib/旧 ui → 见
   `knowledge/devflow/package-properties-easyui-cfg.md`。
2. **产物真的同步了吗？**—— 改 `ui/*.json` 必须**立刻 fui pack 出 ftu**（ftu 是设备加载物；
自动同步规则是「ftu 比 json 新 ≥60s 才 ftu→json 回写」）→ 反查 `fui unpack ui/xxx.ftu tmp.json`。
3. **版本/API 存不存在**—— 本文 §1 三步判定（“不存在”其实是低概率方向）。
4. **控件结构与字段**—— 例：`scrollwindow` 只装 `window`、内容尺寸 > 视口才滚、`touchable` 缺了不可拖、
固定件（标题/底部按钮）要放 scrollwindow **外面**→ `knowledge/uicontrols/scroll-drag-interaction-spec.md`。
5. **可见性 / 启动态**—— `visible:false`、被上层装饰层盖住、z 序压住、`getprop sys.zkapp.state` 不是
   `running`（画面没切给应用，屏上是 logo 或上一页）。

## 4. 修法 / 规避（工程纪律）

- **要新 API**：`Manifest.xml` 改版本 → **`fun install`**（刷新 `.deps.lock` 与 include 路径；
不 install 新包 include 不进 CMake = 加了也白加）→ 编译 → 再按 §1 步③确认**目标设备**运行库也有。
- **设备库太老**：找 FlyThings 厂家（中科世为）要带该能力的新 easyui，**不要**在业务代码里模拟。
- **写新页面要上 scrollwindow**：只有「内容总高 > 可视高」才上；先按 §3-4 把结构摆对，再去怀疑版本。

## 5. 相关

- `knowledge/devflow/dynamic-screen-rotation.md`（`relayout` 逐版本实测矩阵）
- `knowledge/devflow/package-properties-easyui-cfg.md`（EasyUI.cfg / startupLibPath 劫持）
- `knowledge/uicontrols/scroll-drag-interaction-spec.md`（滚动/拖拽参数口径）
- `knowledge/hardware/z20-display-rotate-flip180.md`（整屏旋转，与 relayout 是两件事）
