# album_upload —— 相册传图（手机 → 面板）业务接线层 `zk::album`

> 版本 **0.1.0**（2026-09-30 入库）· 类型：**源码型**（`include/ + src/ + assets/ + scripts/ + example/`）
> 一句话：**面板上出二维码 → 手机微信扫 → 同局域网把照片/视频传进面板 → 落盘 → 通知业务**，
> 这一整套**业务口径**收成一个 API 面；**传输本体不在这里**（`components/mp_transfer/`，本组件引用它）。
> 来源工程：`projects/SmartPanel_HA` 的「相册上传」子页（album.ftu / albumLogic.cc / albumfileLogic.cc）。

## 1. 是什么 / 不是什么

**是**：
- **配置面**：落盘目录、设备名（小程序里看到的名字）、监听端口、二维码内容来源（全部配置项，**不写死**）；
- **生命周期面**：`start()/stop()` 一句起停（内部 = mp_transfer 的 `retain/release` 引用计数，多页共用安全）；
- **回调面**：上传完成 `onFileAdded` / 手机连接状态 `onStateChanged`（归一化过，不外泄底层类型）；
- **二维码面**：`qrInfo()` 给出**要喂给控件的链接**（一条路 + 一个兜底：配置 URL / 本机上传地址）；
- **读数面**：`stats()`（图片/视频计数）、`peerConnected()`（呼吸灯 vs 帧动画）、`lastError()`（人话）。

**不是**：
- ❌ 不实现协议：UDP 8899 广播、TCP 9000、32 KiB 分块 ACK、`.tmp`→rename 落盘全在 `components/mp_transfer/`；
- ❌ 不解析媒体：**只收不解析**（不读 JPG/MP4 头，不给宽高/时长 —— 底部 `TransferFileInfo` 里有字段但本组件不填）；
- ❌ 不做 UI：二维码控件、白卡、呼吸灯、文件网格都是你的页面（接线样板见 `example/flythings_wiring.cc`）；
- ❌ **不下载任何图片、不铺二维码位图**（口径 2026-09-30：二维码只用 URL 现场生成，见 `assets/README.md`）；
- ❌ 不管网络/存储策略：本机 IP 由你注入（`setLocalIpProvider`）；
- ❌ 不认 prefs：本组件不认识 `StoragePreferences`，配置由你从自己的 prefs 读出来后灌进 `Config`。

**分工（移植时对号入座）**

| 层 | 谁 | 干什么 |
|---|---|---|
| 协议/网络/落盘 | `components/mp_transfer/` | UDP 8899 广播 `zkswe:<设备名>`；TCP 9000 收文件；分块 ACK；`.tmp`→校验→rename |
| 业务接线 | **本组件 `zk::album`** | 配置、生命周期、回调归一化、二维码内容（URL）、计数 |
| 工程 | 你的项目 | 读写 prefs、UI 显示二维码（`loadQRCode(qrInfo().content)`）、收到文件后刷列表/入轮播 |

## 2. 怎么用（最小可跑，15 行）

```cpp
#include "zk/zk_album.h"                       // 唯一对外头

zk::album::Uploader &up = zk::album::Uploader::instance();
up.setLogHook(myLog, 0);                       // app 模式下 stdout 是 /dev/null，日志必须接出去
up.setOnFileAdded(myOnFileAdded, 0);           // ⚠️ 在接收线程里被调：只置标志，别动控件
up.setOnStateChanged(myOnState, 0);
up.setLocalIpProvider(myLocalIp, 0);           // 兜底二维码拼 http://<ip>:9000/upload 用

zk::album::Config cfg;                         // 默认值安全（save_dir=/mnt/sdnand/album/）
cfg.save_dir    = "/mnt/sdnand/album/";        // ⚠️ 末尾带 '/'，且与 mp_transfer 的 MP_PATH 一致
cfg.device_name = "我的相框";                   // 小程序里看到的名字（空 → Frame）
up.configure(cfg);                             // 内部会 start()（start_on_configure=true）

up.setQrUrl(myPrefsQrUrl());                   // 二维码内容：从你自己的 prefs 读（空 → 兜底本机上传地址）
up.refresh();                                  // 进页扫一遍：stats() 拿到图片/视频数
zk::album::QrInfo qr = up.qrInfo();            // 一条路 + 一个兜底：见 assets/README.md
// UI 线程：mQrcodePtr->loadQRCode(qr.content.c_str())   ← 内容变了才重算（QR 生成很贵）
```

页面销毁时**两句必做**（真机踩出来的，见 §6 坑 1）：

```cpp
sQrShown.clear();                       // ⚠️ 你自己"已 load 的内容"缓存，与控件同生共死
zk::album::Uploader::instance().stop(); // 离开页面停传输（省电；小程序侧会显示设备不可见）
```

完整接线（prefs 读配置 + 定时器刷新 + 模式开关）见 `example/flythings_wiring.cc`；
端到端生命周期见 `example/album_upload_example.cc`。**跑起来还要三步**（拷 mp_transfer + 拷本组件 + 声明依赖），
命令与判据见 `example/README.md`。

## 3. 对外 API（头文件：`include/zk/zk_album.h`）

| API | 作用 |
|---|---|
| `Uploader::instance()` | 单例（一个进程一份配置/一份回调） |
| `configure(const Config&) -> Result` | 校验并落配置（目录不存在按需创建、不可写直接报错）；默认自动 `start()` |
| `config()` | 取当前配置 |
| `start() / stop() / running()` | 起/停接收（内部 `retain/release`，幂等；`start` 返回成功 ≠ 已 listen，见 §5） |
| `peerConnected()` | 手机是否连上（正在收文件） |
| `setOnFileAdded(fn,user)` | 上传完成回调（**接收线程**；`FileInfo{path,name,size,mtime,kind}`） |
| `setOnStateChanged(fn,user)` | 手机连上/断开（**接收线程**） |
| `setLogHook(fn,user)` / `setLocalIpProvider(fn,user)` | 日志钩子 / 本机 IP 来源 |
| `refresh() / stats() / lastError()` | 重扫落盘目录 / `{photos,videos}` / 最近一次错误（人话） |
| `qrInfo()` | 二维码内容（`QrMode` + `content`（**永远非空**）+ `local_url`） |
| `setQrUrl(url)` | 运行时改二维码内容（如设置页改完立刻生效；**空串 → 退回本机地址兜底**） |
| `localUploadUrl()` | `http://<ip>:<端口>/upload`（`QR_LOCAL_UPLOAD_FALLBACK` 的内容，调试/提示用） |

**二维码口径（只有一条路 + 一个兜底）**：`QrMode{QR_FROM_CONFIG, QR_LOCAL_UPLOAD_FALLBACK}` ——
两种 mode 的 UI 处理**完全一样**：`ZKQRCode::loadQRCode(qr.content)`。组件侧**不缓存**二维码内容
（`qrInfo()` 即时计算），也没有任何"下载/失败"状态。

**线程模型（硬约束）**：`setOnFileAdded` / `setOnStateChanged` 在 **mp_transfer 接收线程**里被调 →
只允许置标志 / 记路径 / 入队列；**禁止**在回调里动控件、注册注销、起停服务。
UI（`loadQRCode`）只能在 UI 线程，靠你的定时器消费标志。

**错误口径**：一切可失败操作返回 `Result{code,msg}`，`msg` 是人话（可直接打日志/回给用户），
**不静默失败**；`lastError()` 留最近一次。日志走 `setLogHook`（未设钩子时完全静默，不刷屏）。

## 4. 依赖

- **组件本体**：只用 libc/POSIX（`opendir/stat/mkdir/access`）—— PC 侧可编（见 §7）；
- **传输本体**：`components/mp_transfer/`（必须一起拷进工程；它依赖 `base::Task` = 包 `base-utility`）；
- **接线层**：`easyui`（`ZKQRCode`、`StoragePreferences`、生成代码）、`log`（工程日志宏）。
  **不需要 `curl-cxx`**（二维码现场生成，不下载位图）。
  各平台版本与声明见 `Manifest.xml`（**改完 Manifest 必须重跑 `fun install`**）。

## 5. 限制（写需求时先看）

| 限制 | 说明 |
|---|---|
| 只收不解析 | 不给宽高/时长/缩略图；要元数据自己解（底部 `TransferFileInfo` 留了字段） |
| 同一局域网 | 手机与面板同一网段，且路由器**不能开 AP 隔离/客户端隔离**（否则 UDP 广播到不了） |
| 单文件上限 | 协议 500 MiB；分块固定 32 KiB（改了两端要一起改） |
| 落盘目录 = 编译期 | mp_transfer 的 `MP_PATH` 是编译期宏；`Config::save_dir` 只是组件侧的校验/统计口径，两者必须一致（不一致会给 WARN） |
| 文件名 | UTF-8，1..256 字节；**禁 `..` `/` `\`**；建议唯一名防覆盖（来源工程按时间戳改名 `小程序_YYMMDD_HHMMSS.<ext>`） |
| 端口固定 9000 | 小程序侧写死；改了口收不到文件（组件会给 WARN） |
| 网络能力 | 无认证/加密/CRC/断点续传；TCP 空闲 2 s 超时（不适合保活）；**仅适合可信局域网** |
| 启动 ≠ 就绪 | `start()` 只是 retain（底层 listen 在任务线程做）；用 `peerConnected()`/日志确认 |
| 二维码内容 = 必须配 | 不配（`qr_url` 空）时只能给本机上传地址兜底（联调保底，不是终端用户入口） |

## 6. 排错（都是真机踩过的）

1. **再进页二维码空白，切一下页面才出来** —— 业务侧缓存活得比控件久：二维码内容存在你的 `static std::string`，
   页面销毁时生成代码把控件指针置 NULL，新控件从未 `loadQRCode()`，而缓存比对直接 `return`。
   → 修法：`onUI_quit` 里**清业务侧缓存**（本组件不缓存二维码内容，无需额外清理）。
2. **二维码边缘发糊/扫不动** —— 别铺位图：素材 128px 压 37 模块 = 3.46 px/模块（非整数像素）必然发糊。
   → 组件口径就是**控件现场生成**（`loadQRCode(qrInfo().content)`，模块像素对齐）。
   还扫不动就查两件事：① `content` 是不是你要的链接（`sp_qr_url` 是否为空走了兜底、链接是否被改坏）
   ② 布局有没有给**白边静区**（≈4 模块；来源工程 = 160×160 白卡 + 128 码居中）。
3. **手机扫不到/发现不了设备** —— ① 不同网段/VLAN ② 路由器开了客户端隔离 ③ 相册模式没开（`stop()` 状态下不广播）。
4. **传完了文件不在目录里** —— ① `save_dir` 与 mp_transfer 的 `MP_PATH` 不一致（看 WARN 日志）
   ② TF 卡/分区没挂载（`configure()` 会直接报"落盘目录不可写"）③ 文件名非法被拒（`..` `/` `\`）。
5. **扫码后手机连不上** —— TCP 9000 被占或防火墙；`listen_port` 必须 9000。
6. **app 模式看不到任何日志** —— `setLogHook` 没接（stdout 是 `/dev/null`）。

## 7. 验证状态（别把"能编"当"已验证"）

| 层 | 判据 | 状态 |
|---|---|---|
| 组件本体（`src/zk_album.cpp` + `example/album_upload_example.cc`） | PC 侧语法自检：`-std=c++11 -fsyntax-only -Wall -Wextra`（用桩头模拟 mp_transfer 接口） | ✅ **通过（0 warning）** |
| 解链接脚本（`scripts/decode_qr_url.py`） | 在码图上解出链接；`--expect` 核对通过；`--write` 产物与 `assets/qr_url.txt` **逐字节一致**（375 B） | ✅ **通过**（离线工具，运行时不依赖图片） |
| 工程侧接线（`example/flythings_wiring.cc`） | 工程 `fun build` 通过 + 真机扫码 | ⚠️ **未在目标工程重放**（样板来自来源工程实跑代码，见 `platforms.md`） |
| 真机（微信扫码传图端到端） | 手机扫面板码 → 小程序 → 传图 → 落盘 → 回调 | ⚠️ **本仓无逐条取证**（来源工程口径见 `platforms.md` §0/§1） |

## 8. 移植注意

1. **mp_transfer 先跑通**：本组件只是"接线层"，协议侧的问题去 `components/mp_transfer/platforms.md`；
   没有 `base::Task` 的平台，照它的 README 换成项目自己的后台线程，
   本组件只依赖 `MpTransferRuntimeCoordinator` / `TcpReceiveTask::TcpReceiveListener` / `TransferFileInfo` 三个符号。
2. **落盘目录写两处**：`Config::save_dir` 与 mp_transfer 的 `MP_PATH`（原工程 `config.h` / 移植工程 `mp_config.h`）
   必须一致，末尾都带 `/`。
3. **本机 IP 注入**：`setLocalIpProvider` 传工程自己的取法（如 `NetKeeper_localIp()`）；**不要**指望组件猜网卡
   （来源工程踩过：只读 wlan0 → 走网线时二维码变成 127.0.0.1）。
4. **二维码内容来自配置**：链接（`sp_qr_url` 语义）由你从自己的 prefs 读出来灌进 `setQrUrl()`；
   组件**不带任何默认链接**（`assets/qr_url.txt` 只是给部署方填配置用的示例值，见 `assets/README.md`）。
   AppID（`sp_mp_appid` 语义 → `Config::mp_app_id`）只记录、不参与生成，也一律配置项。
5. **别在多页各持一份配置**：单例 + `owner` 区分持有者；一个页面 `stop()` 只减引用，最后一个释放才真停。

## 9. 来源与相关

- 传输本体：`components/mp_transfer/`（协议/落盘/PC 侧 Python 参考接收端）+ `knowledge/devflow/mp-transfer-miniprogram.md`
- 组件规范：`components/README.md`、`knowledge/devflow/reusable-components.md`（四件套 + 代码尺子）
- 来源工程：`projects/SmartPanel_HA`（`src/logic/albumLogic.cc`、`src/logic/albumfileLogic.cc`、
  `src/mp_transfer/`、`src/storage/ConfigStore.cpp` 的 `sp_qr_url/sp_mp_appid` 键语义）
- 二维码 URL 口径（为什么不用位图 / URL 从哪来）：`assets/README.md`；解链接工具：`scripts/decode_qr_url.py`

检索词：相册传图 / 扫码传图 / 小程序传图 / 二维码现场生成 / 二维码 URL / zk_album / album_upload /
面板接收手机照片 / 落盘目录 / 上传完成回调 / loadQRCode / sp_qr_url
