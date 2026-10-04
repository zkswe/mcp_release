---
id: uicontrols-button-fields
title: Button 按键控件 JSON 字段规范 + 长按/循环重复配置
category: uicontrols
status: review
confidence: manual
verified_at: 2026-09-29
stale_days: 180
origin: total
source: 2026-09-29 front-matter 迁移（P1：先显式登记"待补可执行判据"）
needs_evidence: true
platforms: []
tags: [循环重复时间通过 UI, IDE 属性表, 可配, button, ui, 1024x600, 137 button]
evidence: []
---
# Button 按键控件 JSON 字段规范 + 长按/循环重复配置

> 检索导引：问「按钮怎么做 / Button 有哪些 json 字段 / 长按时间怎么配（longClickTimeOut·longClickIntervalTime）/ 图标与文字怎么排（iconPosition）/ 五态图 picTab」→ 本文；按钮图片铁律见 `knowledge/devflow/ui-asset-rules.md`。
> **口语问法直达**：按钮点击回调函数叫什么名字（`onButtonClick_Caption`，见文末「回调」）/ 点一下的回调函数名 / 点击走哪个函数。
> 2026-09-08 需求方确认学习：长按触发时间/循环重复时间通过 UI（IDE 属性表）可配。校准源：官方 wiki uicontrols/button.md + SampleUI-New/ui/1024x600（137 button）+ basedemo ButtonDemo-New/ImeDemo-New ftu 反解。

## JSON 字段全集（SampleUI 1024x600 实证频率）
| 字段 | 出现率 | 说明 |
|------|--------|------|
| id/caption/position/alignment/colorTab/picTab/text | 100% | 必写（见 json-field-mandatory.md，touchable true 另加） |
| iconPosition | 98.5% | 图标在按钮内锚点（图标+文字布局用） |
| **longClickTimeOut**| 97.8% | **长按事件触发时间(ms)**：>0 启用长按，默认 -1 = 不启用（134/137 为 -1） |
| **longClickIntervalTime**| 97.8% | **长按事件循环触发间隔(ms)**：>0 = 长按期间循环重复触发；-1 = 仅触发一次不循环 |
| fontSize/bold/italic/bgColorTab/backgroundColor/visible/textPosition/roll* | 97.8% | 文字/背景/滚动属性 |
| fontFamily | 89% | 字体族（0=默认） |
| beepEnable | 8.8% | 按键音（需要才写，非必写） |
| charsetTab | 0.7% | 指定字符用图片渲染 |

## ⚠️ 长按模式：UI 配置 ↔ json ↔ 代码（2026-09-08 确认）
**IDE 属性表两个属性（单位 ms）**：
- **长按事件触发时间**→ json `longClickTimeOut`（按住多久判定为长按并触发）
- **长按事件循环触发间隔时间**→ json `longClickIntervalTime`（长按不松手时，每隔多久重复触发一次 onLongClick）
- 默认 -1（两键都 -1 = 不启用长按，普通点击）；要启用必须显式给 >0 值

**实测真源值**（basedemo）：
- `ButtonDemo-New` LongButton：`longClickTimeOut:1000, longClickIntervalTime:1000` —— 长按 1s 触发，之后每 1s 循环触发（官方示例一致，onLongClick 每次触发都调用，适合音量/加减速连续调节）
- `ImeDemo-New` 删除键 BUTTON_DEL/BUTTON_NUMBER_DEL：`longClickTimeOut:600, longClickIntervalTime:-1` —— 600ms 快启长按，不循环

**代码三件套**（官方 button.md）：
```cpp
namespace {  // 匿名作用域防多文件类名冲突
class LongClickListener : public ZKBase::ILongClickListener {
    virtual void onLongClick(ZKBase *pBase) override {
        LOGD("长按触发（含循环重复）");   // 每次触发都回调
    }
};
}
static LongClickListener gLongListener;      // 静态实例

static void onUI_init() {
    mLongButtonPtr->setLongClickListener(&gLongListener);   // 注册
}
static void onUI_quit() {
    mLongButtonPtr->setLongClickListener(NULL);             // 注销
}
```
- 监听器基类：`ZKBase::ILongClickListener`；回调 `virtual void onLongClick(ZKBase *pBase)`（点击是 IClickListener::onClick）
- 循环重复时 onLongClick 按 interval 反复调用（ButtonDemo 例：文字里「触发次数 ++」可见每次重复都 +1）

**适用控件**：button / listview item.subItem / item（ZKBase 体系通用；subItem/listitem 模板已含 longClickTimeOut/longClickIntervalTime 键）
**典型场景**：音量/亮度/温控连续加减（interval 循环连发）、键盘删除键长按（600ms 快启）、列表项长按菜单

## 图片按钮铁律（勿忘）
- **缺图不致命但属验收缺陷**：`picTab.pic0~picN`/`backgroundPic` 指向不存在的文件 →
控件不可见/无图（framework 容错，不会挂死）；图没出好就删 picTab 条目/置 `''`
  （纯文字按钮可正常工作），只写已落盘的图。
  ⛔ 子盒对象字段（如 `seekbar.thumb`）**必须写成对象**——规格与症状见 `seekbar-fields.md` §0，本页不重复。
- 有按键图片（picTab/backgroundPic）时**不开 bgColorTab**（图片叠底色效果错乱）；仅纯文字按钮用 bgColorTab/colorTab 多态色
- 多态图 picTab：pic0 正常 / pic1 按下 / pic2 选中 / pic3 选中按下 / pic4 无效；两态开关 picTab{pic0:on, pic2:off}+setSelected()
- 图标按钮 iconPosition 指定图标区（控件尺寸≠图片尺寸时必须显式）；控件尺寸与图片一致

## 回调（logic.cc）
`bool onButtonClick_Caption(ZKButton*)` 单击（return false）；长按走上面 LongClickListener（不是 onButtonClick）

## 相关
- 必写键全集：knowledge/uicontrols/json-field-mandatory.md；层级：json-layer-rules.md；官方 wiki uicontrols/button.md
