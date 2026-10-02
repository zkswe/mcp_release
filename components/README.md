# components —— 可复用模块目录（规范）

> 这里放**能被业务直接调用**的模块代码。以前散在专题文章、聊天记录、各工程里的"这么做就对了"，
> 从今天起沉淀到这里：**一个模块一个目录，四件套齐全，拿去就能编、能跑、能查**。
> 建立日期：2026-09-13（定：落地形态 = 参考代码目录下的 components 模块）

---

## 1. 目录与四件套（硬要求）

```
components/
└─ <模块名>/                     ← 小写中划线/单词，如 ble、ota、modbus
   ├─ README.md                  ← ① 落地 README：是什么 / 怎么用 / API / 依赖 / 限制 / 排错
   ├─ platforms.md               ← ② 平台说明：哪些平台可用、每平台前置条件与实测值、已知限制
   ├─ Manifest.xml               ← ③ package 引用：需要哪些底层包、怎么声明；外部怎么引用本模块
   ├─ include/                   ← ④ 头文件（唯一对外面）
   ├─ src/                       ←实现
   └─ example/                   ←可直接调用的最小示例（能拷进工程就跑）
```

**四件套缺一不收**：没有 `platforms.md` 的模块，等于把"什么板子上会翻车"藏起来了；
没有 `example/` 的模块，等于让下一个人从零猜调用姿势。

**两种模块形态**（都算合格）：
- **源码型**（默认）：`include/ + src/ + example/`，对外命名空间 `zk::<模块>`；
- **二进制型**（源码不外发时用）：`include/ + lib/<平台>/ + lib/BUILD_INFO.md + example/`，
对外仍只是 `include/zk/zk_<模块>.h`；**源码私有维护**，但必须给“构建凭据”（每个平台库用什么工具链/
依赖版本构建、符号数、sha256），并提供**机器可跑的符号自检脚本**（对照头文件里的公开 API）。
取库时按目标平台取，**不许拿别的平台的头凑**（ABI 不一致会埋雷）；工具链/libc 必须在 BUILD_INFO 里写清。
- **资产/工具型**（如 `fonts/`）：无 `include/src`，四件套对应为 `README.md + platforms.md + scripts/（可复现的生成/检查脚本）+ 产物目录（字体/资源）`，
使用方式写成"一条命令"（体检/投递/生成），不要求调用方写代码。

---

## 2. 代码规范（review 尺子）

1. **不允许把底层库的类型泄漏到对外头文件**。例：BLE 模块对外只有 `std::string`，
没有 `bd_addr_t` / `hci_con_handle_t`。想用底层的，自己 include 底层头，别逼所有人一起。
2. **统一结果类型**：`Result{code, msg}`（或等价的错误结构）。`msg` 必须是**人话**，
能直接打日志/回给用户；禁止只返回 `-1`，禁止静默失败。
3. **默认参数要安全**：不传参也能跑；有超时；写操作默认"要回应"。
4. **阻塞/线程模型写进 README**：哪些回调在库线程里被调、业务能做什么不能做什么；
跨线程一律走库内封装，不要求业务理解底层 run loop。
5. **平台差异关在内部**：`#ifdef`/平台分支只允许出现在平台适配层，业务层代码里不出现平台名。
6. **可诊断 > 可配置**：能自动探测的不做成配置项；探不到就明确报错并给出"下一步查什么"。
7. **资源路径/节点路径一律给候选链**（不同板子内核枚举不同，写死必翻车）。

---

## 3. package 引用（怎么让工程用上）

**A) 源码引入（推荐起步，改动最快）**

把 `components/<模块名>/` 整目录拷进工程 `src/` 下（或作为子目录加进构建），
并在工程 `Manifest.xml` 里声明该模块所需的底层包（见模块自己的 `Manifest.xml`）。

**B) 依赖包引用（模块定型后）**

模块按平台编译出 `include/` + `lib/`，注册进包仓库，工程里一行：
```xml
<package id="<模块名>" version="x.y.z"></package>
```
版本号**写死**，不用 `^` 浮动（底层 ABI 一变，编出来的东西就不可复现）。

---

## 4. 平台说明怎么写（platforms.md 模板）

每个平台一段，必须包含：可用性（可用/部分可用/不支持）、**前置条件**（电源/串口/固件/属性门）、
实测值（节点路径、波特率、校验、超时）、已知限制、真机验收命令。
禁止写"应该可以"这类话；没实测的标 `未验证`。

---

## 5. 新增模块 checklist

- [ ] 目录名/命名空间定好（对外命名空间 `zk::<模块>`，头文件 `include/zk/zk_<模块>.h`）
- [ ] `README.md`：用法（含一段 10~30 行可跑的代码）+ API 表 + 依赖 + 限制 + 排错
- [ ] `platforms.md`：逐平台写清前置条件与实测值
- [ ] `Manifest.xml`：底层依赖 + 本模块被引用的两种方式
- [ ] `example/`：最小可跑示例，且**真的编译过**（把编译命令写进 README）
- [ ] 版本号 + 变更记录（模块内 README 顶部一段即可）

---

## 6. 现有模块

| 模块 | 说明 | 平台 | 版本 |
|---|---|---|---|
| [`ble/`](ble/README.md) | BLE 门面 `zk::ble`：把蓝牙收拾成 wxapi 那种（**一个 API 面、两个后端**：中心扫描/连接/GATT + 外设广播/GATT 服务/notify）。**二进制型**：只发头 + `lib/<平台>/libzkble.a`（源码私有） | 中心：f133、v85x（btstack）；双角色：z20、z21（gatt，真机跑通）；t113/t113emmc 待补库 | 0.2.1 |
| [`blur/`](blur/README.md) | 高斯模糊（铺底/封面背景）`zk::`：拖一张 4 字节 BGRA 位图进，出一张模糊图（**切歌时算一次**，不逐帧重算）。**源码型**（无第三方包依赖）；档位 AUTO/BOX3/SEP_FLOAT/SEP_FIXED/RVV，带 `prep`（cover 裁切+缩放+模糊+可回大）/`darken`/`bench_once`。真机 F133：1280x800 铺底输出 320x200 缩图 **59~88 ms**（RVV 71 / 标量 88），整链路（解码+模糊+上控件不落盘）**105~141 ms**| F133 已实测（标量 + RVV）；Z20/Z21/T113/V85X 未验证；PC 仅自测 | 0.1.0 |
| [`vinyl/`](vinyl/README.md) | 黑胶/任意角度旋转 `zk::VinylSpin`：把封面按角度逐帧旋转（内存位图 → `setBackgroundBmp`，不落盘），**墙钟定角度**（丢帧不漂移）+ 后台队列 + 双缓冲；**双后端**：定点标量（纯整数 Q16，无浮点，6~12ms/帧，边缘过渡 ~1.5px）/ nanovg(AGG)（更顺滑 ~1.0px，23~44ms/帧，建不起来自动回退）；含正圆覆盖率表（SS=8 面积平均，与静态圆封面同源）。**源码型**（easyui + log；nanovg 可选） | F133 已实测（双后端）；其余平台未验证 | 1.0 |
| [`fonts/`](fonts/README.md) | 字库模块（资产型）：思源黑体三版（常用中文872KB/全中文7.4MB/多国语言10.5MB）+ 设备字体自检（缺中文自动投递） | 全平台（已在 V85X 实测） | 0.1.0 |
| [`icons/`](icons/README.md) | 图标模块（资产型）：收录 **Tabler Icons 3.46.0（MIT）152 个语义图标**（天气 30/开关选项 26/系统 66/智能家居 23/两轮车 7，含 7 条 compose 组合）+ 自绘两轮车仪表 5 个；手写 SVG 与 vendor SVG → 一条命令生成任意分辨率单色 PNG（严格 N×N，支持 `--size WxH`、`--vendor-name`、`--svg`、两态自动配对；自带生成清单+质检） | 全平台（纯 PNG 资源） | 0.2.0 |
| [`imagecache/`](imagecache/README.md) | 列表封面「已解码位图」缓存 `zk::ImageCache`：按**路径**缓存已解码位图（权重 LRU + 引用计数 + 锁 + 容量参数 + `hits()/loads()` 读数），治 listview 刷新/回页重设封面**反复解码**（真机 F133 回页重设同一批 **315 ms → 1 ms**）。**源码型，核心零依赖**（装载/释放回调注入，PC 可编）；带 FlyThings 接线样板与 PC 自测 29 项（含「固定名封面 → 串图」复现） | F133 已实测（经工程内联基线；组件形态待真机回归）；其余平台未验证 · PC 已自测 | 0.1.0 |
| [`mp_transfer/`](mp_transfer/README.md) | 小程序传图/视频（**设备端接收参考实现**）：UDP 广播被发现（`255.255.255.255:8899`，`zkswe:<设备名>`）→ TCP 9000 收文件（34 B 公共包头 / 32 KiB 分块 ACK / 末块 `OK\n` / `.tmp`→rename 落盘）→ 回调通知；含 `runtime_coordinator` 起停协调与 **PC 端 Python 参考接收端**（纯标准库，可先不接设备验链路）。**源码型**（依赖 `base::Task`，移植时换项目自己的后台线程/日志） | 来源工程（F133 相册）现场验证 · **本仓组件形态未上机**· 其余平台未验证 | —（2026-09-24 入库；四件套 = README + platforms.md + src/ + example/，另含 `docs/` 对接指南全文） |
| [`album_upload/`](album_upload/README.md) | 相册传图（手机→面板）**业务接线层**`zk::album`：配置 / 生命周期（`start/stop` 引用计数）/ 回调归一化 / **二维码 URL 现场生成 + 本机地址兜底**（`ZKQrcode::loadQRCode(qrInfo().content)`，不铺位图）/ 计数读数；**协议与落盘引用 `components/mp_transfer/`（不复制一行）**；附扫码 URL（`assets/qr_url.txt`）+ 从码图解链接的离线脚本。**源码型**（本体只用 libc/POSIX；接线侧 easyui + log） | 来源工程 Z20 真机跑通（微信扫码传图）· **本仓组件形态未上机**| 0.1.0 |
| [`wall_sync/`](wall_sync/README.md) | 多屏拼接 / 视频墙同步 `zk::wall`：`Sync`（UDP 自组网 + 主机 epoch + 从机双向测时 RTT/2 算钟差 + 绝对墙钟整边界栅格 + `playlist.json` 多 clip 时间轴 + 失联/时钟守卫）+ `Player`（按栅格挑本机那一格、边界踩点起播、交**注入的 `Engine`**送流）；头文件零 MI/ffmpeg 类型泄漏。**源码型**（rapidjson + base-utility；接线侧 easyui/ffmpeg/mi-module） | Z20 已实测（口径来自来源工程内联版：相位 ≤40ms、simple 引擎稳态偏差 ≤1ms）；其余平台未验证 · **本仓组件形态未上机**| 0.1.0 |
| [`ha_bridge/`](ha_bridge/README.md) | Home Assistant / MQTT 桥 + 继电器语义 `zk::ha`：`Bridge`（配置全空默认 → 不给就明确报错；上行 availability/state/status retained + 连接后自动发 HA Discovery；下行只认 `<prefix>/switch/relay_<n>/command` 的 ON/OFF；retained 撤销原语；**重连只留一个真源**+ 代次作废旧回调 + 退避）；`RelayBank`（继电器唯一事实源 + 变化才通知，UI 视觉单槽与业务具名槽**互不覆盖**）。头文件零 mqtt-cxx 类型泄漏。**源码型**（mqtt-cxx + paho-mqtt3as + openssl） | Z20 已实测（同源逻辑在来源工程真机跑通）；**本仓组件形态未上机**| 0.1.0 |
| [`ui_v1/`](ui_v1/README.md) | **本代 UI 目录（口径 2026-09-16 修正）：只放「FlyThings 没有的能力」的自定义控件包**（`ui_v1/<源控件名>/`，四件套 + `example/evidence`）。已落 **`Chart/`**（折线/柱/环/仪表自绘集合 + 分段环，Z21 真机验收）、**`Calendar/`**（42-textview 日历网格 + 触摸反算命中，Z21 真机验收）与 **`RadButton/`**（painter 自绘带倒角按钮：任意尺寸/半径/四态/边框 + 抗锯齿数字，Z21 真机验收）；**有一一映射的控件走「映射能力」**（`mcp_control_map.json` + op `flythings_map_control`，六框架 212 条）；有平台对应控件但接线值得留的叫**映射参考**（`ui_v1/_mapping/TabView/`，基于 pagewindow）；级别/缺口/平台事实在 `control-map.md`/`gap-list.md`/`platforms.md` | Z21 已验收 · F133 仅编译 · Z20/T113/V85X 未验证 | 0.4.0（含 `Chart` 0.2.0 / `Calendar` 0.1.0 / `_mapping/TabView` 0.1.0） |
| [`blend2d/`](blend2d/README.md) | 离屏矢量出图 `zk::b2d`：圆角/阴影/渐变/OpenType 文本 → 导出位图给 `setBackgroundBmp`（**不是 2D 加速器**）；两档库 = 原厂默认 + 自编 NEON 性能档（真机 480×480 双线程+阴影减层 5.17ms）| Z20 已验（z21/t113emmc 未验；v85x/t113-musl、f13x 不可用） | 0.1.0 |

---

> **相关（不属本目录四件套体系）**：界面块片段库 + 组装器 → [`templates/ui_blocks/`](../templates/ui_blocks/README.md)
> ——把 UI 从「手算坐标」变成「选块 + 填值 + 排序」：`python templates/ui_blocks/compose.py spec.json --project <工程> --render --check`（11 个块，出 json + 切图 + 渲染图 + 全检）。
