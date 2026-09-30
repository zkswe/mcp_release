# album_upload 模块 —— 平台说明

> 逐平台写清"能不能用、前置条件、实测值、限制、怎么验收"。**没实测的标 `未取证`**，不写"应该可以"。
> **数据来源（如实标注）**：
> - 协议口径（8899/9000/包头/分块/落盘）来自 `components/mp_transfer/`（来源工程现场依据：`F133UhaleAlbum` `39c25c1`）；
> - 本模块的**业务口径**来自来源工程 `projects/SmartPanel_HA` 的「相册上传」页
>   （`src/logic/albumLogic.cc`、`src/mp_transfer/mp_config.h`、`src/storage/ConfigStore.cpp`、`ui/album.json`）；
> - ✅ **本仓 `components/album_upload/` 组件形态已于 2026-09-30 在 Z20 真机（<验收机IP>:5555）上单独跑通并逐条取证**：
>   新建 zkgui 工程（`temp/verify71/album_zkgui`，480×480，qrcode 控件 + 文案）按组件 `example/` 接线，
>   判据 a–d 全过（二维码上屏 + 截图解码 == 兜底 URL ／ TCP 9000 在听 + UDP 广播被 PC 收到 ／ PC 发图落盘 + `onFileAdded` 回调）
>   → **§1.6**（含证据路径、判据命令与还原复核）。下文其余"来源工程"记录仍按原文标注来源。

---

## 0. 汇总

| 平台 | 可用性 | 依据 | 备注 |
|---|---|---|---|
| **Z20** | ✅ **组件形态已在 Z20 真机跑通**（2026-09-30，<验收机IP>:5555，480×480 zkgui 工程）；来源工程 `SmartPanel_HA` 亦在 Z20 面板跑过 | 组件形态：`temp/verify71/album_zkgui` 真机验收（§1.6，4 条判据全过 + 还原复核）；来源工程：`fun build -p Z20` + 推真机（`11_相册上传.png`）；协议侧口径见 `components/mp_transfer/platforms.md` | **微信小程序真机扫码那一环仍无取证**（本机无手机/小程序）；用协议等价 PC 客户端代跑「发图→落盘→回调」（§1.6 判据 d） |
| Z21 / T113 / T113EMMC / V85X / F135 / F136 | ❌ 未取证 | — | 先看 §3 前置条件；⚠️ **Z21 没有 `/mnt/sdnand`**（只有 `/mnt/extsd`、`/mnt/usb1`）→ 落盘目录必须换（该事实为 2026-09-29 Z21 实测记录） |

> 「未取证」的准确含义：**没人按本模块 `example/` 的形态在目标机器上把对应环节跑过一遍**。
> Z20 上已于 2026-09-30 按 `example/` 形态跑过一轮（§1.6）——仅剩「手机微信真扫」一环；其它平台仍为❌。

---

## 1. Z20（口径来源平台）

### 1.1 落盘目录

| 项 | 值 | 来源 |
|---|---|---|
| 目录 | `/mnt/sdnand/album/`（**末尾带 `/`**） | 来源工程 `src/mp_transfer/mp_config.h` 的 `MP_PATH`；与「屏保视频/相册」页扫描目录一致 → 传完回页即时出现 |
| 设备侧实况 | `/mnt/sdnand/` 下原本**没有** `album`（首次运行由接收任务 `mkdirs` 创建） | 2026-09-24 设备实测记录 |
| 写入姿势 | `<name>.tmp` → 校验大小 == 包头声明 → `rename` 正式名 → 回 `OK\n`；失败不改名 | 协议口径（`mp_transfer`） |

⚠️ `MP_PATH` 是**编译期宏**，本组件的 `Config::save_dir` 只是校验/统计口径，两者必须一致（不一致会 WARN，见 README §5）。

### 1.2 端口口径（同机三服务，互不冲突）

| 端口 | 用途 | 来源 |
|---|---|---|
| **8899/udp** | 设备发现广播：`zkswe:<设备名>`，每 ≈2 s，`255.255.255.255:8899`。⚠️ 发送侧是**未 bind 的 UDP socket**（`SO_BROADCAST` + `sendto`）→ `netstat -lun` / `/proc/net/udp` **看不到 8899**，验收判据要用**接收端抓广播**（2026-09-30 实测，见 §1.6 坑 1） | 协议口径 + 2026-09-30 真机 |
| **9000/tcp** | 相册传图**收文件**（`0.0.0.0:9000`；accept 后连接 socket 收发超时 2 s） | 协议口径；来源工程 `Main.cpp` 注释「9000=相册上传」 |
| 8080/tcp | 板内配置网页（HA 服务器扫码配置；`/<口令码>/`） | 来源工程 `WebConfigServer`/`Main.cpp`（`:8080`） |
| 8084/tcp | zkmqtt 状态页 | 同上 |

### 1.3 广播名

- 来源工程：广播名取 prefs `sp_dev_name`（设备名称子页可改），未设时用 `MP_DEVICE_NAME`（来源工程为中文名）；
- 协议侧空名 → `Frame`（`mp_transfer` 的兜底）；本组件 `Config::device_name` 空 → 透传给 mp_transfer 的兜底。

### 1.4 二维码（面板侧，480×480 面板实测口径）

| 项 | 值 | 来源 |
|---|---|---|
| 控件 | `qrcode` 控件（`ZKQRCode`）盒 **128×128**，`padding=10` | 来源工程 `ui/album.json`（qrcode__1） |
| 白卡 | 160×160（`qr_card_160.png`），居中 → 四边各 16 px 白边 = 静区 | 同上 |
| 上屏口径 | **只用 URL 现场生成**（`loadQRCode(链接)`）：控件按整数像素对齐模块 → 锐利；**不铺任何二维码位图**（128px / 37 模块 = 3.46 px/模块，非整数 → 边缘发糊） | 来源工程 `albumLogic.cc` 现场生成那条路（2026-09-30 口径） |
| 内容来源 | ① 配置链接（`sp_qr_url` 语义；我方小程序码解出的链接示例见 `assets/qr_url.txt`） ② 链接为空 → 本机上传地址兜底 `http://<ip>:9000/upload`；**两条路上屏方式完全一样** | 组件 `qrInfo()` + 来源工程 `refreshQrcode()`；细节见 `assets/README.md` |
| 扫描可解性 | ① **相册上传页的二维码（组件形态）**：真机截图 → zxing 解出 `http://<验收机IP>:9000/upload`，与 `qrInfo()` 兜底内容逐字符一致（`ec=H`，码区 ≈159×159 px）；② 板内网页二维码在同款手段上也解出成功 | ① 2026-09-30 组件形态真机记录（§1.6 判据 b，证据 `temp/verify71/shots/verify_a_qr.png`）；② 2026-09-30 真机记录（运行模式页的板内网页码，非相册码） |

### 1.5 真机取证状态（逐项，别含混）

| 项 | 状态 | 依据 |
|---|---|---|
| app 包在 Z20 上编译 + 推设备运行 | ✅ 有（组件形态 + 来源工程） | 组件形态（2026-09-30）：`fun build -p Z20` 通过（`.fun/z20/libzkgui.so`）→ 推 `/tmp/lib/` + `/tmp/ui/`，设备侧 md5 与本地一致（§1.6）；来源工程：`fun build -p Z20` + MCP 推包（lib md5 记录） |
| 相册页上屏（状态卡/二维码/计数） | ✅ 有（组件形态另有本次独立截图） | 本次组件形态：qrcode 控件渲染 + 文案上屏，截图 `temp/verify71/shots/verify_a_qr.png`（`QR[fallback]: http://<验收机IP>:9000/upload`、`photos 4 / videos 3`）；来源工程：整机说明书 `manual_shots/11_相册上传.png` |
| 面板侧二维码**能被手机扫到** | 🟡 **等价判据已过；手机实际扫仍未做** | 本次（2026-09-30）：真机截图 → zxing 解出 URL == `qrInfo().content`（§1.6 判据 b，相册码本身）；「手机微信实际扫到」仍无取证（本机无手机/小程序，来源工程说明书该图同样记 `图待补`） |
| **扫码 → 传图 → 落盘 `/mnt/sdnand/album/` → 回调刷新** 端到端 | 🟡 **协议等价客户端已端到端取证（2026-09-30 组件形态）；微信小程序扫码那一环未取证** | 本次：PC 侧 `projects/SmartPanel_HA/tools/mp_send_test.py`（与 `mp_transfer` 同协议的假小程序）发 205 B 图 → 设备 `/mnt/sdnand/album/test_upload_71.png` 落盘（md5 `9847d78feaf1d39db7070c7306000700` 与 PC 侧一致、无 `.tmp` 残留）、`logcat -d -s zkgui` 出现 `album: onFileAdded path=… size=205 kind=0`、页面计数 `photos 4 → 5`（§1.6 判据 d）；**手机微信扫码未做** |
| 落盘文件命名 | 组件形态 = **原名**（2026-09-30 实测：`test_upload_71.png` 原样落盘，无改名）；来源工程口径：小程序原名不友好 → 改名 `小程序_YYMMDD_HHMMSS.<ext>`，同秒加 `_1/_2` | 本次真机 `ls`（§1.6 判据 d）；来源工程 `tcp_receive.cpp` |
| 传输过程中的耗时/吞吐 | ⚠️ 仍无实测数字（本次只发 205 B 小图：单块 + 末块 `OK`，未计时、未测大文件） | 本次真机（§1.6 判据 d） |

⚠️ 引用本文时请连带引用上表：**"Z20 跑通了"= 组件形态「二维码上屏 → 发图 → 落盘 → 回调」四条判据全过（§1.6）；"手机微信扫码"这一环仍未取证**。

### 1.6 组件形态真机验收记录（2026-09-30，Z20 / <验收机IP>:5555）

**工程**：`temp/verify71/album_zkgui`（`flythings_create_project` Z20 480×480 → `fui pack`，10 个控件；
依赖 `easyui ^2.2.0` / `log 0.0.0` / `base-utility ^10.8.5`；组件 `include/zk/zk_album.h` + `src/zk_album.cpp`
+ `mp_transfer` 的 4 源 1 头 + `system/transfer_type_and_data.h` 拷进 `src/`）。

**页面接线**（= 组件口径，`example/flythings_wiring.cc` 的同一条路）：
`configure(save_dir=/mnt/sdnand/album/, device_name=verify71, start_on_configure=false)` →
`setQrUrl(StoragePreferences::getString("sp_qr_url", ""))` → `qrInfo().content` 交给 `ZKQRCode::loadQRCode`
→ 1 s 定时器消费回调标志（回调只置标志，不动控件）。

| 判据 | 结果 | 原始证据 |
|---|---|---|
| a) 二维码**渲染上屏**（非空白、非位图） | ✅ | `temp/verify71/shots/verify_a_qr.png`（480×480；qrcode 盒 180×180 白底、`padding=10`） |
| b) 从截图**解出二维码内容 == 期望** | ✅ `payload = 'http://<验收机IP>:9000/upload'`，`ec=H`，`--expect` 核对 OK | `python components/album_upload/scripts/decode_qr_url.py --src temp/verify71/shots/verify_a_qr.png --expect http://<验收机IP>:9000/upload` → `OK: 与 --expect 一致` |
| c) **TCP 9000 在听** + **UDP 8899 广播** | ✅ TCP：`netstat -ltn` → `0.0.0.0:9000 LISTEN`（`/proc/net/tcp` 行 `:2328` 同证）；UDP：同网段 PC 收到 `zkswe:verify71` | `temp/verify71/dev_ports.sh` 输出；`mp_send_test.py --discover` → `发现设备: <验收机IP>  名称=verify71` |
| d) PC 发图 → **落盘 + 组件回调** | ✅ 205 B 图落盘（md5 与 PC 侧一致、无 `.tmp` 残留）；`logcat -d -s zkgui`：`album: onFileAdded path=/mnt/sdnand/album/test_upload_71.png name=test_upload_71.png size=205 kind=0`、`album: peer connected/disconnected`；页面计数 `photos 4 → 5` | `temp/verify71/logcat_after_upload.txt`；截图 `temp/verify71/shots/verify_d_after_upload.png` |

**组件日志钩子**（`setLogHook`）同一次运行留证（app 模式 stdout 是 `/dev/null`，不接钩子看不到）：
`album[D]: configure: dir=/mnt/sdnand/album/ dev='verify71' port=9000 qr_url=(空→兜底本机地址)`、
`album[D]: start: 广播 UDP 8899 (zkswe:verify71) + 监听 TCP 9000(单文件上限 524288000 B)，期望落盘 /mnt/sdnand/album/`、
`album[W]: qr_url 为空 → 二维码退回本机上传地址兜底 http://<验收机IP>:9000/upload`。

**还原复核**（验收机是别人的调试机：改前是「/tmp 劫持态」`startupLibPath=/tmp/lib/libzkgui.so`）：
改前全备份 → 验收 → 原样推回 → `setprop ctl.restart zkswe` →
`/tmp/lib/libzkgui.so` md5 `f4c1a78187ffbd90dd325a7c959d2c73`、`/tmp/EasyUI.cfg` md5 `df024faf1e3f988964bb23b5b1695f2d`、
**`/tmp/ui` 131/131 文件 md5 与备份逐一相同**、`/data/preferences.json` md5 未变（`sp_relay_state` = 0，三路继电器全关）、
`sys.zkapp.state=running`、截图与备份时同页（仅时钟走字）。
证据：`temp/verify71/{restore_1.json,restore_verify.json,shots/restored_after.png,backup_before/}`。

**本次新确认的口径/坑**（只记录，未改代码/文档结论以外的东西）：
1. **UDP 8899 不能用 `netstat` 证明**：广播是「未 bind 的 UDP socket + `SO_BROADCAST` + `sendto` 到
   `255.255.255.255:8899`」→ `netstat -lun` 与 `/proc/net/udp` 里**都没有 8899**（TCP 侧 9000 可见）。
   判据必须换成**接收端抓广播**（同网段 PC `mp_send_test.py --discover`）。已同步进 §1.2 表。
2. **配置分支未上机**：设备 prefs 里没有 `sp_qr_url` → 只走了兜底分支。两条分支上屏是同一个
   `loadQRCode(content)` 调用（组件 `qrInfo()` 只有一个出口），但按「不冒充实测」口径记为**未取证**。
3. `fun launch` 在本机 6 台设备在线时**硬失败**（fun 自带 Go adb 发旧式 `host:transport <serial>`，
   见 `knowledge/devflow/cli-fun-toolchain.md` §7）；文档里的垫片方案要 kill/重启共享 adb server（会影响
   并行的其它设备会话），故本次部署改用 **MCP 自己的 adb 层**（`adb_tools.push` / `restart_app`，全部带 `-s`）
   复刻 `fun launch` 的部署约定：`/tmp/ui/*.ftu` + `/tmp/lib/libzkgui.so` + `/tmp/EasyUI.cfg`（`resPath` 指
   `/tmp/ui/`）+ `setprop ctl.restart zkswe`。
4. 落盘目录 `/mnt/sdnand/album/` 在验收机上**已有 7 个旧文件**（4 图 3 视频，他人验收残留）→ 组件计数
   直接把它们算进去（`photos 4 / videos 3`），即 `refresh()` 是「扫目录」不是「本次会话」。属预期行为，
   但写验收用例时注意基线。

---

## 2. 其它平台

| 平台 | 状态 | 需要先确认的事 |
|---|---|---|
| Z21 | ❌ 未取证 | **没有 `/mnt/sdnand`**（只有 `/mnt/extsd`、`/mnt/usb1`）→ `MP_PATH` 与 `Config::save_dir` 都要换；`base-utility`/`easyui` 版本以工程为准 |
| T113 / T113EMMC | ❌ 未取证 | 外置卡路径与可写分区要实测；`fun install` 后确认 mp_transfer 能编（`base::Task`） |
| V85X / F135 / F136 | ❌ 未取证 | 同上；F135/F136 板子登录需口令（与本模块无关，但推包调试会撞到） |

---

## 3. 前置条件（移植到新平台/新工程）

1. **可写落盘目录**：`Config::save_dir` 与 mp_transfer 的 `MP_PATH` 指向**同一**已挂载可写目录，**末尾带 `/`**；
   `configure()` 会当场 `mkdir` + 检查可写，不可写直接报「落盘目录不可写」（不要指望运行期兜底）。
2. **mp_transfer 能编**：需要 `base::Task`（包 `base-utility`）；没有就照 `components/mp_transfer/README.md` 换成项目自己的线程。
3. **局域网条件**：手机与面板**同一网段**，路由器**未开 AP 隔离/客户端隔离**（否则 UDP 广播到不了小程序）。
4. **可信网络**：无认证/加密/CRC/断点续传，非法请求直接断连 → 只适合可信局域网。
5. **落盘空间**：单文件上限 500 MiB、分块 32 KiB —— 传视频前先确认分区剩余空间。
6. **端口可用**：9000/tcp 未被占用（同机还有 8080 板内网页 / 8084 zkmqtt 状态页）。
7. **接线层依赖**：`easyui`（`ZKQRCode`、`StoragePreferences`）、`log`。
   二维码现场生成、不下载位图 → **不需要 `curl-cxx`**（`Manifest.xml`）。**改完 Manifest 必须重跑 `fun install`**。

---

## 4. 已知限制（平台维度）

- **文件名**：UTF-8 1..256 字节，禁 `..` `/` `\`；不唯一会覆盖（协议不做重名保护）。
- **只收不解析**：不分类型给宽高/时长；扩展名认得 `.jpg/.jpeg/.png/.bmp/.gif/.webp` 与
  `.mp4/.avi/.mkv/.mov/.3gp/.ts/.flv`，其它算 `FILE_OTHER`（不影响落盘，只影响计数）。
- **TCP 空闲 2 s 超时**：不是整文件限时；文件之间长时间无数据会断连（不适合保活）。
- **广播不可跨网段/VLAN**（无 mDNS、无固定端口探测）。
- **设备上缺常用工具**：来源工程记录设备 busybox 裁剪过（**没有 `wc`**）→ 计数一律 `opendir/readdir`，
  别在代码里 `system("ls | wc -l")`（本组件就是这么实现的）。
- **无设备侧实测的性能数字**（吞吐/耗时）——本仓不编造。

---

## 5. 怎么验收（三层，逐层加真）

| 层 | 做法 | 期望 |
|---|---|---|
| ① PC 侧（不接设备） | 组件本体：`g++ -std=c++11 -fsyntax-only -Wall -Wextra`（桩头模拟 mp_transfer 接口，命令见 `README.md` §7）；链路侧：`components/mp_transfer/src/python/receiver.py` 用**上线小程序**发图 | 编译 0 warning；PC 收端文件长度与发送端一致、逐块 ACK、末块 `OK` |
| ② 设备侧（不上屏） | 拷 mp_transfer + 本组件 → `fun build` → 推设备 → 看日志：广播启动、监听 9000、`start: ...期望落盘 ...` | 小程序能发现设备名；`onFileAdded` 被触发；落盘目录出现文件、无残留 `.tmp`。**2026-09-30 已有组件形态实跑记录（§1.6 判据 c/d）** |
| ③ 端到端 | 面板上屏二维码 → 手机微信扫码 → 小程序选图 → 传 | 文件出现在 `save_dir`，大小 == 协议声明；页面计数/缩略图刷新；**截图 + `ls` 双证**。2026-09-30：二维码上屏 + 截图解码 + 协议等价 PC 客户端发图（截图 + `ls` + `logcat` 三证）已过（§1.6）；**仅剩「手机微信真扫」这一环未取证** |

排障顺序：设备不可见 → 网段/客户端隔离/相册模式是否开启；可见连不上 → 9000 占用与防火墙；
传完没文件 → `save_dir` vs `MP_PATH`、分区挂载、文件名合法性（WARN 日志里有原话）。

---

## 6. 未取证清单（后续补测就照这张表填）

1. 微信扫码传图**端到端**（面板 Z20，手机 + 上线小程序）—— 🟡 2026-09-30 已用**协议等价 PC 客户端**代跑「发图 → 落盘 → 回调 → 计数刷新」（§1.6 判据 d）；**手机微信真扫仍缺**；
2. 相册**二维码**在真机上被手机扫到的实证 —— ✅ 2026-09-30 等价判据已过（真机截图 → zxing 解出 == `qrInfo().content`，§1.6 判据 b）；「手机实际扫到」仍缺；
3. 面板侧链接码与来源工程 `kQrUrlDefault` 的一致性（本仓只校了“解出的链接 == 文档里写的链接”）—— ⚠️ 仍缺（本次走的是**兜底**分支，未配 `sp_qr_url`）；
4. 传输吞吐/耗时（不同大小文件）、`.tmp` 残留清理的实测 —— ⚠️ 仍缺（本次仅 205 B 小图；`.tmp` 无残留已顺带验证）；
5. Z21/T113/V85X/F135/F136 的 mp_transfer 编译与落盘目录（Z21 已知无 `/mnt/sdnand`）—— ⚠️ 仍缺。

---

**相关**：`README.md`（API/依赖/限制/排错）｜`Manifest.xml`（依赖声明）｜`assets/README.md`（二维码 URL 口径）｜
`example/README.md`（三步接起来）｜`../mp_transfer/platforms.md`（协议侧平台事实与 PC 参考接收端）
