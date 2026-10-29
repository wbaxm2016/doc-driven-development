# 变更记录

## 2.0.0

首个以本仓库为源的版本。相对此前手工打出的 `dist/*.skill`（1.0.0 快照），变化如下。

### 修复

- **假通过**：`doc_init.py --docs 文档` 之后，`devlog.py check` 找不到过程层却返回 `errors=0`，收尾四连跑全绿而实际什么都没校验。三份脚本现在统一 exit 2 并说明该查什么。
- **规则与实现漂移**：`check-rules.md` 写了 W4（取代者为占位）、W5（补记缺日期戳），代码从未实现。现在已实现且被自测覆盖。
- **一处码背两个含义**：原 W3 同时指"链接不可达"和"绝对路径"，拆为 W3 / W6。
- **路径写错**：两处文档把 `docs/_layers.json` 写成 `scripts/_layers.json`；层定义现统一为 `docs/_schema.json`。
- **代码围栏误报**：围栏内与行内代码里的 `[x](y)` 曾被当成真链接，不再报 E7。
- **硬编码状态词**：`plan.py` 只认「已完成」，写「完成」仍会进排序 Top。状态词表收进 `_schema.json`，越界报 P3。
- **编号前缀不校验**：`T9.9.9` 挂在 `W1.1` 下能通过。现在 P6 报前缀不一致。
- **编号唯一性只扫第一个视角**，其余视角的同号任务漏检。

### 新增

- `docs/_schema.json`：层、枚举、七段/六段结构、编号规则、文件名规范、状态词、路径的唯一来源。加一层、改维度不用改代码。
- 码表从 12 条扩到 39 条：`E1–E17` / `W1–W7` / `D1–D2`+`S1–S7` / `P1–P10`。
- EARS 句式契约：`assets/templates/requirements.md` 与 `references/requirements-ears.md`，配 E13（契约层约束措辞）、W7（条款行有无规范措辞）。
- MADR 双向取代链：ADR 增 `supersedes`，E15 校验链必须指向存在的 ADR 并终止在活决策上。
- 棘轮基线：`doc_check.py --baseline` / `--update-baseline`，存量只降不升，老项目当天可接入。
- `--json` 输出，便于接 CI。
- `assets/ci/`：pre-commit 与 GitHub Actions 门禁样例，`doc_init.py --ci` 直接生成。
- `assets/agents-snippet.md`：8 行约定，粘进 `AGENTS.md` 后"开场建档、收尾四连跑"不再依赖人记得。
- `scripts/self_test.py`：把验收清单变成 22 条断言，跑在临时目录。
- `build.py`：单一打包入口，体检 + 自测 + 打包 + 验包 + 安装；产物带 `MANIFEST.txt`（版本 + 每文件 sha256）。

### 变更

- 脚本接受 `--docs` / `--dir`，不再硬编码 `docs/`；自动识别 `docs` / `文档` / `documentation`。
- `SKILL.md` 补 Gotchas（易错点）与 failure modes（`python` 不可用时怎么办、项目已有文档体系怎么办、要过合规审计怎么办）。

### 部署注意

- 与 `learning-assistant` 项目内的 `scripts/docs_lint.py` / `devlog.py` / `plan.py` 同名不同源。迁移时先 `doc_check.py --update-baseline` 记下存量，再逐条收敛；`docs_lint.py` 里的 `DOMAINS`、`ALIASES` 需搬进 `_schema.json` 的 `domain` 与 `50-术语/别名表.md`。
