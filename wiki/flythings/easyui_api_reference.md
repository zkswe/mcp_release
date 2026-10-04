# EasyUI API 参考手册

> 版本: 2.9.0 (2026-06-01 更新)
> 来源: FlyThings IDE SDK packages/easyui/2.9.0/include/

---

## 一、bitmap_t — 位图数据格式

**头文件:** `utils/BitmapHelper.h`

```cpp
typedef struct _bitmap_t {
    uint8_t type;       // 类型（一般填 0）
    uint8_t bits;       // 位深（32 = ARGB8888）
    uint8_t bytes;      // 每像素字节数（4）
    uint8_t alpha;      // 是否有 Alpha 通道（1 = 有）
    uint32_t ck;        // Chroma key（一般填 0）
    uint32_t width;     // 图像宽度（像素）
    uint32_t height;    // 图像高度（像素）
    uint32_t pitch;     // 每行字节数（width * bytes，需对齐）
    uint8_t *data;      // 像素数据指针
    uint8_t *am;        // Alpha 掩码（一般填 nullptr）
    uint32_t ap;        // Alpha 掩码相关（一般填 0）
    uint8_t *phy_addr;  // 物理地址（一般填 nullptr）
} bitmap_t;
```

**典型用法：**
```cpp
bitmap_t bmp;
bmp.type   = 0;
bmp.bits   = 32;
bmp.bytes  = 4;
bmp.alpha  = 1;
bmp.ck     = 0;
bmp.width  = width;
bmp.height = height;
bmp.pitch  = stride;  // cairo_stride 或 width*4
bmp.data   = pixels;  // ARGB8888 数据指针
bmp.am     = nullptr;
bmp.ap     = 0;
bmp.phy_addr = nullptr;

// 设置到显示控件
mTextView1Ptr->setBackgroundBmp(&bmp);
```

---

## 二、ZKBase — 控件基类

**头文件:** `control/ZKBase.h`

所有 UI 控件的基类。

### 通用方法

```cpp
// 位置/布局
int getID() const;
void setPosition(const LayoutPosition &position);
const LayoutPosition& getPosition() const;
LayoutPosition getAbsolutePosition() const;

// 可见性
void setVisible(bool isVisible);
bool isVisible() const;

// 状态
void setSelected(bool isSelected);
bool isSelected() const;
void setPressed(bool isPressed);
bool isPressed() const;
void setTouchable(bool isTouchable);
bool isTouchable() const;
void setTouchPass(bool isPass);  // 触摸穿透

// 背景
void setBackgroundPic(const char *pPicPath);          // 图片文件
void setBackgroundBmp(struct _bitmap_t *pBmp);        // 内存位图
void setBackgroundColor(uint32_t color);              // ARGB 颜色
void setBgStatusColor(int status, uint32_t color);
void setBackgroundCrop(const LayoutPosition &crop);   // 裁剪

// 透明度/层级
void setAlpha(uint8_t alpha);         // 0-255
void setOpaque(bool opaque);
void setLayerIndex(int index);

// 重绘/刷新
void invalidate(const LayoutPosition *dirty = NULL);

// 蜂鸣器
void beep();
```

### 控件状态常量

```cpp
#define ZK_CONTROL_STATUS_NORMAL      0x00000000
#define ZK_CONTROL_STATUS_PRESSED     0x00000001
#define ZK_CONTROL_STATUS_SELECTED    0x00000002
#define ZK_CONTROL_STATUS_INVALID     0x00000004
#define ZK_CONTROL_STATUS_VISIBLE     0x00000008
#define ZK_CONTROL_STATUS_TOUCHABLE   0x00000010
#define ZK_CONTROL_STATUS_TOUCH_PASS  0x00000020
```

### 事件监听器

```cpp
// 点击
class IClickListener {
    virtual void onClick(ZKBase *pBase) = 0;
};

// 长按
class ILongClickListener {
    virtual void onLongClick(ZKBase *pBase) = 0;
};

// 触摸
class ITouchListener {
    virtual void onTouchEvent(ZKBase *pBase, const MotionEvent &ev) = 0;
};

void setClickListener(IClickListener *pListener);
void setLongClickListener(ILongClickListener *pListener);
void setTouchListener(ITouchListener *pListener);
```

### 定时器

```cpp
void startTimer(int id, uint32_t time);  // time 单位 ms
void stopTimer(int id);
void resetTimer(int id, uint32_t time);
bool hasTimer(int id);
```

---

## 三、MotionEvent — 触摸事件

**头文件:** `control/Common.h`

```cpp
class MotionEvent {
public:
    enum EActionStatus {
        E_ACTION_NONE,
        E_ACTION_DOWN,    // 按下
        E_ACTION_UP,      // 抬起
        E_ACTION_MOVE,    // 移动
        E_ACTION_CANCEL   // 取消
    };

    EActionStatus mActionStatus;
    int mX;              // X 坐标
    int mY;              // Y 坐标
    long mEventTime;     // 事件时间
};
```

---

## 四、LayoutPosition — 布局位置

**头文件:** `control/Common.h`

```cpp
class LayoutPosition {
public:
    LayoutPosition(int l = 0, int t = 0, int w = 0, int h = 0);
    void offsetPosition(int xOffset, int yOffset);
    bool isHit(int x, int y) const;  // 判定点是否在区域内

    int mLeft;    // X
    int mTop;     // Y
    int mWidth;   // 宽
    int mHeight;  // 高
};
```

---

## 五、ZKTextView — 文本控件

**头文件:** `control/ZKTextView.h`

```cpp
// 文本内容
void setText(const std::string &text);
void setText(const char *text);
void setText(char text);
void setText(int text);
const std::string& getText() const;

// 颜色/字号
void setTextColor(int color);           // 0x ARGB
void setTextStatusColor(int status, uint32_t color);
void setTextSize(uint32_t size);

// 间距/字体
void setTextRowSpace(int space);
void setTextColSpace(int space);
void setTextPadding(const LayoutPadding &padding);
void setFontFamily(const char *family);

// 对齐
void setAlignment(AlignH h, AlignV v);  // 水平+垂直
enum EAlignH { E_ALIGN_H_LEFT, E_ALIGN_H_CENTER, E_ALIGN_H_RIGHT };
enum EAlignV { E_ALIGN_V_TOP, E_ALIGN_V_CENTER, E_ALIGN_V_BOTTOM };

// 粗体/斜体
void setBold(bool bold);
void setItalic(bool italic);

// 超长模式
void setLongMode(ELongMode mode);
enum ELongMode { E_LONG_MODE_NONE, E_LONG_MODE_DOTS, E_LONG_MODE_SCROLL, E_LONG_MODE_SCROLL_CIRCULAR };

// 获取文本宽高
void getTextExtent(const char *text, int &w, int &h);
```

---

## 六、ZKPainter — 画布控件

**头文件:** `control/ZKPainter.h`

```cpp
// 样式
void setLineWidth(uint32_t width);
void setSourceColor(uint32_t color);  // 0x RRGGBB（注意：不是 ARGB！）

// 图形
void drawTriangle(int x0, int y0, int x1, int y1, int x2, int y2);
void drawRect(int left, int top, int width, int height, int radius = 0);
void drawArc(int cx, int cy, int rx, int ry = 0, int startAngle = 0, int sweepAngle = 360);
void drawLines(const SZKPoint *pPoints, int count);
void drawCurve(const SZKPoint *pPoints, int count);

// 填充
void fillTriangle(int x0, int y0, int x1, int y1, int x2, int y2);
void fillRect(int left, int top, int width, int height, int radius = 0);
void fillArc(int cx, int cy, int rx, int ry = 0, int startAngle = 0, int sweepAngle = 360);

// 擦除
void erase(int x, int y, int w, int h);
```

> ⚠️ `setSourceColor` 使用 0xRRGGBB 格式，不是 0xAARRGGBB！

---

## 七、Activity — 界面生命周期

**头文件:** `app/Activity.h`

```cpp
class Activity : public BaseApp {
protected:
    // 生命周期回调
    virtual void onIntent(const Intent *intentPtr) { }  // 接收数据
    virtual void onResume() { }                          // 界面显示
    virtual void onPause() { }                           // 界面隐藏  
    virtual bool onBack() { return true; }               // 返回键
};
```

### Intent — 界面间传参

```cpp
class Intent {
public:
    Intent(int action = E_INTENT_ACTION_MAIN, std::string uri = "");
    void putExtra(const std::string &key, const std::string &value);
    const std::string& getExtra(const std::string &key) const;
};
```

### 界面跳转

```cpp
EASYUICONTEXT->openActivity("appName", intentPtr);   // 打开界面
EASYUICONTEXT->closeActivity("appName");              // 关闭界面
EASYUICONTEXT->goBack();                              // 返回上一界面
EASYUICONTEXT->goHome();                              // 回到主界面
```

---

## 八、BaseApp — 应用基类

**头文件:** `app/BaseApp.h`

```cpp
class BaseApp : public ZKBase::IClickListener, public ZKMainWindow::ITimerListener {
public:
    // 生命周期
    virtual void onCreate();                     // 创建完成回调
    virtual void onClick(ZKBase *pBase);         // 按钮点击
    virtual bool onTimer(int id);                // 定时器回调

    // 查找控件
    ZKBase* findControlByID(int id);

    // 定时器
    void registerTimer(int id, int time);        // id: 定时器ID, time: 周期(ms)
    void unregisterTimer(int id);
    void resetTimer(int id, int time);

protected:
    ZKMainWindow *mMainWndPtr;    // 主窗口指针
};
```

---

## 九、Log — 日志系统

**头文件:** `utils/Log.h`

```cpp
#define LOGD(fmt, args...)   // DEBUG 级别（白色）
#define LOGI(fmt, args...)   // INFO 级别
#define LOGW(fmt, args...)   // WARN 级别（黄色）
#define LOGE(fmt, args...)   // ERROR 级别（红色）
#define LOGV(fmt, args...)   // VERBOSE 级别
```

日志输出到 Android logcat，Tag 默认为 `"zkgui"`。

**查看日志：** `adb logcat | grep "zkgui\|WebView\|TAG"`

---

## 十、EasyUIContext — 全局上下文

**头文件:** `entry/EasyUIContext.h`

```cpp
// 全局触摸监听
class ITouchListener {
    virtual bool onTouchEvent(const MotionEvent &ev) = 0;
};
void registerGlobalTouchListener(ITouchListener *pListener);
void unregisterGlobalTouchListener(ITouchListener *pListener);

// 全局按键监听
class IKeyListener {
    virtual bool onKeyEvent(const KeyEvent &ke) = 0;
};
void registerKeyListener(IKeyListener *pListener);
void unregisterKeyListener(IKeyListener *pListener);

// 界面管理
void openActivity(const char *appName, Intent *intentPtr = NULL);
void closeActivity(const char *appName);
void goBack();
void goHome();

// 状态栏/导航栏
void showStatusBar();
void hideStatusBar();
void showNaviBar();
void hideNaviBar();

// 屏保
void setScreensaverTimeOut(int timeOut);  // -1 = 不进屏保
void screensaverOn();
void screensaverOff();

// 输入法
void showIME(SIMETextInfo *pInfo, IIMETextUpdateListener *pListener);
void hideIME();

// 语言切换
void updateLocalesCode(const char *code);
```

---

## 十一、控件类型名（JSON/Ftu 中用）

**头文件:** `control/Common.h`

| 宏名 | 字符串值 | 控件 |
|------|----------|------|
| `ZK_WINDOW` | `"zk_window"` | Window |
| `ZK_SLIDEWINDOW` | `"zk_slidewindow"` | SlideWindow |
| `ZK_PAGEWINDOW` | `"zk_pagewindow"` | PageWindow |
| `ZK_SCROLLWINDOW` | `"zk_scrollwindow"` | ScrollWindow |
| `ZK_TEXTVIEW` | `"zk_textview"` | TextView |
| `ZK_BUTTON` | `"zk_button"` | Button |
| `ZK_CHECKBOX` | `"zk_checkbox"` | CheckBox |
| `ZK_RADIOGROUP` | `"zk_radiogroup"` | RadioGroup |
| `ZK_SEEKBAR` | `"zk_seekbar"` | SeekBar |
| `ZK_CIRCLEBAR` | `"zk_circlebar"` | CircleBar |
| `ZK_LISTVIEW` | `"zk_listview"` | ListView |
| `ZK_POINTER` | `"zk_pointer"` | Pointer |
| `ZK_DIAGRAM` | `"zk_diagram"` | Diagram |
| `ZK_DIGITALCLOCK` | `"zk_digitalclock"` | DigitalClock |
| `ZK_QRCODE` | `"zk_qrcode"` | QRCode |
| `ZK_EDITTEXT` | `"zk_edittext"` | EditText |
| `ZK_VIDEOVIEW` | `"zk_videoview"` | VideoView |
| `ZK_CAMERAVIEW` | `"zk_cameraview"` | CameraView |
| `ZK_SLIDETEXT` | `"zk_slidetext"` | SlideText |
| `ZK_PAINTER` | `"zk_painter"` | Painter |
| `ZK_IMAGEANIM` | `"zk_imageanim"` | ImageAnim |
