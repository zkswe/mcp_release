# mp_transfer —— 小程序传图/视频（设备端接收参考实现）

> 来源：`F133UhaleAlbum` 设备端提交 `39c25c1`（2026-09-24），**已在其他产品上验证**（附带的 Python 参考接收端由项目维护者用已上线小程序实测通过）。
> 入库：2026-09-24（钟工：「小程序传输对接指南」先入库，做**相册上传/相册传输模式**时用它）。
> 知识文档（可检索、含移植清单与坑）：`knowledge/devflow/mp-transfer-miniprogram.md`

## 是什么 / 不是什么

**是**：任何 FlyThings/EasyUI 设备接「小程序局域网传图/传视频」的最小闭环 ——
**设备 UDP 广播被发现 → 小程序 TCP 连设备 → 收文件落盘 → 回确认**。

**不是**：媒体解析/相册业务/断点续传/加密认证。收完文件怎么用，由目标项目自己定。

## 协议速查

| 项 | 值 |
|---|---|
| 发现 | UDP 广播 `255.255.255.255:8899`，每 ≈2 s，正文 `zkswe:<设备名>`（UTF-8，**无换行**；名字空则 `Frame`） |
| 传输 | TCP `0.0.0.0:9000`；accept 后连接 socket **收发阻塞超时 2 s** |
| 包头 | `type`(uint8) + `len`(uint32 **大端**)，`len`=文件内容字节数，有效 `1..500 MiB` |
| 类型 | `1`=图片 / `2`=视频（`0`=文本兼容分支、`3`=扩展，同文件规则） |
| 文件包 | `type(1B) + fileLen(4B BE) + nameLen(2B BE) + filename(UTF-8) + fileData` |
| 文件名 | UTF-8 长度 1..256 字节；禁 `..` `/` `\` |
| 分块 | 32 KiB；**非末块**回 `ACK <累计字节>\n`，**末块**完成校验改名后回 `OK\n` |
| 落地 | `/mnt/extsd/mp_transfer/`（原工程 `config.h` 的 `MP_PATH`，移植换自己目录，**末尾带 `/`**） |
| 落盘 | 先写 `<name>.tmp` → 校验大小 == fileLen → `rename` → 回 `OK\n`；失败不改名 |

⚠️ 一个连接可连续收多个文件（回 `OK` 后继续读下一包头）；客户端必须持续读 ACK，否则服务端发送缓冲填满 → 2 s 超时断连。

## 文件清单

| 文件 | 作用 |
|---|---|
| `src/mp_transfer/broadcast_task.{h,cpp}` | UDP 广播任务（内部自动加 `zkswe:` 前缀，外面传原始设备名） |
| `src/mp_transfer/tcp_receive.{h,cpp}` | TCP 接收核心：`doTask()` 监听流程、`handleClient()` 包头解析/落盘/ACK/OK |
| `src/mp_transfer/runtime_coordinator.h` | 服务启停（`retain(owner, name)` / `release(owner)`，owner 集合，最后一个释放才停） |
| `src/system/transfer_type_and_data.h` | 接收结果结构 `TransferFileInfo`（其枚举**不是**网络包类型） |
| `src/python/receiver.py` | **PC 模拟设备端**：广播 + 收文件 + ACK/OK，纯标准库（Python ≥3.9） |
| `docs/miniprogram-transfer-guide.md` | 对接指南全文（含流程、代码摘录、边界、联调清单） |

## 怎么用

```bash
# 1) 先不接设备，用 PC 验证网络与小程序链路（手机与电脑同一局域网）
py .\src\python\receiver.py --name PythonFrame --output .\received
#    多网卡/VPN：--bind <本机IP> --broadcast <子网广播地址> --verbose

# 2) 接设备端：复制 4 个源文件 + 1 个头到工程，两个 .cpp 加入编译，适配依赖
#    base::Task/日志宏/defer → 换项目自己的后台线程与 RAII；MP_PATH → 自己的可写目录
#    媒体解析/缓存（FileParseManager 等）可整段删掉，不影响传输与落盘
# 3) 启动/停止
MpTransferRuntimeCoordinator::instance().retain("my-project", "My Frame");
MpTransferRuntimeCoordinator::instance().release("my-project");
```

## 已知边界（写需求时注意）

无版本协商 / 无设备唯一 ID（端口固定 9000）/ 无认证加密 / 无 CRC 校验 / 无断点续传 / 非法请求直接断连不报错 / TCP 空闲超时短（不适合保活）。**仅适合可信局域网。**

检索词：小程序传图 / 相册传输模式 / mp_transfer / UDP 8899 / TCP 9000 / zkswe: 广播 / 32KiB ACK / OK 确认 / 相框接收端


## 编译前置（本组件自带，2026-09-30 补）

- 落盘目录、媒体解析均已收进组件：
  - src/mp_transfer/mp_config.h：MP_PATH（默认 /mnt/sdnand/album/，末尾带 /）—— 改这里或 -DMP_PATH=...。
  - 媒体解析默认**不做**（只填 path/name/size/mtime）；要宽高/时长就给 mp_parse_file() 写强符号，或编译加 -DMP_TRANSFER_HAVE_FILE_PARSER=1 并提供 mtp_monitor/file_parse_manager.h。
- 依赖：ase-utility（ase::Task）+ log（<android/log.h>）。
  ⚠！ase-utility 的头会引入 SDK 的 os/MountMonitor.h（在 easyui 包里）——**单独建 in 工程会编不过**（缺该头；强行链 easyui 又会带一堆未解析符号）。
  本组件属于 **zkgui 工程**，受支持的验证方式 = 接进 zkgui 工程后 un build -p <平台>。
