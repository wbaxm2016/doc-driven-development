---
title: "功能台账"
layer: operation
domain: 全局
status: active
authority: 2
updated: 2026-11-01
summary: "需求 → 功能 → 入口 → 证据：一张表兼做功能设计与已实现清单。"
tags: [功能, 台账, 追溯]
---

# 功能台账

> **一张表两种读法**：筛 `待评审 / 已评审 / 实施中` 是设计视图；筛 `已对照 / 已验收` 是已实现清单。
>
> 状态链：`待评审 → 已评审 → 实施中 → 已对照 → 已验收`（`搁置` 旁挂）。
> **已评审及以后**：`满足的需求` 写 `REQ-nnn`（可多条，用 `、` 分隔）；`—（历史）` 只留给先于契约存在的老功能，且只能停在 `已验收`。
> **已对照 / 已验收**：`代码入口` 必须真实存在；**已验收**还必须有 `verify:` 与 `证据`（哪条命令/哪组自测 + 日期）。

| ID | 功能 | 满足的需求 | 验收口径（人读） | `verify:`（机器跑） | 代价 | 状态 | 评审 | 代码入口 | 证据 | 考核 | 完成于 |
|---|---|---|---|---|---|---|---|---|
| **F-001** | 铺骨架与全库校验 | REQ-002 | `doc_init --target . --full` 幂等；front-matter/链接/层/段/码全判（E1–E24、W1–W7） | `python scripts/self_test.py -v` | M | 已验收 | 满足✓ 可做✓ 代价M｜T4.2.1 / T5.1.1｜2026-10-31 | scripts/doc_init.py、scripts/doc_check.py | `self_test` 第 3、6、23、25、26 组（2026-10-31） | 做法：doc_init 铺骨架、doc_check 一条规则一个码｜一致：全｜代价：M（同估）｜结论：保留 | 276f235 |
| **F-002** | 契约 `verify:` 回检 | REQ-003 | 缺 `verify:` 即报 E18；`verify.py` 按命令真跑，失败/超时 exit 1 | `python scripts/verify.py` | M | 已验收 | 满足✓ 可做✓ 代价M｜T1.2.2｜2026-10-29 | scripts/verify.py、scripts/doc_check.py | `verify` 3 条契约 3/3 通过（2026-10-31） | 做法：契约行强制 verify，verify.py 按命令真跑、失败即 exit 1｜一致：全｜代价：M（同估）｜结论：保留 | 276f235 |
| **F-003** | 契约增量（delta） | REQ-003 | 根目录只放 `proposed`；已合并进 `_archive/` 且 `after` 仍在目标（E19–E21） | `python scripts/self_test.py -v` | M | 已验收 | 满足✓ 可做✓ 代价M｜T1.1.2｜2026-10-30 | scripts/doc_check.py、docs/20-契约/_delta/README.md | `self_test` 第 15 组 | 做法：契约只写增量，E19–E21 判未合并/锚点唯一/归档一致｜一致：全｜代价：M（同估）｜结论：保留 | 276f235 |
| **F-004** | 过程档案与七段校验 | REQ-001 | `new` 编号与文件名正确；七段顺序与引用可判（S1–S7） | `python scripts/self_test.py -v` | M | 已验收 | 满足✓ 可做✓ 代价M｜T2.2.1｜2026-10-30 | scripts/devlog.py | `self_test` 第 2、9 组 | 做法：new 生成七段骨架，check 判段序与 ISS 引用｜一致：全｜代价：M（同估）｜结论：保留 | 24961bd |
| **F-005** | 交接锚点与开场简报 | REQ-001 | §7 首行「下一步：<任务编号>」必须存在于计划（S8/S9）；`brief` 只读给一屏 | `python scripts/self_test.py -v` | M | 已验收 | 满足✓ 可做✓ 代价M｜T2.2.1 / T2.3.1｜2026-10-30 | scripts/devlog.py | `self_test` 第 17、18 组 | 做法：交接首行锚定计划任务（S8/S9），brief 只读一屏｜一致：全｜代价：M（同估）｜结论：保留 | 24961bd |
| **F-006** | 用户侧落点与时间线 | REQ-001 | §2 已填类型的行必须有落点（S10）；时间线行数 ≠ 档案数即提醒（S11） | `python scripts/self_test.py -v` | M | 已验收 | 满足✓ 可做✓ 代价M｜T2.4.1 / T4.1.2｜2026-10-31 | scripts/devlog.py | `self_test` 第 19、21 组 | 做法：§2 落点必填（S10）+ 时间线陈旧提醒（S11）｜一致：全｜代价：M（同估）｜结论：保留 | 24961bd |
| **F-007** | 待分诊与开工门禁 | —（历史） | `ask` 记问题不占 ISS 号；未清完 `new` 拒绝；延期 >5 条也拒 | `python scripts/self_test.py -v` | M | 已验收 | —（历史） | scripts/devlog.py | `self_test` 第 20 组 | —（历史） | —（历史） |
| **F-008** | 转正与新增前查重 | —（历史） | `pending --as iss` 必须给 `--relation`；`new` 自动分配 ISS 号并追加行；`inbox --similar` 给候选 | `python scripts/self_test.py -v` | M | 已验收 | —（历史） | scripts/devlog.py | `self_test` 第 24 组 | —（历史） | —（历史） |
| **F-009** | 计划排序与状态词 | —（历史） | `plan.py index` 三视角加权；改一行后 `--check` 报过时；状态词白名单（P3） | `python scripts/self_test.py -v` | M | 已验收 | —（历史） | scripts/plan.py | `self_test` 第 4 组 | —（历史） | —（历史） |
| **F-010** | 需求状态与出处 | —（历史） | 状态词白名单（E22）；「已实现」必须指得出 ADR/任务/文件（E23） | `python scripts/self_test.py -v` | S | 已验收 | —（历史） | scripts/doc_check.py | `self_test` 第 25 组 | —（历史） | —（历史） |
| **F-011** | 清单化安装 | —（历史） | `install.py` 按清单探查并安装；装完写 `MANIFEST.txt` + `.install.json`，可逐文件核对 | `python install.py --from dist` | M | 已验收 | —（历史） | install.py、install-targets.json | 五宿主 `v2.2.2 source=dist`、各 29 文件、0 失败（2026-10-31） | —（历史） | —（历史） |
| **F-012** | 打包与验包 | —（历史） | `build.py` 体检 → 自测 → 打包 → 验包；产物与 HEAD 包内逐字节一致（`--check-dist`） | `python build.py --check-dist` | M | 已验收 | —（历史） | build.py | 2.2.2 包 27 文件哈希吻合、sha256 `cbf1a4fb…`（2026-10-31） | —（历史） | —（历史） |
| **F-013** | 缺配置不猜层表 | —（历史） | `_schema.json` 与 `_layers.json` 都缺 → exit 2 并给出补齐命令 | `python scripts/self_test.py -v` | S | 已验收 | —（历史） | scripts/doc_check.py | `self_test` 第 23 组 | —（历史） | —（历史） |
| **F-015** | 需求 × 功能 × 证据对账 | REQ-004 | 每条需求至少一个功能覆盖（W8 提醒）；证据里的自测组号必须真实存在（E26） | `python scripts/self_test.py -v` | S | 已验收 | 满足✓ 可做✓ 代价S｜T5.4.1｜2026-10-31 | scripts/doc_check.py | `self_test` 第 30 组（2026-10-31） | 做法：需求覆盖用 W8 提醒、证据组号用 E26 阻断｜一致：全｜代价：S（同估）｜结论：保留 | 276f235 |
| **F-014** | 存量债棘轮 | —（历史） | `--update-baseline` 写入基线；`--baseline` 只许降不许升 | `python scripts/self_test.py -v` | S | 已验收 | —（历史） | scripts/doc_check.py | `self_test` 第 8 组 | —（历史） | —（历史） |
| **F-016** | 会话收尾的决策回顾（并入 `decision-review` 的能力） | REQ-005 | 收尾时逐条给背景 / 影响 / 依据（用户原话）/ 撤销条件；缺项标「断链」并进待分诊；台账里没有的决策先补档再回顾；`待定` 不升格成 `已定` | `python scripts/self_test.py -v`（实现后补组号） | M | 实施中 | 满足✓ 可做✓ 代价M｜T6.1.1、T6.1.2｜2026-11-01 | — | — | — | — |

## 已评审提案

### F-016 · 会话收尾的决策回顾

- **评审结论（2026-11-01，通过·收窄版）**：满足 REQ-005 ✓；可实现（§4 / ADR / 待分诊 / git 都现成）✓；代价 M。收窄为：只对「用户拍板的决策」做四问；§4 决策块加「拍板 / 依据 / 撤销条件」，背景与影响沿用 §1/§3；存量不追溯，机器码只判最新一篇且另开一步（T6.1.2）。归属：形状归本技能，DSH 仓 `session-handoff` 改回引用（ISS-034）。

- **来源**：DSH 侧的 `decision-review` 技能——收尾时对本会话每条决策给「背景 / 影响 / 依据 / 撤销条件」，防的是「台账里只剩一行摘要：结论还在，成因没了」。它只装在 `~/.dsh/skills` 一处；本技能按 `install-targets.json` 分发到 5 个产品，并进本技能，装了本技能的地方就都有了这套回顾。
- **为什么放进本技能**：本技能已经有 ADR（背景 / 备选 / 影响 / 撤销条件 + 双向取代链）和七段会话档案的「决策与选项对比」；缺的只是收尾时**逐条现查**（不凭记忆看台账 / ADR / git）并**判断链**这一步，以及「依据」这一格（引文照抄用户原话）。补这一步即可，不需要第二套技能。
- **落地要改什么**：① `SKILL.md` 的收尾动作加一步「决策回顾」；② `references/process-recording.md` 加一节（四问 + 现查四路：台账 / ADR mtime / 待分诊 / git）；③ 机器校验（`devlog.py check` 新码：档案 §4 的决策行必须写撤销条件）作为**另一步**，不与文本迁移合并，避免一次发布会话里混进脚本改动。
- **不做**：不改已装副本（`skills/doc-driven-development/` 是发布产物，`MANIFEST.txt` 有 sha256，改它会被下次 `install.py` 覆盖）；不新建第三处「决策台账」——契约层 + ADR 已经是权威。
- **已答（2026-11-01）**：边界变化成立——决策回顾的形状归本技能，收尾流程（该不该收、归档单）仍交 `session-handoff`；本技能「边界」一节在 T6.1.1 同步改写。评审门三问见上方「评审结论」。

## 变更记录

| 日期 | 变更 |
|---|---|
| 2026-10-31 | 从「已实现能力清单」改为「功能台账」：加 `满足的需求` / `代价` / `状态` / `代码入口` / `证据` 五列；历史能力标 `—（历史）`，新功能必须挂 `REQ` |
| 2026-11-01 | 加 F-016（待评审）+ REQ-005：决策回顾并入本技能；计划不动（评审门未过不进计划） |
| 2026-11-01 | F-016 评审通过（收窄版）→ `已评审`；落 D6 / W6.1 / T6.1.1–T6.1.2；归属冲突记 ISS-034 |
