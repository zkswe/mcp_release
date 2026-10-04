---
id: devflow-device-screenshot
title: 真机抓屏（device_screenshot）实现要点与判据
category: devflow
status: review
confidence: manual
verified_at: 2026-09-29
stale_days: 180
origin: total
source: 2026-09-29 front-matter 迁移（P1：先显式登记"待补可执行判据"）
needs_evidence: true
platforms: [Z20, Z21]
tags: [fb0 参数, 双缓冲 pan, 视频层抓不到帧, 拼墙抓不到画面, 设备没有 screencap, toast 抓不到, 瞬时元素抓不到, 实现要点与判据在这里]
evidence: []
---
# 真机抓屏（device_screenshot）实现要点与判据

> 检索导引：抓真机截图 / 抓屏 / 屏幕没图 / 抓到的画面是旧的 / 颜色红蓝互换 / 文字侧躺倒立 /
> 取图角度 rotateScreen / fb0 参数 / 双缓冲 pan / **vdec 通道 vdec_chn / 视频层抓不到帧 / 拼墙抓不到画面**/
> 设备没有 screencap / toast 抓不到 / 瞬时元素抓不到 /
> setInvalid 是禁用不是重绘 / 强制重绘 invalidate 时命中。
> 用途：`flythings_device_screenshot` 的完整口径（该工具 docstring 只保留要点，实现要点与判据在这里）。

## 1. 什么时候用

要确认设备上**实际显示成什么样**：布局对不对、图标有没有锯齿、切图对不对、颜色/文字是否正常、
改完要不要验收、用户说「我屏幕上看到的是……」而你手上没有截图。

三段式验收的第二步：预览（秒级）→ **本工具抓真机截图（像素真相）**→ `flythings_ui_visual(action="diff")` 比对。

## 2. 默认用法（默认参数就够了）

| 需求 | 做法 |
|------|------|
| 抓一张 | `flythings_device_screenshot()` → `screenshots/device_600x1600_*.png` |
| 省 token | `scale=0.5`（长宽各半）或 `fmt='jpg', quality=85` |
| 多设备 | `device='<设备IP>:5555'`（先 `adb connect <IP>:5555`） |
| 分析画面 | 把返回的 `path` 交给看图能力；**不要把 raw/文件本身丢给模型**|
| 改前改后验收 | 改前抓一张存好，改后再抓一张 → `flythings_ui_visual(action="diff", image_a=改前, image_b=改后)` 0 token 出差异清单 |
| 方向不对 | **不用自己试角度**：缺省 `rotate='auto'` 会读项目工程 `EasyUI.cfg` 的 `rotateScreen` 自动转正（返回值 `rotateSource` 可自证）；触摸角度看 `screenInfo.rotateTouch`（可与显示不同） |
| 只要应用画面（去黑边） | `crop='auto'` 按 disp 图层 frame 裁出逻辑分辨率区域（仅存在唯一非全屏图层时生效，否则不裁并在 `crop` 字段说明） |

## 3. 实现要点与硬约束

### 3.1 取流链路

设备 rootfs 是裁剪版：**没有 `screencap` / `dd` / `head`**，`adb exec-out` 也不通
（patched adbd 无 shell v2）。唯一可靠链路：

```
设备侧：busybox dd if=<fb> bs=<stride> skip=<pan.y> count=<height> | busybox gzip -1 > /tmp/x
主机侧：adb pull
```

- 裸 raw 7.68MB 经 WiFi pull 要 4 分钟+；gzip 后只剩 ~37KB、0.3 秒（画面平坦色块多，压缩比极高）
- 设备上没有 busybox 时自动退化 `cat <fb> > /tmp/x` + pull（慢，返回里会提示先 push 一个 busybox）

### 3.2 fb 参数

一律问 sysfs：

| 文件 | 内容 |
|------|------|
| `modes` | 可见分辨率（如 `U:600x1600p-50`） |
| `virtual_size` | 可能是可见高的 2 倍（OVERALLOC 双缓冲） |
| `stride` | 行字节数 |
| `bits_per_pixel` | 位深 |

⚠️ **可见高 ≠ 文件行数**，必须按 stride 逐行取，否则下半张图是脏数据。

### 3.3 双缓冲页翻转（最容易抓错）

读 `/sys/class/graphics/fb0/pan`（如 `"0,1600"` = 当前显示 yoffset=1600），
抓图必须 `skip=<yoffset>`；否则抓到的是上一帧——**旧画面仍可能是完整 UI，肉眼很难发现抓错了**。

`offset_y=-1` 会自动读 pan，并在抓图后二次确认 pan 未变（翻了就重抓一次）。

### 3.3-1 ⚠ 双缓冲/pan 偏移 → 抓到上一帧（平台通用，2026-09-16 实测）

**症状**：应用**已经重绘**（日志有、触摸回调有、状态确实变了），抓到的图却是**上一帧**——
点了按钮图不变、翻页后画面不更新，看起来像「改动没生效」。

**判据（一条命令级的硬指标）**：`flythings_device_screenshot` 返回的
`screenInfo.virtualHeight ≈ 2 × height` **且 `pan` 非 0**→ fb0 是**双缓冲**（写 A 显示 B）。
实测：Z21 = 1024x600 / virtualHeight 1200；F133 = 800x1280 / virtualHeight 2560。
⇒ **凡 virtualHeight = 2×height 的平台都可能中招**，不是某一块板子的怪癖。

**对策（按代价从低到高）**：
1. 抓屏**前后各读一次 `fb0/pan`**（或连抓两次比 md5）：不一致就说明刚好翻页，**重抓**；
2. 用触摸注入 `touch long <x> <y> 250` 触发一次重绘后再抓；
3. ⛔ **规范：`setInvalid()` 是"禁用"，不是"重绘"**：
   `ZKBase::setInvalid(bool)` = 把控件置为**无效状态（禁用）**（`ZK_CONTROL_STATUS_INVALID`）——
调了它控件当场**点不动**（可交互控件上发作），现象是「注入坏了 / 界面点哪都没反应」，能白查半天
   （案例里 13 个导航键被这样禁掉）。**内容变更（`setText` / `setBackgroundPic`）引擎本来就会重绘该控件**，
通常什么都不用做；真要手动重绘用 `ZKBase::invalidate()`，但它**在部分设备的旧 `libeasyui.so` 上未导出**
   （实测 `undefined symbol ...invalidate...` → 整屏黑），用前先确认。详见 `knowledge/uicontrols/custom-view-refresh.md`；
4. 像素 diff 验收（`flythings_ui_visual(action="diff")`）之前**先确认「手里这张是新帧」**，
否则会把 stale frame 当「改动没生效」，白查一轮应用逻辑。

### 3.3-2 ⚠ 抓帧次数：**瞬态层单抓、静态页/弹窗双抓**（2026-09-17 实测）

3.3-1 的「抓两次取第二张」（连抓两帧比 md5，不一致就重抓）只适用于**静态页面 / 弹窗**这类
抓的时候还在的画面。**碰到瞬态层（toast 一类，设计寿命约 2s）会把它吃掉**：两次抓帧之间的 adb 往返 + 落盘（实测 ≈0.4s 量级）还没来得及抓第二张，弹层已经到点自动关了 →
得到「toast 没弹出来」的**假 FAIL**（案例实测：slider 页 toast 一批全挂在这上面，改单抓后全过）。

| 对象 | 抓帧次数 | 为什么 |
|------|----------|--------|
| 静态页面 / 模态弹窗 / 面板 | **双抓取第二张**（或前后比 `pan`） | 治双缓冲滞后（3.3-1） |
| 瞬态层：toast / 按压态 / 滚动条 / 逐帧动画中的某一帧 | **单次抓帧**，且**与触发命令放同一次调用**| 寿命短，第二抓必然落空 |
| 拿不准 | 先按**单抓 + 同调用**做一次，再补双抓 | 保命优先：别把「有」判成「无」 |

判据：瞬态层的验收要**先证明触发了**（日志/像素同时留痕），再谈画面细节；
只靠「抓两次取第二张」会在寿命 < 抓帧间隔的对象上系统性误判。

**边界（重要）**：
- 这是**抓图/验收侧的问题，不是应用 bug**，**不要为此改应用逻辑**（不要加无意义的重绘 hack）；
- `offset_y=-1`（缺省）已按 pan 取值 + 抓后二次确认，但设备在抓图期间翻页仍可能抓到旧帧；
返回体里的 `screenInfo.pan` / `offsetY` 就是给你自证的；
- `layer='video'`（SigmaStar）走的是 vdec 输出口，**与 fb0 双缓冲无关**，不适用本条；
多路/拼墙要指定通道 → 见 §4.1.1 `vdec_chn`。

### 3.4 通道序

32bpp 内存序是 **BGRA**（小端 ARGB8888）。工具按 alpha 字节位置自动判通道序
（末字节 ≈0xFF → BGRA）。

- 若颜色红蓝互换，传 `pixel='rgba'` 重抓
- 其他可选：`bgra` / `rgba` / `argb` / `abgr` / `rgb565` / `bgr565` / `rgb888` / `bgr888`

### 3.5 其他匹配参数

`width` / `height` 可覆盖（sysfs 读不到时）、`flip='v|h|both'`、`rotate='auto'|0|90|180|270`、
`crop=''|'auto'|'x,y,w,h'`、`offset_y` 手动指定。

### 3.6 方向/角度只认项目工程配置（2026-09-10 定规）

旋转/取图角度口径（`rotateScreen` / `rotateTouch` 字段、实测角度对应、生效判据）
→ 见 `knowledge/devflow/package-properties-easyui-cfg.md` §9。

## 4. 返回字段

```json
{"success": true, "path": "...", "width": 600, "height": 1600, "format": "png",
 "sizeBytes": 12345, "device": "...", "method": "busybox-cat-gzip",
 "screenInfo": {"width": 600, "height": 1600, "virtualHeight": 3200, "bpp": 32,
                "stride": 2400, "modes": "...", "offsetY": 1600, "pan": "0,1600",
                "rotate": 0, "rotateScreen": 270, "rotateTouch": 270},
 "uiLayer": "...", "pixelOrder": "bgra", "rotateDeg": 270, "rotateSource": "project-cfg",
 "crop": "", "readHint": ""}
```

## 4.1 视频层抓帧（仅 SigmaStar：Z20/Z21，`layer='video'`）

> 背景：Z20/Z21 上**视频是 MI 硬件图层**，`/dev/fb0` 只是 UI(OSD) 层 —— 屏上在放视频时，
> 拓 fb0 得到的是黑的（Z20 实测 800x1280 只得 4KB 全黑，仅右下角一个 Wi-Fi 图标）。
> 2026-09-13：「你如果可以把视频图层抓出来更好了，这样子就可以更好确认问题。」

**怎么做**：`flythings_device_screenshot(layer='video')` → 内部用 `zkshot`（`tools/zkshot/`，成品在 `bin_tools/{z20,z21}/zkshot`）
从 **vdec 输出口**取一帧 → 按帧格式解码落盘：

```
MI_SYS_Init()
MI_SYS_SetChnOutputPortDepth(vdec chn<N> port0, userDepth=1, bufQDepth=2)
MI_SYS_ChnOutputPortGetBuf(&port, &info, &h)     // 取一帧
MI_SYS_Mmap(info.stFrameData.phyAddr[0], size)   // 物理地址映射
fwrite → Munmap → PutBuf
```

#### 4.1.1 通道号 `vdec_chn`（多路/拼墙必读 —— 2026-09-27 补齐）

**症状**：`layer='video'` 抓不到帧（`zkshot` 取帧失败 / 空帧），但屏上确实在播视频。
交付整机说明书时实测：多屏拼接（`SmartPanel_HA`）的**拼墙播放器在 vdec chn 1**，
而工具早期把通道**写死成 chn 0**→ 只能手工 `zkshot <out.raw> vdec 1 0` 兜。

| vdec 通道 | 谁在用 | 解码方式 |
|-----------|--------|----------|
| **chn 0**| 工具**默认值**（单路/历史口径） | — |
| **chn 1**| **多屏拼接拼墙播放器**（SmartPanel_HA，mi-module `h264_player` 移植版） | 硬件 vdec chn1 |

> ⚠️ **别把「屏保 = chn 0」当真**（早先的说法）：Z20 屏保 `zkmedia`/`ssdvideoplayer` 是 **FFmpeg 软解**、
> 全设备扫描确认它**不建 MI VDEC 通道**（2026-09-27 反汇编实证：`workspace/references/kb/z20-mi-vdec-channel-attrs.md` §7）——
> 所以 chn 0 抽不到帧**不一定是工具问题**；「chn 0」只是默认取帧口径。

**怎么用**：`vdec_chn`（int，**默认 0**，向后兼容）仅 `layer='video'` 生效，
等价命令行 = `zkshot <out.raw> vdec <chn> 0`（`tools/zkshot` 的形参是 `[vdec|disp] [chn] [port]`）：

```
flythings_device_screenshot(layer='video', vdec_chn=1)                  # 拼墙
flythings_device_screenshot(layer='video', advanced='{"vdec_chn":1}')  # 或走 advanced
python ui_tools/device_screenshot.py --layer video --vdec-chn 1         # CLI
```

**失败必须可诊断**（不要静默返回空）：取帧失败 / 空帧 / pull 失败 / 解码失败这四条路径的返回体里都带
`vdecChn`（实际用的通道号）、`device`、`zkshotCmd`（还原成命令行，便于肉眼复现）、`hint`（chn 0/1 各是谁、怎么换），
`warnings[]` 里带 `zkshot` 的原始输出（含它自己打的 `SetChnOutputPortDepth(chn=N ...)` 与 `GetBuf failed: 0x...`）。

**排查顺序**：① 确认 `vdecChn` 就是你期望那路 → ② 换 `vdec_chn` 重试 →
③ 还是空帧就查该通道上是否真有播放器（`/proc/mi_modules/mi_vdec`；`mi_disp0` 里能看到哪个端口被 `mi_vdec` 绑定）→
④ 才怀疑 `zkshot` 本身（注意 `zkshot` 跨进程拿别人通道会 `GetBuf failed 0xa009200d` 一类错误；
`/data/zkshot` 不能当通用 vdec 探针）。

返回体带 `frame{width,height,fmt,fmtName,stride}`，可直接核对（Z20 实测 `384x448 fmt=11 → yuv420sp(NV12)`，
尺寸与 `384*448*1.5=258048` 对得上）。

**三条硬约束**
1. `MI_DISP_GetScreenFrame()` **不能用**：那是给“拥有显示层的进程”的，**跨进程只回空帧**
   （layer 0/1 都试过、补 `MI_SYS_Init` 也没用）→ 必须从 **vdec 输出口**取。
2. **按设备实际符号写**：设备 `libmi_sys.so` 只导出**非 Pa 版**（`MI_SYS_ChnOutputPortGetBuf/PutBuf`）；
用 `...GetBufPa`（IDE 包里的库有、设备没）会 `symbol lookup error`。
上手先看一眼：`strings /lib/libmi_sys.so | grep MI_SYS_`。
3. **帧格式不是固定的**：`fmt` 值→格式见 `E_MI_SYS_PixelFormat_e`（11=NV12、0=YUYV422、1/2/3=ARGB/ABGR/BGRA8888、4=RGB565）；
解码器遇到不支持的 fmt 会**明确报错**（不静默当黑屏）。

**边界**
- 视频层分辨率**独立于屏**（Z20 视频 384x448，屏 800x1280）；要“叠回 UI”得读 mi_disp 的 input port attr 拿屏上位置
  （`cat /proc/mi_modules/mi_disp/mi_disp0` 能看到端口被 `mi_vdec` 绑定）—— 当前工具只给**视频帧本身**，不合成。
- **V85X 不适用**（Allwinner disp 分层，视频层要经 `/dev/disp` ioctl 拿）；Z21 **无硬件解码器**（软解 ffmpeg），需求方定：暂不处理。

## 4.2 实测记录（2026-09-20 M6）

**`/tmp` 满 → 抓屏报「raw 数据不足…实际 0 字节」**
抓屏要在设备侧写 `/tmp/.fyshot.bin`；F133(1.182) 的 `/tmp` 是 **123MB tmpfs**，一旦被
（推前备份目录、测试视频素材等）塞满，`dd | gzip` 就产 0 字节，报错文案是
「解码失败: raw 数据不足：需要 4096000 字节…实际 0 字节」，**不是**截屏逻辑坏了。
`df -h /tmp` 看一眼即可确认；腾空间优先删「同盘备份副本」（备份应 tar 回主机或放 `/data`）。
## 4.3 截图可不可信：`staleFrame` 判定（应用不渲染时 fb 上留着上一帧）

**误诊元凶**：应用没在画的时候，fb 上还是上一帧画面 —— 看起来像正常运行，据此下结论就会误判。
判据都在 `device_probes`（只读、不碰 fb 数据）：

| verdict | 依据 | 怎么处置 |
|---|---|---|
| `stale-no-gui` | `ps` 里没有 GUI 进程（`zkgui`/`zkswe`） | **画面不可信**：仍是上一帧 |
| `gui-blocked` | GUI 进程存在但状态是 **D** | 大概率不渲染 |
| `display-idle` | 显示中断计数两次一致 | 可能是静态界面，也可能没在画 → 做个已知动作再抓一张对比 |
| `live` | 显示中断计数在涨 | 通路在刷（**不等于**应用在画） |

`flythings_device_screenshot` 的返回体带 `staleFrame`；可疑时同时进 `warnings[]`。

## 4.4 launch 活性：`launched=true` 只代表「推送成功」，不代表界面起来了

`fun launch` 返回 0 = 推送完成。**黑屏事件的形态就是「推送成功 + 面板黑着」却回了 `launched=true`。**
所以 v0.27.179 起 `flythings_build_ui_flow` 会复核 logcat 证据 + GUI 进程活性
（`device_probes.launch_evidence` / `_launch_liveness`）：

- **强证据**：`registerActivity name: mainActivity OK!`（ftu/Activity 注册成功，实测框架会打）、
  `onUI_show` / `onUI_init`（框架**默认不打**，应用自己 LOGD 才有）
- **弱证据**：`initEasyUICfg ok!`、`register control: zk_`（框架起来了，不等于界面出来了）
- ⚠️ **必须等一会儿再读**：`fun launch` 刚返回时 logcat 里还没有 activity 注册（实测要再过数秒），
  所以判据是**轮询 6 秒**，不是读一次就下结论
- 判定：强证据 → `confirmed`；弱证据 + GUI 进程活着 → `confirmed`；
  进程不在/卡 D → **`suspicious` ⇒ 不报 `launched=true`** 并给告警；都拿不到 → `unknown` + 提示抓屏复核

## 5. 相关

- 设备缺命令（grep/sed/dd…）→ 用 busybox → `knowledge/devflow/busybox-debug-library.md`
- 像素级读图/省 token 阶梯、1 字符=1 像素分类图、文字暗带检测 → `knowledge/devflow/pixel-analysis-ai.md`
- 触摸注入与抓帧时机（注入 + 抓帧同一次 adb 调用、多档 sleep 差分）→ `knowledge/devflow/touch-inject-autotest.md`
- 屏幕方向（rotateScreen / rotateTouch 权威来源）→ `knowledge/devflow/package-properties-easyui-cfg.md` §9
