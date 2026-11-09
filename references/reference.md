# 参考信息索引

> 本文件集中放 SKILL.md 之外的参考信息：按需加载表、模板与脚本清单。SKILL.md 只留指针，细节在这里维护。

## 按需加载

| 文件 | 何时读 |
|---|---|
| `references/layer-model.md` | 判断某份文档该放哪层、`status`/`authority` 填什么、要不要加层、怎么改 `_schema.json` |
| `references/process-recording.md` | 写会话档案、分类用户消息、做八维对比、收尾的决策回顾、设计收件箱字段 |
| `references/plan-model.md` | 建/改开发计划、状态词表、加维度或视角、判断某物该是方向还是任务 |
| `references/requirements-ears.md` | 写契约层、把含糊需求改成可判真假的一句话、理解 E13/W7 的边界 |
| `references/check-rules.md` | 校验报错看不懂、要解释"为什么这条必须机器判"、接 CI |
| `references/ecosystem.md` | 要不要换现成工具、哪些交给 lychee / StrictDoc / sphinx-needs、为什么不整套替换 |

## 模板与脚本

| 资源 | 用途 |
|---|---|
| `assets/templates/docs-README.md` | 总入口：§1「想知道 → 读哪份 → 唯一」表 |
| `assets/templates/session-record.md` | 七段会话档案（占位 `{{TITLE}} {{DATE}} {{NO}} {{SCOPE}} {{SLUG}}`；§4 决策块带「拍板 / 依据 / 撤销条件」） |
| `assets/templates/inbox.md` | 问题收件箱（主表 + 已闭环 + 已拒绝；四维状态示例） |
| `assets/templates/verification.md` | 真机验收台账（主表九列 + 观察记录子表 + 判据三型 / 三态 / 三档出口的规则块）；`doc_init` 铺到 `70-过程/真机验收台账.md`；`V1–V6` 只判形式（ADR-007） |
| `assets/templates/timeline.md` | 时间线（含 `devlog-index` 生成区） |
| `assets/templates/dev-plan.md` | 开发计划（三层 + 六维 + 三视角 + 任务双亲的 `功能` 列 + `plan-rank` 生成区） |
| `assets/templates/adr.md` | ADR 六段 + `supersedes`/`superseded_by` 双向链 |
| `assets/templates/requirements.md` | 契约层：EARS 句式 + `verify:` 可执行入口 + 验收口径 + 不得做的事 |
| `assets/templates/features.md` | 功能台账：`F-nnn` + 满足的需求 + 状态链 + 评审 + 代码入口 + 证据 + `考核汇总`，外加「任务考核」表（四格 + 完成于） |
| `assets/templates/direction.md` | 方向卡：一个方向一行（现状 / 为什么是现在 / 用户·起点 / 成功状态 / 路径 / 接缝 / 不覆盖 / 走通验收 / 关联），`P18` 的四格必填 + 复核日 + 引用存在（REQ-018）；末尾「覆盖」表记单条方向线的走通，「链路」表记跨功能点的串联，`P20` 判链路五格 + `@复核日` + 引用存在（REQ-039–041） |
| `assets/templates/design.md` | 设计卡：一个工作一张（`## K<n> · W<n.m> · 标题` + 接口 / 可替换点 / 观测四格 / 选项空间 / 扩展点 / 失败边界 / 任务拆分 / 取舍），`P19` 的三格必填；选项空间由 `W10` 判形状，观测四格由 `W12` 提醒；小改动只写三行，但选项空间仍写 3 行（含不做 / 少做） |
| `assets/templates/observability.md` | 项目侧观测地图（四维 / 四问 / 系统级串联）；`doc_init` 铺到 `40-运行/可观测性.md`；`W12` 只查设计卡四格，不解析这份文档 |
| `assets/templates/feature-check.md` | 实施后的功能对照清单：功能 / 该验什么 / 结论 / 差异 · 证据（四列，差异必须进收件箱）；`doc_init` 把它铺成 `40-运行/功能对照.md`，那才是要填的实例 |
| `assets/templates/alias-table.md` | 术语规范名/禁用别名（E16 的唯一清单） |
| `assets/templates/process-readme.md` | 过程层协议入口：落进 `70-过程/README.md`，登记本项目的落点与惯例（协议正文仍只在 `references/process-recording.md`，这里不复写） |
| `assets/ci/` | pre-commit 与 GitHub Actions 门禁样例 |
| `assets/agents-snippet.md` | 粘进 `AGENTS.md` 的 8 行约定，让习惯默认生效 |
| `scripts/doc_init.py` | 铺骨架（幂等） |
| `scripts/doc_check.py` | 全库校验：`--docs` `--quiet` `--json` `--baseline` `--update-baseline` |
| `scripts/devlog.py` | `new` / `brief` / `ask` / `pending` / `inbox` / `features` / `check` / `index [--check]` |
| `scripts/plan.py` | `index [--check]` / `check [--json]` / `next [--json]`（唯一出口：第一视角第一名 + 方向 → 工作 → 任务 路径）/ `tree [--html] [--json] [--out 路径]`（只读全貌：方向 → 工作 → 任务，带功能、状态、完成于）/ `set-status <T-id> --to <状态> [--commit] [--review] [--dry-run] [--json]`（状态转写：只写既有列、失败零写入、幂等）/ `new-feature …`（五件套批量入口：一次写 REQ / F / W / T / K，自动编号只认表首列、先验后写、失败零写入；`--work-id` 挂已有工作、`--dry-run` 只列清单）；`P1`–`P19`（含方向卡、设计卡、任务双亲与考核、功能汇总可回溯）；`--help` 只读、不写生成区 |
| `scripts/verify.py` | 按契约 `verify:` 真跑：`--timeout` `--dry-run` `--quiet`；失败/超时 exit 1 |
| `scripts/self_test.py` | 自检：把本文「验收」1–40 跑成断言，在临时目录里铺骨架、造错、跨天、校验，不碰真实项目 |
| `scripts/observe.py` | 自身参考实现：`run` 包一条命令、`five-run` 串五连跑、`show` / `status` / `trend` 只读回看；`trend` 按码 + 目标文件跨 run 聚合；记录落 `.dd/observe/runs/`；写失败只降级、不改主命令退出码 |
| `scripts/yaml_rules.py` | front-matter 与 `.skill-metadata.yaml` 的严格 YAML 子集校验；`build.py` / `install.py` / `self_test.py` 共用这一份规则 |

脚本按**表头**识别维度列（单大写字母列即维度），因此加维度、加视角都不用改代码。
