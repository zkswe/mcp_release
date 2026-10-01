---
id: uicontrols-text-box-height-rule
title: 字号下限与「文本盒抬高度」规则（抬高度只对有文字的盒有效）
category: uicontrols
status: review
confidence: manual
verified_at: 2026-09-29
stale_days: 180
origin: total
source: 2026-09-29 front-matter 迁移（P1：先显式登记"待补可执行判据"）
needs_evidence: true
platforms: []
tags: [字号下限, 18px 太小看不清, 文本盒高度, 抬高度, 盒高, 图被拉伸, 竖椭圆, 三点指示器不圆, 圆点被拉长, 装饰线压住按钮, clamp_fs, 帧动画控件被拉伸, UTF8安全截断, 半个汉字, 多字节分隔符, 全角冒号误切]
evidence: []
---
# 字号下限与「文本盒抬高度」规则（抬高度只对有文字的盒有效）

> 检索导引：问「字号最小多少（18px）/ 文本盒要不要抬高度 / 抬高度把图拉变形·竖椭圆 / 三点指示器不圆 / 装饰线把按钮压住 / **中文被截出乱码问号 · 限宽用字节还是字宽 · 全角冒号把汉字切坏**」→ 本文。
> 检索词：字号下限 / 18px 太小看不清 / 文本盒高度 / 抬高度 / 盒高 / 图被拉伸 / 图变形 /
> 竖椭圆 / 三点指示器不圆 / 圆点被拉长 / 装饰线压住按钮 / 分隔线高度 / clamp_fs / data-h 抬高 /
> 图片尺寸 == 控件盒 / 运行期 setBackgroundPic / 帧动画控件被拉伸 /
> UTF-8 安全截断 / 半个汉字 / 字符边界 / 宽度单位估算 / 汉字 1.0 ASCII 0.55 / 多字节分隔符 / find_first_of 禁用 / 全角冒号误切。
> 案例：`projects/translate/tdesign-miniprogram`（2026-09-17 真机实测；报告 `projects/translate/tdesign-miniprogram/DOTS_ROUND.md`）。
> 适用：所有「出 HTML → html2json/自研生成器 → json」链路里对**盒高做统一规范化**的地方。

## 0. 两条规则

1. **字号下限**：正文/按钮字号 **≥ 18px**（基准 1024×600 画布）。更小的字在平台默认字库下
   **真机看不清**——这是外观口径，不是可选项；小控件盒（徽标/标签）因此会比设计稿大，**图随盒重出**。
2. **「抬高度」只对「有文字的 text 盒」有效**（⚠ 本条是坑）：
   判据是**盒里有没有文字内容**，**不是控件名白名单**。无文字的盒子被抬高度 = **图被按盒拉伸**。

## 1. 三类**绝不能抬高度**的盒（实测踩过）

| 类型 | 为什么不能抬 | 抬了会怎样（实测） |
|---|---|---|
| **h ≤ 4 的装饰线 / 分隔线** | 它是线，不是文本框 | 抬到 26 会**压住下一行按钮 → 整行点不动**（`check_all` 的「装饰件压按钮」WARN 就是这个；补救要 `setTouchable(false)+setTouchPass(true)`） |
| **带 `data-bgpic` 的纯图盒** | 图与盒是 1:1 关系 | 违反「**图片尺寸 == 控件盒**」铁律，图被拉伸 |
| **运行期 `setBackgroundPic()` 逐帧换图的图标盒** | 静态 HTML/json 里**没有** `backgroundPic`，看不出它是图盒 | **正圆被拉成竖椭圆**：三点指示器盒 **48×26**、图 **48×16** → 引擎把图拉满盒（1.625×），10×10 的正圆变成 **10×16 竖椭圆** |

第三类是最阴的：**判据不能只看 HTML 属性**（它没有 `data-bgpic`），要靠「**盒里有没有文字**」。

## 2. 实测数字（三点指示器「不圆」，真机像素级）

- 案例 loading 页三点（`LdDots`）在 HTML 里是**无文字内容的纯图 textview**，图由运行期
  `setBackgroundPic` 逐帧换（`ld_dots_00..02` = **48×16**）；旧实现只对「h≤4 装饰线」和「带 data-bgpic 的纯图」
  网开一面 → 这个盒两条都不满足 → 盒高被从 **16 抬到 26**。
- 真机帧上量三点形状（同一观测窗）：

| 帧 | 改前（盒 48×26）每点 w/h 比 | 改后（盒 48×16）每点 w/h 比 |
|---|---|---|
| 首帧 | 0.61 / 0.62 / 0.56 ❌ | 1.10 / 1.10 / 1.00 ✅ |
| 第 2 / 3 帧 | 0.69~0.61 / 0.61~0.62 / 0.56 ❌ | 1.10 / 1.00~1.10 / 1.00 ✅ |
| 高速档帧 | 0.61 / 0.61 / 0.62 ❌ | 1.10 / 1.00 / 1.00 ✅ |

- 最亮那颗点（同一颗）：**改前 10×16（ratio 0.625）→ 改后 10×10（ratio 1.000）**；
  改后中心上移 5px，正是「26 高盒 vs 16 高图」的居中差——现在点与图 1:1，位置回到设计稿位置。
- **验收判据（可复用）**：每个点 `w/h ∈ [0.8, 1.25]` 且**点数 == 3**。改前 0.56~0.69 全部越界（FAIL），
  改后 1.00~1.10 全过。
- **干跑复现（定位根因的正规做法）**：把现网 HTML 里该盒的 `data-h` 还原成抬之前的 `16`，
  分别跑旧/新实现 —— 旧实现得到 `26` 且**与现网 HTML 逐字节一致（双平台都是 True）** ⇒ 根因坐实；
  新实现在整份 HTML 上**只改 1 行**（双平台一致）。
- **保留两条例外**（`h≤4` 装饰线、带 `data-bgpic` 的纯图）不变；新增第三条：**内容为空/纯空白
  （含 `&nbsp;`）的 text 盒不抬**（匹配要「连内容一起匹配」，只匹配开标签会漏掉「盒里没字」这件事）。
- **同类普查口径**：扫全部 `class="text"` div（案例两平台各 403 个），找「**无文字 + 无 `data-bgpic`
  + 高度恰为被抬后的值**」→ 案例只有 1 个（`LdDots`）；58 个无文字纯图盒**全带 `data-bgpic`** 不受影响；
  其余无文字盒本来就 h≥26 或 h≤4，没被抬。
- **生成幂等**（落盘后复跑生成器）：两平台的 html / json / ftu / 205 张图 md5 **全部 SAME**
  ——不会「下次重新生成又变回去」。

## 3. 平台侧同口径（不是新发明，别在生成器里漏掉）

**`html2json` 的 FT-009 最小尺寸扩展已经是「有文字才抬」**（`ui_tools/html2json.py` `_finalize_layout()`）：

```python
if not text or not fs or not pos.get('width') or not pos.get('height'):
    continue          # ← 无文字的盒直接跳过，不参与最小尺寸扩展
```

⇒ 这是**全平台既有口径**。案例侧自研的 `clamp_fs()` 是重写了一遍，漏了这条判据 → 才踩坑。
**凡是自己实现「统一抬盒高 / 统一字号」的生成器，必须逐条对齐本节 §1 的三类例外。**

## 4. 静态检查的盲区（`check_all` 为什么没报警）

- 规则「图片尺寸 == 控件盒」（#11/#17）只看 **json 里声明的 `backgroundPic`**；
  运行期 `setBackgroundPic()` 设的图**静态查不到** → 被拉变形也不报（案例实测：一路 PASS）。
- 规则「最小尺寸」（#13）只看**有文字**的控件——正是本规则的同一条思路，但它管不到「被多抬」。
- **v0.27.90 已补**：`check_all` **第 20 项「运行期 set...Pic 的图 vs 控件盒」**（口径见 §5），
  能静态抓到「字面量路径」的那一类；但**运行时拼出来的路径**（如案例的 `snprintf("images/%s_%02d.png")`
  helper 逐帧换图）静态无解，仍只有 `dynamic` 计数 → 这类仍必须真机量像素（§2 判据）。

## 5. 已内建到 `ui_tools`：`check_all` 第 20 项（v0.27.90-open 起）

原评估「暂不内建」针对的是**静态 json 检查**（它原理上看不到运行期设图，硬加会把大量合法盒判进去）；
真正能机器化的是**代码侧静态检查**，现已实现：`ui_tools/check_all.py`
`check_runtime_setpic()`（第 20 项，与第 6 项同一套变量名口径）：

| 项 | 口径 |
|---|---|
| 扫什么 | `<项目>/src/**/*.cc`（含 `logic.cc`）与 `*.cpp` 里 `mXXXPtr->set…Pic("…")` 的**字面量**实参 |
| 目标控件 | 变量名 `mXxxPtr` → caption `Xxx`（精确匹配，同第 6 项）；映射不到 → `unresolved[]` 列出（**不静默跳过**） |
| 比对 | 图片 PNG 尺寸 vs 控件 `position`；同一 caption 在**任一页面**的盒对上就算对（多页复用图防误报） |
| 分级 | `resources/images/` 的**自动生成图**尺寸不等 → **FAIL**（铁律 #9/#11）；手绘图（`navi/` 等其它目录）不等 → `stretched[]` **仅提示**（官方基准 `navi/fh.png` 44×26 放 72×40 按钮是合法拉伸，**绝不 FAIL**）；`.9.png` **豁免**；文件不存在 → `missing[]` |
| 判不了的 | 实参是变量/拼接（`setBackgroundPic(path)`）→ 只计 `dynamic` 条数（**明说**「静态判不了」，不假装查过）；非工程内路径（设备侧资源如 `CONFIGMANAGER->getResFilePath(...)`）→ `unresolved` |
| 实测 | 基准 4 工程（SampleUI-New / ShowcaseAlbum-F133 / WebViewDemo / TDesign 案例双平台）**0 新增 FAIL**；案例这个坑（48×16 图 vs 48×26 盒）改回旧值**当场报出**（`48x16 != 盒 main.json textview__235 48x26`），盒高正确时 PASS |

仍属盲区（写入文档，别当已覆盖）：**路径在运行时拼出来的**（案例 `ldFrame()` 走 `snprintf("images/%s_%02d.png", prefix, …)`）
——静态无从得知用哪张图；带格式串的字面量（`"images/x_%02d.png"`）会被归到 `dynamic`/`unresolved` 而不是硬报。
所以 **§2 的真机量像素判据仍是最终验收**。

## 6. 自查清单（改字号 / 改盒高前打勾）

- [ ] 字号 ≥ 18px（正文/按钮）；小控件盒放大后**图已随盒重出**
- [ ] 抬高度的对象**只限「盒里有文字」的 text 盒**（不是按控件名挑）
- [ ] `h ≤ 4` 装饰线**没被抬**（抬了压住下一行按钮 → 整行点不动）
- [ ] 带 `data-bgpic` 的纯图盒**没被抬**（图 ≠ 盒 = 拉伸）
- [ ] **运行期 `setBackgroundPic` 逐帧换图的盒没被抬**（圆点会被拉成竖椭圆）
- [ ] 生成器与 `html2json` FT-009 同口径（「无文字跳过」）
- [ ] 真机量像素验收（比例类判据，如每点 `w/h ∈ [0.8, 1.25]`），别只信静态全检
- [ ] 跑过 `check_all` **第 20 项**（运行期 set...Pic 的图 vs 控件盒）：`mismatch[]` 必须为空；
      若全是 `dynamic`/`unresolved`，说明静态没覆盖到——回到真机量像素那一条

## 7. 文本处理三件套（UTF-8；中文界面必踩）

> 适用：**任何自己截断/裁剪/限宽中文文本**的地方——场景名、设备名、chip 标签、列表行标题。
> 证据：真工程只读 `projects/SmartPanel_HA/src/logic/`（行号已实读核对）；`verified_at` 维持原文 2026-09-29。

### 7.1 安全截断：只在 UTF-8 字符边界断

**现象**：短名被截成「半个字」→ 真机上显示**乱码 / 问号 / 方块**（问号常是「半个汉字」的兜底字形）。
**根因**：按**字节**截（`substr(0, n)` / `resize(n)`）会把 3 字节的汉字切成一半。
**做法**：先按**前导字节**算出该字符占几字节，**整字符** append，一字节都不切。
**判据**：截断结果的字节数**恒为 3 的倍数**（纯 ASCII 段除开）；任取一个字符，首字节 `>= 0xC0` 时不出现孤立尾字节。

### 7.2 显示宽度估算：汉字 1.0 / ASCII 0.55（限宽别用字节数）

**现象**：限宽时中英混排「该截的没截、不该截的截了」（全中文按字节数算会只剩 1/3 个字）。
**做法**：用**单位（units）**估宽：**汉字/全角 = 1.0，ASCII = 0.55**；限宽写 `最多 N 个单位`。
**判据**：`fitUnits(s, N)` 返回值的 `textUnits()` 恒 `<= N`，且等于最长可行前缀。

### 7.3 多字节分隔符：禁用 `find_first_of`，用 `find("整串")`

**现象**：拿场景描述切中文名时，**「回家模式」被切坏**（切出半个字节 + 难认字）。
**根因**：`find_first_of(":：")` **按单字节**匹配——全角冒号「：」的 UTF-8 首字节 `0xEF`，
也是很多汉字的**内部字节**，于是切点落到别的汉字**中间**。
**做法**：对多字节分隔符改用 `find("：")`（**整字节序列**搜索）；ASCII `':'` 与全角各自 `find` 后**取较小的 npos 非空者**。
**判据**：切点必然落在字符边界（同 §7.1）。

### 7.4 可直接抄的函数口径（`utf8CharLen` / `fitUnits` / `textUnits`）

```cpp
// ---- 可直接抄：UTF-8 前导字节 -> 字符字节长（不识别非法序列，仅保证不切半字）----
static size_t utf8CharLen(unsigned char c) {
    return (c < 0x80) ? 1 : ((c < 0xE0) ? 2 : ((c < 0xF0) ? 3 : 4));
}

// ---- 可直接抄：按【显示宽度】安全截断；汉字/全角 = 1.0，ASCII = 0.55 ----
static std::string fitUnits(const std::string& s, double maxUnits) {
    std::string out; double used = 0.0;
    for (size_t i = 0; i < s.size();) {
        unsigned char c = (unsigned char)s[i];
        size_t len = utf8CharLen(c);
        if (i + len > s.size()) break;          // 不切半个字
        double w = (c < 0x80) ? 0.55 : 1.0;
        if (used + w > maxUnits) break;         // 放不下就整字符停
        out.append(s, i, len); used += w; i += len;
    }
    return out;
}

// ---- 可直接抄：量一段文本占几个单位（中英混排限宽判断用）----
static double textUnits(const std::string& s) {
    double used = 0.0;
    for (size_t i = 0; i < s.size();) {
        unsigned char c = (unsigned char)s[i];
        size_t len = utf8CharLen(c);
        if (i + len > s.size()) break;
        used += (c < 0x80) ? 0.55 : 1.0; i += len;
    }
    return used;
}
```

> 想按「最大字节数」限位而非按字宽时，把上面的 `w` 换成 `len` 即得 `dnFit(s, maxBytes)`（只保证不切半字）。

**证据（真工程只读，行号已实读核对）**：
- `projects/SmartPanel_HA/src/logic/homeLogic.cc:97-108` `fitChipText()`：按前导字节取 `len`、只在边界 append；注释「汉字按 1.0、ASCII 按 0.55 估，最多 4 个汉字宽」。
- `projects/SmartPanel_HA/src/logic/homeLogic.cc:110-118` `chipLabelText()`：注释明写「**不能用 `find_first_of(":：")`** —— 它按单字节匹配，全角冒号的字节会误切到其他汉字中间（实测把「回家模式」切坏）」；代码改用 `find(':')` + `find("：")` 整序列搜索并取较小者。
- `projects/SmartPanel_HA/src/logic/devnameLogic.cc:44-57` `dnFit()`：注释「按 UTF-8 字符边界截断（避免截出半个汉字）」；配 `:30` `DN_MAX_BYTES 72 // 最多 24 个汉字（UTF-8 3 字节/字）`。
- `projects/SmartPanel_HA/src/logic/scenesLogic.cc:82-96` `fitUnits()` 与 `:98-108` `textUnits()`（口径源）；配 `:45` `SCENE_NAME_UNITS_MAX 6 // 新增场景名最多 6 个汉字（1 个 ASCII 算 0.55）`。

检索词：中文截断乱码 / 显示问号 / 半个汉字 / UTF-8 字符边界 / 截断函数 / 限宽字节还是字宽 / 汉字宽度估算 / 1.0 0.55 / 多字节分隔符 / find_first_of 坑 / 全角冒号 / 中文名被切坏。

## 相关

- 图片与控件盒 1:1 铁律 / 抗锯齿出图档位 → `knowledge/devflow/ui-asset-rules.md`
- 运行期换图做「隐藏」（同尺寸透明占位图） → `knowledge/devflow/ftu-json-pipeline.md`、`knowledge/uicontrols/custom-view-refresh.md`
- 装饰件压住按钮（`touchable=false` 也要穿透） → `knowledge/uicontrols/touch-events.md` §1
- 静态全检能查什么/查不到什么 → `knowledge/uicontrols/retrieval-boundary.md`、`knowledge/devflow/ui-layout-verify.md`
