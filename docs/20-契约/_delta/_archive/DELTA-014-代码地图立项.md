---
title: "DELTA-014 · 代码地图立项"
layer: contract
domain: 全局
status: snapshot
authority: 4
updated: 2026-11-19
summary: "加 REQ-068：代码地图（生成 + 旁注），一条命令判旁注与代码是否已不一致。"
tags: [契约, 增量]
delta_id: DELTA-014
target: docs/20-契约/requirements.md
---

# DELTA-014 · 代码地图立项

本增量**必须**逐字应用锚点；**不得**手工凑合目标行。

## 1. 变更清单

| # | 操作 | 一句话 |
|---|---|---|
| 1 | ADDED | 加 REQ-068：代码地图四格 + 对象速查表，陈旧可判（D24 立项） |

## 2. 逐字变更

**变更 1 · ADDED · REQ-068**

位置：需求表末尾（REQ-067 行之后）

```markdown
| **REQ-068** | WHEN 有人（人或 AI）要判断某个函数做什么、被谁调用、改动它会牵连什么 THE SYSTEM SHALL 给出代码地图：对 `scripts/*.py` 里每个函数定义给出「做什么 / 谁调我 / 我调谁 / 改它牵连谁」四格，另附对象速查表（类、模块级常量、数据文件与生成产物）；说明文字只写在旁注一处、由代码抽取的部分只由脚本生成，且一条命令能判出旁注与代码已不一致 | 三条各造一个坏例都报并非零退出：旁注漏一个函数定义（覆盖）、旁注某行指向不存在的函数（悬空）、改了代码没重跑生成（陈旧）；干净树上 `check` 退出 0 | `python scripts/codemap.py check` | 待实现 | 本会话、new-feature、F-075、T40.1.1 | — |
```

## 3. 合并记录（合并时填写）

- 合并日期：2026-11-19
- 目标文件合并后的校验：`python scripts/doc_check.py --quiet` 0 error；`plan.py check` / `devlog.py check` 0 error
- 对应会话档案：2026-11-19-001 档 §3.3
