---
title: "契约增量（_delta）目录与文件约定"
layer: contract
domain: 全局
status: active
authority: 1
updated: 2026-10-30
summary: "改契约只写增量：DELTA 文件的命名、结构、三种操作、合并与归档规则。"
tags: [契约, 增量, delta, 合并]
---

# 契约增量（_delta）目录与文件约定

> 本文件是 `docs/20-契约/_delta/` 的唯一约定来源（计划 T1.1.1 / W1.1）。它只回答三件事：增量放哪、怎么写、怎么合；需求本身写什么仍以 [requirements.md](../requirements.md) 为准。
>
> 依据：[ADR-001](../../30-决策/adr/ADR-001-与SDD的分工.md) 决策 2（契约增量，借鉴 OpenSpec 的 ADDED/MODIFIED/REMOVED + 归档合并）。ADR-001 决策 3 要求新增行为落成带码规则，因此本文件只定形，机器判据由计划 T1.1.2 实现。

## 1. 约定解决什么

契约层是一张表：改一行也要重读全篇，容易漏改相邻条款（[ISS-001](../../70-过程/问题收件箱.md)）。约定：**契约内容的每次改动都必须先写成一篇 DELTA**，声明「加哪行 / 换哪行 / 删哪行」；合并时按锚点机械应用，不整篇重写。

W1.1 的验收是「一篇 delta 合并后主文件无冲突」。本文把「无冲突」定义成四条同时成立：

1. 目标文件里没有合并冲突标记；
2. 每条 `before` / `after` 在目标中恰好出现一次（ADDED 的编号必须尚不存在）；
3. 合并提交里目标文件的 diff **只**包含该 delta 声明的行；
4. 合并后 `doc_check`、`verify.py`、`plan.py check`、`devlog.py check` 全部 0 error。

## 2. 目录

```
docs/20-契约/_delta/
├── README.md                    # 本约定，不是 delta
├── DELTA-001-<短标题>.md        # 未合并：status: proposed
└── _archive/
    └── DELTA-001-<短标题>.md    # 已合并：status: snapshot，只读留档
```

- 根目录**只放未合并**的 delta；根目录出现一篇 = 有一条契约改动尚未合并。
- 合并时**必须**把 delta 移入 `_archive/`，不得直接删除——删掉就没有「只改了哪几行」的留档，只剩主文件的整段 diff。
- `_archive/` 是历史快照：`status: snapshot`、`authority: 4`，不构成约束，也不得被引用来否定 [requirements.md](../requirements.md)（一个事实一处）。
- 归档文件仍在 `20-契约/` 下，`snapshot` 只表示「不构成约束」，不减省形式检查：正文必须保留「必须/不得」（E13），需求正文必须留在代码围栏里（否则 E18 会把增量行当主表条款）。
- 一个 delta **只改一篇**目标文件、只做一个逻辑改动；跨文件或跨主题拆成多篇，保证合并原子、冲突可隔离。

## 3. 文件命名与编号

- 文件名：`DELTA-<三位序号>-<短标题>.md`；短标题不含空格、不带版本号（版本交给 Git）。
- 编号 `DELTA-nnn` 只增不复用；取号 = `git log --all --name-only`（含已归档与已删除）里出现过的最大号 + 1。
- 编号写进 front-matter 的 `delta_id`，同时作为 H1 前缀，便于人读与后续检查。

## 4. DELTA 文件结构

### 4.1 front-matter

仓库统一字段之外，另加 `delta_id` 与 `target`（`target` 写**仓库根相对路径**）：

```yaml
---
title: "DELTA-001 · <短标题>"
layer: contract
domain: 全局
status: proposed
authority: 1
updated: 2026-10-30
summary: "≤80 字，一句话说清加/改/删了什么。"
tags: [契约, 增量]
delta_id: DELTA-001
target: docs/20-契约/requirements.md
---
```

### 4.2 正文骨架

以下是一篇 delta 的正文骨架；示例内容不是真实需求，复制后替换即可。

**1. 变更清单**

| # | 操作 | 一句话 |
|---|---|---|
| 1 | ADDED | 新增导出超时需求 |
| 2 | MODIFIED | 收紧一条既有需求的验收口径 |

**2. 逐字变更**

**变更 1 · ADDED · REQ-004**

位置：需求表末尾（需要插在中间时写「REQ-002 行之后」）

```markdown
| **REQ-004** | WHEN … | … | `…` | 待实现 | … |
```

**变更 2 · MODIFIED · REQ-002**

锚点（before，逐字，含首尾）：

```markdown
| **REQ-002** | WHEN 契约层写入一条 … |
```

合并后（after，逐字）：

```markdown
| **REQ-002** | WHEN 契约层写入一条 … |
```

**3. 合并记录（合并时填写）**

- 合并日期：
- 目标文件合并后的校验：`python scripts/doc_check.py --quiet` / `python scripts/verify.py` / `python scripts/plan.py check` / `python scripts/devlog.py check`
- 对应会话档案：

**逐字**是硬要求：`before` / `after` **必须**从目标文件原样复制（含 `|` 转义与行内代码反引号），不得改写措辞、不得「大意相同」。锚点不是摘要，是可供机械匹配的原文。

**为什么需求正文放在代码围栏里**：`doc_check` 的 E18 只读围栏外的表格行。把增量行放进围栏，避免它被当成主表条款重复检查，同时原文不被 Markdown 渲染、逐字匹配不会被表格转义破坏。T1.1.2 会为围栏内的增量行补专门检查（含 `verify:`）。

## 5. 三种操作

| 操作 | 含义 | 合并动作 | 冲突判据 |
|---|---|---|---|
| ADDED | 新增一条需求 | 按「位置」插入 `after` 行；缺省追加到需求表末尾 | 编号已存在于目标，或插入位置找不到 |
| MODIFIED | 改一条既有需求 | `before` 在目标中恰好出现一次 → 原地替换为 `after` | 出现 0 次或 >1 次 |
| REMOVED | 删除一条需求 | `before` 恰好出现一次 → 删除该行 | 出现 0 次或 >1 次 |

- MODIFIED **不得**改编号；要换编号就写「REMOVED 旧号 + ADDED 新号」，让追溯看得见。
- REMOVED 的编号作废，**不得**复用。
- 同一篇里有多条变更时按 §1 清单顺序应用；任何一条冲突，整篇停止合并，不允许「跳过这条先合别的」。

## 6. 合并流程

1. 前置：`python scripts/doc_check.py --quiet` 为 `errors=0`；delta 的 `status` 是 `proposed`。
2. 逐条按 §5 应用；合并后主文件的 diff **必须**只包含 delta 声明的行。
3. 同一次提交里完成三件事：改目标文件、把 delta 移入 `_archive/`、把 `status` 改成 `snapshot` 并填好 §3 合并记录。
4. 合并后校验：`doc_check --quiet` 0 error、`verify.py` 退出 0、`plan.py check`、`devlog.py check` 各 0 error。
5. 冲突处理：任一锚点不唯一或不存在 → 停止并重写 `before`（rebase），**不得**手工「凑合」出目标文本；两篇 delta 动同一行时，先合并者保留，后合并者按合并后的原文重写锚点。

**回滚**：合并提交可整体 revert；revert 后把 `_archive/` 里的 delta 移回根目录、`status` 改回 `proposed`，再重做，不要改写已发布的历史。

## 7. 边界

- **不得**把 `_delta` 用于 ADR、计划、过程档案：它们各有变更记录与生成区；`_delta` 只服务契约层。
- **不得**把 delta 当会话档案：过程叙述写 `70-过程/会话/`，delta 只写「改哪几行」。
- **不得**在 `_archive/` 里改已合并的 delta：要改契约就开新 delta，让历史保持只读。
- 检查能力边界：本文件只定约定；「未合并 delta」「合并后冲突」的机器判据由计划 T1.1.2 落成带码规则（ADR-001 决策 3：不得只写文档不实现）。

## 8. 变更记录

| 日期 | 变更 | 依据 |
|---|---|---|
| 2026-10-30 | 创建：目录、命名、结构、三种操作、合并与归档 | ADR-001、ISS-001、计划 T1.1.1 |
