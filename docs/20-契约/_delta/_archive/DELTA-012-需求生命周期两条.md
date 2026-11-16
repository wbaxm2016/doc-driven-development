---
title: "DELTA-012 · 需求生命周期两条"
layer: contract
domain: 全局
status: snapshot
authority: 4
updated: 2026-11-16
summary: "新增 REQ-065（改句后旧确认不得沿用）与 REQ-066（删除只走归档删除、去「作废」）。"
tags: [契约, 增量]
delta_id: DELTA-012
target: docs/20-契约/requirements.md
---

# DELTA-012 · 需求生命周期两条

本增量**必须**逐字应用锚点；**不得**手工凑合目标行。

## 2. 逐字变更

**变更 1 · ADDED · REQ-065**

位置：REQ-064 行之后（需求表末尾）

```markdown
| **REQ-065** | WHEN 一条既有需求通过 MODIFIED 增量改句、且改后仍标「已实现」 THE SYSTEM SHALL 要求该行的「确认」列与 before 行不同——改句后旧确认不得沿用，沿用即由 `[E20]` 报出；需求状态词只允许 `待实现` / `已实现` / `阻塞` / `搁置` 四个 | 临时项目造 MODIFIED delta：after 照抄 before 的确认 → `[E20]`；换新确认 → 0 error；需求行写「作废」→ `[E22]`；`self_test` 第 31 组含正反例 | `python scripts/self_test.py -v`（第 31 组） | 已实现 | 本场、K55、W38.1、T38.1.1、ADR-008 | 复述✓ 2026-11-16｜本场 §2 #2 |
```

**变更 2 · ADDED · REQ-066**

位置：REQ-065 行之后（需求表末尾）

```markdown
| **REQ-066** | WHEN 一条需求要被删除 THE SYSTEM SHALL 只走 `_delta` 的 `REMOVED` 并移入 `_archive/` 留档这一条路，不提供「作废」状态；`E22` 白名单不得再含「作废」，被删编号不得复用 | 需求行写「作废」→ `[E22]`；REMOVED delta 合并归档后 → 0 error；`self_test` 第 31 组含正反例；`verify.py` 不再跳过「作废」行 | `python scripts/self_test.py -v`（第 31 组） | 已实现 | 本场、K55、W38.1、T38.1.2、ADR-008 | 复述✓ 2026-11-16｜本场 §2 #2 |
```

## 3. 合并记录

- 合并日期：2026-11-16
- 目标文件合并后的校验：`python scripts/doc_check.py --quiet` 0 error
- 对应会话档案：2026-11-16-003 档 §3.4
