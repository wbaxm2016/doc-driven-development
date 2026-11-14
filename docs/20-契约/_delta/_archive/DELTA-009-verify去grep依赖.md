---
title: "DELTA-009 · 三条 verify 去 grep 依赖"
layer: contract
domain: 全局
status: snapshot
authority: 1
updated: 2026-11-14
summary: "REQ-052 / REQ-054 / REQ-060 的 verify 从 grep 改 python -c，Windows 本地也能跑。"
tags: [契约, 增量]
delta_id: DELTA-009
target: docs/20-契约/requirements.md
---

# DELTA-009 · 三条 verify 去 grep 依赖

> 本篇是契约增量，已合并归档；约定见 `_delta/README.md`（本文件在 `_archive/` 下，相对链接会失效，故只写路径）。

三条 verify 命令**不得**依赖 `grep`（Windows 上没有这个命令，会把契约判据误红成环境故障）；**必须**用标准库 `python -c` 判断同一个事实。语义与验收口径不变，只换可执行写法。

**1. 变更清单**

| # | 操作 | 一句话 |
|---|---|---|
| 1 | MODIFIED | REQ-052 的 verify 改 `python -c` |
| 2 | MODIFIED | REQ-054 的 verify 改 `python -c` |
| 3 | MODIFIED | REQ-060 的 verify 改 `python -c` |

**2. 逐字变更**

**变更 1 · MODIFIED · REQ-052**

锚点（before，逐字，含首尾）：

```markdown
| **REQ-052** | WHEN 读者打开 SKILL.md THE SYSTEM SHALL 在开头一屏呈现内核总纲（骨架＋两主线）并给 14 个章节各带归属索引，使任抽一条规则都能答出它服务骨架、流程线还是开发者线 | 干净克隆读 SKILL 开头一屏答出骨架＋两主线；任抽 3 条规则（如复述门 / verify: / 回复档位）各答得出归属；self_test 全绿；doc_check / plan check 0 error | `grep -n "内核总纲" SKILL.md` | 已实现 | 本会话、new-feature、F-060、T33.1.1 / T33.1.2、`048f359` / `7c612f0` | 采纳✓ 2026-11-11｜用户拍板「按「骨架＋两主线」落档起草方向卡」（001 档 §4 D4 复述门） |
```

合并后（after，逐字）：

```markdown
| **REQ-052** | WHEN 读者打开 SKILL.md THE SYSTEM SHALL 在开头一屏呈现内核总纲（骨架＋两主线）并给 14 个章节各带归属索引，使任抽一条规则都能答出它服务骨架、流程线还是开发者线 | 干净克隆读 SKILL 开头一屏答出骨架＋两主线；任抽 3 条规则（如复述门 / verify: / 回复档位）各答得出归属；self_test 全绿；doc_check / plan check 0 error | `python -c "import pathlib,sys;sys.exit(0 if '内核总纲' in pathlib.Path('SKILL.md').read_text(encoding='utf-8') else 1)"` | 已实现 | 本会话、new-feature、F-060、T33.1.1 / T33.1.2、`048f359` / `7c612f0` | 采纳✓ 2026-11-11｜用户拍板「按「骨架＋两主线」落档起草方向卡」（001 档 §4 D4 复述门） |
```

**变更 2 · MODIFIED · REQ-054**

锚点（before，逐字，含首尾）：

```markdown
| **REQ-054** | WHEN 一条用户消息到达 THE SYSTEM SHALL 先按既有 8 类判类并为该消息留一条带流程入口的任务记录（会话档案 §2 一行：类型 / 原话 / 入口 / 状态），再按入口推进，不允许无入口直接推进；人话对照：提出需求＝R、寻找方向＝E·D、提出问题＝Q；复合消息以主类接入、判不了先用三问回落（提出需求？寻找方向？提出问题？）仍判不了归 O 回落；映射不替代任何门，判类与记录由 agent 执行，不新增脚本判据、不构成跳过门禁的理由 | SKILL「日常三动作」含「消息路由」小节（映射表＋主类规则＋任务记录规则＋三问回落＋O 回落＋边界句）；AGENTS.md 留指针；8 类定义未被改动；不新增脚本判据；self_test 全绿、五连跑 0 error；任抽 3 条消息（含一条复合消息）各答得出判类、入口与任务记录四格 | `grep -n "消息路由" SKILL.md` | 已实现 | 本会话、new-feature、F-062、T34.1.1 / T34.1.2、`61ce814` | 采纳✓ 2026-11-11｜用户拍板「先拍板消息路由 M1」（005 档复述门：M1 落路由表，代价接受）；升级✓ 2026-11-11｜用户拍板「每条消息判类、落任务记录、指认入口」（009 档复述门过） |
```

合并后（after，逐字）：

```markdown
| **REQ-054** | WHEN 一条用户消息到达 THE SYSTEM SHALL 先按既有 8 类判类并为该消息留一条带流程入口的任务记录（会话档案 §2 一行：类型 / 原话 / 入口 / 状态），再按入口推进，不允许无入口直接推进；人话对照：提出需求＝R、寻找方向＝E·D、提出问题＝Q；复合消息以主类接入、判不了先用三问回落（提出需求？寻找方向？提出问题？）仍判不了归 O 回落；映射不替代任何门，判类与记录由 agent 执行，不新增脚本判据、不构成跳过门禁的理由 | SKILL「日常三动作」含「消息路由」小节（映射表＋主类规则＋任务记录规则＋三问回落＋O 回落＋边界句）；AGENTS.md 留指针；8 类定义未被改动；不新增脚本判据；self_test 全绿、五连跑 0 error；任抽 3 条消息（含一条复合消息）各答得出判类、入口与任务记录四格 | `python -c "import pathlib,sys;sys.exit(0 if '消息路由' in pathlib.Path('SKILL.md').read_text(encoding='utf-8') else 1)"` | 已实现 | 本会话、new-feature、F-062、T34.1.1 / T34.1.2、`61ce814` | 采纳✓ 2026-11-11｜用户拍板「先拍板消息路由 M1」（005 档复述门：M1 落路由表，代价接受）；升级✓ 2026-11-11｜用户拍板「每条消息判类、落任务记录、指认入口」（009 档复述门过） |
```

**变更 3 · MODIFIED · REQ-060**

锚点（before，逐字，含首尾）：

```markdown
| **REQ-060** | WHEN 一条用户消息被回答 THE SYSTEM SHALL 在该回复里点明它的流程入口（8 类之一）并给出一个落点（会话档案 §2 行 / ISS-nnn / D / T / 无新落点），8 类皆然 | 任一回复能直接读出「类 → 入口」与落点一行；§2 的行与回复里的落点对得上 | `grep -n "无新落点" SKILL.md` | 已实现 | `abb06c5`、F-068、T18.3.1 | 复述✓ 2026-11-13｜档案 010 §3.3 |
```

合并后（after，逐字）：

```markdown
| **REQ-060** | WHEN 一条用户消息被回答 THE SYSTEM SHALL 在该回复里点明它的流程入口（8 类之一）并给出一个落点（会话档案 §2 行 / ISS-nnn / D / T / 无新落点），8 类皆然 | 任一回复能直接读出「类 → 入口」与落点一行；§2 的行与回复里的落点对得上 | `python -c "import pathlib,sys;sys.exit(0 if '无新落点' in pathlib.Path('SKILL.md').read_text(encoding='utf-8') else 1)"` | 已实现 | `abb06c5`、F-068、T18.3.1 | 复述✓ 2026-11-13｜档案 010 §3.3 |
```

**3. 合并记录（合并时填写）**

- 合并日期：2026-11-14
- 目标文件合并后的校验：`python scripts/doc_check.py --quiet` 0 error；`python scripts/verify.py` 三条 PASS（Windows 本地，见 2026-11-14-002 档 §6）
- 对应会话档案：2026-11-14-002
