---
title: "DELTA-005 · 临时需求：输出前打印分隔线"
layer: contract
domain: 全局
status: snapshot
authority: 4
updated: 2026-11-05
summary: "新增一条临时需求（REQ-004），随后由 DELTA-006 撤掉，用来演练取代链。"
tags: [契约, 增量]
delta_id: DELTA-005
target: docs/20-契约/requirements.md
superseded_by: DELTA-006
---

# DELTA-005 · 临时需求：输出前打印分隔线

## 1. 变更清单

| # | 操作 | 一句话 |
|---|---|---|
| 1 | ADDED | 新增 REQ-004：输出前打印一行分隔线 |

## 2. 逐字变更

**变更 1 · ADDED · REQ-004**

位置：需求表末尾

```markdown
| **REQ-004** | WHEN 调用 `python verify_square.py 7` THE SYSTEM SHALL 先打印一行 `---` 再输出结果 | 输出两行：`---` 与 `49` | `python verify_square.py 7` | 待实现 | verify_square.py | 采纳✓ 2026-11-05｜示例场景 |
```

**合并要求**：本 delta **必须**按锚点合并进目标文件，**不得**直接删除。

## 3. 合并记录（合并时填写）

- 合并日期：2026-11-05（示例）
- 对应会话档案：`2026-11-05-001-平方计算走通一场.md`


