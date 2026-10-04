# KB: 游戏机方案（RetroArch/libretro 动态库前端）+ Knob 旋钮输入

> 定位：**基于 RetroArch/libretro 动态库 + FlyThings 前端的游戏机方案**（对外销售）+ **物理旋钮输入**通用方案。
> ⚠️ 本页为专项知识：仅当用户提到 **游戏机 / 游戏前端 / RetroArch / libretro / 模拟器 / 游戏列表 / ROM / 旋钮 / Knob / 旋转编码器** 等关键词时关联，不影响常规 UI/工程需求。

## 🔑 关键词索引
**游戏机 / RetroArch / libretro / 模拟器 / 游戏前端 / 游戏列表 / ROM / 预览 GIF / 存读档 / 旋钮 / Knob / 旋转编码器 / 物理按键 / 游戏手柄 / SigmaStar 游戏机**

## 🎮 游戏机方案（Game640480_Retro）
### 方案要点（需求方确认）
- **core 来源**：RetroArch 或任意开源模拟器的 libretro 模块编译即可，**方案对外销售**
- **渲染性能**：30fps 满足——前面软件 memcpy 拷贝帧，**TextView→屏幕由硬件 G2D 加速**
- 平台：SigmaStar（Z20/SSD20x），Makefile 链接 `-lmi_common -lmi_ao -lmi_sys -lmi_gfx -lcam_os_wrapper`

### libretro core 动态加载（dylib.c，RetroArch 官方代码）
```c
#include <dlfcn.h>
typedef void* dylib_t;
dylib_t dylib_load(const char *path) { return dlopen(path, RTLD_LAZY | RTLD_LOCAL); }
function_t dylib_proc(dylib_t lib, const char *proc) {
  void *ptr_sym = dlsym(lib, proc);   // 取 retro_load_game/retro_run 等符号
  memcpy(&sym, &ptr_sym, sizeof(void*));  // 规避 (void*)→fn-ptr 转型非法
  return sym;
}
void dylib_close(dylib_t lib) { dlclose(lib); }
```
### 运行线程接口（GameMainThread.h；⚠️ .cpp 已残缺）
- load_core(path)/unload_core()：dlopen/dlsym libretro 入口
- load_game(gamefile)：retro_load_game
- threadLoop()：retro_run 循环，video_refresh 回调 → GameView::updateVideodata
- save_game_slot(slot)/load_game_slot(slot)（-1=默认档，0-9=普通档）、CaptureGame(path) 截帧、start_pause/restartGame

### 渲染链路（核心技巧）
```
libretro 输出 RGB565 帧
  → 软件 memcpy 拷贝到 ZKTextView 的 bitmap canvas（GameView::updateVideodata）
  → setInvalid 触发刷新
  → TextView→屏幕由硬件 G2D 加速（30fps OK）
```
```cpp
// GameView：ZKTextView 当画布
bool initvideoRGB565(int w, int h) {
  // 生成 24bit BMP 头 → BitmapHelper::loadBitmapFromFile → setBackgroundBmp 挂画布
  // rota==1 时宽高互换（90° 旋转）
}
int updateVideodata(const void* data, unsigned w, unsigned h, size_t pitch) {
  // memcpy 帧到 _s_canvas->data（RGB565，每行 width*2）；支持旋转翻转拷贝
  // _this->setInvalid(!_this->isInvalid());  // 刷新
}
bool Capture(const char* path) { // RGB565→RGB888 → stbi_write_bmp 存图 }
```

### 按键映射（inputEvent.cpp）
```cpp
const S_KEY_TRANS keyTrans[] = {
  KEYCODE_UP/DOWN/LEFT/RIGHT → SDLK_UP/DOWN/LEFT/RIGHT,
  KEYCODE_UP → SDLK_8, KEYCODE_DOWN → SDLK_2, KEYCODE_LEFT → SDLK_4, KEYCODE_RIGHT → SDLK_6,
  KEYCODE_B → SDLK_LALT, KEYCODE_A → SDLK_LCTRL, KEYCODE_X → SDLK_RCTRL, KEYCODE_Y → SDLK_RALT,
  KEYCODE_L1 → SDLK_LEFTPAREN, KEYCODE_L2 → SDLK_LEFTBRACKET,
  KEYCODE_R1 → SDLK_RIGHTPAREN, KEYCODE_R2 → SDLK_RIGHTBRACKET,
  KEYCODE_SELECT → SDLK_SPACE, KEYCODE_START → SDLK_RETURN,
  KEYCODE_MENU → SDLK_MENU, KEYCODE_POWER → SDLK_POWER,
  KEYCODE_VOLDEC → SDLK_MINUS, KEYCODE_VOLPLUS → SDLK_PLUS,
};
// inputEvent 线程：FB_PumpEvents 读 Linux input → getUserKeyCode 转 SDL 键码 → 回调
// 长按/重复：setRepeat(延时, 间隔)，prockeyTimer 状态机（1=首次长按，2=重复）
```

### 游戏库（GameDBFile + sqlite3）
- 内嵌 sqlite3（sqlite3.c 单文件）+ CppSQLite3，库文件 `/mnt/extsd/game.db`；表 game/gamehis
- 字段：gameid/gameType/fileName/bFav/runcmd/his
- getGameList/searchGame(拼音)/updateGameFav/updateGameHis/recoverhisfav/startScan（扫 SD 卡 ROM 按机种分类入库）

### 其他
- CGifPlayer + gif_lib：游戏预览 GIF 动画
- audioplay：BEEP/BGMUSIC/LOGOMUSIC/GAMEING 四类音频
- zkhw：亮度/背光/ADC/电池；多语言 20+（i18n/*.tr）

## 🎛 Knob 旋钮输入（KnobDemo）
### 事件定义
```cpp
// 旋转方向判定（EV_ABS code/value 配对）
Clockwise_Start = 14, Clockwise_Stop = 7,          // 顺时针 start=14 → stop=7
Counterclockwise_Start = 13, Counterclockwise_Stop = 11  // 逆时针 start=13 → stop=11

enum { EVENT_KET_DOWN, EVENT_KET_UP, EVENT_KET_CLOCKWISE, EVENT_KET_COUNTERCLOCKWISE };
typedef void KnobReport(Knob_Report msg);
int start_key_event_ctx();  // 启动 select 监听线程
void set_knobp_report_listener(KnobReport* cb);  // 注册上报回调
```
### 底层实现要点
- input 节点（写死，换硬件要改）：`/dev/input/event68`、`/dev/input/event1`
- select 多路复用监听所有节点 fd + wakeup pipe 优雅退出
- EV_ABS → 旋转判定（start/stop 配对）；EV_KEY → 按键（按下/抬起）
- 旋转上报异常时修改 start/stop 值对接（readme 说明）
### 事件分发（EventCtrl 单例）
```cpp
class EventCtrl {
  static EventCtrl* GetInstance();
  void DealPressDownUIEvent(void*);  // 点击
  void DealSpinEvent(void*);         // 旋转
  void DealLongClick(void*);         // 长按
  void setExecutionEventListener/ setSpinEventListener/ setLongClickListener;
};
#define EVENTCTRLHELPER EventCtrl::GetInstance()
```
### UI 接入示例（mainLogic.cc）
```cpp
void MainKnobReport(Knob_Report msg){
  switch (msg.type) {
    case EVENT_KET_DOWN: key_down = GetBootTimestampMs(); break;
    case EVENT_KET_UP:   // 时间差判长按 → DealLongClick
    case EVENT_KET_CLOCKWISE:  EVENTCTRLHELPER->DealSpinEvent(&Clockwise); break;
    case EVENT_KET_COUNTERCLOCKWISE: EVENTCTRLHELPER->DealSpinEvent(&Counterclockwise); break;
  }
}
void onUI_init(){ start_key_event_ctx(); set_knobp_report_listener(MainKnobReport); }
```

## ⛔ 铁律
1. GameMainThread.cpp 残缺，libretro 运行线程实现以 RetroArch 官方集成示例 + 头文件接口为准
2. core 用开源 libretro 模块编译（RetroArch/开源模拟器），方案对外销售
3. 渲染软件 memcpy + 硬件 G2D（TextView→屏幕），30fps 满足；别在软件层做缩放
4. mi_*（mi_gfx/mi_ao/mi_sys）= SigmaStar 专有，全志平台换对应接口
5. **芯片支持（需求方确认）**：SSD201/SSD202、T113 等，FlyThings OS 平台理论上都支持（工程基于 SSD20x，移植改音视频/显示层）
6. **ROM（需求方确认）**：SDCard 扫描到数据库；公司不提供 ROM，客户自己授权/提供
7. 旋钮 input 节点**不是写死**（event68/event1 只是示例），按实际项目定；可代码自动扫描 /dev/input 匹配旋钮设备
8. 旋钮旋转值 14/7、13/11 是配对判定，异常可调；长按/双击在 MainKnobReport 用时间戳自己实现；移植拷 Knob/ + dealevent/ 两目录
