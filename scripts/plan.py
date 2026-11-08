#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""开发计划的排序与校验。

用法：
    python scripts/plan.py index            # 重算各视角排序视图，写回文档生成区
    python scripts/plan.py index --check    # 只比对，不写（CI / 收尾用）
    python scripts/plan.py check [--json]   # 结构校验（含任务与功能的双亲、考核）
    python scripts/plan.py next [--json]    # 唯一出口：按第一个视角给出「下一步」与理由链
    python scripts/plan.py tree [--html|--json]  # 只读全貌：方向 → 工作 → 任务
    python scripts/plan.py set-status T1.1.1 --to 已完成 --commit abc1234 \\
        --review "做法=…｜一致=…｜代价=…｜结论=…" [--dry-run]  # 状态转写（REQ-017）
    python scripts/plan.py new-feature --title "功能名" --req "WHEN … THE SYSTEM SHALL …" \\
        --accept "怎么判" --verify "`python scripts/self_test.py -v`（第 N 组）" \\
        --direction D1 --work "工作名" --task "任务名" --scores 3,4,3,3,5,4 --cost S \\
        --design-interface "…" --design-swappable "…" --design-failure "…" \\
        [--design-option "A|轴|假设|失败模式|选中|—"] [--work-id W1.1] \\
        [--dry-run]  # 五件套批量入口（REQ-031）

维度与视角全部从表头读取，脚本不认识具体维度名 —— 加维度/加视角不改代码。
编号规则、状态词、文件位置来自 <docs>/_schema.json。

P14–P16 要读功能台账（`40-运行/FEATURES.md`）：任务挂的功能必须存在、已完成的任务
必须有任务考核、已验收的功能必须由任务支撑。P18 要读方向卡（`00-门面/方向卡.md`）：
方向必须有现状、成功状态与走通验收。P19 要读设计卡（`00-门面/设计卡.md`）：还没做完
的工作要有卡，卡里接口、可替换点、失败边界不能空。P20 要读方向卡的「链路」表：
链路是系统视角的边，至少串起 2 个功能点，接缝与复核日不能空。判定靠表头，不靠列序。
"""
from __future__ import annotations

import datetime
import hashlib
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
# 「待提交」也按没记算（ISS-046）：它曾经是个合规的免死金牌，锚点可以永远空着。
# 正确顺序是「先提交代码 → 回写完成于 → 再补一次 docs 提交」。
PLACEHOLDERS = {"", "-", "—", "–", "无", "待补", "待填", "待定", "tbd", "todo"}
ANCHOR_PLACEHOLDERS = PLACEHOLDERS | {"待提交"}
ASSESS_CELLS = ("做法", "一致", "代价", "结论")
# 方向卡的必填格（P18）。REQ-018：走通验收还要带 @复核日；路径 / 接缝 / 走通验收里
# 出现的 F- / W / K 引用必须存在——机器只判存在，走没走通、接缝归谁仍人读（ISS-061）。
CARD_CELLS = ("现状", "成功状态", "走通验收", "接缝")
# 链路行的必填格（P20，REQ-039 / REQ-040）。链路是「线之间」的边，所以门槛是
# 至少串起 2 个功能点，而不是跨 2 个方向——方向颗粒太粗，会漏掉同方向内跨组件的串联。
CHAIN_CELLS = ("起点", "终点", "涉及功能点", "关键接缝", "走通验收")
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

def cells(line):
    s = line.strip()
    if not s.startswith("|") or not s.endswith("|") or len(s) < 3:
        return None
    return split_row(s)


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
    return load_lines(read(path).splitlines())


def load_lines(lines):
    """按行解析计划。与 `load(path)` 同源——`set-status` 要先验「改完之后」的文本，
    不能靠写盘再读（那正是「写半截」的来源）。"""
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
    return parse_features(read(path).splitlines())


def parse_features(lines):
    """按行解析功能台账（`load_features` 的同一份逻辑，供「改完之后」的文本复用）。"""
    feats, assess = {}, {}
    has_feature_table = has_assess_table = False
    for header, rows, _ in read_tables(lines):
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
            out[did] = {h: strip_md(r[heads.index(h)]) for h in heads}
        return out
    return None


def load_chains(path):
    """读方向卡「链路」表：`{L-n: {起点, 终点, 涉及功能点, 关键接缝, 走通验收, 最近走通, 结论, 证据}}`。

    链路是系统视角的「边」：全局视角回答「每步走过没有」，链路回答「线之间串起来没有」。
    缺表返回 None —— 不报错（与覆盖表同档：表还没建的项目不该红一片）。
    """
    if not path or not os.path.exists(path):
        return None
    for header, rows, _ in read_tables(read(path).splitlines()):
        heads = [strip_md(h) for h in header]
        if not {"链路", "起点", "终点", "涉及功能点", "关键接缝", "走通验收"} <= set(heads):
            continue
        out = {}
        for r in rows:
            if len(r) != len(heads):
                continue
            lid = strip_md(r[heads.index("链路")])
            if not lid:
                continue
            out[lid] = {h: strip_md(c) for h, c in zip(heads, r)}
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
    return parse_designs(read(path).splitlines())


def parse_designs(lines):
    """`load_designs` 的同一份解析，供「改完之后」的文本复用（不靠写盘再读）。"""
    cards, cur = {}, None
    for ln in lines:
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
             designs=None, chains=None):
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
    # REQ-018 / ISS-061：机器判形式（复核日 / 引用存在 / 接缝非空），语义仍人读。
    if dir_ids:
        if cards is None:
            E("P18", "找不到方向卡（00-门面/方向卡.md）：方向的现状 / 成功状态 / "
                     "走通验收无处可查；先按模板建卡，再往计划里加 D")
        else:
            feat_ids = set(feats["feats"]) if feats else set()
            design_ids = set(designs) if designs else set()
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
                    continue
                if not re.search(r"@\d{4}-\d{2}-\d{2}", card.get("走通验收", "")):
                    E("P18", f"方向卡 {did} 的走通验收缺复核日期（@YYYY-MM-DD）："
                             f"到期提醒无从触发（REQ-018 / ISS-061）")
                for cell, text in card.items():
                    if cell not in ("接缝", "走通验收") and not cell.startswith("路径"):
                        continue
                    for ref in sorted(set(re.findall(r"F-\d+", text))):
                        if ref not in feat_ids:
                            E("P18", f"方向卡 {did} 的{cell}引用了不存在的功能 {ref}："
                                     f"引用存在才能说清「每步靠哪个功能」（REQ-018 / ISS-061）")
                    for ref in sorted(set(re.findall(r"W\d+\.\d+", text))):
                        if ref not in work_ids:
                            E("P18", f"方向卡 {did} 的{cell}引用了不存在的工作 {ref}")
                    for ref in sorted(set(re.findall(r"K\d+", text))):
                        if ref not in design_ids:
                            E("P18", f"方向卡 {did} 的{cell}引用了不存在的设计卡 {ref}")
            for did in sorted(set(cards) - dir_ids):
                E("P18", f"方向卡里的 {did} 不在计划 §3：孤儿方向——要么补进计划，要么删掉卡")

    # P20 链路（REQ-040）：系统视角的边——哪些环节串起来、接缝在哪、验过没有。
    # 只判形式：串起 ≥2 个功能点、五格非空、走通验收带复核日、引用存在；
    # 走没走通、接缝归谁仍人读（ADR-006）。缺表不报错（覆盖 / 链路都是加分项）。
    if chains:
        feat_ids = set(feats["feats"]) if feats else set()
        design_ids = set(designs) if designs else set()
        for lid in sorted(chains):
            ch = chains[lid]
            if not re.fullmatch(r"L\d+", lid):
                E("P20", f"链路编号不合规：{lid}（应形如 L1）")
                continue
            frefs = sorted(set(re.findall(r"F-\d+", ch.get("涉及功能点", ""))))
            if len(frefs) < 2:
                E("P20", f"链路 {lid} 只涉及 {len(frefs)} 个功能点：链路是「线之间」的串联，"
                         f"至少串起 2 个 F（REQ-039）")
            for ref in frefs:
                if ref not in feat_ids:
                    E("P20", f"链路 {lid} 的涉及功能点引用了不存在的功能 {ref}")
            miss = [c for c in CHAIN_CELLS if blank(ch.get(c))]
            if miss:
                E("P20", f"链路 {lid} 缺{'、'.join(miss)}：缺了这一格就说不清接缝在哪、怎么算走过")
                continue
            if not re.search(r"@\d{4}-\d{2}-\d{2}", ch.get("走通验收", "")):
                E("P20", f"链路 {lid} 的走通验收缺复核日期（@YYYY-MM-DD）：到期提醒无从触发（REQ-040）")
            walked = (ch.get("最近走通") or "").strip()
            if walked and not walked.startswith(("—", "-")):
                for c in ("结论", "证据"):
                    if blank(ch.get(c)):
                        E("P20", f"链路 {lid} 记了走通日期却缺「{c}」：记录要能被复核（REQ-040）")
            for cell in ("关键接缝", "走通验收", "证据"):
                text = ch.get(cell, "")
                for ref in sorted(set(re.findall(r"W\d+\.\d+", text))):
                    if ref not in work_ids:
                        E("P20", f"链路 {lid} 的{cell}引用了不存在的工作 {ref}")
                for ref in sorted(set(re.findall(r"K\d+", text))):
                    if ref not in design_ids:
                        E("P20", f"链路 {lid} 的{cell}引用了不存在的设计卡 {ref}")

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
                if (row.get("完成于") or "").strip() in ANCHOR_PLACEHOLDERS:
                    E("P15", f"{it['id']} 的考核没记「完成于」：写该任务的 commit 短号，"
                             f"回滚到它之前就靠这个锚点（「待提交」不算记）")
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


# ---------------------------------------------------------------- 树视图（D → W → T）
def tree_build(dirs, works, items, feats):
    """把三层拼成树：方向 → 工作 → 任务。孤儿（方向不存在 / 工作不存在）单独收尾。

    只读视图：不改任何文档，也不替 `check` 判合规——它回答的是「现在长什么样」，
    合规由 `plan.py check` 判。
    """
    d_order, d_name = [], {}
    if dirs:
        for r in dirs[1]:
            if not r:
                continue
            d_order.append(r[0])
            d_name[r[0]] = r[1] if len(r) > 1 else ""
    w_rows, w_by_d = {}, {d: [] for d in d_order}
    if works:
        h = works[0]
        for r in works[1]:
            if not r or len(r) != len(h):
                continue
            wid = r[0]
            did = r[h.index("方向")] if "方向" in h else ""
            w_rows[wid] = {"name": r[h.index("工作")] if "工作" in h else "",
                           "state": r[h.index("状态")] if "状态" in h else "",
                           "dir": did}
            w_by_d.setdefault(did, []).append(wid)
    t_by_w = {}
    for it in items:
        t_by_w.setdefault(it["work"], []).append(it)
    return d_order, d_name, w_rows, w_by_d, t_by_w


def tree_tail(it, assess):
    """任务行的尾巴：功能 · 状态 · 完成于。"""
    tail = f"{it['feature']} · {it['status']}"
    anchor = (assess.get(it["id"]) or {}).get("完成于", "")
    if anchor and anchor not in ("—", "-"):
        tail += f" · {anchor}"
    return tail


def tree_text(d_order, d_name, w_rows, w_by_d, t_by_w, items, assess):
    out = [f"方向 → 工作 → 任务：{len(d_order)} 方向 · {len(w_rows)} 工作 · {len(items)} 任务"]

    def block(prefix, kids):
        for i, (label, render) in enumerate(kids):
            last = i == len(kids) - 1
            out.append(prefix + ("└─ " if last else "├─ ") + label)
            render(prefix + ("   " if last else "│  "))

    def task_kid(it):
        return (f"{it['id']}  {it['name']}   [{tree_tail(it, assess)}]", lambda _p: None)

    for did in d_order:
        wids = w_by_d.get(did, [])
        ts = [t for wid in wids for t in t_by_w.get(wid, [])]
        done_n = sum(1 for t in ts if t["status"] == "已完成")
        out.append("")
        out.append(f"{did}  {d_name[did]}   ({len(wids)} 工作 · {len(ts)} 任务 · 完成 {done_n})")
        kids = []
        for wid in wids:
            w = w_rows[wid]
            inner = [task_kid(t) for t in t_by_w.get(wid, [])]

            def render_inner(p, inner=inner):
                for j, (label, _) in enumerate(inner):
                    out.append(p + ("└─ " if j == len(inner) - 1 else "├─ ") + label)

            kids.append((f"{wid}  {w['name']}   [{w['state']}]", render_inner))
        block("", kids)

    orphans_w = [w for w in w_rows if w_rows[w]["dir"] not in d_order]
    orphans_t = [it for it in items if it["work"] not in w_rows]
    if orphans_w or orphans_t:
        out.append("")
        out.append("未挂：")
        for wid in orphans_w:
            out.append(f"├─ {wid}  {w_rows[wid]['name']}   方向 {w_rows[wid]['dir'] or '空'}")
            for t in t_by_w.get(wid, []):
                out.append(f"│  └─ {t['id']}  {t['name']}   [{tree_tail(t, assess)}]")
        for it in orphans_t:
            out.append(f"└─ {it['id']}  {it['name']}   工作 {it['work'] or '空'}")
    return "\n".join(out)


def tree_html(d_order, d_name, w_rows, w_by_d, t_by_w, items, assess, date):
    """单文件 HTML：不引外部资源、不连网、不跑脚本；只为「人在浏览器里看一眼」。"""
    import html as _h
    e = lambda s: _h.escape(str(s or ""), quote=True)
    chip = lambda s: f'<span class="chip">{e(s)}</span>'
    chunks = []
    for did in d_order:
        wids = w_by_d.get(did, [])
        ts = [t for wid in wids for t in t_by_w.get(wid, [])]
        done_n = sum(1 for t in ts if t["status"] == "已完成")
        rows = []
        for wid in wids:
            w = w_rows[wid]
            tasks = "".join(
                f'<li><span class="tid">{e(t["id"])}</span> <span class="tname">{e(t["name"])}</span> '
                f'{chip(t["feature"])} {chip(t["status"])} '
                f'<code>{e((assess.get(t["id"]) or {}).get("完成于", "") or "")}</code></li>'
                for t in t_by_w.get(wid, []))
            rows.append(f'<div class="work"><div class="wh"><span class="wid">{e(wid)}</span> '
                        f'<span class="wname">{e(w["name"])}</span> {chip(w["state"])}</div>'
                        f'<ul class="tasks">{tasks}</ul></div>')
        chunks.append(
            f'<section><h2><span class="did">{e(did)}</span> {e(d_name[did])}'
            f'<span class="meta">{len(wids)} 工作 · {len(ts)} 任务 · 完成 {done_n}</span></h2>'
            + "".join(rows) + "</section>")
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>开发计划：方向 → 工作 → 任务</title>
<style>
:root{{--fg:#1f2328;--muted:#656d76;--line:#d0d7de;--bg:#fff;--soft:#f6f8fa;--accent:#0969da}}
*{{box-sizing:border-box}}
body{{margin:0;padding:32px 24px 64px;background:var(--bg);color:var(--fg);
font:15px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei",sans-serif}}
main{{max-width:1040px;margin:0 auto}}
h1{{font-size:22px;margin:0 0 4px}}
.sub{{color:var(--muted);font-size:13px;margin-bottom:24px}}
section{{border:1px solid var(--line);border-radius:8px;padding:16px 18px;margin:0 0 16px;background:var(--bg)}}
h2{{font-size:16px;margin:0 0 12px;display:flex;align-items:baseline;gap:8px}}
.did,.wid,.tid{{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-weight:600}}
.did{{color:var(--accent)}}
.meta{{margin-left:auto;color:var(--muted);font-size:12px;font-weight:400}}
.work{{border-left:2px solid var(--line);padding:6px 0 6px 12px;margin:8px 0}}
.wh{{font-size:14px}}
.wid{{color:var(--muted);margin-right:4px}}
ul.tasks{{list-style:none;margin:6px 0 0;padding:0}}
ul.tasks li{{padding:2px 0;font-size:14px;color:var(--fg)}}
ul.tasks li .tname{{margin-right:6px}}
.tid{{color:var(--muted);font-size:13px;margin-right:4px}}
.chip{{display:inline-block;border:1px solid var(--line);border-radius:10px;padding:0 7px;
font-size:12px;color:var(--muted);background:var(--soft);margin-right:4px;white-space:nowrap}}
code{{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:12px;color:var(--muted)}}
footer{{color:var(--muted);font-size:12px;border-top:1px solid var(--line);padding-top:12px;margin-top:24px}}
</style></head><body><main>
<h1>开发计划：方向 → 工作 → 任务</h1>
<div class="sub">{len(d_order)} 方向 · {len(w_rows)} 工作 · {len(items)} 任务 · 生成于 {e(date)}</div>
{''.join(chunks)}
<footer>本文件由 <code>python scripts/plan.py tree --html</code> 生成，不参与校验，<strong>不要手改</strong>；
数据改 <code>docs/</code> 下的计划与台账，改完重跑命令。</footer>
</main></body></html>
"""


# ---------------------------------------------------------------- set-status（REQ-017）
# 只做「把已由人裁决的状态写进既有载体」的转写：不推断证据、不新增载体、
# 任一校验失败一个字节都不写。判定读的是**改完之后**的文本，不是写盘再读——
# 写盘再读正是 ISS-036 记的「改了一半、文件被重写」那条路。
def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def write_atomic(path, text):
    """写临时文件再 replace：中途失败不会留下半截文件。"""
    tmp = path + ".set-status.tmp"
    try:
        with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def table_windows(lines):
    """[(header, header_line, [(line_idx, cells)])] —— 原始单元格，供原地改写用。"""
    out = []
    i, n = 0, len(lines)
    while i < n:
        header = cells(lines[i])
        if header is None:
            i += 1
            continue
        j = i + 1
        if j < n:
            sc = cells(lines[j])
            if sc is not None and is_sep(sc):
                j += 1
        rows = []
        while j < n:
            rc = cells(lines[j])
            if rc is None:
                break
            if not is_sep(rc):
                rows.append((j, rc))
            j += 1
        out.append((header, i, rows))
        i = j
    return out


def join_row(cs):
    return "| " + " | ".join(cs) + " |"


def parse_set_status(argv):
    opts = {"task": "", "to": "", "commit": "", "review": "", "dry": False}
    i = 0
    args = [a for a in argv if a != "set-status"]
    while i < len(args):
        a = args[i]
        if a in ("--to", "--commit", "--review") and i + 1 < len(args):
            opts[a[2:]] = args[i + 1]
            i += 2
            continue
        if a == "--dry-run":
            opts["dry"] = True
        elif not a.startswith("--") and not opts["task"]:
            opts["task"] = a
        i += 1
    return opts


def parse_review(text):
    """`做法=…｜一致=…｜代价=…｜结论=…` → dict；半角竖线也认。"""
    out = {}
    for part in re.split(r"[｜|]", text or ""):
        if "=" in part:
            k, v = part.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def cmd_set_status(docs, schema, plan_path, argv, as_json):
    opts = parse_set_status(argv)
    tid, to = opts["task"].strip(), opts["to"].strip()
    if not tid or not to:
        return die("用法：plan.py set-status <T-id> --to <状态> [--commit <短号>] "
                   "[--review \"做法=…｜一致=…｜代价=…｜结论=…\"] [--dry-run]", as_json, 2)
    cfg = schema["plan"]
    if to not in cfg["states"]:
        return die(f"目标状态不在白名单：{to!r}（允许：{'、'.join(cfg['states'])}）",
                   as_json, 1)
    done = set(cfg["done_states"])
    review = parse_review(opts["review"])
    commit = (opts["commit"] or "").strip()
    if to in done:
        miss = [c for c in ASSESS_CELLS
                if not review.get(c) or review.get(c) in ANCHOR_PLACEHOLDERS]
        if miss:
            return die(f"目标状态是「{to}」，但考核四格缺：{'、'.join(miss)}"
                       f"（一条命令写全，才不必事后再手工补 FEATURES）", as_json, 1)
        if commit in ANCHOR_PLACEHOLDERS:
            return die(f"目标状态是「{to}」，但没给可用的 `完成于` 锚点："
                       f"写 commit 短号；「待提交」不算记（ISS-046）", as_json, 1)
        for c in ASSESS_CELLS:
            if "|" in review[c]:
                return die(f"考核格「{c}」里有竖线，会撑破表格：改写成「A / B」", as_json, 1)

    feats_path = features_path(docs, schema)
    if feats_path is None:
        return die("找不到功能台账（FEATURES.md）：任务考核无处落", as_json, 1)
    plan_text, feats_text = read(plan_path), read(feats_path)
    before_hash = {plan_path: sha256_of(plan_path), feats_path: sha256_of(feats_path)}
    cards = load_directions(directions_path(docs, schema))
    designs = load_designs(designs_path(docs, schema))

    # ---- 在计划 §5 里定位任务行
    lines = plan_text.splitlines()
    task_hit = None
    for header, _, rows in table_windows(lines):
        h = [strip_md(x) for x in header]
        if h and h[0] == "ID" and "任务" in h and "状态" in h:
            for idx, cs in rows:
                if strip_md(cs[0]) == tid:
                    task_hit = (h, idx, cs)
                    break
        if task_hit:
            break
    if task_hit is None:
        return die(f"计划 §5 里没有任务 {tid}：编号写错？先确认它在任务表里", as_json, 1)
    h, idx, cs = task_hit
    old = strip_md(cs[h.index("状态")])
    cs_new = list(cs)
    cs_new[h.index("状态")] = to
    lines[idx] = join_row(cs_new)

    # ---- 在 FEATURES「任务考核」里定位 / 插入考核行
    flines = feats_text.splitlines()
    changes = [{"file": os.path.relpath(plan_path), "table": "任务表", "row": tid,
                "field": "状态", "old": old, "new": to}]
    if to in done:
        assess_hit, insert_at, a_header = None, None, None
        for a_h, a_hidx, rows in table_windows(flines):
            ah = [strip_md(x) for x in a_h]
            if {"任务", "做法", "一致", "代价", "结论"} <= set(ah):
                a_header = ah
                for aidx, acs in rows:
                    if strip_md(acs[0]) == tid:
                        assess_hit = (aidx, acs)
                        break
                if assess_hit is None:
                    insert_at = (rows[-1][0] + 1) if rows else (a_hidx + 2)
                break
        if a_header is None:
            return die("FEATURES 里找不到「任务考核」表：已完成的任务要各占一行", as_json, 1)
        vals = {c: review[c] for c in ASSESS_CELLS}
        vals["完成于"] = commit
        if assess_hit:
            aidx, acs = assess_hit
            acs_new = list(acs)
            for c in ASSESS_CELLS + ("完成于",):
                if c in a_header:
                    acs_new[a_header.index(c)] = vals[c]
            flines[aidx] = join_row(acs_new)
            changes.append({"file": os.path.relpath(feats_path), "table": "任务考核",
                            "row": tid, "field": "四格 + 完成于",
                            "old": "｜".join(f"{c}={strip_md(acs[a_header.index(c)])}"
                                             for c in ASSESS_CELLS + ("完成于",)
                                             if c in a_header),
                            "new": "｜".join(f"{c}={vals[c]}" for c in ASSESS_CELLS + ("完成于",)
                                             if c in a_header)})
        else:
            row = [vals.get(name, "—") for name in a_header]
            row[0] = f"**{tid}**"
            flines.insert(insert_at, join_row(row))
            changes.append({"file": os.path.relpath(feats_path), "table": "任务考核",
                            "row": tid, "field": "新增考核行",
                            "old": "（无）",
                            "new": "｜".join(f"{c}={vals[c]}" for c in ASSESS_CELLS + ("完成于",)
                                            if c in a_header)})

    new_plan = "\n".join(lines) + "\n"
    new_feats = "\n".join(flines) + "\n"
    if new_plan == plan_text and new_feats == feats_text:
        if as_json:
            print(json.dumps({"ok": True, "dry_run": opts["dry"], "written": False,
                              "changes": []}, ensure_ascii=False, indent=2))
        else:
            print(f"set-status：无改动（{tid} 已是「{to}」，考核行已一致）")
        return 0

    # ---- 先验「改完之后」的文本：只拒绝这次改动造成的错误，项目原有的债不拦转写
    try:
        l0, w0, t0, wo0, d0, fr0 = load_lines(plan_text.splitlines())
        errs0 = validate(w0, t0, wo0, d0, cfg, fr0,
                         parse_features(feats_text.splitlines()), cards, designs)[0]
        l2, w2, t2, wo2, d2, fr2 = load_lines(new_plan.splitlines())
        errs2 = validate(w2, t2, wo2, d2, cfg, fr2,
                         parse_features(new_feats.splitlines()), cards, designs)[0]
    except SystemExit as exc:
        return die(f"改完之后的文档解析失败（不落盘）：{exc}", as_json, 1)
    old_keys = {(e["code"], e["message"]) for e in errs0}
    fresh = [e for e in errs2 if (e["code"], e["message"]) not in old_keys]
    if fresh:
        return die("改完之后校验不过（不落盘）："
                   + "；".join(f"[{e['code']}] {e['message']}" for e in fresh), as_json, 1)

    if opts["dry"]:
        if as_json:
            print(json.dumps({"ok": True, "dry_run": True, "written": False,
                              "changes": changes}, ensure_ascii=False, indent=2))
        else:
            print("set-status（dry-run，不落盘）：")
            for c in changes:
                print(f"  {c['file']} · {c['table']} · {c['row']} · "
                      f"{c['field']}：{c['old']} → {c['new']}")
        return 0

    # ---- stale 守卫：读入到写入之间文件被改过，就一个字节都不写
    for p, h0 in before_hash.items():
        if not os.path.exists(p) or sha256_of(p) != h0:
            return die(f"{os.path.relpath(p)} 在读取后被改动过（stale）：不写，重跑一次",
                       as_json, 1)
    try:
        write_atomic(plan_path, new_plan)
    except OSError as exc:
        return die(f"写 {os.path.relpath(plan_path)} 失败，两个文件都没改：{exc}", as_json, 2)
    try:
        write_atomic(feats_path, new_feats)
    except OSError as exc:
        return die(f"已写 {os.path.relpath(plan_path)}，但写 "
                   f"{os.path.relpath(feats_path)} 失败：{exc}"
                   f"——先 git diff 核对，再重跑一次", as_json, 2)

    if as_json:
        print(json.dumps({"ok": True, "dry_run": False, "written": True,
                          "changes": changes}, ensure_ascii=False, indent=2))
    else:
        print(f"set-status：{tid} →「{to}」")
        for c in changes:
            print(f"  {c['file']} · {c['table']} · {c['row']} · "
                  f"{c['field']}：{c['old']} → {c['new']}")
    return 0


# ---------------------------------------------------------------- 五件套批量入口（REQ-031）
NEW_KEYS = ("title", "req", "accept", "verify", "direction", "work", "task",
            "scores", "cost", "design-interface", "design-swappable",
            "design-failure", "req-id", "feature-id", "work-id", "task-id",
            "card-id")
EARS_CUES = ("WHEN", "IF", "WHILE", "GIVEN", "SHALL", "当", "若", "一旦",
             "必须", "应", "不得", "不许")


def cell_esc(s):
    """单元格里的竖线会撑破表格（E28）：写成 `\\|`，与 split_row 同口径。"""
    return str(s).replace("|", "\\|").strip()


def as_code(s):
    s = (s or "").strip()
    return s if "`" in s else f"`{s}`"


def parse_new_feature(argv):
    opts = {k: "" for k in NEW_KEYS}
    opts["design-options"], opts["dry"] = [], False
    args = [a for a in argv if a != "new-feature"]
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--dry-run":
            opts["dry"] = True
            i += 1
            continue
        if a.startswith("--") and i + 1 < len(args):
            key = a[2:]
            if key == "design-option":
                opts["design-options"].append(args[i + 1])
            elif key in opts:
                opts[key] = args[i + 1]
            else:
                raise ValueError(f"未知参数：{a}")
            i += 2
            continue
        raise ValueError(f"无法识别的参数：{a}")
    return opts


def find_table(lines, pred):
    """按表头找人写的表：返回 (表头, 表头行号, [(行号, 单元格)])。"""
    for header, at, rows in table_windows(lines):
        heads = [strip_md(x) for x in header]
        if pred(heads):
            return heads, at, rows
    return None


def col_index(head, *names):
    for i, h in enumerate(head):
        for n in names:
            if h == n or h.startswith(n):
                return i
    return -1


def build_row(head, values):
    """按表头名填一格；缺列直接抛 ValueError（不静默错位）。"""
    row = ["—"] * len(head)
    for names, val in values:
        i = col_index(head, *names)
        if i < 0:
            raise ValueError(f"表头缺列：{' / '.join(names)}")
        row[i] = val
    return row


def inc_insert(rows, header_at):
    """表尾插入点：最后一行之后；空表插在表头与分隔行之后。"""
    return rows[-1][0] + 1 if rows else header_at + 2


def max_seq(text, pattern):
    best = 0
    for m in re.finditer(pattern, text, re.M):
        best = max(best, int(m.group(1)))
    return best


def max_row_seq(rows, pattern):
    """只认「首列就是编号」的行：正文里的反例（F-999）不能把下一个编号推成 F-1000。"""
    best = 0
    for _, cs in rows:
        m = re.fullmatch(pattern, strip_md(cs[0]))
        if m:
            best = max(best, int(m.group(1)))
    return best


def id_taken(text, ident):
    return re.search(rf"(?<![\w.]){re.escape(ident)}(?![\w.])", text) is not None


def card_block(card_id, work_id, title, interface, swappable, failure,
               options, task_id, task_name):
    out = ["", f"## {card_id} · {work_id} · {title}", "",
           f"- **接口**：{interface}",
           f"- **可替换点**：{swappable}"]
    if options:
        out += ["- **选项空间**：", "",
                "  | 选项 | 轴 | 假设 | 失败模式 | 结论 | 回到条件 |",
                "  |---|---|---|---|---|---|"]
        for o in options:
            parts = [p.strip() for p in o.split("|")]
            if len(parts) != 6:
                raise ValueError("--design-option 要 6 段（选项|轴|假设|失败模式|结论|回到条件）："
                                 f"{o!r}")
            out.append("  | " + " | ".join(parts) + " |")
    else:
        out.append("- **选项空间**：待补（还没过设计门；`W10` 只提醒不阻断）")
    out += [f"- **失败边界**：{failure}",
            f"- **任务拆分**：{task_id} {task_name}。", ""]
    return "\n".join(out)


def cmd_new_feature(docs, schema, plan_path, argv, as_json):
    try:
        opts = parse_new_feature(argv)
    except ValueError as exc:
        return die(f"new-feature 参数错误：{exc}", as_json, 2)

    title = opts["title"].strip()
    req_text = opts["req"].strip()
    accept = opts["accept"].strip()
    verify = opts["verify"].strip()
    direction = opts["direction"].strip()
    work_name = opts["work"].strip()
    task_name = opts["task"].strip()
    cost = opts["cost"].strip().upper()

    miss = [name for name, val in (("--title", title), ("--req", req_text),
                                   ("--accept", accept), ("--verify", verify),
                                   ("--direction", direction), ("--task", task_name),
                                   ("--scores", opts["scores"].strip()),
                                   ("--cost", cost)) if not val]
    if not opts["work-id"].strip() and not work_name:
        miss.append("--work")
    if miss:
        return die("new-feature 缺必填参数：" + "、".join(miss)
                   + "\n（五件套一次写全：需求句 / 验收 / verify / 方向 / 工作 / 任务 / 六维 / 代价）",
                   as_json, 1)
    if not any(c in req_text for c in EARS_CUES):
        return die("--req 不像 EARS 句式：至少出现 WHEN/IF/WHILE/SHALL/当/若/一旦/必须/应 之一",
                   as_json, 1)
    if not re.fullmatch(r"D\d+", direction):
        return die(f"--direction 形态不对：{direction!r}（应为 D1 这种）", as_json, 1)
    if cost not in ("S", "M", "L"):
        return die(f"--cost 只认 S / M / L：{cost!r}", as_json, 1)
    try:
        scores = [int(x) for x in re.split(r"[,，\s]+", opts["scores"].strip()) if x]
    except ValueError:
        return die("--scores 只能是 1–5 的整数，用逗号分隔", as_json, 1)
    if len(scores) != 6 or any(not 1 <= s <= 5 for s in scores):
        return die(f"--scores 要给 6 个 1–5 的整数（U,C,S,R,V,E）：收到 {scores}", as_json, 1)

    feats_path = features_path(docs, schema)
    if feats_path is None:
        return die("找不到功能台账（FEATURES.md）：五件套无处落", as_json, 1)
    cdir = layer_dir(schema, "contract")
    req_name = (schema.get("names") or {}).get("requirements", "requirements.md")
    req_path = os.path.join(docs, cdir or "", req_name)
    if not os.path.exists(req_path):
        return die(f"找不到需求清单：{os.path.relpath(req_path)}", as_json, 1)
    card_path = designs_path(docs, schema)
    if card_path is None:
        return die("找不到设计卡（00-门面/设计卡.md）：K 无处落", as_json, 1)

    plan_text, feats_text = read(plan_path), read(feats_path)
    req_all, card_text = read(req_path), read(card_path)
    before = {p: sha256_of(p) for p in (req_path, feats_path, plan_path, card_path)}
    lines, flines = plan_text.splitlines(), feats_text.splitlines()
    rlines, clines = req_all.splitlines(), card_text.splitlines()
    cards = load_directions(directions_path(docs, schema))
    designs = parse_designs(clines)

    dhit = find_table(lines, lambda h: bool(h) and h[0] == "编号" and "方向" in h)
    if dhit is None:
        return die("计划里找不到方向表（§3）", as_json, 1)
    if direction not in {strip_md(c[0]) for _, c in dhit[2]}:
        return die(f"方向 {direction} 不在计划 §3：先立方向卡再建五件套", as_json, 1)

    req_t = find_table(rlines, lambda h: "编号" in h and any(x.startswith("需求") for x in h))
    feat_t = find_table(flines, lambda h: {"ID", "功能", "满足的需求", "状态"} <= set(h))
    work_t = find_table(lines, lambda h: bool(h) and h[0] == "编号" and "工作" in h
                        and "方向" in h)
    task_t = find_table(lines, lambda h: bool(h) and h[0] == "ID" and "任务" in h
                        and "功能" in h)
    if not all((req_t, feat_t, work_t, task_t)):
        return die("五份文档表头不齐：需求表 / 功能表 / §4 工作表 / §5 任务表缺一", as_json, 1)

    dn = int(direction[1:])
    work_id = opts["work-id"].strip()
    w_ids = {strip_md(c[0]) for _, c in work_t[2]}
    existing_work = bool(work_id) and work_id in w_ids
    if work_id:
        m = re.fullmatch(r"W(\d+)\.(\d+)", work_id)
        if not m:
            return die(f"--work-id 形态不对：{work_id!r}（应为 W1.2 这种）", as_json, 1)
        if int(m.group(1)) != dn:
            return die(f"工作号 {work_id} 与方向 {direction} 不一致", as_json, 1)
        tn, tm = int(m.group(1)), int(m.group(2))
    else:
        wm = 0
        for _, c in work_t[2]:
            mm = re.fullmatch(r"W(\d+)\.(\d+)", strip_md(c[0]))
            if mm and int(mm.group(1)) == dn:
                wm = max(wm, int(mm.group(2)))
        work_id = f"W{dn}.{wm + 1}"
        tn, tm = dn, wm + 1

    task_id = opts["task-id"].strip()
    if task_id:
        if not re.fullmatch(rf"T{tn}\.{tm}\.\d+", task_id):
            return die(f"--task-id {task_id} 与工作 {work_id} 不一致", as_json, 1)
        if any(strip_md(c[0]) == task_id for _, c in task_t[2]):
            return die(f"任务 {task_id} 已存在（编号只增不复用）", as_json, 1)
    else:
        kmax = 0
        for _, c in task_t[2]:
            mm = re.fullmatch(rf"T{tn}\.{tm}\.(\d+)", strip_md(c[0]))
            if mm:
                kmax = max(kmax, int(mm.group(1)))
        task_id = f"T{tn}.{tm}.{kmax + 1}"

    req_id = opts["req-id"].strip()
    if req_id:
        if not re.fullmatch(r"REQ-\d{3}", req_id):
            return die(f"--req-id 形态不对：{req_id!r}（应为 REQ-001 这种）", as_json, 1)
        if id_taken(req_all, req_id):
            return die(f"需求 {req_id} 已存在（编号只增不复用）", as_json, 1)
    else:
        # 3.8 里 f-string 的表达式部分不能含反斜杠（PEP 701 是 3.12 才放开），
        # 所以正则先算出来再格式化；下面 feature_id / card_id 同理。
        req_seq = max_row_seq(req_t[2], r"REQ-(\d+)")
        req_id = f"REQ-{req_seq + 1:03d}"

    feature_id = opts["feature-id"].strip()
    if feature_id:
        if not re.fullmatch(r"F-\d{3}", feature_id):
            return die(f"--feature-id 形态不对：{feature_id!r}（应为 F-001 这种）", as_json, 1)
        if id_taken(feats_text, feature_id):
            return die(f"功能 {feature_id} 已存在（编号只增不复用）", as_json, 1)
    else:
        feat_seq = max_row_seq(feat_t[2], r"F-(\d+)")
        feature_id = f"F-{feat_seq + 1:03d}"

    card_id = opts["card-id"].strip()
    if existing_work:
        own = next((k for k, v in (designs or {}).items() if v["work"] == work_id), "")
        if not own:
            return die(f"工作 {work_id} 没有设计卡：先补卡再挂功能（P19）", as_json, 1)
        if card_id and card_id != own:
            return die(f"工作 {work_id} 的卡是 {own}，不是 {card_id}", as_json, 1)
        card_id = own
    elif card_id:
        if not re.fullmatch(r"K\d+", card_id):
            return die(f"--card-id 形态不对：{card_id!r}（应为 K1 这种）", as_json, 1)
        if re.search(rf"^##\s*{re.escape(card_id)}\b", card_text, re.M):
            return die(f"设计卡 {card_id} 已存在（编号只增不复用）", as_json, 1)
    else:
        card_seq = max_seq(card_text, r"^##\s*K(\d+)")
        card_id = f"K{card_seq + 1}"

    if not existing_work:
        lack = [n for n, v in (("--design-interface", opts["design-interface"].strip()),
                               ("--design-swappable", opts["design-swappable"].strip()),
                               ("--design-failure", opts["design-failure"].strip())) if not v]
        if lack:
            return die("新建工作要一张设计卡（P19 三格必填）：缺 " + "、".join(lack)
                       + "\n（只想挂已有工作：用 --work-id W1.1）", as_json, 1)

    try:
        req_row = build_row(req_t[0], [
            (("编号",), f"**{req_id}**"),
            (("需求",), cell_esc(req_text)),
            (("验收",), cell_esc(accept)),
            (("verify",), cell_esc(as_code(verify))),
            (("状态",), "待实现"),
            (("依据",), f"本会话、new-feature、{feature_id}、{task_id}"),
            (("确认",), "—"),
        ])
        feat_row = build_row(feat_t[0], [
            (("ID",), f"**{feature_id}**"),
            (("功能",), cell_esc(title)),
            (("满足的需求",), req_id),
            (("验收口径",), cell_esc(accept)),
            (("verify",), cell_esc(as_code(verify))),
            (("代价",), cost),
            (("状态",), "待评审"),
            (("评审",), "—"),
            (("代码入口",), "—"),
            (("证据",), "—"),
            (("考核汇总",), "—"),
            (("完成于",), "—"),
        ])
        work_row = build_row(work_t[0], [
            (("编号",), f"**{work_id}**"),
            (("工作",), cell_esc(work_name or title)),
            (("方向",), direction),
            (("状态",), "待开工"),
            (("验收判据", "验收"), cell_esc(accept)),
            (("证据",), "—"),
            (("关联",), f"{req_id}、{feature_id}、{card_id}"),
        ])
        task_row = build_row(task_t[0], [
            (("ID",), f"**{task_id}**"),
            (("任务",), cell_esc(task_name)),
            (("功能",), feature_id),
            (("所属",), work_id),
            (("状态",), "待开工"),
            (("前置",), "-"),
            (("验收",), cell_esc(as_code(verify))),
            (("关联",), f"{req_id}、{card_id}"),
        ])
        dims = dim_codes(task_t[0])
        if len(dims) != 6:
            return die(f"任务表应有 6 个维度列（U C S R V E），实际 {len(dims)} 个",
                       as_json, 1)
        for d, s in zip(dims, scores):
            task_row[task_t[0].index(d)] = str(s)
        block = "" if existing_work else card_block(
            card_id, work_id, title, opts["design-interface"].strip(),
            opts["design-swappable"].strip(), opts["design-failure"].strip(),
            opts["design-options"], task_id, task_name)
    except ValueError as exc:
        return die(str(exc), as_json, 1)

    new_rlines, new_flines, new_lines = list(rlines), list(flines), list(lines)
    new_rlines.insert(inc_insert(req_t[2], req_t[1]), join_row(req_row))
    f001 = next((idx for idx, c in feat_t[2] if strip_md(c[0]) == "F-001"), None)
    f_at = (f001 + 1) if f001 is not None else inc_insert(feat_t[2], feat_t[1])
    new_flines.insert(f_at, join_row(feat_row))
    # 先插 §5（行号大），再插 §4，避免先插 §4 把 §5 的行号推后
    new_lines.insert(inc_insert(task_t[2], task_t[1]), join_row(task_row))
    if not existing_work:
        new_lines.insert(inc_insert(work_t[2], work_t[1]), join_row(work_row))
    new_req = "\n".join(new_rlines) + "\n"
    new_feats = "\n".join(new_flines) + "\n"
    new_plan = "\n".join(new_lines) + "\n"
    if existing_work:
        new_card = card_text          # 挂已有工作：卡一个字节都不动
    else:
        new_card = card_text.rstrip("\n") + "\n" + block
        if not new_card.endswith("\n"):
            new_card += "\n"

    cfg = schema["plan"]
    try:
        l0, w0, t0, wo0, d0, fr0 = load_lines(lines)
        errs0 = validate(w0, t0, wo0, d0, cfg, fr0, parse_features(flines),
                         cards, designs)[0]
        l2, w2, t2, wo2, d2, fr2 = load_lines(new_lines)
        errs2 = validate(w2, t2, wo2, d2, cfg, fr2, parse_features(new_flines),
                         cards, parse_designs(new_card.splitlines()))[0]
    except SystemExit as exc:
        return die(f"改完之后的文档解析失败（不落盘）：{exc}", as_json, 1)
    old_keys = {(e["code"], e["message"]) for e in errs0}
    fresh = [e for e in errs2 if (e["code"], e["message"]) not in old_keys]
    if fresh:
        return die("改完之后校验不过（不落盘）："
                   + "；".join(f"[{e['code']}] {e['message']}" for e in fresh), as_json, 1)

    ids = {"req": req_id, "feature": feature_id, "work": work_id,
           "task": task_id, "card": card_id}
    changes = [{"file": os.path.relpath(req_path), "table": "需求", "row": req_id},
               {"file": os.path.relpath(feats_path), "table": "功能", "row": feature_id},
               {"file": os.path.relpath(plan_path), "table": "任务", "row": task_id}]
    if not existing_work:
        changes.append({"file": os.path.relpath(plan_path), "table": "工作", "row": work_id})
        changes.append({"file": os.path.relpath(card_path), "table": "设计卡", "row": card_id})

    if opts["dry"]:
        if as_json:
            print(json.dumps({"ok": True, "dry_run": True, "written": False,
                              "ids": ids, "changes": changes}, ensure_ascii=False, indent=2))
        else:
            print(f"new-feature（dry-run，不落盘）：{req_id} / {feature_id} / "
                  f"{work_id} / {task_id} / {card_id}")
            for c in changes:
                print(f"  {c['file']} · {c['table']} · +{c['row']}")
        return 0

    for p, h0 in before.items():
        if not os.path.exists(p) or sha256_of(p) != h0:
            return die(f"{os.path.relpath(p)} 在读取后被改动过（stale）：不写，重跑一次",
                       as_json, 1)
    writes = [(req_path, new_req), (feats_path, new_feats), (plan_path, new_plan)]
    if not existing_work:
        writes.append((card_path, new_card))
    written = []
    for p, text in writes:
        try:
            write_atomic(p, text)
        except OSError as exc:
            tail = f"——已写：{'、'.join(written)}；先 git diff 核对，再重跑一次" if written else ""
            return die(f"写 {os.path.relpath(p)} 失败：{exc}{tail}", as_json, 2)
        written.append(os.path.relpath(p))

    if as_json:
        print(json.dumps({"ok": True, "dry_run": False, "written": True,
                          "ids": ids, "changes": changes}, ensure_ascii=False, indent=2))
    else:
        print(f"new-feature：{req_id} / {feature_id} / {work_id} / {task_id} / {card_id}")
        for c in changes:
            print(f"  {c['file']} · {c['table']} · +{c['row']}")
        if not existing_work and not opts["design-options"]:
            print("  提示：设计卡「选项空间」待补，W10 会提醒（不阻断）")
        print("  提示：功能停在「待评审」——过评审门后再推到「已评审」")
    return 0


# ---------------------------------------------------------------- main
def main():
    argv = sys.argv[1:]
    docs_arg, file_arg, out_arg = None, None, None
    rest, i = [], 0
    while i < len(argv):
        a = argv[i]
        if a in ("--docs", "--file", "--out") and i + 1 < len(argv):
            if a == "--docs":
                docs_arg = argv[i + 1]
            elif a == "--file":
                file_arg = argv[i + 1]
            else:
                out_arg = argv[i + 1]
            i += 2
            continue
        rest.append(a)
        i += 1
    argv = rest
    as_json = "--json" in argv
    argv = [a for a in argv if a != "--json"]

    # 帮助必须是只读的：以前 --help 会掉进默认的 index 分支，顺手把排序视图重写一遍
    # （内容碰巧相同，git status 看不出来；文档一改就静默弄脏工作区）。
    if any(a in ("-h", "--help") for a in argv):
        print((__doc__ or "").strip())
        return 0

    cmd = next((a for a in argv if not a.startswith("--")), "index")
    if cmd not in ("index", "check", "tree", "next", "set-status", "new-feature"):
        return die(f"未知命令：{cmd}（可用：index / check / tree / next / "
                   f"set-status / new-feature）", as_json)
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

    if cmd == "set-status":
        return cmd_set_status(docs, schema, path, argv, as_json)
    if cmd == "new-feature":
        return cmd_new_feature(docs, schema, path, argv, as_json)

    try:
        lines, weights, tasks, works, dirs, fragments = load(path)
    except SystemExit as exc:
        return die(str(exc), as_json, 1)

    cfg = schema["plan"]
    feats = load_features(features_path(docs, schema))
    cards = load_directions(directions_path(docs, schema))
    designs = load_designs(designs_path(docs, schema))
    chains = load_chains(directions_path(docs, schema))
    errs, items, codes, done, work_ids = validate(weights, tasks, works, dirs, cfg,
                                                  fragments, feats, cards, designs, chains)

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

    if cmd == "tree":
        d_order, d_name, w_rows, w_by_d, t_by_w = tree_build(dirs, works, items, feats)
        assess = (feats or {}).get("assess", {}) if feats else {}
        today = datetime.date.today().isoformat()
        if "--html" in argv:
            text = tree_html(d_order, d_name, w_rows, w_by_d, t_by_w, items, assess, today)
        elif as_json:
            print(json.dumps({
                "directions": [{"id": d, "name": d_name[d],
                                "works": [{"id": w, "name": w_rows[w]["name"],
                                           "state": w_rows[w]["state"],
                                           "tasks": [{"id": t["id"], "name": t["name"],
                                                      "feature": t["feature"],
                                                      "status": t["status"],
                                                      "done_at": (assess.get(t["id"]) or {}).get("完成于", "")}
                                                     for t in t_by_w.get(w, [])]}
                                          for w in w_by_d.get(d, [])]}
                               for d in d_order],
                "tasks": len(items), "works": len(w_rows), "errors": errs},
                ensure_ascii=False, indent=2))
            return 1 if errs else 0
        else:
            text = tree_text(d_order, d_name, w_rows, w_by_d, t_by_w, items, assess)
        if out_arg:
            with open(out_arg, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(text + "\n")
            print(f"written: {out_arg}（{len(d_order)} 方向 · {len(w_rows)} 工作 · {len(items)} 任务）")
        else:
            print(text)
        for e in errs:
            print(f"  ERROR [{e['code']}] {e['message']}", file=sys.stderr)
        return 1 if errs else 0

    if cmd == "next":
        # 唯一出口：第一个视角的第一名就是「下一步」；其它视角的第一名若不同，
        # 一并列出——排序不是唯一答案，选哪条由人定（README「可调优先级」）。
        views = compute(weights, items, codes, done, work_ids, cfg)
        work_meta, dir_name = {}, {}
        if works:
            wh, wrows = works
            i_wname = wh.index("工作") if "工作" in wh else None
            i_wdir = wh.index("方向") if "方向" in wh else None
            for r in wrows:
                if len(r) == len(wh) and r:
                    work_meta[r[0]] = {"name": r[i_wname] if i_wname is not None else "",
                                       "dir": r[i_wdir] if i_wdir is not None else ""}
        if dirs:
            dh, drows = dirs
            i_dname = dh.index("方向") if "方向" in dh else None
            for r in drows:
                if len(r) == len(dh) and r and i_dname is not None:
                    dir_name[r[0]] = r[i_dname]

        picks = []
        for view, order in views:
            free = [o for o in order if not o[1]["blocked_by"]]
            picks.append((view, free[0] if free else None))

        if as_json:
            out = {"ok": not errs, "errors": errs, "views": []}
            for view, top in picks:
                if top is None:
                    out["views"].append({"view": view, "task": None})
                    continue
                score, t, worst = top
                wm = work_meta.get(t["work"], {})
                out["views"].append({"view": view, "task": t["id"], "name": t["name"],
                                     "score": score, "weak": f"{worst}={t['scores'][worst]}",
                                     "feature": t["feature"], "status": t["status"],
                                     "work": t["work"], "direction": wm.get("dir", "")})
            print(json.dumps(out, ensure_ascii=False, indent=2))
            return 1 if errs else 0

        if not picks or picks[0][1] is None:
            print("下一步：无可排任务（没有未完成、也未被前置阻塞的任务）")
        else:
            view, top = picks[0]
            score, t, worst = top
            wm = work_meta.get(t["work"], {})
            print(f"下一步：{t['id']} {t['name']}")
            print(f"  排序：视角「{view}」总分 {score:.2f}；弱项 {worst}={t['scores'][worst]}")
            print(f"  路径：{wm.get('dir', '')} {dir_name.get(wm.get('dir', ''), '')} → "
                  f"{t['work']} {wm.get('name', '')} → {t['id']}")
            print(f"  功能：{t['feature']}；状态：{t['status']}")
            others = [f"{v}→{o[1]['id']}" for v, o in picks[1:] if o and o[1]["id"] != t["id"]]
            if others:
                print("  其它视角的第一名：" + "；".join(others)
                      + " ← 排序不是唯一答案，先看哪个由人定")
        for e in errs:
            print(f"  ERROR [{e['code']}] {e['message']}", file=sys.stderr)
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
