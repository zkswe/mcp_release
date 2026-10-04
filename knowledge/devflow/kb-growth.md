---
id: devflow-kb-growth
title: 知识库生长机制（P1）：采集 / 验证 / 检索三闭环
category: devflow
status: verified
confidence: offline
verified_at: 2026-09-29
machine_verified_at: "2026-09-29 20:45:47"
stale_days: 180
origin: total
source:需求方 2026-09-29「改造到用户基于这个开发后可以做到自动生长 + 可检索可验证」→ P1
needs_evidence: false
platforms: []
tags: [知识放哪个目录, 会不会写进 MCP 安装目录, 怎么回流总账, 脱敏补丁包, kb-contrib, 未收录怎么办, 知识缺口清单, kb_gaps, 复验知识, evidence 怎么写, kb_verify, kb_index, json, 知识体检]
evidence:
  - {kind: offline, cmd: python -m unittest tests.test_kb_growth -q, expect_rc: 0, expect_contains: OK, ran_at: "2026-09-29 20:45:47", output_sha256: ae14d0eca96adeb68d04b7e565e6557e9949c3f1107b4d678d315f47e1e21dfc}
---
# 知识库生长机制（P1）：采集 / 验证 / 检索三闭环

> **检索导引**：知识怎么自动生长 / 现场结论怎么入库 / capture 怎么用 / 候选区在哪 /
> 知识放哪个目录 / 会不会写进 MCP 安装目录 / 怎么回流总账 / 脱敏补丁包 / kb-contrib /
> 未收录怎么办 / 知识缺口清单 / kb_gaps / 复验知识 / evidence 怎么写 / kb_verify /
> verified 和 draft 区别 / kb_index.json / 知识体检 / 谁能让知识变成 verified

---

## 0. 一句话

**自动生长 ≠ 自动追加文档。**没有闸门的生长 = 自动腐化。所以本机制是三条**带闸门**的闭环：

```
① 采集：现场结论 → 候选(inbox) → 去重 → 复核/复验 → verified 入库
② 验证：verified → evidence（命令+期望）→ 定期复验 → 失败降级 stale
③ 检索：提问 → 命中（带状态/时效/证据）→ 未命中落盘 → kb_gaps 清单 → 驱动 ①
```

---

## 1. 三层存储（铁律：**不写 MCP 安装目录**）

| 层 | 位置 | 是否提交 | 谁能写 | 检索可见 |
|---|---|---|---|---|
| ① 本地层（用户私有） | `$FLYTHINGS_KB_DIR` 或 `~/.flythings/kb_local/` | 不提交 | AI / 用户 | 本机可见优先 |
| ② 项目层 | `<项目>/docs/kb/` | 随项目 git | 项目成员 | 打开项目时可见 |
| ③ 总账层 | `<MCP>/knowledge/` | 走 PR / 补丁包 | **仅维护者**| 全体可见 |

> MCP 安装目录是**版本物**：升级会覆盖、发行包会多出私有文件。用户知识写进去 = 升级即丢 + 污染发布物。

本地层目录结构：

```
~/.flythings/kb_local/
   inbox/<yyyymmdd-HHMM>-<slug>.md候选条目（front-matter status=draft/review）
   kb_candidates.jsonl候选流水（机读）
   _logs/no_hit.jsonl检索未命中日志（生长燃料；只在本机）
   exports/kb-contrib-<时间>.json脱敏补丁包（回流用）
```

## 2. 状态机（写死）

`draft → review → verified`；复验失败 → `stale`；被取代 → `deprecated`。

- **只有 `verified` 进检索索引与发布**；`draft/review` 只在候选区（不进索引、**不当依据**）。
- 晋升只有两把钥匙：**机器复验通过**或 **人工签字**。**AI 不能自评通过**（反模式）。
- 每条 verified 要么有 `evidence`，要么显式标 `needs_evidence: true`（不许口头结论冒充已验证）。

## 3. 采集：`flythings_knowledge_capture`

```
flythings_knowledge_capture(
  title="Z20 /data 写满导致注入工具推不上去",     # 一句话说清现象/结论
  body="现象/根因/判据/处置…",
  category="devflow", platforms="Z20", tags="测试,注入",
  evidence='[{"kind":"offline","cmd":"python -c ...","expect_contains":"mnt/extsd"}]',
  source="现场", layer="local",             # local（缺省）| project（配 project_root）
  project_root="")
```

- 落 `inbox/` + `kb_candidates.jsonl`；返回 `id / path / fingerprint / status`。
- **去重**：指纹 = 归一化标题 + 关键命令 + 平台。命中同主题 → 回 `duplicateOf`，
提示**合并到已有条目**（追加平台矩阵/新证据/复现日期），**不新建重复篇**。
- 想让 AI 自己拿结论换 token 的省法：直接让它把结论 + 判据一次写全，再跑复验。

## 4. 验证：`scripts/kb_verify.py`

```
python scripts/kb_verify.py                    # 只跑 offline 证据（CI，零设备）
python scripts/kb_verify.py --scope all --device 198.51.100.9:5555   # 含真实设备判据
python scripts/kb_verify.py --apply            # 结果写回（失败 → status=stale）
```

| kind | 判据 | 说明 |
|---|---|---|
| `offline` | 跑 `cmd`，比 `expect_rc`（默认 0）/`expect_contains` | 进 CI |
| `real-device` | `%DEVICE%` 替换成设备序列号后跑 | 需 `--device`；没设备就**显式 skipped**|
| `manual` | 不跑 | **不算通过**，只统计（要写明为什么不能自动验） |

报告落 `knowledge/_reports/kb_verify.json`（gitignore）。

## 5. 检索闭环

- 未命中/低置信 → 落本地层 `_logs/no_hit.jsonl`，返回体带 `gapLogged / gapLog / gapHint`。
- `python scripts/kb_gaps.py` → `knowledge/_reports/kb_gaps.md（scripts/kb_gaps.py 生成）`：**用户真的问不到的 top-N = 下一批写作清单**。
这是"生长"的引擎：不是让 AI 自由发挥写文档，而是**缺口驱动写作**。
- **命中会带证据等级**（2026-09-29 提报发现 ② 后的收口）：`hits[].status / evidenceLevel /
  verifiedAt`；`evidenceLevel` 取 `has-evidence`（有可执行判据）/ `manual-only`（人工沉淀、无判据）/
  `none`。非 verified 或 none 的额外带 `advisory` —— 因为首轮迁移把 80/85 篇迁成
  `verified + needs_evidence`，**光看 `verified` 会被误当“已验”**。
- **tags 只允许检索词**：`kb_local.clean_tag()` + `validate_meta()` 档住反引号/星号/尖括号/分号等
  markdown 碎片（首轮自动抽取污染过 33/85 篇，而 tags 是索引的一部分 ⇒ 噪声会造假命中）；
重抽：`python scripts/kb_frontmatter.py --retags`。

## 6. 机读清单：`knowledge/kb_index.json`

```
python scripts/gen_kb_index.py            # 生成
python scripts/gen_kb_index.py --check    # 门禁（源哈希/篇数不一致即 FAIL）
```

带 `meta{source_hash, doc_count, built_at, mcp_version}`、summary（verified / 带证据 / 待补证据 /
无问法登记 / 超期 / inbox / manualOnly）与逐篇字段（含 `sha256 / fingerprint / hasQueries /
`ageDays / evidenceLevel`）。**新鲜度看源哈希，不看 mtime**。

## 7. 回流总账（三条通道）

| 通道 | 谁用 | 机制 | 自动化 |
|---|---|---|---|
| **A. 脱敏补丁包（默认）**| 任何用户 | `flythings_knowledge_export(scope="inbox")` → `kb-contrib-<时间>.json` | 导出自动；导入+晋升人工 |
| **B. Git PR**| 有 git 的团队 | 只改 `knowledge/inbox/**`；CI 跑 KB 门禁 | CI 判候选区；晋升人工 |
| **C. 匿名缺口上报**| 不便回传正文者 | 只上报问法哈希 + 平台 + 版本，不上报正文/代码/项目名/IP | P3，默认关 |

- 导出**强制脱敏**：IP / 本机路径 / 凭据 / 主机名 / 手机号 → 占位符；未脱敏须 `internal=True`（维护者自用）。
- 总账侧流水线：隐私闸门 → 去重（命中则合并进已有条目）→ 我方复验 → 问法登记（≥5 条，含 ≥1 反例）
  → **人工签字**→ `status=verified` 进索引 → 回执。
- 没过闸的留在总账 `knowledge/inbox/`：可见、**不进检索**、不当依据。

## 8. 门禁（P1）

| 检查 | 判据 |
|---|---|
| front-matter 合规 | 必填字段齐全 + status/confidence 取值合法 + verified 必须有 evidence 或 `needs_evidence` |
| `kb_index.json` 新鲜 | `gen_kb_index.py --check`：源哈希 + 篇数一致 |
| 索引只收总账层 | `knowledge/inbox/**` 不进索引 |
| 无问法登记的篇数 | 报数（P1 只报告；P2 起 verified 新条目强制 ≥5 问法） |

## 9. 反模式（看见就拒）

1. 无门禁追加；2. 未验证当结论；3. 用 mtime 当新鲜度；4. **AI 自评通过**；5. 重复文档（先合并）。（无需复验方法：反面清单，非可验项）
