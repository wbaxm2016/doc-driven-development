# doc-driven-development

[中文](./README.md) | **English**

> This is the English translation. The Chinese [README.md](./README.md) is the source of truth; if the two differ, the Chinese version wins.
>
> Translation notes: `方向线` direction track · `需求线` requirement track · `五道门` five gates · `走通验收` walkthrough acceptance · `接缝` seams · `问题收件箱` issue inbox. Status words and field names stay in Chinese because the scripts and templates use them.

**The first question in AI-assisted development is not "can the AI write code?" but "where does the context live?"** If it lives only in the agent's window, that is a problem that disappears when the session closes; persist it in documents and it lasts; make documents the single source of truth and it can be handed over; once that foundation is solid, a skill has somewhere to grow capabilities.

## From Agent Context to a Project's Single Source of Truth

Four steps, each harder than the last:

1. **Problem: context lives only in the agent**—close the session, and why, where we are, and what comes next are re-told from memory; another person cannot pick it up, and three months later it cannot be found.
2. **Documents persist it—and classify, organize, condense, and sediment it**—this is not dumping chat logs into docs: your words are filed by type, the Agent's reasoning and trade-offs get their own columns, the process is compressed into a handoff anchor, and conclusions settle into requirements, decisions, and feature rows.
3. **Documents become the single source of truth**—not "one copy in code, one in docs, guess which is newer when they conflict," but one definition per fact: defined once, references checkable, scripts verifiable, generated sections never hand-edited.
4. **Capabilities grow on that foundation**—documentation is no longer overhead outside development but the executable skeleton of the development process itself; the capabilities below all stand on it.

## What It Provides

| Capability | In one line |
|---|---|
| Document skeleton | One command lays down 5 / 8 layers, `_schema.json`, and the checking scripts; directories, enums, and numbering rules are defined once. |
| Process memory | One dual-sided record per session: words filed by type, reasoning and trade-offs in their own columns, the process compressed into a handoff anchor, conclusions settled into requirements, decisions, and feature rows; the timeline is rebuilt automatically. |
| Decision memory | One ADR per decision, with a bidirectional supersede chain and revocation conditions; rejected options stay, with the signal that would bring them back. |
| Requirements & features | Requirements as falsifiable EARS sentences with a `verify:` command; the feature ledger records entry points, evidence, and the completing commit. |
| Plan & ranking | Three levels—direction / work / task—with six-dimension scores and multi-view ranking; one exit for "what next," and the order is computed. |
| Issue inbox | Findings land immediately without interrupting; closable issues close, open ones carry a return condition. |
| Real-machine acceptance | If it is not final, keep it replaceable and open an `RV` entry: three criterion types, an observation-record sub-table, three states and three outcomes; surfaced only when asked. |
| Five gates | Alignment, review, design, comparison, assessment; machines check form, humans judge meaning, irreversible actions are human-decided. |
| Observability | Component level leaves a record, system level leaves a trace; four questions define content, four dimensions define acceptance. |
| Self-check & delivery | Five wrap-up checks, full self-test, six-client install; whatever a script can check is not left to discipline. |

> In one sentence: **what is said can be verified, what is verified can be reverted, and what is unfinished has somewhere to stay.**

## Four Promises

1. **One definition**: the same fact appearing a second time is an error.
2. **Traceable**: every "done" can point to a requirement, a code entry point, an acceptance command, and a commit.
3. **Adjustable priority**: if you want to see a capability first, move it up—change the six-dimension scores or the view weights, rerun `plan.py index`, and the order is recomputed. The order is calculated, not hand-arranged.
4. **No lost issues**: every finding has a landing point; nothing disappears silently.

In exchange, you get four things: no repeated alignment, no doubt about fake completion, no issues lost halfway, and no daily agonizing over what to do first.

## Design Trade-off: Subtract, Aim for System-Level Coverage

Most methodologies expand coverage: more document types, more fields, more ceremony. This one goes the other way—**it does not seek feature coverage; it seeks system-level coverage**: start anywhere in the system, walk one whole path through before starting the next, and every path a user can walk must close; covering features does not count. Before adding a step, answer "how do you tell whether it is true or false, and when can it be removed?" If you cannot answer, do not add it. So there are only five gates, and each gate has either a machine criterion or an explicit human judgment.

Three judgments support this trade-off:

- **Judge truth before talking about completion**: comparison comes before testing. A test only proves "it matches the assertion," not "the assertion is the requirement's sentence." Reverse the order and you will take "all tests green for the wrong direction" as evidence of completion.
- **Completion must be reversible**: the `完成于` (completed at) field records the commit; "done" is a point you can `git revert`. A completion without an anchor can only be restored from memory.
- **Open issues must not be closed**: only closable issues can be closed. Open issues trade "how far this round goes" for "what signal brings us back"—their end state is a judgment, not a closure.

Together this is a closed loop: **what is said can be verified, what is verified can be reverted, and what is unfinished has somewhere to stay**. Remove one and it degrades into a record.

## Dual Tracks: Direction and Requirements

Development moves along two tracks at once: one asks "how does the user get through," the other asks "what must hold." They are not two processes but two facets of the same development, and they converge at **tasks**.

| | Direction track | Requirement track |
|---|---|---|
| Starting point | Multiple rounds of conversation to understand the current state | One sentence that must hold |
| Answers | How users use it, how the system connects | What counts as done |
| Breakdown | Current state (`D`) → `W` → `T` | `REQ` → `F` → `T` |
| Criterion | Success state + walkthrough acceptance | EARS + `verify:` |
| Failure mode | The path is smooth, but every step is unverifiable | Many features, but they do not form a path |
| Role | Accelerator | Brake |

**Direction track**: features are nodes, directions are edges. Build only nodes and the system is a pile of features; build only edges and it is an empty path with no content.

What users actually perceive are **seams**—did the data from the previous step carry over, can a failure be undone, will the state still be there tomorrow, can another person pick it up? Empty states, permissions, timeouts, and retries belong to no single feature; integration bugs also live in the seams. So direction-track work is often not adding features but making A's output a legitimate input for B.

The direction track can start from any feature—it looks at the whole path, not a module; walk one path through, then the next. Path coverage is the means; **system-level coverage is the goal**: the object of coverage is paths, not features—features are only nodes; the path is what must be verified.

This is exactly where AI is most likely to miss the point: it can make a single prompt as good as possible, but it cannot judge which path is worth walking or which experience cannot be compromised. **AI fills in the implementation; humans set the path.**

The direction is written as one row in the direction card ([`docs/00-门面/方向卡.md`](./docs/00-门面/方向卡.md)): nine fields such as current state, success state, path, seams, non-coverage, and walkthrough acceptance. The machine checks whether four fields exist (current state / success state / walkthrough acceptance / seams), whether the walkthrough acceptance has an `@YYYY-MM-DD` review date, and whether references exist (`P18` / REQ-018); **if you cannot write the seams, this direction is still just a collection of features**.

Then comes a loop, not a pipeline:

```
Current state ──► Work ──► Design ──► Tasks ──► Progress
     ▲                                                 │
     └────────────── new current state ◄───────────────┘
```

- **Work `W`**: a slice along the direction that can be accepted independently within 1–3 sessions.
- **Design**: one design card per work—interfaces, replaceable points, extension points, failure boundaries. If the design is not settled, do not split tasks.
- **Task `T`**: the smallest change that can be completed, verified, and assessed in one session.
- **Progress**: implement → compare → assess → test → write back. Finish one, update the current state once.

The **requirement track** is the reverse: it needs one falsifiable sentence. Only when you can write the trigger condition (`WHEN <condition> THE SYSTEM SHALL <behavior>`) and pair it with a runnable command does it count as a requirement.

If you cannot write the `WHEN`, you have not thought it through—open an ADR first; do not blur it into "must be usable" in a contract. `REQ` holds only after the user restates or adopts it; `F` enters the plan only after answering three questions (which requirement it satisfies, whether it can be built, and what it costs).

The two tracks split differently: `W` attaches to `D`, not `REQ`; one `REQ` can span several `W`s. They converge only at **tasks**—each task has exactly one feature and one work, but a feature's tasks can span multiple works. Scoring also lands only on tasks: directions and work do not enter the six-dimension score; which path to take and which to walk first are human decisions.

## How a Development Cycle Runs

The division of labor is fixed: **humans provide facts and judgment; the Agent reads, writes, executes, and verifies.**

**Approval is not judgment.** The Agent's reads, writes, executions, and verifications do not need item-by-item approval—set the approval policy to `从不询问` (never ask) in DSH and it will still finish a round. Clicking "approve" answers only "let it run," not "is it right?" Judgment stays at the gates: is the direction worth walking, is the requirement this sentence, is the behavior correct—humans pass five gates; closing open issues and releasing / rolling back—two irreversible actions—are decided by humans.

| Stage | What humans do | What the Agent does | Where it lands |
|---|---|---|---|
| Opening | Say what this session should solve | `brief` reads the previous handoff, unfinished plan items, and inbox count | This session's scope |
| Current state & direction | Explain what exists, where it is stuck, and what is wanted | Ask questions over multiple rounds, inspect code, write checkable facts | Session §1/§3, direction card |
| Facet (alignment gate) | **Decide**: restate or adopt the requirement; the direction is worth walking | Write `REQ` (EARS + `verify:`) or `D` | `REQ` / `D` |
| Middle layer (review gate) | **Confirm**: the feature answers three questions; the work can be accepted independently | Write `F` (entry point, evidence) or `W` | `F` / `W` |
| Design (design gate) | **Review**: interfaces, replaceable points, failure boundaries | Write the design card; open an ADR for important trade-offs | Design card |
| Tasks & implementation | Decide key trade-offs; no need to watch every step | Split `T`, change code, run smoke tests, put issues into the inbox immediately | `T` + code + `ISS` |
| Comparison (comparison gate) | **Read behavior**: is this the requirement's sentence? | Take the feature row, fill the comparison checklist, log differences as `ISS` | Comparison checklist |
| Assessment (assessment gate) | **Judge**: worth it? cost on target? will it survive the next change? | Provide evidence, list open issues | Task assessment four fields |
| Testing & write-back | Confirm the status write-back | Run `verify` + the five wrap-up checks, write back according to evidence | `0 error` |
| Wrap-up | Confirm next steps, open issues, and current-state changes | Write session §7, update the current state, rebuild the timeline | The next session's starting point |

The five gates in one sentence: do not start until the requirement or direction has been restated or adopted by the user; do not enter the plan if a feature or work cannot answer "which requirement, can it be built, what does it cost"; do not split tasks until the design card is settled; do not move to `已对照` (compared) until the comparison is done and differences are logged; do not say `已验收` (accepted) until the task assessment's four fields are complete.

Review before establishing: before confirming a requirement, adding a direction to the plan, or splitting tasks, write the three review lines in session §3.3 / the direction card / the design card (upstream quote verbatim / what already exists / where it conflicts, or why this is more reasonable); after the user decides, add one line to the decision block on why it is more reasonable.

The machine checks form: structure, references, numbering, status words, entry points exist, `verify` actually runs, the design card exists. Humans judge meaning: is the clause correct, is the behavior the intended one, should the open issue be closed, is the direction right, will the design survive replacement.

Assessment is not the end; there are three exits: move on if no task is needed; return to "tasks & implementation" if a task is needed; return to "design" if the design must change, and mark the old task `搁置` (shelved) or `撤回` (withdrawn)—do not push on with the old design.

Outside the main line, two places must be decided by humans:

| Checkpoint | Where | What happens without a decision |
|---|---|---|
| Closing open issues | During review, before wrap-up | Issues are silently closed, or left hanging forever |
| Release / rollback | Outside the main line | An irreversible release accident |

**The five wrap-up checks**: `devlog check` → `devlog index` → `plan check` → `plan index` → `doc_check`; any one not at `0 error` does not count as wrap-up. `verify` is too slow; put it in CI.

**Overturning and rollback**: to void a requirement, use `REMOVED` in `_delta` (numbers are not reused); to withdraw a feature, change its status and write the reason; to roll back an implementation, use the commit in `完成于` and `git revert`. **Change documents before code**, otherwise you get "code reverted, requirement still says implemented."

**Scale by change size**: light-touch changes that only adjust wording, typos, formatting, or comments do not need a session record or the five wrap-up checks; run only the checks they touch. The same applies to design cards—small changes get three lines.

## Visibility: Component-Level and System-Level Observability

The closed loop governs "what is recorded is correct"; observability governs "what actually happened." Two layers:

- **Component level**: when a command, a gate, or a script finishes, it leaves a record—what ran, which rule produced the result, and where the failure landed.
- **System level**: string them together (the five wrap-up checks, session record → check → write-back, release → install, gate chain) and leave a trace—did the previous step's output become the next step's input, and where did it break?

Every record answers four questions: **what ran · why this result · what was expected · what is the system's next step**. The four questions are the record's content; the four dimensions are the acceptance frame: **observable** (did it run, what ran), **explainable** (why this result), **diagnosable** (where is the problem, what next), **improvable** (does the same problem recur, how should the rule change). The first three can be answered by a single record; improvable requires cross-run aggregation.

The skill gives projects three anchors; it does not run the project's runtime:

| Carrier | What it is | Machine criterion |
|---|---|---|
| Observability map | `doc_init` lays down `40-运行/可观测性.md`: component list, four questions per component, signals and windows, system-level wiring | Usable once laid down |
| Design card "observability four fields" | Observed object / questions to answer / signals / window | `W12` reminder (non-blocking; no retroactive checks) |
| Its own reference implementation | `observe.py run / five-run / show / status / trend` | Assertion groups 63 / 64; write failures degrade only, never change the main command's exit code |

`observe trend` aggregates across runs by "code + target file": how many times the same issue appeared, when it started, and whether it changed across versions. Observability is a side channel—a failed write does not block the main command, nor does it write back to ledger status.

## What It Does Not Guarantee

The closed loop says "what is recorded is correct," not "everything that should be recorded is recorded."

- **Completeness depends on discipline, not checks**. Scripts can judge fields, numbers, references, and status words, but not whether an issue should be recorded or closed.
- **It does not guarantee the Agent will not take wrong actions**. If it does not ask item by item, it will run wrong commands and edit wrong files. The backstop is git and evidence—a completion anchor can be reverted with `git revert`, `verify` can be rerun, and before committing, `add` only your own paths; approval popups stop actions, not wrong thinking.
- **Criteria wake up only when a date is written**. Put `@YYYY-MM-DD` in a revocation condition, return condition, or walkthrough acceptance; after the date, `brief` lists it on its own line. For those without a date, the script does not guess—guessing wrong creates noise.
- **Observability does not run the project's runtime**. The skill provides templates, four fields, and a `W12` reminder; projects implement their own runtime from the template. Missing records report an evidence gap only; they do not block the main command.
- **It assumes one person + one Agent, one session at a time**. Two sessions editing the same workspace will step on each other: checks may briefly go red, numbers may collide—there is no concurrency control here.

## Quick Start

```bash
git clone https://github.com/wbaxm2016/doc-driven-development.git
cd doc-driven-development && python scripts/self_test.py   # about 1–2 minutes; runs in a temp dir, does not touch your project
```

Add it to your project:

```bash
python install.py --list          # see which products on this machine can be installed and where
python install.py --only dsh      # install into DeepSeek Harness; ids are in the output above

cd <your-project-root>
python "$HOME/.dsh/skills/doc-driven-development/scripts/doc_init.py" --target .
python scripts/doc_check.py       # expect errors=0
```

Which host gets installed is declared in [`install-targets.json`](./install-targets.json) (`install.py --list` reads it and prints each host's target directory); release and rollback are in [CONTRIBUTING.md](./CONTRIBUTING.md); daily commands, templates, and wrap-up checks are in [SKILL.md](./SKILL.md).

## Document Map

| To learn | Read |
|---|---|
| Product positioning and model (three layers + three networks + four issue dimensions) | [docs/00-门面/vision.md](./docs/00-门面/vision.md) |
| How components and the system are observed (four questions / four dimensions) | The `可观测性` (Observability) section of [SKILL.md](./SKILL.md) |
| This repository's document index | [docs/README.md](./docs/README.md) |
| The skill body read by the Agent | [SKILL.md](./SKILL.md) |
| Contributing, releasing, rolling back | [CONTRIBUTING.md](./CONTRIBUTING.md) |

## License

MIT, see [LICENSE](./LICENSE). Commercial use, modification, and redistribution are allowed; keep the copyright notice.
