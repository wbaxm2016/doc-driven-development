---
title: "技术设计"
layer: architecture
domain: 全局
status: active
authority: 2
updated: 2026-11-01
summary: "仓库结构与校验链路：结构只在 _schema.json 定义，规则必须带码，脚本只用标准库。"
tags: [架构, 校验, 打包]
---

# 技术设计

## 1. 仓库分层

| 目录 | 职责 | 是否进 `.skill` 包 |
|---|---|---|
| `SKILL.md` | 技能本体：常驻上下文，只放"什么时候做什么" | 是 |
| `references/` | 按需加载的详细说明（层模型、过程记录、计划模型、EARS、码表、生态） | 是 |
| `assets/templates/` | 铺骨架用的模板；`assets/ci/` 为 pre-commit 与 Actions 样例 | 是 |
| `scripts/` | `doc_init` / `doc_check` / `devlog` / `plan` / `verify` / `self_test` | 是 |
| `build.py` | 体检 + 自测 + 打包 + 验包 + 安装（`dist/` 的唯一生成者） | 否 |
| `dist/` | 构建产物：稳定别名 + 带版本号两份 | 否（产物本身） |
| `docs/` | 本项目的自举文档层（过程、决策、计划、契约） | **否** |
| `CHANGELOG.md` / `README.md` | 版本演进与仓库开发说明 | 否 |

`build.py` 的 `INCLUDE_DIRS = ("scripts","references","assets")`、`ROOT_FILES = ("SKILL.md","VERSION",".skill-metadata.yaml")` 是包边界的唯一来源；把 `docs/` 加进去会破坏"包内文件与源仓库逐一一致"的验包断言。

## 2. 校验链路（码不重叠）

```
doc_init.py  ──> docs/_schema.json （层/枚举/段结构/编号规则/路径的唯一来源）
                 │
doc_check.py ───> E / W 码：front-matter、链接、ADR 六段与取代链、术语旧称、契约 verify、delta、需求状态与出处、功能台账与需求覆盖、棘轮基线（码表见 references/check-rules.md）
devlog.py    ───> D / S 码：收件箱、会话档案与七段顺序、交接锚点、落点、时间线陈旧
plan.py      ───> P 码：编号、分值、状态词、所属与前置、方向引用、表格截断
verify.py    ───> 按契约 `verify:` 真跑（退出码即结论；CI 在 build 前跑它）
self_test.py ───> 把 SKILL.md 的验收跑成断言（当前 34 组；临时目录，不碰真实项目）
build.py     ───> 体检 front-matter/引用路径/语法 → 自测 → 打包 → 解包再自测 → 安装后自测
```

## 3. 三个关键机制

1. **结构单点定义**：加层、改目录名、加状态词、加段——只改 `docs/_schema.json`，不改脚本。脚本按表头识别维度列（单大写字母列即维度），因此加维度、加视角也不用改代码。
2. **不假装跑过**：找不到 `docs/`、配置读不出来 → exit 2 + 一行说明，绝不返回 `errors=0` 的假通过。安装同理：装到没人读的目录等于没装，所以 `--skills-dir` 与安装后自测是硬要求。
3. **生成区不手改**：时间线与排序视图由 `devlog.py index` / `plan.py index` 重建；`--check` 只比对不写，供 CI 用。

## 4. 不变的骨架 / 可变的肌肉

判断标准只有一条：**改错了会不会让别人的已有工作作废**。

| | 是什么 | 改它要什么 | 例子 |
|---|---|---|---|
| **不变的骨架** | 别人依赖、改了会让已有文档或安装失效的东西 | ADR + 版本号（minor/major）+ 迁移说明 | 层表与 `_schema.json` 的段结构、码段与码表、判定权（谁能改成什么）、七段档案结构、包边界（`INCLUDE_DIRS` / `ROOT_FILES`） |
| **可变的肌肉** | 内容本身，改了只影响这一份 | 一个任务 + 一条断言 + 收尾回写 | 契约条款正文、脚本实现细节、计划排序与任务拆分、会话记录内容、模板文案 |

两条推论：

- 改骨架时**先加断言再改**（否则已有文档会静默失效）；改肌肉时断言只需覆盖这一处。
- 「文档是唯一事实源」约束的是**肌肉**：代码要回到文档里；骨架只在 ADR 里改。

## 5. 已知边界

- 只做形式校验：条款写得对不对、撤销条件是否已成立、语义重复（只有 W2 的 `summary` 相同这一条弱信号）仍需人读。
- 外链失效交给 lychee（cron 跑，不阻塞每次提交）；合规追溯交给 StrictDoc / sphinx-needs。理由见 `references/ecosystem.md`。
