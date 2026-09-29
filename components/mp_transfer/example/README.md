# example · mp_transfer 最小示例（设备端接线 + PC 侧联调）

> ⚠️ **验证状态**：本模块的协议口径有**来源工程**的现场依据（`F133UhaleAlbum` 提交 `39c25c1` + 维护者用已上线小程序实测），
> 但**本仓的组件形态（4 源文件 + 1 头）没有设备侧上机记录** → 本示例是「接线形态 + 怎么验」，不是「已验结果」。
> 详见 `../platforms.md` §0。

| 文件 | 用途 |
|---|---|
| `mp_transfer_min_example.cc` | 设备端接线示例：`retain/release` 起停、`TcpReceiveTask::TcpReceiveListener` 收文件通知、`TcpReceiveParams` 参数、典型生命周期调用 |
| （本目录无 ui/json） | 本模块**不提供 UI**：媒体解析与相册业务按项目自己定（README 明说「不是媒体解析/相册业务」） |

## 1. 三步接起来

1. **拷文件**（照 `../README.md` 的「怎么用」）：把 `src/mp_transfer/{broadcast_task,tcp_receive}.{h,cpp}`、
   `src/mp_transfer/runtime_coordinator.h`、`src/system/transfer_type_and_data.h` 复制进工程；
   两个 `.cpp` 加进编译。
2. **适配依赖**：`base::Task` / 日志宏 / `defer` → 换项目自己的后台线程与 RAII；`MP_PATH` → 自己可写目录（**末尾带 `/`**）；
   媒体解析/缓存（`FileParseManager` 等）可整段删掉，不影响传输与落盘。
3. **接线 + 编译**：把 `mp_transfer_min_example.cc` 的核心三行抄进你的生命周期：
   ```cpp
   MpTransferRuntimeCoordinator::instance().retain("my-project", "My Frame");   // 起（广播 + 监听 9000）
   TcpReceiveTask::instance().addListener(&listener);                          // 收文件通知
   MpTransferRuntimeCoordinator::instance().release("my-project");             // 停（owner 全释放才真停）
   ```
   然后 `fun build`（依赖 `base-utility`）。

## 2. 验证点（三层，逐层加真）

| 层 | 命令/做法 | 期望 |
|---|---|---|
| ① PC 侧（不接设备） | `py .\src\python\receiver.py --name PythonFrame --output .\received` | 小程序能发现 `PythonFrame` 并传图；文件长度与发送端一致；非末块 `ACK <累计字节>\n`、末块 `OK\n` |
| ② 设备侧（不上屏） | `fun build` → 推设备跑 → 看 logcat | 广播任务启动、TCP 监听 9000；小程序能发现你的设备名 |
| ③ 端到端 | 小程序传图片/视频 | 文件落在 `MP_PATH`，大小 == 协议声明的 `fileLen`，**无残留 `.tmp`**；`onFileAdded()` 回调被触发 |

## 3. 联调最容易踩的三件事（协议层面，来自指南）

1. **客户端必须持续读 ACK**：只发不读 → 服务端发送缓冲填满 → 2 s 超时断连（大文件必踩）。
2. **分块边界按"累计到 32 KiB"算**，不是按单次 `recv()` 返回长度；`\n` 是真正的 `0x0A`（不要发 NUL、不要发字符串 `"\\n"`）。
3. **UDP 广播到不了小程序**：路由器开了 AP 隔离/客户端隔离，或手机与设备不同 VLAN。
   设备端无需等"搜索请求"，它只是每 ≈2 s 广播一次。
