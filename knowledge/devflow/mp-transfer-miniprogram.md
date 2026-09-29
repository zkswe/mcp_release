---
id: devflow-mp-transfer-miniprogram
title: 📥 小程序传图/视频对接（相框类设备的局域网接收端）
category: devflow
status: verified
confidence: manual
verified_at: 2026-09-29
stale_days: 180
origin: total
source: 2026-09-29 front-matter 迁移（P1：先显式登记"待补可执行判据"）
needs_evidence: true
platforms: []
tags: [2026-09-24 入库, 小程序传输对接指南, 已在其他产品上验证, 先入库, 2026-09-24, mp_transfer, python, receiver, EasyUI 项目要接, 小程序传图]
evidence: []
---
# 📥 小程序传图/视频对接（相框类设备的局域网接收端）

> 检索导引：问「小程序传图/传视频 / 相框类设备接收端 / UDP 8899 设备发现 / TCP 9000 收文件 / ACK 怎么回 / 局域网对接怎么联调」→ 本文；实现代码在 `components/mp_transfer/`。
> 2026-09-24 入库（钟工：「小程序传输对接指南.zip 是相册传输模式下的对接方案，已在其他产品上验证，先入库」）。
> 来源：`F133UhaleAlbum` 设备端提交 `39c25c1`（2026-09-24）；附带的 Python 参考接收端由项目维护者用**已上线小程序**实测通过。
> 原始资料与源码：`components/mp_transfer/`（6 个 C++ 文件 + `src/python/receiver.py` + 指南全文）。
> 适用：任何 FlyThings/EasyUI 项目要接「小程序传图/传视频」的场景（本项目 `SmartPanel_HA` 的**相册上传**功能即用它）。

---

## 1. 一句话结论

设备只干三件事：**每 2 秒 UDP 8899 广播 `zkswe:<设备名>` → TCP 9000 收文件（32 KiB 分块，非末块回 `ACK <累计字节>\n`）→ 完整落盘后回 `OK\n`**。
媒体格式/分辨率/拿到文件后怎么用，由目标项目自己定；协议不含认证、校验和、断点续传，只适合可信局域网。

## 2. 协议速查

| 功能 | 协议 | 端口 | 方向 | 现状 |
|---|---|---|---|---|
| 设备发现 | UDP 广播 | **8899** | 设备 → 小程序 | 已实现 |
| 图片传输 | TCP | **9000** | 小程序 → 设备 | 已实现 |
| 视频传输 | TCP | **9000** | 小程序 → 设备 | 已实现 |

- **广播正文**：UTF-8 文本、**不带换行**：`zkswe:<deviceName>`（设备名空 → `Frame`）；周期 ≈2 s，目标 `255.255.255.255:8899`
- **小程序侧取 IP**：用 UDP 报文的 `remoteInfo.address`，**不要从广播正文里找 IP**（正文没有 IP）
- **TCP 监听** `0.0.0.0:9000`，`accept()` 后的连接 socket **收发阻塞超时 2 s**（≠ 整文件限时，大文件可传超 2 s；但文件间长空闲会被断开）
- **公共包头 5 B**：`type`(uint8) + `len`(uint32 **大端**)，`len` = 文件内容字节数（0 < len ≤ 500 MiB；非法即断连）
- **type**：`0`=文本兼容分支（收完回 `OK\n`，无文件名、无分块 ACK）；`1`=图片；`2`=视频；`3`=扩展（同文件规则）→ 传图传视频用 **1 / 2**
- **文件包**：`type(1) + fileLen(4,BE) + nameLen(2,BE) + filename(nameLen UTF-8) + fileData(fileLen)`
  - 文件名：UTF-8 长度 **1..256 字节**；禁含 `..`、`/`、`\`；建议唯一名防覆盖
- **落地目录**：`/mnt/extsd/mp_transfer/`（原工程 `config.h` 的 `MP_PATH`；移植时改成自己已挂载可写的目录，**末尾带 `/`**）
- **落盘姿势**：先写 `<name>.tmp` → 校验临时文件大小 == `fileLen` → `rename` 为正式文件 → 回 `OK\n`；失败不改名、不回复成功，残留 `.tmp` 由清理流程删

## 3. ACK 规则（最容易抄错的地方）

内部按 **32 KiB** 接收，**每个非末块**回 `ACK <累计已接收字节数>\n`：

```text
发送第 1 块 32768 字节   ← ACK 32768\n
发送第 2 块 32768 字节   ← ACK 65536\n
发送第 3 块 32768 字节   ← ACK 98304\n
发送最后一块 1696 字节   ← OK\n          （末块不回 ACK）
```

不可改动的边界行为：

1. 文件 ≤ 32768 B：**没有分块 ACK**，完成直接 `OK\n`
2. 文件恰好是 32768 整数倍：最后一个完整分块也只对应最终 `OK\n`
3. `ACK` 里的数字 = **当前文件的累计内容字节数**（不含包头/文件名），**每个文件从 0 重新累计**
4. ACK 边界按 `recvAll()` 累计到分块长度决定，**不能按单次 `recv()` 返回长度**
5. `\n` 是真换行 `0x0A`，别发 NUL；不要加欢迎/握手包；**一个连接可连续收多个文件**（回 `OK` 后继续读下一个包头）
6. 客户端**必须持续读 ACK**：只发不读会把服务端发送缓冲填满 → 2 s 超时断连

## 4. 设备端实现要点（照抄这几段）

广播（`components/mp_transfer/src/mp_transfer/broadcast_task.cpp`）：

```cpp
addr.sin_family = AF_INET;
addr.sin_port   = htons(8899);
addr.sin_addr.s_addr = inet_addr("255.255.255.255");
while (isRunning()) {
    std::string whole_content = "zkswe:" + params.content;   // 前缀在任务内加，外面传原始名即可
    sendto(sfd, whole_content.c_str(), strlen(whole_content.c_str()), 0,
           (struct sockaddr*)&addr, sizeof(addr));
    /* 等约 2 秒再发下一次 */
}
```

接收主体（`tcp_receive.cpp::TcpReceiveTask::handleClient()`）：

```cpp
uint8_t type = 0; uint32_t len = 0;
recvAll(client_fd, &type, sizeof(type), "read packet type", peer, false);
recvAll(client_fd, &len, sizeof(len), "read payload length", peer);
len = ntohl(len);
if (len == 0 || len > params.max_file_size) break;          // 非法 → 断连接
if (type != TYPE_IMAGE && type != TYPE_VIDEO && type != TYPE_LIVE) break;

while (received < len && isStarted()) {
    size_t need = std::min((size_t)(len - received), buf.size());
    recvAll(client_fd, buf.data(), need, "read file chunk", peer);
    fwrite(buf.data(), 1, need, fp);
    received += (uint32_t)need;
    if (received < len) sendPacketAck(client_fd, received, peer);   // 非末块才 ACK
}
if (stat(tmp_path.c_str(), &st) != 0 || (uint64_t)st.st_size != len) break;  // 大小校验
rename(tmp_path.c_str(), final_path.c_str());
updateCacheWithFile(final_path, is_live_packet);            // ← 原工程媒体管理，可替换/删除
sendFinalOk(client_fd, peer);                               // OK\n
```

服务启停（`runtime_coordinator.h`，owner 字符串集合，最后一个持有者释放才停）：

```cpp
MpTransferRuntimeCoordinator::instance().retain("my-project", "My Frame");  // 启动（网络与接收目录就绪后）
MpTransferRuntimeCoordinator::instance().release("my-project");             // 退出时用同一 owner
```

- 启动接口返回 ≠ 已监听成功，要自己检查 `bind/listen` 结果
- 运行中改名可能重启服务 → 避开发送过程
- 文件完成通知：实现 `TcpReceiveListener` + `addListener()`，在 `onFileAdded()` 拿文件信息；回调要快返回，别在回调里做注册/注销/服务启停

## 5. 移植清单

| 原工程依赖 | 处理 |
|---|---|
| `base::Task` / 单例宏 / 日志宏 / `defer`（非标准 C++） | 用现有基础库，或换成项目自己的后台线程 + RAII 清理 |
| POSIX socket / 文件 API | 目标设备工具链直接编（源码面向 Linux） |
| `config.h` 的 `MP_PATH` | 改成自己可写目录，**末尾带 `/`**；代码直接拼文件名不补斜杠 |
| `base::exists/mkdirs/listFiles` | 换自己的目录文件操作，**保留未完成临时文件的清理** |
| `FileParseManager` / 文件缓存 | 只需收文件时可删/替换（`scanPath()`、`updateCacheWithFile()`）——接收和保存成功后再通知项目，不影响长度校验与改名 |

必须保持不变的传输行为：主动广播 UDP 8899 + 监听 TCP 9000（不等小程序搜索）｜保留 `recvAll/sendAll` 的拆包短读短写处理｜非末块累计 ACK + 末块 `OK\n`｜临时文件→校验→改名｜回 `OK` 后继续收同一连接的下一个文件｜停服时唤醒/关闭阻塞 socket 并释放资源。

## 6. 怎么验证（不接真机也能联调）

用附带的 Python 参考接收端在电脑上模拟设备（**只用标准库，Python ≥3.9**）：

```bash
py .\src\python\receiver.py --name PythonFrame --output .\received
# 多网卡/VPN 时指定与手机同网段的地址：
py .\src\python\receiver.py --name PythonFrame --bind <本机IP> --broadcast <子网广播地址> --output .\received --verbose
```

手机与电脑同一局域网 → 在已上线小程序里选 `PythonFrame`（可能显示成 `zkswe:PythonFrame`）→ 发照片/视频 → 文件落在 `received/`。
实测记录（2026-09-24）：该 Python 接收端已用**上线小程序**验证通过，可作为其他项目联调基准。
排障：设备不可见 → 查网卡/广播地址/路由器**客户端隔离**；可见连不上 → 查 TCP 9000 防火墙与端口占用；`--timeout` 只是把 2 s 收发超时放宽，不是整文件限时。

## 7. 协议边界（写需求时别指望这些）

无协议版本号｜无设备唯一 ID（TCP 端口固定 9000）｜无握手协商｜无认证/加密｜无 CRC/HASH 校验｜不支持断点续传｜非法请求直接断连不返回结构化错误｜TCP 空闲超时短（不适合长连接保活）｜适合可信局域网。

## 8. 联调检查清单（12 条）

1. 手机与设备同一路由器且**未开客户端隔离** 2. 小程序能监听 UDP 8899 3. 广播正文以 `zkswe:` 开头 4. 用广播来源 IP 连 TCP 9000 5. 整数一律**大端** 6. 文件名长度按 **UTF-8 字节数** 7. 每个非末块 32 KiB 后读并校验 ACK 8. 末块后读 `OK` 9. 别把设备端 2 s socket 超时当整文件限时 10. 图 `type=1` / 视频 `type=2` 11. 只有完整落盘+本地检查通过才回最终 `OK` 12. 文件完成通知要快返回，别阻塞收下一个文件

---

**相关**：`components/mp_transfer/`（源码 + 指南全文 + Python 参考接收端）｜项目侧落地见 `projects/SmartPanel_HA`（相册上传子页）

检索词：小程序传图 / 小程序传视频 / 相册传输模式 / 局域网传文件 / UDP 8899 广播 / TCP 9000 接收 / zkswe: 前缀 / 32KiB 分块 ACK / OK\n 确认 / mp_transfer / 相框接收端 / 断点续传缺失 / 文件大小校验 / .tmp 改名
