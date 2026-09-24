# 其他项目接入小程序传图/视频对接指南

本文面向需要接入小程序局域网传图/视频的其他 FlyThings/EasyUI 项目。目标项目可按本文复现设备广播、文件接收和确认行为，并按第 6 节接入附带 C++ 源码。本文只约定广播、传输、保存和确认；媒体格式、分辨率及文件后续用途由目标项目自行决定。

> 兼容基准：`F133UhaleAlbum` 设备端提交 `39c25c1`（2026-09-24），项目维护者确认该次修改后的设备仍能配合已上线小程序正常传图。  
> 实测补充：2026-09-24，项目维护者使用已上线小程序实际验证了附带 Python 接收端，确认可正常完成传输，可作为其他项目的联调参考。（可优先参考python中的相关逻辑）  
> 整理日期：2026-09-24  
> 本文接入重点：UDP 设备发现、TCP 普通图片和视频接收；附带源码中的其他类型保持原有兼容行为。

附带的 6 个 C++ 源码文件与上述设备工程对应文件一致。对照 `ea5cd5c`（2026-06-24）历史版本，普通图片和视频的包头、32 KiB 分块确认、最终 `OK` 及设备端 2 秒 socket 超时规则均保持一致。本文以设备端行为为依据，不将当前本地小程序的选择、压缩及超时实现视为上线版本的准确源码。普通视频有接收实现依据；上线版本的视频实测结果应在目标设备联调时单独记录。

## 1. 协议概览

相框和小程序需要处于同一局域网。相框主动发送 UDP 广播，小程序从广播来源地址取得相框 IP，然后连接相框的 TCP 服务。

| 功能 | 协议 | 端口 | 方向 | 当前状态 |
| --- | --- | ---: | --- | --- |
| 设备发现 | UDP 广播 | 8899 | 相框 → 小程序 | 已实现 |
| 图片传输 | TCP | 9000 | 小程序 → 相框 | 已实现 |
| 视频传输 | TCP | 9000 | 小程序 → 相框 | 已实现 |

当前协议没有协议版本协商、身份认证、应用层内容校验和断点续传；接收端会检查文件字节数。文件传输仅适合可信局域网环境。

## 2. 总体交互流程

```text
相框启动小程序传输服务
        │
        ├─ 每约 2 秒向 255.255.255.255:8899 发送 UDP 广播
        │
小程序监听 UDP 8899
        │
        ├─ 解析设备名称
        ├─ 使用 UDP 数据包的来源 IP 作为相框 IP
        │
小程序连接 <相框 IP>:9000
        │
        ├─ 发送图片包 / 视频包
        ├─ 文件传输过程中按规则读取 ACK
        └─ 完成后读取 OK\n
```

设备端为 `accept()` 得到的连接 socket 设置了 2 秒收发阻塞超时。它不是整个文件的传输限时，也不是已上线小程序内部的 ACK 等待时长。服务端完成一个文件后会立即等待下一文件包头；等待数据期间长时间无数据到达，可能触发超时并关闭连接。一个大文件可以持续传输超过 2 秒。

## 3. UDP 设备发现

### 3.1 广播地址和频率

- 目标地址：`255.255.255.255`
- 目标端口：`8899`
- 发送周期：约 2 秒一次
- 数据格式：UTF-8 文本，不带换行符

### 3.2 广播内容

```text
zkswe:<deviceName>
```

示例：

```text
zkswe:Living Room
```

字段说明：

| 字段 | 示例 | 说明 |
| --- | --- | --- |
| 固定前缀 | `zkswe:` | 当前已验证设备端使用的广播前缀；移植时保持相同格式 |
| `deviceName` | `Living Room` | 相框名称；为空时相框侧使用 `Frame` |

小程序连接 TCP 时，应使用 UDP 消息的来源地址 `remoteInfo.address`，不要从广播文本中寻找 IP，因为当前广播正文不包含 IP 地址。

6 月历史版本直接广播设备名称，9 月 24 日版本增加了 `zkswe:` 前缀；维护者确认修改后仍可与上线小程序正常传图。本文采用后者作为接入格式，不据此推断上线小程序是否过滤或移除该前缀。设备无需等待小程序发出 UDP 搜索请求。

### 3.3 相框端实际广播代码

广播任务由 `src/mp_transfer/runtime_coordinator.h` 启动，UDP 数据由
`src/mp_transfer/broadcast_task.cpp` 发送，内容为 `zkswe:` 和设备名称：

```cpp
// src/mp_transfer/runtime_coordinator.h
void startLocked() {
    BroadcastTask::instance().start(
        BroadcastParams{mBroadcastName.empty() ? "Frame" : mBroadcastName});
    TcpReceiveTask::instance().start(TcpReceiveParams{});
}
```

```cpp
// src/mp_transfer/broadcast_task.cpp 的关键发送逻辑
addr.sin_family = AF_INET;
addr.sin_port = htons(8899);
addr.sin_addr.s_addr = inet_addr("255.255.255.255");

while (isRunning()) {
    std::string whole_content = "zkswe:" + params.content;
    sendto(sfd, whole_content.c_str(), strlen(whole_content.c_str()), 0,
           (struct sockaddr*)&addr, sizeof(addr));
    // 后续等待约 2 秒，再发送下一次广播。
}
```

实际函数还包括 socket 创建、`SO_BROADCAST` 设置、停止检查和错误日志；上面只摘录与协议有关的代码。

### 3.4 小程序发现示例

以下代码仅演示发现流程，不是已上线小程序源码。接入设备端时无需修改小程序；示例中的前缀过滤属于演示实现，具体 API 需按所使用的微信小程序基础库版本调整：

```js
const decoder = new TextDecoder('utf-8');
const udp = wx.createUDPSocket();

function parseFrameBroadcast(text) {
  const prefix = 'zkswe:';
  if (!text.startsWith(prefix)) return null;

  const name = text.slice(prefix.length);
  if (!name) return null;

  return {
    name,
  };
}

udp.onMessage(({ message, remoteInfo }) => {
  const text = decoder.decode(message);
  const device = parseFrameBroadcast(text);
  if (!device) return;

  const frame = {
    ...device,
    address: remoteInfo.address,
    tcpPort: 9000,
  };

  console.log('发现相框：', frame);
});

udp.bind(8899);
```

如果路由器开启了 AP 隔离、客户端隔离，或者手机和相框处于不同 VLAN，UDP 广播可能无法到达小程序。

## 4. TCP 连接

### 4.1 连接参数

| 参数 | 当前值 |
| --- | ---: |
| 相框监听地址 | `0.0.0.0` |
| TCP 端口 | `9000` |
| 设备端已接受连接的 socket 收发阻塞超时 | `2000 ms` |
| 文件分块大小 | `32 KiB` |
| 单包最大 payload | `500 MiB` |

TCP 是字节流协议，单次 `write()` 不保证对应服务端单次 `recv()`。客户端必须严格按字段长度发送；读取服务端响应时也必须自行缓存并按 `\n` 拆分，不能假设一次回调恰好收到一整行。

### 4.2 公共包头

所有 TCP 包都以 5 字节公共包头开始：

| 偏移 | 长度 | 类型 | 字节序 | 说明 |
| ---: | ---: | --- | --- | --- |
| 0 | 1 | `uint8` | 不适用 | 包类型 `type` |
| 1 | 4 | `uint32` | 网络字节序/大端 | payload 长度 `len` |

包类型定义：

| 值 | 名称 | 说明 |
| ---: | --- | --- |
| 1 | `TYPE_IMAGE` | 普通图片文件 |
| 2 | `TYPE_VIDEO` | 普通视频文件 |
| 3 | `TYPE_LIVE` | 附带源码保留的扩展类型，使用同一文件报文和确认规则 |

`len` 必须大于 0，并且不能超过 `500 * 1024 * 1024`。非法类型或非法长度会使相框关闭当前 TCP 连接，当前不会返回结构化错误。

附带源码还保留早期已有的 `TYPE_TEXT=0` 分支：公共包头后直接读取 `len` 字节文本，再回复 `OK\n`，没有文件名字段，也不按文件分块发送 ACK。没有证据说明上线传图流程必然使用该类型；复用源码时可保留此分支，不要将其解释为必须先发送的握手或设备控制命令。

## 5. 文件包

### 5.1 报文格式

媒体文件使用以下报文结构：

```text
+------+------------------+------------------+--------------------+----------------+
| type | fileLen, 4字节   | nameLen, 2字节   | filename           | fileData       |
+------+------------------+------------------+--------------------+----------------+
| 1字节| uint32，大端     | uint16，大端     | nameLen 字节       | fileLen 字节   |
+------+------------------+------------------+--------------------+----------------+
```

注意：公共包头中的 `len` 对文件包表示**文件内容字节数**，不包含 `nameLen` 和 `filename`。

文件名要求：

- UTF-8 编码后的长度为 `1..256` 字节；
- 不能包含 `..`；
- 不能包含 `/`；
- 不能包含 `\`；
- 建议使用唯一文件名，避免覆盖相同路径的旧文件。

相框接收目录：

```text
/mnt/extsd/mp_transfer/
```

### 5.2 相框端实际接收代码

实际接收入口为 `src/mp_transfer/tcp_receive.cpp` 中的
`TcpReceiveTask::handleClient()`。服务端先循环读取类型和大端 payload 长度：

```cpp
uint8_t type = 0;
uint32_t len = 0;
recvAll(client_fd, &type, sizeof(type), "read packet type", peer, false);
recvAll(client_fd, &len, sizeof(len), "read payload length", peer);
len = ntohl(len);

if (len == 0 || len > params.max_file_size) {
    break;
}
```

在前述文本分支之后，文件接收分支允许以下类型：

```cpp
if (type != TYPE_IMAGE && type != TYPE_VIDEO && type != TYPE_LIVE) {
    break;
}
const bool is_live_packet = (type == TYPE_LIVE);
```

文件分支继续读取 UTF-8 文件名，写入 `.tmp` 临时文件。主体接收逻辑如下（省略异常检查和日志）：

```cpp
while (received < len && isStarted()) {
    size_t need = std::min(
        static_cast<size_t>(len - received), buf.size());
    recvAll(client_fd, buf.data(), need, "read file chunk", peer);
    fwrite(buf.data(), 1, need, fp);
    received += static_cast<uint32_t>(need);

    if (received < len) {
        sendPacketAck(client_fd, received, peer);
    }
}
```

收到完整文件后会校验临时文件大小，再将其重命名为正式文件、更新缓存并返回最终 `OK\n`：

```cpp
if (stat(tmp_path.c_str(), &st) != 0 ||
        static_cast<uint64_t>(st.st_size) != len) {
    break;
}

rename(tmp_path.c_str(), final_path.c_str());
updateCacheWithFile(final_path, is_live_packet);
sendFinalOk(client_fd, peer);
```

普通图片和普通视频分别使用类型 `1` 和 `2`。示例保留源码的扩展类型分支，仅用于说明现有接收实现。

### 5.3 文件接收过程

相框不会直接写最终文件，而是先写临时文件：

```text
photo.jpg → photo.tmp
video.mp4 → video.tmp
```

接收完成后设备执行：

1. 校验实际临时文件大小是否等于 `fileLen`；
2. 将 `.tmp` 重命名为最终文件名；
3. 按需发出文件完成通知；
4. 回复 `OK\n`。

附带源码中的媒体解析和缓存更新属于原项目附加逻辑，可按第 6.2 节替换或移除，不是完成文件传输的前提。

传输中断或大小校验失败时，不会将临时文件改名为正式文件，也不会回复成功。残留 `.tmp` 会在后续清理流程中删除。

`OK` 表示文件接收流程完成，不代表目标项目已完成后续使用。附带源码通过 `onFileAdded()` 通知接收结果，移植时可替换为项目自己的通知方式，见第 6.3 节。

### 5.4 ACK 规则

相框内部按 `32 KiB` 接收文件。每完成一个**非最后分块**，回复：

```text
ACK <累计已接收字节数>\n
```

例如发送一个 100000 字节文件：

```text
发送第 1 块 32768 字节 ← ACK 32768\n
发送第 2 块 32768 字节 ← ACK 65536\n
发送第 3 块 32768 字节 ← ACK 98304\n
发送最后一块 1696 字节 ← OK\n
```

最后一个分块不回复 `ACK`，完成文件大小校验和重命名后直接回复 `OK\n`。

移植接收端时必须保留以下边界行为：

- 文件大小不超过 32768 字节时，没有分块 ACK，完成后直接回复 `OK\n`。
- 文件大小恰好是 32768 的整数倍时，最后一个完整分块仍只对应最终 `OK\n`。
- ACK 中的数字是当前文件累计接收的内容字节数，不包含包头或文件名；每个文件从零重新累计。
- 按 `recvAll()` 累积到指定分块长度后再回复，不能按单次 `recv()` 返回的长度决定 ACK 边界。
- `\n` 表示真正的换行字节 `0x0A`，不是反斜杠和字母 n 两个字符；不要额外发送字符串结尾的 NUL。
- 不增加包头确认、欢迎消息或必需握手；每个文件只发送一次最终 `OK`，随后继续读取同一连接的下一文件包头。

客户端必须持续读取这些响应。若客户端只发送数据、不读取 ACK，大文件传输时服务端发送缓冲区可能被占满，最终导致 2 秒发送超时并断开连接。

### 5.5 文件发送参考代码

以下示例用于说明协议，不是已上线小程序源码。假定 `fileBytes` 是普通 `Uint8Array`，`readLine()` 能跨多次 TCP 回调缓存数据，直到读取到 `\n`：

```js
const TYPE_IMAGE = 1;
const TYPE_VIDEO = 2;
const CHUNK_SIZE = 32 * 1024;

function buildFileHeader(type, filename, fileSize) {
  const name = new TextEncoder().encode(filename);
  if (name.byteLength === 0 || name.byteLength > 256) {
    throw new Error('invalid filename length');
  }
  if (filename.includes('..') || filename.includes('/') || filename.includes('\\')) {
    throw new Error('invalid filename');
  }

  const header = new Uint8Array(1 + 4 + 2 + name.byteLength);
  const view = new DataView(header.buffer);
  view.setUint8(0, type);
  view.setUint32(1, fileSize, false);       // uint32，大端
  view.setUint16(5, name.byteLength, false); // uint16，大端
  header.set(name, 7);
  return header.buffer;
}

async function sendFile(tcp, readLine, type, filename, fileBytes) {
  tcp.write(buildFileHeader(type, filename, fileBytes.byteLength));

  let offset = 0;
  while (offset < fileBytes.byteLength) {
    const end = Math.min(offset + CHUNK_SIZE, fileBytes.byteLength);
    const chunk = fileBytes.slice(offset, end);
    tcp.write(chunk.buffer);
    offset = end;

    if (offset < fileBytes.byteLength) {
      const line = await readLine();
      const expected = `ACK ${offset}`;
      if (line !== expected) {
        throw new Error(`unexpected ACK: ${line}, expected: ${expected}`);
      }
    }
  }

  const result = await readLine();
  if (result !== 'OK') {
    throw new Error(`transfer failed: ${result}`);
  }
}

// 普通图片
await sendFile(tcp, readLine, TYPE_IMAGE, 'photo.jpg', imageBytes);

// 普通视频
await sendFile(tcp, readLine, TYPE_VIDEO, 'video.mp4', videoBytes);
```

生产代码不建议把大文件一次性全部读入内存，应使用小程序文件系统 API 按 `32 KiB` 分段读取。

## 6. 如何参考附带 C++ 源码

接入目标是完成：**设备广播 → 小程序连接 → 接收并保存文件 → 回复确认**。文件收到后如何使用，由目标项目自行决定，不要求具备原相框项目的业务模块。

### 6.1 各文件参考什么

| 文件 | 作用 | 接入时重点参考 |
| --- | --- | --- |
| [broadcast_task.h](src/mp_transfer/broadcast_task.h)、[broadcast_task.cpp](src/mp_transfer/broadcast_task.cpp) | UDP 设备广播 | 创建广播 socket，约每 2 秒向 UDP 8899 发送设备名。传入原始名称即可，任务内部会添加 `zkswe:`。 |
| [tcp_receive.h](src/mp_transfer/tcp_receive.h) | 接收参数与接口 | TCP 9000、32 KiB 分块、500 MiB 上限、设备端 2 秒 socket 超时。 |
| [tcp_receive.cpp](src/mp_transfer/tcp_receive.cpp) | TCP 接收核心 | 从 `doTask()` 看监听流程，从 `handleClient()` 看包头解析、文件保存、ACK 和 OK。 |
| [runtime_coordinator.h](src/mp_transfer/runtime_coordinator.h) | 服务启停 | `retain()` 启动并持有服务，`release()` 释放；最后一个持有者释放后停止服务。 |
| [transfer_type_and_data.h](src/system/transfer_type_and_data.h) | 接收结果结构 | 可保留 `TransferFileInfo`，也可转换为目标项目自己的文件信息。其枚举不是网络包类型。 |

建议先读 `tcp_receive.h` 的参数，再读 `handleClient()` 的完整收包流程。第 5 节仅是摘录，实际移植应参考完整源码中的错误判断和资源清理。

### 6.2 目标项目需要适配的地方

已有同一套 `base` 框架时，可复制这 6 个文件，将两个 `.cpp` 加入编译，并适配依赖。没有该框架时，按源码保留网络和文件处理逻辑，用项目自己的线程、日志和文件接口替换。

| 原工程依赖 | 接入方式 |
| --- | --- |
| `base::Task`、单例宏、日志宏、`defer` | 使用现有基础库，或替换成目标项目的后台任务和资源清理方式；`defer` 不是标准 C++ 语法。 |
| POSIX socket、文件 API | 在目标设备工具链下编译；当前源码面向 Linux 设备。 |
| `config.h` 中的 `MP_PATH` | 改为设备上已挂载、可写的接收目录。当前代码直接拼接文件名，目录末尾需带 `/`。 |
| `base::exists/mkdirs/listFiles` | 替换为项目自己的目录和文件操作；保留未完成临时文件的清理。 |
| `FileParseManager`、文件缓存 | 属于原工程的媒体管理。只需接收文件时，可移除或替换 `scanPath()`、`updateCacheWithFile()` 中相应逻辑，连同不再使用的头文件和调用一起调整。 |

媒体解析、扫描和缓存并不是网络传输的必需条件。可以在正式文件保存成功后，直接通知目标项目文件路径和大小，再按原时序回复 `OK`。这些改动不应影响文件长度校验、临时文件改名和异常清理。

### 6.3 启动、停止和完成通知

在网络和接收目录准备好后启动服务；退出或不再需要传输时停止。若保留附带协调器，可参考：

```cpp
#include "mp_transfer/runtime_coordinator.h"

// 启动：传入原始设备名称。
MpTransferRuntimeCoordinator::instance().retain("my-project", "My Frame");

// 停止：在对应的退出位置使用同一 owner。
MpTransferRuntimeCoordinator::instance().release("my-project");
```

以上两句放在各自的启动和退出位置，不是连续执行。`owner` 按字符串集合管理，同一名称多次持有不会累加次数；仍有其他持有者时，服务不会停止。运行中改名可能重启服务，应避开发送过程。启动接口返回不代表监听已成功，需检查 `bind/listen` 结果。

如果需要收到文件完成通知，可实现 `TcpReceiveListener` 并通过 `addListener()` 注册，在 `onFileAdded()` 中取得文件信息；不需要的扫描和连接状态回调可留空。若已替换原缓存逻辑，也可以在保存完成处调用项目自己的通知接口。

回调应尽快返回，耗时操作由项目另行安排。监听者销毁前先注销，不要在回调内部执行注册、注销或服务启停操作。

### 6.4 必须保持一致的传输行为

- 设备主动广播 UDP 8899，并监听 TCP 9000；无需等待小程序发送搜索请求。
- 按第 5 节读取字段，保留 `recvAll/sendAll` 对拆包和短读短写的处理。
- 每个非末尾 32 KiB 分块回复累计字节数 ACK，最后一块完成后回复一次 `OK\n`；不能随意改变确认边界或增加额外握手。
- 文件先写临时文件，完整接收并校验大小后改名；失败时结束本次连接并清理未完成文件。
- 回复 `OK` 后继续读取同一连接的下一文件，不要默认一个连接只接收一个文件。
- 停止服务时唤醒或关闭阻塞的 socket 操作，并释放文件与连接资源。

接入后用上线小程序验证设备发现、单张图片、连续多文件、视频以及中断后重新发送。判断传输完成以文件正确保存和最终确认成功为准；文件的后续用途不属于本指南的接入要求。

### 6.5 用 Python 模拟设备端验证

附带 [receiver.py](src/python/receiver.py) 可在电脑上模拟设备：主动广播、接收小程序上传的文件，并回复 ACK／OK。只需 Python 3.9 或更新版本，无需安装第三方库，不检查媒体格式或分辨率。

**实测记录（2026-09-24）：** 项目维护者已使用上线小程序实际验证，确认该 Python 接收程序可用。接入其他项目时，可先运行它确认网络与小程序传输正常，再对照其广播、包头解析、分块 ACK 和最终 `OK` 行为实现目标接收端。

在本指南所在目录打开 PowerShell，运行：

```powershell
py .\src\python\receiver.py --name PythonFrame --output .\received
```

手机与电脑连接同一局域网，在已上线小程序中找到 `PythonFrame`（名称可能显示为 `zkswe:PythonFrame`），选择后发送照片或视频。文件保存在当前目录的 `received` 文件夹，终端显示文件名、大小、进度和最终确认结果。Windows 如弹出防火墙提示，请允许 Python 在当前专用网络通信。按 `Ctrl+C` 停止服务。

电脑有多个网卡或 VPN、默认广播无法被手机发现时，用 `ipconfig` 查看与手机同网段的本机 IPv4，然后指定网卡地址和对应的子网广播地址。例如以下命令适用于 `<本机IP>/24` 的网络，实际地址应按本机 IP 和子网掩码填写：

```powershell
py .\src\python\receiver.py --name PythonFrame --bind <本机IP> --broadcast <子网广播地址> --output .\received --verbose
```

- 固定使用 UDP `8899` 和 TCP `9000`；广播每 2 秒发送一次，TCP 每个非末尾 32 KiB 分块回复 ACK。
- 默认连接收发超时为 2 秒，与附带 C++ 一致；可用 `--timeout 10` 临时放宽以排查传输停顿，此参数不是整文件限时。
- `--verbose` 会打印广播和分块 ACK。设备不可见时检查网卡、广播及路由器客户端隔离；可见但无法连接时检查 TCP 9000 的防火墙规则和端口占用。
- 同一连接支持连续文件；临时文件在失败后清理，成功后才回复 `OK`。同名文件会覆盖，建议使用单独的测试接收目录。
- 脚本保留类型 `0/1/2/3` 的网络兼容处理，只保存媒体文件，不执行原设备业务；Windows 不支持的文件名会拒绝并记录原因。

## 7. 当前协议边界

- 广播没有协议版本字段；
- 广播没有设备唯一 ID 和 TCP 端口字段，TCP 端口固定为 9000；
- TCP 没有握手版本协商；
- TCP 没有认证和加密；
- TCP 包没有 CRC、HASH 或内容摘要；
- 文件不支持断点续传；
- 非法请求通常直接断开连接，不返回详细错误；
- ACK 是本协议的一部分，小程序必须持续读取；
- TCP 空闲超时较短，不适合长时间保持空闲连接；

## 8. 联调检查清单

1. 手机和相框连接同一路由器，且没有开启客户端隔离；
2. 小程序能够监听 UDP 8899；
3. 广播正文以 `zkswe:` 开头；
4. 使用广播来源 IP 连接 TCP 9000；
5. 所有整数按大端发送；
6. 文件名按 UTF-8 字节数计算长度；
7. 文件传输每个非末尾 32 KiB 分块后读取并校验 ACK；
8. 最后一个分块后读取 `OK`；
9. 设备端 socket 的 2 秒阻塞超时没有被误作整文件传输限时；接收及文件间停顿不会导致意外断连；
10. 普通图片使用 type 1，普通视频使用 type 2；
11. 确认接收端仅在完整落盘和本地检查成功后回复最终 `OK`；
12. 文件完成通知及时返回，后续项目处理不会阻塞下一文件的接收。
