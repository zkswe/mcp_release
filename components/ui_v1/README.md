# components/ui_v1 — 当前 UI 组件 / 映射基线（FlyThings IDE + easyui 这一代）

> **这是什么**：FlyThings 现有那一代开发方式（**FlyThings IDE + easyui 控件 + 受限 HTML → json → ftu**）
> 的**框架基线目录**：把「跨框架控件怎么映射、缺口怎么处置、哪些组件值得沉淀」一次性写清楚，
> 让下一个案例**从表开始**，而不是每次重新踩坑。
>
> **建立**：2026-09-16（钟工：「对齐一下控件，然后入库。可以把 LVGL 有的控件我们替代的在 components 目录
> 新建一个 UI 目录…弄个 `ui_v1` 的目录，用来保存当前的组件框架。把新增发现不同的框架加载进去。」）
> **版本**：v0.27.73-open ｜ **状态**：**只放「平台真缺的能力」的自定义控件包（已落 3 个：Chart、Calendar、RadButton）**
>
> **口径（★ 2026-09-16 钟工最终修正，两条必须照做）**：
> 1. **有一一映射的控件 → 走「映射能力」，不写散文**：机读索引 `mcp_control_map.json` + MCP op
>    `flythings_map_control(query, source)`——输入源控件名（LVGL/Qt/Android/小程序/emWin/MFC 任一）
>    一次对上我们的控件 + 级别 + 可直接粘的 json 片段。**此类一律不进 `ui_v1/<源控件名>/`**。
> 2. **`components/ui_v1/<源控件名>/` 只放「FlyThings 没有的能力」的自定义控件包**（如日历选择器、
>    TimePicker、折线图）：一个缺口控件一个目录，四件套 + `example/` + 真机证据。
>
> 下面的基线文档（`control-map.md` / `logic-map.md` / `gap-list.md` / `platforms.md` / `components.md`）
> **保留**，作为级别口径、缺口编号、平台事实的说明与索引（机读数据从它们收口而来）。

---

## 1. 这一代框架的边界（写死，别混进新框架）

**属于 ui_v1 的**（本目录所有结论只对这代有效）：
- 控件面：easyui 内建控件（`window`/`button`/`textview`/`edittext`/`listview`/`slidewindow`/`scrollwindow`/
  `pagewindow`/`pointer`/`circlebar`/`diagram`/`digitalclock`/`imageanim`/`painter`/`qrcode`/`radiogroup`/
  `checkbox`/`seekbar`/`cameraview`/`videoview`/`slidetext`）+ 自研 `lib-ext_widgets` 8 控件
- 界面通道：受限 HTML → `html2json` → `ui/*.json` → `fui pack` → `*.ftu`
- 程序通道：`src/logic/*Logic.cc`（回调表 / `mXXXPtr` / `REGISTER_ACTIVITY_TIMER_TAB` / `INIT_UI_TIMERS` /
  `EASYUICONTEXT` 导航）
- 工具链：`fun` / `fui`（`fun build|install|launch|sim`）
- 平台：Z21 / F133 / Z20 / T113 / V85X（**无 GPU / 无硬解** → 伪 3D 口径）

**不属于 ui_v1**（不要写进本目录）：
- 将来「fun 全流程」等新一代方案 → 另开 **`components/ui_v2/`**（架构/控件/工程组织都会不同）
- 纯底层平台能力（disp 分层、音视频解码、BLE、网络）→ 走 `components/ble`、`knowledge/v85x/*`、平台 KB
- 原始 demo 源码与第三方框架用法 → **禁止**把 Qt/Android/LVGL 的字段/API 抄进本目录（见
  `knowledge/uicontrols/retrieval-boundary.md`）

### 与 `ui_v2` 的关系（预留，先定规矩）
| 项 | ui_v1（本目录） | ui_v2（未来） |
|---|---|---|
| 界面通道 | 受限 HTML → json → ftu（`html2json`） | 待定（fun 全流程） |
| 控件面 | easyui 内建 + 自研 lib-ext_widgets | 待定 |
| 映射表 | `control-map.md`（散文权威表）+ **`mcp_control_map.json`（机读，op `flythings_map_control`）** | v2 另建，**不得覆盖 v1 结论** |
| 迁移规则 | v1 结论**长期有效**（老工程还要维护） | 新方案落地时**逐条标注**「v2 是否仍适用」 |

---

## 1.5 目录约定（★ 控件包长什么样）

```
components/ui_v1/
├─ README.md             本文件（代次边界 + 目录约定 + 状态表）
├─ platforms.md          平台口径（控件可用性差异 / 设备硬限制）
├─ control-map.md       ★ 控件映射权威表（源框架 × 我们控件 × 级别；散文版，机读版已收口到 mcp_control_map.json）
├─ logic-map.md         ★ 逻辑映射表（事件/定时器/列表/导航/生命周期）
├─ gap-list.md          缺口清单 + 五级处置 + 3D 策略 + 工具链坑
├─ components.md        ★ 组件状态表（已实现自定义控件 / 映射项 / 计划中的自定义控件 三段）
├─ examples/            已完成案例索引（案例工程在开发工作区，不随包发布）
├─ _mapping/            ★ **映射参考**（有平台对应控件、因此**不算控件包**的接线留档，如 TabView→pagewindow）
└─ <源控件名>/           ★★ **自定义控件包（仅限「FlyThings 没有的能力」的缺口控件）**
   ├─ README.md         替代哪个源控件 / 我们怎么做 / 接口 / 依赖 / 限制 / 验收记录 / 排错
   ├─ platforms.md      逐平台：可用性 + 前置条件 + 实测值 + 已知限制（未实测标 `未验证`）
   ├─ Manifest.xml      底层依赖包 + 本模块被引用的两种方式
   ├─ include/zk/*.h    唯一对外头（命名空间 `zk::ui_v1::<控件>`）
   ├─ src/*.cpp         实现（源码型）
   └─ example/          最小可跑工程（真的编译过 + 真机跑过）
      ├─ README.md      从零跑起来的命令（含平台部署坑）
      ├─ ui/ src/ Manifest.xml  工程本体
      └─ evidence/*.png 真机截图 +（有像素验收的）diff 图
```

**目录命名铁律（防止把已有控件又包一遍）**：
- **有一一映射的控件一律不进本目录**（哪怕封装过）：它们走映射能力（`flythings_map_control` + 数据文件），
  需要接线细节就放 `_mapping/<源控件名>/`（如 `_mapping/TabView/`，基于平台 `pagewindow`）。
- `<源控件名>/` 里的目录名必须是**源框架控件名**，且该能力**平台确实缺**
  （级别 L3 自绘 / L4 降级 / L5 不支持，且 `gap-list.md` 有编号）——如 `Calendar/`（日期选择器）、
  `TimePicker/`、`WheelPicker/`、`RichText/`、`TableGrid/`、`Chart/`、`Pseudo3D/`。
  判定口径：**平台有没有能 1:1 覆盖的控件**（有 → 映射；无 → 才建包）。

**四件套沿用 `components/README.md`**（缺一不收）；与 `components/ble|fonts|icons` 的差别只在：
ui_v1 的包**依赖 easyui 控件面**，所以 `platforms.md` 必须写清 **easyui 版本**与**控件可用性差异**。

## 2. 文件清单与状态表

| 文件 | 内容 | 覆盖 | 状态 | 备注 |
|---|---|---|---|---|
| [`README.md`](README.md) | 本文件：代次边界 + 与 ui_v2 关系 + 状态表 + 用法 | — | ✅ 完成 | — |
| [`platforms.md`](platforms.md) | 平台口径：分辨率 / rotate / 部署路径 / **easyui 版本与控件可用性差异** / 设备硬限制 | 5 平台 | ✅ 完成 | 未实测项标 `未验证` |
| [`control-map.md`](control-map.md) | ★**唯一权威控件映射表**：源框架 × 我们控件 × 级别 × 备注（+ 级别口径与换算 + 平台事实 F1~F12） | 4 大节 ~70 行 | ✅ 完成 | 知识库只放指针 |
| [`logic-map.md`](logic-map.md) | ★统一**逻辑映射表**：事件/值变化/生命周期/定时器/状态/列表/导航/弹窗/键盘/自绘刷新/异步 + 最小骨架 4 段 | ~40 行 | ✅ 完成 | — |
| [`gap-list.md`](gap-list.md) | 缺口清单（G-01~G-36）+ 五级处置 + 自绘论证 + **3D 策略** + 工具链坑（T1~T12） | LVGL 20 + 小程序 22 + 家底 9 | ✅ 完成 | 可检索、可引用 |
| [`components.md`](components.md) | 组件状态表 **三段**：**已实现自定义控件**（缺口控件包）/ **映射项**（指向 op 与数据文件）/ **计划中的自定义控件** | 18 项 | ✅ 完成 | 本轮已迁出 TabView（→ `_mapping/`） |
| [`examples/README.md`](examples/README.md) | 指向两个已完成案例 + 各自真机证据要点 | 2 案例 | ✅ 完成 | 案例工程在开发工作区，不随 MCP 包发布 |
| [`_mapping/README.md`](_mapping/README.md) | ★ **映射参考目录**（有平台对应控件、**不算控件包**的接线留档） | 1 项（TabView） | ✅ 完成 | 机读映射见 `mcp_control_map.json` |
| [`_mapping/TabView/`](_mapping/TabView/README.md) | ★ **映射项**：页签页容器接线（基于平台 `pagewindow`：滑动切页 + 页签高亮/下划线双向同步 + 手感默认值） | Z21 已验收·F133 未验证 | ✅ **映射项**（非自定义控件包） | 含 `example/` + 4 张真机证据 |
| [`Chart/`](Chart/README.md) | ★ **自定义控件包**（平台真缺）：图表集合 `zk::ui_v1::Chart`（LINE/BAR/RING/GAUGE 自绘 + textview 刻度 + **0.2.0 分段环 `setRingSegments`**） | Z21 已验收·F133 未验证 | ✅ **已实现** | 含 `example/` + 5 张真机证据 + 2 张 diff |
| [`Calendar/`](Calendar/README.md) | ★ **自定义控件包**（平台真缺）：日期选择器 `zk::ui_v1::Calendar`（42 个 textview 网格 + 业务侧触摸反算命中 + 标记/今天/翻月） | Z21 已验收·F133 未验证 | ✅ **已实现** | 含 `example/` + 5 张真机证据 + 1 张 diff |

> **本轮交付口径**：**缺口控件才建包**（`<源控件名>/` + 四件套 + 真机证据）；**有对应控件的一律走映射能力**
> （`mcp_control_map.json` + op `flythings_map_control`），需要接线就放 `_mapping/`。基线文档作为级别/缺口/平台事实的索引保留。

### 机读映射数据（本轮新增，不再只靠散文）

| 文件 / 入口 | 内容 |
|---|---|
| `mcp_control_map.json`（仓库根目录） | 六个源框架（lvgl / qt / android / miniprogram / emwin / mfc）共 212 条常用控件映射：`name / aliases / target / level / json（可直接粘）/ notes / ref` + `targets`（目标控件：caption/指针/片段） |
| MCP op `flythings_map_control(query, source)` | 按控件名/别名模糊匹配（忽略大小写与下划线/连字符），命中回级别 + 片段 + 指针；未命中回 `NO_HIT` + 候选 + 「缺口五级」处置建议 |
| 能力说明 | `knowledge/uicontrols/control-mapping-capability.md` |

---

## 3. 怎么用（人 / AI 都照这个顺序）

1. **要转一个别的框架的界面** → 先调 MCP op `flythings_map_control(query="<源控件名>")`（一次对上我们的
   控件 + 级别 + 可直接粘的 json 片段）；机读数据在 `mcp_control_map.json`。拿不到名字时再查散文权威表
   `control-map.md`；级别是 L3/L4/L5 的，去 `gap-list.md` 看处置与降级点。
2. **要写页面逻辑** → 查 `logic-map.md`（事件/定时器/列表/导航/状态一张表）。
3. **动工前** → 查 `platforms.md` 对应平台那一行（能用的控件、别用的 API、部署与内存限制）。
4. **遇到"平台缺能力"** → 先看 `gap-list.md` 有没有编号的现成处置；没有就新增一条（含级别 + 证据），**别现场发明**。
5. **想复用实现** → 查 `components.md`：**映射项** 段 → 已有控件 + 接线在 `_mapping/<源控件名>/`；
   **已实现自定义控件** 段 → 直接用 `components/ui_v1/<控件名>/`（含 `example/`，抄过去就能跑）；
   **计划**段里的 → 还没写（平台真缺的才在此列），需要就走批次立项。
6. **AI 检索口径**：控件用法/字段只查 MCP 知识库或官方站（`retrieval-boundary.md`）；
   跨框架映射查 op `flythings_map_control` / `mcp_control_map.json`（知识库侧摘要见
   `knowledge/uicontrols/control-mapping-capability.md`）。

---

## 4. 维护规则（防漂移）

1. **权威表只此一份**：控件映射的散文权威在 `control-map.md`，**机读权威在 `mcp_control_map.json`**
   （两者由同一批口径收口，冲突以 KB `knowledge/uicontrols/*` 为准），逻辑映射在 `logic-map.md`；
   `knowledge/uicontrols/framework-control-mapping.md` 与 `control-mapping-capability.md` **只写摘要 + 口径 + 指针**。
2. **新增发现必须落到表里**：案例里发现的新框架控件/新坑 → 先补 **`mcp_control_map.json`**（对应 source 加一条）
   再补 `control-map.md` 行 + `gap-list.md` 编号；只写案例文档 = 下一个人重踩。
3. **级别不许临时发明**：只用 L1~L5 五级口径（判定规则见 `control-map.md` §0），旧案例的 A/B/C/D 按 §0.1 换算。
4. **不写"应该可以"**：未实测标 `未验证`；不确定的写进「待确认」并点名找谁确认。
5. **改动要连动**：改本目录 → `kb_tools.py` 版本递增 + `MCP_FEATURES` 顶部加一条 + 重建 `rag_index.json`
   + 跑 `python scripts/check_consistency.py --with-tests`（全绿才算完）。
6. **控件包不许“文档先行”**：`<源控件名>/` 目录**必须四件套齐 + `example/` 真的编译过**；
   能在真机跑的，`example/evidence/` 里必须有截图（拿不到设备的，在包 README 里写「待设备空闲补真机验收」）。
   没做到就不算「已实现」，只能呆在 `components.md` 的**计划**段里。
7. **建包前先证明“平台真缺”**：先跑 op `flythings_map_control(query)`：
   命中 L1/L2 → **不许建包**（走映射，接线放 `_mapping/`）；命中 L3/L4/L5 或 NO_HIT → 才能进 `<源控件名>/`，
   且 `gap-list.md` 必须有对应缺口编号（没有就先加编号 + 证据）。

---

## 5. 相关文件

- 目录规范（组件怎么收）：`components/README.md`
- 机读映射数据 + 用法：`mcp_control_map.json` / `knowledge/uicontrols/control-mapping-capability.md`
- 知识库摘要 + 指针：`knowledge/uicontrols/framework-control-mapping.md`
- 检索边界（禁抄别家控件用法）：`knowledge/uicontrols/retrieval-boundary.md`
- 自研控件方法论：`knowledge/devflow/custom-widget.md`　·　家底盘点：`knowledge/devflow/gui-controls-gap.md`
- 案例（真机证据）：`examples/README.md`
