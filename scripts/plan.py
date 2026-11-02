#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""开发计划的排序与校验。

用法：
    python scripts/plan.py index            # 重算各视角排序视图，写回文档生成区
    python scripts/plan.py index --check    # 只比对，不写（CI / 收尾用）
    python scripts/plan.py check [--json]   # 结构校验（含任务与功能的双亲、考核）

维度与视角全部从表头读取，脚本不认识具体维度名 —— 加维度/加视角不改代码。
编号规则、状态词、文件位置来自 <docs>/_schema.json。

P14–P16 要读功能台账（`40-运行/FEATURES.md`）：任务挂的功能必须存在、已完成的任务
必须有任务考核、已验收的功能必须由任务支撑。P18 要读方向卡（`00-门面/方向卡.md`）：
方向必须有现状、成功状态与走通验收。P19 要读设计卡（`00-门面/设计卡.md`）：还没做完
的工作要有卡，卡里接口、可替换点、失败边界不能空。判定靠表头，不靠列序。
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
        "design_before_states": ["待开工", "进行中"],
    },
}

BEGIN = "<!-- BEGIN:plan-rank -->"
END = "<!-- END:plan-rank -->"

# 任务挂的功能必须是这个形态；「—（历史）」只留给先于双亲模型的存量任务。
FEATURE_ID_RE = re.compile(r"^F-\d+$")
TASK_ID_RE = re.compile(r"^T\d+\.\d+\.\d+$")
LEGACY = "—（历史）"
# 考核一行里这些写法等于没写（与 doc_check 的 REF_PLACEHOLDERS 同口径）。
# 注意「待提交」不在集合里：编码与校验必须发生在提交之前，commit 短号是提交后回写的。
PLACEHOLDERS = {"", "-", "—", "–", "无", "待补", "待填", "待定", "tbd", "todo"}
ASSESS_CELLS = ("做法", "一致", "代价", "结论")
# 方向卡的三格必填（P18）。路径与接缝不判：步数靠人读，接缝按 ADR-003 的已知缺口不做机器判。
CARD_CELLS = ("现状", "成功状态", "走通验收")
# 设计卡的三格必填（P19）。扩展点 / 任务拆分 / 取舍按改动大小可省：ADR-003 允许小改动只写
# 三行，判满六格会把设计门变成填表仪式。
DESIGN_CELLS = ("接口", "可替换点", "失败边界")
CARD_HEAD_RE = re.compile(r"^#{2,3}\s*(K\d+)\s*·\s*(W\d+\.\d+)\s*·?\s*(.*)$")
CARD_FIELD_RE = re.compile(r"^[-*]\s*\*\*(.+?)\*\*\s*[：:]\s*(.*)$")


def blank(v):
    """单元格是不是「没写」：占位词，或整格被（）包住的模板提示。"""
    v = (v or "").strip()
    return v in PLACEHOLDERS or (v.startswith("（") and v.endswith("）"))


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


# ---------------------------------------------------------------- 功能台账（P14–P16）
def features_path(docs, schema):
    """功能台账的位置：操作层目录 + `names.features`（缺省 FEATURES.md）。"""
    d = layer_dir(schema, "operation")
    name = (schema.get("names") or {}).get("features", "FEATURES.md")
    if not d:
        return None
    p = os.path.join(docs, d, name)
    return p if os.path.exists(p) else None


def load_features(path):
    """读功能台账：功能行的状态 / 是否历史 / 考核汇总，以及「任务考核」表的行。

    只按表头取列；合规判定不在这里（E24 / E27 在 doc_check）。这里只提供 P14–P16
    需要的三个事实：有哪些功能、每个功能的状态与汇总、每个任务有没有考核行。
    台账缺失时返回 None —— 调用方必须把它变成一条报错，不能当成「没有功能」跳过去。
    """
    if not path or not os.path.exists(path):
        return None
    feats, assess = {}, {}
    has_feature_table = has_assess_table = False
    for header, rows, _ in read_tables(read(path).splitlines()):
        heads = [strip_md(h) for h in header]
        if {"ID", "功能", "满足的需求", "状态"} <= set(heads):
            has_feature_table = True
            i_id = heads.index("ID")
            i_req = heads.index("满足的需求")
            i_st = heads.index("状态")
            i_sum = next((i for i, h in enumerate(heads) if h.startswith("考核")), None)
            for r in rows:
                if len(r) != len(heads):
                    continue
                fid = strip_md(r[i_id])
                if not FEATURE_ID_RE.fullmatch(fid):
                    continue
                feats[fid] = {
                    "legacy": strip_md(r[i_req]) in LEGACY,
                    "state": strip_md(r[i_st]),
                    "summary": strip_md(r[i_sum]) if i_sum is not None else "",
                }
        elif {"任务", "做法", "一致", "代价", "结论"} <= set(heads):
            has_assess_table = True
            i_t = heads.index("任务")
            for r in rows:
                if len(r) != len(heads):
                    continue
                tid = strip_md(r[i_t])
                if not TASK_ID_RE.fullmatch(tid):
                    continue
                assess[tid] = {h: strip_md(r[heads.index(h)])
                               for h in ASSESS_CELLS + ("完成于",) if h in heads}
    if not has_feature_table:
        return None
    return {"feats": feats, "assess": assess,
            "has_assess": has_assess_table}


# ---------------------------------------------------------------- 方向卡（P18）
def directions_path(docs, schema):
    """方向卡的位置：门面层目录 + `names.direction_card`（缺省 方向卡.md）。"""
    d = layer_dir(schema, "facade")
    name = (schema.get("names") or {}).get("direction_card", "方向卡.md")
    if not d:
        return None
    p = os.path.join(docs, d, name)
    return p if os.path.exists(p) else None


def load_directions(path):
    """读方向卡：`{D-n: {现状, 成功状态, 走通验收}}`，卡缺失或表头改坏返回 None。

    卡是方向的唯一载体；计划 §3 只登记编号与依据。返回 None 必须变成一条 P18——
    把它当成「没有方向」跳过去，方向就退化成一句口号而没人发现。
    """
    if not path or not os.path.exists(path):
        return None
    for header, rows, _ in read_tables(read(path).splitlines()):
        heads = [strip_md(h) for h in header]
        if not {"方向", "现状", "成功状态", "走通验收"} <= set(heads):
            continue
        out = {}
        i_d = heads.index("方向")
        for r in rows:
            if len(r) != len(heads):
                continue
            did = strip_md(r[i_d])
            if not re.fullmatch(r"D\d+", did):
                continue
            out[did] = {h: strip_md(r[heads.index(h)]) for h in CARD_CELLS if h in heads}
        return out
    return None


# ---------------------------------------------------------------- 设计卡（P19）
def designs_path(docs, schema):
    """设计卡的位置：门面层目录 + `names.design_card`（缺省 设计卡.md）。

    与方向卡同层：两者都是「计划怎么来的」——方向回答往哪走，设计回答这一块以后怎么换。
    技术设计（10-架构）写系统为何这样搭，设计卡随工作产生、随工作归档，不混在一处。
    """
    d = layer_dir(schema, "facade")
    name = (schema.get("names") or {}).get("design_card", "设计卡.md")
    if not d:
        return None
    p = os.path.join(docs, d, name)
    return p if os.path.exists(p) else None


def load_designs(path):
    """读设计卡：`{K1: {"work": W1.1, "cells": {接口: …}}}`，卡缺失返回 None。

    卡按小节写（`## K1 · W1.1 · 标题` 下挂 `- **接口**：…`），不按表格：设计卡按改动
    大小伸缩，小改动只写三行，表格会把接口压成一格。返回 None 必须变成一条 P19——
    当成「还没有设计」跳过去，设计门就退化成一句口号。
    """
    if not path or not os.path.exists(path):
        return None
    cards, cur = {}, None
    for ln in read(path).splitlines():
        m = CARD_HEAD_RE.match(ln.strip())
        if m:
            cur = {"work": m.group(2), "title": m.group(3).strip(), "cells": {}}
            cards[m.group(1)] = cur
            continue
        if ln.startswith("#"):
            cur = None
            continue
        if cur is None:
            continue
        f = CARD_FIELD_RE.match(ln.strip())
        if f:
            cur["cells"][f.group(1).strip()] = strip_md(f.group(2))
    return cards


# ---------------------------------------------------------------- 校验
def validate(weights, tasks, works, dirs, cfg, fragments=(), feats=None, cards=None,
             designs=None):
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

    # P18 方向卡：方向不能只是一句「成功状态 + 依据」——它是现状的结论，还要说清怎么算走通。
    # 卡缺失时不逐行刷屏，只报一条（否则一个没迁移的项目会红一片，看不出真正的毛病）。
    if dir_ids:
        if cards is None:
            E("P18", "找不到方向卡（00-门面/方向卡.md）：方向的现状 / 成功状态 / "
                     "走通验收无处可查；先按模板建卡，再往计划里加 D")
        else:
            for did in sorted(dir_ids):
                card = cards.get(did)
                if card is None:
                    E("P18", f"{did} 在计划 §3 里，但方向卡里没有它：现状、路径、接缝、"
                             f"走通验收都要写进卡")
                    continue
                miss = [c for c in CARD_CELLS if blank(card.get(c))]
                if miss:
                    E("P18", f"方向卡 {did} 缺{'、'.join(miss)}：方向是现状的结论，"
                             f"缺了这一格就只剩一句口号")
            for did in sorted(set(cards) - dir_ids):
                E("P18", f"方向卡里的 {did} 不在计划 §3：孤儿方向——要么补进计划，要么删掉卡")

    # P19 设计卡：设计是工作与任务之间的一步。还没做完的工作必须有卡，卡里至少写满
    # 接口 / 可替换点 / 失败边界；已经做完的工作不追溯（与 P18 的存量策略一致）。
    # 卡缺失只报一条，不逐行刷屏——否则一个没建卡的项目会红一片，看不出真正的毛病。
    need = []
    ws_header, ws_rows = works if works else ([], [])
    for row in ws_rows:
        if len(row) != len(ws_header):
            continue
        wid = strip_md(row[0])
        st = row[ws_header.index("状态")] if "状态" in ws_header else ""
        if st in cfg.get("design_before_states", ["待开工", "进行中"]):
            need.append(wid)
    if need:
        if designs is None:
            E("P19", "找不到设计卡（00-门面/设计卡.md）：接口 / 可替换点 / 失败边界无处可查；"
                     "先按模板建卡（一个工作一张），再拆任务")
        else:
            by_work = {}
            for kid, card in designs.items():
                by_work.setdefault(card["work"], []).append(kid)
            for wid in need:
                kids = by_work.get(wid)
                if not kids:
                    E("P19", f"{wid} 还没做完却没有设计卡：先写接口 / 可替换点 / 失败边界，"
                             f"再拆任务（设计没定不拆任务）")
                    continue
                if len(kids) > 1:
                    E("P19", f"{wid} 有 {len(kids)} 张设计卡（{'、'.join(sorted(kids))}）："
                             f"一个工作只留一张，否则设计有两份真相")
                for kid in sorted(kids):
                    miss = [c for c in DESIGN_CELLS if blank(designs[kid]["cells"].get(c))]
                    if miss:
                        E("P19", f"设计卡 {kid}（{wid}）缺{'、'.join(miss)}：三格写满才算设计定稿"
                                 f"（确实没有可替换点的，写「无」并说明为什么——只写「无」按空算）")
            for wid in sorted(set(by_work) - work_ids):
                E("P19", f"设计卡里的 {wid} 不在计划 §4：孤儿卡——要么补工作行，要么删掉卡")

    all_task_ids = {r[idx["ID"]] for r in t_rows if len(r) == len(t_header)}
    # P14 的前半：没有这一列，双亲就只剩一半（任务只挂工作）。台账缺失也不能当成
    # 「没有功能」静默跳过——那会让三个码同时沉默，变成 errors=0 的假通过。
    i_fe = idx.get("功能")
    i_acc = next((i for i, h in enumerate(t_header) if h.startswith("验收")), None)
    if i_fe is None:
        E("P14", "任务表缺「功能」列：每个任务要同时挂一个功能（F-nnn）与一个工作")
    elif feats is None:
        E("P14", "找不到功能台账（40-运行/FEATURES.md）：任务挂的功能无从核对；"
                 "先按模板建功能行，再拆任务")
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
        # P14 双亲：功能必须是存在的 F-nnn；「—（历史）」只对已完成任务开放
        fcell = r[i_fe] if i_fe is not None else ""
        if i_fe is not None:
            if fcell in LEGACY:
                if status not in done:
                    E("P14", f"{tid} 还没完成却把「功能」写成 —（历史）："
                             f"新任务必须挂真实的 F-nnn，历史豁免只对存量已完成任务")
            elif not FEATURE_ID_RE.fullmatch(fcell):
                E("P14", f"{tid} 的「功能」不是 F-nnn：{fcell!r}"
                         f"（每条任务同时挂一个功能与一个工作）")
            elif feats is not None and fcell not in feats["feats"]:
                E("P14", f"{tid} 挂的功能不存在：{fcell}（先在 FEATURES 立功能行，再拆任务）")
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
                      "feature": fcell, "accept": r[i_acc] if i_acc is not None else "",
                      "status": status, "pre": pre, "scores": scores})

    # ---- P15 考核下沉：已完成的任务要有验收与任务考核（四格 + 完成于）。
    # 判在任务级、不判在功能级，是因为「一场会话做完了」只有任务说得清；功能一大会
    # 变成整块总结，写不出代价估错没有（ADR-003 §2）。
    if feats is not None and i_fe is not None:
        if not feats["has_assess"]:
            E("P15", "找不到「任务考核」表：已完成的任务要各占一行（做法 / 一致 / 代价 / 结论 / 完成于）")
        else:
            for it in items:
                if it["status"] not in done:
                    continue
                if blank(it["accept"]):
                    E("P15", f"{it['id']} 已完成却缺「验收」：写一条命令或一次实测，"
                             f"否则没人能判断它是不是真做完了")
                row = feats["assess"].get(it["id"])
                if row is None:
                    E("P15", f"{it['id']} 已完成但「任务考核」表里没有它："
                             f"补一行 做法 / 一致 / 代价 / 结论 + 完成于")
                    continue
                miss = [c for c in ASSESS_CELLS if blank(row.get(c))]
                if miss:
                    E("P15", f"{it['id']} 的任务考核缺槽位：{'、'.join(miss)}"
                             f"（四格要同时写满，否则考核退化成一句话总结）")
                if blank(row.get("完成于")):
                    E("P15", f"{it['id']} 的考核没记「完成于」：写该任务的 commit 短号，"
                             f"回滚到它之前就靠这个锚点")
            for tid in sorted(feats["assess"]):
                if tid not in all_task_ids:
                    E("P15", f"「任务考核」表里的 {tid} 不在计划 §5："
                             f"要么编号写错，要么任务被删了而考核行留着")

    # ---- P16 汇总可回溯：功能「已验收」必须由任务支撑，且汇总点名的任务要真挂在它下面。
    # 这一条专治「汇总写得很漂亮，但没人做过」——E27 只判格子填没填。
    if feats is not None:
        by_feature = {}
        for it in items:
            if FEATURE_ID_RE.fullmatch(it["feature"] or ""):
                by_feature.setdefault(it["feature"], []).append(it["id"])
        for fid, meta in sorted(feats["feats"].items()):
            if meta["state"] != "已验收" or meta["legacy"]:
                continue
            linked = by_feature.get(fid, [])
            if not linked:
                E("P16", f"{fid} 已验收但没有任何任务挂它：功能要先拆出任务（考核才有来源）；"
                         f"先于任务模型的存量功能请在「满足的需求」标 —（历史）")
            for t in re.findall(r"T\d+\.\d+\.\d+", meta["summary"]):
                if t not in all_task_ids:
                    E("P16", f"{fid} 的考核汇总点名了不存在的任务 {t}")
                elif t not in linked:
                    E("P16", f"{fid} 的考核汇总点名了 {t}，但那条任务的「功能」不是 {fid}"
                             f"（汇总不能拿别人家的任务给自己背书）")

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
    feats = load_features(features_path(docs, schema))
    cards = load_directions(directions_path(docs, schema))
    designs = load_designs(designs_path(docs, schema))
    errs, items, codes, done, work_ids = validate(weights, tasks, works, dirs, cfg,
                                                  fragments, feats, cards, designs)

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
