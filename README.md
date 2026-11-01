# doc-driven-development

和 AI 写代码，最贵的不是写，是这三件事：发现一个新问题就拐进去，回头主线已经凉了；上下文越堆越多，脑子里装不下整个系统；换一个 Agent，又得从头讲一遍。

这个 Agent Skill 用**两条线 + 分层**接住这三件事：需求线管「必须成立什么」，方向线管「先做哪个」；发现的问题先落地、不打断，下一步只有一个出口，交接写成任何 Agent 都能读、脚本也能查的文档。

想先试一次，clone 下来跑 `python scripts/self_test.py`——约 1 分钟，跑在临时目录，不碰你的项目：

```bash
git clone https://github.com/wbaxm2016/doc-driven-development.git
cd doc-driven-development && python scripts/self_test.py
```

> 命令里的 `python`，在只有 `python3` 的机器上换成 `python3` 或 `py -3`。

下次开新会话，Agent 先读交接和计划，从上次停下的地方接着做。想接进自己的项目，跳到 [5 分钟接入](#5-分钟接入一个真实项目)。

## 和 AI 协作开发，最耗人的三件事

### 1. 发现一个新问题，就拐进去

修一个 bug 时发现「这里其实该重构」，于是顺手重构；重构到一半又发现文档过期……半天过去，原来的主线还在原地。

**怎么接**：发现的问题先记一行，不打断当前话题；问题按「命运」分两类——能关的（缺陷、文档债）有完成判据，关不掉的（优化空间、待决取舍）只挂「回到条件」。方向线是判断「这是不是主线」的参照：不在当前方向上的，进收件箱，不进今天。

### 2. 上下文太多，脑子装不下

需求、功能、决策、问题、下一步全堆在一起，每做一个决定都要把整个系统在脑子里过一遍——这是 AI 协作里最容易被低估的成本。

**怎么接**：两条线 + 分层，把「现在只需要看什么」分开——**任务**回答今天做什么，**工作**回答这块什么时候算完，**方向**回答为什么现在做这块；其余的都落在文档里，不占脑子。方向线还有一个副作用：写「成功状态」和「验收判据」的过程，本身就是在帮你理清思路——很多模糊的需求，是在写方向和工作的过程中才变清楚的。

### 3. 换一个 Agent，就得重讲一遍

今天用这个 Agent，明天换那个；聊天记录带不过去，技术栈、约束、已否方案全要重讲。

**怎么接**：状态不在聊天里，在文档里。交接段的第一行就是「下一步」（任务编号，或「无」）；新 Agent 先跑 `devlog brief`，读一页交接就能接着做。文档是纯 Markdown + 标准库脚本，5 个宿主都能装——换 Agent 的负担，从「重讲一遍」降到「读一页交接」。

## 两条线：一条管「必须成立」，一条管「先做哪个」

**需求线**回答「什么必须成立、做到了没有」：每条需求一句可判真假的话，带一条能跑的验收；每个功能指回需求、代码入口与证据。

**方向线**回答「先做哪个、为什么现在」：方向（1–3 个月）→ 工作（1–3 场会话）→ 任务（一场会话），按六个维度打分、三个视角排序。

两条线不是父子关系：**工作挂在方向上，不挂在需求上**。一条需求可以跨几个工作，一个工作也可以服务几条需求——硬把工作塞到某条需求下面，需求一复杂，排期就跟着需求树一起打结。

**方向线是主线，需求线是底线。** 方向线决定这一段时间系统往哪走；需求线决定每一步是不是真的成立。没有方向线，需求会变成功能堆叠；没有需求线，方向会变成不可验证的路线图。

它们在**功能行**交汇：功能既说「满足了哪条需求」，也说「代码入口与证据」。需求少时一条方向就够；需求一多，方向线就是那根把「先做哪件」串起来的线。

**为什么这能降认知负荷**：方向线把「整个系统」压缩成一句话的成功状态 + 当前这块工作的验收判据；你不需要同时记住所有需求，只需要知道「现在这块为什么做、做到哪算完」。AI 也一样——拿到方向、工作和功能行，它就能沿着一条系统级的线往下做，而不是每次从一句孤立的「帮我实现 X」开始猜上下文。

结构上的精确边界（哪些链接是脚本硬判的、哪些靠人写）见 [产品定位](./docs/00-门面/vision.md)。

## 它跟「多写文档」有什么不一样

普通文档规范靠自觉，这套东西靠脚本：

- **每条规则有码**：`E` 层 / 字段、`W` 警告、`S` 会话、`P` 计划……报错行都带 `[码]`，CI 可以直接 grep。
- **每条需求带一条能跑的命令**：契约用 EARS 句式（`WHEN <条件> THE SYSTEM SHALL <行为>`），旁边写 `verify:`——一个测试文件或命令，`verify.py` 真跑，不是「人工检查一下」。
- **不假装跑过**：目录找不到、配置读不出来就 `exit 2` 并说清原因，绝不返回一个 `errors=0` 的假通过。
- **生成区不手改**：时间线、优先级排序由脚本重建；手改会被下次生成覆盖，也会被检查抓出来。

## 它长什么样

铺完骨架，`docs/` 下会多出 5 层（`--full` 再加 3 层）：**门面**（是什么、下一步做什么）、**契约**（必须成立的需求）、**决策**（一个决定一份 ADR）、**运行**（功能台账：需求 → 入口 → 证据）、**过程**（会话档案、问题收件箱、时间线）。完整目录树与各层职责见 [docs/README.md](./docs/README.md) §4。

`docs/_schema.json` 是层、枚举、段结构、编号规则、路径的唯一来源；加一层改这里，不改脚本。

## 5 分钟接入一个真实项目

### 1. 装技能（先确认它读哪个目录）

装错目录时脚本会打印「安装成功」，而技能列表里根本没有它——这是最容易翻车的一步。

| 产品 | id | 技能目录 |
|---|---|---|
| DeepSeek Harness | `dsh` | `~/.dsh/skills/` |
| 千问办公（QwenWork） | `qwenworkcn` | `~/.qwenworkcn/skills/` |
| 豆包 | `doubao` | `~/Doubao/skills/` |
| Qoder CN | `qoder-cn` | `~/.qoder-cn/skills/` |
| WorkBuddy | `workbuddy` | `~/.workbuddy/skills/` |

在本仓库里，三种装法任选：

```bash
python install.py --list          # 先看本机哪些产品能装、各装到哪
python install.py --only dsh      # 只装一个；id 见上一条输出，可逗号分隔多个
# 或者：把 dist/doc-driven-development.skill 解压到上表对应目录
# 或者：把 .skill 交给安装方的导入入口（卡片 / 上传），由它决定落点
```

装完**重开会话 / 窗口**，确认技能出现在列表里——那才是装上的证据。再自检一次：

```bash
python "$HOME/.dsh/skills/doc-driven-development/scripts/self_test.py"
cat "$HOME/.dsh/skills/doc-driven-development/MANIFEST.txt"   # 核对版本与哈希
```

> `.dsh` 按上表换成你的产品目录；Windows 上 `$HOME` 在 PowerShell 与 Git Bash 里都可用。

### 2. 在项目根目录铺骨架

```bash
cd <你的项目根目录>
python "$HOME/.dsh/skills/doc-driven-development/scripts/doc_init.py" --target .
python scripts/doc_check.py        # 期望：errors=0  warnings=0
```

`doc_init.py` 只在技能目录里（它靠 `../assets/templates` 取模板），不会被复制进项目——所以要用绝对路径。它是幂等的，不会覆盖已有文件。

### 3. 开第一场会话

```bash
python scripts/devlog.py brief     # 只读：上一场停在哪、计划还剩什么、收件箱几条
python scripts/devlog.py new --title "本次主题" --scope "范围（含明确不做什么）"
```

然后正常干活。你说的话会被归到 8 类（问答 / 需求 / 功能 / 实现探讨 / 决策 / 确认否决 / 明确排除 / 其它），每句都有落点；发现的问题进收件箱，不打断你。

### 4. 收尾跑五条

```bash
python scripts/devlog.py check
python scripts/devlog.py index
python scripts/plan.py check
python scripts/plan.py index
python scripts/doc_check.py
```

全部 `0 error` 才算收尾完成。

### 5. 存量项目：先接住，再收紧

老项目一接就报一堆错是正常的。先记下现状，再只许降不许升：

```bash
python scripts/doc_check.py --update-baseline   # 把当前债记成基线
python scripts/doc_check.py --baseline          # 之后只报新增，不许比基线更差
```

## 维护这个仓库

第一次参与先读 [CONTRIBUTING.md](./CONTRIBUTING.md)：怎么跑、改哪里、怎么验。

### 改完先跑一条命令

```bash
python build.py            # 体检 → 自测 → 打包 → 验包
```

`build.py` 会拦下这些「装到别人机器上才炸」的失败：

- `SKILL.md` 的 front-matter 不合规：`name` 必须等于目录名、描述长度 10–1024、双语字段齐全；
- `.skill-metadata.yaml` 缺失，或双语示例少于 2 条；
- `SKILL.md` 点名的 `references/` `assets/` `scripts/` 路径不存在，或包里有文件从没被提到；
- 脚本语法错误；
- `self_test.py` 断言不过；
- 包内文件与源仓库不一致（多一个、少一个、内容不同），或 `MANIFEST.txt` 的哈希对不上；
- `SKILL.md` 没落在包根目录。

`self_test.py` 在临时目录里铺骨架、故意制造错误、验取代链与契约措辞、验跨天开档与引用不存在——跑完不碰任何真实项目。

### 发版

只有**包内文件**变了才要发版：`scripts/`、`references/`、`assets/`、`SKILL.md`、`VERSION`、`.skill-metadata.yaml`。只改 `docs/`、`README.md`、`CHANGELOG.md`、`build.py`、`install.py` 不用发版，`dist/` 仍然有效。

顺序是**先提交、后打包**——反过来会让产物来自脏工作区，说不清它对应哪个提交：

1. 平时改包内文件，先在 `CHANGELOG.md` 的 `## Unreleased` 里攒一笔。
2. 发版：把 `## Unreleased` 改名成 `## <新版本>`，改 `VERSION`（改规则 / 码表算 minor，破兼容算 major）。
3. **先提交**（源码 + `VERSION` + `CHANGELOG`）。
4. `python build.py`：体检 → 自测 → 打包 → 验包。
5. `python build.py --check-dist`：确认产物与 HEAD 的包内文件逐字节一致；包内文件有未提交改动时直接拒绝。
6. 提交 `dist/`，再 `python install.py --from dist` 装到各宿主（`.install.json` 记 `source=dist` 与产物路径）。

`dist/doc-driven-development.skill` 是「最新版」的稳定别名，`dist/doc-driven-development-<版本>.skill` 供锁定版本安装。

### 回滚

- **回到某个功能之前**：功能行的「完成于」记着验收时的 commit 短号——`git revert <commit>`（保留历史）或 `git checkout <commit>^ -- <文件>`（只回退文件）。
- **回到某个需求之前**：先在契约里用 `_delta` 的 `REMOVED` 作废它（编号作废不复用，`_archive/` 留档），再按功能的「完成于」回滚实现。**先改文档、再回滚代码**，否则会出现「代码回退了但需求还写着已实现」。
- **回到某个版本**：发版 tag（`v…`）比功能级 tag 少得多、也更稳定，整仓回退用它。

## 设计原则

1. **结构只写一处**：层、枚举、段结构、编号规则、路径全在项目内的 `docs/_schema.json`，加一层不用改脚本。
2. **规则必须有码，且码必须打印**：每条规则在 `references/check-rules.md` 里有一个码，三份带码脚本的错误行都带 `[码]`，CI 可以直接 grep。**不是每条规则都有断言，而是每条「会静默骗人」的规则都有**。
3. **不假装跑过**：找不到目录、配置读不出来就 `exit 2` 并说清楚，绝不返回 `errors=0` 的假通过。安装也是同一类风险：装到没人读的目录等于没装。
4. **存量债棘轮**：老项目用 `--update-baseline` 当天接入，之后只许降不许升。
5. **只做形式校验**：语义是否合理靠人。外链失效、锚点交给 lychee；合规追溯交给 StrictDoc / sphinx-needs（见 `references/ecosystem.md`）。

## 目录

```
SKILL.md            技能本体：常驻上下文，只放「什么时候做什么」
VERSION             语义版本，唯一来源
build.py            打包 + 验包 + 安装
install.py          按 install-targets.json 装到各宿主
scripts/            doc_init / doc_check / devlog / plan / verify / self_test
references/         按需加载的详细说明（层模型、过程记录、计划模型、EARS、码表、生态选型）
assets/templates/   铺骨架用的模板
assets/ci/          pre-commit 与 GitHub Actions 样例
assets/agents-snippet.md   粘进 AGENTS.md 的 8 行约定
dist/               构建产物（.skill = zip），只允许由 build.py 生成
```

---

## 许可证

MIT，见 [LICENSE](./LICENSE)。可商用、修改、再分发，保留版权声明即可。

这个仓库自己的文档地图见 [docs/README.md](./docs/README.md)；产品定位的权威版本见 [docs/00-门面/vision.md](./docs/00-门面/vision.md)。本文件是入口摘要，定义以那两份与 `SKILL.md` 为准。
