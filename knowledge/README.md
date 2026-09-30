# 📚 knowledge 文档治理规范（唯一权威实践知识，禁止双份）

> 2026-09-09 定规（MCP 结构化整理：消除 knowledge ↔ wiki 双份 44 篇 + MCP_FEATURES 冗余）。
> 本文件是 knowledge/ 的治理约定，改文档前先读。

## 1. 目录结构（两类知识分家）

| 位置 | 内容 | 是否随 Gitee | 检索 |
|------|------|------|------|
| **`knowledge/`**（本目录） | **实践知识唯一权威**：uicontrols（控件字段/API）/ devflow（工程机制）/ hardware（跨平台硬件 API）/ v85x（平台深度，内部）/ t113-car 等 | ✅ 随仓库分发 | ✅ AI 检索主源 |
| `wiki/flythings/`（本地，仓库外） | **官方文档镜像**（developer.flythings.cn 全量：system/upgrade/manifest 等）+ 本地参考资料 | ❌ 不进仓库 | ✅ 本地 rag 索引辅助源 |

⚠️ **practice 文档只放 knowledge/，禁止复制到 wiki/flythings/**（历史双份已清理，别再犯——rag 双命中 + 内容漂移都源于此）。wiki 目录内只允许官方镜像类内容。

## 2. 新增/更新文档流程（照此做）

1. **只改 `knowledge/<分类>/<文档>.md`**——不 Copy 到 wiki（wiki 官方镜像与 knowledge 实践内容互不复制）
2. 文档头部写检索导引（命中条件，参考现有文档格式）；内部引用用相对路径（如 `knowledge/v85x/aw-dvr-runtime-compat.md`）或 `knowledge/` 前缀，**不引用 wiki 实践副本路径**
3. 改完：`kb_tools.py` 版本递增 + `MCP_FEATURES` 顶部加一条精华摘要（版本史：**近期**在 `MCP_FEATURES`，**更早**归档在仓库根 `VERSION_HISTORY.md`；CHANGELOG.md 自 v0.27.31 起已冻结，不再维护）
4. `python rebuild_index_local.py` 重建索引（默认收 wiki 官方 + knowledge 实践，无重复）
5. commit + push origin（release 同步走 PUBLISH.md 流程）

## 3. 维护工具

- **重复检测**：`scripts/check_duplicate.py`——查 knowledge ↔ wiki 双份（字节相同=双命中、不同=漂移），整理后应 0 双份
- **MCP_FEATURES 精简**：治理约定 = 只保留近期精华 + 能力概括（`compact=False` 取近期全量）；**更早版本史归档在仓库根 `VERSION_HISTORY.md`**（CHANGELOG.md 已冻结为历史归档）

## 4. 红线
- 真实 accessKey / 内部工程名（CV201/mark_cv201/UvcJpegTest 等）不进 open 分发内容（master 内部版保留工程上下文，release 版去工程化）
- v85x 深度、方案类（tuya/voip/lylink/车载）只进内部 master，不进 release（PUBLISH.md §3）
