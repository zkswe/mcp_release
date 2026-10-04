# SampleUI-New 样例学习笔记

> 源码位置: `projects/SampleUI-New/`
> 屏幕分辨率: 1024×600
> 共 42 个 UI 页面 + 对应 Logic.cc 代码

---

## 目录结构

```
SampleUI-New/
├── Manifest.xml
├── i18n/                    # 多国语言翻译文件
│   ├── zh_CN.tr
│   └── en_US.tr
├── resources/               # 图片资源（含多分辨率子目录）
│   ├── 480x272/             # 480×272 专用资源
│   ├── main/                # 主界面图标
│   ├── main_/               # 主界面 SlideWindow 图标
│   ├── button_/             # 按钮各类图片
│   ├── navi/                # 导航按钮（返回）
│   └── ...
├── ui/                      # UI 布局文件
│   ├── 480x272/
│   ├── 800x480/
│   └── 1024x600/            # 本笔记分析的分辨率
│       ├── main.json        # (原 ftu，已转 JSON)
│       ├── testText.json
│       ├── testButton.json
│       ├── tesList.json
│       └── ... (共 42 个)
├── src/
│   ├── Main.cpp             # 入口
│   ├── activity/            # 自动生成的 Activity(.h/.cpp)
│   └── logic/               # 用户逻辑代码
│       ├── mainLogic.cc
│       ├── testTextLogic.cc
│       ├── testButtonLogic.cc
│       └── ... (共 42 个)
```

---

## 全局设计模式

### 1. 页面导航（SlideWindow 主页菜单）

主界面 `main.ftu` 使用 **SlideWindow** (4列×2行) 作为功能菜单，点击图标通过 `onSlideItemClick` 跳转：

```c++
static void onSlideItemClick_Slidewindow1(ZKSlideWindow *pSlideWindow, int index) {
    EASYUICONTEXT->openActivity(IconTab[index]);  // 打开对应 Activity
}
```

`IconTab[]` 数组按索引映射到 22 个页面名：
```c++
const char* IconTab[] = {
    "testTextActivity",     // 0: 文本
    "testSliderActivity",   // 1: 滑块
    "testButtonActivity",   // 2: 按键
    "inputtextActivity",    // 3: 编辑框
    "waveViewActivity",     // 4: 波形图
    "testpointerActivity",  // 5: 指针
    "windowActivity",       // 6: 窗口
    "video2Activity",       // 7: 视频
    "audioActivity",        // 8: 音频
    "tesListActivity",      // 9: 列表
    "adActivity",           // 10: 广告
    "qrcodeActivity",       // 11: 二维码
    "animationActivity",    // 12: 动画
    "sliderwindowActivity", // 13: 滑动窗口
    "uartMenuActivity",     // 14: 串口
    "painterActivity",      // 15: 画布
    "NetSettingActivity",   // 16: 网络
    "cameraActivity",       // 17: 摄像头
    "tableActivity",        // 18: 表格
    "LanguageSettingActivity", // 19: 语言
    "DeveloperSettingActivity",// 20: 开发者
    "clockActivity",        // 21: 时钟
};
```

每个子页面都包含：
- **返回按钮**：`button__sys_back` (ID=100)，带 navi/fh.png 图标
- **帮助按钮**：`button__Button1` 或类似，点击 `openActivity("helpXxxActivity")`

### 2. 通用代码模式

```c++
// 隐藏状态栏（几乎每个页面都调用）
EASYUICONTEXT->hideStatusBar();

// 打开/关闭页面
EASYUICONTEXT->openActivity("testTextActivity");
EASYUICONTEXT->closeActivity("mainActivity");  // 关闭后不再返回
EASYUICONTEXT->goHome();  // 回到主桌面

// 页面生命周期
static void onUI_init() {}    // 页面初始化
static void onUI_show() {}    // 页面显示时
static void onUI_hide() {}    // 页面隐藏时
static void onUI_quit() {}    // 页面退出时
```

---

## JSON 布局文件格式详解

### 根节点
```json
{
  "backgroundColor": -1,         // -1=透明
  "backgroundPic": "bg.png",     // 背景图
  "id": 0,                       // 根节点固定0
  "touchable": false,
  "resolution": { "width": 1024, "height": 600 },
  "position": { "left": 0, "top": 0, "width": 1024, "height": 600 }
}
```

### 控件键名规则
`"类型__序号"`（双下划线），序号全局递增：

| 键名 | 控件类型 | ID 范围 | 示例 |
|------|---------|---------|------|
| `textview__N` | TextView | 50000+ | `"textview__1": { "id": 50001, ... }` |
| `button__N` | Button | 20000+ | `"button__7": { "id": 20001, ... }` |
| `slidewindow__N` | SlideWindow | 30001 | `"slidewindow__2": { "id": 30001, ... }` |
| `window__N` | Window | 110000+ | `"window__3": { "id": 110002, ... }` |
| `listview__N` | ListView | 80000+ | `"listview__2": { "id": 80000, ... }` |
| `digitalclock__N` | DigitalClock | 93000+ | `"digitalclock__4": { "id": 93002, ... }` |
| `painter__N` | Painter | 52001 | `"painter__5": { "id": 52001, ... }` |

### 颜色值
所有颜色使用**十进制整数**：
- `-1` = 透明
- `16777215` = 0xFFFFFF (白色)
- `0` = 0x000000 (黑色)
- `38360` = 0x95D8 (青色)

### 对齐 alignment
- `0` = 默认
- `36` = 靠左垂直居中（实测 2026-08-29：非居中）
- `37` = 居中对齐（水平+垂直居中，按钮/标题实测）
- `38` = 靠右垂直居中

### 按钮多状态图片 (picTab)
```json
"picTab": {
  "pic0": "button_/TOGGLE_ON.png",    // 正常状态
  "pic1": "button_/TOGGLE_OFF.png",   // 按下状态(省略=同正常)
  "pic2": "button_/TOGGLE_OFF.png"    // 选中状态
}
```

### ListView 嵌套结构
```json
"listview__N": {
  "id": 80000,
  "cols": 1, "rows": 5,
  "item": {
    "text": "标题",
    "subItem": [
      { "id": 70001, "text": "", "picTab": { "pic0": "...", "pic2": "..." } },
      { "id": 20002, "text": "姓名" },
      { "id": 20003, "text": "描述" }
    ]
  }
}
```

### SlideWindow 嵌套结构
```json
"slidewindow__N": {
  "id": 30001,
  "cols": 4, "rows": 2,
  "items": [
    { "text": "@title_wbsp", "picTab": { "pic0": "main_/wbsp.png", "pic1": "main_/wbsp_ax.png" } }
  ]
}
```

### 自定义字符映射 (charsetTab)
TextView/Button 可以用图片替代数字显示：
```json
"charsetTab": [
  { "char": 48, "pic": "num/0.png", "size": { "width": 50, "height": 80 } },
  { "char": 49, "pic": "num/1.png", "size": { "width": 48, "height": 80 } }
]
```

---

## 各控件代码模式

### 1. TextView (文本)
```c++
mTextview1Ptr->setText("hello");
mTextview1Ptr->setTextTr("@i18n_key");  // 多语言
mTextview1Ptr->setTextColor(0xFFFF0000);
mTextview1Ptr->setBackgroundColor(0xFF00FF00);
mTextview2Ptr->setVisible(false);       // 隐藏
```

### 2. Button (按键)
```c++
// 按钮点击回调
static bool onButtonClick_Button1(ZKButton *pButton) {
    pButton->setSelected(!pButton->isSelected());  // 切换选中状态
    return true;
}

// 多状态按钮: pic0=正常 pic1=按下 pic2=选中
// 选中代码: pButton->setSelected(true/false)
```

### 3. SlideWindow (滑动窗口菜单)
```c++
static void onSlideItemClick_Slidewindow1(ZKSlideWindow *pSlideWindow, int index) {
    EASYUICONTEXT->openActivity(IconTab[index]);
}
```

### 4. ListView (列表)
三个回调函数：
```c++
// ① 返回列表总项数
static int getListItemCount_Listview1(const ZKListView *pListView) {
    return sizeof(sData)/sizeof(S_DATA_STRUCT);
}

// ② 设置每一项的显示内容
static void obtainListItemData_Listview1(ZKListView *pListView,
    ZKListView::ZKListItem *pListItem, int index) {
    // 操作列表项
    pListItem->setText(sData[index].name);
    pListItem->setTextTr("@i18n_key");  // 多语言版本

    // 操作子项
    ZKListView::ZKListSubItem* sub = pListItem->findSubItemByID(ID_XXX_SubItemName);
    if (sub) {
        sub->setText(sData[index].desc);
        sub->setSelected(sData[index].bOn);  // 开关状态
        sub->setBackgroundPic("/path/pic.png");  // 动态设置头像
    }
}

// ③ 点击回调
static void onListItemClick_Listview1(ZKListView *pListView, int index, int id) {
    sData[index].bOn = !sData[index].bOn;    // 切换数据
    mListview1Ptr->refreshListView();         // 刷新列表
}
```

### 5. SeekBar (滑块)
```c++
static void onProgressChanged_SeekBar1(ZKSeekBar *pSeekBar, int progress) {
    LOGD("进度: %d", progress);
}
// 代码设置: mSeekBar1Ptr->setProgress(50);
```

### 6. Pointer (指针/仪表)
```c++
// 在活动周期中控制指针旋转
static void onUI_show() {
    mPointer1Ptr->setTargetAngle(120);  // 设置目标角度
}
```

### 7. Painter (画布)
```c++
// 绘图
mPainter1Ptr->setLineWidth(3);
mPainter1Ptr->setSourceColor(0xFF0000);
mPainter1Ptr->drawArc(x, y, 2, 2, 0, 360);  // 画点
mPainter1Ptr->erase(0, 0, width, height);    // 清除
mPainter1Ptr->setTouchable(false);            // 禁止触摸
```

### 8. 定时器
```c++
// 注册
static S_ACTIVITY_TIMEER REGISTER_ACTIVITY_TIMER_TAB[] = {
    {0, 1000},     // id=0, 间隔1000ms
    {kTimerId, 40}, // 常量命名
};

// 回调
static bool onUI_Timer(int id) {
    switch (id) {
    case 0:
        // 定时逻辑
        break;
    }
    return true;  // true=继续 false=停止
}

// 手动注册/停止
mActivityPtr->registerUserTimer(101, 2000);   // 一次性定时器
mActivityPtr->unregisterUserTimer(101);
```

### 9. 串口通讯
```c++
#include "uart/ProtocolSender.h"

// 发送协议
BYTE data[2] = {0, (BYTE)value};
sendProtocol(CMD_BUTTON_ON, data, sizeof(data));

// 接收回调
static void onProtocolDataUpdate(const SProtocolData &data) {
    // 数据更新
}
```

### 10. 触摸事件
```c++
static bool onmainActivityTouchEvent(const MotionEvent &ev) {
    switch (ev.mActionStatus) {
    case MotionEvent::E_ACTION_DOWN: break;  // 按下
    case MotionEvent::E_ACTION_MOVE: break;  // 滑动
    case MotionEvent::E_ACTION_UP:   break;  // 抬起
    }
    return false;  // false=继续传递 true=拦截
}
```

---

## i18n 国际化

文本中以 `@` 开头的值表示引用翻译文件中的 key：
```json
{ "text": "@about_me" }
```

在 `.tr` 文件中定义：
```
about_me = "hello"
about_text = "text content"
```

代码中使用：
```c++
pListItem->setTextTr("@i18n_key");  // Logic.cc 中自动翻译
LANGUAGEMANAGER->getValue("key");   // 手动获取翻译值
```

---

## 常见 View 切换模式

| 操作 | 代码 |
|------|------|
| 打开新页面 | `EASYUICONTEXT->openActivity("xxxActivity")` |
| 关闭当前回主页 | `EASYUICONTEXT->closeActivity("mainActivity")` |
| 回到桌面 | `EASYUICONTEXT->goHome()` |
| 隐藏状态栏 | `EASYUICONTEXT->hideStatusBar()` |
| 显示状态栏 | `EASYUICONTEXT->showStatusBar()` |
| 设置可见 | `mButton1Ptr->setVisible(true/false)` |
| 刷新列表 | `mListview1Ptr->refreshListView()` |
| 返回上一页 | `EASYUICONTEXT->goBack()` |

---

## 实战模式汇总（42 个页面全部解析）

### 📱 媒体播放

#### 音频播放 (audioLogic)
```c++
// 创建音频播放器
ZKMediaPlayer* player = new ZKMediaPlayer(ZKMediaPlayer::E_MEDIA_TYPE_AUDIO);
player->setVolume(0.5);  // 单声道
player->setVolume(0.5, 0.5);  // 双声道 (Z6S/A33NOR)
player->play("/mnt/extsd/music.mp3");
player->pause();
player->resume();
player->stop();
player->seekTo(position * 1000);
int duration = player->getDuration() / 1000;  // 总时长(秒)
int curPos = player->getCurrentPosition() / 1000;  // 当前位置

// 播放状态监听
class Listener : public ZKMediaPlayer::IPlayerMessageListener {
  virtual void onPlayerMessage(ZKMediaPlayer*, int msg, void*) {
    switch (msg) {
    case ZKMediaPlayer::E_MSGTYPE_PLAY_STARTED: break;
    case ZKMediaPlayer::E_MSGTYPE_PLAY_COMPLETED: break;
    case ZKMediaPlayer::E_MSGTYPE_ERROR_INVALID_FILEPATH: break;
    case ZKMediaPlayer::E_MSGTYPE_ERROR_MEDIA_ERROR: break;
    }
  }
};

// 扫描音乐文件
fy::files::list("/mnt/extsd", "*.mp3", true);
ioutil::Append(fileList, fy::files::list("/mnt/usb1", "*.mp3", true));

// 释放
player->stop();
system("echo 3 > /proc/sys/vm/drop_caches");
delete player;
```

#### 视频播放 (video2Logic)
```c++
// VideoView 播放
mVideoview1Ptr->play("/mnt/extsd/video.mp4");
mVideoview1Ptr->pause();
mVideoview1Ptr->resume();
mVideoview1Ptr->stop();
mVideoview1Ptr->seekTo(position * 1000);
mVideoview1Ptr->setVolume(0.5);

// 播放完成回调（自动生成的关联函数）
static void onVideoViewPlayerMessageListener_VideoviewTT(ZKVideoView *pVideoView, int msg) {
  switch (msg) {
  case ZKVideoView::E_MSGTYPE_VIDEO_PLAY_STARTED: break;
  case ZKVideoView::E_MSGTYPE_VIDEO_PLAY_COMPLETED: break;
  case ZKVideoView::E_MSGTYPE_VIDEO_PLAY_ERROR: break;
  }
}
```

### 📷 摄像头 (cameraLogic)
```c++
// 在 onUI_show 中开启预览
mCameraview1Ptr->startPreview();
// 在 onUI_hide 中停止预览
mCameraview1Ptr->stopPreview();

// 错误回调
class ErrorCallback: public ZKCameraView::IErrorCodeCallback {
  virtual void onErrorCode(int error) {
    mTextviewErrorPtr->setText("Error:" + to_string(error));
  }
};
```

### 📱 二维码 (qrcodeLogic)
```c++
// 实时生成二维码（绑定 EditText 输入变化）
static void onEditTextChanged_Edittext1(const std::string &text) {
    mQrcode1Ptr->loadQRCode(text.c_str());
}
```

### 🎨 画布 (painterLogic)
```c++
// 初始化绘制
mPainter1Ptr->setLineWidth(4);
mPainter1Ptr->setSourceColor(0x7092be);        // 设置颜色
mPainter1Ptr->drawRect(10, 10, 430, 230, 5);    // 圆角矩形
mPainter1Ptr->drawArc(80, 80, 40, 40, -20, -120);  // 圆弧
mPainter1Ptr->fillArc(80, 80, 40, 40, -20, 120);   // 扇形
mPainter1Ptr->drawTriangle(x1,y1, x2,y2, x3,y3);   // 空心三角
mPainter1Ptr->fillTriangle(x1,y1, x2,y2, x3,y3);   // 实心三角
mPainter1Ptr->drawLines(points, count);            // 折线
mPainter1Ptr->drawCurve(points, count);            // 曲线
mPainter1Ptr->drawArc(ev.mX, ev.mY, 1, 1, 0, 360); // 触摸画点

// 平台差异 (Z6S/A33NOR vs 新平台)
// Z6S: 使用 MPPOINT
// 其他: 使用 SZKPoint
```

### 📊 波形图 (waveViewLogic)
```c++
// 方式1: 批量更新整段波形数据
SZKPoint sPoints[100];
for(int i = 0; i < 100; i++){
  sPoints[i].x = (100*i)/100;
  sPoints[i].y = rand() % 100;
}
mDiagram1Ptr->setData(0, sPoints, 100);  // info索引0, 数据, 点数

// 方式2: 实时追加数据
mDiagram2Ptr->addData(0, newValue);  // info索引0, 新值

// 关闭/开启波形刷新
bRefresh = !bRefresh;
mButtonOnOffPtr->setSelected(!bRefresh);
```

### 🚗 仪表盘 (pointerLogic)
```c++
// 指针角度控制（含平滑动画）
mDashbroadView_1Ptr->setTargetAngle(value);

// 同时控制指针 + 波形图
mDiagram1Ptr->addData(0, v);  // 实时波形
mDashbroadView_1Ptr->setTargetAngle(value);
```

### ⏰ 系统时间/时钟 (clockLogic)
```c++
// NTP 时间同步
ntp::syncTime(ntp::defaultServerList(), 5000);

// 获取当前时间
base::DateTime now = base::DateTime::now();
string timeStr = now.toString();

// 手动设置系统时间
base::DateTime dt;
dt.year = 2026; dt.month = 5; dt.day = 31;
dt.hour = 10; dt.min = 30; dt.second = 0;
base::setSystemDateTime(dt);
TimeHelper::setDateTime("2026-05-31 10:30:00");

// 获取格式化时间（字符串）
struct tm *t = TimeHelper::getDateTime();
sprintf(buf, "%02d:%02d", t->tm_hour, t->tm_min);
```

### 🔗 Intent 页面传参
```c++
// 发送方：创建 Intent 传参
Intent* intent = new Intent();
intent->putExtra("value", "100");
intent->putExtra("pay", "￥10.00");
intent->putExtra("time", "38分钟");
EASYUICONTEXT->openActivity("Charge2Activity", intent);

// 接收方：在 onUI_intent 中读取
static void onUI_intent(const Intent *intentPtr) {
  if (intentPtr != NULL) {
    std::string tv = intentPtr->getExtra("pay");
    std::string time = intentPtr->getExtra("time");
    mTextCoastPtr->setText(tv);
  }
}

// 或另一种写法
static void onActivityItent(const Intent *intentPtr) {
  int target = atoi(intentPtr->getExtra("target").c_str());
}
```

### 🔌 串口终端 (uartLogic)
```c++
// 读取串口原始数据
static void readHook(const BYTE* data, int len) {
  // 十六进制显示
  string s = "";
  for (int i = 0; i < len; ++i) {
    snprintf(buf, sizeof(buf), "%02x ", data[i]);
    s += buf;
  }
  mTextviewLogPtr->setText(s);
}

// 注册/取消原始数据钩子
UARTCONTEXT->addReadHook(readHook);      // onUI_show
UARTCONTEXT->removeReadHook();           // onUI_hide

// 发送原始数据
sendRaw((BYTE*)text.c_str(), text.size());

// 扫描可用串口
serial_port_list = fy::files::list("/dev", "ttyS*", false);
pListItem->setText(serial_port_list[index]);
```

### 📟 MODBUS (modbusLogic)
```c++
ModbusContext* modbus = new ModbusContext();
modbus->openUart("/dev/ttyS1", B115200);
modbus->RegisterListener(&listener);

// 读取单个寄存器
modbus->ReadRegisters(startReg, endReg);

// 写入单个寄存器
modbus->WriteRegister(reg, value);

// 回调
class ModbusListener: public ModbusContext::Listener {
  virtual void OnMessage(const ModbusMsg* msg) {
    // msg->data[0] = 值
    // msg->reg = 寄存器地址
    // msg->nb = 数据数量
  }
};

// 生命周期
modbus->closeUart();
modbus->UnregisterListener(&listener);
delete modbus;
```

### 🌐 网络/WiFi (adLogic)
```c++
// WiFi 状态
NETMANAGER->getWifiManager()->isConnected();
NETMANAGER->getWifiManager()->isWifiEnable();
WifiInfo* info = NETMANAGER->getWifiManager()->getConnectionInfo();
info->getSsid();

// 以太网
NETMANAGER->getEthernetManager()->getIp();

// Socket 连接
net::Conn* conn = net::Dial("tcp", "192.168.1.100:30000", 50);
```

### 🔆 屏幕亮度
```c++
#include "utils/BrightnessHelper.h"
BRIGHTNESSHELPER->setBrightness(progress);  // 0-100
```

### 🪟 Window 窗口控制
```c++
mWindow1Ptr->showWnd();     // 显示窗口
mWindow1Ptr->hideWnd();     // 隐藏窗口
mWindow1Ptr->isWndShow();   // 是否显示
mWindow1Ptr->isVisible();   // 是否可见
mWindow1Ptr->setPosition(pos);  // 拖动窗口

// 触摸拖动窗口
case MotionEvent::E_ACTION_MOVE: {
  int x_offset = ev.mX - last_ev.mX;
  int y_offset = ev.mY - last_ev.mY;
  if (mWindowDragPtr->getPosition().isHit(ev.mX, ev.mY)) {
    LayoutPosition pos = mWindowDragPtr->getPosition();
    pos.mLeft += x_offset;
    pos.mTop += y_offset;
    mWindowDragPtr->setPosition(pos);
  }
}
```

### 🏗 动画（窗口进出滑动）
```c++
// 通过定时器逐帧改变窗口位置实现动画
static bool onUI_Timer(int id) {
  static LayoutPosition pos = mWindowSetupPtr->getPosition();
  pos.mLeft = animationLocation[index++];  // 预设位置数组
  mWindowSetupPtr->setPosition(pos);
}

// 手动注册一次性动画定时器
mActivityPtr->registerUserTimer(TIMER_ID, 10);
```

---

## 页面清单 (42个)

| 文件名 | UI 页面 | 关联控件 | 核心功能 |
|--------|---------|---------|---------|
| `mainLogic` | main | SlideWindow, Button, Painter, DigitalClock | 主页菜单，触摸轨迹动画，背景色切换 |
| `testTextLogic` | testText | TextView ×6, Button ×2 | 文本展示(字号/颜色/滚动/自定义字符图) |
| `testButtonLogic` | testButton | Button ×8, TextView | 多状态按钮(toggle/check/数字滚轮) |
| `testSliderLogic` | testSlider | SeekBar ×2, CircleBar | 进度条调亮度/温度，串口发送 |
| `testpointerLogic` | testpointer | Pointer, Button | 指针随机角度/串口控制模式切换 |
| `inputtextLogic` | inputtext | EditText ×4 | 输入框(普通/数字/密码) |
| `tesListLogic` | tesList | ListView ×2 | 开关列表 + 联系人列表(头像/姓名/描述) |
| `waveViewLogic` | waveView | Diagram ×3, Button | 波形图 setData/addData 两种模式 |
| `painterLogic` | painter | Painter ×2 | 绘图(矩形/弧/三角形/折线/曲线) |
| `qrcodeLogic` | qrcode | QRCode, EditText | 实时生成二维码 |
| `pointerLogic` | pointer | Pointer, Diagram, TextView | 汽车仪表盘(速度/RPM/温度/油耗/波形) |
| `windowLogic` | window | Window ×3, Button | 模态窗口/普通窗口/拖拽窗口 |
| `audioLogic` | audio | SeekBar, Button, ZKMediaPlayer | 音频播放器(扫描/播放/进度/音量) |
| `video2Logic` | video2 | VideoView, SeekBar, Button | 视频播放器(扫描/播放/seek/音量) |
| `cameraLogic` | camera | CameraView | 摄像头预览 |
| `animationLogic` | animation | TextView | 图片帧动画(50ms循环) |
| `sliderwindowLogic` | sliderwindow | SlideWindow, TextView | 应用案例导航页 |
| `detailLogic` | detail | SlideWindow, ListView, CircleBar | 洗衣机详情(程序选择/参数调整) |
| `washerLogic` | washer | SlideWindow, ListView, Window | 洗衣机主界面(程序列表/设置弹窗动画) |
| `xinfengLogic` | xinfeng | Multiple buttons, Text, SeekBar | 新风系统(PM2.5/CO2/童锁密码/串口协议) |
| `ChargeLogic` | Charge | Button | 充电桩金额选择(Intent传参) |
| `Charge2Logic` | Charge2 | SeekBar, Button, Text | 充电支付界面(微信/支付宝) |
| `clockLogic` | clock | EditText ×6, Button | NTP同步 + 手动设系统时间 |
| `tableLogic` | table | ListView (6列子项) | 数据表格(斑马纹/多列/选中高亮) |
| `uartLogic` | uart | ListView ×2, EditText, Button | 串口调试终端(HEX/ASCII收发) |
| `uartMenuLogic` | uartMenu | Button ×2 | 串口功能菜单 |
| `modbusLogic` | modbus | EditText, Button, ListView, Window | MODBUS RTU(读/写寄存器) |
| `adLogic` | ad | Button, SeekBar, Window | WiFi广告推送/远程升级 |
| `statusbar` | statusbar | Button ×2 | 系统状态栏(返回/主页) |
| `emptyLogic` | empty | — | 初始化后跳转主页 |
| `help*Logic` (×12) | help* | TextView | 各控件的使用说明帮助页 |
