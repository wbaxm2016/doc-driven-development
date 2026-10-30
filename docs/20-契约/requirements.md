---
title: "需求清单"
layer: contract
domain: 全局
status: active
authority: 1
updated: 2026-10-29
summary: "必须成立的需求与验收口径；每条一个 REQ 编号，用 EARS 句式写成可判真假的句子。"
tags: [契约, 需求, EARS]
---

# 需求清单

> 契约层只写**约束**，不写解释。每条需求都要能被一句命令或一次实测判定真假。
>
> **句式（EARS）**：写不出这个句式，说明还没想清楚——先去开 ADR，别在这里糊一句「必须好用」。
>
> | 类型 | 句式 |
> |---|---|
> | 常规行为 | `WHEN <触发条件> THE SYSTEM SHALL <可观察的行为>` |
> | 异常处理 | `IF <异常> THEN THE SYSTEM SHALL <兜底行为>` |
> | 持续约束 | `WHILE <状态成立> THE SYSTEM SHALL <行为>` |
> | 无条件约束 | `THE SYSTEM SHALL <行为>`（只在确实无触发条件时用） |
>
> **`verify:`**：写一条**能直接跑**的命令或测试文件路径（CI 据此回检实现）；「验收」写人读的判定口径。两者都必须能判真假。

## 1. 需求

| 编号 | 需求（EARS 句式） | 验收（一条命令 / 一次实测） | `verify:`（可执行入口） | 状态 | 依据 |
|---|---|---|---|---|---|
| **REQ-001** | WHEN 一场会话按「收尾五连跑」结束时 THE SYSTEM SHALL 三份校验脚本全部以 0 退出 | 三份脚本各自以 0 退出；`doc_check --quiet` 输出 `errors=0` | `python scripts/doc_check.py --quiet && python scripts/devlog.py check && python scripts/plan.py check` | 已实现 | `SKILL.md` 日常三动作 |
| **REQ-002** | WHEN 契约层写入一条 `REQ-nnn` 条款 THE SYSTEM SHALL 该条款使用 EARS 句式并同时给出可执行的验收命令 | 删掉某条的「必须/不得」→ 报 `[E13]`；条款行无规范措辞 → 报 `[W7]` | `python scripts/self_test.py -v`（第 6 组判 E13；W7 目前只能人工抽查） | 已实现 | `references/check-rules.md` |
| **REQ-003** | WHEN 一条 EARS 契约被新增或修改 THE SYSTEM SHALL 其正文保留 `verify:` 字段指向可执行的测试或命令，且缺失时被 `doc_check` 报出 | 删掉某条的 `verify:` 单元格 → 退出码 1 并报出 `[E18]` | `python scripts/self_test.py -v`（第 13 组判 E18） | 已实现 | [ADR-001](../30-决策/adr/ADR-001-与SDD的分工.md)、ISS-002 |

## 2. 不得做的事

> 只写「要什么」不写「不许什么」，约束就是半边的。这一节不得为空。

- **不得**把 `authority: 4` 的过程记录（会话档案）当作裁决依据，或据此直接修改契约——要成为约束必须回写本节或新开 ADR。
- **不得**为一次小改动重写全量契约、或把契约层扩写成单体长 spec（ADR-001 备选 C/D）。
- **不得**引入没有「回到条件」与「触发信号」的决策记录——单向门会让半年后没人敢推翻它。
- **不得**把 `docs/` 加进 `build.py` 的 `ROOT_FILES` / `INCLUDE_DIRS`：安装包结构与自校验会一并失效。

## 3. 变更记录

| 日期 | 变更 | 依据 |
|---|---|---|
| 2026-10-29 | 创建 | — |
| 2026-10-29 | 落 REQ-001/002（已实现）、REQ-003（待实现）；补四条「不得」 | [ADR-001](../30-决策/adr/ADR-001-与SDD的分工.md) |
| 2026-10-29 | 需求表加 `verify:` 列（T1.2.1）；判缺检查仍待 T1.2.2，状态不变 | [ADR-001](../30-决策/adr/ADR-001-与SDD的分工.md)、W1.2 |
| 2026-10-29 | `verify:` 缺失必须报 E18（T1.2.2 完成），REQ-003 转已实现 | [ADR-001](../30-决策/adr/ADR-001-与SDD的分工.md)、W1.2 |
