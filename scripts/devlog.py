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
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return ""


def read_tables(text):
    tables, block = [], []
    for line in text.splitlines() + [""]:
        s = line.strip()
        if s.startswith("|") and s.endswith("|") and len(s) > 2:
            block.append([c.strip() for c in s[1:-1].split("|")])
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


def set_pending_state(path, qid, state, note):
    out = []
    for ln in read(path).splitlines(True):
        s = ln.strip()
        if s.startswith("|") and s.endswith("|") and s.count("|") >= 5:
            parts = s[1:-1].split("|")
            if parts[0].strip().strip("*` ") == qid:
                parts[-2] = " %s " % state
                parts[-1] = " %s " % cell(note)
                out.append("|" + "|".join(parts) + "|\n")
                continue
        out.append(ln)
    write(path, "".join(out))


# ---------------------------------------------------------------- 收件箱（查重 / 转正）
def inbox_entries(ctx):
    """收件箱主表 + 已闭环表的条目（id/state/question/impact/to）。"""
    out = []
    if not os.path.exists(ctx.inbox):
        return out
    prefix = re.escape(ctx.schema["ids"]["issue"])
    id_re = re.compile(rf"{prefix}-\d+")
    for header, rows in read_tables(read(ctx.inbox)):
        heads = [strip_md(h) for h in header]
        if "ID" not in heads:
            continue
        # 主表（有「问题」列）与闭环表（只有「结论 / 闭环日」）都要认：
        # 只读主表会让「已闭环」永远显示 0（ISS-033）。
        i_id = heads.index("ID")
        i_q = heads.index("问题") if "问题" in heads else heads.index("结论") if "结论" in heads else None
        if i_q is None:
            continue
        i_st, i_imp, i_to = _col(heads, "状态"), _col(heads, "影响"), _col(heads, "落点")
        for r in rows:
            if len(r) != len(heads):
                continue
            iid = strip_md(r[i_id])
            if not id_re.fullmatch(iid):
                continue
            out.append({
                "id": iid,
                "state": strip_md(r[i_st]) if i_st is not None else "done",
                "question": strip_md(r[i_q]),
                "impact": strip_md(r[i_imp]) if i_imp is not None else "",
                "to": strip_md(r[i_to]) if i_to is not None else "",
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
        if e["state"] not in ("open", "deferred"):
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


def append_inbox_row(ctx, iid, kind, question, impact, to):
    """只**追加**一行到收件箱主表末尾：不动别人的行、不重排、不改历史。"""
    text = read(ctx.inbox)
    lines = text.splitlines(True)
    head = None
    for i, ln in enumerate(lines):
        if not ln.strip().startswith("|"):
            continue
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        if cells and cells[0] == "ID" and "状态" in cells and "问题" in cells:
            head = i
            break
    if head is None:
        raise ValueError("收件箱里找不到「ID | … | 状态 | … | 问题 |」的主表")
    end = head + 1
    while end < len(lines) and lines[end].strip().startswith("|"):
        end += 1
    row = "| **%s** | %s | 分诊转正 | %s | %s | %s | `open` | %s | — |\n" % (
        iid, datetime.date.today().isoformat(), cell(kind), cell(question),
        cell(impact), cell(to))
    lines.insert(end, row)
    write(ctx.inbox, "".join(lines))


def cmd_inbox(ctx, args):
    if not args.similar:
        entries = inbox_entries(ctx)
        opened = [e for e in entries if e["state"] == "open"]
        deferred = [e for e in entries if e["state"] == "deferred"]
        print("收件箱：open %d · deferred %d · 已闭环 %d"
              % (len(opened), len(deferred), len(entries) - len(opened) - len(deferred)))
        for e in opened + deferred:
            print("  %s  [%s]  %s" % (e["id"], e["state"], e["question"]))
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
        print("对照清单：assets/templates/feature-check.md（三栏：功能 / 该验什么 / 结论与差异）")
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
                append_inbox_row(ctx, iid, args.type, target["question"],
                                 args.impact, args.to)
                state, note = "→" + iid, note or ("新登记 " + iid)
                print("新增 %s（独立）" % iid)
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
    """返回 (ids, rows, dups)。

    主表与「已闭环」表都统计：done 条目留在主表 = 编号重复（D1），这是刻意的。
    """
    ids, rows, dups = [], [], []
    if not os.path.exists(ctx.inbox):
        return ids, rows, dups
    prefix = re.escape(ctx.schema["ids"]["issue"])
    id_re = re.compile(rf"^{prefix}-\d+$")
    for header, trows in read_tables(read(ctx.inbox)):
        if not header or header[0] != "ID":
            continue
        has_state = "状态" in header
        i_state = header.index("状态") if has_state else None
        i_back = header.index("回到条件") if "回到条件" in header else None
        for r in trows:
            raw = strip_md(r[0])
            if not id_re.fullmatch(raw):
                continue
            ids.append(raw)
            rows.append({
                "id": raw,
                "state": strip_md(r[i_state]) if i_state is not None and i_state < len(r) else "done",
                "back": strip_md(r[i_back]) if i_back is not None and i_back < len(r) else "",
            })
    seen = set()
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


def cmd_check(ctx, as_json=False):
    errors, warns = [], []
    sections = ctx.schema["session_sections"]
    ids, rows, dups = parse_inbox(ctx)
    plan_ids, pending, plan_ok = plan_tasks(ctx)

    for d in dups:
        errors.append({"file": os.path.basename(ctx.inbox), "code": "D1",
                       "message": f"{d} 编号重复（done 条目应移入「已闭环」并从主表删除）"})
    for r in rows:
        if r["state"] == "deferred" and not r["back"]:
            errors.append({"file": os.path.basename(ctx.inbox), "code": "D2",
                           "message": f"{r['id']} 为 deferred 但缺「回到条件」"})

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
    counts = {"open": 0, "deferred": 0, "done": 0}
    for r in rows:
        counts[r["state"]] = counts.get(r["state"], 0) + 1

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
    print(f"收件箱：open {counts.get('open', 0)} · deferred {counts.get('deferred', 0)}"
          f" · 已闭环 {counts.get('done', 0)}")
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
    print(f"timeline written: {len(ctx.sessions())} sessions")
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
    p_pend.add_argument("--type", default=None, help="--relation new 时必填：缺陷/风险/文档债/口径冲突/待决/机会")
    p_pend.add_argument("--impact", default=None, help="--relation new 时必填：不处理会怎样")
    p_pend.add_argument("--to", default=None, help="--relation new 时必填：落点（计划任务/文件/ADR）")
    p_inbox = sub.add_parser("inbox")
    p_inbox.add_argument("--similar", default=None, help="给一段文字，列可能相关的开放条目")
    p_inbox.add_argument("--top", type=int, default=3)
    p_features = sub.add_parser("features")
    p_features.add_argument("--state", default=None,
                            help="只看某个状态（实施中 / 已对照 / 已验收 …）")
    sub.add_parser("check")
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
    return cmd_index(ctx, args.check)


if __name__ == "__main__":
    sys.exit(main())
