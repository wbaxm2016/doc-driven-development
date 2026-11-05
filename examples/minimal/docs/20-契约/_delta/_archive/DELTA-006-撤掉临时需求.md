---
title: "DELTA-006 · 撤掉临时分隔线需求"
layer: contract
domain: 全局
status: snapshot
authority: 4
updated: 2026-11-05
summary: "撤掉 DELTA-005 新增的 REQ-004，并在 DELTA-005 上标 superseded_by。"
tags: [契约, 增量]
delta_id: DELTA-006
target: docs/20-契约/requirements.md
supersedes: DELTA-005
---

# DELTA-006 · 撤掉临时分隔线需求

## 1. 变更清单

| # | 操作 | 一句话 |
|---|---|---|
| 1 | REMOVED | 撤掉 REQ-004（分隔线并入输出格式时再说） |

## 2. 逐字变更

**变更 1 · REMOVED · REQ-004**

锚点（before，逐字，整行）：

```markdown
| **REQ-004** | WHEN 调用 `python verify_square.py 7` THE SYSTEM SHALL 先打印一行 `---` 再输出结果 | 输出两行：`---` 与 `49` | `python verify_square.py 7` | 待实现 | verify_square.py | 采纳✓ 2026-11-05｜示例场景 |
```

合并动作：删除该行；同时给 `_archive/DELTA-005` 的 front-matter 加 `superseded_by: DELTA-006`。

**合并要求**：本 delta **必须**按锚点合并进目标文件，**不得**直接删除。

## 3. 合并记录（合并时填写）

- 合并日期：2026-11-05（示例）
- 对应会话档案：`2026-11-05-001-平方计算走通一场.md`

