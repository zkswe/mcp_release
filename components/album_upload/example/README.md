# example —— album_upload 最小接线

> ⚠️ **验证状态**：组件本体（`../src/zk_album.cpp`）判据 = PC 侧语法自检（0 warning，见 `../README.md` §7）；
> `flythings_wiring.cc` 是**接线形状**（要工程里的 easyui 头 + 生成代码，不能单独编）；
> **真机端到端（微信扫码传图）本仓无逐条取证** —— 详见 `../platforms.md` §0/§1.5。

| 文件 | 作用 |
|---|---|
| `album_upload_example.cc` | 端到端生命周期样板：`configure → setQrUrl(prefs) → 回调 → start → （运行业务）→ stop`；含二维码两条来源的打印与"上屏就是 loadQRCode(content)"的注释 |
| `flythings_wiring.cc` | FlyThings 工程接线样板：从 prefs 读配置（键名语义 `sp_dev_name`/`sp_album_mode`/`sp_qr_url`/`sp_mp_appid`）、**二维码落 UI（`qrInfo().content` → 控件现场生成，不铺位图）**、定时器刷新、模式开关 |

## 1. 三步接起来

```bash
# ① 传输本体：把 components/mp_transfer/ 拷进工程（**不要**复制本组件里的任何传输代码）
#    src/mp_transfer/{broadcast_task,tcp_receive}.{h,cpp}
#    src/mp_transfer/runtime_coordinator.h
#    src/system/transfer_type_and_data.h
#    两个 .cpp 加进编译；MP_PATH 指到你要的目录（末尾带 '/'）

# ② 本组件
#    components/album_upload/include/zk/zk_album.h  ->  <工程>/src/zk/zk_album.h
#    components/album_upload/src/zk_album.cpp       ->  <工程>/src/zk/zk_album.cpp（并加进编译）

# ③ 依赖：按 ../Manifest.xml 往工程 Manifest/fun.json 里加 easyui / log / base-utility
#    （二维码现场生成、不下载位图 → **不需要 curl-cxx**）
#    ⚠️ 改完 Manifest 必须重跑：fun install      （否则新 include 路径不进 CMake）

# ④ 编译
fun build -p <平台>
```

然后把 `flythings_wiring.cc` 里的 `albumPageInit/Show/Hide/Quit/Timer` 五段贴进你的
`onUI_init/onUI_show/onUI_hide/onUI_quit/onUI_Timer`（**别改**语义：回调只置标志、UI 定时器消费标志）。

## 2. 三个最容易踩的点（照抄能省一轮真机）

1. **`onUI_quit` 两句必做**：业务侧二维码内容缓存 `clear()` + `stop()`。
   不做 → 再进页二维码空白、要切页面才出来（真机复现过，见 `../README.md` §6 坑 1）。
   组件侧**不缓存**二维码内容（`qrInfo()` 即时计算），没有需要清的组件缓存。
2. **回调是接收线程**：`onFileAdded` / `onStateChanged` 里只置标志（`sNeedRefresh = true`），
   控件操作全放到 UI 定时器 —— 直接在回调里 `setText()` 是竞态来源。
3. **落盘目录写两处**：`Config::save_dir` 与 mp_transfer 的 `MP_PATH` 必须一致，末尾都带 `/`。
4. **二维码内容从 prefs 灌**：`setQrUrl(StoragePreferences::getString("sp_qr_url", ""))`；空串 = 本机地址兜底，
   组件**不带默认链接**（示例值见 `../assets/qr_url.txt`，取自 `../assets/README.md`）。

## 3. 怎么验（三层，逐层加真）

| 层 | 命令/做法 | 期望 |
|---|---|---|
| ① PC（不接设备） | 组件：`g++ -std=c++11 -fsyntax-only -Wall -Wextra -Iinclude -I<桩头>` `src/zk_album.cpp example/album_upload_example.cc`；链路：`components/mp_transfer/src/python/receiver.py` | 0 warning；PC 收端文件长度一致、逐块 `ACK`、末块 `OK` |
| ② 设备（不上屏） | `fun build -p <平台>` + 推设备 + 看日志 | 「广播 UDP 8899 + 监听 TCP 9000，期望落盘 …」；小程序能发现设备名 |
| ③ 端到端 | 面板上屏二维码 → 手机微信扫码 → 选图传 | 文件出现在 `save_dir`（大小 == 协议声明、无 `.tmp` 残留）；`onFileAdded` 触发；页面计数刷新 |

（②③ 的验收口径与"未取证清单"见 `../platforms.md` §5/§6。）
