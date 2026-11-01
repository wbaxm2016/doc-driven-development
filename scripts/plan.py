#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""开发计划的排序与校验。

用法：
    python scripts/plan.py index            # 重算各视角排序视图，写回文档生成区
    python scripts/plan.py index --check    # 只比对，不写（CI / 收尾用）
    python scripts/plan.py check [--json]   # 结构校验

维度与视角全部从表头读取，脚本不认识具体维度名 —— 加维度/加视角不改代码。
编号规则、状态词、文件位置来自 <docs>/_schema.json。
"""
from __future__ import annotations

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
    "names": {"plan": "开发计划.md"},
    "plan": {
        "done_states": ["已完成"],
        "states": ["待开工", "进行中", "已实现（未验收）", "已完成", "阻塞", "搁置"],
        "task_pattern": r"^T\d+\.\d+\.\d+$",
        "work_pattern": r"^W\d+\.\d+$",
        "direction_pattern": r"^D\d+$",
    },
}

BEGIN = "<!-- BEGIN:plan-rank -->"
END = "<!-- END:plan-rank -->"


def die(msg, as_json=False, code=2):
    if as_json:
        print(json.dumps({"ok": False, "fatal": msg}, ensure_ascii=False))
    else:
        print(f"ERROR {msg}")
    return code


def read(path):
    # utf-8-sig：带 BOM 的计划文档不该被当成坏 JSON/坏文件。
    with open(path, encoding="utf-8-sig") as fh:
        return fh.read()


def write(path, text):
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def strip_md(s):
    return re.sub(r"[*`]", "", s).strip()


def layer_dir(schema, name):
    for d, v in schema["layers"].items():
        if v == name:
            return d
    return None


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
                    f"{p} 解析失败：{exc}。这个文件是层/枚举/编号规则的唯一来源，"
                    f"要么修好它，要么删掉回退内置默认")
            if not isinstance(raw, dict):
                raise SchemaError(f"{p} 顶层不是对象（应为 {{\"layers\": {{...}}}}）")
            merged = json.loads(json.dumps(DEFAULT_SCHEMA))
            for k, v in raw.items():
                if isinstance(v, dict) and isinstance(merged.get(k), dict):
                    merged[k].update(v)
                else:
                    merged[k] = v
            # layers 整表替换（与 doc_check / devlog 同一条规则）：合并会让默认 5 层
            # 项目永远带着 8 层的内置表，找不到 process 层的"假缺失"就是这么来的。
            if "layers" in raw:
                merged["layers"] = raw["layers"]
            return merged
    return json.loads(json.dumps(DEFAULT_SCHEMA))


# ---------------------------------------------------------------- 表格解析
def cells(line):
    s = line.strip()
    if not s.startswith("|") or not s.endswith("|") or len(s) < 3:
        return None
    return [p.strip() for p in s[1:-1].split("|")]


def is_sep(row):
    return all(re.fullmatch(r":?-{2,}:?", c or "-") for c in row)


def read_tables(lines):
    tables, i, n = [], 0, len(lines)
    while i < n:
        header = cells(lines[i])
        if header is None:
            i += 1
            continue
        start = i
        rows, i = [], i + 1
        while i < n:
            c = cells(lines[i])
            if c is None:
                break
            if not is_sep(c):
                rows.append([strip_md(x) for x in c])
            i += 1
        tables.append(([strip_md(h) for h in header], rows, start + 1))
    return tables


# 表格被空行/断行截断后，后半段的「表头」其实是数据行。用编号形态认出它：
# 真正的表头是「ID / 编号 / 视角 / 日期 / 选项」这类词，不会是 T1.1.1 或 2026-11-01。
FRAGMENT_ID = re.compile(
    r"^(T\d+\.\d+\.\d+|W\d+\.\d+|D\d+|ISS-\d+|REQ-\d+|F-\d+|\d{4}-\d{2}-\d{2})$")


def dim_codes(header):
    return [h for h in header if re.fullmatch(r"[A-Z]", h)]


# ---------------------------------------------------------------- 载入
def load(path):
    lines = read(path).splitlines()
    weights = tasks = works = dirs = None
    fragments = []
    for header, rows, no in read_tables(lines):
        if not header:
            continue
        if header[0] == "视角" and len(dim_codes(header)) >= 2:
            weights = (header, rows)
        elif header[0] == "ID" and "任务" in header and dim_codes(header):
            tasks = (header, rows)
        elif header[0] == "编号" and "工作" in header:
            works = (header, rows)
        elif header[0] == "编号" and "方向" in header:
            dirs = (header, rows)
        elif FRAGMENT_ID.fullmatch(header[0]):
            fragments.append((header[0], no))
    if weights is None:
        raise SystemExit("找不到权重表（首列应为「视角」且含维度列）")
    if tasks is None:
        raise SystemExit("找不到任务表（首列应为「ID」且含维度列）")
    return lines, weights, tasks, works, dirs, fragments


# ---------------------------------------------------------------- 校验
def validate(weights, tasks, works, dirs, cfg, fragments=()):
    """返回 (errs, items, codes, done, work_ids)。errs 里每条都带码，与 check-rules.md 的 P 段一一对应。"""
    errs = []

    def E(code, msg):
        errs.append({"code": code, "message": msg})

    # P13：表格被空行/断行截断后，后半段的行会被当成「表头」静默丢掉——
    # 那正是「errors=0 却只校验了 26 个任务」的来源（ISS-035）。
    for label, no in fragments:
        E("P13", f"第 {no} 行起的表格被空行/断行截断：表头其实是数据行「{label}」；"
                 f"这一段不在任何表里，接回上一张表（或删掉多余空行）")

    w_header, w_rows = weights
    t_header, t_rows = tasks
    codes = dim_codes(t_header)
    idx = {name: i for i, name in enumerate(t_header)}
    pat_t = re.compile(cfg["task_pattern"])
    pat_w = re.compile(cfg["work_pattern"])
    pat_d = re.compile(cfg["direction_pattern"])
    states = set(cfg["states"])
    done = set(cfg["done_states"])

    work_ids, work_dir = set(), {}
    if works:
        for r in works[1]:
            if r:
                work_ids.add(r[0])
                if not pat_w.fullmatch(r[0]):
                    E("P9", f"工作编号不合规：{r[0]}（应形如 W1.1）")
                if "方向" in works[0]:
                    work_dir[r[0]] = r[works[0].index("方向")]
    dir_ids = set()
    if dirs:
        for r in dirs[1]:
            if r:
                dir_ids.add(r[0])
                if not pat_d.fullmatch(r[0]):
                    E("P9", f"方向编号不合规：{r[0]}（应形如 D1）")
    # P12：工作表的方向列必须落在方向表里（任务→工作有 P5，工作→方向不能缺）
    if dir_ids:
        for wid, dref in sorted(work_dir.items()):
            if dref and dref not in dir_ids:
                E("P12", f"{wid} 所属方向不存在：{dref}")

    all_task_ids = {r[idx["ID"]] for r in t_rows if len(r) == len(t_header)}
    items, seen = [], {}
    for r in t_rows:
        if len(r) != len(t_header):
            E("P10", f"任务行列数不符（{len(r)}≠{len(t_header)}）：{' | '.join(r)[:60]}")
            continue
        tid = r[idx["ID"]]
        if tid in seen:
            E("P2", f"任务编号重复：{tid}")
        seen[tid] = True
        if not pat_t.fullmatch(tid):
            E("P1", f"任务编号不合规：{tid}（应形如 T1.1.1）")
        status = r[idx["状态"]] if "状态" in idx else ""
        if states and status not in states:
            E("P3", f"{tid} 的状态词不在白名单：{status!r}（允许：{'、'.join(sorted(states))}）")
        scores = {}
        for c in codes:
            v = r[idx[c]]
            if not re.fullmatch(r"\d", v or "") or not 1 <= int(v) <= 5:
                E("P4", f"{tid} 的 {c} 分值非法：{v!r}（应为 1–5 整数）")
                scores[c] = 0
            else:
                scores[c] = int(v)
        work = r[idx["所属"]] if "所属" in idx else ""
        if work_ids and work not in work_ids:
            E("P5", f"{tid} 的所属工作不存在：{work}")
        if pat_t.fullmatch(tid) and pat_w.fullmatch(str(work)):
            if tid[1:].split(".")[:2] != work[1:].split("."):
                E("P6", f"{tid} 的前缀与所属 {work} 不一致（编号应共享 n.m）")
        pre = r[idx["前置"]] if "前置" in idx else "-"
        pres = [p.strip() for p in re.split(r"[,，/]", pre) if p.strip() and p.strip() != "-"]
        # P11：前置必须指向表里存在的任务，否则该任务会被永久标 ⛔ 且没有任何诊断
        for p in pres:
            if p not in all_task_ids:
                E("P11", f"{tid} 的前置编号不存在：{p}（表里没有这条任务；"
                         f"写错一个编号就会把它永久卡在 ⛔）")
        items.append({"id": tid, "name": r[idx["任务"]], "work": work,
                      "status": status, "pre": pre, "scores": scores})

    for row in w_rows:
        if len(row) != len(w_header):
            E("P10", f"权重行列数不符：{' | '.join(row)[:60]}")
            continue
        try:
            total = sum(int(row[w_header.index(c)]) for c in dim_codes(w_header))
        except ValueError:
            E("P7", f"权重行含非数字：{' | '.join(row)[:60]}")
            continue
        if total == 0:
            E("P7", f"视角「{row[0]}」权重全为 0")

    return errs, items, codes, done, work_ids


# ---------------------------------------------------------------- 计算
def compute(weights, items, codes, done, work_ids, cfg):
    w_header, w_rows = weights
    statuses = {t["id"]: t["status"] for t in items}
    for t in items:
        pres = [p.strip() for p in re.split(r"[,，/]", t["pre"]) if p.strip() and p.strip() != "-"]
        blocked = []
        for p in pres:
            if p not in statuses:
                blocked.append(f"前置不存在:{p}")
            elif statuses[p] not in done:
                blocked.append(p)
        t["blocked_by"] = blocked
        if work_ids and t["work"] not in work_ids:
            t["blocked_by"].append(f"所属工作不存在:{t['work']}")

    views = []
    for row in w_rows:
        if len(row) != len(w_header):
            continue
        w = {c: int(row[w_header.index(c)]) for c in dim_codes(w_header)}
        total_w = sum(w.get(c, 0) for c in codes)
        if total_w == 0:
            continue
        order = []
        for t in items:
            if t["status"] in done:
                continue
            score = sum(w.get(c, 0) * t["scores"][c] for c in codes) / total_w
            worst = min(codes, key=lambda c: (t["scores"][c], -w.get(c, 0)))
            order.append((round(score, 2), t, worst))
        order.sort(key=lambda x: (-x[0], x[1]["id"]))
        views.append((row[0], order))
    return views


def render(views):
    out = [BEGIN, "",
           "_由 `python scripts/plan.py index` 生成，勿手改；⛔＝前置未完成，不进 Top。_"]
    for view, order in views:
        free = [o for o in order if not o[1]["blocked_by"]]
        out += ["", f"**视角：{view}**", "",
                "| # | ID | 任务 | 分数 | 弱项 | 状态 |", "|---|---|---|---|---|---|"]
        for i, (score, t, worst) in enumerate(free[:5], 1):
            out.append(f"| {i} | {t['id']} | {t['name']} | {score:.2f} "
                       f"| {worst}={t['scores'][worst]} | {t['status']} |")
        blocked = [o for o in order if o[1]["blocked_by"]]
        if blocked:
            out += ["", "⛔ 暂不可排：" + "、".join(
                f"{t['id']}（卡 {', '.join(t['blocked_by'])}）" for _, t, _ in blocked)]
    out += ["", END]
    return "\n".join(out)


# ---------------------------------------------------------------- main
def main():
    argv = sys.argv[1:]
    docs_arg, file_arg = None, None
    for i, a in enumerate(argv):
        if a in ("--docs", "--file") and i + 1 < len(argv):
            if a == "--docs":
                docs_arg = argv[i + 1]
            else:
                file_arg = argv[i + 1]
            del argv[i:i + 2]
            break
    as_json = "--json" in argv
    argv = [a for a in argv if a != "--json"]

    cmd = next((a for a in argv if not a.startswith("--")), "index")
    check_only = "--check" in argv

    docs = find_docs(docs_arg)
    if docs is None:
        return die("找不到文档目录（docs/ 文档/ documentation）。用 --docs 指定。", as_json)
    try:
        schema = load_schema(docs)
    except SchemaError as exc:
        return die(str(exc), as_json)
    fdir = layer_dir(schema, "facade")
    path = file_arg or os.path.join(docs, fdir or "", schema["names"]["plan"])
    if not os.path.exists(path):
        return die(f"找不到计划文档：{path}", as_json)

    try:
        lines, weights, tasks, works, dirs, fragments = load(path)
    except SystemExit as exc:
        return die(str(exc), as_json, 1)

    cfg = schema["plan"]
    errs, items, codes, done, work_ids = validate(weights, tasks, works, dirs, cfg, fragments)

    if cmd == "check":
        views = compute(weights, items, codes, done, work_ids, cfg)
        pending = [t for t in items if t["status"] not in done]
        if pending and not any(not o[1]["blocked_by"] for _, order in views for o in order):
            errs.append({"code": "P8", "message": "所有视角都无可排任务（全部被前置阻塞）"})
        if as_json:
            print(json.dumps({"ok": not errs, "tasks": len(items),
                              "works": len(work_ids), "views": len(views), "errors": errs},
                             ensure_ascii=False, indent=2))
            return 1 if errs else 0
        print(f"tasks: {len(items)}  works: {len(work_ids)}  views: {len(views)}")
        for e in errs:
            print(f"  ERROR [{e['code']}] {e['message']}")
        print(f"errors={len(errs)}")
        return 1 if errs else 0

    if errs:
        for e in errs:
            print(f"  ERROR [{e['code']}] {e['message']}")
        print(f"errors={len(errs)}")
        return 1

    views = compute(weights, items, codes, done, work_ids, cfg)
    start = end = None
    for i, ln in enumerate(lines):
        if ln.strip() == BEGIN:
            start = i
        elif ln.strip() == END:
            end = i
    if start is None or end is None or end < start:
        return die("文档里找不到 BEGIN/END:plan-rank 生成区标记", as_json)

    block = render(views)
    if check_only:
        same = "\n".join(lines[start:end + 1]).strip() == block.strip()
        print("plan-rank up-to-date" if same else "plan-rank OUT OF DATE")
        return 0 if same else 1

    lines[start:end + 1] = block.splitlines()
    write(path, "\n".join(lines) + "\n")
    print(f"plan-rank written: {len(views)} views, {len(items)} tasks")
    return 0


if __name__ == "__main__":
    sys.exit(main())
