---
title: "DELTA-013 · 档案三落笔口径修正"
layer: contract
domain: 全局
status: snapshot
authority: 4
updated: 2026-11-17
summary: "改 REQ-067：开档只写 §1，§2 的消息行随 §3–§7 收尾一次写成（ISS-138 口径①）。"
tags: [契约, 增量]
delta_id: DELTA-013
target: docs/20-契约/requirements.md
---

# DELTA-013 · 档案三落笔口径修正

本增量**必须**逐字应用锚点；**不得**手工凑合目标行。

## 1. 变更清单

| # | 操作 | 一句话 |
|---|---|---|
| 1 | MODIFIED | 开档只写 §1；§2 的消息行随 §3–§7 收尾一次写成（ISS-138 口径①） |

## 2. 逐字变更

**变更 1 · MODIFIED · REQ-067**

锚点（before，逐字，含首尾）：

```markdown
| **REQ-067** | WHEN 一场会话开档 THE SYSTEM SHALL 只在开档时写 §1–§2，结论齐后一次写成 §3–§7，此后只回写 run_id 一行 | 档案只在三处落笔（开档 / 收尾一次 / run_id 回写）；过程中发现进收件箱或待分诊、不进 §3；旧口径原句（「会话进行中边写边补」/「AI 侧边做边填」/「过程中追加 §2/§4」）0 命中；下一场档案 repeat_edit ≤3 | `python -c "import pathlib,sys; s=pathlib.Path('SKILL.md').read_text(encoding='utf-8'); sys.exit(0 if '档案只落三次笔' in s and '会话进行中边写边补' not in s and 'AI 侧边做边填' not in s else 1)"` | 已实现 | 本场、F-074、W39.1、T39.1.1、K56 | 强制过门 2026-11-17（用户不复述、按推荐落，代价可接受）｜本场 §2 #1 |
```

合并后（after，逐字）：

```markdown
| **REQ-067** | WHEN 一场会话开档 THE SYSTEM SHALL 只在开档时写 §1，§2–§7 结论齐后一次写成，此后只回写 run_id 一行 | 档案只在三处落笔（开档 / 收尾一次 / run_id 回写）；§2 的全部消息行随 §3–§7 一次写成、过程中不落档；发现进收件箱或待分诊、不进 §2–§7；旧口径原句（「会话进行中边写边补」/「AI 侧边做边填」/「过程中追加 §2/§4」/「每句话按 §2 追加一行」）0 命中；下一场多消息会话档案 repeat_edit ≤3 | `python -c "import pathlib,sys; s=pathlib.Path('SKILL.md').read_text(encoding='utf-8'); sys.exit(0 if '档案只落三次笔' in s and '会话进行中边写边补' not in s and 'AI 侧边做边填' not in s and '每句话按 §2 追加一行' not in s else 1)"` | 已实现 | 本场、F-074、W39.1、T39.1.2、K56 | 强制过门 2026-11-17（用户不复述、按推荐落，代价可接受）｜本场 §2 #1；2026-11-17 ISS-138 用户拍板口径①（§2 随 §3–§7 一次写）｜本场 §2 #2 |
```

## 3. 合并记录（合并时填写）

- 合并日期：2026-11-17
- 目标文件合并后的校验：`python scripts/doc_check.py --quiet` 0 error；`plan.py check` / `devlog.py check` 0 error
- 对应会话档案：2026-11-17-004 档 §3.3 / §3.5
