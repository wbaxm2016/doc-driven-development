---
title: "DELTA-011 · 交互协议：推荐是默认、问是例外"
layer: contract
domain: 全局
status: snapshot
authority: 1
updated: 2026-11-14
summary: "新增 REQ-064：需要用户做选择时默认给一个推荐，问是例外，被否只追一问。"
tags: [契约, 增量]
delta_id: DELTA-011
target: docs/20-契约/requirements.md
---

# DELTA-011 · 交互协议：推荐是默认、问是例外

> 本篇是契约增量，已合并归档；约定见 `_delta/README.md`（本文件在 `_archive/` 下，相对链接会失效，故只写路径）。

把「怎么把选择交给用户」落成一条可判的契约：需要用户做选择时，**必须**默认给一个推荐（理由 + 最大代价 + 什么情况会改）；并列菜单**不得**再当默认交付；信息不足且会改变推荐时才问（≤3 个），**不得**为了消除 AI 自己的不确定而问；被否只追一句。与 REQ-021（选项空间是记录）、REQ-058（不问批准）互补——本条管呈现，不改谁有权决定。

**1. 变更清单**

| # | 操作 | 一句话 |
|---|---|---|
| 1 | ADDED | 新增 REQ-064：推荐是默认、问是例外、被否追一问 |

**2. 逐字变更**

**变更 1 · ADDED · REQ-064**

位置：需求表末尾（REQ-063 行之后）

```markdown
| **REQ-064** | WHEN 一次回答需要用户在方案 / 判断 / 排期上做选择 THE SYSTEM SHALL 默认先给一个推荐（一句理由 + 最大代价 + 什么情况会改），不把并列选项清单当作默认交付；只在缺失的意图或价值会改变推荐时，先问不超过 3 个具体问题（缺什么、不同回答会改变什么），问完再给推荐；用户否掉推荐时只追问一句「哪一点不对」，不要求用户自拟或改写方案；用户主动提出的方案按新输入处理、不改写成菜单 | 抽 5 次需要用户做选择的回复：每次能指出推荐 / 理由 / 被否后的追问；菜单不再是默认交付；用户自拟选项 ≤1 次（人读） | `python -c "import pathlib,sys; s=pathlib.Path('SKILL.md').read_text(encoding='utf-8'); sys.exit(0 if '推荐是默认' in s and '被否' in s else 1)"` | 已实现 | 本会话、new-feature、F-072、T37.1.1、K54、DELTA-011 | 采纳✓ 2026-11-14｜本场 §2 #6 / #7 / #8 |
```

**3. 合并记录（合并时填写）**

- 合并日期：2026-11-14
- 目标文件合并后的校验：`python scripts/doc_check.py --quiet` 0 error；`python scripts/plan.py check` / `python scripts/devlog.py check` 0 error；REQ-064 的 `verify` 命令 exit 0
- 对应会话档案：2026-11-14-003
