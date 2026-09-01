# 🏷️ 电子价签 ESL 方案（通用技术参考）

> 来源：内部电子价签项目代码学习（2026-09）
> 一句话：**一套代码跑多个 ARM 平台的价签固件**，HTML 内容渲染上屏 + BLE 配网 + 云端推送内容。
> ⚠️ 本文只收录通用技术方法；云平台协议、私有包细节、客户定制等涉密内容不在此列。

## 1. 多平台一套代码的 Manifest.xml 设计方法

### 1.1 结构：主平台 + enableOnPlatforms 分组依赖

```xml
<manifest cyclicDependency="true" platform="Z20">

  <!-- 按平台启用的框架配置（如某平台关闭 easyui 图形栈，走自绘/HTML 渲染） -->
  <easyui enableOnPlatforms="Z20">
    <gfxEnable type="boolean" value="false" />
    <dispBufferEnable type="boolean" value="false" />
  </easyui>

  <dependencies enableOnPlatforms="Z20">
    <package id="easyui" version="3.0.0" />
    <package id="html-builder" version="^5.0.0" />
    <package id="networking" version="^5.0.0" />
    <package id="frpc" version="^5.0.0" />
    <package id="mqtt-cxx" version="3.1.0" />
    <package id="paho-mqtt3a" version="1.3.13" />
    <package id="ntp" version="1.0.1" />
    <package id="watchdog" version="0.0.3" />
    <package id="ini" version="0.0.1" />
    <!-- 私有包：带 accessKey 才能拉取（key 向中科世为申请） -->
    <package id="xxx" version="^12.0.0" accessKey="..." />
  </dependencies>

  <dependencies enableOnPlatforms="T113EMMC">
    <package id="easyui" version="0.0.0-240311" />
    <package id="frpc" version="^4.0.0" />
    <package id="rabbitmq-c" version="0.14.0" />      <!-- 另一平台用 AMQP -->
    <package id="mqtt-cxx" version="^2.0.3" />
    <package id="animations" version="^7.0.0" />
    <package id="xxx" version="^11.0.0" accessKey="..." />
  </dependencies>
</manifest>
```

### 1.2 要点

- **`platform="Z20"`** 声明主平台；**`enableOnPlatforms`** 让同一 Manifest 按平台选依赖组，编译时只解析对应组
- **同名包不同版本**：同一业务包在不同平台版本可能不同步（如 ^12.0.0 vs ^11.0.0、mqtt 3.x vs 2.x），**切平台时同步核对版本**
- **`cyclicDependency="true"`**：允许循环依赖（业务包依赖 easyui，easyui 又反向引用时）
- **`<package accessKey="...">`**：私有包鉴权，key 申请制；`.deps.lock` 记录解析后的版本与依赖树（如 xxx 12.0.3 → easyui>=3.0.0 + webview ^10.0.0 + html-builder ^5.0.0）
- **easyui 按平台关渲染**：部分平台不用 easyui 图形栈（gfxEnable/dispBufferEnable=false），内容由 webview/自绘直接输出，省内存提帧率

### 1.3 代码层平台分支（#ifdef 宏）

编译期宏：`__PLATFORM_Z20__` / `__PLATFORM_T113EMMC__`（IDE 自动注入，无需手动定义）。典型差异点：

| 差异点 | 平台 A | 平台 B |
|--------|--------|--------|
| 内核模块 insmod 路径 | `/lib/modules/4.9.84/...` | `/lib/modules/5.4.61/...` |
| BLE 广播名前缀 | `tag-<id>` | `XM<id>` |
| HTML 渲染层 | 独立 RenderView（newView 创建，性能好） | 直接渲染到 ZKWindow |
| USB/SD 产测挂载点 | `/mnt/usb1` | `/mnt/extsd` |
| 消息队列 | paho MQTT | rabbitmq AMQP |
| 视频 | — | 需 `setenv("ZKMEDIA_VIDEO_HOLDFRAME","1")` |
| 升级包 | 普通 update.img | 必须合并 boot.img（见下） |

运行时还可探测芯片型号：`sysinfo()` 看总内存 <64MB 视为低配（SSD201），性能不足时拒绝承担主设备角色。

## 2. HTML 内容渲染体系（html-builder / webview）

### 2.1 链路

```
云端下发内容(JSON 包裹 HTML) → 消息回调
  → makeCronParams(存储目录, html) 解析出 Cron 轮播表（定时/轮播/多页面）
  → render_service_.start(RenderParams) → webview 渲染上屏
```

关键 API（私有业务包封装，头文件 `<xxx/...>`，此处为通用模式）：

```cpp
RenderParams param;
param.html = html;                          // HTML 内容
param.view = render_view_.get();            // 独立渲染层（性能好）；否则传 ZKWindow
param.progressing = ...;                    // 加载进度回调
param.video_views.push_back(video_view);    // HTML 内 <video> 绑定 ZKVideoView
param.storage_registry = storage_registry;  // 资源缓存注册表
param.client_x/y = window 坐标; param.client_w/h = 屏宽高;
param.retries = 30;                         // 资源拉取重试
param.load_only = true;                     // 只预加载资源不渲染
param.render_only = true;                   // 只渲染成图片不显示（代渲染场景）
param.imageStyle = ...; param.quality = 60; // 输出 JPG 参数
```

### 2.2 通用设计要点（可复用经验）

- **Cron 轮播**：HTML 内容解析成 `std::vector<Cron>`，每个 Cron 有生效时间段 + 内容（getHtml()/getCarouselInfo()），到点切内容
- **StorageRegistry**：管理 HTML 内引用的图片/视频等资源下载与缓存，`exists()/path()/cleanTo(字节数)`（升级前 cleanTo 腾空间）
- **断电恢复**：内容原文存 `<存储目录>/origin`，开机先恢复上屏，再后台拉新配置
- **未绑定页**：用 `html::Document` 命令式生成 HTML（img/text/qrcode 元素 + layout/color/textAlign/fontSize），内容含设备 SN 二维码 + BLE 广播名提示
- **代渲染图片**：低端 MCU 屏设备没有渲染能力时，主设备把 HTML `render_only` 渲染成 JPG（内容 md5 命名），经本机 HTTP 服务供 MCU 拉取显示
- **内存**：渲染大内容前 `malloc_trim(0)`；定时器监控 RSS，超阈值写 `/proc/sys/vm/drop_caches=3` + malloc_trim

## 3. BLE 使用（自研 BlueZ GATT Server 思路）

> 不用平台自带 BLE 封装，直接集成 BlueZ gatt-server 静态库，自己写 L2CAP/ATT/HCI 层。

### 3.1 架构

```
startBluetooth()
  ├─ insmod 蓝牙驱动模块（aic_btusb.ko，按平台内核版本路径）+ hciconfig hci0 up
  ├─ bt_gatt_impl_start(cb) → 独立线程跑 mainloop
  │    ├─ socket(PF_BLUETOOTH, SOCK_SEQPACKET, BTPROTO_L2CAP) 绑 ATT_CID=4 监听
  │    ├─ mainloop 等 accept → bt_att_new → bt_gatt_server_new(mtu=517)
  │    └─ 断连回调里重新开广播
  └─ on_start(db) 里 gatt_db_add_service 建服务
```

- **驱动**：aic_btusb.ko（AIROHA 蓝牙芯片），内核版本按平台不同，insmod 失败静默
- **广播**：`hci_send_req` 发 `OGF_LE_CTL` 广播参数/使能命令；`hci_send_cmd` 发 `HCI_LE_Set_Advertising_Data`（ogf=0x08, ocf=0x0008），**手工拼 advdata 把设备名塞进广播包**（flag + local name 结构），App 扫广播即可识别设备
- **GATT 服务**：服务 UUID `0xfff0`；特征 `0xfff1`（可读可写+NOTIFY+CCCD 描述符）、`0xfff2`（只写）。写入回调 → handler 异步收包
- **粘包**：收包累积 + `send_unique_message_delayed(END, 200ms)` 200ms 无新数据才派发；累计超 4096 立即派发
- **收包格式**（两套兼容）：
  - 专用协议：以固定前缀开头（如 `+SET-DEVICE:`）+ JSON，key 驱动对应动作
  - 通用协议：`key=value` 按 `\r\n` 分行解析
- **配网**：BLE 收 wifi（`ssid:passwd` 或 JSON）→ WIFIConnecter 切 WiFi → 成功后持久化

### 3.2 生命周期建议（省电 + 抗干扰）

- BLE 服务只在 WiFi 开启时运行（循环检查，WiFi 断开→停 BLE）；开机先禁 WiFi 跑 BLE 等配网，配网成功后延迟启动 WiFi
- 绑定/配网完成后定时自动关 BLE（如 15 分钟），需要时再开
- BLE 广播名 = 设备标识（平台前缀 + id 尾段），未绑定页面显示名字引导用户连接

## 4. 其他工程要点（通用）

- **OTA 升级**：Updater 单例（lock 防并发），prepare 下载校验（url+md5+file_size）→ boot logo 特判单独升级（双屏按 ScreenWidth>=1600 生成双屏 logo）→ start 写升级包；T113 升级前先清理缓存腾空间
- **T113 整包**：发布脚本 `imgmerge.exe os\boot.img <update> update.img` 把内核和应用合并成整包（Z20 直接出 update.img）
- **产测**：U 盘/SD 根目录放 `product_test.ini` → 挂载事件拉起 TestActivity（wifi/screen/mount/manual 等测试项）
- **看门狗**：重启前 `os::watchdogStart(10)` 先喂狗防卡死；系统状态属性 `sys.zkapp.state`
- **开机防呆**：`appBootCount() >= 10`（release）→ 判定资源异常清空存储重启；从设备 WiFi 启动延迟错峰
- **版本号**：version.h 统一 APP_MAJOR/MINOR/PATCH，`appVersinString()` 上报
- **i18n**：LANGUAGEMANAGER->getValue() 多语言文案（en_US / zh_CN），云端可下发语言切换指令 updateLocalesCode

## 5. 可复用经验（写代码时参考）

1. 多平台工程：Manifest `enableOnPlatforms` 分组依赖 + 代码 `#ifdef __PLATFORM_XXX__` + 构建后脚本差异，三件套缺一不可
2. 私有包：`accessKey` 属性即可拉取，包内可依赖其它私有/公开包；跨平台私有包版本可能不同步
3. BLE 配网产品策略：WiFi 可用则关 BLE；绑定成功定时关 BLE；广播名 = 设备标识方便 App 识别
4. HTML 内容渲染要配 StorageRegistry 缓存 + 断电恢复（origin 快照）+ 预加载，否则弱网体验差
5. 主从设备间转发用 RPC+压缩比直接透传可靠，且能统一回执
