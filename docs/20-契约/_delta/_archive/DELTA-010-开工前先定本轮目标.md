---
title: "DELTA-010 · 开工前先定本轮目标"
layer: contract
domain: 全局
status: snapshot
authority: 1
updated: 2026-11-14
summary: "新增 REQ-063：会话 / 继续 / issue / 分阶段的一轮开工前，先明确本轮要拿到什么。"
tags: [契约, 增量]
delta_id: DELTA-010
target: docs/20-契约/requirements.md
---

# DELTA-010 · 开工前先定本轮目标

> 本篇是契约增量，未合并；约定见 `_delta/README.md`。

本条**必须**在每轮开工前写进本场档案 §1；目标未明确前**不得**进入实现。与 REQ-058 / REQ-061「不逐项批准」互补——这不是多一道门，是把人的判断放回起点。

把「先定目标再动手」从用户的两次口头要求落成一条可判的契约：**任何一轮开工前**（新会话 / 继续上一场 / 做某条 `ISS` / 分阶段实施中的一轮），先把「这一轮要拿到什么效果 / 目的」说清楚并写进本场档案 §1；能从上文确定的复述一句确认，确定不了的先问；目标未明只做读现状与建档。与 REQ-058 / REQ-061「不逐项批准」互补——这不是多一道门，是把人的判断放回起点。

**1. 变更清单**

| # | 操作 | 一句话 |
|---|---|---|
| 1 | ADDED | 新增 REQ-063：开工前先定本轮目标 |

**2. 逐字变更**

**变更 1 · ADDED · REQ-063**

位置：需求表末尾（REQ-062 行之后）

```markdown
| **REQ-063** | WHEN 一场会话开工、继续上一场的工作、做某条 open issue、或一次做不完的需求进入分阶段实施中的一轮 THE SYSTEM SHALL 在动手前先明确用户本轮想要实现的效果与目的，并写进本场档案 §1「要解决什么」；能从用户原话与既有档案确定的，复述一句确认即可；确定不了的先问清；目标未明确前只做读现状、建档等不改变系统的动作 | 抽 3 个真实起点（新会话 / 继续 / issue）各能指出本轮目标写在哪、谁确认的；没有「目标未明就动手」的场 | `python -c "import pathlib,sys; s=pathlib.Path('SKILL.md').read_text(encoding='utf-8'); sys.exit(0 if '开工前先定本轮目标' in s else 1)"` | 已实现 | 本会话、new-feature、F-071、T22.2.1、K53、DELTA-010 | 采纳✓ 2026-11-14｜本场 §2 #3 / #4 |
```

**3. 合并记录（合并时填写）**

- 合并日期：2026-11-14
- 目标文件合并后的校验：`python scripts/doc_check.py --quiet` 0 error；`python scripts/plan.py check` / `python scripts/devlog.py check` 0 error；REQ-063 的 `verify` 命令 exit 0
- 对应会话档案：2026-11-14-003
