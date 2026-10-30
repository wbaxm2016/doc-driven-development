---
name: doc-driven-development
name_en: Doc-Driven Development
name_zh: 文档驱动的开发过程
description: Treat documents as the single source of truth for development. Dual-sided session records (8 user-side categories, 6 AI-side items, 8-dimension option comparison), an issue inbox that logs findings without interrupting, a generated timeline, ADRs with bidirectional supersede chains, EARS-phrased contracts, and a three-level plan (direction/work/task) scored on six dimensions across multiple views — all machine-validated by stdlib scripts. Use when the user asks to record or trace development process and system evolution, keep discussions and decisions on file, manage and prioritise what comes next, lay down a docs/ hierarchy or single source of truth, backfill verifiable docs into an existing project, or mentions ADR, session records, ISS ids, plan ranking, EARS, or doc drift.
description_en: Treat documents as the single source of truth for development: dual-sided session records, issue inbox, generated timeline, ADRs with supersede chains, EARS-phrased contracts, and a scored three-level plan, all machine-validated. Use for recording/tracing development process, archiving decisions, prioritising next steps, or laying down a verifiable docs/ hierarchy.
description_zh: 用文档当成唯一事实源来管住开发：双侧会话档案（用户侧 8 类 + AI 侧 6 项 + 八维选项对比）、问题收件箱、时间线、ADR（双向取代链）、EARS 句式契约、三层开发计划（方向/工作/任务）配六维优先级与多视角排序，全部带脚本校验与棘轮基线。当用户要求"记录/追溯开发过程与系统演化""把讨论和决策留档""管理下一步做什么并排优先级""搭一套文档体系/唯一事实源""给现有项目补可校验的文档骨架"，或提到 docs/ 分层目录、ADR、会话档案、ISS 编号、开发计划排序、EARS、文档漂移时使用。
argument-hint: Point me at the project root, or paste the decisions and next steps to record
argument-hint_en: Point me at the project root, or paste the decisions and next steps to record
argument-hint_zh: 告诉我项目根目录，或把要留档的讨论结论与下一步候选贴给我
user-invocable: true
---

# 文档驱动的开发过程

## 核心结构

三件事各有一份**唯一**文档，其余文档只做索引或引用：

| 想知道 | 唯一载体 | 谁维护 |
|---|---|---|
| 这件事怎么一步步变成现在这样 | 会话档案（一次会话一份）+ 时间线 | 会话进行中边写边补 |
| 为什么这么定、还摆着哪些选项 | ADR（一文件一决策，带取代链） | 定案时 |
| 下一步做什么、为什么是它 | 开发计划（三层 + 六维 + 多视角） | 每次收尾 |

外加一张**问题收件箱**：过程中发现的一切问题先落地，不打断当前话题。

## 从不空手开始

`doc_init.py` **只在技能目录里**（它要靠 `../assets/templates` 取模板，所以不会被复制进项目）。在项目根目录直接写 `python scripts/doc_init.py` 会报 `can't open file`——初始化必须带技能目录绝对路径：

```bash
python "<技能目录>/scripts/doc_init.py" --target .              # 5 层：门面/契约/决策/运行/过程
python "<技能目录>/scripts/doc_init.py" --target . --full       # 再加 架构/术语/规范
python "<技能目录>/scripts/doc_init.py" --target . --full --ci  # 另写 pre-commit + GitHub Actions
```

技能目录本机是 `~/.qwenworkcn/skills/doc-driven-development`。

幂等，不覆盖已有文件。落地内容：层目录、**`docs/_schema.json`（层/枚举/段结构/编号规则/路径的唯一来源）**、README、开发计划、需求清单、收件箱、时间线、会话模板、ADR 模板、过程层协议入口、别名表、最小占位文档，并把 `doc_check.py` / `devlog.py` / `plan.py` / `verify.py` 复制进 `<target>/scripts`——日常命令才是「在项目根目录跑 `python scripts/<脚本>.py`」这个形式；前三件是收尾门禁，`verify.py` 供 CI 回检契约。

铺完先跑 `python scripts/doc_check.py`，应为 `errors=0`（若有 `E9 层为空`，说明有层没内容：补一篇或从 `_schema.json` 删该层）。

## 日常三动作

**开场**：

```bash
python scripts/devlog.py new --title "本次主题" --scope "范围"
```

> 只改措辞 / 错字 / 格式 / 注释的**轻档**改动不建档、不跑收尾五连跑；判据与「不豁免校验」的边界见硬规则 12。

**过程中**：用户说的每句话按 8 类归档（`Q R F E D C X O`），每行都要有落点；AI 侧边做边填需求理解、实现思路、组件归属、gap。发现任何问题——缺陷、口径冲突、文档债、风险、待决、机会——立刻在收件箱加一行，然后继续当前话题。**不要停下来问用户要不要处理它**。

**收尾**：

```bash
python scripts/devlog.py check      # 七段顺序、front-matter、ISS 引用、文件名
python scripts/devlog.py index      # 重建时间线
python scripts/plan.py check        # 编号 / 分值 / 状态词 / 所属工作 / 前置与方向引用
python scripts/plan.py index        # 重建排序视图
python scripts/doc_check.py         # 全库字段与链接
```

全部 0 error 才算收尾完成。新建档案在填完 §7 前会报 `S6 交接段过短` WARN 与 `S8` 提醒，属正常；§7 已写正文、首行却不是「下一步：<任务编号>」时，`S8` 才是错误。

契约回检另有一条：`python scripts/verify.py` 按每条需求的 `verify:` 真跑（失败/超时 → exit 1，状态=`待实现/阻塞` 的行跳过）。它可能很慢，所以**不在收尾五连跑里**；CI 每次 push 跑它，改了契约或测试再本地跑一次。

第一次接入**存量项目**时用棘轮，别试图一天清完：

```bash
python scripts/doc_check.py --update-baseline   # 记下当前债务
python scripts/doc_check.py --baseline          # 之后只许降不许升
```

## 写什么

**会话档案七段**（顺序固定）：本次范围 → 用户侧记录 → AI 侧记录 → 决策与选项对比 → 开放项 → 本次产出 → 交接。
交接段**首行**必须是「下一步：<计划任务编号>」——编号要在计划 §5 的任务表里（`devlog check` 的 `S8`/`S9` 互校）；计划全部完成时写「下一步：无」。
档案 `status: snapshot` + `authority: 4`：它是记录，**不构成约束**。

**用户侧 8 类**：`Q` 提问 / `R` 需求 / `F` 功能 / `E` 实现探讨 / `D` 决策 / `C` 确认否决 / `X` 明确排除 / `O` 其它。
"未定的决策"必须同时进 §5 开放项——否则会烂在档案里。

**AI 侧 6 项**：需求理解（含与用户原话的偏差）/ 实现思路 / 组件归属（组件 + 位置 + REQ 或 ADR）/ 系统位置 / gap 四列（`期望 / 现在 / 证据 / 缺口`，无证据只写"未核实"）/ 本轮提出的问题。

**决策对比 8 维**：语义正确性、实现成本、改动半径、可逆性、长期维护、用户可感知、可验证性、风险（允许"两者相当"）。
被否决的选项**不删**：写清当时为什么没选 + **回到条件** + **触发信号**。

**契约用 EARS 句式**：`WHEN <条件> THE SYSTEM SHALL <行为>`。写不出触发条件，说明还没想清楚——先去开 ADR，别在契约里糊一句"必须好用"。每条需求另带 `verify:` 列：一条能直接跑的命令或测试文件路径，**用反引号包住**（`verify.py` 只执行第一个反引号片段）；写成"人工检查一下"等于没写。详见 `references/requirements-ears.md`。

**开发计划三层**：方向 `D-n`（写成 `D1`）/ 工作 `W-n.m`（写成 `W1.1`）/ 任务 `T-n.m.k`（写成 `T1.1.1`）。唯一分层判据——**会话收尾能不能一句话说清"这个做完了"**。编号前缀是结构：`T1.2.3` 的所属必须是 `W1.2`；这三条格式与引用关系都由 `plan.py check` 机器判（码 `P1`–`P12`，输出里带 `[P?]`，可直接 grep）。

**六维**（分越高越先做，成本取反）：`U` 用户可感知 / `C` 闭环贡献 / `S` 系统完备 / `R` 正确性风险 / `V` 可验证 / `E` 实施成本。
**三视角权重**：尽快看到效果、系统更完备、核心功能优化——加视角只是加一行权重，不改脚本。

**三条硬约束**（优先于分数）：门禁 > 优先级；`R=5` 且动已存数据则置顶；前置未解标 ⛔ 不排期。

## 硬规则

1. **一个事实一处**：出现两份定义同类内容，删弱的那份或降为 `reference`，不要两边同步维护。
2. **过程不构成约束**：要成为约束，必须回写契约或新开 ADR。
3. **只记要点，不逐字转录**：原话摘句 ≤ 2 行。
4. **发现即登记**：不打断用户；收件箱不是待办清单，排序归计划。
5. **`ISS-nnn` 只增不复用**；`done` 的条目从主表移入「已闭环」表（两处都留会报 D1）。
6. **状态只被证据推进**：`已实现（未验收）` ≠ `已完成`；状态词必须在白名单里，否则报 P3。
7. **生成区不手改**：时间线与排序视图由脚本重建。
8. **`title` 必须与正文 H1 逐字一致**（从模板复制后最常忘）。
9. **模板内只写纯文本路径**：模板放在上层目录却要指向子目录时，相对链接两头都不对。
10. **`summary` ≤ 80 字**；`updated` 必须是真实日期，失真比错误更坏。
11. **结构只在一处定义**：加层、改目录名、加状态词、加段——改 `docs/_schema.json`，不要改脚本。
12. **改动分级**：判据只有一条——**这次改动有没有改变事实**。只改措辞、错字、格式、注释，且不碰契约条款、ADR、开发计划、码表、`_schema.json` 与脚本行为，算**轻档**：不新开会话档案、不跑收尾五连跑，但仍要跑改动真正触及的校验（文档 → `doc_check`；档案/收件箱 → `devlog check`；计划 → `plan check`；脚本 → `self_test`）；只要动了上述任一处（含改脚本行为、加层改段），就是**重档**，走满日常三动作与收尾五连跑。**分级只决定过程成本，永不豁免校验**——同一份文件在哪一档都过同一套检查，报错照报。

## 坑（都是真实踩过的，不是假设）

- **从模板复制会话档案后忘改 `title`** → E4 立刻报。顺序应该是：先改 front-matter 的 `title/session_date/session_no/scope`，再写正文。
- **在模板里写相对链接** → 模板被复制到 `会话/` 子目录后，指向 `../00-门面/x.md` 的链接两头都不对。模板内只写纯文本路径（不带 `[]()`）。
- **`deferred` 的 ISS 不填「回到条件」** → D2 报错，但更重要的是：三个月后没人知道该不该把它捡回来。
- **把 `authority: 4` 的会话档案当裁决依据** → 记录变成了判决书，整套权威体系随之失效。
- **契约层写成说明文** → 全篇没有「必须/不得」，E13 会拦；但 E13 只能拦形式，句子的可判性仍要人读。
- **ADR 只写「为什么没选」，不写「回到条件」** → 决策变成单向门，半年后没人敢推翻它。
- **写「完成」而不是「已完成」** → 不在状态白名单，P3 直接报（旧版会静默把它当成未完成继续排序，那才难查）。
- **把旧称留在门面/契约/规范里** → E16 会报。历史快照与 ADR 不扫描，它们记录的是当时口径。
- **`.skill` 是构建产物** → 改了源仓库的脚本要重新打包，否则技能里的版本会悄悄落后（这份包就因为漏了重新生成，曾缺 8 条规则）。

## 现实不配合时怎么办

| 情况 | 正确行为 |
|---|---|
| `python` 不可用（Windows 常见，只有 `python3` / `py` / `py -3`） | 换 `python3` 或 `py -3` 重试；仍失败就如实报告"脚本没跑成"，**不要假装跑过了** |
| `python scripts/doc_init.py` 报 `can't open file` | 正常——`doc_init.py` 只在技能目录里。改用 `python "<技能目录>/scripts/doc_init.py" --target <项目>`；装完之后 `doc_check/devlog/plan` 才在 `<项目>/scripts` 里 |
| `docs/` 不在默认位置 | 用 `--docs 文档` 指定。各脚本都会先找 `docs` / `文档` / `documentation`；找不到会**直接 exit 2 并说明**，不再返回 `errors=0` 的假通过 |
| 项目已有一套自己的文档体系 | 先只跑 `doc_check.py` 摸清现状，不要 `doc_init` 覆盖；用 `--update-baseline` 记下存量，再逐条收敛 |
| 校验报错但用户说"先别管" | 把错误原文写进会话档案 §3.5 与收件箱，继续当前话题（符合"发现即登记"），不要静默丢弃 |
| `verify.py` 很慢 / 命令要联网 | 调 `--timeout`、先 `--dry-run` 看要跑什么；不要为了变绿去删契约行或把状态改回「待实现」——那是拿掉证据，不是修好 |
| 用户的项目要过合规审计（ISO 26262 / DO-178C / IEC 62304） | 契约层改用 StrictDoc 或 sphinx-needs 承载，本实践只保留过程层与计划层。见 `references/ecosystem.md` |
| 用户想整套换成 Spec Kit / BMAD / Kiro | 说明它们解决的是"一次变更讲清楚"，不是"项目连续演化留痕"；可借鉴格式，不建议替换过程层 |

## 按需加载

| 文件 | 何时读 |
|---|---|
| `references/layer-model.md` | 判断某份文档该放哪层、`status`/`authority` 填什么、要不要加层、怎么改 `_schema.json` |
| `references/process-recording.md` | 写会话档案、分类用户消息、做八维对比、设计收件箱字段 |
| `references/plan-model.md` | 建/改开发计划、状态词表、加维度或视角、判断某物该是方向还是任务 |
| `references/requirements-ears.md` | 写契约层、把含糊需求改成可判真假的一句话、理解 E13/W7 的边界 |
| `references/check-rules.md` | 校验报错看不懂、要解释"为什么这条必须机器判"、接 CI |
| `references/ecosystem.md` | 要不要换现成工具、哪些交给 lychee / StrictDoc / sphinx-needs、为什么不整套替换 |

## 模板与脚本

| 资源 | 用途 |
|---|---|
| `assets/templates/docs-README.md` | 总入口：§1「想知道 → 读哪份 → 唯一」表 |
| `assets/templates/session-record.md` | 七段会话档案（占位 `{{TITLE}} {{DATE}} {{NO}} {{SCOPE}} {{SLUG}}`） |
| `assets/templates/inbox.md` | 问题收件箱（含示例 ISS 与已闭环表） |
| `assets/templates/timeline.md` | 时间线（含 `devlog-index` 生成区） |
| `assets/templates/dev-plan.md` | 开发计划（三层 + 六维 + 三视角 + `plan-rank` 生成区） |
| `assets/templates/adr.md` | ADR 六段 + `supersedes`/`superseded_by` 双向链 |
| `assets/templates/requirements.md` | 契约层：EARS 句式 + `verify:` 可执行入口 + 验收口径 + 不得做的事 |
| `assets/templates/alias-table.md` | 术语规范名/禁用别名（E16 的唯一清单） |
| `assets/templates/process-readme.md` | 过程层协议入口：落进 `70-过程/README.md`，登记本项目的落点与惯例（协议正文仍只在 `references/process-recording.md`，这里不复写） |
| `assets/ci/` | pre-commit 与 GitHub Actions 门禁样例 |
| `assets/agents-snippet.md` | 粘进 `AGENTS.md` 的 8 行约定，让习惯默认生效 |
| `scripts/doc_init.py` | 铺骨架（幂等） |
| `scripts/doc_check.py` | 全库校验：`--docs` `--quiet` `--json` `--baseline` `--update-baseline` |
| `scripts/devlog.py` | `new` / `check` / `index [--check]` |
| `scripts/plan.py` | `index [--check]` / `check [--json]` |
| `scripts/verify.py` | 按契约 `verify:` 真跑：`--timeout` `--dry-run` `--quiet`；失败/超时 exit 1 |
| `scripts/self_test.py` | 自检：把本文「验收」1–13 跑成断言，在临时目录里铺骨架、造错、跨天、校验，不碰真实项目 |

脚本按**表头**识别维度列（单大写字母列即维度），因此加维度、加视角都不用改代码。

## 边界

覆盖：过程留档与追溯、决策的选项开放性、问题不丢、下一步的唯一排序、形式校验自动化、存量债棘轮、门禁落地。

不覆盖，需另建机制并靠人守：**语义重复**（只有 W2 的 `summary` 相同这一条弱信号）；**ADR 撤销条件是否已成立**（需定期人工复核）；**条款写得对不对**（E13/W7 只判形式）；**改动分级判得对不对**（判据是「是否改变事实」，脚本只能证明「分级不改变校验结果」，判不了这句改动是措辞还是口径变更）；**术语唯一性**只在被登记进别名表之后才生效；**与外部看板 / Issues 的同步**；**外链失效**（交给 lychee，见 `ecosystem.md`）。

## 验收

1. `doc_init.py` 铺完，`doc_check.py` 为 `errors=0`。
2. `devlog.py new` 能建出编号与文件名正确的档案。
3. 故意制造断链、ADR 缺段、`summary` 超长、ISS 重复、分值越界——五种错误都能被报出。
4. 改任一任务行后 `plan.py index --check` 报过时；重跑 `index` 后转为 up-to-date。
5. 时间线按日期倒序列出全部会话，链接可点。
6. 把某篇契约的「必须」删掉 → E13 报；把 `superseded_by` 指向不存在的 ADR → E15 报。
7. 在 `docs/文档` 而不是 `docs/` 下铺骨架 → `doc_check --docs 文档` 通过，`devlog.py` / `plan.py` 不报假通过。
8. **跨天**：铺完骨架后把 `会话档案模板.md` 的日期改成昨天（模拟"骨架是昨天铺的"），再 `devlog.py new` → `check` 必须 0 error，文件名前缀 = `<session_date>-<session_no>-`，时间线日期列与档案标题同一天。2.0.0 就是缺这一条：`doc_init` 把模板里的 `{{DATE}}` 烤死在铺骨架那天，第二天起每次开档都自相矛盾。
9. 前置写一个表里不存在的编号 → `plan.py check` 报 `[P11]`；工作表方向列写 `D9`（方向表里没有）→ 报 `[P12]`。查不出这两条时，任务会被永久标 ⛔ 且没有任何诊断。
10. 把 `_schema.json` 改成非法 JSON → 四份脚本（`doc_check` / `devlog` / `plan` / `verify`）都给 `exit 2` + 一行说明（不是回溯）。
11. 把某条需求 `verify:` 指向的测试改成必然失败 → `python scripts/verify.py` 退出码 1；状态=`待实现` 的行跳过。
12. **改动分级不改变校验结果**：只改一段正文的轻档改动，`doc_check` 的 `errors/warnings` 与改前一致；在同一处制造断链、删掉条款的 `verify:` → `E7` / `E18` 照报；`SKILL.md` 硬规则里恰有一条这样的体量判据。
13. **交接锚点与计划表互校**：交接段首行写「下一步：T1.1.1」（计划表里有）→ `devlog.py check` 0 error；写一个不存在的编号 → `S9` 且 exit 1；首行没有锚点 → `S8`；计划表还有未完成任务却写「下一步：无」→ `S9`。

`scripts/self_test.py` 把上面 1–13 跑成断言；改任何脚本或文档后先跑它，再跑 `build.py`。
