---
title: "DELTA-002 · 收紧 REQ-001 的验收口径"
layer: contract
domain: 全局
status: snapshot
authority: 4
updated: 2026-11-05
summary: "把 REQ-001 的验收口径补全：非法输入时除了退出码 2，还要打印用法。"
tags: [契约, 增量]
delta_id: DELTA-002
target: docs/20-契约/requirements.md
---

# DELTA-002 · 收紧 REQ-001 的验收口径

## 1. 变更清单

| # | 操作 | 一句话 |
|---|---|---|
| 1 | MODIFIED | REQ-001 的验收补上「并打印用法」 |

## 2. 逐字变更

**变更 1 · MODIFIED · REQ-001**

锚点（before，逐字）：

```markdown
| **REQ-001** | WHEN 调用 `python verify_square.py 7` THE SYSTEM SHALL 输出 49 并以 0 退出 | `python verify_square.py 7` → 输出 `49`、退出码 0；`python verify_square.py x` → 退出码 2 | `python verify_square.py 7` | 已实现 | verify_square.py、T1.1.1 | 采纳✓ 2026-11-05｜示例场景 |
```

合并后（after，逐字）：

```markdown
| **REQ-001** | WHEN 调用 `python verify_square.py 7` THE SYSTEM SHALL 输出 49 并以 0 退出 | `python verify_square.py 7` → 输出 `49`、退出码 0；`python verify_square.py x` → 退出码 2 并打印用法 | `python verify_square.py 7` | 已实现 | verify_square.py、T1.1.1 | 采纳✓ 2026-11-05｜示例场景 |
```

**合并要求**：本 delta **必须**按锚点合并进目标文件，**不得**直接删除。

## 3. 合并记录（合并时填写）

- 合并日期：2026-11-05（示例）
- 对应会话档案：`2026-11-05-001-平方计算走通一场.md`

