---
id: devflow-pixel-analysis-ai
title: 抓帧读图：程序化像素分析 + 像素级渲染坑
category: devflow
status: review
confidence: manual
verified_at: 2026-09-29
stale_days: 180
origin: total
source: 2026-09-29 front-matter 迁移（P1：先显式登记"待补可执行判据"）
needs_evidence: true
platforms: []
tags: [2026-09-10 入库, 必要的做好入库就好了]
evidence: []
---
# 抓帧读图：程序化像素分析 + 像素级渲染坑

> 检索导引：问「不烧 token 怎么看截图 / 字符画读图 / 文字暗带检测 / 坐标要不要换算 / 像素级渲染坑怎么验」→ 本文；抓图见 `knowledge/devflow/device-screenshot.md`，像素 diff 见 `knowledge/devflow/ui-layout-verify.md`。
> 口语/错说法（用户原话）：列表每行出现黑块怎么修 / 行里一块块的黑、黑色方块 / 列表项发黑有暗条 / 截图上一道道黑带是什么。
> 2026-09-10 入库（来源：外部 skill `flythings-device-screenshot` 与知识库逐条比对后补缺；
> 2026-09-10 21:31「必要的做好入库就好了」）。适用：拿到设备截图后想**不烧 token**地读它。

## 0. 省 token 阶梯（先算、后程序读、最后才给视觉模型）

| 层 | 做法 | 成本 | 能回答 |
|---|---|---|---|
| L1 | 直接读结构化数据（`device_screenshot` 返回的 width/height/pixelOrder、像素值采样） | 0 token | 尺寸对不对、颜色对不对、是不是黑屏/花屏 |
| L2 | **程序化读图**（本文 §1 §2：字符分类图、暗带检测） | 0 token | 屏幕骨架大致长啥样、文字有没有换行/溢出 |
| L3 | `flythings_ui_visual(action="diff")` 像素 diff（容差 ±2 + 抖动补偿） | 0 token | 改前/改后哪里变了（回归） |
| L4 | 视觉模型看图 | 有 token | **语义**（这个图标是不是“设置”） |

→ 先用 L1~L3 定位“哪里不对”，只有需要**语义判断**时才把**差异区小图**（不是整屏）丢给模型。

## 1. 方法一：1 字符 = 1 像素分类图（“看”屏幕但不烧 token）

把帧按块降采样成等宽字符画，每格用 1 个字符表示该块的颜色类别：

- 分类规则（可调）：背景/黑 = `.`；亮度 >200 = `#`；高饱和 → `R/G/B/Y/C/M`；灰（180~210）= `:`；其余 = `+`
- 采样块：先按 `8×16` 试（600×1600 → 75×100 字符 ≈ 3KB，一眼能读完；要更细就用 `4×8`）
- 能直接判的结论：
  - 某区域**整片 `.`**= 没内容（控件没生效 / 被上层遮住 / 图没推上去）
  - 出现**意外 `#` 白块**= 白块/丢图/图片路径错
  - 整屏单色 = 黑屏/花屏/抓错帧（回查 `pan`）
- 优点：AI 读字符画几乎不花 token，但比读整张 PNG 更能看出“骨架对不对”。

## 2. 方法二：文字暗带（bands）检测

文字行在行方向上亮度方差大 → 在控件矩形内逐行统计“非背景像素数”：

- 计数突变的行 = 文字行的起止；连续有内容行 = 1 条 band；**band 数 = 实际行数**
- 三个常用判据：
  1. **换行是否生效**：band 数 == 期望行数
  2. **文字是否溢出控件**：最后一条 band 越过控件 rect 下边界，或被整齐切掉一半（裁字）
  3. **是否空文本 / 字没显示**：0 条 band
- 与 `check_all.py` 的 `_text_min_size()` 互补：**静态查“尺寸够不够”，band 查“真机渲染成几个字几行”**。

## 3. 情况：坐标要换算吗？——缺省不用

`flythings_device_screenshot` 缺省 `rotate='auto'`，输出**已经是项目逻辑方向**（读工程 `EasyUI.cfg` 的
`rotateScreen` 转正）→ 直接按图里坐标点/裁图，**不需要换算**；显式 `rotate=0` 或触摸注入的换算口径
（旋转函数、`rotateTouch` 与 `rotateScreen` 可以不同）→ 见 `knowledge/devflow/package-properties-easyui-cfg.md` §9。

## 4. 像素级渲染坑（改图/改 json 时常踩，全是像素能验的）

| 现象（像素上看） | 根因 | 解法 |
|---|---|---|
| 滑块被裁成“扁方” | seekbar **控件高 < 滑块图高**| 控件高 ≥ 滑块图高 |
| 滑块周围一圈**暗环**| 滑块图自带了灰色描边环 | 切图时别加描边环（要边就靠页面底色/阴影烘进图） |
| 图标边缘发黑/发脏 | 图是**半透明 PNG**却贴在纯色底上 | **纯色底就烘底**（把底色烘进图）；真需要透明装饰件用 **button + picTab**（alpha 混合正确） |
| 圆角背景**四角发黑**| 圆角图四角是透明像素，被渲成黑 | 圆角图**四角烘页面底色**（见 nine-patch-rule.md） |
| listview / item / subItem 出现**黑块**| 填了 `backgroundColor` + `bgColorTab` | **删掉**这两个键 |
| 浅色形状（浅色带/卡片）边界有**断续暗边/亮白点、圆角发毂齿**| 超采样缩回用了 `LANCZOS`（负瓣振铃）→ 反预乘后 RGB 越界；且低对比边界（只差单通道 12 级）靠肉眼/亮度阈值看不见 | 缩回换**面积平均（AREA/BOX）**，详见 `knowledge/devflow/ui-asset-rules.md` 铁律 #10；用 `tools/qa/aa_audit.py --fail` 验（判 `resid_bad`） |

## 5. 相关

- 抓屏工具与方向口径：`knowledge/devflow/ui-layout-verify.md`（§2-1）；旋转字段与取图角度口径：
  `knowledge/devflow/package-properties-easyui-cfg.md` §9
- 触摸注入与抓帧时机：`knowledge/devflow/touch-inject-autotest.md`
- 设备端工具缺失（无 grep/sed/head）：`knowledge/devflow/busybox-debug-library.md`
