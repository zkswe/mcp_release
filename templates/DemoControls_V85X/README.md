# DemoControls_V85X —— 常用功能演示模板（480×800 / V85X）

> **一句话**：`HelloWord_*` 是空骨架；这份是「滑动菜单主界面 + 7 类常用控件各一页」的可跑样例，
> 用来**演示 / 真机验收 / 当多页工程起点**。骨架（`src/Main.cpp` + `src/uart/*`）与
> `templates/HelloWord_Z20/src` **逐字节一致**（`scripts/sync_project_skeleton.py --check` 管着）。
> 真机验收日期：2026-10-04（设备 `20080411` / Zkswe_V85X_SPINOR / 480×800），7 页全通过。

## 1. 里面有什么

> 截图列**已去掉**（2026-10-05）：真机验收截图是**会话产物**，落在被 `.gitignore` 的 `temp/` 下
> （按需求方口径「temp 只是测试，可以全删」）—— 写进 README 等于指向不存在的文件。
> 要复现验收：照 §7 的三条命令现场抓屏。

| 页（`ui/<p>.json` → `<p>Activity`） | 演示的控件 |
|---|---|
| `main`（主界面：`window__1` 容器 + 7 个图标磁贴按钮；**2026-10-05 起不再用 slidewindow**） | window / button(picTab) / textview |
| `text` 文本控件 | textview 字号 14/20/32/44、alignment 0/36/37/38、colorTab、跑马灯 roll |
| `button` 按键 / 输入 | button、**带图标按键**（切图==控件盒，图标烘焙在图内）、checkbox、edittext |
| `progress` 进度条 / 滑条 | seekbar（可拖，条 448×32 + 滑块 32×32）、circlebar（按进度裁图成扇形） |
| `pointer` 指针 / 表盘 | pointer：表盘底图 + 指针图 + **1s 定时器驱动 `setTargetAngle`**（真机可见转动） |
| `canvas` 画布绘制 | painter：fillRect / drawRect / fillArc / drawArc / drawLines(线宽) |
| `scroll` 滚动窗口 | scrollwindow（`orientation:1` 竖向 + 内层 `window` 承内容，12 行） |
| `page` 翻页窗口 | pagewindow（3 个 window **都 `visible:true`**，滑动翻页） |

⛔ **新建页面之前先看 `.settings/com.zksw.flythings.easyui.prefs` 的 `resolution`**：
IDE 新建页会**按它自动填分辨率**（2026-10-05 实测踩到：本模板工程是 480×800，而 prefs 里
还是从 `HelloWord_V85X` 继承来的 `480x480` → 新建的页被自动写成 480×480）。现已改为 `480x800`。
（`HelloWord_V85X` 本身就是 480×480，它写 480x480 是对的，别一起改。）

`resources/images/`：8 张磁贴（`menu_*.png`，200×96）+ 进度页切图（`pb_*.png`）+ 表盘/指针（`pt_*.png`）
+ 图标钮切图（`bt_icon_toggle*.png`）。

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
- 主界面新增磁贴 = 在 `ui/main.json` 的 **`window__1`**（不能再用 slidewindow：平铺子控件不合层级规范，
  见 §8）里加一个 `button__<N>`（`left:8, top:8+i*100, 宽 200, 高 96`）
  + 在 `mainLogic.cc` 加 `onButtonClick_menu<X>(ZKButton*)` 回调。

## 4. 换图标 / 换切图

| 用途 | 文件 | 尺寸口径 |
|---|---|---|
| 主界面磁贴 | `menu_<页名>.png` | **== 控件盒**（本模板 200×96） |
| 进度条轨道 / 有效值 | `pb_track.png` / `pb_fill.png` | == 控件盒（448×32）、小圆角 r=4（2026-10-05 重出：原先是 450×34 药丸形，见下） |
| 圆环底 / 有效环 | `pb_ring_bg.png` / `pb_ring.png` | == 控件盒（200×200） |
| 滑块 | `pb_thumb.png` | == `thumb.size`（32×32 == 条高；**不是**控件盒） |
| 表盘 / 指针 | `pt_dial.png` / `pt_needle.png` | 表盘 == 控件盒（300×300）；指针 == `pointerSize`（16×140），铰点 = `fixedPoint`（8,134） |
| 带图标按键 | `bt_icon_toggle(_p).png` | **== 控件盒**（216×64）：图标烘焙在图内、其余真透明（`iconPosition` 只是"位置"不是盒子，check_all #11 按控件盒核尺寸） |

- 一律放 `resources/images/`，json 里写 `images/xxx.png`（**不带** `resources/` 前缀、不写绝对路径）。
- ✅ **进度条两张图已按本节口径重出（2026-10-05，需求方拍板）**：原来是 **450×34 药丸形**（r = 条高/2），
  与「图 == 盒」冲突（`check_all` #11 报 `450x34 != 448x32`）；现用 `ui_tools/gen_res.py` 的
  `rounded_rect_cov(448, 32, 4, …)`（α = 覆盖率口径，不是 1x 直画）重出为 **448×32 / r=4**，颜色沿用原图
  （轨道 `#24304A` = 36,48,74；有效值 `#4DA6FF` = 77,166,255）。重出后 `check_all` 该项转 PASS。
- `menu_back.png` 是**孤儿**（72×72、全仓没有任何 json 引用它，只有本节提过）——要么删，要么真接进主界面。
- 出图优先 `op flythings_generate_ui_assets`（图标）或 `ui_tools/gen_res.py` 的公开函数；**禁止 1x 直画**。
- ⚠️ **进度条的「有效图」会被平台按进度横向拉伸**（离线渲染器同口径：`resize((w*frac, h))`）——
  所以药丸形端头在低进度时圆角会被压小，轨道色从月牙处露出来（**参考工程同样是药丸形，同样躲不掉**）。
  条族请用小圆角（本模板 r=4，缩放后错位 ≤1.6px）或纯直角，别用「条高/2」的大圆角。

## 5. 出图规范（抗锯齿五要素，真机见真章）

1. **强曲率形状**（圆 / 圆环 / 药丸 / 细圆条 / 圆角≥min(w,h)/2）走 **8× 超采样 + 面积平均（`Image.BOX`）**：
   `gen_res.rounded_rect_ss(w, h, radius, fill, ss=8)`；圆环用覆盖率口径
   `coverage_mask(外圆) − coverage_mask(内圆)`（别拿半透明层叠，会出脏边）。
2. **尺寸 == 控件盒**：引擎对「图 ≠ 盒」是**拉伸填充、不报错**，所以这是**质量纪律**（非整数缩放必糊／正圆变椭圆）。
3. **rect 族必须有倒角**（`drawRect(..., radius)` 或切图 `radius > 0`），直角在圆角界面上就是磁贴。
4. **形状外真透明**：四角 `alpha == 0`（生成后自检）。
5. 文件名进 json 前先自检：`op flythings_verify_assets(project_root)` / `ui_tools/check_all.py` 的第 21/22/23 项
   （`aa_audit` 锯齿 / `corner_audit` 倒角 / `alpha_bg_audit` 底板）。

## 6. ⛔ 五个真机坑（本模板实测踩过，别再犯）

1. **`circlebar` 的 `progressPicPos` / `touchRange` 必须是对象**（`{left,top,width,height}` / `{lower,upper}`）。
   写成 `0`（旧注册表把它们误声明成 `int`）→ 真机**进这一页时主线程 100% 空转、一条日志都不出**（假死，
   截图是冻结帧）。已修 `ui_schema.json` v1.1，`ui_schema_loader.type_check` 现在按 **fatal** 报。
2. **所有子盒字段**（`thumb` / `position` / `range` / `padding` / `colorTab` / `size` / `point` …）写成标量 =
   同类**无声挂死**（规则见注册表 `valueRules.subboxType`）。
3. **截图会滞后一帧**（`/dev/fb` 抓到的是上一帧）：判「进没进页」**以 logcat 为准**，截图**连抓两帧取第二张**。
4. **`pagewindow` 的子 `window` 必须都 `visible: true`**（真机实测）：把非首页设成 `visible:false` 后，
   翻到那一页是**空白**（`pagewindow` 自己负责"显示哪一页"，不需要你用 visible 关）。
5. **`scrollwindow` 的 `orientation`：0 = 横向、1 = 竖向**（真机实测）：竖排列表写成 0 时上下拖**毫无反应**；
   且内容必须放进**内层 `window`**、内层高度要**大于视口**（本模板 700 > 560）才有可滚空间。

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

7 页逐页结果（进页 ✓ / 返回 ✓ / 无假死 ✓）。抓屏产物落在 `temp/`（**不进库**，按需求方口径「temp 只是测试，可全删」）——
要复现就照上面的命令现场抓。

## 8. 本模板的 `check_all` / `ui_compile` 状态（2026-10-05 检讨按实测重写）

`python ui_tools/check_all.py templates/DemoControls_V85X`（基线：`templates/HelloWord_V85X` 全 PASS）
＋ `python ui_tools/ui_compile.py templates/DemoControls_V85X`。

- **`ui_compile`（编译式验收）：`fatal=0 error=0` 通过**（8 页 / 71 控件；5 条 warn 是「注册表外字段」提示）。
- `check_all`：已修 13 项里的 12 项（8 个 Logic 缺 `REGISTER_ACTIVITY_TIMER_TAB`、文本页特殊字符、
  文本页 7 处最小尺寸、`scrollwindow` 补内层 `window`、图标钮 `picTab` 改控件盒尺寸、
  **主界面 `slidewindow` → `window__1`**（层级规范）、**进度条切图 450×34 → 448×32**（见 §4））。

**剩余 1 项**（"真机可见可用、但与判据不一致"，未擅自改）：

| FAIL | 现象 | 收口法 |
|---|---|---|
| `ui/text.json`：`rollA/rollB` 最小尺寸（需 ≥964×22，盒 448×40） | **这是跑马灯的设计意图**（长串横向滚动；真机两行各停在同一长串的不同段 = 滚动生效） | ⚠️ `check_all` #13 没有 `rollEnable` 豁免 —— 跑马灯页**必然**红。要么给 checker 加「`rollEnable=true` 跳过 #13」的豁免，要么牺牲这页的跑马灯演示 |

## 9. 其它已知缺项（如实登记，尚未做）

- ~~第 9 个页面 `maintest`~~ → **已删（2026-10-05，需求方确认那是他做测试用的页）**：
  `ui/maintest.{json,ftu}` + `src/activity/maintestActivity.*` + `src/logic/maintestLogic.cc` 全部移除，
  IDE 构建残留（`Release/`）一并清掉。**它当年 resolution 写成 480×480 的根因已修**：
  `.settings/com.zksw.flythings.easyui.prefs` 的 `resolution` 是 480x480（继承自 `HelloWord_V85X`），
  而 IDE 新建页面按它自动填 → 见 §1 的提醒（现为 `480x800`）。
- `menu_back.png` 仍是孤儿（见 §4）；`check_all` 对 `window` 里的子控件键会报「注册表外字段」WARN
  （`ui_compile` 不报，属提示性噪音）。
- 本模板**不含字体副本**（`font/` 未入库）：中文靠设备字体或 `flythings_device_preflight` 自动投递
  （见 `knowledge/devflow/custom-font-config.md`）。
