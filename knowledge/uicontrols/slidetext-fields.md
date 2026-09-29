---
id: uicontrols-slidetext-fields
title: SlideText 滑动文本控件 JSON 字段规范
category: uicontrols
status: verified
confidence: manual
verified_at: 2026-09-29
stale_days: 180
origin: total
source: 2026-09-29 front-matter 迁移（P1：先显式登记"待补可执行判据"）
needs_evidence: true
platforms: []
tags: [2026-09-07 git, ImeDemo-New, KaiduZ9, Z9S 拼音输入法候选词条, 实测, 可滑动, 点击某个单元回调, 横向选项条]
evidence: []
---
# SlideText 滑动文本控件 JSON 字段规范

> 检索导引：问「横向文本单元滑动条怎么做 / 输入法候选词控件 / setTextList 灌数据 / onTextUnitClick 点选回调 / 和跑马灯 textview 的区别」→ 本文。
> 2026-09-07 git.com 全库学习 + basedemo/ImeDemo-New（KaiduZ9/Z9S 拼音输入法候选词条）实测。
> 场景：一串文本单元横排、可滑动、点击某个单元回调（典型：输入法候选词、横向选项条）。

## 核心铁律

1. **SlideText = 横向可滑动文本单元列表**：`setTextList(vector<string>)` 灌入文本数组，控件内部把每项当独立"文本单元"横排，支持滑动惯性（VelocityTracker）、点击命中、边界阻尼。
2. **典型用途 = 拼音输入法候选词条**（ImeDemo/KaiduZ9S 实测）：`im_search()` 出候选汉字数组 → `setTextList(hanZiList)`；点候选词 → `onTextUnitClick(pSlideText, text)` 自动回调，**回调里自行处理选中逻辑**（addStr + clearPinyin），非自动上屏。
3. 点中某项的回调只给文本内容，不给 index；需要 index 自行从列表里查。
4. 与 textview 的 rollEnable（单条文字跑马灯滚动）**不同**：SlideText 是多单元滑动选择器。

## JSON 字段表（ImeDemo SLIDETEXT_HANZI 实测）

| 字段 | 类型/取值 | 说明 |
|------|----------|------|
| `caption` | string | 控件名（实测 `SLIDETEXT_HANZI`） |
| `id` | int | 控件 id（实测 **51000** 段） |
| `alignment` | int | 文本对齐 |
| `fontSize` | int | 字号（实测 40，候选词大字体） |
| `textBgColor` | int | 文本单元（高亮/按下）背景色。**透明必须写 -1**；`0` = **不透明黑**，不是透明（2026-09-20 M6 更正：旧文误写「0=透明」，实机按 0 会画出黑块）。官方 ImeDemo 用 `16777215`（白底+黑字）；深色卡片建议走 DESIGN.md 令牌（如 accent 689407）|
| `colorTab` | {color0..4} | 文字颜色（color0=正常） |
| `touchable` | bool | 必须 true 才能点选滑动 |
| `text` | string | 初始单条文本 |
| `position`/`textPosition` | | 位置 |

## 代码操作（ImeDemo/KaiduZ9S 实测顺序）

```cpp
mSLIDETEXT_HANZIPtr->setTextList(hanZiList);   // 灌候选词数组
mSLIDETEXT_HANZIPtr->clearTextList();           // 清空
const std::string &t = mSLIDETEXT_HANZIPtr->getText(0);  // 取某项

class MyListener : public ZKSlideText::ITextUnitClickListener {
  virtual void onTextUnitClick(ZKSlideText *pSlideText, const std::string &text) {
    addStr(sContentStr.length(), text);  // 自行处理选中
    clearPinyin();
  }
};
mSLIDETEXT_HANZIPtr->setTextUnitClickListener(&sListener);
```

## 样例代码
ImeDemo-New（完整拼音输入法：pinyinime 引擎 im_search → setTextList → 点击上屏）；KaiduZ9/KaiduZ9S UserImeLogic.cc 同款。
