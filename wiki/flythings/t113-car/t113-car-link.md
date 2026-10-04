# KB: T113 车载互联平台（HiCar/CarPlay/AndroidAuto/CarLife 手机互联启动流程 + 蓝牙 + 多媒体 + 倒车）

> 定位：**T113 平台车载 PND 整机方案**：手机互联（CarPlay/Android Auto/CarLife/HiCar/AirPlay/Miracast/AiCast）+ 蓝牙（音乐/电话/通讯录）+ 本地多媒体（音乐/视频/相册）+ 倒车影像 + FM 发射。
> ⚠️ 本页为专项知识：仅当用户提到 **T113 车载 / CarPlay / Android Auto / HiCar / CarLife / 手机互联 / 车机互联 / 车载蓝牙音乐 / 倒车影像 / Miracast / AirPlay 车机** 等关键词时关联，不影响常规 UI/工程需求。

## 🔑 关键词索引
**HiCar 互联启动流程 / CarPlay 手机互联接入 / Android Auto 互联 / CarLife / 车机互联 / 车载 / T113 / 蓝牙音乐 / 蓝牙电话 / 通话弹框 / 倒车影像 / reverse / lylink / 辽原 / 诚谦 / A2DP / HFP / FM 发射 / PND**

## 🏗 架构总览（jni/ 经典工程）
| 模块 | 职责 |
|------|------|
| `link/` + `lylinkapi.h` | 手机互联（辽原 SDK）：CarPlay/Auto/CarLife/HiCar/AirPlay/Miracast，音视频回调 |
| `bt/` | 蓝牙全功能（诚谦/辽原/顾凯三模块可选）：音乐/电话/通讯录/方控 |
| `media/` | 本地多媒体：音乐播放器（ZKMediaPlayer）、视频（ZKVideoView）、相册、h264 硬件播放器 |
| `net/` | WiFi 三模式：AP / STA / P2P |
| `system/` | 倒车检测（uevent）、FM 发射、设置、TVOUT |
| `activity/`+`logic/` | 19 个页面（main/music/video/PhotoAlbum/bt*/calling/lylinkview/reverse/...） |

## 📱 手机互联（lylink 辽原 SDK）
### 启动
```cpp
#include "link/context.h"
lk::add_lylink_callback(_lylink_callback);   // 事件回调
lk::start_lylink();                          // lylinkapi_start(&params)
// 依赖 config.h：LINK_VIEW_WIDTH/HEIGHT(1024x600)、LINK_USB_ENABLE(1=有线开)
// 后台跑 /res/bin/lylinkapp_cn（国内 hicar/carlife）或 lylinkapp_ab（国外 android auto）
```
### 关键事件（LYLINKAPI_EVENT）
- `LYLINK_LINK_ESTABLISH/DISCONN`：建立/断开，para0=类型（WIFICP/USBCP/WIFIAUTO/USBAUTO/USBLIFE/WIFILIFE/USBHICAR/WIFIHICAR/AIRPLAY/MIRACAST/WIFILY/USBLY）
- `LYLINK_PHONE_CONNECT/DISCONN`：手机接入/断开
- `LYLINK_FOREGROUND/BACKGROUND`：进/出前台（进前台 openActivity("lylinkviewActivity")）
- `LYLINK_VIDEO_START/HEAD/DATA/STOP`：视频流（HEAD 是 SPS，用 parseSps 解分辨率；DATA 喂 h264 播放器）
- `LYLINK_AUDIO_START/STOP`：音频流（NODEC 混音模式自动 48k 双声道）
- `LYLINK_CALL_STATE`：通话状态（Hang/Ring/Conn）
- `LYLINK_MEDIA_SONG/ARTIST/ALBUM/PROGRESS/VOLUME`：互联音乐元数据
- `LYLINK_MEDIA_DATA/VR_DATA/TTS_DATA/PHONE_DATA`：NOMIX 模式四类音频
- `LYLINK_AUDIO_DUCK`：声音压低/恢复
- `LYLINK_BT_RFCOMM/BT_GOCSDK`：蓝牙透传（HiCar 用 gocsdk，CarPlay/Auto 用 rfcomm）
### 发送接口
- `lylinkapi_touch(id, mode, x, y)` 触摸；`lylinkapi_key(code, mode)` 按键（Home/Back/电话键/旋钮/方向键）
- `lylinkapi_cmd(LYLINK_CMD)`：切音频/视频源、昼夜模式、断开 AP、AUDIOSOURCE_NATIVE/BT/LYLINK/PHONE
- `lylinkapi_wifi(&params)`：上报 WiFi 状态（AP 开/关/接入、STA、MONITOR）
- `lylinkapi_bt(type, str, len)` / `lylinkapi_rfcomm` / `lylinkapi_gocsdk`：蓝牙透传
- `lylinkapi_record(buf, len)` 录音上行；`lylinkapi_volume(vol)`（-1 静音/101 取消）

### 视频显示（硬件 H264 层，非控件）
```cpp
// h264_player.h（T113 私有 C API）
zk_h264_player_init(w, h, rot, 0);
zk_h264_player_set_pos(x, y, w, h);     // 显示区域
zk_h264_player_set_crop(x, y, w, h);    // 裁剪
zk_h264_player_put_frame(data, size);   // LYLINK_VIDEO_DATA 回调里喂帧
zk_h264_player_show() / hide() / deinit();
```
- 分辨率：LYLINK_VIDEO_HEAD 的 SPS 用 `h264_decode_sps` 解析（misc/parseSps.h）
- AirPlay/Miracast 等比 letterbox 适配（_link_view_show）；HiCar 退出必须 video_stop 回本地模式
- 互联页 onUI_show 延迟 0ms 定时器启动播放，避免与倒车页冲突

### 互联音频（混音模式）
- `zk_audio_multi_player_init(ch, rate, 1024, 4)` 多路播放器；Phone 类型 enable_loopback（回采）
- CarPlay TTS 喂数据不及时 → alsa xrun 卡顿，预填 400ms 静音解决
- 通话用独立 phone_player（采样率/通道不同）

## 🎵 蓝牙（bt/，诚谦 BLINK 模块）
- config.h 选模块：BLINK（诚谦，/dev/BT_serial，500000，blink -c授权码 -T/dev/ttyS3）/ LYGOC（辽原）/ GOCSDK（顾凯）
- 授权：OTP 烧 LINK_LIC(32B)+BT_LIC(220B)；诚谦另有 /data/blink/.btlicense
### API 速查（namespace bt）
```cpp
bt::init();  bt::power_on/off/is_on();
bt::start_scan/stop_scan;  get_scan_dev_by_index;  get_matched_dev_by_index;
bt::connect(addr)/disconnect/start_match/del_match_device/set_auto_connect;
bt::dial(num)/redial/answer/reject/hangup/dial_key_num(num);  // 通话
bt::sound_to_phone/sound_to_car/set_mic_mute/set_auto_answer;
bt::is_calling/is_car_sound/get_call_num/get_call_contact;
bt::download_phone_book/download_call_record/start_download;   // 通讯录/通话记录
bt::get_contact_by_index/get_record_by_index/find_first_contact_by_initial;  // 拼音索引
bt::music_play/pause/next/prev/music_is_playing/get_music_info();  // A2DP 音乐
bt::set_bt_mute(bool);  bt::set_volume(float);  bt::send_data(data,len);
```
- 回调（bt_cb_t）：power/connect/scan/call/download/music/misc_info/raw_data/square_data(方控)
- 诚谦 AT 指令：P1/P0 开关、CC/CD 连接、CW 拨号、CE/CF/CG 接听拒接挂断、PA/PB+PX 下载电话本、MK 音乐信息、MA/MD/ME 播放/下一曲/上一曲、CN/CP 声音切换、BS 扫描方控

### 通话弹框（callingActivity）
- 来电/去电自动弹 callingActivity；显示联系人/号码/通话计时（1s 定时器）
- 按键：接听挂断、静音（set_mic_mute）、声音切换（sound_to_phone/car）、数字键盘（通话中 redial 逐位发 DTMF）、长按删除

## 🎶 本地多媒体（media/）
```cpp
media::music_init();
media::music_play(type, index, msec) / music_play(path, msec);
media::music_pause/resume/seek/stop/is_playing;
media::music_next(isConvert)/prev(isConvert);   // 循环/单曲/随机
media::music_set_play_mode(E_MEDIA_PLAY_MODE_CYCLE/SINGLE/RANDOM);
media::music_set_volume(vol)/music_set_gain(gain);  // gain 用于 TTS 压低
media::music_get_duration/current_position/current_play_file;
media::music_add_play_status_cb(cb);  // STARTED/PAUSE/RESUME/STOP/COMPLETED/ERROR
```
- COMPLETED → 自动 next；ERROR → 3s 定时器 next(true) 跳坏文件
- ID3：`parse_id3_info(path,&info)` 标题/歌手/专辑；`parse_id3_pic(path,"/tmp/music.jpg")` 封面
- 文件扫描：media_context 按 SD/USB 扫描音频/视频/图片；MountMonitor 监听 /mnt/extsd、/mnt/usb1、/mnt/usbotg
- 视频：ZKVideoView + 轮播列表（*_video_list.txt）；相册 PhotoAlbumActivity

## 📻 倒车（reverse）
```cpp
sys::reverse_detect_start();       // mainLogic onUI_init 调用
sys::reverse_add_status_cb(cb);    // ENTER(1) → openActivity("reverseActivity")；EXIT(0) → close
```
- 原理：uevent netlink 监听 `ZKVIDEO_BACK=1/0`；启动先读 sysfs `/sys/devices/platform/soc@3000000/5c01000.tvd0/tvd0_attr/tvd_back_det`
- 等待 init.svc.zklogo 退出才进应用倒车；设置 sys.zkapp.state=running
- reverseLogic：ZKCameraView（setDevPath /dev/video0 AHD 或 /dev/video4 CVBS + setChannel/FormatSize/FrameRate）；无信号连续 2 次显示提示
- 格式表：AHD/TVI 720P/1080P、CVBS PAL/NTSC、DM5885；切换设 ZKCAMERA_DI_ENABLE 环境变量
- 互联播放中倒车：reverse_does_enter_status() 时不打开互联页

### 摄像头格式参数表（AHD/TVI/CVBS/DM5885，T113CarSystem_PND 实测）

| 显示名 | 宽 | 高 | 帧率 | di_enable（奇偶合并） | 备注 |
|--------|-----|-----|------|----------------------|------|
| AHD 720P 25 | 1280 | 720 | 25 | false | |
| AHD 720P 30 | 1280 | 720 | 30 | false | |
| TVI 720P 25 | 1280 | 720 | **24** | false | 标 25 实际 24 |
| TVI 720P 30 | 1280 | 720 | **29** | false | 标 30 实际 29 |
| AHD 1080P 25 | 1920 | 1080 | 25 | false | |
| AHD 1080P 30 | 1920 | 1080 | 30 | false | |
| TVI 1080P 25 | 1920 | 1080 | **24** | false | |
| TVI 1080P 30 | 1920 | 1080 | **29** | false | |
| CVBS PAL 50 | 960 | 576 | 50 | **true** | N/P 制才使能 |
| CVBS NTSC 60 | 960 | 480 | 60 | **true** | |
| DM5885 50 | 720 | 480 | 50 | false | 逐行 |
| DM5885 49 | 720 | 480 | 49 | true | 隔行 |

⚠️ TVI 帧率是 24/29 不是 25/30；切换格式流程：stopPreview → WAIT 停预览 → setFormatSize+setFrameRate → setenv ZKCAMERA_DI_ENABLE → startPreview；无信号回调 E_CAMERA_STATUS_CODE_NO_SIGNAL 连续 2 次才提示。完整代码见 knowledge/t113-car/ahd-camera-format.md。

## 🔊 音频统一管理（audio_context）
- `audio::change_audio_type(type)` 音源互斥：不同模块正在播放者自动 pause，切换后恢复
- `audio::handle_phone(type, phoning)`：通话中 arm 静音 + 暂停其他音源；通话音量单独 CALL_VOL_KEY
- `audio::handle_tts`：media::music_set_gain(0.2) 压低媒体音，播完恢复
- 音量三档：录音 zk_audio_record_set_volume / 系统 zk_audio_player_set_volume / 通话
- ALSA：ALSA_CONFIG_DIR=/res/ui/alsa、ALSA_PLUGIN_DIR=/res/lib；ZKMEDIA_SOUND_UNADJABLE=1
- 音频类型（media_base.h）：本地 MUSIC/VIDEO/RADIO/LINEIN；蓝牙 BT_MUSIC/BT_PHONE(0x10)；互联 LYLINK_MUSIC/PHONE/VR/TTS(0x20)

## 🌐 网络（net/context）
```cpp
net::init();  net::change_mode(E_NET_MODE_AP/WIFI/P2P);  net::get_mode();
```
- AP（CarPlay/Auto/HiCar 无线）：hostapd+udhcpd，密码 88888888，5G 信道 36，conf 代码动态生成
- STA（AirPlay/CarLife）：wpa_supplicant；P2P（Miracast/AiCast）：p2p_supplicant
- 模式联动（mainLogic _change_link_app）：HiCar/CarPlay/Auto→AP+蓝牙开；AirPlay/CarLife→STA；Miracast/AiCast→P2P

## 🖥 主界面/状态栏
- 本地音乐快捷控制 + app 九宫格（SlideWindow）+ 状态栏小图标右对齐自动排布（声音/网络/蓝牙/USB/SD/互联/FM/AUX）
- 6s 定时器查互联授权 lk::query_is_authorized()；HiCar 无线连 10s 后断蓝牙（HICAR_DIS_BT），断互联回连

## ✅ 商务/授权 FAQ（需求方 2026-08-31 确认）
1. **OTP 授权烧录**：出厂烧录 + 后期烧录两份都支持，默认出厂烧录，后期可通过 API 获取授权状态/补烧
2. **有线互联与 adb 冲突**：软件协议层冲突（非硬件限制），LINK_USB_ENABLE=1 时 USB 协议被互联占用
3. **zk_h264_player**：带硬件解码的芯片都支持（非 T113 私有）
4. **蓝牙模块选型**：保留诚谦/辽原/顾凯接口让用户自选，代码调试好的是诚谦（BLINK）模块
5. **lylink 商务**：对接中科世为公司即可拿到 SDK/授权
6. ⚠️ **重要流程**：车载项目客户没拿到基础 SDK 的先联系商务，商务对接后才释放 SDK，之后才提供技术支持

## ⛔ 铁律
1. 互联画面是 **h264 硬件层**，不是控件；UI 控件在其上层
2. **有线互联开启时 USB adb 不可用**（LINK_USB_ENABLE=1），只能网络 adb
3. 互联/蓝牙需 **OTP 授权**（LINK_LIC 32B + BT_LIC 220B）
4. 音频切换必须走 `audio::change_audio_type`，直接播会混响；通话中 arm 静音统一处理
5. CarPlay TTS 需预填静音防 alsa xrun；NODEC 混音自动 48k 双声道
6. 倒车 uevent 依赖内核 ZKVIDEO_BACK + tvd0 sysfs，改平台需同步
7. AirPlay/Miracast 需 letterbox 适配；HiCar 退出必须 video_stop
8. 蓝牙换厂商改 config.h BT_MODULE + AT 指令集
9. i18n 用 .tr + setTextTr；中文联系人拼音索引 utils/chinesetopinyin
10. hostapd/wpa_supplicant conf 避免 Windows \r\n——代码动态生成
