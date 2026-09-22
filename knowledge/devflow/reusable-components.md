# 可复用组件（components）—— 组件化落地规范

> 检索导引：可复用模块 / 组件化 / 封装一层 / wxapi 风格 API / 参考代码目录 / 组件规范 / 四件套 /
> 模块目录 / 资产型模块 / 组件 README / 平台说明 / package 引用
> 定规：2026-09-13（沛哥：落地形态 = 在参考代码目录下提供 `components/` 模块，以后模块代码放这里；
> 规范 = 落地 README + package 引用 + 平台说明 + 代码直接可以调用）

---

## 0. 一句话

**把散落在专题文章/聊天/各工程里的"这么做就对了"，沉淀成可复用模块**：一个模块一个目录，四件套齐全，拿去能编、能跑、能查。

现状（**随 MCP 发布的路径：`components/`**，即本仓 `tools/FlyThings_mcp_open/components/`；
这样所有接入本 MCP 的 AI 都能直接拿到代码）：

| 模块 | 类型 | 说明 |
|---|---|---|
| `ble/` | 代码型 | BLE 门面 `zk::ble`：把蓝牙收拾成 wxapi 那种（**一个 API 面、两个后端**：中心扫描/连接/GATT + 外设广播/GATT 服务/notify）；中心：F133、V85X；双角色：Z20/Z21/T113EMMC |
| `blur/` | 代码型 | 高斯模糊（铺底/封面背景）`zk::`：拖一张 4 字节 BGRA 位图进，出一张模糊图；**切歌时算一次**不逐帧重算；带 `prep`/`darken`/`bench_once`，档位 AUTO/BOX3/SEP_*/RVV；真机 F133 缩图铺底 **59~88 ms**（详见 §7） |
| `fonts/` | 资产型 | 思源黑体三版（常用中文872KB / 全中文7.4MB / 多国语言10.5MB）+ 设备字体自检（缺中文自动投递） |

---

## 1. 目录与四件套（硬要求）

```
components/
└─ <模块名>/                     ← 小写中划线/单词，如 ble、fonts、ota
   ├─ README.md                  ← ① 落地 README：是什么 / 怎么用 / API / 依赖 / 限制 / 排错
   ├─ platforms.md               ← ② 平台说明：哪些平台可用、每平台前置条件与实测值、已知限制
   ├─ Manifest.xml               ← ③ package 引用：需要哪些底层包、怎么声明；外部怎么引用本模块
   ├─ include/ + src/            ← ④ 头文件 + 实现（代码型模块）
   ├─ example/                   ←    可直接调用的最小示例（能拷进工程就跑）
   └─ scripts/ + <产物目录>/      ←    资产/工具型模块：可复现的生成/检查脚本 + 产物（如字体）
```

**两种模块形态**（都算合格）：

- **代码型**（默认）：`include/ + src/ + example/`，对外命名空间 `zk::<模块>`，头文件 `include/zk/zk_<模块>.h`；
- **资产/工具型**（如 `fonts/`）：无 `include/src`，四件套对应为
  `README.md + platforms.md + scripts/（可复现的生成/检查脚本）+ 产物目录`，使用方式写成"一条命令"。

**四件套缺一不收**：没有 `platforms.md` 的模块 = 把"什么板子上会翻车"藏起来了；
没有 `example/` 的模块 = 让下一个人从零猜调用姿势。

---

## 2. 代码规范（review 尺子）

1. **不把底层库类型泄漏到对外头文件**：BLE 模块对外只有 `std::string`，没有 `bd_addr_t` / `hci_con_handle_t`。
   想用底层的自己 include 底层头，别逼所有人一起。
2. **统一结果类型** `Result{code, msg}`：`msg` 必须是**人话**（可直接打日志/回给用户）；禁止只回 `-1`、禁止静默失败。
3. **默认参数要安全**：不传参也能跑；有超时；写操作默认"要回应"。
4. **线程模型写进 README**：哪些回调在库线程里被调、业务能做什么不能做什么；跨线程一律库内封装，
   不要求业务理解底层 run loop。
5. **平台差异关在内部**：`#ifdef`/平台分支只允许出现在平台适配层，业务层代码里不出现平台名。
6. **可诊断 > 可配置**：能自动探测的不做成配置项；探不到就明确报错并给出"下一步查什么"
   （如 `zk::ble` 的 `getDiag()` 一次给 芯片/上电/预初始化/HCI状态/真实事件数/hint）。
7. **资源/节点路径一律给候选链**（不同板子内核枚举不同，写死必翻车）。
8. **日志要能接出去**：库内部日志提供钩子（如 `setLogHook`），否则 app 模式下 stdout 是 `/dev/null`，
   现场排错只能靠猜。

---

## 3. package 引用（怎么让工程用上）

**A) 源码引入（起步推荐）**：把 `components/<模块>/` 整目录拷进工程 `src/` 下，
并在工程 `Manifest.xml`/`fun.json` 声明模块所需底层包（见模块自己的 `Manifest.xml`）。

**B) 依赖包引用（模块定型后）**：模块按平台编出 `include/ + lib/`，注册进包仓库，工程一行：
```xml
<package id="<模块名>" version="x.y.z"></package>
```
版本号**写死**，不用 `^` 浮动（底层 ABI 一变就不可复现）。

⚠️ 工程侧两个坑：`fun.json` **优先于** `Manifest.xml`（依赖写 `fun.json`）；
`type:"executable"` 才出可执行 ELF（否则出 `libzkgui.so`）。

⚠️ 模块自己的 `Manifest.xml` 里声明底层包时，**框架基础包 `base-utility` 不能漏**：fun 生成的
`generated/event_dispatcher.h` 等固定 `#include <base/functional.h>`（`base-http-client` 的 `base/http_*.h`、
`base-json` 的 `base/json_*.h` 不算）。漏了工程侧表现是 `fatal error: base/functional.h: No such file or directory`，
且**改 Manifest 后必须重跑 `fun install`**（include 路径才进 CMake）——
详见 `cli-fun-toolchain.md` §4.7「老工程升级：补 base-utility」。

---

## 4. platforms.md 必须写什么

每个平台一段：可用性（可用/部分可用/不支持）、**前置条件**（电源/串口/固件/属性门）、
实测值（节点路径、波特率、校验、超时、包版本）、已知限制、真机验收步骤。
**禁止写"应该可以"**；没实测的标 `未验证`。

---

## 5. 新增模块 checklist

- [ ] 目录名/命名空间定好（`zk::<模块>` / `include/zk/zk_<模块>.h`，或资产型则定产物与脚本入口）
- [ ] `README.md`：用法（10~30 行可跑示例）+ API 表 + 依赖 + 限制 + 排错
- [ ] `platforms.md`：逐平台前置条件与实测值（未实测标 `未验证`）
- [ ] `Manifest.xml`：底层依赖 + 本模块被引用的两种方式
- [ ] `example/`（或资产型的"一条命令"）：**真的跑过/编过**，把命令写进 README
- [ ] 版本号 + 变更记录（模块内 README 顶部一段）

---

## 6. 与 MCP 知识库的分工

- **知识库（knowledge/）**：讲清"为什么/怎么判/坑在哪"——可检索，写给 AI 与工程师；
- **组件（components/，随 MCP 一起发布）**：给出"可直接调的代码/资产"——能给业务/AI 直接用。
- 两者互链：知识库文档里指向对应组件相对路径（如 `components/fonts/`），组件 README 里反向引用经验来源。

> ⚠️ 定位（沛哥 2026-09-13 明确）：**底层过程不入库**。例如蓝牙/射频模组的 bring-up 与上电时序，
> 用户与 AI 只需要"上层概念 + 直接用组件"，不再让任何人去跑那套排查流程；
> 因此这类文档已从知识库删除，实现细节只保留在组件自带文档（`components/ble/`）里供维护者查阅。

## 7. 组件实测速查：`blur`（高斯模糊 铺底/封面背景）

**能力**：拿一张 4 字节/像素（BGRA）位图 -> 出一张模糊图。专治「音乐播放器封面高斯模糊铺底」这类
需求：**切歌时算一次**，平时只显示那张图，不逐帧重算。包底固定、可调强度、可定点压暗保文字可读。

**API 摘要**（唯一对外头 `components/blur/include/zk/zk_blur.h`，纯 C ABI，无第三方包依赖）：

| 函数 | 作用 |
|---|---|
| `zk_blur_opts_default(o)` | 推荐默认：AUTO / down=4 / upBack=1 / passes=3 |
| `zk_blur_bgra(src,w,h,srcStride,radius,dst,dstStride,o)` | 同尺寸模糊 |
| `zk_blur_prep(src,w,h,srcStride,radius,dst,dw,dh,dstStride,o,outW,outH)` | **铺底专用**：cover 裁切 -> 缩放 ->（可降采样）模糊 ->（可回大）；`outW/outH` 回真实尺寸 |
| `zk_blur_darken(buf,w,h,stride,factor256)` | 定点压暗（铺底可读性；256 = 不变） |
| `zk_blur_mode_recommended()` / `zk_blur_mode_active(m)` / `zk_blur_mode_name(m)` / `zk_blur_has_rvv()` | 档位探测（RVV 不可用自动退回 BOX3） |
| `zk_blur_set_log(fn)` / `zk_blur_bench_once(...)` | 日志钩子 / 单档计时+误差（bench 用） |

**实测性能（真机 F133 / C906，标量构建；1 次 = 全链路，同名次跑 N 次取 min）**：

| 场景 | 参数 | 耗时 |
|---|---|---|
| 1280x800 铺底、**输出 320x200 缩图**（显示层拉伸，推荐） | BOX3 r=8 down=1 | **88 ms**（RVV 71 ms） |
| 同上，真实播放器形态（640x640 封面 -> 320x200） | BOX3 r=8 | 88 ms（RVV 71） |
| 铺底输出就直接是 1280x800 全尺寸 | BOX3 r=32 down=4 + 放大回 | 447~516 ms |
| 只要极快（160x100 铺底） | BOX3 r=32 down=8 | 54 ms |
| **整链路（真实播放页，不落盘）** | 解码 37~57 + 模糊 59~88 + 组装 0 + 上控件 0~1 | **105~141 ms**（对照 PNG 落盘版 395 ms） |

**已知限制（选型前必看）**：

1. **RVV 档要整工程开关**：`-march=rv64gcv0p7` 是**整工程级**的（Xuantie GCC 10.4 不支持单文件
   `__attribute__((target(...)))`）→ 不想改全工程指令集就用标量档（BOX3）；`zk_blur_has_rvv()/mode_active()`
   可在运行时确认实际生效档。RVV 实测提速只有 +11~19%（三趟盒式的**横趟有像素间依赖**、滑窗串行，只能标量）。
2. **`SEP_FIXED`（定点核 + 256 项乘积查表）在本平台反而最慢**：核表 65 taps x 256 x 2B = **33 KB，
   L1 装不下**，每米像素都在打内存 -> 1280x800 实测 **40539 ms**（比 float 档还慢 3.4 倍）。**不要用**。
3. 只吃 **4 字节/像素 BGRA**（与 `screencap`/`image_load` 字节序一致）；3 字节源请调用方先补 alpha。
4. 纯计算、可重入、无全局状态；**别在 UI 线程调大图**（几十~几百 ms），放工作线程（如工程内 `TaskRunner`）。
5. `radius <= 128`；`down ∈ {1,2,4,8}`（>8 收益见顶）；`threads` 字段保留未实现（C906 单核）。

---

## 相关

- `components/ble/`（BLE 门面 `zk::ble`：上层直接调；上电/预初始化/线程/TLV 全在组件内部）
- `components/blur/`（高斯模糊 `zk::`：把 4 字节位图变模糊图；铺底/封面背景；档位与实测见 §7）
- `components/fonts/`（思源黑体三版 + 设备字体自检）
- `components/icons/`（Tabler 图标库：语义图标 → 任意分辨率单色 PNG，两条命令出图）
- `components/ui_v1/`（**框架基线目录，文档型**：当前这代 FlyThings IDE + easyui 的跨框架**控件映射唯一权威表** + 逻辑映射 + 缺口五级处置 + 候选组件登记；**跨框架控件映射查这里**）
- `devflow/custom-font-config.md`（字库机制 + 设备字体自检使用口径）
- `devflow/upgrade-pack-image.md`（固化出包与刷机；⚠️ 会整体替换 `/res`）

---

## 8. `components/vinyl/` —— 黑胶/任意角度旋转（`zk::VinylSpin`，2026-09-22 入库）

- **问题**：平台没有"任意角度旋转位图"的现成能力（`ZKPainter` 不画位图、`misc::bitmap_rotate` 只支持 90° 整数倍、
  `ZKImageAnim` 只吃 GIF/WebP）。要转的圆图（唱片/表盘）只能自己逐帧算。
- **口径**：逐帧把封面旋转画进一张 BGRA 内存位图 → `setBackgroundBmp`（**只交一次**）→
  每帧 `setInvalid(!isInvalid())` 翻转刷新；角度按**墙钟**算（`角度 = spinMs × 24°/s`），
  暂停不累加、丢帧不漂移；解码与旋转都在组件自带的单线程队列上（UI 线程只做拷贝 + 翻转）。
- **双后端**（运行期可切，nanovg 建不起来自动回退定点）：
  | 后端 | 每帧（320×320） | 圆边过渡 | 说明 |
  |---|---|---|---|
  | 定点标量（默认） | **6~12ms** | ~1.5px | Q16 反向映射 + 2x2 盒平均 + SS=8 覆盖率表；**纯整数、无浮点** |
  | nanovg(AGG) | 23~44ms | ~1.0px | `nvgCreateAGG` 直接渲染到我方位图（**只支持 BGRA 目标**）；更顺滑 |
- **实测结论（提速）**：`NVG_IMAGE_NEAREST`、去 memset、把 rotate 换成 `nvgImagePattern` 的 angle **都省不下来**；
  只有**降分辨率**（160×160 ≈ 5.4ms）或**降帧率**有效。
- **顺带定的一条平台口径**：自定义 view 每帧刷新的正确写法是 `ctrl->setInvalid(!ctrl->isInvalid())`
  （gameview 口径）；`invalidate(&getAbsolutePosition())` 传绝对矩形会被按**控件本地坐标**裁成"右下角一块"，
  屏上只刷一块 → 详见 `uicontrols/custom-view-refresh.md`。
- **文件**：`components/vinyl/{README.md,platforms.md,Manifest.xml,include/zk/zk_vinyl.h,src/*,example/}`；
  落地来源 `projects/iOSStyle-F133`（已切到组件副本，`fun build` 0 error + 真机跑通）。
