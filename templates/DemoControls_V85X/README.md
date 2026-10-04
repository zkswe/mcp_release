# DemoControls_V85X —— 常用功能演示模板（480×800 / V85X）

> **一句话**：`HelloWord_*` 是空骨架；这份是「滑动菜单主界面 + 7 类常用控件各一页」的可跑样例，
> 用来**演示 / 真机验收 / 当多页工程起点**。骨架（`src/Main.cpp` + `src/uart/*`）与
> `templates/HelloWord_Z20/src` **逐字节一致**（`scripts/sync_project_skeleton.py --check` 管着）。
> 真机验收日期：2026-10-04（设备 `20080411` / Zkswe_V85X_SPINOR / 480×800），7 页全通过。

## 1. 里面有什么

| 页（`ui/<p>.json` → `<p>Activity`） | 演示的控件 | 真机截图 |
|---|---|---|
| `main`（主界面：slidewindow + 7 个图标磁贴按钮） | slidewindow / button(picTab) / textview | `temp/fix_main.png` |
| `text` 文本控件 | textview 字号 14/20/32/44、alignment 0/36/37/38、colorTab、跑马灯 roll | `temp/acc_text.png` |
| `button` 按键 / 输入 | button、checkbox、edittext | `temp/acc_button.png` |
| `progress` 进度条 / 滑条 | seekbar（可拖）、circlebar（按进度裁图成扇形） | `temp/acc_progress.png` |
| `pointer` 指针 / 表盘 | pointer（⚠️ 见 §8 已知缺项） | `temp/acc_pointer.png` |
| `canvas` 画布绘制 | painter：fillRect / drawRect / fillArc / drawArc / drawLines(线宽) | `temp/one_canvas.png` |
| `scroll` 滚动窗口 | scrollwindow（12 行） | `temp/acc_scroll.png` |
| `page` 翻页窗口 | pagewindow（3 窗） | `temp/acc_page.png` |

`resources/images/`：8 张磁贴（`menu_*.png`，200×96）+ 5 张进度页切图（`pb_*.png`）。

## 2. 怎么用它建新工程

```bash
cp -r templates/DemoControls_V85X <新工程目录>
# 改工程名：<新工程>/.project 的 <name>、.cproject 里的工作区路径（或直接走 op flythings_create_project
# 建 HelloWord_V85X，再把本模板的 ui/ src/logic/ resources/ 覆盖过去）
fun install --project-dir <新工程>          # 同步 Manifest 依赖（base-utility 必须有）
fun build   --project-dir <新工程> -p v85x  # 编译
# 上机：op flythings_build_ui_flow(project_root=<新工程>, device=<serial>)
```

## 3. 加一页（三步，桩不许手写）

1. **写 json**：`ui/<p>.json`。控件键名 = `<类型>__<序号>`，字段按**必填键全集**写全
   （唯一真源 `ui_tools/ui_schema.json`；片段用 op `flythings_map_control`，字段问 op `flythings_ui_schema`）。
2. **打包**：`fui pack ui/<p>.json ui/<p>.ftu`（设备实际加载的是 ftu，不是 json）。
3. **构建**：`fun build --project-dir <工程> -p v85x` → 工具链生成 `src/logic/<p>Logic.cc` 与回调桩
   （桩由工具链追加；若桩落在函数内，把它移到文件作用域）。

- ⛔ **不要删含业务代码的 `<p>Logic.cc`**（代码衰退）；只有首次构建/空文件才可删了重建。
- 跳转/返回业务代码**不分叉**：`EASYUICONTEXT->openActivity("<p>Activity")` / `EASYUICONTEXT->goBack()`。
  （fun 构建不产出 `<p>Activity.*`，那是**构建层**差异，不是缺陷。）
- 主界面新增磁贴 = 在 `ui/main.json` 的 `slidewindow__1` 里加一个 `button__<N>`（`left:8, top:8+i*100, 宽 200, 高 96`）
  + 在 `mainLogic.cc` 加 `onButtonClick_menu<X>(ZKButton*)` 回调。

## 4. 换图标 / 换切图

| 用途 | 文件 | 尺寸口径 |
|---|---|---|
| 主界面磁贴 | `menu_<页名>.png`（+ `menu_back.png`） | **== 控件盒**（本模板 200×96） |
| 进度条轨道 / 有效值 | `pb_track.png` / `pb_fill.png` | == 控件盒（448×64） |
| 圆环底 / 有效环 | `pb_ring_bg.png` / `pb_ring.png` | == 控件盒（200×200） |
| 滑块 | `pb_thumb.png` | == `thumb.size`（24×24，**不是**控件盒） |

- 一律放 `resources/images/`，json 里写 `images/xxx.png`（**不带** `resources/` 前缀、不写绝对路径）。
- 出图优先 `op flythings_generate_ui_assets`（图标）或 `ui_tools/gen_res.py` 的公开函数；**禁止 1x 直画**。

## 5. 出图规范（抗锯齿五要素，真机见真章）

1. **强曲率形状**（圆 / 圆环 / 药丸 / 细圆条 / 圆角≥min(w,h)/2）走 **8× 超采样 + 面积平均（`Image.BOX`）**：
   `gen_res.rounded_rect_ss(w, h, radius, fill, ss=8)`；圆环用覆盖率口径
   `coverage_mask(外圆) − coverage_mask(内圆)`（别拿半透明层叠，会出脏边）。
2. **尺寸 == 控件盒**：引擎对「图 ≠ 盒」是**拉伸填充、不报错**，所以这是**质量纪律**（非整数缩放必糊／正圆变椭圆）。
3. **rect 族必须有倒角**（`drawRect(..., radius)` 或切图 `radius > 0`），直角在圆角界面上就是磁贴。
4. **形状外真透明**：四角 `alpha == 0`（生成后自检）。
5. 文件名进 json 前先自检：`op flythings_verify_assets(project_root)` / `ui_tools/check_all.py` 的第 21/22/23 项
   （`aa_audit` 锯齿 / `corner_audit` 倒角 / `alpha_bg_audit` 底板）。

## 6. ⛔ 三个真机坑（本模板实测踩过，别再犯）

1. **`circlebar` 的 `progressPicPos` / `touchRange` 必须是对象**（`{left,top,width,height}` / `{lower,upper}`）。
   写成 `0`（旧注册表把它们误声明成 `int`）→ 真机**进这一页时主线程 100% 空转、一条日志都不出**（假死，
   截图是冻结帧）。已修 `ui_schema.json` v1.1，`ui_schema_loader.type_check` 现在按 **fatal** 报。
2. **所有子盒字段**（`thumb` / `position` / `range` / `padding` / `colorTab` / `size` / `point` …）写成标量 =
   同类**无声挂死**（2026-10-02 iMirror 固件 A/B 实测；注册表 `valueRules.subboxType`）。
3. **截图会滞后一帧**（`/dev/fb` 抓到的是上一帧）：判「进没进页」**以 logcat 为准**，截图**连抓两帧取第二张**。

## 7. 真机验收口径（可复现，2026-10-04 记录）

```bash
adb push bin_tools/v85x/touch /data/touch && adb shell chmod 777 /data/touch
adb shell /data/touch tap 108 <152 + i*100>      # 菜单第 i 项中心（slidewindow top=96 + item top=8+i*100 + 高 96/2）
adb shell /data/touch tap 76 748                 # 各页「返回」键中心
```

| 判据 | 怎么看 |
|---|---|
| 真进页 | logcat 出现 `[<p>Logic.cc:.. onUI_show]`（不是"看截图像不像"） |
| 真返回 | logcat 出现 `[mainLogic.cc:26 onUI_show]` |
| 主线程假死 | `/proc/<pid>/stat` 的 `utime+stime` 增量（100 ticks/s）> 50% 且日志静止 |
| 应用起没起 | `/proc/<pid>/comm == zkgui_ui` 且 state 从 `D/R` 回到 `S`（启动瞬间的 `D` 是正常的，别急着断电） |

7 页逐页结果（进页 ✓ / 返回 ✓ / 无假死 ✓）与截图见 `temp/acc_*.png`。

## 8. 已知缺项（如实登记，尚未做）

- **`pointer` 指针页目前只有标题 + 返回**：`pointer__1` 的 `backgroundPic` / `pointerPic` 都是 `''`（无表盘、无指针图），
  也没有 `setTargetAngle()` 的定时驱动 → 页面上看不到控件。补齐需要：表盘底图 + 指针图
  （`rotationPoint` = 控件系圆心、`fixedPoint` = 图系铰点、`pointerSize` == 指针图尺寸）+ 一个定时器。
- **`text` 文本页的跑马灯两条**：长文本**溢出控件盒**（未水平滚动）；底部长文本行同样溢出。
  需按「文本盒高/字号」口径重排，或把 roll 参数调对（`rollEnable/rollDirection/rollStep/rollIntervalTime`）。
- 本模板**不含字体副本**（`font/` 未入库）：中文靠设备字体或 `flythings_device_preflight` 自动投递
  （见 `knowledge/devflow/custom-font-config.md`）。
