---
title: "功能台账"
layer: operation
domain: 全局
status: active
authority: 2
updated: 2026-10-31
summary: "需求 → 功能 → 入口 → 证据：一张表兼做功能设计与已实现清单。"
tags: [功能, 台账, 追溯]
---

# 功能台账

> **一张表两种读法**：筛 `待评审 / 已评审 / 实施中` 是设计视图；筛 `已对照 / 已验收` 是已实现清单。
>
> 状态链：`待评审 → 已评审 → 实施中 → 已对照 → 已验收`（`搁置` 旁挂）。
> **已评审及以后**：`满足的需求` 写 `REQ-nnn`（可多条，用 `、` 分隔）；`—（历史）` 只留给先于契约存在的老功能，且只能停在 `已验收`。
> **已对照 / 已验收**：`代码入口` 必须真实存在；**已验收**还必须有 `verify:` 与 `证据`（哪条命令/哪组自测 + 日期）。

| ID | 功能 | 满足的需求 | 验收口径（人读） | `verify:`（机器跑） | 代价 | 状态 | 评审 | 代码入口 | 证据 |
|---|---|---|---|---|---|---|---|---|
| **F-001** | 铺骨架与全库校验 | REQ-002 | `doc_init --target . --full` 幂等；front-matter/链接/层/段/码全判（E1–E24、W1–W7） | `python scripts/self_test.py -v` | M | 已验收 | 满足✓ 可做✓ 代价M｜T4.2.1 / T5.1.1｜2026-10-31 | scripts/doc_init.py、scripts/doc_check.py | `self_test` 第 3、6、23、25、26 组（2026-10-31） |
| **F-002** | 契约 `verify:` 回检 | REQ-003 | 缺 `verify:` 即报 E18；`verify.py` 按命令真跑，失败/超时 exit 1 | `python scripts/verify.py` | M | 已验收 | 满足✓ 可做✓ 代价M｜T1.2.2｜2026-10-29 | scripts/verify.py、scripts/doc_check.py | `verify` 3 条契约 3/3 通过（2026-10-31） |
| **F-003** | 契约增量（delta） | REQ-003 | 根目录只放 `proposed`；已合并进 `_archive/` 且 `after` 仍在目标（E19–E21） | `python scripts/self_test.py -v` | M | 已验收 | 满足✓ 可做✓ 代价M｜T1.1.2｜2026-10-30 | scripts/doc_check.py、docs/20-契约/_delta/README.md | `self_test` 第 15 组 |
| **F-004** | 过程档案与七段校验 | REQ-001 | `new` 编号与文件名正确；七段顺序与引用可判（S1–S7） | `python scripts/self_test.py -v` | M | 已验收 | 满足✓ 可做✓ 代价M｜T2.2.1｜2026-10-30 | scripts/devlog.py | `self_test` 第 2、9 组 |
| **F-005** | 交接锚点与开场简报 | REQ-001 | §7 首行「下一步：<任务编号>」必须存在于计划（S8/S9）；`brief` 只读给一屏 | `python scripts/self_test.py -v` | M | 已验收 | 满足✓ 可做✓ 代价M｜T2.2.1 / T2.3.1｜2026-10-30 | scripts/devlog.py | `self_test` 第 17、18 组 |
| **F-006** | 用户侧落点与时间线 | REQ-001 | §2 已填类型的行必须有落点（S10）；时间线行数 ≠ 档案数即提醒（S11） | `python scripts/self_test.py -v` | M | 已验收 | 满足✓ 可做✓ 代价M｜T2.4.1 / T4.1.2｜2026-10-31 | scripts/devlog.py | `self_test` 第 19、21 组 |
| **F-007** | 待分诊与开工门禁 | —（历史） | `ask` 记问题不占 ISS 号；未清完 `new` 拒绝；延期 >5 条也拒 | `python scripts/self_test.py -v` | M | 已验收 | —（历史） | scripts/devlog.py | `self_test` 第 20 组 |
| **F-008** | 转正与新增前查重 | —（历史） | `pending --as iss` 必须给 `--relation`；`new` 自动分配 ISS 号并追加行；`inbox --similar` 给候选 | `python scripts/self_test.py -v` | M | 已验收 | —（历史） | scripts/devlog.py | `self_test` 第 24 组 |
| **F-009** | 计划排序与状态词 | —（历史） | `plan.py index` 三视角加权；改一行后 `--check` 报过时；状态词白名单（P3） | `python scripts/self_test.py -v` | M | 已验收 | —（历史） | scripts/plan.py | `self_test` 第 4 组 |
| **F-010** | 需求状态与出处 | —（历史） | 状态词白名单（E22）；「已实现」必须指得出 ADR/任务/文件（E23） | `python scripts/self_test.py -v` | S | 已验收 | —（历史） | scripts/doc_check.py | `self_test` 第 25 组 |
| **F-011** | 清单化安装 | —（历史） | `install.py` 按清单探查并安装；装完写 `MANIFEST.txt` + `.install.json`，可逐文件核对 | `python install.py --from dist` | M | 已验收 | —（历史） | install.py、install-targets.json | 五宿主 `v2.2.2 source=dist`、各 29 文件、0 失败（2026-10-31） |
| **F-012** | 打包与验包 | —（历史） | `build.py` 体检 → 自测 → 打包 → 验包；产物与 HEAD 包内逐字节一致（`--check-dist`） | `python build.py --check-dist` | M | 已验收 | —（历史） | build.py | 2.2.2 包 27 文件哈希吻合、sha256 `cbf1a4fb…`（2026-10-31） |
| **F-013** | 缺配置不猜层表 | —（历史） | `_schema.json` 与 `_layers.json` 都缺 → exit 2 并给出补齐命令 | `python scripts/self_test.py -v` | S | 已验收 | —（历史） | scripts/doc_check.py | `self_test` 第 23 组 |
| **F-015** | 需求 × 功能 × 证据对账 | REQ-004 | 每条需求至少一个功能覆盖（W8 提醒）；证据里的自测组号必须真实存在（E26） | `python scripts/self_test.py -v` | S | 已验收 | 满足✓ 可做✓ 代价S｜T5.4.1｜2026-10-31 | scripts/doc_check.py | `self_test` 第 30 组（2026-10-31） |
| **F-014** | 存量债棘轮 | —（历史） | `--update-baseline` 写入基线；`--baseline` 只许降不许升 | `python scripts/self_test.py -v` | S | 已验收 | —（历史） | scripts/doc_check.py | `self_test` 第 8 组 |

## 变更记录

| 日期 | 变更 |
|---|---|
| 2026-10-31 | 从「已实现能力清单」改为「功能台账」：加 `满足的需求` / `代价` / `状态` / `代码入口` / `证据` 五列；历史能力标 `—（历史）`，新功能必须挂 `REQ` |
