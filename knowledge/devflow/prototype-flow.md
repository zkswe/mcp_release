# 🏗️ 一句话需求 → 线框确认 → UI 美化 流程（沛哥定规 2026-09-02）

> 用户一句话描述产品（如「我想设计一个医疗口腔内窥镜」——**仅为示例，流程适用于任何产品**）→
> **自动拆解功能点 → HTML 线框图（单 HTML 多页面 + 标注）→ 用户确认 → 多套风格美化 → 确认 → 转换交付**。
> 两段式：线框确认 = 确认「做什么」，美化 = 确认「长什么样」。

---

## 总览

```
一句话需求 ──→ ① 功能拆解 ──→ ② 页面层级设计 ──→ ③ HTML 线框图 ──→ ④ 用户确认
（文字输入）    功能清单+确认清单   页面树            wireframe.html    ✅ 确认清单+线框
                                                                      │
                                                    未通过 ←── 反馈修改（回②③，带标注多轮沟通）
                                                                      ▼
                       ⑤ UI 美化（3+ 套风格）──→ ⑥ 风格选择 ──→ ⑦ 美化稿预览 ──→ ⑧ 确认
                                                                                      │
                                                                                      ▼
                                                                     ⑨ html2json → pack → 交付
```

---

## ① 功能拆解（AI 分析）

按硬件产品典型维度拆：核心功能 / 数据管理 / 设置 / 辅助功能。
**产出两份**：功能清单 JSON（AI 用）+ **确认清单**（给客户看：产品名/模块数/功能点数/建议页面数）。

```json
{"product": "医疗口腔内窥镜",  // ⚠️ 仅示例：按用户实际产品拆解
 "modules": [
   {"id":"preview","name":"实时预览","features":["视频实时显示","拍照","录像","亮度/聚焦调节","画面翻转"]},
   {"id":"album","name":"影像回放","features":["图片列表","视频播放","删除/重命名","导出"]},
   {"id":"settings","name":"系统设置","features":["WiFi配网","分辨率选择","存储管理","关于"]},
   {"id":"patient","name":"病例管理","features":["患者建档","检查记录","报告生成"]}
 ]}
```
> 拆解维度参考：核心功能 / 数据管理 / 设置 / 辅助功能（按产品类型调整，不套模板）

## ② 页面层级设计（信息架构）

输出页面树（层级 + 跳转），每页分配 `page-id`（英文短名，后续分页/回调命名用）：

```
home（首页/主入口）
├── preview（实时预览页）— 主功能页
│   ├── 拍照/录像工具栏
│   ├── 图像调节弹窗
│   └── 连接状态栏
├── album（影像回放页）
│   └── detail（影像详情页）
├── patient（病例管理页）
│   ├── list（患者列表）→ detail（患者详情/检查记录）
│   └── report（报告生成）
└── settings（设置页）
    ├── network（WiFi 配网）
    ├── display（显示设置）
    └── storage（存储/关于）
```

## ③ HTML 线框图（单 HTML 多页面 + 标注，核心）

### 结构规范（单 HTML 预览所有功能，data-page 区分，AI 后续按此分页）

一个 `wireframe.html` 含全部页面，每页一个 `.screen`，**HTML 注释 + data-page 明确区分**：

```html
<!-- ===== PAGE: home 首页（主入口）===== -->
<div class="screen" data-page="home" data-page-name="首页" data-res="800x480" data-bg="#808080">
  <div class="text" data-caption="TitleBar" data-x="0" data-y="0" data-w="800" data-h="48"
       data-note="顶部标题栏：产品名/当前页名">医疗口腔内窥镜</div>
  <div class="btn" data-caption="BtnPreview" data-x="40" data-y="120" data-w="320" data-h="80"
       data-goto="preview" data-note="进入实时预览页">▶ 实时预览</div>
</div>

<!-- ===== PAGE: preview 实时预览页 ===== -->
<div class="screen" data-page="preview" data-page-name="实时预览" data-res="800x480" data-bg="#808080">
  ...
</div>
```

### 标注规范（支持多轮交互/UI 沟通修改）

- **页面标注**：`.screen` 前注释 `<!-- ===== PAGE: xxx 页面名 ===== -->` + `data-page`（id）+ `data-page-name`（中文名）
  → AI 后续按 `data-page` 分页生成独立 json/ftu
- **控件标注**：每个控件加 `data-note`（一句话说明功能/交互意图）→ 多轮沟通时客户指「这个按钮」→ AI 按 caption/data-note 定位修改
- **交互标注**：可交互控件加 `data-goto="目标page"` → 示意跳转关系，后续 logic 回调按此实现
- **线框风格**：灰阶（#808080 系）、无图片、方框占位 + 文字标注功能点

### 线框元素映射（HTML_SUBSET 内）

| 元素 | 用途 | data 标注 |
|------|------|----------|
| div.screen | 一个页面 | data-page / data-page-name |
| div.text | 标题/说明文字 | data-note |
| div.btn | 功能按钮/入口 | data-goto / data-note |
| div.list | 列表（相册/患者） | data-note |
| div.input | 输入框（搜索/建档） | data-note |
| div.bar | 进度/状态 | data-note |
| div.modal | 弹窗 | data-note |

## ④ 用户确认（线框轮）

- 交付：`wireframe.html`（浏览器打开）+ **确认清单**（① 产出）
- 确认点：① 页面齐全 ② 层级/跳转正确 ③ 功能点覆盖
- **多轮沟通**：客户反馈带控件标注定位（「拍照按钮改右上角」「加录像时长显示」）→ 按 data-note/caption 定位改 HTML → 重新预览，循环至确认
- 确认后锁定页面结构 → 美化轮

## ⑤ UI 美化（多套风格方案，沛哥决策）

在已确认线框 HTML 上生成 **3 套以上风格方案**供客户选择。

**⚠️ 风格不固定模板——根据实际产品行业/场景定制**（沛哥 2026-09-02 补充）：
- 医疗/专业设备 → 科技蓝、纯净白、深色专业等（示例方向）
- 消费电子/家用 → 明亮活泼、圆润卡片、暖色亲和等
- 工业/车载 → 高对比、深底亮字、大控件触控友好等
- 智能家居 → 简约、浅色、无边框大留白等
- 具体方案由 AI 结合产品定位提出，不套固定 4 套

每套 = 同结构不同配色/字体/图标的 HTML 效果稿（可含 CSS 渐变/阴影，html2json 自动转图）
客户选一套（或混合微调）→ 确定美化稿

## ⑥⑦⑧ 美化稿确认 + 转换交付

1. 选中风格美化稿 → 客户预览确认细节（按钮态/间距/图标）
2. `flythings_html_to_json` → `ui/*.json`（**按 data-page 分页生成多个 json，每页一个**）
3. `flythings_generate_ui_preview` 出预览稿
4. `flythings_fui_pack` → ftu；`flythings_build_ui_flow` → build + launch
5. 交付

---

## 关键决策（沛哥 2026-09-02 拍板）

| # | 决策 | 方案 |
|---|------|------|
| 1 | 确认清单 | ✅ 需要：产品名/模块数/功能点数/页面数 |
| 2 | 语音输入 | 不做，文字输入（语音二期可加 Web Speech API） |
| 3 | 页面组织 | 单 HTML 多 .screen，data-page 区分，AI 后续按此分页 |
| 4 | 美化风格 | 3+ 套方案客户选择（**按实际产品定制，不套固定模板**） |
| + | 标注信息 | 页面注释 + data-page + data-note + data-goto，支持多轮修改 |

## 落地工具

- 流程本文件入库：AI 检索 `prototype` / `线框` / `wireframe` / `功能拆解` / `页面层级` 关键词触发
- 转换：`flythings_html_to_json`（美化稿，data-page 分页）→ preview → pack → build_ui_flow
