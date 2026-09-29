# knowledge/inbox/ — 候选区（可见，但**不进索引、不进检索、不当依据**）

> 本目录是知识生长的**入口**。按 `knowledge/devflow/kb-growth.md` 的状态机：
> `draft → review → verified`；**只有 `verified` 才进检索索引与发布**。
> 候选条目留在这里：AI 检索**看不到**它（`gen_kb_index.py` 只扫分类目录，`check_kb.py` 另有断言），
> 但人和维护者能看到它、能接手补齐。

## 谁能往这里放东西

1. **用户/AI 现场**（推荐路径）：`flythings_knowledge_capture(...)`
   —— 默认写**用户本地层**（`~/.flythings/kb_local/inbox/`），**不写本目录**（本目录是总账侧候选区）。
2. **回流（我方侧）**：收到脱敏补丁包 / PR 后，未过闸的条目落这里，并写明"缺什么才能晋升"。
3. **外部提交**：有 git 的人可直接对 `knowledge/inbox/**` 提 PR（CI 只判候选区合规）。

## 晋升成 `verified` 的检查单（缺一不可）

| # | 要求 | 怎么验 |
|---|---|---|
| 1 | front-matter 合规 | `python scripts/kb_frontmatter.py --check` + `python scripts/check_kb.py` |
| 2 | **≥1 条可执行判据**（`evidence`） | `python scripts/kb_verify.py --scope all --device <serial>`（离线项现跑现判，真机项带设备） |
| 3 | **≥5 条检索问法**（含 ≥1 反例） | 登记进 `scripts/check_retrieval.py` 的 `GROUPS`，先 `--report` 取实测 top-1、再回填 `min_top1` = 实测 − 1 |
| 4 | 不与既有条目重复 | 指纹（标题+命令+平台）比对；命中 → **合并进已有条目**（追加平台矩阵/新证据/日期），不新建 |
| 5 | **人工签字** | 维护者确认；**AI 不能自评通过**（反模式 #4） |
| 6 | 升级动作 | 移到 `knowledge/<category>/` → `python scripts/gen_kb_index.py` → `python rebuild_index_local.py` → 全量门禁 |

## 当前候选（2026-09-29 收到，外部提交）

| 文件 | id | 状态 | 为什么还是 draft | 待补 |
|---|---|---|---|---|
| `20260929-open-source-stack-integration.md` | `devflow-open-source-stack-integration` | draft | 第 2 节判据是方法论、第 3 节多个库（sqlite3 / libmodbus / open62541…）**无真机结论** | 判据 1（musl/glibc 对照）、判据 3（strip 前后 `/res` 占用）、挑 1 个自编库走完四判据 |
| `20260929-custom-render-paths.md` | `devflow-custom-render-paths` | draft | ②b 离屏渲染 / ④ 独立进程图层 / ⑤ LVGL 接管 fb **均未真机验证**；① / ②a / ③ 有实测但判据文件未整理 | ②b 每帧耗时+内存峰值+连抓两帧；④ 3 天原型（kill 渲染进程看 UI）；把 ①/③ 的证据路径写成 `evidence` |

**两份都有正文 `> 检索导引：` 行 + 文末 10 条问法**（晋升时把这两组问法登记进 `check_retrieval.py`）：

- 开源栈接入：`想用开源库怎么办` / `registry 里没有这个包` / `自己编译的库怎么加进工程` /
  `dlopen 找不到库` / `musl 和 glibc 有什么区别` / `静态库太大怎么办` / `SQLite 能用吗` /
  `第三方 .so 放哪` / `undefined reference 链接错误` / `ldd 看哪些库`
- 自定义渲染：`FlyThings 怎么做自定义渲染` / `想用 LVGL 怎么办` / `能不能用 cairo/SDL` /
  `直接写 framebuffer 可以吗` / `离屏渲染成图再显示` / `视频层怎么叠加` / `releaseLayer 是什么` /
  `复杂动画性能不够` / `自绘指针表怎么做` / `stb 系列头文件库能用吗`

> 按本仓纪律，这两篇**先留在候选区**：可以让人读、可以被人接手补判据，
> 但**不会被 AI 当已验知识检索到**。若要立刻可检索，走两条路之一：
> ① 补证据升 `verified`；② 只把"已验部分"拆成 `verified` 条目、未验部分留候选。
