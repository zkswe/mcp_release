# THIRD-PARTY.md —— 第三方资产与许可说明

> 一句话：**图标图形全部来自 Tabler Icons（MIT），本模块只做"单色化 + 等比缩放"，
> 不改图形**；另有 5 个两轮车仪表图标为自绘（无第三方版权）。
> 更新：2026-09-17（v0.3.0，单归档；许可义务未变）

---

## 1. 收录的第三方资产：Tabler Icons

| 项 | 值 |
|---|---|
| 项目 | **Tabler Icons**（`@tabler/icons`） |
| 版本 | **3.46.0** |
| 来源 | `https://registry.npmjs.org/@tabler/icons/-/icons-3.46.0.tgz` |
| tarball sha256 | `6d727ad0489854d2d7d07ba9baa6476af7ee415aaa2eba1adc0deab48556852b` |
| 许可 | **MIT**（原版 LICENSE 随资产一起放在 `vendor/tabler/LICENSE`） |
| 收录时间 | 2026-09-16 00:05 |
| 收录形态 | **单一归档** `vendor/tabler-3.46.0.pack.tgz`（455,379 B，sha256 `a0ba69f2…1c95`，条目 5774）—— 我侧打包，**内容未改**：`icons/*.svg`（outline 4754）+ `icons-filled/*.svg`（filled 1019）+ `map.json`；`LICENSE` / `index.json` / `VERSION.txt` 留在归档外随资产分发 |
| **已排除** | **`brand-*` 品牌 logo 376 个 —— 一个都不收**（避免商标/品牌风险；已核验归档内 0 个 brand-*） |
| 语义映射 | `vendor/tabler/map.json`（**在归档内**）：198 条（191 条单 glyph + 7 条 `compose` 组合） |
| 源文件清单 | `vendor/tabler/index.json`（在归档外，供快速索引） |
| 版本凭据 | `vendor/tabler/VERSION.txt`（版本/url/sha256/收录时间/统计） |

**我们对图形做了什么**（这一点很关键）：
1. **不做任何图形修改**：不重绘、不合并路径、不描边化、不改变比例、不增删细节；
2. 只做**单色化**：SVG 里的 `currentColor` 在渲染时替换成调用方指定的 `--color`，
   输出 RGBA PNG（RGB 恒等于该颜色，只有 alpha 变化）；
3. 只做**等比缩放**：`viewBox 0 0 24 24` 等比缩放到 `--size`，线宽按
   `max(1, round(2 × size/24 × 2)/2)` 取半像素对齐（这是"输出采样"层面的取整，
   不是改图形）；
4. 组合图标（`compose`）是**多个 Tabler glyph 的叠放**（按 `dx/dy/scale`），
   各自独立缩放后 alpha 合成 —— 同样没有修改任何单个 glyph。

> 结论：产物是本模块对 MIT 资产的"再分发 + 格式转换"。**MIT 义务必须履行**（见 §3）。

---

## 2. 自绘部分

| 项 | 说明 |
|---|---|
| 文件 | `svg/vehicle/*.svg`（5 个图标 × off/on = 10 个）、`scripts/author_svg.py` 里的几何定义 |
| 版权 | 本项目自有，可自由用于本项目任意平台（含商用交付），无第三方限制 |
| 为什么自绘 | 两轮车仪表的转向箭头（粗实箭头）、大灯/远光（带光束的灯泡与灯丝）、
定速巡航（闪电）—— Tabler 对应图形是细线风格，与仪表观感不匹配 |

另有 **v0.1.0 的自绘集**（天气/开关选项/通用系统/智能家居，86 图标 × ios/material）：
**已被 vendor 取代**；几何与自绘表的唯一出处是 `scripts/author_svg.py`（保留），
原留档目录 `svg_retired/`（162 个 svg）**已于 v0.3.0 移出仓库**——理由是实测可逐字节重生：
`python scripts/author_svg.py` 能把它连同 `svg/` 一起重写出来（163 文件 sha256 全同），
而 `gen_catalog.py` / `selfcheck.py` / `gen_icons.py` **都不读它**。版权同为本项目自有。

---

## 3. MIT 义务（再分发时必须做）

Tabler Icons 采用 MIT 许可，要求在**所有副本或实质部分**中保留版权声明与许可声明：

- [x] 本模块内保留 **`vendor/tabler/LICENSE`**（原版许可全文，未改动）；
- [x] 保留 **版本/来源/sha256 凭据**：`vendor/tabler/VERSION.txt`；
- [ ] **交付到产品时**：若把本模块生成的 PNG 随 app 出厂，产品侧的 third-party notices
      里应包含 Tabler 的版权与 MIT 许可（照抄 `vendor/tabler/LICENSE` 即可）。
      本模块不擅自改动产品级 notices 文件，请由发布流程统一挂接。

MIT 允许商用、允许修改、允许再分发（保留声明即可）；**不提供担保**（原许可的免责条款）。

---

## 4. 品牌与商标

- `vendor/tabler` 收录时**已排除全部 `brand-*`**（376 个，含各公司 logo/商标图形）。
- 本模块**不得**收录：品牌 logo、厂商商标、任何"看起来像某家公司标志"的图形。
  需要品牌图标时由产品侧自行取得品牌方授权，不要放进这个公共资产库。
- 自绘部分同样不包含任何品牌元素。

---

## 5. 若日后要新增第三方来源（规范）

必须做齐四件事，缺一不收：
1. `vendor/<来源>/LICENSE`（原样，不改）与 `VERSION.txt`（版本、url、sha256、收录时间、统计）；
2. `vendor/<来源>/map.json`：语义名 → glyph 映射（供 `gen_catalog.py` 合并）；
   若采用"单归档"形态（v0.3.0 起 vendor 线即如此）：svg + map.json 进
   `vendor/<来源>-<版本>.pack.tgz`（`scripts/make_pack.py`），LICENSE / VERSION.txt /
   索引 json 留在归档外，并在 `README.md` 写清读层与环境变量；
3. `catalog.json` 中该条目的 `source` / `license` 字段由生成器自动写入（**禁止手写**）；
4. 在本文件登记（来源/版本/许可/收录日期/文件清单/用途/排除项）。

**禁止**：收录 SF Symbols（Apple 许可禁止再分发）、任何未明确许可的图标站素材、
任何"截图/切图"来的图形、任何品牌 logo。

---

## 6. 本目录下非本模块产物的文件（已处理）

`components/icons/fonts/` 曾放过 6 个 Google Material Icons 字体文件（Apache-2.0），
**v0.3.0 核实：该目录已不存在于仓库/工作区**（本模块走"vendor SVG + 生成器"路线，
不需要图标字体，理由见 `platforms.md` §2.3）；若在历史版本或别的分支上又见到它，
按下列二选一处理：删除（推荐）或迁到 `references/` 补齐 LICENSE/NOTICE。
