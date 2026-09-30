---
id: devflow-custom-widget
title: FlyThings 自定义控件方法（lib-ext_widgets 拆解）
category: devflow
status: review
confidence: manual
verified_at: 2026-09-29
stale_days: 180
origin: total
source: 2026-09-29 front-matter 迁移（P1：先显式登记"待补可执行判据"）
needs_evidence: true
platforms: []
tags: [F136, 2026-09-03 拆解, 草稿待确认入库, ⚠️ 内部代码, 方法论文档只提炼模式与骨架, 不整段复制实现]
evidence: []
---
# FlyThings 自定义控件方法（lib-ext_widgets 拆解）

> 检索导引：问「想做一个平台没有的控件 / 自定义控件怎么写 / 继承 ZKBase / onDraw 自绘 / 控件触摸事件重写 / 有没有现成自创控件可抄」→ 本文；先看缺什么控件见 `devflow/gui-controls-gap.md`，交付形态见 `devflow/reusable-components.md`，**能力边界总纲见 `devflow/render-extension-boundary.md`**。
> 来源：内部私有仓库 `guoxs/lib-ext_widgets`（LearningProject 本地副本，F136/F133 + easyui ^2.3.0），
> ZKSWE Develop Team 2024-2025 系列自研控件。2026-09-03 拆解，草稿待确认入库。
> ⚠️ 内部代码，方法论文档只提炼模式与骨架，不整段复制实现；新控件做时按需回工程精读对应控件。

## 0. 一句话方法

**FlyThings 自定义控件 = 继承 `ZKBase`（easyui 控件基类）→ 空 `create(Json::Value())` 纯代码实例化 →**
**组合基础控件 或 重写 `onDraw` 自绘 → 暴露 build(attr)/setXxxAdapter() 由使用方驱动 →**
**页面 onUI_init `new Xxx(父容器Ptr)` 挂载、onUI_quit `delete` 释放。**

控件不进 ftu/IDE，是纯 C++ 类；使用方代码 new 到 ftu 里已有容器（ZKWindow*）上。
参考库内 8 个成品：AlbumListView / FrameImageView / ImageBoxView / ImageEditView /
RotateImageView / SliceProgressBar / PullWidget（+BaseView 基类），每个配独立测试 Activity。

## 1. 基类（BaseView，所有控件的父类）

```cpp
class BaseView : public ZKBase {
public:
    BaseView(ZKBase *parent) : ZKBase(parent) {
        create(Json::Value());                       // ① 空 json 创建（非 ftu 实例化）
        const LayoutPosition &pos = parent->getPosition();
        setPosition(LayoutPosition(0, 0, pos.mWidth, pos.mHeight));  // ② 默认铺满父容器
    }
protected:
    ZKButton* createButton(ZKBase *parent = NULL);   // 创建子按钮（默认隐藏不可点，作画布/热区）
    bitmap_t* createBmp(int w, int h, int bpp = -1); // 内存画布：/tmp 写 BMP 头→BitmapHelper 加载→删文件
    void clearBmp(bitmap_t *bmp, uint32_t color = 0);// 清画布（0=快速 memset；支持 24/32 位填色）
};
```
要点：
- **`create(Json::Value())` 是关键**——所有 easyui 控件都支持"代码创建"（json 传空对象走默认值），
  不依赖 ftu 反序列化；`ZKButton`/`ZKBase` 等都能这么 new
- 子控件构造也要 `create(Json::Value())`；按钮默认 `setVisible(false)+setTouchable(false)`，
  用的时候再开（很多控件拿按钮当"可放图、可点、可换态的通用矩形"用）
- 画布：`createBmp` 生成一个 `bitmap_t` 内存位图（透明/填色/直接操作 data），
  配合 `ZKButton::setBackgroundBmp` 之类显示——自绘控件的基本素材

## 2. 两条实现路线

**路线 A：组合式（子控件拼装）**——适合能拆成标准控件的（进度条/按钮组/列表）
- 例：SliceProgressBar 内部维护 `std::vector<ZKButton*>`，每个切片 = 一个 createButton()
  + `setButtonStatusPic(NORMAL/SELECTED, 图标)` + 按图片尺寸 setPosition
- setProgress(i)：前 i 个 visible、第 i 个 selected（光标态）、其余隐藏——纯状态切换，无需自绘
- 例：AlbumListView（复杂组合）——头部 head_list_（ZKButton*）+ item_list_（内部 Item 类，
  Item 又含 sub_item_count 个 ZKButton**）全用基础控件拼，滚动/回弹用触摸驱动 setPosition/move

**路线 B：自绘式（重写 onDraw）**——适合基础控件表达不了的（帧动画/特殊形状/图像处理）
- 例：FrameImageView 重写 `virtual void onDraw(ZKCanvas *pCanvas)`，把解码好的 `bitmap_t`
  按帧画到控件上（配合 Region 脏区只重绘变化区域）
- 自绘需要拿到画布：onDraw 里用 ZKCanvas API + 预解码 bitmap_t；解码放后台线程
  （MessageQueueThread），完成后再触发重绘

## 3. 与页面/布局的关系（使用方视角）

```cpp
// xxxLogic.cc  (ftu 里放一个占位 ZKWindow* mWindow1Ptr)
#include "ui/SliceProgressBar.h"
static ui::SliceProgressBar *test_bar;

static void onUI_init() {
    test_bar = new ui::SliceProgressBar(mWindow1Ptr);   // 挂到 ftu 容器
    test_bar->build(CONFIGMANAGER->getResFilePath("slice_bar"));  // 构建内容
}
static void onUI_quit() {
    delete test_bar;                                    // 必须释放
}
```
- **父容器**：ftu 里已有的控件（常用 ZKWindow）作 parent；控件构造自动铺满 parent 区域
- 页面切换 openActivity 时 onUI_quit 释放；重复进入每次 new（不能 static 复用跨页面）
- 控件回调到页面：控件不直接认识页面，页面持有控件指针（如 test_bar）直接调 setProgress；
  控件→页面用函数指针 setter（适配器）或控件自己发事件/回调

## 4. 配置与数据：Attr 结构 + 适配器回调（控件不自带业务）

**Attr 聚合配置**（构建参数，例 AlbumListView::Attr 有 30+ 字段：间距/头/item 尺寸字体颜色/
列行数/滚动条/缓存/长按…）——控件外观行为全用结构体一次 build(attr) 配置，
**不做 json 属性解析**（纯代码控件没有 ftu 属性通道），需要持久化时使用方自己存 json。

**适配器回调**（数据驱动，List 类控件标配）：
```cpp
typedef void (*func_get_item_count_list)(AlbumListView*, std::vector<int>&);
typedef void (*func_obtain_item_data)(AlbumListView*, ZKButton* head, int head_index,
                                      AlbumListView::Item& item, int item_index);
typedef void (*func_click_listener)(AlbumListView*, int head_index, int item_index,
                                    int sub_index, bool long_click);
view->setDataAdapter(get_list, obtain);   // 数据来源
view->setClickListener(listener);         // 交互结果
view->refresh();                          // 刷新 → 触发回调
```
模式：控件只负责 布局/滚动/回收/命中/动画；内容由使用方在 obtain 回调里填。
⚠️ obtain 回调里禁耗时（滚动逐项调用）——图片加载走缓存适配器或异步。

## 5. 触摸/手势（onTouchEvent 重写）

```cpp
virtual bool onTouchEvent(const MotionEvent &ev);   // 返回 true=吃掉事件
// ev.mActionStatus: E_ACTION_DOWN/MOVE/UP/CANCEL; ev.mX/mY 相对控件；ev.mEventTime
```
- 滚动实现套路（AlbumListView/ImageBoxView）：DOWN 记录 down_event_+位置 → MOVE 计算位移
  setPosition/move 平移内容（或 offset）→ UP 判断惯性：VelocityTracker 算速度 → is_rolling_
  定时器逐步减速滚动 → 越界回弹（is_damping_ + 阻尼系数）→ 长按计时（long_click_timeout）
- 全局触摸监听：Activity 层 `registerGlobalTouchListener`（测试页手势），控件内不必要
- **多指触控**：src/event/multi_touch.* 提供全局多点触摸分发（TouchPoint 列表回调），
  ImageBoxView 用它实现双指缩放（prepareScale/processScale：两指距离比例 → setPosition 缩放）
- 控件内定时器：`onTimer(int id)`（页面注册的定时器框架会分发？——见各控件：滚动/回弹/
  动画步进都在 onTimer 里做，id 用控件内私有 id）

## 6. 绘制基础（bitmap_t + Region）

> ⚠️ **刷新触发口径（2026-09-22 钟工定规）**：自定义 view（自绘/帧渲染/位图自己改的那类）每帧刷新用
> `ctrl->setInvalid(!ctrl->isInvalid())`（gameview 口径）；**不要**用 `invalidate(&getAbsolutePosition())`
> 传绝对矩形（会被按控件本地坐标裁成“右下角一块”，屏上只刷一块）→ 详见 `uicontrols/custom-view-refresh.md`。

- `bitmap_t`：easyui 位图结构（width/height/pitch/bytes/data），`BitmapHelper::loadBitmapFromFile`
  解码文件、unloadBitmap 释放；createBmp 造内存画布后直接操作 data（24 位 BGR / 32 位带 alpha，
  `bmp->type |= 0x01` 透明）
- 控件显示位图：子 ZKButton `setBackgroundBmp(bmp)`（或 setBackgroundPic 文件）——**这就是平台的 canvas 画布扩展**：
  `ZKTextView`/`ZKButton` 挂一张内存位图当画布，只调一次 + `setInvalid(!isInvalid())` 交替刷帧；
  控件不自绘时用按钮当"图框"最省事。能力边界（三层模型 / 非 3D GPU 皆可 / 软模拟）见 `devflow/render-extension-boundary.md`，
- `Region`（left/top/right/bottom + 宏：SET/RESET/IS_EMPTY/OFFSET/CONTAINS/DOES_INTERSECT/
  Intersect/Bound）——脏区/裁剪/命中通用；typedef.h 里 EImageShowMode/EMotionFilter/枚举风格库内统一

## 7. 异步（MessageQueueThread，misc/）

- 解码/加载大图/文件 IO 放 `MessageQueueThread`（投递消息到工作线程），避免阻塞 UI 线程
  （FrameImageView 帧解码、ImageBoxView 预加载、AlbumListView 图片缓存都靠它）
- 控件持有线程要处理退出（exit_flag_ + join），析构时安全释放
- image_cache.*（LRU 图片缓存）/ bitmap_utility / image_utility / text_utility 是控件通用工具层

## 8. 资源驱动构建（约定优于配置）

SliceProgressBar::build(res_dir)：扫目录 `*normal.png` 自动建切片，文件名即配置：
`<序号>.<x>x<y>_normal.png`（如 `0.10x10_normal.png`）+ 同名 `_cursor.png` 选中态——
换皮肤/加切片只换资源不改代码。做新控件可沿用"文件名编码布局"思路。

## 9. 库内 8 控件速览（做什么新控件前先看有没有可抄的）

| 控件 | 路线 | 能力 | 关键 API |
|------|------|------|---------|
| AlbumListView | 组合 | 分头/多子项列表、滚动+惯性+回弹、可拖滚动条、图片 LRU 缓存、长按、全局/局部刷新 | build(Attr)/setDataAdapter/setClickListener/refresh/locateTo/getItemWidget |
| ImageBoxView | 组合+多指 | 图片翻页相框：预加载、滑动切页、双指缩放、裁剪、切换特效(移/缩放/挤压)、循环 | setPageAdapter/setCurrentPage/nextPage/setSwitchEffect |
| FrameImageView | 自绘 | 帧图像播放（解码线程+脏区重绘） | load(dir)/play(index)/getFrameCount |
| ImageEditView | 组合 | 看图编辑（旋转等，typedef EImageEditMode） | 见工程 |
| RotateImageView | — | 旋转图像控件 | 见工程 |
| SliceProgressBar | 组合 | 切片进度条（N 段状态点） | build(三种)/setProgress/getMax |
| PullWidget | 组合 | 下拉部件 | 见工程 |
| BaseView | 基类 | createButton/createBmp/clearBmp | 所有控件继承 |

## 10. 测试工程规范（做控件标配）

每个控件 = 独立 Activity（ftu 一个容器 Window + 输入/按钮）+ Logic：
- 页面放调试输入（EditText）+ 触发按钮（例：输入进度值→setProgress）+ sys_back
- onUI_init 里 new 控件 + build + 演示数据；onUI_quit delete
- TestCaseActivity 作目录页（列出全部测试入口，openActivity 跳转）
- AlbumListViewCacheTest（开缓存版）/ AlbumListViewTest（普通版）双页面对比

## 11. 新控件开发 checklist（按此流程可稳定产出）

1. 想清楚交互/数据：拆成"控件职责（布局/手势/回收/动画）"与"内容（适配器回调）"
2. 能组合就用基础控件拼（路线 A，省事稳定）；画不了再自绘（路线 B onDraw）
3. 建类：`class XxxView : public ui::BaseView`（或 ZKBase），构造 `create(Json::Value())` 铺满父容器
4. Attr 聚合配置结构 + `build(attr)`（或 build(res_dir) 资源驱动）；默认值给好
5. 数据/事件出口全部函数指针 setter（setXxxAdapter/setXxxListener），禁控件内写业务
6. 手势：onTouchEvent 处理 DOWN/MOVE/UP；惯性用 VelocityTracker + 定时器；多指用 event::multi_touch
7. 重活（解码/加载）丢 MessageQueueThread，完成回 UI 刷新；析构安全停线程
8. 图片显示优先子按钮 setBackgroundBmp/Pic；确需自绘再 onDraw + Region 脏区；
   **每帧刷新的触发按 `uicontrols/custom-view-refresh.md` 的 `setInvalid(!isInvalid())` 口径写**
9. 配独立测试页（输入控件驱动 + 演示数据），跑真机/模拟器验证手势与刷新
10. 页面内 new/delete 生命周期严格配对；obtain 回调禁耗时
