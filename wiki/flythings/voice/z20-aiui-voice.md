# KB: Z20 智能家居面板语音方案（讯飞 AIUI + 语音控制框架）

> 定位：**Z20 智能家居面板**（灯光/空调/窗帘/开关/场景控制）+ **语音交互**（讯飞 AIUI，推荐方案）。
> ⚠️ 本页为专项知识：仅当用户提到 **语音控制 / 语音助手 / 智能家居面板 / AIUI / 讯飞语音 / 语音识别 / 唤醒词 / 语音控制灯光空调** 等关键词时关联，不影响常规 UI/工程需求。

## 🔑 关键词索引
**语音控制 / AIUI / 讯飞 / 唤醒词 / 语音识别 / 智能家居面板 / 语音助手 / 灯光语音控制 / 空调语音控制 / 窗帘 / 场景控制 / Z20 语音 / 魔飞 / 离线语音 / TTS**

## 🎯 方案定位（需求方确认）
- **语音推荐 AIUI 方案**（在线，讯飞开放平台）；魔飞（MoFei）有在线/离线两版，离线免网络但需烧模型
- SmartHome 工程 = **UI demo + 简单继电器控制**，不是真实涂鸦/云端对接（演示 UI 和语音链路用）
- 涂鸦 IOT 网关 SDK 已弃用；涂鸦方案走 tuyaoscxx 包
- SIP SDK 版本迭代差别不大，**用最新版即可**

## 🗣 AIUI 语音方案
### 依赖
```
VOICE_LDFLAGS += -laiui -lvtn_mic2        # AIUI 核心 + 麦克风 VAD
VOICE_LDFLAGS += -lmi_common -lmi_sys -lmi_ai -lmi_ao   # ⚠️ SigmaStar(SSD20x/21x/22x) 硬件音频 API
```
### 核心流程（VoiceManager.cpp）
```cpp
#include "aiui/AIUI_C.h"
#include "aiui/Types.h"
#include "aiui/wakeup.h"          // IvwResult/IvwAudio/IatAudio 唤醒回调

aiui_set_aiui_dir(BASEPATH "AIUI");          // ① AIUI 资源目录（唤醒词/技能配置）
CAENew(&s_cae_handle, sn, IvwResult, IvwAudio, IatAudio, icae_config, NULL);  // ② 唤醒引擎
AIUIMessage msg = aiui_msg_create(CMD_SYNC, SYNC_DATA_SCHEMA, 0, "", buf);    // ③ 同步语义 schema
aiui_agent_send_message(g_agent, msg);

// ④ 唤醒处理
void VoiceManager::voiceWakeup() {
  play(CONFIGMANAGER->getResFilePath("AIUI/wakeupVoice.mp3"));  // 播唤醒提示音
  EASYUICONTEXT->openActivity("voiceActivity");                 // 开语音交互页
  // CMD_RESET_WAKEUP 重置回待唤醒状态
}
```
### 回调注册
| 回调 | 用途 |
|------|------|
| registerWakeupCallbacke | 唤醒成功（提示音/开语音页） |
| registerSleepCallback | 休眠/待唤醒 |
| registerResultCallback | 识别结果（JSON 字符串） |
| registerCommWordCallback | 离线命令词命中（words[] + callback） |
| registerAiuiSkillCallback | 技能回调（getSkillCategory 分类） |
| registerUserConversationCallbacke | 用户会话（多轮） |
| registerUserIat | 听写文本 |

### 结果解析
- 识别结果 JSON：`getObject(json, "intent")` → `"text"` 拿语义文本；`getVoiceRecognitionResult(data)` 提取最终文本
- 语义文本 → voiceCtrl 关键词匹配 → 控制设备；TTS 用 `CMD_TTS` + stream_player 播放

## 🎛 voiceCtrl 语音控制框架
### 设备模型（DevBase.h）
```cpp
#define SWITCH 1   // 开关
#define LIGHT 2    // 灯具
#define CURTAIN 3  // 窗帘
#define AIRCON 4   // 空调
#define SCENE 5    // 场景
class Device : public DevInfo, public DevState {};   // 名称/id/品类 + 电源/亮度/窗帘%/空调模式风速风向温度
class DevBase  { std::map<int, Device> mDevices; addDev/updateDev/findDevices; addCtrlDevCallback; };
```
### 关键词匹配控制（voiceCtrl/*Ctrl.h）
```cpp
static const VoiceCtrlBase mLightVoiceSolverVec[] = {
  {LIGHT_POWER,      lightPowerOffKeyWorldsSolve},       // "关"
  {LIGHT_POWER,      lightPowerOnKeyWorldsSolve},        // "开"
  {LIGHT_BRIGHTNESS, lightBrightnessIncKeyWorldsSolve},  // "亮"/"调亮到N"/"最亮"
  {LIGHT_BRIGHTNESS, lightBrightnessDecKeyWorldsSolve},  // "暗"/"调暗到N"/"最暗"
};
// 关键词判定：statement.find("开") != npos → 执行
// 数字提取：getStringNum(statement, num) → 调亮度/温度到指定值；步进 ±20，限 0~100
```
- 入口：`VoiceCtrlManager::solverUserInstruct(statement)` → ctrlScene/ctrlSwitch/ctrlDevices 分发
- 控制生效：`DEVMANAGER->updateDev(device)`（更新模型 + 触发控制回调 → 继电器）
- 空调：电源/模式/风速/风向/温度；窗帘：开合百分比；场景：一键多设备

## 🔌 控制链路
- UI 面板（light/airCon/curtain/switch 页）→ DevManager 更新设备 → GPIO/继电器控制
- 语音链路：AIUI 识别 → 语义文本 → VoiceCtrlManager 关键词匹配 → 设备模型更新 → 执行
- 配套：DhcpClient、ntp、WatchDog、WiFiDetectManager、Ext4Utils（sdnand 挂载失败自动 format）

## ⛔ 铁律
1. **mi_ai/mi_ao 是 SigmaStar 专有**（SSD20x/21x/22x），Z20 语音采集播放用它；其他平台无 mi_*，跨平台需换音视频接口
2. 语音推荐 AIUI（在线，需讯飞开放平台 appid + 资源）；魔飞离线免网络但模型/授权走商务
3. SmartHome 是 UI demo + 继电器，不接真实云平台
4. AIUI 资源目录用 aiui_set_aiui_dir 指定；唤醒词/技能在 resources/AIUI 下配置
5. 关键词匹配控制只认语义文本，识别结果 JSON 字段以 AIUI 事件解析参考为准
