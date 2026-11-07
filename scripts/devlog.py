#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""过程档案工具：建档 / 校验 / 时间线。

用法：
    python scripts/devlog.py new --title "主题" [--date 2026-10-29] [--scope 范围]
    python scripts/devlog.py brief [--json]        # 开场先读：上一场锚点/计划未完成/收件箱/待分诊
    python scripts/devlog.py ask "问题" [--if "前提"]   # 记一条要用户定的问题（不占 ISS 号）
    python scripts/devlog.py pending [--clear Q1 --as iss|s5|drop|defer --relation … --type … --impact … --to …]
    python scripts/devlog.py inbox [--similar "一段文字" --top 3]
    python scripts/devlog.py check [--json]
    python scripts/devlog.py index [--check]

路径与段结构全部来自 <docs>/_schema.json，不硬编码目录名。
找不到文档目录或过程层时**直接失败**（不再返回 errors=0 的假通过）。
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

DEFAULT_SCHEMA = {
    "layers": {"00-门面": "facade", "10-架构": "architecture", "20-契约": "contract",
               "30-决策": "decision", "40-运行": "operation", "50-术语": "glossary",
               "60-规范": "norm", "70-过程": "process"},
    "session_sections": ["本次范围", "用户侧记录", "AI 侧记录",
                         "决策与选项对比", "开放项", "本次产出", "交接"],
    "names": {"plan": "开发计划.md", "inbox": "问题收件箱.md",
              "timeline": "时间线.md",
              "session_template": "会话档案模板.md", "sessions_dir": "会话"},
    "ids": {"issue": "ISS", "digits": 3},
    "plan": {"done_states": ["已完成"], "task_pattern": r"^T\d+\.\d+\.\d+$"},
}

BEGIN = "<!-- BEGIN:devlog-index -->"
END = "<!-- END:devlog-index -->"


def die(msg, as_json=False, code=2):
    if as_json:
        print(json.dumps({"ok": False, "fatal": msg}, ensure_ascii=False))
    else:
        print(f"ERROR {msg}")
    return code


def read(path):
    # utf-8-sig：带 BOM 的档案/模板不该被当成「缺 front-matter」。
    with open(path, encoding="utf-8-sig") as fh:
        return fh.read()


def write(path, text):
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def cell(s):
    """表格单元格：竖线转义、换行压平。

    标题里出现一个 `|`，就会把整行时间线撑成多一列（实测列数 9 vs 8）。
    """
    return str(s).replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def requote_fm(text, keys=("title", "scope", "summary")):
    """把 front-matter 里带用户文本的行重写成 JSON 字符串字面量。

    模板是 `title: "{{TITLE}}"`，标题原样塞进去时，标题里的 `"` 或 `\\` 会让
    PyYAML 直接 ParserError，而脚本自己的正则校验照样报 0 error——坏文件被当成好文件。
    """
    lines = text.splitlines(True)
    if not lines or lines[0].strip() != "---":
        return text
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return text
    for i in range(1, end):
        m = re.match(r"^(%s):\s*(.*?)\s*$" % "|".join(keys), lines[i].rstrip("\r\n"))
        if not m:
            continue
        val = m.group(2)
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "'\"":
            val = val[1:-1]
        lines[i] = "%s: %s\n" % (m.group(1), json.dumps(val, ensure_ascii=False))
    return "".join(lines)


def parse_fm(text):
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end < 0:
        return {}
    data = {}
    for line in text[3:end].splitlines():
        m = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", line)
        if m:
            val = m.group(2).strip()
            if len(val) >= 2 and val[0] == val[-1] and val[0] in "'\"":
                q, val = val[0], val[1:-1]
                if q == '"':
                    # 与 doc_check 同一条规则：双引号块按 JSON 字符串还原转义。
                    try:
                        val = json.loads('"' + val + '"')
                    except ValueError:
                        pass
            data[m.group(1)] = val
    return data


def strip_md(s):
    return re.sub(r"[*`]", "", s).strip()


def h1_of(text):
    """正文 H1：先跳过 front-matter 块，再找第一个 `# ` 行。

    front-matter 里允许出现 `# 注释`（模板的成本自报说明就是）。旧实现取全文
    第一个 `# ` 行，会把注释当成 H1，S2 就报「title 与 H1 不一致」——新档一建
    就假红，每场都要人工消错（ISS-094）。`doc_check` 的 E4 走的是已剥离头块的
    body，没有这个问题；这里补上同样的口径。
    """
    start = 0
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end >= 0:
            start = end + 4          # 跳过 `\n---`；没闭合就退回整篇扫，不静默返回空
    for line in text[start:].splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return ""


def split_row(s):
    """按未转义的 `|` 切单元格，并把 `\\|` 还原成 `|`。

    收件箱里真的有「标题含竖线」这类条目（ISS-011）：写的时候 `cell()` 转义了，
    读的时候再按裸 `|` 切，整行会多出一列并被静默跳过——S5 就会误报「ISS 不存在」。
    """
    return [c.strip().replace("\\|", "|") for c in re.split(r"(?<!\\)\|", s)]


def read_tables(text):
    tables, block = [], []
    for line in text.splitlines() + [""]:
        s = line.strip()
        if s.startswith("|") and s.endswith("|") and len(s) > 2:
            block.append(split_row(s[1:-1]))
        else:
            if len(block) >= 2:
                header, rows = block[0], block[1:]
                rows = [r for r in rows
                        if not all(re.fullmatch(r":?-{2,}:?", c or "-") for c in r)]
                tables.append((header, rows))
            block = []
    return tables


def layer_dir(schema, name):
    for d, v in schema["layers"].items():
        if v == name:
            return d
    return None


# ---------------------------------------------------------------- 定位
def find_docs(arg):
    """找文档目录：显式 --docs → **当前工作目录** → 脚本所在仓库。

    cwd 必须排在脚本目录之前：用开发副本的脚本去别的项目跑时，读写的必须是
    那个项目的 docs；排在后面就会静默串档（ISS-028，实测把探针写进本仓库）。
    """
    if arg:
        return arg if os.path.isdir(arg) else None
    here = os.path.dirname(os.path.abspath(__file__))
    found = []
    for root in (os.getcwd(), os.path.dirname(here)):
        for name in ("docs", "文档", "documentation"):
            p = os.path.join(root, name)
            if os.path.isdir(p):
                found.append(p)
                break
    if len({os.path.abspath(p) for p in found}) > 1:
        print(f"WARN 同时存在两个文档目录，用当前目录的 {found[0]}（忽略 {found[1]}）",
              file=sys.stderr)
    return found[0] if found else None


class SchemaError(Exception):
    """配置文件存在但读不出来——报清楚该查哪个文件，不抛回溯。"""


def load_schema(docs):
    for name in ("_schema.json", "_layers.json"):
        p = os.path.join(docs, name)
        if os.path.exists(p):
            try:
                raw = json.loads(read(p))
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise SchemaError(
                    f"{p} 解析失败：{exc}。这个文件是层/枚举/段结构的唯一来源，"
                    f"要么修好它，要么删掉回退内置默认")
            if not isinstance(raw, dict):
                raise SchemaError(f"{p} 顶层不是对象（应为 {{\"layers\": {{...}}}}）")
            merged = json.loads(json.dumps(DEFAULT_SCHEMA))
            for k, v in raw.items():
                if isinstance(v, dict) and isinstance(merged.get(k), dict):
                    merged[k].update(v)
                else:
                    merged[k] = v
            return merged
    return json.loads(json.dumps(DEFAULT_SCHEMA))


class Ctx:
    def __init__(self, docs, schema):
        pdir = layer_dir(schema, "process") or ""
        fdir = layer_dir(schema, "facade") or ""
        self.docs = docs
        self.root = os.path.dirname(os.path.abspath(docs))
        self.pdir = os.path.join(docs, pdir)
        n = schema["names"]
        self.sess = os.path.join(self.pdir, n["sessions_dir"])
        self.inbox = os.path.join(self.pdir, n["inbox"])
        self.timeline = os.path.join(self.pdir, n["timeline"])
        self.template = os.path.join(self.pdir, n["session_template"])
        self.plan = os.path.join(docs, fdir, n.get("plan", "开发计划.md"))
        self.schema = schema

    def sessions(self):
        if not os.path.isdir(self.sess):
            return []
        return sorted(os.path.join(self.sess, f)
                      for f in os.listdir(self.sess) if f.endswith(".md"))


def plan_tasks(ctx):
    """读开发计划 §5 的任务表 → (全部编号, 未完成编号, 表是否可读)。

    交接锚点的「互校」只判编号存在性，不判状态：历史档案的「下一步」指向的任务
    后来完成了，档案仍是对的（它记录的是当时）。「无」才是唯一需要状态的出口。
    """
    ids, pending = set(), set()
    if not os.path.exists(ctx.plan):
        return ids, pending, False
    done = set(ctx.schema["plan"]["done_states"])
    for header, rows in read_tables(read(ctx.plan)):
        heads = [strip_md(h) for h in header]
        if not heads or heads[0] != "ID" or "任务" not in heads:
            continue
        i_state = heads.index("状态") if "状态" in heads else None
        for r in rows:
            if len(r) != len(heads):
                continue
            tid = strip_md(r[0])
            ids.add(tid)
            if i_state is not None:
                status = strip_md(r[i_state])
                if status not in done:
                    pending.add(tid)
        return ids, pending, True
    return ids, pending, False


# ---------------------------------------------------------------- 待分诊
def pending_dir(ctx):
    """待分诊文件住仓库根的 .dd/pending/：不进 docs/（躲开 doc_check 的形状检查），
    也不进 git（临时问题不该进历史），但关掉会话仍留在盘上。"""
    return os.path.join(ctx.root, ".dd", "pending")


def pending_files(ctx):
    d = pending_dir(ctx)
    if not os.path.isdir(d):
        return []
    return sorted(os.path.join(d, f) for f in os.listdir(d) if f.endswith(".md"))


def _col(heads, *names):
    for i, h in enumerate(heads):
        if any(h == n or h.startswith(n) for n in names):
            return i
    return None


def pending_rows(ctx):
    """读所有待分诊文件 → [{file,id,question,premise,state,note}]。"""
    rows = []
    for path in pending_files(ctx):
        for header, trows in read_tables(read(path)):
            heads = [strip_md(h) for h in header]
            if "id" not in heads or "问题" not in heads or "状态" not in heads:
                continue
            i_id, i_q, i_st = heads.index("id"), heads.index("问题"), heads.index("状态")
            i_pre, i_note = _col(heads, "前提"), _col(heads, "处置")
            for r in trows:
                if len(r) != len(heads):
                    continue
                qid = strip_md(r[i_id])
                if not re.fullmatch(r"Q\d+", qid):
                    continue
                rows.append({
                    "file": path,
                    "id": qid,
                    "question": strip_md(r[i_q]),
                    "premise": strip_md(r[i_pre]) if i_pre is not None else "",
                    "state": strip_md(r[i_st]),
                    "note": strip_md(r[i_note]) if i_note is not None else "",
                })
    return rows


def pending_gate(ctx):
    """开工门禁：还有 open 项、或延期超过 5 条，就不许开新会话建档。

    它挡的不是「没写」，而是「写了没人清」——只要问题记下来，下一次开场一定被摆到眼前。
    """
    rows = pending_rows(ctx)
    opened = [r for r in rows if r["state"] == "open"]
    deferred = [r for r in rows if r["state"] == "deferred"]
    errs = []
    if opened:
        errs.append("仍有 %d 条待分诊：" % len(opened))
        for r in opened[:8]:
            errs.append("  %s  %s（%s）" % (r["id"], r["question"],
                                            os.path.basename(r["file"])))
        errs.append("先 `devlog.py pending` 看全量，再 "
                    "`pending --clear <id> --as iss|s5|drop|defer` 分诊")
    if len(deferred) > 5:
        errs.append("延期项 %d 条（上限 5）：先排优先级，别拿延期绕开门禁" % len(deferred))
    return errs


def split_row(s):
    """按未转义的竖线切一行表格；`\\|` 还原成 `|`（ISS-070，与 doc_check 同口径）。"""
    s = s.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|") and not s.endswith("\\|"):
        s = s[:-1]
    cells, cur, i = [], "", 0
    while i < len(s):
        if s[i] == "\\" and i + 1 < len(s) and s[i + 1] == "|":
            cur += "|"
            i += 2
            continue
        if s[i] == "|":
            cells.append(cur.strip())
            cur = ""
            i += 1
            continue
        cur += s[i]
        i += 1
    cells.append(cur.strip())
    return cells


def set_pending_state(path, qid, state, note):
    out = []
    for ln in read(path).splitlines(True):
        s = ln.strip()
        if s.startswith("|") and s.endswith("|") and s.count("|") >= 5:
            parts = split_row(s)
            if parts[0].strip().strip("*` ") == qid:
                parts[-2] = " %s " % state
                parts[-1] = " %s " % cell(note)
                out.append("|" + "|".join(parts) + "|\n")
                continue
        out.append(ln)
    write(path, "".join(out))


# ---------------------------------------------------------------- 收件箱（查重 / 转正）
ISSUE_ACTIVE = ("确立", "实施中")
ISSUE_TERMINAL = ("实现关闭", "拒绝")
ISSUE_ALIASES = {"open": "确立", "deferred": "确立", "done": "实现关闭"}


def issue_cfg(ctx):
    return ctx.schema.get("issue", {})


def normalize_issue_state(ctx, raw):
    """旧值一次归一：open/deferred → 确立，done → 实现关闭。"""
    s = strip_md(raw or "")
    return issue_cfg(ctx).get("state_aliases", ISSUE_ALIASES).get(s, s)


def inbox_entries(ctx):
    """收件箱三张表的条目：主表 / 已闭环 / 已拒绝。

    统一成 {id,state,nature,type,question,impact,to,back,evidence,updated,table}。
    旧值在这一层归一，后面的命令只认新状态。
    """
    out = []
    if not os.path.exists(ctx.inbox):
        return out
    prefix = re.escape(ctx.schema["ids"]["issue"])
    id_re = re.compile(rf"{prefix}-\d+")
    for header, rows in read_tables(read(ctx.inbox)):
        heads = [strip_md(h) for h in header]
        if "ID" not in heads:
            continue
        i_id = heads.index("ID")
        i_q, i_conc, i_reason = _col(heads, "问题"), _col(heads, "结论"), _col(heads, "理由")
        if i_q is None and i_conc is None and i_reason is None:
            continue
        i_st, i_type = _col(heads, "状态"), _col(heads, "类型")
        i_nat, i_imp, i_to = _col(heads, "性质"), _col(heads, "影响"), _col(heads, "落点")
        i_back, i_ev = _col(heads, "回到条件"), _col(heads, "依据", "证据")
        i_up = _col(heads, "更新")
        i_dec = _col(heads, "决策人")
        i_date = _col(heads, "闭环日", "拒绝日", "发现日")
        i_reopen = _col(heads, "重新考虑条件")
        # 表类型：有状态=主表；有结论=已闭环；有理由=已拒绝。
        if i_st is not None:
            table = "main"
        elif i_conc is not None:
            table = "closed"
        else:
            table = "rejected"
        for r in rows:
            if len(r) != len(heads):
                continue
            iid = strip_md(r[i_id])
            if not id_re.fullmatch(iid):
                continue
            if table == "main":
                state = normalize_issue_state(ctx, r[i_st]) or "确立"
                question = r[i_q] if i_q is not None else ""
            elif table == "closed":
                state, question = "实现关闭", r[i_conc]
            else:
                state, question = "拒绝", r[i_reason]
            out.append({
                "id": iid,
                "state": state,
                "nature": strip_md(r[i_nat]) if i_nat is not None else "",
                "type": strip_md(r[i_type]) if i_type is not None else "",
                "question": strip_md(question),
                "impact": strip_md(r[i_imp]) if i_imp is not None else "",
                "to": strip_md(r[i_to]) if i_to is not None else "",
                "back": strip_md(r[i_back]) if i_back is not None else "",
                "evidence": strip_md(r[i_ev]) if i_ev is not None else "",
                "updated": strip_md(r[i_up]) if i_up is not None else "",
                "decider": strip_md(r[i_dec]) if i_dec is not None else "",
                "date": strip_md(r[i_date]) if i_date is not None else "",
                "reopen": strip_md(r[i_reopen]) if i_reopen is not None else "",
                "table": table,
            })
    return out


def _shingles(text, n=2):
    s = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "", text or "")
    if len(s) < n:
        return {s} if s else set()
    return {s[i:i + n] for i in range(len(s) - n + 1)}


def similar_issues(ctx, text, top=3, floor=0.10):
    """按字符二元组重合度找近似条目——只给**候选**，是不是包含/扩展仍要人判。"""
    scored = []
    for e in inbox_entries(ctx):
        if e["state"] not in ISSUE_ACTIVE:
            continue
        a, b = _shingles(text), _shingles(e["question"] + " " + e["impact"])
        score = len(a & b) / max(1, len(a | b))
        if score >= floor:
            scored.append((score, e))
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[:top]


def next_issue_id(ctx):
    nums = []
    prefix = re.escape(ctx.schema["ids"]["issue"])
    for e in inbox_entries(ctx):
        m = re.fullmatch(rf"{prefix}-(\d+)", e["id"])
        if m:
            nums.append(int(m.group(1)))
    return "%s-%03d" % (ctx.schema["ids"]["issue"], (max(nums) + 1) if nums else 1)


def append_inbox_row(ctx, iid, kind, question, impact, to, nature="可关闭",
                     evidence=None, back="—"):
    """只**追加**一行到收件箱主表末尾：按表头写，不假设列顺序。"""
    text = read(ctx.inbox)
    lines = text.splitlines(True)
    head, heads = None, None
    for i, ln in enumerate(lines):
        if not ln.strip().startswith("|"):
            continue
        cells = split_row(ln)
        if cells and cells[0] == "ID" and "状态" in cells and "问题" in cells:
            head, heads = i, cells
            break
    if head is None:
        raise ValueError("收件箱里找不到「ID | … | 状态 | … | 问题 |」的主表")
    end = head + 1
    while end < len(lines) and lines[end].strip().startswith("|"):
        end += 1
    today = datetime.date.today().isoformat()
    values = {
        "ID": f"**{iid}**", "发现日": today, "来源": "分诊转正",
        "类型": kind, "性质": nature, "问题": question, "影响": impact,
        "状态": "确立", "依据": evidence or "确立：分诊转正",
        "落点": to, "回到条件": back, "更新": today,
    }
    def value_for(head):
        # 与 _col() 同一条匹配规则：精确优先，否则「表头 startswith 候选名」。
        # ISS-060：表头是「影响（不处理会怎样）」，精确 key「影响」取不到，曾写成「—」。
        if head in values:
            return values[head]
        for k, v in values.items():
            if head.startswith(k):
                return v
        return "—"

    row = "| " + " | ".join(cell(value_for(h)) for h in heads) + " |\n"
    lines.insert(end, row)
    write(ctx.inbox, "".join(lines))


def cmd_inbox(ctx, args):
    if not args.similar:
        entries = inbox_entries(ctx)
        counts = {}
        for e in entries:
            counts[e["state"]] = counts.get(e["state"], 0) + 1
        print("收件箱：确立 %d · 实施中 %d · 实现关闭 %d · 拒绝 %d"
              % (counts.get("确立", 0), counts.get("实施中", 0),
                 counts.get("实现关闭", 0), counts.get("拒绝", 0)))
        for e in entries:
            if e["state"] in ISSUE_ACTIVE:
                print("  %s  [%s/%s]  %s"
                      % (e["id"], e["state"], e["nature"] or "?", e["question"]))
        return 0
    hits = similar_issues(ctx, args.similar, top=args.top)
    if not hits:
        print("没有相近的开放条目（相似度下限 0.10）——可能是独立的新问题")
        return 0
    print("可能相关的开放条目（字面重合度，仅供人判包含 / 扩展 / 独立）：")
    for score, e in hits:
        print("  %s  %.2f  [%s]  %s" % (e["id"], score, e["state"], e["question"]))
    return 0


# ---------------------------------------------------------------- 功能台账（读）
def features_path(ctx):
    d = layer_dir(ctx.schema, "operation")
    if not d:
        return None
    p = os.path.join(ctx.docs, d, "FEATURES.md")
    return p if os.path.exists(p) else None


def feature_rows(ctx):
    """功能台账的行（id / 功能 / 需求 / 状态 / 入口）。只读，不判合规——那有 E24。"""
    path = features_path(ctx)
    if not path:
        return []
    out = []
    for header, rows in read_tables(read(path)):
        heads = [strip_md(h) for h in header]
        if not {"ID", "功能", "状态"} <= set(heads):
            continue
        i_id, i_fn, i_req = heads.index("ID"), heads.index("功能"), _col(heads, "满足的需求")
        i_st, i_to = heads.index("状态"), _col(heads, "代码入口")
        for r in rows:
            if len(r) != len(heads):
                continue
            fid = strip_md(r[i_id])
            if not re.fullmatch(r"F-\d+", fid):
                continue
            out.append({
                "id": fid,
                "feature": strip_md(r[i_fn]),
                "req": strip_md(r[i_req]) if i_req is not None else "",
                "state": strip_md(r[i_st]),
                "to": strip_md(r[i_to]) if i_to is not None else "",
            })
    return out


def cmd_features(ctx, args):
    rows = feature_rows(ctx)
    if not rows:
        print("没有功能台账（%s）。先跑 doc_init.py，或按模板建 40-运行/FEATURES.md"
              % (features_path(ctx) or "未找到"))
        return 0
    want = (args.state or "").strip()
    picked = [r for r in rows if not want or r["state"] == want]
    if not picked:
        print("功能台账 %d 行，没有状态为「%s」的行" % (len(rows), want))
        return 0
    if want:
        print("功能台账：状态「%s」%d 行" % (want, len(picked)))
    else:
        counts = {}
        for r in rows:
            counts[r["state"]] = counts.get(r["state"], 0) + 1
        print("功能台账：%d 行（%s）"
              % (len(rows), " · ".join("%s %d" % (k, v) for k, v in counts.items())))
    for r in picked:
        print("  %s  [%s]  %s%s" % (r["id"], r["state"], r["feature"],
                                    ("  ← " + r["req"]) if r["req"] else ""))
    if want in ("实施中", "已对照"):
        print("对照清单：40-运行/功能对照.md（四列：功能 / 该验什么 / 结论 / 差异 · 证据）")
    return 0


def cmd_ask(ctx, args):
    """记一条「要用户定」的问题：不占 ISS 号（所以门槛低），但不等于不进历史。"""
    files = ctx.sessions()
    if not files:
        return die("先跑 devlog.py new 建档，再记待分诊问题")
    stem = os.path.splitext(os.path.basename(files[-1]))[0]
    d = pending_dir(ctx)
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, stem + ".md")
    if not os.path.exists(path):
        write(path, "# 待分诊（会话 %s）\n\n"
                    "| id | 提出 | 问题 | 前提（什么变了就作废） | 状态 | 处置 |\n"
                    "|---|---|---|---|---|---|\n" % stem)
    text = read(path)
    nums = [int(m.group(1)) for m in re.finditer(r"\|\s*Q(\d+)\s*\|", text)]
    qid = "Q%d" % (nums[-1] + 1 if nums else 1)
    premise = (args.premise or "").strip()
    row = "| %s | %s | %s | %s | open | — |\n" % (
        qid, datetime.datetime.now().strftime("%H:%M"),
        cell(args.question), cell(premise or "未写"))
    if not text.endswith("\n"):
        text += "\n"
    write(path, text + row)
    print("added: %s -> %s" % (qid, path))
    if not premise:
        print("WARN  没写前提：`--as defer` 时会被拒（说不出什么变了它就作废，通常不是待决项）")
    print("收尾前用 `devlog.py pending --clear` 分诊；未清项会挡住下一场的 `devlog.py new`")
    return 0


def cmd_pending(ctx, args):
    rows = pending_rows(ctx)
    if args.clear:
        # 编号在同一会话文件内唯一，跨会话会重号（Q1 各有一份）；只认还 open 的那条，
        # 已分诊的历史行不参与匹配——否则上一场留下的 Q1 会把这一场的 Q1 顶掉。
        target = next((r for r in rows
                       if r["id"] == args.clear and r["state"] == "open"), None)
        if target is None:
            seen = [r["state"] for r in rows if r["id"] == args.clear]
            if seen:
                return die("%s 已经分诊过：%s" % (args.clear, "、".join(seen)))
            return die("找不到 %s（`devlog.py pending` 看现有条目）" % args.clear)
        kind = args.export
        if kind is None:
            return die("--clear 需要同时给 --as iss|s5|drop|defer")
        note = (args.note or "").strip()
        if kind == "iss":
            # 新增 ISS 前必须先核对已有条目：包含 / 扩展 / 独立，由人决定（ISS-031）。
            # 脚本只给字面候选，判断与取舍不代劳。
            if not args.relation:
                hits = similar_issues(ctx, target["question"] + " " + target["premise"])
                print("新增 ISS 前先核对已有条目：包含 / 扩展 / 独立，由人决定。")
                if hits:
                    print("  候选（字面重合度，仅供人判）：")
                    for score, e in hits:
                        print("    %s  %.2f  [%s]  %s" % (e["id"], score, e["state"], e["question"]))
                else:
                    print("  候选：无（相似度 ≥0.10 的开放条目）")
                if note and re.fullmatch(r"ISS-\d+", note):
                    print("  提示：已有编号 %s 时用 `--relation merge:%s`（或 extends/updates/duplicate）" % (note, note))
                return die("缺 --relation：new | merge:ISS-nnn | extends:ISS-nnn | updates:ISS-nnn | duplicate:ISS-nnn")
            m = re.fullmatch(r"(new|merge|extends|updates|duplicate)(?::(ISS-\d+))?", args.relation.strip())
            if not m:
                return die("--relation 只接受 new | merge:ISS-nnn | extends:ISS-nnn | updates:ISS-nnn | duplicate:ISS-nnn")
            how, ref = m.group(1), m.group(2)
            if how == "new":
                missing = [k for k in ("type", "impact", "to") if not getattr(args, k)]
                if missing:
                    return die("--relation new 需要收件箱行的三格人判字段：缺 "
                               + "、".join("--" + k for k in missing))
                iid = next_issue_id(ctx)
                nature = args.nature or ("开放" if args.type in ("机会", "待决") else "可关闭")
                append_inbox_row(ctx, iid, args.type, target["question"],
                                 args.impact, args.to, nature=nature,
                                 back=(target["premise"] or "—"))
                print("新增 %s（独立，性质 %s%s）"
                      % (iid, nature, "" if args.nature else "，按类型推断"))
                state, note = "→" + iid, note or ("新登记 " + iid)
            else:
                if not ref:
                    return die("--relation %s 需要写成 %s:ISS-nnn" % (how, how))
                ids = {e["id"] for e in inbox_entries(ctx)}
                if ref not in ids:
                    return die("收件箱里没有 %s" % ref)
                label = {"merge": "合并入", "extends": "扩展", "updates": "更新",
                         "duplicate": "重复于"}[how]
                state, note = "→%s %s" % (label, ref), note or label
                print("%s -> %s %s；脚本不改别人的行，请把内容并进 %s 后自行确认"
                      % (args.clear, label, ref, ref))
        elif kind == "s5":
            state, note = "→§5", note or "转开放项"
        elif kind == "drop":
            if not note:
                return die("--as drop 需要 --note 写清为什么丢弃")
            state = "dropped"
        else:
            if target["premise"] in ("", "未写"):
                return die("--as defer 需要该条先有前提（重新 ask 时加 --if \"…\"）")
            state, note = "deferred", note or "延期"
        set_pending_state(target["file"], args.clear, state, note)
        print("%s -> %s（%s）" % (args.clear, state, note))
        print("剩余待分诊：%d" % len([r for r in pending_rows(ctx) if r["state"] == "open"]))
        return 0

    opened = [r for r in rows if r["state"] == "open"]
    deferred = [r for r in rows if r["state"] == "deferred"]
    print("待分诊：open %d · deferred %d" % (len(opened), len(deferred)))
    for r in opened + deferred:
        extra = "" if r["premise"] in ("", "未写") else "（前提：%s）" % r["premise"]
        print("  %s  [%s]  %s  %s" % (r["id"], r["state"], r["question"], extra))
    if not opened and not deferred:
        print("  无（可以开工）")
    return 0


# ---------------------------------------------------------------- new
def cmd_new(ctx, args):
    blocked = pending_gate(ctx)
    if blocked:
        print("ERROR 待分诊没清完，先分诊再开工：")
        for line in blocked:
            print("  " + line)
        return 1
    date = args.date or datetime.date.today().isoformat()
    if not re.fullmatch(r"20\d{2}-\d{2}-\d{2}", date):
        return die(f"--date 格式应为 YYYY-MM-DD：{date}")
    seqs = []
    for f in ctx.sessions():
        m = re.match(rf"{re.escape(date)}-(\d{{3}})-", os.path.basename(f))
        if m:
            seqs.append(int(m.group(1)))
    no = f"{max(seqs) + 1:03d}" if seqs else "001"
    title = f"{date} · {no} · {args.title}"
    safe = re.sub(r'[<>:"/\\|?*\s]+', "-", args.title).strip("-")
    fname = f"{date}-{no}-{safe}.md"
    target = os.path.join(ctx.sess, fname)
    if os.path.exists(target):
        return die(f"已存在：{target}")
    if not os.path.exists(ctx.template):
        return die(f"缺少模板：{ctx.template}（先跑 doc_init.py）")
    text = read(ctx.template)
    for k, v in {"{{TITLE}}": title, "{{DATE}}": date, "{{NO}}": no,
                 "{{SCOPE}}": args.scope, "{{SLUG}}": args.title}.items():
        text = text.replace(k, v)
    # 先给标题/范围/摘要补上转义：模板里这三处都包在双引号中，用户文本原样落进去，
    # 一个 `"` 或行尾的 `\` 就是坏 YAML（`--title '他说"这样"行不行'` 实测 ParserError）。
    text = requote_fm(text)
    # 兜底：doc_init 铺骨架时已经把模板里的 {{DATE}} 换成了当天日期，
    # 第二天起占位符替换等于没做事——文件名会用真实日期、front-matter 却停在铺骨架那天，
    # 于是 check 必报 S7、时间线日期与标题互相打脸。这里按本次真实日期强制归一。
    text = re.sub(r"(?m)^(updated|session_date): .*$", r"\g<1>: " + date, text, count=2)
    os.makedirs(ctx.sess, exist_ok=True)
    write(target, text)
    print(f"created: {target}")
    print("下一步：填 §1 → 过程中追加 §2/§4 → 收尾定稿 §3/§5/§6/§7")
    return 0


# ---------------------------------------------------------------- check
def parse_inbox(ctx):
    """返回 (ids, rows, dups)。三张表统一走 inbox_entries，旧值已归一。"""
    rows = inbox_entries(ctx)
    ids = [r["id"] for r in rows]
    seen, dups = set(), []
    for i in ids:
        if i in seen and i not in dups:
            dups.append(i)
        seen.add(i)
    return ids, rows, dups


def is_placeholder_handoff(body):
    """§7 是否还是模板占位：每行都只是「- **标签**（说明）：」且值为空。"""
    lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
    if not lines:
        return True
    for ln in lines:
        if not re.fullmatch(r"[-*]?\s*\*\*[^*]+\*\*(?:（[^）]*）)?[：:]?", ln):
            return False
    return True


LANDING_PLACEHOLDERS = {"", "—", "-", "–", "待补", "待填", "tbd", "无", "同上", "n/a"}


def section_body(text, keyword):
    """取以 keyword 命名的 ## 段正文（到下一个 ## 为止）。"""
    m = re.search(rf"(?ms)^##\s+[^\n]*{re.escape(keyword)}[^\n]*\n(.*?)(?=^##\s|\Z)", text)
    return m.group(1) if m else ""


OUTPUT_SPAN_RE = re.compile(r"`([^`]+)`")
OUTPUT_EXT_RE = re.compile(r"\.(md|py|json|ya?ml|txt|skill|html)$")


def check_output_paths(rel, text, ctx):
    """W11：最新一篇 §6「本次产出」里列的路径要真实存在（只提醒，不阻断）。

    只认反引号里的、带扩展名的、仓库根相对的路径；`%TEMP%` / 绝对路径 / 网址跳过。
    """
    body = section_body(text, "本次产出")
    if not body:
        return []
    root = os.path.dirname(os.path.abspath(ctx.docs))
    missing = []
    for span in OUTPUT_SPAN_RE.findall(body):
        s = span.strip()
        if not s or "%" in s or s.startswith(("/", "~")) or "://" in s:
            continue
        if not OUTPUT_EXT_RE.search(s):
            continue
        if not os.path.exists(os.path.join(root, s)):
            missing.append(s)
    if not missing:
        return []
    return [{"file": rel, "code": "W11",
             "message": "§6「本次产出」列了不存在的路径：" + "、".join(sorted(set(missing)))}]


IDEA_KINDS = ("目标", "愿景", "功能", "需求")


def ideas_filled(text):
    """§3.7 是否真的填过一行想法：类别是四类之一且原话非空。

    只判「填没填」，判不了「这条算不算想法」——所以它只做提醒（S13 / brief），不阻断收尾。
    """
    m = re.search(r"(?ms)^###\s*3\.7\b[^\n]*\n(.*?)(?=^#{1,3}\s|\Z)", text)
    if not m:
        return False
    for _header, rows in read_tables(m.group(1)):
        for row in rows:
            if len(row) >= 2 and row[1].strip().strip("`*") in IDEA_KINDS and row[2].strip():
                return True
    return False


def check_user_side(rel, text):
    """S10：§2 用户侧记录里**已填类型**的行必须给出落点。

    「每行都要有落点」一直只是散文：漏写一行，四件照样全绿。这里只判
    「有没有给」——落点写得对不对仍需人读，脚本不假装能判。模板占位行
    （类型列为空）不算，否则新开的档案一建就红。
    """
    errs = []
    for header, rows in read_tables(section_body(text, "用户侧记录")):
        heads = [strip_md(h) for h in header]
        if "落点" not in heads:
            continue
        i_land = heads.index("落点")
        i_type = heads.index("类型") if "类型" in heads else None
        for n, r in enumerate(rows, 1):
            if len(r) != len(heads):
                continue
            kind = strip_md(r[i_type]) if i_type is not None else ""
            if not kind:
                continue
            if strip_md(r[i_land]).lower() in LANDING_PLACEHOLDERS:
                errs.append({"file": rel, "code": "S10",
                             "message": f"§2 第 {n} 行（类型 {kind}）没有落点："
                                        f"写清它落到哪一段 / 哪个 ISS / 哪份文档"})
    return errs


DECISION_FIELD_PLACEHOLDERS = {"", "—", "-", "–", "待补", "待填", "待定", "tbd", "n/a"}


def decision_blocks(text):
    """§4 决策块：[(标题, 正文)]。只认 `### D<n> · …` 开头。"""
    body = section_body(text, "决策与选项对比")
    blocks, title, buf = [], None, []
    for line in body.splitlines():
        m = re.match(r"^###\s+(D\d+)\s*·\s*(.*)$", line)
        if m:
            if title:
                blocks.append((title, "\n".join(buf)))
            title, buf = f"{m.group(1)} · {m.group(2)}".strip(" ·"), []
        elif title is not None:
            buf.append(line)
    if title:
        blocks.append((title, "\n".join(buf)))
    return blocks


def decision_field(block, name):
    """取决策块里的 `**字段**：值` 行；没有这一行返回 None。"""
    m = re.search(rf"(?m)^\s*\*\*{re.escape(name)}\*\*\s*[：:]\s*(.*)$", block)
    return None if m is None else m.group(1).strip()


def is_placeholder_value(val):
    v = (val or "").strip()
    if v.lower() in DECISION_FIELD_PLACEHOLDERS:
        return True
    return bool(re.fullmatch(r"（[^）]*）", v))   # 模板里的（…）占位


def _without_decision_section(text):
    """去掉「## 4. 决策与选项对比」整节：查引用原话时要跳过决策块自己。"""
    m = re.search(r"^##\s*4[\.、\s]", text, re.M)
    if not m:
        return text
    rest = text[m.end():]
    n = re.search(r"^##\s", rest, re.M)
    return text[:m.start()] + (rest[n.start():] if n else "")


def check_decision_review(rel, text):
    """S12：最新一篇的 §4 用户决策块必须写「依据」与「撤销条件」。

    只判**有没有写**：依据是不是真用户原话、撤销条件是否可观察，仍需人读。
    只判最新一篇（与 S9 同法，ISS-032）：存量档案没有这两行，追溯会让历史集体变红。
    拍板写「agent 自选」的块豁免——实现选择不是决策，不该被抬成四问。

    复述门（REQ-026）：用户拍板的块，「依据」必须引用用户原话（「…」），且该句在本档
    §4 之外的正文里逐字可查——把「我替你总结的结论」和「你说过的话」分开。
    """
    errs = []
    outside = _without_decision_section(text)
    for title, block in decision_blocks(text):
        if "（在决定什么）" in title:          # 新建档案的模板占位块
            continue
        who = decision_field(block, "拍板") or ""
        if re.search(r"agent|自选", who, re.I):
            continue
        for field in ("依据", "撤销条件"):
            val = decision_field(block, field)
            if val is None:
                errs.append({"file": rel, "code": "S12",
                             "message": f"决策「{title}」缺「{field}」行——"
                                        f"用户拍板的决策要答四问；实现选择写「拍板：agent 自选」可豁免"})
            elif is_placeholder_value(val):
                errs.append({"file": rel, "code": "S12",
                             "message": f"决策「{title}」的「{field}」是占位（{val or '空'}）——"
                                        f"答不出的标「断链」并用 devlog.py ask 进待分诊"})
        ev = decision_field(block, "依据") or ""
        quoted = re.findall(r"「([^」]+)」", ev)
        if not quoted:
            errs.append({"file": rel, "code": "S12",
                         "message": f"决策「{title}」的「依据」要引用用户原话（「…」）——"
                                    f"复述门：拍板前先让用户用自己的话核 2–4 个要点（SKILL 复述门）"})
            continue
        for q in quoted:
            if q.strip() and q not in outside:
                errs.append({"file": rel, "code": "S12",
                             "message": f"决策「{title}」引用的原话在本档查不到（逐字）："
                                        f"{q[:24]}——照抄用户说过的原句，别改写"})
    return errs


def check_handoff_anchor(rel, m, plan_ids, pending, plan_ok, cfg, is_latest=True):
    """S8/S9：交接段首行必须是「下一步：<任务编号>」，并与计划任务表互校。

    首行是唯一锚点位置：下一场会话先读到的就是这一行。
    §7 还是空模板时只提醒 S8，不阻断——填完再校验。

    「无」只对**最新一篇**判：更早的档案写下「无」时计划确实已清空，是当时的真话；
    后来又被插进新任务，不该让历史档案倒过来变红（ISS-032）。
    """
    errs, warns = [], []
    if not m:
        return errs, warns
    body = m.group(1)
    placeholder = is_placeholder_handoff(body)
    first = next((ln.strip() for ln in body.splitlines() if ln.strip()), "")
    anchor = re.search(r"下一步[^：:\n]*[：:]", first)
    if not anchor:
        msg = "交接段首行缺「下一步：<计划任务编号>」（锚点只认首行）"
        if placeholder:
            warns.append({"file": rel, "code": "S8", "message": msg + "；§7 仍是占位，填完再校验"})
        else:
            errs.append({"file": rel, "code": "S8", "message": msg})
        return errs, warns
    tail = first[anchor.end():].strip().lstrip("*_` ")
    if tail.startswith("无"):
        if not is_latest:
            return errs, warns
        if not plan_ok:
            errs.append({"file": rel, "code": "S9",
                         "message": "写「下一步：无」但读不到计划任务表，无法确认没有可排任务"})
        elif pending:
            errs.append({"file": rel, "code": "S9",
                         "message": "写「下一步：无」但计划表仍有未完成任务："
                                    + "、".join(sorted(pending)[:5])})
        return errs, warns
    ids = re.findall(cfg["task_pattern"].strip("^$"), first)
    if not ids:
        msg = ("交接段首行没有任务编号（应为「下一步：T1.1.1」；"
               "计划全部完成时才写「下一步：无」）")
        if placeholder:
            warns.append({"file": rel, "code": "S8", "message": msg + "；§7 仍是占位"})
        else:
            errs.append({"file": rel, "code": "S8", "message": msg})
        return errs, warns
    if not plan_ok:
        errs.append({"file": rel, "code": "S9",
                     "message": f"交接锚点 {ids[0]} 无法互校：读不到计划任务表"})
        return errs, warns
    for tid in ids:
        if tid not in plan_ids:
            errs.append({"file": rel, "code": "S9",
                         "message": f"交接锚点 {tid} 不在计划任务表"
                                    f"（写错编号会让下一个会话从不存在的地方开始）"})
    return errs, warns


def timeline_row_count(ctx):
    """时间线生成区里有多少条会话行；没有时间线或生成区返回 None。"""
    if not os.path.exists(ctx.timeline):
        return None
    text = read(ctx.timeline)
    i, j = text.find(BEGIN), text.find(END)
    if i < 0 or j < 0:
        return None
    block = text[i + len(BEGIN):j]
    return sum(1 for ln in block.splitlines()
               if re.match(r"^\|\s*20\d{2}-\d{2}-\d{2}\s*\|", ln))


INBOX_PLACEHOLDERS = {"", "—", "-", "–", "待补", "待填", "tbd", "n/a"}


def check_inbox_rows(ctx, rows, errors, warns):
    """D1–D10：问题状态机的机器判。

    只判形式：枚举、必填、前缀、开放不得关闭、实施中有无关联任务。
    判不了「这条该不该关」「理由成不成立」——那仍要人读。
    """
    f = os.path.basename(ctx.inbox)
    cfg = issue_cfg(ctx)
    types = set(cfg.get("types", []))
    natures = set(cfg.get("natures", []))
    today = datetime.date.today()
    for r in rows:
        iid, state, table = r["id"], r["state"], r["table"]
        if table == "main":
            if not r["type"] or (types and r["type"] not in types):
                errors.append({"file": f, "code": "D3",
                               "message": f"{iid} 的类型缺失或不在白名单：{r['type'] or '(空)'}"
                                          f"（允许：{'、'.join(sorted(types))}）"})
            if not r["nature"] or (natures and r["nature"] not in natures):
                errors.append({"file": f, "code": "D3",
                               "message": f"{iid} 的性质缺失或不在白名单：{r['nature'] or '(空)'}"
                                          f"（允许：{'、'.join(sorted(natures))}）"})
            if state not in ISSUE_ACTIVE:
                if state in ISSUE_TERMINAL:
                    errors.append({"file": f, "code": "D9",
                                   "message": f"{iid} 已是终态（{state}），应移入归档表并从主表删除"})
                else:
                    errors.append({"file": f, "code": "D3",
                                   "message": f"{iid} 的状态不在主表白名单：{state!r}"
                                              f"（主表只允许 确立 / 实施中；候选在待分诊，不占 ISS 号）"})
            if r["nature"] == "开放" and state in ISSUE_ACTIVE and not r["back"]:
                errors.append({"file": f, "code": "D2",
                               "message": f"{iid} 是开放问题，缺「回到条件」"})
            if r["nature"] == "开放" and state == "实现关闭":
                errors.append({"file": f, "code": "D5",
                               "message": f"{iid} 是开放问题，不得「实现关闭」；"
                                          f"本轮收口改回「确立」并更新回到条件"})
            if state in ("确立", "实施中"):
                ev = r["evidence"]
                if ev in INBOX_PLACEHOLDERS or not ev.startswith(state):
                    errors.append({"file": f, "code": "D4",
                                   "message": f"{iid} 的「依据」缺失或没有以「{state}：」开头"
                                              f"（当前：{ev or '(空)'}）"})
            if state == "实施中":
                if not re.search(r"(?<![A-Za-z0-9])[TW]\d+(?:\.\d+)*", r["evidence"]):
                    errors.append({"file": f, "code": "D6",
                                   "message": f"{iid} 为实施中，但「依据」里没有关联任务（T/W）"})
                if not r["updated"]:
                    errors.append({"file": f, "code": "D4",
                                   "message": f"{iid} 为实施中，但缺「更新」日期"})
                else:
                    try:
                        d = datetime.date.fromisoformat(r["updated"])
                        if (today - d).days > 14:
                            warns.append({"file": f, "code": "D10",
                                          "message": f"{iid} 为实施中，已 {(today - d).days} 天未更新"})
                    except ValueError:
                        errors.append({"file": f, "code": "D4",
                                       "message": f"{iid} 的「更新」不是合法日期：{r['updated']}"})
        elif table == "closed":
            if not r["question"] or r["question"] in INBOX_PLACEHOLDERS:
                errors.append({"file": f, "code": "D8",
                               "message": f"{iid} 在已闭环表里但没有结论"})
            if not re.fullmatch(r"20\d{2}-\d{2}-\d{2}", r["date"] or ""):
                errors.append({"file": f, "code": "D8",
                               "message": f"{iid} 在已闭环表里但「闭环日」缺失或非法"})
        elif table == "rejected":
            if not r["question"] or r["question"] in INBOX_PLACEHOLDERS:
                errors.append({"file": f, "code": "D7",
                               "message": f"{iid} 在已拒绝表里但没有理由"})
            if not r["decider"] or r["decider"] in INBOX_PLACEHOLDERS:
                errors.append({"file": f, "code": "D7",
                               "message": f"{iid} 在已拒绝表里但没有「决策人」"})
            if not re.fullmatch(r"20\d{2}-\d{2}-\d{2}", r["date"] or ""):
                errors.append({"file": f, "code": "D7",
                               "message": f"{iid} 在已拒绝表里但「拒绝日」缺失或非法"})
            if not r["reopen"] or r["reopen"] in INBOX_PLACEHOLDERS:
                errors.append({"file": f, "code": "D7",
                               "message": f"{iid} 在已拒绝表里但没有「重新考虑条件」"})


def cmd_check(ctx, as_json=False):
    errors, warns = [], []
    sections = ctx.schema["session_sections"]
    ids, rows, dups = parse_inbox(ctx)
    plan_ids, pending, plan_ok = plan_tasks(ctx)

    for d in dups:
        errors.append({"file": os.path.basename(ctx.inbox), "code": "D1",
                       "message": f"{d} 编号重复（终态条目应移入归档表并从主表删除）"})
    check_inbox_rows(ctx, rows, errors, warns)

    sessions = ctx.sessions()
    for i, path in enumerate(sessions):
        rel = os.path.relpath(path, ctx.docs).replace(os.sep, "/")
        text = read(path)
        fm = parse_fm(text)
        if not fm:
            errors.append({"file": rel, "code": "S1", "message": "缺 front-matter"})
            continue
        for k in ("title", "session_date", "session_no", "scope"):
            if not fm.get(k):
                errors.append({"file": rel, "code": "S1", "message": f"缺字段 {k}"})
        if fm.get("title") and fm["title"] != h1_of(text):
            errors.append({"file": rel, "code": "S2", "message": "title 与 H1 不一致"})
        if fm.get("session_date") and not re.fullmatch(r"20\d{2}-\d{2}-\d{2}", fm["session_date"]):
            errors.append({"file": rel, "code": "S3", "message": "session_date 非法"})

        heads = [m.group(1).strip() for m in re.finditer(r"(?m)^##\s+([^\n]+)", text)]
        pos = []
        for name in sections:
            hit = next((i for i, h in enumerate(heads) if name in h), None)
            if hit is None:
                errors.append({"file": rel, "code": "S4", "message": f"缺段「{name}」"})
            else:
                pos.append(hit)
        if pos and pos != sorted(pos):
            errors.append({"file": rel, "code": "S4",
                           "message": "段落顺序不符，应为：" + " → ".join(sections)})

        for r in sorted(set(re.findall(rf"{ctx.schema['ids']['issue']}-\d+", text)) - set(ids)):
            errors.append({"file": rel, "code": "S5", "message": f"引用了收件箱不存在的 {r}"})

        errors.extend(check_user_side(rel, text))
        if i == len(sessions) - 1:      # S12 只判最新一篇：存量不追溯（ISS-032）
            errors.extend(check_decision_review(rel, text))
            warns.extend(check_output_paths(rel, text, ctx))
            if not ideas_filled(text):
                warns.append({"file": rel, "code": "S13",
                              "message": "想法候选（§3.7）还没填：收尾时把本场用户原话里的"
                                         " 目标 / 愿景 / 功能 / 需求 抽一次"})

        m = re.search(r"(?ms)^##\s+[^\n]*交接[^\n]*\n(.*)$", text)
        if m and len(re.sub(r"[>\-*#\s]", "", m.group(1))) < 40:
            warns.append({"file": rel, "code": "S6", "message": "交接段过短，可能没写可执行下一步"})
        e2, w2 = check_handoff_anchor(rel, m, plan_ids, pending, plan_ok,
                                      ctx.schema["plan"],
                                      is_latest=(i == len(sessions) - 1))
        errors.extend(e2)
        warns.extend(w2)

        base = os.path.basename(path)
        expect = f"{fm.get('session_date', '')}-{fm.get('session_no', '')}-"
        if fm.get("session_date") and not base.startswith(expect):
            errors.append({"file": rel, "code": "S7", "message": f"文件名应以 {expect} 开头"})

    # 时间线陈旧是静默的：new 之后不重建，按时间线回溯就会漏掉最近的会话（ISS-030）。
    rows = timeline_row_count(ctx)
    if rows is not None and rows != len(ctx.sessions()):
        warns.append({"file": os.path.basename(ctx.timeline), "code": "S11",
                      "message": f"时间线 {rows} 行、档案 {len(ctx.sessions())} 篇——"
                                 f"跑 devlog.py index 重建"})

    if as_json:
        print(json.dumps({"ok": not errors, "sessions": len(ctx.sessions()),
                          "inbox": len(ids), "errors": errors, "warnings": warns},
                         ensure_ascii=False, indent=2))
        return 1 if errors else 0
    print(f"sessions: {len(ctx.sessions())}  inbox: {len(ids)}")
    for w in warns:
        print(f"  WARN  [{w['code']}] {w['file']}: {w['message']}")
    for e in errors:
        print(f"  ERROR [{e['code']}] {e['file']}: {e['message']}")
    print(f"errors={len(errors)}  warnings={len(warns)}")
    return 1 if errors else 0


# ---------------------------------------------------------------- brief
def latest_session(ctx):
    """最后一篇会话档案（按文件名排序）；没有返回 None。"""
    files = ctx.sessions()
    return files[-1] if files else None


def handoff_first_line(text):
    """§7 交接段的首个非空行；没有交接段返回空串。"""
    m = re.search(r"(?ms)^##\s+[^\n]*交接[^\n]*\n(.*)$", text)
    if not m:
        return ""
    return next((ln.strip() for ln in m.group(1).splitlines() if ln.strip()), "")


DUE_RE = re.compile(r"@(\d{4}-\d{2}-\d{2})")


def _read_text(path):
    try:
        with open(path, encoding="utf-8-sig") as fh:
            return fh.read()
    except OSError:
        return ""


def due_items(ctx):
    """反向判据的唤醒点：回到条件 / ADR 撤销条件 / 方向卡走通验收 里的 `@YYYY-MM-DD`。

    只认显式日期。「下次动 X 时」这类条件脚本判不了，也不该猜——猜错就变成噪音，
    而噪音会让这条提醒本身失去可信度（ISS-050 的最小机制：先让写了日期的那部分会响）。
    """
    out = []
    for r in inbox_entries(ctx):
        if r.get("table") != "main":
            continue
        m = DUE_RE.search(r.get("back") or "")
        if m:
            out.append((r["id"], m.group(1), "回到条件"))
    adr_dir = os.path.join(ctx.docs, layer_dir(ctx.schema, "decision") or "",
                           ctx.schema["names"]["adr_dir"])
    if os.path.isdir(adr_dir):
        for name in sorted(os.listdir(adr_dir)):
            if not name.endswith(".md"):
                continue
            text = _read_text(os.path.join(adr_dir, name))
            sec = re.search(r"##\s*撤销条件\s*\n(.*?)(?=\n##\s|\Z)", text, re.S)
            hit = DUE_RE.search(sec.group(1)) if sec else None
            if hit:
                out.append((name[:-3], hit.group(1), "撤销条件"))
    card = os.path.join(ctx.docs, layer_dir(ctx.schema, "facade") or "",
                        ctx.schema["names"].get("direction_card", "方向卡.md"))
    if os.path.exists(card):
        for header, rows in read_tables(_read_text(card)):
            heads = [strip_md(h) for h in header]
            if "走通验收" not in heads:
                continue
            i_ok = heads.index("走通验收")
            i_dir = heads.index("方向") if "方向" in heads else 0
            for r in rows:
                if len(r) != len(heads):
                    continue
                m = DUE_RE.search(r[i_ok])
                if m:
                    out.append((strip_md(r[i_dir]), m.group(1), "走通验收"))
    return out


def coverage_summary(ctx):
    """覆盖：方向卡「覆盖」表里有走通记录的方向数 / 方向总数（REQ-022）。

    只统计记录，不判定「走通没走通」——那只有人知道。缺表或缺主表时给 0，
    不报错：覆盖是加分项，不该把还没走通的项目变成红。
    """
    card = os.path.join(ctx.docs, layer_dir(ctx.schema, "facade") or "",
                        ctx.schema["names"].get("direction_card", "方向卡.md"))
    if not os.path.exists(card):
        return None
    dirs, cov, latest = [], {}, ""
    for header, rows in read_tables(_read_text(card)):
        heads = [strip_md(h) for h in header]
        if "方向" not in heads:
            continue
        i_dir = heads.index("方向")
        if "走通验收" in heads:
            dirs = [strip_md(r[i_dir]).strip() for r in rows if len(r) == len(heads)]
        if "最近走通" in heads:
            i_ok = heads.index("最近走通")
            for r in rows:
                if len(r) != len(heads):
                    continue
                key = strip_md(r[i_dir]).strip()
                val = strip_md(r[i_ok]).strip()
                if not key or not val or val.startswith("—") or val.startswith("-"):
                    continue
                cov[key] = val
                m = re.search(r"\d{4}-\d{2}-\d{2}", val)
                if m and m.group(0) > latest:
                    latest = m.group(0)
    n = sum(1 for d in dirs if d in cov)
    return {"n": n, "m": len(dirs), "latest": latest, "covered": sorted(cov)}


def plan_works(ctx):
    """读开发计划 §4 的工作表 → [(工作号, 方向, 状态)]。只读，不判合规。"""
    works = []
    if not os.path.exists(ctx.plan):
        return works
    for header, rows in read_tables(read(ctx.plan)):
        heads = [strip_md(h) for h in header]
        if not heads or heads[0] != "编号" or "工作" not in heads or "方向" not in heads:
            continue
        i_dir = heads.index("方向")
        i_state = heads.index("状态") if "状态" in heads else None
        for r in rows:
            if len(r) != len(heads):
                continue
            works.append((strip_md(r[0]), strip_md(r[i_dir]),
                          strip_md(r[i_state]) if i_state is not None else ""))
        return works
    return works


def coverage_gaps(ctx):
    """工作已全部完成、但覆盖表没有走通记录的方向（REQ-023）。

    这是「走通骨架」落成固定产物的一环：工作做完不等于这条线走通过，
    所以把「工作全完成、从没走过」的方向每场都摆到开场屏幕上。
    """
    by_dir = {}
    for _wid, did, st in plan_works(ctx):
        by_dir.setdefault(did, []).append(st)
    if not by_dir:
        return []
    cov = coverage_summary(ctx)
    covered = set(cov["covered"]) if cov else set()
    done = set(ctx.schema["plan"]["done_states"])
    return [d for d, states in by_dir.items()
            if states and all(s in done for s in states) and d not in covered]


def cmd_brief(ctx, as_json=False):
    """开场简报：上一场交接锚点 / 计划未完成 / 收件箱计数 / 最近三场。

    只读命令：不写文件、不产生码、不参与门禁。它存在的理由只有一个——
    让「开场先读现状」从一句纪律变成一条命令；不读就不会知道自己落后在哪。
    """
    path = latest_session(ctx)
    ids, pending, plan_ok = plan_tasks(ctx)
    _, rows, _ = parse_inbox(ctx)
    wait = pending_rows(ctx)
    p_open = [r for r in wait if r["state"] == "open"]
    p_def = [r for r in wait if r["state"] == "deferred"]
    counts = {"确立": 0, "实施中": 0, "实现关闭": 0, "拒绝": 0}
    for r in rows:
        counts[r["state"]] = counts.get(r["state"], 0) + 1

    due = due_items(ctx)
    cov = coverage_summary(ctx)
    gaps = coverage_gaps(ctx)
    today = datetime.date.today().isoformat()
    overdue = [d for d in due if d[1] <= today]
    # 没有 @日期 的活跃问题不会自己响。不猜日期，只把数量与编号摆出来：让「记得回来」
    # 从自觉变成一屏可见的清单（ISS-050 的同一思路：只提醒，不替人判）。
    active = [r for r in rows if r.get("state") in ("确立", "实施中")
              and not DUE_RE.search(r.get("back") or "")]

    recent = []
    for p in ctx.sessions()[-3:][::-1]:
        fm = parse_fm(read(p))
        title = re.sub(
            rf"^{re.escape(fm.get('session_date', ''))}\s*·\s*{re.escape(fm.get('session_no', ''))}\s*·\s*",
            "", fm.get("title", os.path.basename(p)))
        recent.append(f"{fm.get('session_date', '')} {fm.get('session_no', '')} {title}")

    anchor = handoff_first_line(read(path)) if path else ""
    if not plan_ok:
        plan_line = "计划：读不到计划任务表（§5 不可读）"
    elif not pending:
        plan_line = f"计划：未完成 0 / {len(ids)}（计划表全部已完成）"
    else:
        shown = "、".join(sorted(pending)[:5]) + ("…" if len(pending) > 5 else "")
        plan_line = f"计划：未完成 {len(pending)} / {len(ids)}（{shown}）"

    if as_json:
        print(json.dumps({
            "ok": True,
            "session": os.path.basename(path) if path else None,
            "handoff": anchor,
            "plan_ok": plan_ok,
            "pending": sorted(pending),
            "awaiting": {"open": len(p_open), "deferred": len(p_def)},
            "inbox": counts,
            "due": {"total": len(due), "overdue": [{"id": i, "date": d, "where": w}
                                                   for i, d, w in overdue],
                    "undated": [r["id"] for r in active]},
            "coverage": cov,
            "coverage_gaps": gaps,
            "ideas_filled": ideas_filled(read(path)) if path else None,
            "recent": recent,
        }, ensure_ascii=False, indent=2))
        return 0

    print("=== 开场简报 ===")
    if not path:
        print("上一场：无（尚无会话档案，先 devlog.py new）")
    else:
        print(f"上一场：{os.path.basename(path)}")
        print("  " + (anchor or "（交接段为空，收尾时补首行「下一步：<任务编号>」）"))
    print(plan_line)
    if p_open:
        print("待分诊：open %d · deferred %d  ← 未清完不许开工（devlog.py pending）"
              % (len(p_open), len(p_def)))
    else:
        print("待分诊：open 0 · deferred %d" % len(p_def))
    print(f"收件箱：确立 {counts.get('确立', 0)} · 实施中 {counts.get('实施中', 0)}"
          f" · 实现关闭 {counts.get('实现关闭', 0)} · 拒绝 {counts.get('拒绝', 0)}")
    if overdue:
        shown = "；".join(f"{k} @{d}（{w}）" for k, d, w in overdue[:4])
        print(f"复核：已到期 {len(overdue)}（{shown}）← 回来判断它还算不算成立")
    elif due:
        print("复核：%d 条设了日期，最近到期 %s" % (len(due), min(d for _, d, _ in due)))
    else:
        print("复核：无——在「回到条件 / 撤销条件 / 走通验收」里写 @YYYY-MM-DD，到期就出现在这里")
    if active:
        shown = "、".join(r["id"] for r in active[:6]) + ("…" if len(active) > 6 else "")
        print(f"回访：{len(active)} 条活跃问题没设 @日期（{shown}）"
              "← 它们不会自己响；收口时补日期，或写明「无日期」原因")
    if cov and cov["m"]:
        if cov["n"]:
            print(f"覆盖：{cov['n']}/{cov['m']}（最近走通 {cov['latest'] or '—'}）"
                  "← 覆盖 = 有走通记录的方向数 / 方向总数（REQ-022）")
        else:
            print(f"覆盖：0/{cov['m']}——还没有走通记录；跑完一条后写进方向卡的「覆盖」表")
    if gaps:
        print(f"走通待补：{'、'.join(gaps)}（工作已全部完成、覆盖表无记录）"
              "← 跑一次该方向的走通验收并写进覆盖表（REQ-023）")
    dec_bad = [r for r in collect_decisions(ctx) if r["status"] != "正常"]
    if dec_bad:
        n_link = sum(1 for r in dec_bad if r["status"] == "断链")
        print(f"决策待复核：{len(dec_bad)} 条（断链 {n_link} / "
              f"久未复核 {len(dec_bad) - n_link}）"
              "← 跑 `devlog.py decisions` 看台账（REQ-028）")
    if path and not ideas_filled(read(path)):
        print("整理：上一场档案还没填 §3.7（想法候选）← 收尾时抽一次 目标/愿景/功能/需求，"
              "原话逐字（E29 会核）")
    print("最近 3 场：" + (" / ".join(recent) if recent else "无"))
    return 0


# ---------------------------------------------------------------- index
def build_timeline(ctx):
    rows = []
    for path in ctx.sessions():
        fm = parse_fm(read(path))
        if not fm.get("session_date"):
            continue
        title = re.sub(
            rf"^{re.escape(fm.get('session_date', ''))}\s*·\s*{re.escape(fm.get('session_no', ''))}\s*·\s*",
            "", fm.get("title", os.path.basename(path)))
        rows.append((fm.get("session_date", ""), fm.get("session_no", ""), title,
                     fm.get("scope", ""), fm.get("decisions", ""),
                     fm.get("open_items", ""), "./" + ctx.schema["names"]["sessions_dir"] + "/"
                     + os.path.basename(path)))
    rows.sort(key=lambda r: (r[0], r[1]), reverse=True)
    out = ["| 日期 | # | 会话主题 | 范围 | 决策 | 开放项 | 档案 |",
           "|---|---|---|---|---|---|---|"]
    if not rows:
        out.append("| — | — | 尚无会话档案；用 `python scripts/devlog.py new --title \"主题\"` 建第一份 "
                   "| — | — | — | — |")
    for date, no, title, scope, dec, opened, link in rows:
        out.append(f"| {cell(date)} | {cell(no)} | [{cell(title)}]({cell(link)}) "
                   f"| {cell(scope)} | {cell(dec)} | {cell(opened)} "
                   f"| `{os.path.basename(link)}` |")
    out += ["", "> 按日期倒序；数据来自各档案 front-matter，由 `scripts/devlog.py index` 生成，勿手改。"]
    return "\n".join(out) + "\n"


DECISION_LEDGER = "决策台账.md"
# 决策「撤销条件」里引用的编号：只在「表格首格」出现才算被定义（避免自证）
DEF_ID_RE = re.compile(
    r"^\|\s*\**\s*((?:REQ|ISS|F)-\d+|(?:W|T)\d+(?:\.\d+)*|(?:D|K)\d+)\s*\**\s*\|")
# 方向卡 / 设计卡用标题定义编号：`## K16 · W18.1 · …`、`| **D11** | …`（后者走表格规则）
DEF_HEAD_RE = re.compile(r"^#{2,3}\s*((?:D|K)\d+)\b")
REF_ID_RE = re.compile(r"\b(?:REQ|ISS|F)-\d+\b|\b(?:W|T)\d+\.\d+(?:\.\d+)?\b|\b(?:D|K)\d+\b")
DECISION_STALE_DAYS = 60


def _known_ids(ctx):
    """全库「定义过」的编号：表格首格出现的才算（正文里提到的不算）。"""
    ids = set()
    for root, _dirs, files in os.walk(ctx.docs):
        for f in files:
            if not f.endswith(".md"):
                continue
            for line in read(os.path.join(root, f)).splitlines():
                s = line.strip()
                m = DEF_ID_RE.match(s)
                if m:
                    ids.add(m.group(1))
                    continue
                m = DEF_HEAD_RE.match(s)
                if m:
                    ids.add(m.group(1))
    return ids


def collect_decisions(ctx):
    """读全部会话档案 §4，返回每条决策的摘要与待复核状态（只读）。"""
    known = _known_ids(ctx)
    today = datetime.date.today()
    out = []
    for path in ctx.sessions():
        text = read(path)
        fm = parse_fm(text) or {}
        date = (fm.get("session_date") or "").strip()
        for title, block in decision_blocks(text):
            if "（在决定什么）" in title:
                continue
            concl = decision_field(block, "结论") or ""
            who = decision_field(block, "拍板") or ""
            why = decision_field(block, "依据") or ""
            redo = decision_field(block, "复述") or ""
            undo = decision_field(block, "撤销条件") or ""
            refs = sorted(set(REF_ID_RE.findall(undo)))
            dangling = [r for r in refs if r not in known]
            stale = False
            try:
                stale = (today - datetime.date.fromisoformat(date)).days > DECISION_STALE_DAYS
            except ValueError:
                pass
            status = "断链" if dangling else ("久未复核" if stale else "正常")
            out.append({
                "date": date,
                "file": os.path.basename(path),
                "title": title,
                "conclusion": concl.strip(),
                "who": who.strip(),
                "why": why.strip(),
                "redo": redo.strip(),
                "undo": undo.strip(),
                "dangling": dangling,
                "status": status,
            })
    return out


def render_decision_ledger(rows):
    today = datetime.date.today().isoformat()
    lines = [
        "---",
        'title: "决策台账"',
        "layer: process",
        "domain: 协作",
        "status: active",
        "authority: 4",
        f"updated: {today}",
        'summary: "自动生成：每条决策的结论 / 拍板 / 撤销条件与待复核状态。"',
        "tags: [过程, 生成区]",
        "---",
        "",
        "# 决策台账",
        "",
        "> **自动生成，勿手改**：由 `python scripts/devlog.py decisions` 重建（生成区不手改）。",
        "> 一屏看全：什么时候、谁拍的板、依据是什么、撤销条件写了什么、以及**是否待复核**（断链 / 久未复核）。",
        "",
        f"共 **{len(rows)}** 条决策；待复核 **{sum(1 for r in rows if r['status'] != '正常')}** 条"
        f"（断链 {sum(1 for r in rows if r['status'] == '断链')} / 久未复核 {sum(1 for r in rows if r['status'] == '久未复核')}）。",
        "",
        "| 日期 | 档案 | 决策 | 结论 | 拍板 | 撤销条件 | 状态 |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        cells = [r["date"], r["file"], r["title"], r["conclusion"], r["who"],
                 r["undo"] or "—", r["status"]]
        # 台账比档案高一层：原文里的相对链接在这是断的，只留文字（E7）
        cells = [re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", c)
                 .replace("|", "\\|").replace("\n", " ") for c in cells]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def cmd_decisions(ctx, as_json):
    rows = collect_decisions(ctx)
    if as_json:
        print(json.dumps({"total": len(rows), "rows": rows}, ensure_ascii=False, indent=2))
        return 0
    path = os.path.join(ctx.pdir, DECISION_LEDGER)
    write(path, render_decision_ledger(rows))
    bad = sum(1 for r in rows if r["status"] != "正常")
    print(f"决策台账 written: {len(rows)} 条，待复核 {bad} 条（{path}）")
    return 0


COST_LEDGER = "成本台账.md"


def _minutes(v):
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


def _table_rows(body):
    n = 0
    for line in body.splitlines():
        s = line.strip()
        if s.startswith("|") and not re.match(r"^\|[\s\-:|]+\|$", s):
            n += 1
    return max(0, n - 1)          # 去掉表头


def collect_costs(ctx):
    """读全部会话档案：自报耗时（front-matter）+ 自动密度（预审 / 决策条数）。"""
    rows = []
    for path in ctx.sessions():
        text = read(path)
        fm = parse_fm(text) or {}
        total = _minutes(fm.get("cost_minutes"))
        tool = _minutes(fm.get("cost_tool_minutes"))
        pre = _table_rows(section_body(text, "预审记录"))
        dec = len([t for t, _b in decision_blocks(text) if "（在决定什么）" not in t])
        rows.append({
            "date": (fm.get("session_date") or "").strip(),
            "file": os.path.basename(path),
            "total": total,
            "tool": tool,
            "share": (round(100.0 * tool / total, 1) if total and tool is not None else None),
            "preaudit": pre,
            "decisions": dec,
            "note": (fm.get("cost_note") or "").strip(),
        })
    return rows


def render_cost_ledger(rows):
    today = datetime.date.today().isoformat()
    tot = [r for r in rows if r["total"] is not None]
    tool = [r for r in tot if r["tool"] is not None]
    avg = (sum(r["total"] for r in tot) / len(tot)) if tot else None
    avg_tool = (sum(r["tool"] for r in tool) / len(tool)) if tool else None
    lines = [
        "---",
        'title: "成本台账"',
        "layer: process",
        "domain: 协作",
        "status: active",
        "authority: 4",
        f"updated: {today}",
        'summary: "自动生成：每场自报耗时（总 / 工具）+ 密度（预审 / 决策）+ 环比。"',
        "tags: [过程, 生成区]",
        "---",
        "",
        "# 成本台账",
        "",
        "> **自动生成，勿手改**：由 `python scripts/devlog.py cost` 重建。",
        "> 自报耗时写在档案 front-matter：`cost_minutes`（总）/ `cost_tool_minutes`（其中工具）/ `cost_note`（一句话）。",
        "",
        f"共 **{len(rows)}** 场；有自报 **{len(tot)}** 场"
        f"（平均总耗时 **{avg:.0f} 分钟**），其中 **{len(tool)}** 场报了工具耗时"
        f"（平均 **{avg_tool:.0f} 分钟**）。" if avg is not None else
        f"共 **{len(rows)}** 场；还没有自报耗时（写 front-matter 的 `cost_minutes` 后重建）。",
        "",
        "| 日期 | 档案 | 总(分) | 工具(分) | 工具占比 | 预审条 | 决策数 | 较上一场 | 备注 |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    prev = None
    for r in rows:
        delta = "—"
        if prev is not None and r["total"] is not None and prev["total"] is not None:
            d = r["total"] - prev["total"]
            delta = f"{d:+d} 分"
        cells = [r["date"], r["file"],
                 "—" if r["total"] is None else str(r["total"]),
                 "—" if r["tool"] is None else str(r["tool"]),
                 "—" if r["share"] is None else f"{r['share']}%",
                 str(r["preaudit"]), str(r["decisions"]), delta, r["note"] or "—"]
        cells = [c.replace("|", "\\|").replace("\n", " ") for c in cells]
        lines.append("| " + " | ".join(cells) + " |")
        prev = r
    return "\n".join(lines) + "\n"


def cmd_cost(ctx, as_json):
    rows = collect_costs(ctx)
    if as_json:
        print(json.dumps({"total": len(rows), "rows": rows}, ensure_ascii=False, indent=2))
        return 0
    path = os.path.join(ctx.pdir, COST_LEDGER)
    write(path, render_cost_ledger(rows))
    n = sum(1 for r in rows if r["total"] is not None)
    print(f"成本台账 written: {len(rows)} 场，有自报 {n} 场（{path}）")
    return 0


def cmd_index(ctx, check_only):
    if not os.path.exists(ctx.timeline):
        return die(f"缺少时间线：{ctx.timeline}")
    text = read(ctx.timeline)
    i, j = text.find(BEGIN), text.find(END)
    if i < 0 or j < 0:
        return die("时间线缺少生成区标记 BEGIN/END:devlog-index")
    block = build_timeline(ctx)
    new_text = text[: i + len(BEGIN)] + "\n\n" + block + "\n" + text[j:]
    if check_only:
        same = new_text == text
        print("timeline up-to-date" if same else "timeline OUT OF DATE")
        return 0 if same else 1
    write(ctx.timeline, new_text)
    ledger = os.path.join(ctx.pdir, DECISION_LEDGER)
    write(ledger, render_decision_ledger(collect_decisions(ctx)))
    write(os.path.join(ctx.pdir, COST_LEDGER), render_cost_ledger(collect_costs(ctx)))
    print(f"timeline written: {len(ctx.sessions())} sessions（决策台账 / 成本台账同步重建）")
    return 0


# ---------------------------------------------------------------- main
def main():
    argv = sys.argv[1:]
    docs_arg = None
    for i, a in enumerate(argv):
        if a == "--docs" and i + 1 < len(argv):
            docs_arg = argv[i + 1]
            del argv[i:i + 2]
            break

    as_json = "--json" in argv
    argv = [a for a in argv if a != "--json"]

    ap = argparse.ArgumentParser(description="过程档案工具：建档 / 校验 / 时间线")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_new = sub.add_parser("new")
    p_new.add_argument("--title", required=True)
    p_new.add_argument("--date", default=None)
    p_new.add_argument("--scope", default="待填")
    sub.add_parser("brief")
    p_ask = sub.add_parser("ask")
    p_ask.add_argument("question")
    p_ask.add_argument("--if", dest="premise", default="")
    p_pend = sub.add_parser("pending")
    p_pend.add_argument("--clear", default=None)
    p_pend.add_argument("--as", dest="export", default=None,
                        choices=["iss", "s5", "drop", "defer"])
    p_pend.add_argument("--note", default="")
    p_pend.add_argument("--relation", default=None,
                        help="转正关系：new | merge:ISS-nnn | extends:ISS-nnn | updates:ISS-nnn | duplicate:ISS-nnn")
    p_pend.add_argument("--type", default=None,
                        help="--relation new 时必填：缺陷/缺口/债/冲突/风险/机会/待决")
    p_pend.add_argument("--nature", default=None, choices=["可关闭", "开放"],
                        help="--relation new 时可选：可关闭/开放；缺省按类型推断（机会/待决=开放）")
    p_pend.add_argument("--impact", default=None, help="--relation new 时必填：不处理会怎样")
    p_pend.add_argument("--to", default=None, help="--relation new 时必填：落点（计划任务/文件/ADR）")
    p_inbox = sub.add_parser("inbox")
    p_inbox.add_argument("--similar", default=None, help="给一段文字，列可能相关的开放条目")
    p_inbox.add_argument("--top", type=int, default=3)
    p_features = sub.add_parser("features")
    p_features.add_argument("--state", default=None,
                            help="只看某个状态（实施中 / 已对照 / 已验收 …）")
    sub.add_parser("check")
    sub.add_parser("decisions")
    sub.add_parser("cost")
    p_idx = sub.add_parser("index")
    p_idx.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)

    docs = find_docs(docs_arg)
    if docs is None:
        return die("找不到文档目录（已试 docs/ 文档/ documentation）。"
                   "用 --docs 指定，或在项目根目录运行。", as_json)
    try:
        schema = load_schema(docs)
    except SchemaError as exc:
        return die(str(exc), as_json)
    ctx = Ctx(docs, schema)
    if not os.path.isdir(ctx.pdir):
        return die(f"找不到过程层目录：{ctx.pdir}。"
                   f"检查 _schema.json 的 layers 是否含 process，或先跑 doc_init.py", as_json)

    if args.cmd == "new":
        return cmd_new(ctx, args)
    if args.cmd == "brief":
        return cmd_brief(ctx, as_json)
    if args.cmd == "ask":
        return cmd_ask(ctx, args)
    if args.cmd == "pending":
        return cmd_pending(ctx, args)
    if args.cmd == "inbox":
        return cmd_inbox(ctx, args)
    if args.cmd == "features":
        return cmd_features(ctx, args)
    if args.cmd == "check":
        return cmd_check(ctx, as_json)
    if args.cmd == "decisions":
        return cmd_decisions(ctx, as_json)
    if args.cmd == "cost":
        return cmd_cost(ctx, as_json)
    return cmd_index(ctx, args.check)


if __name__ == "__main__":
    sys.exit(main())
