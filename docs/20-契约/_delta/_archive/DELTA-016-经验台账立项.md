---
title: "DELTA-016 · 经验台账立项"
layer: contract
domain: 全局
status: snapshot
authority: 4
updated: 2026-11-19
summary: "加 REQ-069：项目级经验台账（EXP）一条一行，E33 只判形式、来源要指得出真东西。"
tags: [契约, 增量]
delta_id: DELTA-016
target: docs/20-契约/requirements.md
superseded_by: DELTA-017
---

# DELTA-016 · 经验台账立项

本增量**必须**逐字应用锚点；**不得**手工凑合目标行。

## 1. 变更清单

| # | 操作 | 一句话 |
|---|---|---|
| 1 | ADDED | 加 REQ-069：项目级经验台账（`EXP-nnn`），一条一行（D25 立项） |

## 2. 逐字变更

**变更 1 · ADDED · REQ-069**

位置：需求表末尾（REQ-068 行之后）

```markdown
| **REQ-069** | WHEN 一场开发会话里出现一条下次还会用到的经验（踩过的坑与绕法 / 有效做法与判断口径 / 工具与命令的用法 / 本项目特有的领域知识）THE SYSTEM SHALL 把它记进项目级经验台账 70-过程/经验台账.md 的 EXP-nnn 一行（类别 / 经验 / 适用场景 / 怎么用 / 来源 / 状态），同一件事只写一处，且被规则 / 契约 / ADR / 任务吸收时标「已升级：编号」、不再成立时标「已失效：原因」 | 六条坏例各报并非零退出：表头少一列 / EXP 编号重复 / 类别不在白名单 / 状态写「已升级」却缺去处 / 来源引用不存在的 ISS / 日期不是 YYYY-MM-DD；一条合规经验行三态混排时 0 error；doc_init 铺出的项目带这张台账且首跑 0 error | `python scripts/self_test.py -v`（第 76 组判 E33 正反例） | 待实现 | 本会话、new-feature、F-076、T41.1.1 | — |
```

## 3. 合并记录（合并时填写）

- 合并日期：2026-11-19
- 目标文件合并后的校验：`python scripts/doc_check.py --quiet` 0 error；`plan.py check` / `devlog.py check` 0 error
- 对应会话档案：2026-11-19-003 档 §3.3
- 说明：本行由 `plan.py new-feature` 先落进主表，本篇在合并记录里逐字复述它——同一提交内归档，不留在 `_delta/` 根目录。
