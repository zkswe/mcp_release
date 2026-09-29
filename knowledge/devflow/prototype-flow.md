---
id: devflow-prototype-flow
title: 🏗️ 一句话需求 → 线框确认 → UI 美化 流程（沛哥定规 2026-09-02）
category: devflow
status: verified
confidence: manual
verified_at: 2026-09-29
stale_days: 180
origin: total
source: 2026-09-29 front-matter 迁移（P1：先显式登记"待补可执行判据"）
needs_evidence: true
platforms: []
tags: [新需求, 开发一个, 做一个, 写一个, 实现, 需求拆解, 功能拆解, 原型设计, 界面设计, 设计稿]
evidence: []
---
# 🏗️ 一句话需求 → 线框确认 → UI 美化 流程（沛哥定规 2026-09-02）

> 检索导引：问「新项目从哪开始 / 一句话需求怎么变成界面 / 线框图怎么给用户确认 / 要出几套风格 / 需求里带设计稿先做什么」→ 本文（原型确认流程总纲）；带稿后的分辨率对齐硬规则也在文末。
> 检索词（用户问法与 AI 检索都命中这里）：新项目 / 新需求 / 开发一个 / 做一个 / 写一个 / 实现 /
> 需求拆解 / 功能拆解 / 原型设计 / 界面设计 / 设计稿 / 设计图 / 参考图 / 线框图 / wireframe /
> 流程图 / 确认稿 / HTML 原型 / 智能家居 / 面板 / 屏保 / 温湿度 / 天气 / MQTT / 情景联动 /
> 多页面 / 页面树 / 一页一 Activity。
>
> ⚠️ 硬口径（钟工 2026-09-21 口径 A）：用户提「新项目/新需求」却**没给**流程图或 UI 设计图时，
> AI **必须先走本流程**（功能拆解 -> 页面树 -> 线框图 -> 确认稿 -> 用户确认），
> **禁止直接 flythings_create_project 或写业务代码**；请求里已带设计稿（设计图 / HTML 原型 /
> 布局 json / ftu）的，先按稿还原并出确认稿给用户确认，确认后再 pack / 写逻辑。
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

### ⚠️ 分页落地清单（硬规则：第 ③ 步的 N 个 .screen，第 ⑨ 步必须 N 页全落地）

★ 这是本流程最容易出错的一步（2026-09-21 修的实际事故：多屏设计稿只生成了一个页面，
因为转换器只取**第一个** `.screen`）。清单如下，缺一步就是交付事故：

1. **数屏**：第 ③ 步产出多少屏（`wireframe.html` / 美化稿里并列 `div.screen` 的个数）就记下 N，
   并逐屏写下 `data-page`（后续文件名、回调命名都靠它）；
2. **AI 逐屏判定归属**（这一步是 AI 的活，不是工具的活；钟工 2026-09-21 口径：哪些属于不同
   Activity、哪些属于同屏内 window/dialog，**前期 AI 就可以分清楚**）：
   - **不同的 Activity** -> 每屏各自一个 `.screen`，转换后**各自一个 json / 一个 ftu**
     （html2json **缺省**口径，不用带参数）；
   - **同一个 Activity 内部的弹窗/浮层（window / dialog）** -> 写在**该屏 `.screen` 里面**
     （`div.window` / `div.modal`），它们是这一页的显隐元素，**不另占一页**；
   - 例外的合并形态（**仅当 AI 判定这几屏同属一个 Activity**、就是同 ftu 内叠多个整屏 window 时）：
     `flythings_html_to_json` 传 `merge_windows=true`（CLI `--merge-windows`）合成一个 json；
3. **转 + 核屏数**：`flythings_html_to_json` 返回的 `screensDetected` / `pagesProduced`
   **必须相等且 == N**（缺省口径下 json 数也 == N，看 `jsonsProduced` / `pages[]`）；
   不等就是 `success:false`，先修 HTML（别往下走）；
4. **预览逐页看**：`flythings_ui_preview` 出来的确认稿要能**切到每一页**
   （多 json 用项目页面行；合并形态用页面切换条 / `#window__N` 直达），不能只看到首页；
5. **交付前核对**：**设计稿 N 屏 <-> 产出 N 页（= N 个 json）**（合并形态则是 1 个 json 内 N 个整屏
   window），对不上 = **FAIL**，不许交付。

> 工具口径：html2json 返回体带 `screensDetected`/`pagesProduced`/`jsonsProduced`/`pages[]`，
> 前两者不等一律 `success:false`；**缺省 = 一个 `.screen` = 一个页面 = 一个 Activity = 一个 json**，
> 合并且仅当同属一个 Activity 时才用 `merge_windows=true`。屏数 = 页数才是合格物。
> HTML 写法与两种形态的完整说明见 `ui_tools/HTML_SUBSET.md`「多屏」节。

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
  - 落地时按 `data-page` 定页 id：**缺省形态 = json 文件名**（**必须唯一**，重复即报错）；
    合并形态（`merge_windows=true`，仅同属一个 Activity 时）= 该整屏 window 的 `caption`
  - 该页自己的弹窗/浮层用 `div.window` / `div.modal` 写在**这个 `.screen` 里面**，不新起 `.screen`
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
2. `flythings_html_to_json` → `ui/*.json`（**页数 = 屏数**）：同业务域多页直接转 = 一个 json 内多个整屏
   window；缺省（每屏一个 json）不用带参数，AI 逐屏判定归属后再转；无论哪种都先看
   `screensDetected` / `pagesProduced` 是否相等（见上「分页落地清单」）
3. `flythings_ui_preview` 出预览稿
4. `flythings_fui_pack` → ftu；`flythings_build_ui_flow` → build + launch
5. 交付

---

## 关键决策（沛哥 2026-09-02 拍板）

| # | 决策 | 方案 |
|---|------|------|
| 1 | 确认清单 | ✅ 需要：产品名/模块数/功能点数/页面数 |
| 2 | 语音输入 | 不做，文字输入（语音二期可加 Web Speech API） |
| 3 | 页面组织 | 单 HTML 多 .screen，data-page 区分，AI 后续按此分页（**页数 = 屏数，一屏不许丢**） |
| 4 | 美化风格 | 3+ 套方案客户选择（**按实际产品定制，不套固定模板**） |
| + | 标注信息 | 页面注释 + data-page + data-note + data-goto，支持多轮修改 |

## 落地工具

- 流程本文件入库：AI 检索 `prototype` / `线框` / `wireframe` / `功能拆解` / `页面层级` 关键词触发
- 转换：`flythings_html_to_json`（美化稿：**缺省每屏一个 json = 一个页面一个 Activity 一个 ftu**；仅当几屏同属一个 Activity、要合成同 ftu 内多整屏 window 时才传 `merge_windows=true`）-> preview -> pack -> build_ui_flow
- 口径：多屏落地形态判据 = `page-architecture-spec.md`；屏数核对 = 本文件「分页落地清单」与 `ui_tools/HTML_SUBSET.md`「多屏」节

---

## 已提供设计稿时：先匹配平台与分辨率（硬规则，钟工 2026-09-21 拍板）

检索词：已提供设计稿 / 有设计稿 / 设计图 / 原型稿 / 匹配硬件平台 / 分辨率不一致 / 缩放适配 / scale_audit / rotateScreen / 分辨率选择

用户**已经给了设计稿**（UI 图 / 流程图 / HTML 原型 / 布局 json / ftu）时，**跳过 ①~③ 的线框阶段**，但**必须**先做下面三件事，再动手写工程与逻辑：

1. **匹配硬件平台 + 屏幕物理分辨率与方向**
   - 先确认目标平台：Z20 / F133 / Z21 / T113 / V85x / SSD20x ...
   - 再确认**屏幕物理分辨率 + 方向**（`rotateScreen`）。例：F133 面板物理 800x1280 竖屏 + `rotateScreen=270` -> UI 坐标 1280x800（`references/kb/devices.md`、`easyui-cfg` 口径）。
   - **平台或分辨率没确认，不许开始建工程 / 写逻辑。**
2. **分辨率必须对齐（不一致就走适配并审计）**
   - 设计稿分辨率 == 平台分辨率 -> 按稿直接还原。
   - **不等** -> 走分辨率适配口径（`references/kb/resolution-scaling.md`），并用 `tools/qa/scale_audit.py` 审计：**FAIL 必须 0**；**满宽/满高/发丝线类元素**触发人工评审；缩放只允许明确规则（先乘后除，避免累积误差），保留可核对差异清单。**禁止擅自拉伸糊过去。**
3. **出确认稿再动手**
   - 按稿还原 -> `flythings_ui_preview` 出**确认稿**（只出预览，**不 pack**）-> 用户确认 -> `flythings_create_project(platform, resolution)`（**平台+分辨率必须与确认过的一致**，方向写进 `EasyUI.cfg`）-> pack / 写逻辑 / 验收。
