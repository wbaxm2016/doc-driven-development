# 可粘进 AGENTS.md / CLAUDE.md 的片段

把下面 8 行粘进项目根的 `AGENTS.md`（或 `CLAUDE.md` / `.cursor/rules`）。目的是让**任何** agent 在开场自动执行「日常三动作」，而不是依赖用户每次提醒。

```markdown
## 文档约定（docs/ 是唯一事实源）

- 每个开发会话开头：先 `python scripts/devlog.py brief` 读现状（上一场交接锚点 / 计划未完成 / 收件箱计数），再 `python scripts/devlog.py new --title "主题" --scope "范围"` 建档，按 `docs/70-过程/会话档案模板.md` 写。
- 过程中发现任何问题（缺陷/口径冲突/文档债/风险/待决/机会）：立刻在 `docs/70-过程/问题收件箱.md` 加一行，然后继续当前话题，**不要停下来问要不要处理**。
- 收尾五条命令，全部 0 error 才算完：`doc_check.py` → `devlog.py check` → `devlog.py index` → `plan.py check` → `plan.py index`。
- 一个事实只有一处：出现两份定义同类内容，删弱的那份或降为 `reference`，不要两边同步维护。
- 过程档案（`status: snapshot` / `authority: 4`）**不是约束**；要成为约束必须回写契约或新开 ADR。
- 状态只被证据推进：`已实现（未验收）` ≠ `已完成`。
- 生成区（时间线、排序视图）不手改，由脚本重建。
- 「下一步做什么」只看 `docs/00-门面/开发计划.md`，别处不写排期。
```

## 为什么要这一段

`SKILL.md` 只在技能被激活时进上下文；而「开场建档、收尾四连跑」这类**习惯**需要在每个会话都生效。写进 `AGENTS.md` 是把它从「需要被想起的技能」变成「默认加载的约束」——这是这套体系能不能活过半年的分水岭。
