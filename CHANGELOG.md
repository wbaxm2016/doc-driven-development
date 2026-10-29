# 变更记录

## 2.1.0

外部审计（2026-10-29）逐条回归后的修复版。2.0.0 的 22 条自测全绿，却仍然测不出下面第一条——这就是加断言组的原因。

### 修复

- **P0 跨天建档（2.0.0 未修，且自测测不出）**：`doc_init.py` 铺骨架时把 `会话档案模板.md` 里的 `{{DATE}}` 替换成铺骨架那天，`devlog.py new` 只做占位符替换；于是**第二天起每次开档**文件名用真实日期、front-matter 停在铺骨架那天，`devlog check` 必报 `S7`，时间线日期列与档案标题互相打脸，`--date` 补记历史日期同样炸。现在 `cmd_new` 在替换后按本次真实日期强制归一 `updated` / `session_date` 两行；自测第 9 组把"模板停在昨天开档"和"`--date` 补记昨天"两种场景钉住。
  注意：另一种改法（让模板保留 `{{DATE}}`）实测会把 `doc_check` 变成 `E6 updated 非法`，把"铺完首跑 errors=0"的承诺打破——不要那么改。
- **P0 安装到没人读的目录**：`build.py --install` 与 README 都写死 `~/.workbuddy/skills/`，而千问办公读 `~/.qwenworkcn/skills/`，导致"安装成功 + 自测通过"而技能列表里没有它。现在按 `QWENWORK_SKILLS` → `WORKBUDDY_SKILLS` → `~/.qwenworkcn/skills` → `~/.workbuddy/skills` 依次选根目录，新增 `--skills-dir`，安装后校验 `SKILL.md` 确实落盘、打印绝对路径，并提示"重开会话后能在列表里看到"才算装上。
- **`plan.py` 的 `P*` 码只存在于文档**：规则在跑但错误行不带码（`ERROR 任务编号不合规：…`），CI 无法 grep，SKILL/码表里写的"P6/P3"用户在输出里永远找不到。现在三份脚本错误行统一带 `[码]`。
- **前置编号不存在 = 完全静默**：`前置` 写成表里没有的 `T8.8.8` 时 `check` 返回 `errors=0`，任务被永久标 ⛔ 且零诊断。新增 **P11**（前置编号不存在）。
- **工作→方向引用不校验**：`工作` 表方向列写 `D9`（方向表里没有）也通过。新增 **P12**，并让 ⛔ 行把"前置不存在:xxx"直接写出来。
- **配置损坏抛回溯**：`_schema.json` / 基线文件写坏时三份脚本直接 `Traceback`。现在给 `exit 2` + 一行说明（修好它，或删掉回退内置默认）。
- **`70-过程/README.md` 是空占位**：门面 README 把它列为"过程协议唯一载体"，而 `doc_init` 只写了一句 `（待填）`。现在由 `assets/templates/process-readme.md` 落地：只登记本项目的落点与固定动作，协议正文仍在 `references/process-recording.md`，不复写。
- **`python scripts/doc_init.py` 在项目根目录报 `can't open file`**：`doc_init.py` 只存在于技能目录（它要读 `../assets/templates`）。SKILL.md 现在写明用技能目录绝对路径初始化，并把这条收进「现实不配合时怎么办」。

### 新增

- `self_test.py` 断言 22 → **32**：新增第 9 组跨天/补记、第 10 组引用存在性、第 11 组配置损坏；第 3 组的 `P4` 改为必须带 `[P4]` 才通过。
- `.skill-metadata.yaml`：4 条能力各一条中英 query（铺骨架 / 开档案 / 排下一步 / 存量接入），点「使用」不再只预填通用问句。
- `SKILL.md` front-matter 补齐平台要求的双语字段与 `argument-hint`、`user-invocable`；`build.py` 体检现在会拦缺失项。
- `SKILL.md`「验收」补 8–10 条（跨天、引用存在性、配置损坏），并说明 `self_test.py` 就是跑这 10 条。

### 变更

- `build.py` 体检要求 `.skill-metadata.yaml` 存在且双语齐，示例数 2–5；MANIFEST 的 `files:` 拆成 `payload_files:` 与 `files_in_package:`（后者含 MANIFEST 自身，两者差 1 是有意的，旧写法看着像少算一个文件）。
- 码表数量口径校正：2.0.0 写"扩到 39 条"，按其自己列出的 `E1–E17 / W1–W7 / D1–D2 / S1–S7 / P1–P10` 实为 43 条；加上 P11/P12 后本版本是 **45** 条。
- README 设计原则 2 改成实话：不是"每条规则都有断言"，而是"每条会静默骗人的规则都有"；并补"码必须打印出来"。
- `assets/templates/dev-plan.md` §1 增加编号"写法"列（`D1` / `W1.1` / `T1.1.1`），与 `P1`/`P9` 的强制格式对齐；`docs-README.md` §4 目录树标明哪些层是 `--full` 才有。
- `agents-snippet.md` 的"收尾四连跑"改为"五条命令"（列了 5 条却写 4）。
- `requirements-ears.md` / `check-rules.md` 的 W7 措辞提示词表补全为代码里的 `EARS_CUES`（原来漏了 `GIVEN`/`一旦`/`不许`）。

### 已知不做

- 包结构仍是 `SKILL.md` 落在 zip 根（`build.py` 自校验锁死）。若某个安装方要求顶层同名目录，那是安装方的约定，需要在对方机器上实测后再改，不凭猜改。
- SKILL.md 仍复述部分 references 的枚举词汇表（8 类 / 6 项 / 8 维 / 六维）。这是常驻上下文的取舍，瘦身需要单独一轮，且要防止"agent 不读 references 就少词汇表"。

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
