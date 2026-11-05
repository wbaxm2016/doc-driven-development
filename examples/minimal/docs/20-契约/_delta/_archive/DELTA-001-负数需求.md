---
title: "DELTA-001 · 负数平方需求"
layer: contract
domain: 全局
status: snapshot
authority: 4
updated: 2026-11-05
summary: "新增一条负数平方的需求（REQ-002），验证输入为负时结果仍为非负平方。"
tags: [契约, 增量]
delta_id: DELTA-001
target: docs/20-契约/requirements.md
---

# DELTA-001 · 负数平方需求

## 1. 变更清单

| # | 操作 | 一句话 |
|---|---|---|
| 1 | ADDED | 新增负数平方需求（REQ-002） |

## 2. 逐字变更

**变更 1 · ADDED · REQ-002**

位置：需求表末尾

```markdown
| **REQ-002** | WHEN 调用 `python verify_square.py -3` THE SYSTEM SHALL 输出 9 并以 0 退出 | `python verify_square.py -3` → 输出 `9`、退出码 0 | `python verify_square.py -3` | 待实现 | verify_square.py | 采纳✓ 2026-11-05｜示例场景 |
```

**合并要求**：本 delta **必须**按锚点合并进目标文件，**不得**直接删除。

## 3. 合并记录（合并时填写）

- 合并日期：2026-11-05（示例）
- 目标文件合并后的校验：`python ../../scripts/doc_check.py` / `python ../../scripts/plan.py check` / `python ../../scripts/devlog.py check`
- 对应会话档案：`2026-11-05-001-平方计算走通一场.md`


