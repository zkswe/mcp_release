# T113 平台组件包清单

**来源：** https://package.flythings.cn/t113
**API：** https://package.flythings.cn/api/platforms/t113/packages
**更新日期：** 2026-05-31

## 全部 41 个包

| 包名 | 版本 | 说明 |
|------|------|------|
| Poco | 1.9.4 | Poco C++ Library |
| av | 1.0.5 | 使用FFMPEG读取音视频 (依赖 base-utility) |
| awh264player | 1.1.0 | 播放h264流 |
| base-json | 3.0.3 | 构造JSON与解析JSON |
| base-utility | 10.8.6 | 基础通用功能 |
| boost | 1.58.1 | Boost Library |
| cares | 1.17.2 | c-ares DNS resolver |
| cdx | 0.0.0 | — |
| civetweb | 1.16.0 | HTTP服务端 |
| civetweb-cxx | 2.1.0 | HTTP服务端封装 |
| **curl** | **8.12.1** | **✅ HTTP客户端** |
| **curl-cxx** | **9.0.1** | **✅ HTTP封装 (依赖 curl, openssl, cares, z)** |
| cutils | 0.0.0 | — |
| easyui | 2.6.0 | UI框架 |
| eigen | 3.4.0 | Eigen |
| faac | 1.30.0 | AAC编码 |
| ffmpeg | 4.1.9-configure2 | FFMPEG (本项目不需要) |
| fribidi | 1.0.12 | 双向文本 |
| gatt | 1.0.0 | BLE GATT |
| glibcxx-headers | 1.0.1 | glibc++头文件 |
| **jpeg** | **9.1.0** | **✅ JPEG解码** |
| ktp | 2.0.0 | 基于UDP的可靠传输 |
| log | 0.0.0 | 日志 |
| lrtp | 0.0.9 | RTP传输 |
| mp4v2 | 2.1.3 | MP4封装 |
| mqtt-cxx | 2.0.3 | MQTT客户端 |
| ntp | 2.1.0 | NTP客户端 |
| openh264 | 2.1.1 | H.264编码 (本项目不需要) |
| openssl | 1.1.1-g | ✅ SSL/TLS |
| paho-mqtt3as | 1.3.13 | Paho MQTT |
| **png** | **1.2.56** | **✅ PNG解码** |
| rapidjson | 1.1.0 | JSON解析 |
| sqlite3 | 3.7.11 | ✅ SQLite数据库 |
| transfer-protocols | 2.0.0 | 协议收发 |
| uClibc++ | 0.1.1 | uClibc++ STL |
| utf8conv | 1.1.1 | UTF8/GBK转换 |
| watchdog | 1.0.2 | 系统看门狗 |
| webp | 0.0.1 | WebP解码 |
| **z** | **1.2.11** | **✅ zlib压缩** |
| zkhardware | 0.0.0 | 硬件操作 |
| zknet | 0.0.0 | 网络操作 |

## 本项目 (WebView) 使用到的组件包

| 包名 | 用途 |
|------|------|
| curl (8.12.1) | HTTP 网页加载 |
| openssl (1.1.1-g) | HTTPS |
| png (1.2.56) | 图片解码 |
| jpeg (9.1.0) | 图片解码 |
| z (1.2.11) | gzip 解压 |
| sqlite3 (3.7.11) | WebKit 本地存储 |

## 系统自带（需确认路径）

| 库 | 说明 |
|----|------|
| freetype | 字体渲染，系统已集成 |
| 全志硬件 H.264 解码器 | 视频播放，通过回调接口对接 |
