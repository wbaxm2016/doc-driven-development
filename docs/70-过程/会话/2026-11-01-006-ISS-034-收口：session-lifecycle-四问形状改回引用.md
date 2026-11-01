---
title: "2026-11-01 · 006 · ISS-034 收口：session-lifecycle 四问形状改回引用"
layer: process
domain: 协作
status: snapshot
authority: 4
updated: 2026-11-01
session_date: 2026-11-01
session_no: 006
scope: "DSH 仓 skills/session-lifecycle/SKILL.md 一处归属改写 + 0.1.1 打包装机 5 端；本仓 W6.2/T6.2.1 与收件箱回写"
decisions: "D1 做 ISS-034 而不是 ISS-036（用户）；D2 只改 DSH 侧那处归属声明（agent）；D3 改包内文件就必须重建 0.1.1 并重装 5 端（agent）"
open_items: 3
summary: "ISS-034 收口：DSH 侧 session-lifecycle 的「四问形状归自己」改回引用本技能；0.1.1 装 5 端；本仓 open 归零。"
tags: [过程, 会话, 跨仓, 口径冲突, 装机]
---

# 2026-11-01 · 006 · ISS-034 收口：session-lifecycle 四问形状改回引用

> 本篇是过程档案，**不构成约束**（authority 4 / snapshot）。收尾时跑 `python scripts/devlog.py check`。

## 1. 本次范围

- **要解决什么**：ISS-034 那条口径冲突——DSH 仓的收尾技能声称「决策回顾四问的形状由本 skill 给出」，而 F-016 已定形状归 doc-driven-development。同一件事两处权威，改一处另一处会悄悄过期。本轮把它改成只剩一处权威，并让 5 端真正看到新文本。
- **明确不做什么**：不动 DSH 仓第二个写者的未提交改动（`side-question/` 等）；不发本仓 2.3.x（本仓 `SKILL.md` 的旧名只登记，见 ISS-038）；不做 ISS-036（回到条件未触发）；不改 `doc_check` 既有 E/W、`_delta`、ADR-001。
- **承接上期**：005 收口了 2.3.2（P13 / yaml_rules 进包 / metadata 修复，5 端 30/30），留下 ISS-034、ISS-036 两条候选与「本地领先 13 个提交待推」。本轮取 ISS-034。

## 2. 用户侧记录（分类）

| # | 类型 | 用户原话（摘） | 归类理由 | 落点 | 状态 |
|---|---|---|---|---|---|
| 1 | R | 「继续 doc-driven-development（仓 D:\career\ai-agent\doc-driven-development）。先读：docs/70-过程/会话/2026-11-01-005-…md §7、docs/70-过程/问题收件箱.md」 | 交回范围并要求先读现状 | §1、§3.2 | 已执行 |
| 2 | R | 「开工前先 git status，确认没有第二个写者。」 | 硬约束：一个仓库一个写者 | §3.2、§7 | 已执行 |
| 3 | C | 「ISS-034 跨仓一行（推荐）」 | 从两个候选中拍板本轮做哪件 | §4 D1 | 已执行 |

## 3. AI 侧记录

### 3.1 需求理解

用户要的是把「同一件事两处权威」收敛成一处，而不是把一行字改得好看。**与交接描述的偏差**：交接写的是「跨仓一行」，现场比这多两步——① DSH 侧该技能已从 `session-handoff` 改名升级为 `session-lifecycle`（`4fae01a`），冲突行搬到了新文件的 §五，按旧路径 grep 会 0 命中；② 改的是**包内文件**，只改源码不重建 dist、不重装 5 端，运行时（含本会话）读到的仍是旧口径——「改了但没生效」等于没改。

### 3.2 实现思路

1. **先侦察再动手**：两仓 `git status` 都跑；DSH 仓有第二个写者的未提交改动（`side-question/`、`.dsh/direction.md`、以及该仓里 doc-driven-development 的 2.3.2 装机副本），所以只允许 `git add` 指定文件 + `git commit --only`。
2. **只改认定错的一侧**：F-016 已定「决策回顾的形状归 doc-driven-development」，所以错的是 DSH 侧那句「由本 skill 给出形状」；本仓 §边界 那处只是**旧名**（不是归属冲突），另立 ISS-038 等下次发版同批改。
3. **改包内文件就必须重建**：`VERSION` 0.1.0 → 0.1.1，`build.py` 体检 + 打包 + 验包，`install.py` 装 5 端，再独立按 `MANIFEST.txt` 逐端核哈希（`install.py` 只覆盖不清理，不核一遍不知道端上真是什么）。
4. **只提交该提交的**：DSH 仓提交 `7d47958`，6 个文件（`SKILL.md` / `VERSION` / `MANIFEST.txt` / `.install.json` / 新旧两个 dist 包），第二个写者的改动一个没碰。
5. **本仓回写**：新增 W6.2 / T6.2.1 记账，ISS-034 进闭环表，另立 ISS-038（旧名）、ISS-039（装机残留），收件箱 open 归零。

### 3.3 组件归属与系统位置

| 功能 / 能力 | 组件 | 代码或文档位置 | 对应 REQ / ADR | 依赖 / 被依赖 |
|---|---|---|---|---|
| 决策回顾四问的形状 | 本仓技能正文 | `SKILL.md` 收尾动作 + `references/process-recording.md` + §4 模板 | F-016、REQ-005 | 被 DSH 侧 `session-lifecycle` 引用 |
| 四问形状的引用（不再定义） | DSH 侧技能 | `skills/session-lifecycle/SKILL.md` §五 第 151 行 | ISS-034 | 依赖本仓 |
| 打包与装机 | DSH 侧脚本 | `skills/session-lifecycle/{build,install}.py`、`install-targets.json` | ISS-034 | 产物 `dist/session-lifecycle-0.1.1.skill` |
| 台账回写 | 文档 | `docs/00-门面/开发计划.md`、`docs/70-过程/问题收件箱.md` | ISS-034、ISS-038、ISS-039 | 被 `plan.py` / `devlog.py` 校验 |

**系统位置**：形状的唯一权威在**本仓**（`doc-driven-development`）；DSH 侧 `session-lifecycle` 只描述「什么时候做回顾」与「结论怎么落地」，形状一句引用。5 端装的是 0.1.1 的 3 个包内文件（`SKILL.md` + `references/*2`）。

### 3.4 实现 vs 需求 gap

| 期望（用户要的） | 现在 | 证据（文件/命令） | 缺口 | 下一步 |
|---|---|---|---|---|
| 一处一个权威 | DSH 侧不再声称形状归自己，改回引用 | `skills/session-lifecycle/SKILL.md:151`；`grep 四问` 只剩「形状归 `doc-driven-development`」 | 本仓 `SKILL.md` 边界仍写旧名 `session-handoff` | ISS-038，下次发 2.3.x 同批 |
| 改动真正到达运行时 | 5 端 `session-lifecycle` v0.1.1、3 文件哈希与 `MANIFEST.txt` 全等 | 逐端核对脚本输出（5×`bad=[] extra=[]`，dsh 端另有残留见 ISS-039） | DSH 需重开会话才加载新文本 | 用户下次开会话 |
| 不干扰第二个写者 | DSH 仓只多出 `7d47958` 一个提交，别人的改动原样 | `git status` 前后对比；`git log --oneline -2` | — | — |
| 推送 | **没推成**：`git ls-remote` 与 `git push` 均报 `Recv failure: Connection was reset`（github.com:443） | §7 首条 | 本仓本地已领先 `origin/main` 15 个提交（含本轮的 `c798cb8`）；DSH 仓没有配 `origin`（纯本地仓） | 网络恢复后先推本仓 |

### 3.5 本轮提出的问题

| ISS | 一句话 |
|---|---|
| ISS-038 | 本仓 `SKILL.md` 边界仍写旧名 `session-handoff`，与 DSH 侧改名后的 `session-lifecycle` 不符 |
| ISS-039 | `~/.dsh/skills/session-lifecycle` 除 3 个包内文件外还留着 `build.py` / `install.py` / `dist/` / `.sandbox-probe.txt`——`install.py` 只覆盖不清理 |

## 4. 决策与选项对比

### D1 · 本轮做哪一件

| 选项 | 语义正确性 | 实现成本 | 改动半径 | 可逆性 | 长期维护 | 用户可感知 | 可验证性 | 风险 |
|---|---|---|---|---|---|---|---|---|
| A ISS-034（选中） | 5 | 4 | 2 | 5 | 5 | 2 | 4 | 2 |
| B ISS-036 | 2 | 3 | 3 | 3 | 2 | 1 | 2 | 4 |
| C 只等网络 | 3 | 5 | 0 | 5 | 1 | 1 | 1 | 1 |

**结论**：选 A。ISS-036 自己的「回到条件」没触发（stale 0 次、回写未超 60 次），提前做会多出第二条状态写路径；ISS-034 反而是收件箱里唯一还 open 的一条。
**是否暂定**：否。
**拍板**：用户（「ISS-034 跨仓一行（推荐）」）。
**依据**：「ISS-034 跨仓一行（推荐）」——采纳推荐项。
**撤销条件**：若 DSH 侧装机后哈希不等或该仓出现冲突，回滚 `7d47958` 并退回 0.1.0。

### D2 · 改哪一侧

| 选项 | 语义正确性 | 实现成本 | 改动半径 | 可逆性 | 长期维护 | 用户可感知 | 可验证性 | 风险 |
|---|---|---|---|---|---|---|---|---|
| A 只改 DSH 侧那句归属（选中） | 5 | 5 | 1 | 5 | 5 | 1 | 5 | 1 |
| B 只改本仓 | 2 | 4 | 2 | 4 | 3 | 1 | 4 | 3 |
| C 两侧都改 + 发 2.3.3 | 5 | 2 | 4 | 3 | 4 | 2 | 4 | 3 |

**结论**：选 A。F-016 已定形状归本仓，声明「归自己」的是 DSH 侧，改它即收敛；本仓那处是旧名而非归属冲突，为它发一次版不值当（C 还会把第二个写者仓里的装机副本搅乱）。
**是否暂定**：否；回看条件：ISS-038 若因别的原因必须提前发版，再一起改。
**拍板**：agent 自选。
**依据**：F-016 决策 + 「一处一个权威」+ 「一个仓库一个写者」。
**撤销条件**：若复查发现本仓其实也重新定义了四问形状（两份都要收），则改走 C。

### D3 · 改完文本要不要重建 0.1.1

| 选项 | 语义正确性 | 实现成本 | 改动半径 | 可逆性 | 长期维护 | 用户可感知 | 可验证性 | 风险 |
|---|---|---|---|---|---|---|---|---|
| A 重建 + 装 5 端（选中） | 5 | 4 | 3 | 4 | 5 | 3 | 5 | 2 |
| B 只改文本并提交 | 3 | 5 | 1 | 5 | 2 | 1 | 3 | 4 |
| C 改文本不提交 | 1 | 5 | 0 | 5 | 1 | 1 | 1 | 5 |

**结论**：选 A。改的是包内文件，不重建就是「源码对、端上旧」——正是 2.3.2 那轮修的同一类病（dist 与 HEAD 同名不同物）。
**是否暂定**：否。
**拍板**：agent 自选。
**依据**：005 的坑②③ 与 `build.py` 的验包纪律；装机后逐端核哈希。
**撤销条件**：若某端装机失败或哈希不等，退回 0.1.0 并登记 ISS。

## 5. 开放项

| ISS | 事项 | 类型 | 为什么现在不定 | 回到条件 |
|---|---|---|---|---|
| ISS-036 | 状态回写靠手工编辑、编辑前没重读导致 stale | 机会 | 工具化会产生第二条状态写路径，收益不足；触发条件未到 | 单会话回写 >60 次或 stale ≥3 次，或下次改 plan/devlog 写文件路径时 |
| ISS-038 | 本仓 `SKILL.md` 仍写旧名 `session-handoff` | 文档债 | 改包内文件必须走一次 build + 5 端重装，不值当单独发版 | 下次发 2.3.x / 5 端重装时 |
| ISS-039 | `~/.dsh/skills/session-lifecycle` 混着开发产物，`install.py` 只覆盖不清理 | 风险 | 不影响运行，届时与装机脚本一起改 | 下次动该技能装机或改 `install.py` 时 |

## 6. 本次产出

| 类型 | 路径 | 说明 |
|---|---|---|
| 技能（DSH 仓） | `skills/session-lifecycle/SKILL.md` §五 第 151 行 | 形状改回引用本技能；不再自称形状权威 |
| 版本（DSH 仓） | `skills/session-lifecycle/VERSION` | 0.1.0 → 0.1.1 |
| 产物（DSH 仓） | `dist/session-lifecycle-0.1.1.skill` | sha256 `921ce7c0…`、12.8 KB、3 文件 |
| 安装 | 5 端 `skills/session-lifecycle` | v0.1.1、3 文件、source=dist、逐端哈希与 `MANIFEST.txt` 全等 |
| 提交（DSH 仓） | `7d47958` | 只含该技能的 6 个文件，第二个写者的改动未动 |
| 计划 | `docs/00-门面/开发计划.md` | 新增 W6.2 / T6.2.1；§8 变更记录一行 |
| 收件箱 | `docs/70-过程/问题收件箱.md` | ISS-034 闭环；新增 ISS-038 / ISS-039 |
| 档案 | 本档 | — |
| 实证 | 命令输出 | `build.py` 验包 3/3；`install.py` 5/5、0 失败；逐端核对 5×`bad=[]`；`plan.py check` 36 任务 / 18 工作、0 error |

## 7. 交接（下次从这里开始）

- **下一步**：无（计划 36/36 全完成；候选 = ISS-038 旧名随下次发版清掉、ISS-036 工具化待触发）
- **现在在哪**：① 本仓 `main` 领先 `origin/main` **15 个提交**（`c798cb8` 起往前），`git push` 仍不通（`Recv failure: Connection was reset`，2026-11-01 18:0x 实测）；② DSH 仓 `deepseek-herness` **没有配 `origin`**（纯本地仓），本轮新增提交 `7d47958`，另有第二个写者的未提交改动（`side-question/`、`.dsh/direction.md`、该仓里 doc-driven-development 的 2.3.2 装机副本）——**不要整树提交**；③ 5 端 `session-lifecycle` 已是 v0.1.1；本会话的 DSH 运行时仍读旧文本，重开会话才生效。
- **别踩的坑**：① 技能改名后按旧名 grep 会 0 命中——先确认「这个技能还在不在、现在叫什么」再动；② 改包内文件就必须重建 dist 并重装，否则是「源码对、端上旧」；③ DSH 仓有第二个写者，只能用 `git add <指定文件>` + `git commit --only`；④ `install.py` 只覆盖不清理，装完必须另写一遍哈希核对（ISS-039 就是这么发现的）；⑤ Git 的 `LF will be replaced by CRLF` 警告在本仓是常态，不用管。
- **读这几篇就够**：本档 §3.2；`docs/70-过程/问题收件箱.md` 的 ISS-034 / ISS-038 / ISS-039；DSH 仓 `skills/session-lifecycle/SKILL.md` §五。
- **补记（2026-11-01 22:07，推送核验）**：上面「现在在哪 ①」已被本条取代——远端**早已**在 `195a83d`，本仓与 `origin/main` 现在 **0/0 完全同步**（推送 0 收到 0 引用、拉取 0 收到 0 引用），没有待推提交；当时写的「领先 15 个提交」是本地 `origin/main` 引用陈旧（自 18:0x 无网）造成的假象，不是真有 15 个提交等着推。本轮 `git push` **一个提交都没发出去**（非交互终端取不到凭据：`credential.helper=manager`，报 `could not read Username`），那 15 个提交是别处推上去的。网络实情与可用配方：直连 `github.com:443` 不通（`Test-NetConnection` False、无 `http_proxy` 配置）；走本机 `127.0.0.1:7897` 时 schannel 报 `SEC_E_NO_CREDENTIALS`，**换 openssl 后端才通**——`git -c http.proxy=http://127.0.0.1:7897 -c http.sslBackend=openssl ls-remote --heads origin` → `195a83d`（exit 0）。另：VS Code（18:09 起在跑）占着 `.git/FETCH_HEAD`，`git fetch` 会报 `Permission denied`，不影响结论。已登记 ISS-040。
