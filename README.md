# doc-driven-development

一个 Agent Skill：**把文档当成唯一事实源**，让开发过程可追溯、并用文档管理"下一步做什么"。

不是文档规范合集，而是三件带校验的事：

| 想知道 | 唯一载体 | 谁维护 |
|---|---|---|
| 这件事怎么一步步变成现在这样 | 会话档案（一次会话一份，用户侧 8 类 / AI 侧 6 项）+ 时间线 | 会话进行中边写边补 |
| 为什么这么定、还摆着哪些选项 | ADR（一文件一决策，带双向取代链） | 定案时 |
| 下一步做什么、为什么是它 | 开发计划（方向/工作/任务三层 + 六维 + 多视角排序） | 每次收尾 |

外加一张问题收件箱：过程里发现的一切先落地，不打断当前话题。

用法见 `SKILL.md`（Agent 读的那份）；本文件讲**这个仓库怎么开发、怎么发版**。

## 目录

```
SKILL.md            技能本体：常驻上下文，只放"什么时候做什么"
VERSION             语义版本，唯一来源
build.py            打包 + 验包 + 安装
scripts/            doc_init / doc_check / devlog / plan / self_test
references/         按需加载的详细说明（层模型、过程记录、计划模型、EARS、码表、生态选型）
assets/templates/   铺骨架用的模板
assets/ci/          pre-commit 与 GitHub Actions 样例
assets/agents-snippet.md   粘进 AGENTS.md 的 8 行约定
dist/               构建产物（.skill = zip），只允许由 build.py 生成
```

## 开发流程

```bash
python build.py            # 体检 → 自测 → 打包 → 验包
python build.py --install  # 同上，再覆盖安装到 ~/.workbuddy/skills/
```

改完任何脚本或文档，**先跑 `python build.py`**。它会拦下这些情况：

- `SKILL.md` front-matter 不合规（`name` 必须等于目录名、`description` ≤ 1024、行数过大告警）
- `SKILL.md` 里点名的 `references/` `assets/` `scripts/` 路径不存在，或有文件从未被提及
- 脚本语法错误（装到用户机器上才炸是最贵的失败）
- `self_test.py` 断言不过
- 包内文件与源仓库不一致（多一个、少一个、内容不同）
- `MANIFEST.txt` 里任一文件哈希与包内实际内容不符
- `SKILL.md` 没落在包根目录（安装方会识别不到技能）

自测 `scripts/self_test.py` 把 `SKILL.md` 的验收清单变成 22 条断言：自己在临时目录铺骨架、故意制造 5 类错误、验证假通过不再发生、验证棘轮基线。它跑在临时目录，不碰任何真实项目。

单跑自测：

```bash
python scripts/self_test.py      # 22 条断言
python scripts/self_test.py -v   # 顺带打印每条命令的退出码
```

## 发版

1. 改 `VERSION`（语义版本：改规则/码表算 minor，破兼容算 major）
2. 在 `CHANGELOG.md` 加一节
3. `python build.py --install`
4. 提交 `VERSION`、`CHANGELOG.md`、源码与 `dist/`。`dist/doc-driven-development-<版本>.skill` 就是给其他 Agent 的安装包

`dist/doc-driven-development.skill` 是"最新版"的稳定别名，`dist/doc-driven-development-2.0.0.skill` 供锁定版本安装。

## 安装（其他 Agent / 其他机器）

```bash
# 方式一：解压到技能目录
unzip doc-driven-development.skill -d ~/.workbuddy/skills/doc-driven-development

# 方式二：Zip 技能直接投放
# 把 .skill 放到技能市场/上传入口即可
```

安装后先自检：

```bash
python ~/.workbuddy/skills/doc-driven-development/scripts/self_test.py
cat ~/.workbuddy/skills/doc-driven-development/MANIFEST.txt   # 核对版本与哈希
```

## 设计原则

1. **配置先于代码**：层、枚举、段结构、编号规则、路径全在项目内的 `docs/_schema.json`，加一层不用改脚本。
2. **规则必须有码**：每条规则在 `references/check-rules.md` 里有一个码（`E`/`W`/`D`/`S`/`P`），且有断言覆盖。文档写了代码没实现，是这套实践最该避免的失败。
3. **不假装跑过**：找不到目录就 exit 2 并说清楚，绝不返回 `errors=0` 的假通过。
4. **存量债棘轮**：老项目用 `--update-baseline` 当天接入，只许降不许升。
5. **只做形式校验**：语义是否合理靠人。外链失效、锚点交给 lychee；合规追溯交给 StrictDoc / sphinx-needs（见 `references/ecosystem.md`）。
