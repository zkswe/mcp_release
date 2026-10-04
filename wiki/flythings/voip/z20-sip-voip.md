# KB: Z20 SIP 对讲方案（voip 组件包初始化注册/呼叫 + Poco-http 内置页面服务）

> 定位：**Z20 平台 voip 组件包（SIP 对讲）初始化注册 + 呼叫接听 + 内置 Web 管理页**完整方案（楼宇对讲/门禁/安防类产品）。
> 架构：`voip` 组件包（SIP 协议栈：注册/呼叫/视频/DTMF/IM，双账号 + 备用服务器）+ `Poco-http` 内置 HTTP 服务（设备跑 Web 管理页，浏览器直连设备 IP 配置）。
> ⚠️ 本页为专项知识：仅当用户提到 **SIP 对讲 / voip 组件 / voip 包 / 楼宇对讲 / 门禁呼叫 / 内置 Web 管理页 / HTTP 页面服务** 等关键词时关联，不影响常规 UI/工程需求。

> 🔑 关键词索引：**voip / SIP / 对讲 / 呼叫 / 接听 / 挂断 / 注册 / 初始化 / 双账号 / 广播 / DTMF / 门禁 / 楼宇对讲 / 室内机 / 门口机 / Poco-http / Web 管理页 / HTTP 服务器 / AdminService / GetTelephone / MakeCall / Answer / Hangup**

## 📦 依赖（Manifest.xml）
```xml
<manifest platform="Z20">
  <dependencies>
    <package id="voip" version="4.4.1-hzxTest" accessKey="..." />  <!-- SIP 组件包（私有 accessKey） -->
    <package id="Poco-http" version="0.0.6"/>
    <package id="Poco" version="1.9.4"/>
    <package id="base-json" version="2.6.1" />
    <package id="audio-utility" version="3.0.10"/>
    <package id="watchdog" version="0.0.3"/>
    <package id="zip" version="1.10.1" />
    <package id="av" version="1.1.0-test2" />
  </dependencies>
</manifest>
```
- `voip` = SIP 组件包（核心头 `telephone.h` / `zkaudio.h`），accessKey 私有包
- `Poco-http` + `Poco` = 内置 HTTP 服务器（`http/http_server.h`）

## 🚀 voip 组件包初始化注册（GetTelephone 单例模式）

voip 组件包的初始化注册完整流程：构造 voip::Configuration（含账号配置）→ new voip::Telephone(conf) → 自动发起 SIP 注册。
```cpp
#include <telephone.h>
voip::Telephone* GetTelephone() {
  // 账号配置：最多 2 平台账号 + 1 本地账号
  voip::AccountConfiguration user1;
  user1.identifier = number;                 // 注册账号
  user1.user_name = number;
  user1.password = password;
  user1.id_uri = URI(number, domain);        // sip:101@domain
  user1.server_uri = URI(domain, port);      // sip:domain:5060
  user1.transport_type = voip::SIP_TRANSPORT_UDP;  // 或 TCP
  user1.headers["AuthTag"] = "timestamp=..;sign=..";  // 自定义头（鉴权）
  user1.auto_transmit_video_to_remote = true;

  voip::Configuration conf;
  conf.accounts.push_back(user1);            // 按开关 push（PlatformEnable + PlatformAccount1Enable/2Enable）
  conf.accounts.push_back(localuser);        // 本地账号 "sip:<本机IP>"
  conf.local_port = 5060;
  conf.reg_timeout = 150;                    // 注册超时
  conf.reg_delay_before_refresh = 30;        // 刷新提前量
  conf.audio_device = std::make_shared<i::AudioCustom>(aec_conf, apc_conf); // AEC/APC(8K)
  conf.output_stream_config.fps = 25;
  conf.output_stream_config.max_bps = 8*1024*1024;  // ⚠️ 码率调大否则流控丢帧
  return new voip::Telephone(conf);
}
```
- URI 辅助：`URI(account, domain, port)` → `sip:101@domain:5060`
- 备用服务器：注册失败自动切 `*_SPARE` 配置键，状态缓存在临时文件（REGISTERED_STATE_1/2）

## 📞 呼叫 / 接听 / 挂断
```cpp
static voip::CallInfo info;                    // 全局当前通话
voip::CallSetting CS;
CS.enable_video = ...;
CS.headers["X-displayName"] = account;         // 自定义 SIP 头
int ret = GetTelephone()->MakeCall(uri, CS, name);  // ret!=0 失败
GetTelephone()->Answer(Call_Id, 200);          // 接听
GetTelephone()->Hangup(Call_Id, 603);          // 挂断（可带原因码）
info = GetTelephone()->GetCallInfo(call_id);
// info.state / call_direction / remote_uri / remote_alias / incoming_header / last_state
```
- 状态监听：`AddCallStateListener(&cb)`，cb 内 `switch(voip::State)`
  - `STATE_CALL_CALLING` 呼出 / `STATE_CALL_EARLY` 振铃 / `STATE_CALL_INCOMING` 来电
  - `STATE_CALL_CONNECTING` / `STATE_CALL_CONFIRMED` 接通 / `STATE_CALL_DISCONNECTED` 挂断
- 方向：`CALL_DIRECTION_INCOMING/OUTGOING`；挂断原因码：`SIP_STATUS_CODE_BUSY_HERE / TEMPORARILY_UNAVAILABLE / DECLINE`、603、600
- 通话数限制：`GetCallCount() > 2` 新来电直接 `Hangup(call_id, SIP_STATUS_CODE_BUSY_HERE)`
- 自动接听：`SIP_AUTO_ANSWER` 开关 + `AutoResponseTime` 秒；无应答挂断 `NoReplyHangUpTime` 秒
- **广播呼叫**：remote_uri 含 `broadcast`/`110004` 或 incoming_header 含 `prompt`+`answer-after=0` → 自动 Answer()；广播与新通话互斥（`SetHold(广播id, true)` 保持，断后恢复）

## 📡 注册状态 & 保活
```cpp
void RegisteredStateListener(voip::Telephone* tel, int code) {
  int sc = GetTelephone()->GetRegistrationStatusCode(account);  // 200=OK
  if (sc != 200) { count++; if (count >= 25) {                  // 25 次失败强制重注册
    GetTelephone()->SetSipRegistration(account, false);
    GetTelephone()->SetSipRegistration(account, true);  count = 0; } }
  // 双账号全挂 3 轮 → setprop ctl.restart zkswe 重启应用
}
GetTelephone()->AddRegisteredStateListener(&cb);
```
- 保活线程：60s 无注册回调且状态非 200 → 重注册；双账号全挂 → 重启应用

## 🔢 DTMF / 寻呼 / IM
```cpp
void DTMFDigitListener(unsigned int digit, voip::DtmfMethod method) { DTMF += digit; }
GetTelephone()->AddDtmfDigitListener(&cb);        // 累积匹配预设码触发 IO
void MessagePagerListener(void* ctx, const char* from, const char* type) { ... }
GetTelephone()->AddMessagePagerListener(&cb);     // 寻呼 ALERT=<start>/<stop>
GetTelephone()->SendInstantMessage(uri, "", msg); // 告警上报（先查注册状态==OK）
```
- 告警消息格式：`Alarm_Info:SIP User=<账号>;port=input1` 或 `Description=IP ...;Mac=..;IP=..`
- GPIO 输入告警：`GpioHelper::input(IOx)==电平` + `SecurityInputxReportAlarmEnable` → SendInstantMessage + 播报警音
- GPIO 输出联动（SecurityOutputx + 前置条件）：来电中/呼出中/接通中/广播中/输入 IO 触发/DTMF 码匹配/寻呼 ALERT 匹配

## 🌐 内置 HTTP 页面服务（Poco-http）
```cpp
#include <http/http_server.h>
class AdminService {
  static AdminService& instance();
  void start(int port) {                        // 线程跑 runForever(port=80)
    std::thread t([this,port]{ initServer(server_); server_.runForever(port); });
    t.detach();
  }
  void initServer(http::HTTPServer& srv);       // 路由注册
};
```
### 路由 API
- `srv.handleDir("/public", resPath)` 静态目录；`srv.GET("/login.html", cb)` `ctx.view(path)` 返回页面
- `srv.GET("/data/xxx", cb)`：`ctx.response.send() << json字符串` / `ctx.response.sendFile(path,"txt")`
- `srv.POST("/data/xxx", cb)`：`ctx.requestBody()` → `base::JSONObject::parse(body)` → 写 StoragePreferences
- 页面资源：`resources/admin_web/`（login.html + index.html 单页 + public/font）

### 文件上传（升级/语音/配置）
```cpp
http::FilePartHandler file_handler;
file_handler.file("file", [&](http::FormField& f, std::istream& stream) {
  std::ofstream ofs(upload_filename + f.fileName, std::ios::binary);
  Poco::StreamCopier::copyStream(stream, ofs);
});
Poco::Net::HTMLForm form(ctx.request, ctx.request.stream(), file_handler);
// 校验: 文件大小==form.get("fileSize") && MD5==form.get("digest")（流式 MD5，1KB 分块）
// 升级: 改名 /tmp/update.img → touch /tmp/zkautoupgrade → UPGRADEMONITOR->checkUpgradeFile
// 配置: zip 解包 → preferences.json 写 /data/ + 报警音 → 重启应用
```
- 配置导出：z::ZipArchive 打 config.zip（preferences.json + 报警音）→ sendFile
- 远程控制：`POST /control` body=restart/Key1~Key5 → 重启/触发按键
- 抓包：`/data/StartTcpdump`（fork+setsid 起 tcpdump）/ `StopTcpdump` / `tcpdump` 下载 pcap
- 首页信息：`GET /data/HomePageInit` → SN/固件版本/账号/服务器/MAC/IP/运行时长/注册状态

### 管理页设置接口（POST + JSON）
| 接口 | 内容 |
|------|------|
| WANsetting | 动态/静态 IP、掩码、网关、DNS |
| Timesetting | 自动校时 + 手动时间（ntp） |
| Platformsetting | SIP 双账号/域名/密码/端口/协议/备用服务器（改完重启应用） |
| Keysetting | 5 个直拨键配置 |
| Functionsetting | 自动接听/视频/早媒体/ICE/DTMF 方式 |
| Volumesetting | 输出/铃声音量、响铃策略 |
| SecurityInputsetting | 4 路输入（使能/电平/告警/报警音/关联键） |
| SecurityOutputsetting | 8 路输出（触发条件组合/DTMF/寻呼） |
| Videosetting | 视频源 URL/分辨率 |
| Communicationsetting | 3 路串口（232/485 波特率、TCP/UDP 桥接） |

## 🩺 SIP 健康检查（sip_health.c 独立 C 模块）
```c
// SIP OPTIONS 探测：200→OK(0)；401/407→ALIVE(1)；超时/网络错→负值
sip_status_t sip_check_health(const char *server_ip, int port,
                              const char *protocol /* "udp"/"tcp" */,
                              int timeout_sec, char *response_msg, int msg_buf_size);
```
- 用途：主服务器注册失败切备用前的健康探测

## 📡 组播设备发现
- 设备端：组播接收线程周期发 JSON 心跳（device/heartbeat），收远端指令：audio_play/stop、record_start/stop/play、reboot
- PC 端：device_scanner.py（Python Tkinter）组播扫描 + 指令发送

## 🔧 其他模块
- SocketHandle：串口透传桥接（TCP Server/Client/UDP），onProtocolDataUpdate 转发
- zip：z::ZipArchive open/readFile/addFile/close（升级/配置/语音包）
- sqlite3：src/dependencies/ 内置（call_log/defence_log 落库）
- ntp：ntp::startSynchronizationTask(defaultServerList)；时区 setenv("TZ","UTC-8",1)
- 看门狗：os::watchdogStart(15)/watchdogKeepalive()（5s 喂狗）/watchdogStop()
- 恢复出厂：长按 5s → rm -rf /data/* → reboot
- 视频：RTSP 拉流（VideoStream NALU 队列）→ register_cbar_impl(cbar) 喂 voip 发送

## ⛔ 铁律
1. voip / Poco-http 是 **accessKey 私有包**，公开 registry 无 API 文档，用法以参考工程为准
2. 视频码率必须调大（max_bps ≥ 8Mbps），否则流控强制丢帧
3. AEC/APC 固定 8K 采样率；MIC 类型 setenv("MIC_TYPE","AMIC",1)
4. 广播通话必须自动接听，与新通话互斥（SetHold）
5. 注册保活：25 次失败重注册 / 60s 无回调重注册 / 双账号全挂重启应用
6. Web 配置改完大多要 setprop ctl.restart zkswe 生效
7. 大文件上传 MD5 校验必须流式（1KB 分块）
8. 该形态产品 UI 极简，交互几乎全走 Web 页 + 物理按键 + GPIO
