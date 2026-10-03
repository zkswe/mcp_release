---
id: devflow-reusable-components
title: 可复用组件（components）—— 入口：规范在哪、清单在哪
category: devflow
status: review
confidence: manual
verified_at: 2026-10-03
stale_days: 180
origin: total
source: 2026-10-03 收敛为「指针页」：规范真源 = components/README.md；清单真源 = components/ 树（派生页 knowledge/components/components-catalog.md）
needs_evidence: false
platforms: []
tags: [组件规范, 四件套规范, 模块目录约定, 组件怎么写, 代码规范, package 引用, 平台说明模板, 新增模块, 资产型模块]
evidence: []
---
# 可复用组件（components）

> 检索导引：组件规范 / 四件套规范 / 模块目录约定 / 组件怎么写 / 代码规范（review 尺子）/
> package 引用怎么写 / platforms.md 写什么 / 新增模块 checklist / 资产型模块 / 组件怎么接进工程

## 0. 这一页是指针页

它原来自带一份「四件套规范」+ 一份手维护的组件表 + 若干组件实测明细 —— 2026-10-03 收敛掉：
**同一份知识留两处，改一处必漏一处**（实测：本页原写"两种模块形态"，而规范已是**三种**，已经分叉）。
现在只留指向真源的指针：

| 你要找的 | 去这里（真源） |
|---|---|
| 组件化规范：四件套、模块形态、代码规范、package 引用、platforms.md 模板、新增模块 checklist | **`components/README.md`** |
| 有哪些现成组件（含版本/平台/验收到哪一步的详细索引） | **`components/README.md` §7 现有模块** |
| 「有没有现成的 XX 组件」这类检索 | 派生页 `knowledge/components/components-catalog.md` |
| 可检索的组件卡片（形态 / 平台 / 依赖包 / 示例 / 缺件） | `knowledge/components/components-catalog.md`（由 `components/` 树派生） |
| 某组件在某平台可不可用 | `platform_capabilities.json` → 派生页 `knowledge/devflow/platform-capability-matrix.md` |
| 某组件的实测数字与坑 | 该组件自己的 `components/<名>/README.md` + `platforms.md` |
| 平台真缺控件时怎么做自定义控件包 | `knowledge/devflow/custom-widget.md` |

## 1. 一句话

把散落在专题文章/聊天/各工程里的"这么做就对了"沉淀成**可复用模块**：一个模块一个目录，
四件套齐全（`README.md` + `platforms.md` + `Manifest.xml` + `include/src` 或 `lib` 或 `scripts` + `example/`），
**拿去能编、能跑、能查**。规范和清单见上表，本页不复述。

## 2. 为什么收敛成指针页

- **规范抄了两遍**（本页 vs `components/README.md`）→ 留离代码最近的那份（规范那侧也更全）；
- **组件表靠手维护**（原 §0 那张）→ 必然漂移；现在 `components/` 树的形状/依赖/示例由扫描派生，
  而且门禁把那条「**四件套缺一不收**」跑成了可执行校验（`components_catalog.py`）；
- **组件实测数字写在总页里**（原 §7/§8/§9 的 blur / vinyl / imagecache 明细）→ 与组件自己的 README
  重复且更易过期；实测数字的唯一出处是各组件的 README。

---

## 相关

- `components/README.md` —— 组件化落地规范 + 现有模块详细索引（真源）
- `knowledge/components/components-catalog.md` —— 组件卡片（由树派生）
- `knowledge/devflow/custom-widget.md` —— 平台真缺控件时的自定义控件包做法
- `knowledge/devflow/platform-capability-matrix.md` —— 「某平台能用哪些组件」
