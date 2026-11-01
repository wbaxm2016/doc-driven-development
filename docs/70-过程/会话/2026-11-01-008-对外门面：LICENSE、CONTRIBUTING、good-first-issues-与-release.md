---
title: "2026-11-01 · 008 · 对外门面：LICENSE、CONTRIBUTING、good first issues 与 v2.3.2 release"
layer: process
domain: 协作
status: snapshot
authority: 4
updated: 2026-11-01
session_date: 2026-11-01
session_no: 008
scope: "LICENSE(MIT) / 仓库 description+topics / CONTRIBUTING + PR 模板 / 3 条 good first issue / v2.3.2 release；提交并推送 007 的 README 改动；不 bump 版本、不改包内文件"
decisions: "D1 五件套 + 先提交 007（用户）；D2 MIT（agent）；D3 tag 指 4d126cd（agent）"
open_items: 0
summary: "补齐 LICENSE、description/topics、CONTRIBUTING、3 条 good first issue 与 release。"
tags: [过程, 会话, 门面, 开源]
---

# 2026-11-01 · 008 · 对外门面：LICENSE、CONTRIBUTING、good first issues 与 v2.3.2 release

> 本篇是过程档案，**不构成约束**（authority 4 / snapshot）。收尾时跑 `python scripts/devlog.py check`。

## 1. 本次范围

- **要解决什么**：仓库对外是「能看不能参与」：无 LICENSE（法律上默认保留所有权利）、无 CONTRIBUTING、GitHub description/topics 为空、0 release、0 open issue。外部开发者点进来，不知道能不能用、从哪下手。本场把五件补齐，并把 007 的 README 改动提交。
- **明确不做什么**：不 bump `VERSION`、不改包内文件（`SKILL.md` / `scripts/` / `references/` / `assets/`）、不重建 `dist/`、不重装 5 端；不翻译 README 全文；不做语义 / 合规类能力。
- **承接上期**：007 把 README 改写为白话入口（未提交）；本场先补提交，再补门面。

## 2. 用户侧记录（分类）

| # | 类型 | 用户原话（摘） | 归类理由 | 落点 | 状态 |
|---|---|---|---|---|---|
| 1 | R | 「我要是想要向它人介绍这个项目吸引更多开发者参与，怎么介绍这个项目」 | 定目标：对外介绍与吸引贡献 | §1、§3.1 | 已执行 |
| 2 | D | 「动手」 | 采纳上一轮提议的五件套 | §4 D1 | 已执行 |
| 3 | X | （上轮）「不要直接发版」 | 本场沿用为：不 bump / 不重建 / 不重装；只发布已构建的 2.3.2 | §1、§3.1 | 已执行 |

## 3. AI 侧记录

### 3.1 需求理解

用户要的不是再写一份介绍文案，而是把「介绍发出去能接住人」这件事做实。我把「动手」理解成上一轮列的五件：LICENSE、description + topics、CONTRIBUTING、3 条 good first issue、release；外加一个前置：007 的 README 还没提交，必须先入库。

**与用户原话的偏差**：上一轮我说「不直接发版」，本场仍不 bump 版本——只把已有的 2.3.2 产物发布成 GitHub Release（tag 指 `4d126cd`），给外部一个稳定下载入口；这不是重新发版，包内能力一字未改。

### 3.2 实现思路

1. **先核现状**：API 查仓库 → 0 star / 0 fork、description 与 topics 为空、0 release；本地无 `LICENSE` / `CONTRIBUTING`。五件都真缺，不是补文档。
2. **先提交 007**（`ca7cc0b`）：介绍发出去，别人看到的必须是新 README，否则第一屏还是旧术语表。
3. **门面**：MIT `LICENSE` + README「许可证」段；仓库 description（中文一句话）+ 8 个 topics；`CONTRIBUTING.md`（先跑 / 改哪 / 硬规则 / 怎么验 / 提交约定 / 发版边界）+ PR 模板。
4. **给「可认领」的入口**：3 条 good first issue——英文 TL;DR、issue 模板、`install.py` 多余文件告警；每条写背景 / 改哪里 / 验收 / 预计耗时，第 3 条挂 ISS-039。
5. **release**：tag `v2.3.2` 指向 `4d126cd`（2.3.2 产物所在提交），附 `dist` 资产。第一次用 `Invoke-RestMethod -Form` 上传，资产被改了字节（124450 → 124717）；删掉重传原始字节（`ReadAllBytes` + `Content-Type: application/zip`），下载核对 sha256 一致。
6. **记账**：计划新增 D7 / W7.1 / T7.1.1–T7.1.5；收件箱 ISS-039 的落点补 issue #3。

### 3.3 组件归属与系统位置

| 功能 / 能力 | 组件 | 代码或文档位置 | 对应 REQ / ADR | 依赖 / 被依赖 |
|---|---|---|---|---|
| 法律许可 | `LICENSE` | 仓库根 | — | 所有使用者 / 贡献者 |
| 参与入口 | `CONTRIBUTING.md` + `.github/pull_request_template.md` | 仓库根 / `.github/` | 用户 2026-11-01 目标 | 外部贡献者 |
| 可发现性 | description + topics | GitHub 仓库设置（API） | — | 搜索与首页访客 |
| 可认领任务 | issue #1–#3 | GitHub Issues | ISS-039（#3） | 新贡献者 |
| 版本下载 | tag `v2.3.2` + Release 资产 | GitHub Releases | `4d126cd`（2.3.2 dist） | 安装者 |

**系统位置**：这些都在**包外**，不进 `.skill`；发布物仍是 2.3.2，技能能力未变。5 端装的仍是 2.3.2，本场不需要重装。

### 3.4 实现 vs 需求 gap

| 期望（用户要的） | 现在 | 证据（文件/命令） | 缺口 | 下一步 |
|---|---|---|---|---|
| 能合法使用 | MIT LICENSE 就位，README 有许可证段 | `LICENSE`、`README.md` | 无 | — |
| 能被搜到 / 看懂 | description + 8 个 topics | API GET 实测 | 无 | — |
| 知道怎么参与 | CONTRIBUTING + PR 模板，README 有链接 | 两个文件；`README.md`「维护这个仓库」 | issue 模板还没做（已开 #2） | 等认领 |
| 有可认领的活 | 3 个 open issue，均带 `good first issue` | issues #1–#3 | 还没有人认领 | 等社区 |
| 有稳定下载 | v2.3.2 release，资产 sha256 与 dist 一致 | `releases/tag/v2.3.2` | 无 | — |
| 介绍发出去看到新 README | 007 已提交 `ca7cc0b` | `git log` | 待 push | 本场 push |

### 3.5 本轮提出的问题

| ISS | 一句话 |
|---|---|
| — | 无新增 ISS。ISS-039 的落点补了 issue #3，仍是 deferred（等工作被认领或修完） |

## 4. 决策与选项对比

### D1 · 本场做哪几件

| 选项 | 语义正确性 | 实现成本 | 改动半径 | 可逆性 | 长期维护 | 用户可感知 | 可验证性 | 风险 |
|---|---|---|---|---|---|---|---|---|
| A 五件套 + 先提交 007（选中） | 5 | 3 | 2 | 4 | 4 | 5 | 5 | 2 |
| B 只写介绍文案 | 2 | 5 | 0 | 5 | 1 | 3 | 2 | 3 |
| C 只补 LICENSE | 3 | 5 | 0 | 5 | 2 | 2 | 4 | 4 |

**结论**：选 A。介绍文案解决「怎么说」，门面解决「说完别人能不能接住」；五件里缺任一件，转化都会断在具体一步。
**是否暂定**：否。
**拍板**：用户。
**依据**：「动手」——用户本轮原话，采纳上一轮列出的五件套。
**撤销条件**：若 GitHub 权限 / 网络导致 release 或 API 设置失败，保留已完成项并登记 ISS，不把未完成写成完成。

### D2 · 许可证选哪个

| 选项 | 语义正确性 | 实现成本 | 改动半径 | 可逆性 | 长期维护 | 用户可感知 | 可验证性 | 风险 |
|---|---|---|---|---|---|---|---|---|
| A MIT（选中） | 5 | 5 | 1 | 4 | 5 | 3 | 5 | 2 |
| B Apache-2.0 | 4 | 4 | 1 | 3 | 4 | 3 | 5 | 2 |
| C 暂不放 | 2 | 5 | 0 | 5 | 1 | 2 | 2 | 4 |

**结论**：选 A。项目无专利池、无商标诉求，MIT 最短、最常见，外部开发者一看就懂；现在没有外部贡献，将来若要换 Apache-2.0 成本最低。
**是否暂定**：否。
**拍板**：agent 自选。
**依据**：技能 / 脚本类工具的常见选择；README 设计原则里没有专利授权诉求。
**撤销条件**：若出现企业用户要求专利授权，或要合并 Apache-2.0 代码，改 Apache-2.0 并更新 README 与 NOTICE。

### D3 · release 的 tag 指向哪个提交

| 选项 | 语义正确性 | 实现成本 | 改动半径 | 可逆性 | 长期维护 | 用户可感知 | 可验证性 | 风险 |
|---|---|---|---|---|---|---|---|---|
| A `4d126cd`（2.3.2 dist 提交，选中） | 5 | 5 | 0 | 5 | 5 | 3 | 5 | 1 |
| B 当前 HEAD | 3 | 5 | 0 | 5 | 3 | 3 | 5 | 2 |

**结论**：选 A。tag 是版本锚点，应指向产物对应的提交；HEAD 之后还有 README / docs 改动，不代表 2.3.2。
**是否暂定**：否。
**拍板**：agent 自选。
**依据**：`git log -- dist/doc-driven-development-2.3.2.skill` = `4d126cd`；`build.py --check-dist` 证明 dist 与 HEAD 包内一致。
**撤销条件**：若发现 2.3.2 产物不是从 `4d126cd` 构建，改 tag 指向正确提交并重建 release。

## 5. 开放项

| ISS | 事项 | 类型 | 为什么现在不定 | 回到条件 |
|---|---|---|---|---|
| ISS-039 | `install.py` 只覆盖不清理，装完不提示多余文件 | 风险 | 已开 good first issue #3，等外部认领或下次动 `install.py` 时修 | 有人认领 #3，或下次改 `install.py` |

## 6. 本次产出

| 类型 | 路径 | 说明 |
|---|---|---|
| 法律 | `LICENSE` | MIT 全文 |
| 文档 | `CONTRIBUTING.md` | 先跑 / 改哪 / 硬规则 / 怎么验 / 提交约定 / 发版边界 |
| 模板 | `.github/pull_request_template.md` | PR 检查清单（自测 / 构建 / 文档校验 / 影响面） |
| 文档 | `README.md` | 加「维护这个仓库」参与入口 + 「许可证」段 |
| 仓库设置 | description + 8 topics | API 实测：`ai-agent, agent-skills, documentation, adr, developer-tools, ai-coding, context-engineering, python` |
| Issues | #1 / #2 / #3 | 均带 `good first issue`；#3 挂 ISS-039 |
| Release | `v2.3.2` | tag → `4d126cd`；资产 `doc-driven-development-2.3.2.skill`，sha256 `60d90094…`，下载核对一致 |
| 计划 | `docs/00-门面/开发计划.md` | D7 / W7.1 / T7.1.1–T7.1.5；41 任务 / 19 工作 |
| 收件箱 | `docs/70-过程/问题收件箱.md` | ISS-039 落点补 issue #3，仍 deferred |
| 提交 | `ca7cc0b` + 本场提交 | 007 已提交；本场改动随后提交并推送 |

## 7. 交接（下次从这里开始）

- **下一步**：无（计划 41/41 全完成；外部可认领的 3 个 issue 不属于本仓计划）
- **现在在哪**：007 已提交 `ca7cc0b`；本场改动已提交并推送；远端 `main` 与本地 0/0；tag `v2.3.2` 已推，Release 已建且资产哈希与 `dist/` 一致；5 端仍是 2.3.2，无需重装。
- **别踩的坑**：① 二进制资产别用 `Invoke-RestMethod -Form` 传（本场把 124450 字节传成 124717）——用原始字节 + `Content-Type: application/zip`，上传后下载核 sha256；② tag 指产物提交，不指 HEAD；③ description 用 `PATCH /repos`，topics 要单独 `PUT /repos/.../topics`；④ README / CONTRIBUTING 是包外文件，改它们不用发版；⑤ `install.py --only <id>` 只装指定宿主，别用裸 `install.py` 把没装的产品算成失败。
- **读这几篇就够**：本档 §3.2；`CONTRIBUTING.md`；`README.md` 的「维护这个仓库」；issues #1–#3；`docs/70-过程/问题收件箱.md` 的 ISS-039。
