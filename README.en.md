# doc-driven-development

[中文](./README.md) | **English**

> This is the English translation. The Chinese [README.md](./README.md) is the source of truth; if the two differ, the Chinese version wins. Status words stay in Chinese because the scripts and templates use them.

This is a skill (Agent Skill) for AI coding assistants, intended for people who write code with AI, especially developers with limited experience. It moves development context from the chat window into project documents and makes those documents the project's single source of truth. On that foundation, it promotes AI-heavy collaboration without turning human involvement into a formality: people own goals, value trade-offs, and risk boundaries; the AI defaults to reversible implementation, self-checks, and iteration. Human input should make a real judgment, not approve every step or fill process forms. When feedback is useful, the AI provides either a usable result or observable evidence, whichever fits the situation. Replies should also keep cognitive load low. The workflow follows agile-first: build the minimum useful product and refine it through use; prioritize a complete, working system over piling on features.

## What This Is

When developing with AI, context (what the AI knows about this project: requirements, progress, reasons for decisions, next steps) usually lives only in the chat window and disappears when the window closes.

This skill does three things in order:

1. Lay the foundation — move context from the chat window into project documents and make them the single source of truth: each fact has exactly one definition place, rules carry codes, scripts can check them, and generated sections are rebuilt by scripts, never hand-edited.
2. Classify and organize what comes in: the user's words are filed by type, the AI's reasoning and trade-offs get their own column, the process is compressed into a handoff anchor, and conclusions settle into requirements, decisions, and feature entries.
3. On the foundation, raise the core skeleton — status advances only on evidence, and the five gates have machines check form while humans judge meaning; then run two lines:

   - For the system's design and development process: build the minimum viable system first, then on that working base settle the system's necessary components, keep extending the system, and adjust and optimize its components.
   - For the developer: lower cognitive load — prefer diagrams for explanations, keep text replies short and to the point.

## Who It Is For

People who write code with AI, especially developers with little development experience.

The division of labor is not “the AI does the work and a human signs off every step.” People own the goal, value trade-offs, and risk boundaries; the AI reads project context, advances reversible implementation, checks it, and corrects it. Human judgment is requested only when it can materially affect the goal, acceptable risk, or outcome. For reversible details within agreed constraints, the AI proceeds with a safe, recoverable default.

There is no need to watch the AI step by step or approve each action. When human feedback is useful, the AI provides enough to judge: either a usable result or observable evidence, as appropriate—not necessarily both. This lets developers, especially those with less experience, focus on judging intent and outcomes rather than operating process gates. The action-by-action division is in the "Division of Labor" section of [SKILL.md](SKILL.md).

## What It Solves

AI-assisted development has four collaboration costs; this skill is designed to reduce them:

1. Background retold again and again: every session change, person change, or three-month gap forces a retelling of requirements and progress. The handoff anchor plus the opening brief let the next session read the current state before starting.
2. The reported "done" cannot be trusted: the AI says it is done, but that is not necessarily what you wanted. The deviation is either unverified — done is only claimed; or off-target — the requirement was understood wrong, or one place got fixed while another broke. Two gates stop it: timely feedback, so deviations surface on the spot after every change; and comparison, which before wrap-up checks that what was built is the requirement's sentence. A completion that passes both gates lands in a document record and a commit, so you can look back on it and roll it back.
3. Discovered issues get lost: findings during the process either derail the main thread or disappear silently. The issue inbox lands them immediately without interrupting; closable ones close through a loop, open ones carry a return condition.
4. Daily struggle over what to do first: re-deciding what to do every day, or pushing five things at once. The plan has one exit for the next step; order is computed from scores, never hand-arranged.

## Goal and Approach

The goal is system-level coverage: from any entry point in the system, walk through every path a user can walk. Walked-through means each step's result can be verified, failures can be rolled back, and another person can pick up. Laying down features one by one does not count; the path is what must be verified. Path coverage is the means, not the goal.

The approach in two sentences:

- Agile first: build the minimum viable version first, use it right away, and adjust while using it. Many trade-offs can only be judged after the product is built and used on a real machine. Feedback ranks above implementation: implementation is the means, feedback is the end.
- AI-heavy: the AI defaults to reversible implementation and self-checks; people focus on goals, meaningful trade-offs, material risks, and whether the outcome is acceptable. This shortens the build-and-learn cycle.

Before adding any step, ask whether it supports a real judgment, verification, or rollback. If it only creates paperwork, repeated confirmation, or process completeness, it should not become a human gate. Alignment, review, design, comparison, and assessment remain useful checks, but the AI and machines can perform them continuously; involve a person only where their judgment can change the result. Work hours, Gantt charts, and kanban sync are explicitly not done.

When feedback is needed, provide what fits the decision: a usable result or observable evidence. Usable and observable are alternatives, not a requirement to provide both every time.

The result in one sentence: people spend attention on judgments that matter while AI moves reversible work forward; what is said can be verified, what is verified can be reverted, and what is unfinished has somewhere to stay.

## Four Promises

1. One definition: the same fact appearing in a second place is an error.
2. Traceable: every done item can point to a requirement, a code entry point, an acceptance command, and a commit.
3. Adjustable priority: to see a capability sooner, change the scores or the view weights and rerun `plan.py index` to re-rank.
4. No lost issues: every finding has a landing point; nothing disappears silently.

## Capabilities at a Glance

| Capability | What it does |
|---|---|
| Document skeleton | One command lays down 5 / 8 directory layers, the schema, and the checking scripts |
| Process memory | One dual-sided record per session; the timeline is rebuilt automatically |
| Decision memory | One ADR per decision; rejected options stay, with the signal that would reopen them |
| Requirements & features | Requirements written as verifiable sentences with acceptance commands |
| Plan & ranking | Three levels: direction, work, task; six-dimension scores, multi-view ranking |
| Issue inbox | Discovered issues land first without interrupting the current work |
| Real-machine acceptance | If it is not final, keep it replaceable and open an RV entry |
| Five check dimensions | Alignment, review, design, comparison, assessment; machines check form, humans make judgments that need human intent or trade-offs |
| Observability | Component level leaves a record; system level leaves a trace |
| Self-check & delivery | Five wrap-up checks, full self-test, six-host install |

An ADR is a decision record: one file per decision, why it was made, what other options existed, and under what condition it can be overturned.

## Quick Start

```bash
git clone https://github.com/wbaxm2016/doc-driven-development.git
cd doc-driven-development && python scripts/self_test.py   # about 1–2 minutes, does not touch your project
```

Add it to your project:

```bash
python install.py --list          # see which products on this machine can be installed and where
python install.py --only dsh      # install into DeepSeek Harness; ids are in the output above

cd <your-project-root>
python "$HOME/.dsh/skills/doc-driven-development/scripts/doc_init.py" --target .
python scripts/doc_check.py       # expect errors=0
```

Which host gets installed is declared in [install-targets.json](./install-targets.json); release and rollback are in [CONTRIBUTING.md](./CONTRIBUTING.md); daily commands and templates are in [SKILL.md](./SKILL.md).

## How One Development Cycle Runs

Approval is not judgment: clicking approve only says “let it run,” not “it is right.” The AI should proceed with reversible work by default; people focus on goals, value trade-offs, material risks, and whether the result is acceptable.

| Stage | What humans do | What the Agent does |
|---|---|---|
| Opening | Say what this session should solve | Read the previous handoff, unfinished plan items, and the inbox |
| Current state & direction | Explain what exists, where it is stuck, what is wanted | Ask questions over several rounds, inspect code, write checkable facts |
| Alignment gate | Decide: is the requirement this sentence, is the direction worth walking | Write the requirement or direction |
| Review gate | Confirm: which requirement the feature satisfies, whether it can be built, what it costs | Write the feature or work entry |
| Design gate | Review: interfaces, replaceable points, failure boundaries | Write the design card |
| Tasks & implementation | Decide key trade-offs | Split tasks, change code, run smoke tests, put issues into the inbox |
| Comparison gate | Read behavior: is this the requirement's sentence | Fill the comparison checklist, log differences |
| Assessment gate | Judge: worth it, cost on target | Provide evidence, list open issues |
| Testing & write-back | Confirm the status write-back | Run acceptance commands and the five wrap-up checks |
| Wrap-up | Confirm next steps and open issues | Write the session handoff, rebuild the timeline |

The five gates in one sentence: do not start until the requirement or direction has been restated or adopted by the user; do not enter the plan if a feature cannot answer which requirement it satisfies, whether it can be built, and what it costs; do not split tasks until the design card is settled; do not move to 已对照 (compared) until the comparison is done and differences are logged; do not say 已验收 (accepted) until the assessment's four fields are complete.

Machines check form: structure, references, numbering, status words, entry points exist, acceptance commands actually run. Humans judge meaning: is the clause correct, is the behavior the intended one, should the open issue be closed, is the direction right.

The five wrap-up checks: `devlog check` → `devlog index` → `plan check` → `plan index` → `doc_check`; any one not at `0 error` does not count as wrap-up.

Rollback: to void a requirement, change the document status; to roll back an implementation, use the commit recorded in 完成于 (completed at) with `git revert`. Change documents before code.

Light changes that only touch wording, typos, or formatting need no session record; run only the checks they touch.

## What It Does Not Guarantee

- Completeness depends on discipline, not checks. Scripts can check fields and references, but not whether an issue should be recorded or closed.
- It does not guarantee the Agent will not take wrong actions. Since it does not ask step by step, it may run wrong commands or edit wrong files. The backstop is git: completion anchors can be reverted, acceptance commands can be rerun.
- Criteria wake up only when a date is written. Put `@YYYY-MM-DD` in a return condition; the reminder fires only after the date. Without a date, the script does not guess.
- Observability does not run the project's runtime. The skill provides templates and a reference implementation; the project implements its own records.
- It assumes one person plus one Agent, one session at a time. Two sessions editing the same workspace in parallel will step on each other; there is no concurrency control here.

## Document Map

| To learn | Read |
|---|---|
| Product positioning, goal, and model details | [docs/00-门面/vision.md](./docs/00-门面/vision.md) |
| Daily commands, templates, and wrap-up checks | [SKILL.md](./SKILL.md) |
| This repository's document index | [docs/README.md](./docs/README.md) |
| Contributing, releasing, rolling back | [CONTRIBUTING.md](./CONTRIBUTING.md) |

## License

MIT, see [LICENSE](./LICENSE). Commercial use, modification, and redistribution are allowed; keep the copyright notice.
