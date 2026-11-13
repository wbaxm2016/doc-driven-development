#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""docs/ 全库校验：front-matter / 链接 / ADR 结构 / 取代链 / 术语 / 契约 verify / 棘轮基线。

用法：
    python scripts/doc_check.py [--docs docs] [--quiet] [--json]
    python scripts/doc_check.py --baseline          # 棘轮：只对超出基线的规则报错
    python scripts/doc_check.py --update-baseline   # 把当前计数写进基线文件

配置唯一来源：<docs>/_schema.json（缺失时回退 <docs>/_layers.json，再回退内置默认）。
规则清单与码表见 references/check-rules.md —— 本文件与那份文档必须逐条对应。

设计：
  * 只读，不改任何文件（除 --update-baseline 写基线）；
  * 代码围栏与行内代码先剔除再查链接，避免示例里的 `](x.md)` 误报；
  * 段结构、枚举、文件名、路径全部来自 _schema.json，不硬编码中文目录名。
"""
from __future__ import annotations

import datetime
import json
import os
import re
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# ---------------------------------------------------------------- 默认配置
DEFAULT_SCHEMA = {
    "version": 1,
    "layers": {
        "00-门面": "facade",
        "10-架构": "architecture",
        "20-契约": "contract",
        "30-决策": "decision",
        "40-运行": "operation",
        "50-术语": "glossary",
        "60-规范": "norm",
        "70-过程": "process",
    },
    "status": ["active", "proposed", "draft", "implemented",
               "superseded", "snapshot", "reference"],
    "authority": ["1", "2", "3", "4"],
    "domain": None,
    "session_sections": ["本次范围", "用户侧记录", "AI 侧记录",
                         "决策与选项对比", "开放项", "本次产出", "交接"],
    "adr_sections": ["状态", "背景", "决策", "备选方案", "影响", "撤销条件"],
    "names": {
        "plan": "开发计划.md",
        "inbox": "问题收件箱.md",
        "timeline": "时间线.md",
        "session_template": "会话档案模板.md",
        "sessions_dir": "会话",
        "adr_dir": "adr",
        "adr_index": "decisions.md",
        "alias_table": "别名表.md",
    },
    "ids": {"issue": "ISS", "adr": "ADR", "req": "REQ", "digits": 3},
    "plan": {
        "done_states": ["已完成"],
        "states": ["待开工", "进行中", "已实现（未验收）", "已完成", "阻塞", "搁置"],
        "task_pattern": r"^T\d+\.\d+\.\d+$",
        "work_pattern": r"^W\d+\.\d+$",
    },
    "ears": {"enabled": True},
    "baseline": ".docs-baseline.json",
}

REQUIRED = ["title", "layer", "domain", "status", "authority", "updated", "summary"]
PLACEHOLDER = "原文未记录"
ALIAS_LAYERS = {"facade", "contract", "norm"}
ALIAS_SKIP_STATUS = {"snapshot", "reference", "implemented", "superseded"}
EARS_CUES = ("WHEN", "IF", "WHILE", "GIVEN", "SHALL",
             "当", "若", "一旦", "必须", "应", "不得", "不许")
# verify 列里这些写法等于没写：占位符不是可执行入口（T1.2.2）
VERIFY_PLACEHOLDERS = {"", "-", "—", "–", "待补", "待填", "待定", "无",
                       "n/a", "na", "tbd", "todo", "none"}

# 需求行的状态词白名单（E22）：与 verify.py 的跳过集合对齐——
# 只有「待实现 / 阻塞 / 搁置」会被跳过，其余状态意味着 verify 必须真跑。
REQ_STATES = {"待实现", "已实现", "阻塞", "搁置", "作废"}
# 标了「已实现」就必须指得出出处（E23）：「依据」里要有可核对的锚
TRACE_REF_RE = re.compile(r"(ADR-\d+|ISS-\d+|T\d+\.\d+\.\d+|W\d+\.\d+|D\d+\b|[\w\-./]+\.md)")
REF_PLACEHOLDERS = {"", "-", "—", "–", "无", "待补", "待填", "tbd"}

# 功能台账的状态链（E24）：设计视图（待评审/已评审/实施中）与已实现（已对照/已验收）同表
FEATURE_STATES = {"待评审", "已评审", "实施中", "已对照", "已验收", "搁置", "撤回"}
# 「—（历史）」只给先于契约存在的老功能，且只能停在已验收
LEGACY_REQ = {"—（历史）", "-（历史）", "—(历史)", "-(历史)"}

# 码表：顺序即打印顺序，也用于 --json 的 counts
CODES = ["E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8", "E9", "E10",
         "E11", "E12", "E13", "E14", "E15", "E16", "E17", "E18", "E28",
         "E19", "E20", "E21", "E22", "E23", "E24", "E26", "E27", "E31",
         "W1", "W2", "W3", "W4", "W5", "W6", "W7", "W8", "W9", "W10", "W12"]


# ---------------------------------------------------------------- 基础工具
def read(path):
    # utf-8-sig：Windows 编辑器很容易写 BOM，而 `text.startswith("---")` 会把
    # BOM 当成正文首字符，于是明明有 front-matter 却报 E1。
    with open(path, encoding="utf-8-sig") as fh:
        return fh.read()


def parse_fm(text):
    """返回 (front-matter dict, body)。缺 front-matter 时 dict 为 None。"""
    if not text.startswith("---"):
        return None, text
    end = text.find("\n---", 3)
    if end < 0:
        return None, text
    block = text[3:end]
    body = text[end + 4:]
    data = {}
    for line in block.splitlines():
        m = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", line)
        if not m:
            continue
        val = m.group(2).strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "'\"":
            q, val = val[0], val[1:-1]
            if q == "'":
                val = val.replace("''", "'")
            else:
                # 双引号块按 JSON 字符串还原转义（devlog 写标题时就是这么转的），
                # 否则 `他说\"这样\"` 与正文 H1 的 `他说"这样"` 永远不相等 → 假 E4。
                try:
                    val = json.loads('"' + val + '"')
                except ValueError:
                    pass
        data[m.group(1)] = val
    return data, body


def strip_code(text):
    """剔除围栏代码块与行内代码，链接检查只看真实正文。"""
    text = re.sub(r"(?ms)^[ \t]*(```|~~~).*?^[ \t]*\1", "", text)
    return re.sub(r"`[^`\n]*`", "", text)


def strip_fences(text):
    """只剔除围栏代码块，保留行内代码——E18 要看 verify 单元格里的命令本身。"""
    return re.sub(r"(?ms)^[ \t]*(```|~~~).*?^[ \t]*\1", "", text)


def verify_col(header):
    """需求表里 verify 列的索引；表里没有这一列返回 None。"""
    for i, h in enumerate(header):
        s = strip_md(h).strip().rstrip(":：").strip().lower()
        if s == "verify" or s.startswith("verify"):
            return i
    return None


def verify_missing(cell):
    """空单元格与占位符（— / 待补 / TBD…）都等于没写可执行入口。"""
    return strip_md(cell).strip().lower() in VERIFY_PLACEHOLDERS


def strip_md(s):
    return re.sub(r"[*`]", "", s).strip()


def h1_of(body):
    for line in body.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return ""


def split_row(s):
    """按**未转义**的竖线切一行表格；`\\|` 还原成 `|`（GFM 的转义写法）。

    ISS-070：原来直接 `split("|")`。一格写了 `| ID | 发现日 |` 就把 7 列的行切成 12 格，
    E18 读到第 4 格「ID」——校验全绿而 CI 的 verify 红，人先去怀疑 CI。
    """
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


def table_width_errors(text):
    """[(行号, 表头格数, 本行格数)]：行内未转义竖线会让整行错位（E28）。"""
    out, head = [], None
    for no, line in enumerate(text.splitlines(), 1):
        s = line.strip()
        if s.startswith("|") and s.endswith("|") and len(s) > 2:
            n = len(split_row(s))
            if head is None:
                head = n
            elif n != head:
                out.append((no, head, n))
        else:
            head = None
    return out


def read_tables(text):
    """极简 Markdown 表解析：返回 [(header, rows)]。"""
    tables, block = [], []
    for line in text.splitlines() + [""]:
        s = line.strip()
        if s.startswith("|") and s.endswith("|") and len(s) > 2:
            block.append(split_row(s))
        else:
            if len(block) >= 2:
                header, rows = block[0], block[1:]
                rows = [r for r in rows
                        if not all(re.fullmatch(r":?-{2,}:?", c or "-") for c in r)]
                tables.append((header, rows))
            block = []
    return tables


# ---------------------------------------------------------------- 契约增量（_delta）
# 只定机器判据，约定本身见 <contract>/_delta/README.md（T1.1.1）。三条码各管一段：
#   E19 目录与 status 不符（根目录有未合并 delta / 归档不是 snapshot）；
#   E20 待合并 delta 的锚点与目标冲突（不能机械应用）；
#   E21 已归档 delta 的合并结果与目标不一致（合并丢失或目标被改）。
DELTA_README = "README.md"
DELTA_ARCHIVE = "_archive"
# git 的冲突标记只认行首 7 个字符后跟空格/行尾，避免误伤 Markdown 分隔线
CONFLICT_MARK_RE = re.compile(r"^(?:<{7}|={7}|>{7})(?: |$)", re.M)


def delta_change_re(req_prefix):
    return re.compile(
        rf"^\*{{0,2}}变更\s*(\d+)\s*[·・•]\s*(ADDED|MODIFIED|REMOVED)\s*[·・•]\s*"
        rf"({re.escape(req_prefix)}-\d+)\*{{0,2}}\s*$")


def parse_delta(body, req_prefix):
    """把一篇 DELTA 拆成 [{no, op, req, before, after, position}]。

    每个变更段落由 `**变更 N · 操作 · REQ-nnn**` 开头，后面跟 1–2 个代码围栏。
    围栏属于 before 还是 after，看它上方最近的标注（「锚点（before…）」/
    「合并后（after…）」）；ADDED 只有一个围栏时按 after 处理。
    返回 (changes, problems)：problems 是结构性问题（重复块），由调用方带码报出。
    """
    changes, problems = [], []
    change_re = delta_change_re(req_prefix)
    cur, role = None, None
    lines = body.splitlines()
    i = 0
    while i < len(lines):
        s = lines[i].strip()
        m = change_re.match(s)
        if m:
            cur = {"no": int(m.group(1)), "op": m.group(2), "req": m.group(3),
                   "before": None, "after": None, "position": ""}
            changes.append(cur)
            role = None
            i += 1
            continue
        if not s.startswith(("```", "~~~")):
            if cur is not None:
                low = s.lower()
                if "位置" in s:
                    cur["position"] = s.split("：", 1)[-1].strip()
                elif "before" in low or "锚点" in s:
                    role = "before"
                elif "after" in low or "合并后" in s:
                    role = "after"
            i += 1
            continue
        fence = s[:3]
        j = i + 1
        block = []
        while j < len(lines) and not lines[j].strip().startswith(fence):
            block.append(lines[j])
            j += 1
        # 只去掉块首尾的空行，行内空白必须原样保留——逐字匹配的前提
        while block and not block[0].strip():
            block.pop(0)
        while block and not block[-1].strip():
            block.pop()
        if cur is not None:
            key = role or ("after" if cur["op"] == "ADDED" else "")
            if key and cur.get(key) is None:
                cur[key] = "\n".join(block)
            elif key:
                problems.append(
                    f"变更 {cur['no']}（{cur['op']} {cur['req']}）有多个 {key} 代码块")
        i = j + 1
    return changes, problems


def row_req_ids(text, req_re):
    """表格行里「编号单元格就是整条 REQ-nnn」的编号（与 E18 的判定口径一致）。"""
    ids = []
    for line in text.splitlines():
        s = line.strip()
        if not s.startswith("|"):
            continue
        for cell in split_row(s):
            m = req_re.fullmatch(strip_md(cell))
            if m:
                ids.append(m.group(0))
    return ids


def requirement_header(text, req_re):
    """目标文件里需求表的表头（用来定位 verify 列与列数）。"""
    for header, rows in read_tables(strip_fences(text)):
        if verify_col(header) is not None:
            return header
        for row in rows:
            if any(req_re.fullmatch(strip_md(c)) for c in row):
                return header
    return None


def check_delta(changes, problems, target_text, archived, req_re, superseded=False):
    """返回 [(code, message)]：proposed 按 _delta/README.md §5 判冲突，归档判合并结果。

    `superseded=True`（front-matter 有 superseded_by）时，归档 delta 不核「after 仍要在目标里」：
    它新增/改过的行可能已被后续 delta 合法删掉或再改；链条由 E31 保证。
    """
    out = []
    code = "E21" if archived else "E20"
    for msg in problems:
        out.append((code, msg))
    if not changes:
        out.append((code, "没解析出「**变更 N · ADDED|MODIFIED|REMOVED · REQ-nnn**」段落"))
        return out
    if CONFLICT_MARK_RE.search(target_text):
        out.append((code, "target 含合并冲突标记（<<<<<<< / ======= / >>>>>>>）"))
    target_ids = set()
    for _h, rows in read_tables(strip_fences(target_text)):
        for row in rows:
            target_ids.update(row_req_ids("|" + "|".join(row) + "|", req_re))
    for ch in changes:
        tag = f"变更 {ch['no']}（{ch['op']} {ch['req']}）"
        before, after = ch["before"], ch["after"]
        at_ids = row_req_ids(after or "", req_re)
        if archived:
            if superseded:
                continue
            if ch["op"] == "REMOVED":
                if not before:
                    out.append((code, f"{tag} 缺 before 代码块，无法核对是否已删除"))
                elif target_text.count(before):
                    out.append((code, f"{tag} 声明删除该行，但目标里仍能找到"
                                      f"（{target_text.count(before)} 次）"))
            elif not after:
                out.append((code, f"{tag} 缺 after 代码块，无法核对合并结果"))
            else:
                n = target_text.count(after)
                if n != 1:
                    out.append((code, f"{tag} 的 after 在目标中出现 {n} 次（应为 1 次；"
                                      f"合并丢失或目标被后续改动）"))
            continue
        if ch["op"] == "ADDED":
            if not after:
                out.append((code, f"{tag} 缺 after 代码块（新增行原文）"))
            elif ch["req"] not in at_ids:
                out.append((code, f"{tag} 的 after 行不是 {ch['req']}（编号与声明不一致）"))
            if ch["req"] in target_ids:
                out.append((code, f"{tag} 的编号已出现于目标（ADDED 只能新增）"))
            for n in req_re.findall(ch["position"]):
                if n not in target_ids:
                    out.append((code, f"{tag} 的插入位置「{n} 行之后」在目标里找不到"))
        else:
            if not before:
                out.append((code, f"{tag} 缺 before 代码块（锚点）"))
            else:
                n = target_text.count(before)
                if n == 0:
                    out.append((code, f"{tag} 的 before 锚点在目标中出现 0 次"
                                      f"（不存在，需按目标原文重写）"))
                elif n > 1:
                    out.append((code, f"{tag} 的 before 锚点在目标中出现 {n} 次"
                                      f"（不唯一，需按目标原文重写）"))
                elif at_ids and ch["req"] not in at_ids:
                    out.append((code, f"{tag} 的 after 行不是 {ch['req']}"
                                      f"（MODIFIED 不得改编号）"))
            if ch["op"] == "MODIFIED" and not after:
                out.append((code, f"{tag} 缺 after 代码块（合并后原文）"))
    return out


# ---------------------------------------------------------------- 配置
class SchemaError(Exception):
    """配置文件存在但读不出来——报清楚该查哪个文件，不抛回溯。"""


def load_schema(docs):
    for name in ("_schema.json", "_layers.json"):
        cfg = os.path.join(docs, name)
        if os.path.exists(cfg):
            try:
                raw = json.loads(read(cfg))
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise SchemaError(
                    f"{cfg} 解析失败：{exc}。这个文件是层/枚举/段结构的唯一来源，"
                    f"要么修好它，要么删掉回退内置默认")
            if not isinstance(raw, dict):
                raise SchemaError(f"{cfg} 顶层不是对象（应为 {{\"layers\": {{...}}}}）")
            merged = json.loads(json.dumps(DEFAULT_SCHEMA))
            for k, v in raw.items():
                if isinstance(v, dict) and isinstance(merged.get(k), dict):
                    merged[k].update(v)
                else:
                    merged[k] = v
            # layers 是「这一套层就是全部」，只能整表替换、不能与内置 8 层合并：
            # doc_init 默认只写 5 层，合并会让它永远"缺"另外 3 层，铺完首跑就报
            # 3 条假 E9（2.x 真实回归）。旧版 _layers.json 同理整表替换。
            if "layers" in raw:
                merged["layers"] = raw["layers"]
            return merged, name
    # 缺配置就**不猜**：内置 8 层只是满配默认，按它判 5 层项目会多出 3 条假 E9（ISS-013）。
    raise SchemaError(
        f"{docs} 下既没有 _schema.json 也没有 _layers.json：层表/枚举/段结构无从判断。"
        f"跑 `python <技能目录>/scripts/doc_init.py --target .` 补齐（幂等，不覆盖已有文件）")


def layer_dir(schema, layer_name):
    for d, v in schema["layers"].items():
        if v == layer_name:
            return d
    return None


# ---------------------------------------------------------------- 术语别名
def load_aliases(docs, schema):
    gdir = layer_dir(schema, "glossary")
    if not gdir:
        return []
    path = os.path.join(docs, gdir, schema["names"]["alias_table"])
    if not os.path.exists(path):
        return []
    out = []
    for header, rows in read_tables(read(path)):
        if "禁用别名" not in header:
            continue
        i = header.index("禁用别名")
        for row in rows:
            if i >= len(row):
                continue
            for a in re.split(r"[、，,/;；]", row[i]):
                a = a.strip().strip("`*").strip("—").strip()
                if len(a) >= 2:
                    out.append(a)
    return sorted(set(out))


# ---------------------------------------------------------------- 想法候选
IDEAS_HEADING = re.compile(r"^### 3\.7\b[^\n]*", re.M)
ID_PATTERN = re.compile(r"REQ-\d+|F-\d+|(?<![A-Za-z])D\d+")
IDEA_KINDS = ("目标", "愿景", "功能", "需求")
# 活文档出处：`路径.md（YYYY-MM-DD）`——带版本日期才跳过逐字（REQ-025）
DOC_SRC_RE = re.compile(r"^(?P<path>[^\s（(]+\.md)\s*[（(](?P<date>\d{4}-\d{2}-\d{2})[)）]$")


def ideas_parts(body):
    """切出所有「### 3.7 想法候选」小节，并给出「不含这些小节」的正文（原话要在正文里逐字存在）。"""
    spans = []
    for m in IDEAS_HEADING.finditer(body):
        rest = body[m.end():]
        nxt = re.search(r"^#{1,3} ", rest, re.M)
        end = m.end() + (nxt.start() if nxt else len(rest))
        spans.append((m.start(), end))
    if not spans:
        return None, body
    segs = [body[s:e] for s, e in spans]
    parts, last = [], 0
    for s, e in spans:
        parts.append(body[last:s])
        last = e
    parts.append(body[last:])
    return "\n".join(segs), "".join(parts)


PRECHECK_HEADING = re.compile(r"^### 3\.8\b[^\n]*", re.M)
PRECHECK_ACTIONS = ("补证据", "改条款", "维持")
PRECHECK_VERDICTS = ("待裁决", "采纳", "驳回")
PRECHECK_NOT_APPLICABLE = ("对齐门", "发版", "回滚", "开放问题收口")
PRECHECK_COLS = ("指向", "逐字引文", "疑点", "建议动作", "裁决")
PRECHECK_FORBIDDEN = ("状态", "确认", "评审", "考核")


def precheck_parts(body):
    """切出所有「### 3.8 预审记录」小节，并给出「不含这些小节」的正文（本档引文要在正文里逐字存在）。"""
    spans = []
    for m in PRECHECK_HEADING.finditer(body):
        rest = body[m.end():]
        nxt = re.search(r"^#{1,3} ", rest, re.M)
        end = m.end() + (nxt.start() if nxt else len(rest))
        spans.append((m.start(), end))
    if not spans:
        return None, body
    segs = [body[s:e] for s, e in spans]
    parts, last = [], 0
    for s, e in spans:
        parts.append(body[last:s])
        last = e
    parts.append(body[last:])
    return "\n".join(segs), "".join(parts)


def precheck_problems(seg, scope, docs_dir, repo_root, cache):
    """E30：预审记录的形状 / 引文逐字 / 指向存在 / 不适用条目不写结论。"""
    probs = []
    path_re = re.compile(r"[\w\-./]+\.md")
    for header, rows in read_tables(seg):
        heads = [strip_md(h) for h in header]
        for bad in PRECHECK_FORBIDDEN:
            if bad in heads:
                probs.append("预审记录的表头不能有「%s」列——预审不是台账" % bad)
        if not set(PRECHECK_COLS) <= set(heads):
            probs.append("预审记录缺列：需要 指向 / 逐字引文 / 疑点 / 建议动作 / 裁决")
            continue
        col = {h: i for i, h in enumerate(heads)}

        def cell(row, name):
            i = col[name]
            return row[i].strip() if i < len(row) else ""

        for row in rows:
            target = strip_md(cell(row, "指向"))
            quote = strip_md(cell(row, "逐字引文")).strip("「」").strip()
            action = strip_md(cell(row, "建议动作"))
            verdict = strip_md(cell(row, "裁决"))
            if not target:
                continue
            pm = path_re.search(target)
            if pm is None and any(k in target for k in PRECHECK_NOT_APPLICABLE):
                if action != "不适用":
                    probs.append("「%s」不在预审范围，建议动作必须写「不适用」" % target[:12])
                continue
            if action == "不适用":
                probs.append("「%s」不在不适用三处，却写了「不适用」" % target[:12])
                continue
            if action not in PRECHECK_ACTIONS:
                probs.append("预审的建议动作 %r 不在白名单（补证据 / 改条款 / 维持）" % action)
            if verdict and verdict not in PRECHECK_VERDICTS:
                probs.append("预审的裁决 %r 不在白名单（待裁决 / 采纳 / 驳回）" % verdict)
            if not quote:
                probs.append("预审记录有一行缺「逐字引文」：%s" % target[:18])
                continue
            if target.startswith("本档"):
                hay = scope
            else:
                hay = None
                for cand in ([pm.group(0)] if pm and os.path.isabs(pm.group(0)) else [
                        os.path.join(repo_root, pm.group(0)) if pm else "",
                        os.path.join(docs_dir, pm.group(0)) if pm else ""]):
                    if cand and os.path.isfile(cand):
                        if cand not in cache:
                            cache[cand] = read(cand)
                        hay = cache[cand]
                        break
                if hay is None:
                    probs.append("预审的指向文件不存在：%s（指向只认 .md 路径：卡片写 `docs/00-门面/设计卡.md`；"
                              "写卡号 / `.py` 会被拒，脚本类疑点指到对应 `.md` 载体或写「本档」）"
                              % (pm.group(0) if pm else target[:18]))
                    continue
            if verdict in ("采纳", "驳回"):
                # 已裁决的行是当时的快照：修复会改动原文，不要求引文今天仍逐字存在。
                continue
            if quote not in hay and quote not in strip_md(hay):
                probs.append("预审引文在指向里找不到（逐字）：%s" % quote[:24])
    return probs


def ideas_problems(seg, scope, docs_dir, repo_root, cache, all_ids):
    """E29：类别白名单 / 原话逐字存在 / 建议落点的编号存在。返回 (问题, 原话列表)。"""
    probs, quotes = [], []
    for header, rows in read_tables(seg):
        if not any(h.startswith("原话") for h in header):
            continue
        col = {h: i for i, h in enumerate(header)}

        def pick(name):
            if name in col:
                return col[name]
            for h, i in col.items():
                if h.startswith(name):
                    return i
            return None

        def cell(row, name):
            i = pick(name)
            return row[i].strip() if i is not None and i < len(row) else ""

        for row in rows:
            kind = strip_md(cell(row, "类别")).strip()
            quote = strip_md(cell(row, "原话")).strip().strip("「」").strip()
            src = cell(row, "出处")
            target = cell(row, "建议落点")
            if not quote:
                continue
            if kind not in IDEA_KINDS:
                probs.append("想法类别 %r 不在白名单（目标 / 愿景 / 功能 / 需求）" % kind)
                continue
            if src.startswith("本档"):
                hay = scope
            else:
                m = DOC_SRC_RE.match(src)
                if m:
                    # 活文档带版本日期：只核文件存在与日期合法，不核逐字——
                    # 引文记的是「那一版」，拿今天的文本去核它必然失效（REQ-025）。
                    path_v, date_v = m.group("path").strip(), m.group("date")
                    try:
                        datetime.date.fromisoformat(date_v)
                    except ValueError:
                        probs.append("出处的版本日期不合法：%s（要 YYYY-MM-DD）" % src)
                        continue
                    cands = [path_v] if os.path.isabs(path_v) else [
                        os.path.join(docs_dir, path_v), os.path.join(repo_root, path_v)]
                    if not any(os.path.exists(c) for c in cands):
                        probs.append("想法的出处文件不存在：%s" % path_v)
                        continue
                    for pid in ID_PATTERN.findall(target):
                        if pid not in all_ids:
                            probs.append("建议落点 %s 不存在" % pid)
                    quotes.append(quote)
                    continue
                if src.endswith(".md"):
                    probs.append("出处不能用活文档（源头一改引文就失效）：%s"
                                 "——写成本档 §N，或带版本日期如 vision.md（2026-11-04）" % src)
                    continue
                hay = None
                cands = [src] if os.path.isabs(src) else [
                    os.path.join(docs_dir, src), os.path.join(repo_root, src)]
                for cand in cands:
                    if os.path.exists(cand):
                        if cand not in cache:
                            cache[cand] = read(cand)
                        hay = cache[cand]
                        break
                if hay is None:
                    probs.append("想法的出处文件不存在：%s" % src)
                    continue
            if quote not in hay:
                probs.append("原话在出处里找不到（逐字）：%s" % quote[:24])
                continue
            for pid in ID_PATTERN.findall(target):
                if pid not in all_ids:
                    probs.append("建议落点 %s 不存在" % pid)
            quotes.append(quote)
    return probs, quotes


def design_card_problems(card_text, plan_status):
    """W10：待开工 / 进行中工作的设计卡，选项空间是否具备最小形状。

    只判形状：≥3 个方案、含一个不做 / 少做、被否方案有回到条件；广度够不够仍人读。
    """
    probs = []
    head_re = re.compile(r"^## K(\d+) · (W\d+\.\d+) · [^\n]*", re.M)
    for m in head_re.finditer(card_text):
        kid, wid = "K" + m.group(1), m.group(2)
        if plan_status.get(wid) not in ("待开工", "进行中"):
            continue
        rest = card_text[m.end():]
        nxt = re.search(r"^## ", rest, re.M)
        sec = rest[:nxt.start()] if nxt else rest
        opt = re.search(r"- \*\*选项空间\*\*[：:]\s*\n(.*?)(?=\n- \*\*|\Z)", sec, re.S)
        if not opt:
            probs.append(f"{kid}（{wid}）缺「选项空间」表：先摆 ≥3 个结构不同的方案（含一个不做 / 少做），再选方向")
            continue
        tables = read_tables(opt.group(1))
        if not tables:
            probs.append(f"{kid}（{wid}）的「选项空间」下没有表：用表列出方案 / 轴 / 结论 / 回到条件")
            continue
        header, rows = tables[0]
        heads = [strip_md(h) for h in header]
        if "选项" not in heads or "回到条件" not in heads:
            probs.append(f"{kid}（{wid}）的选项空间表缺「选项」或「回到条件」列")
            continue
        i_opt, i_back = heads.index("选项"), heads.index("回到条件")
        i_con = heads.index("结论") if "结论" in heads else None
        if len(rows) < 3:
            probs.append(f"{kid}（{wid}）的选项空间少于 3 个方案：先广度后深度")
        opts = [strip_md(r[i_opt]) for r in rows if i_opt < len(r)]
        if not any(("不做" in o or "少做" in o) for o in opts):
            probs.append(f"{kid}（{wid}）的选项空间没有「不做 / 少做」：补一个最省路径")
        for r in rows:
            verdict = strip_md(r[i_con]) if i_con is not None and i_con < len(r) else ""
            if "被否" in verdict:
                back = strip_md(r[i_back]) if i_back < len(r) else ""
                if back in ("", "—", "-", "无", "待补", "待填"):
                    probs.append(f"{kid}（{wid}）的被否方案没有回到条件：写什么信号出现时切回")
                    break
    return probs


OBS_CELLS = ("观测对象", "要回答的问题", "信号", "窗口")
OBS_PLACEHOLDERS = {"", "—", "-", "–", "待补", "待填", "待定", "…", "...", "无", "tbd", "n/a"}


def observability_problems(card_text, plan_status):
    """W12：待开工 / 进行中的设计卡缺「观测四格」。

    只判形状：四个标签各有一个非占位值；内容够不够仍人读。存量已完成卡不追溯。
    """
    probs = []
    head_re = re.compile(r"^## K(\d+) · (W\d+\.\d+) · [^\n]*", re.M)
    for m in head_re.finditer(card_text):
        kid, wid = "K" + m.group(1), m.group(2)
        if plan_status.get(wid) not in ("待开工", "进行中"):
            continue
        rest = card_text[m.end():]
        nxt = re.search(r"^## ", rest, re.M)
        sec = rest[:nxt.start()] if nxt else rest
        obs = re.search(r"- \*\*观测四格\*\*[：:]\s*(.*?)(?=\n- \*\*|\Z)", sec, re.S)
        if not obs:
            probs.append(f"{kid}（{wid}）缺「观测四格」：写 观测对象 / 要回答的问题 / 信号 / 窗口")
            continue
        val = obs.group(1)
        missing = []
        for lab in OBS_CELLS:
            m2 = re.search(re.escape(lab) + r"\s*[=：:]\s*([^\n；;｜|]+)", val)
            if not m2 or m2.group(1).strip().strip("`*_ ") in OBS_PLACEHOLDERS:
                missing.append(lab)
        if missing:
            probs.append(f"{kid}（{wid}）的「观测四格」缺：{'、'.join(missing)}"
                         "（空 / — / 待补 / 无 都算缺）")
    return probs


# ---------------------------------------------------------------- 主流程
def main():
    argv = sys.argv[1:]
    quiet = "--quiet" in argv
    as_json = "--json" in argv
    baseline_mode = "--baseline" in argv
    update_baseline = "--update-baseline" in argv

    docs = None
    for i, a in enumerate(argv):
        if a == "--docs" and i + 1 < len(argv):
            docs = argv[i + 1]

    if docs is None:
        docs = "docs"
        for cand in ("docs", "文档", "documentation"):
            if os.path.isdir(cand):
                docs = cand
                break
    if not os.path.isdir(docs):
        msg = f"找不到文档目录（已试 docs/ 文档/ documentation）：{docs}。用 --docs 指定。"
        if as_json:
            print(json.dumps({"ok": False, "fatal": msg}, ensure_ascii=False))
        else:
            print(f"ERROR {msg}")
        return 2

    try:
        schema, cfg_name = load_schema(docs)
    except SchemaError as exc:
        msg = str(exc)
        if as_json:
            print(json.dumps({"ok": False, "fatal": msg}, ensure_ascii=False))
        else:
            print(f"ERROR {msg}")
        return 2
    layers = schema["layers"]
    layer_names = set(layers.values())
    names = schema["names"]
    today = datetime.date.today().isoformat()

    files = []
    for dp, _dn, fn in os.walk(docs):
        for f in fn:
            if f.lower().endswith(".md"):
                files.append(os.path.join(dp, f))
    files.sort()

    aliases = load_aliases(docs, schema)
    errors, warns = [], []
    idea_quotes, idea_cache = {}, {}
    precheck_cache = {}
    all_ids = set()
    for path in files:
        _txt = read(path)
        _fm, _body = parse_fm(_txt)
        # 想法候选表里的编号是「建议」，不能自己证明自己存在：取编号时先把这一节去掉
        all_ids.update(ID_PATTERN.findall(_body if _fm else _txt)
                       if not _fm else ID_PATTERN.findall(ideas_parts(_body)[1]))
    per_layer = {v: [] for v in layers.values()}
    summaries = {}
    adr_files, adr_ids, adr_states, adr_links = [], {}, {}, {}
    idx_links = set()

    decision_dir = layer_dir(schema, "decision")
    adr_index_rel = f"{decision_dir}/{names['adr_index']}" if decision_dir else None
    # 契约增量目录固定在契约层下（_delta/README.md §2）；target 是仓库根相对路径
    contract_dir = layer_dir(schema, "contract")
    delta_prefix = f"{contract_dir}/_delta/" if contract_dir else None
    delta_archive_prefix = (f"{delta_prefix}{DELTA_ARCHIVE}/" if delta_prefix else None)
    repo_root = os.path.dirname(os.path.abspath(docs))

    # 取代链（REQ-024）：先收齐所有 delta 的编号，供 superseded_by 核对。
    delta_ids = set()
    if delta_prefix:
        for path in files:
            rel0 = os.path.relpath(path, docs).replace(os.sep, "/")
            if not rel0.startswith(delta_prefix) or os.path.basename(rel0) == DELTA_README:
                continue
            fm0, _ = parse_fm(read(path))
            did = ((fm0 or {}).get("delta_id") or "").strip()
            if not did:
                m = re.match(r"(DELTA-\d+)", os.path.basename(rel0))
                did = m.group(1) if m else ""
            if did:
                delta_ids.add(did)

    # 功能台账要判「引用的需求是否存在」，所以先把契约层出现过的 REQ 编号收一遍
    req_ids = set()
    req_defs = {}
    feat_cover = set()
    accepted_features = {}
    checked_features = set()
    check_table_seen = False
    if contract_dir:
        req_pat = re.compile(rf"{re.escape(schema['ids']['req'])}-\d+")
        for path in files:
            rel0 = os.path.relpath(path, docs).replace(os.sep, "/")
            # 只认「真正定义需求」的文件：README 与 _delta/ 里的编号是示例，
            # 算进来会造出「REQ-004 没有功能覆盖」这种假账（W8 首跑就撞上）。
            if not rel0.startswith(contract_dir + "/"):
                continue
            if rel0.endswith("README.md") or rel0.startswith(delta_prefix or "\0"):
                continue
            for rid in req_pat.findall(read(path)):
                req_ids.add(rid)
                req_defs.setdefault(rid, rel0)

    # 证据里引用的「第 N 组」要对得上 self_test 里真实存在的组
    test_groups = set()
    st_path = os.path.join(repo_root, "scripts", "self_test.py")
    if os.path.exists(st_path):
        test_groups = {int(x) for x in re.findall(r'print\("\\n(\d+)\. ', read(st_path))}

    # 设计卡选项空间（W10）要知道工作是否还没做完：只查待开工 / 进行中的卡
    plan_status = {}
    plan_path = os.path.join(docs, layer_dir(schema, "facade"),
                             names.get("plan", "开发计划.md"))
    if os.path.exists(plan_path):
        for header, rows in read_tables(strip_fences(read(plan_path))):
            heads = [strip_md(h) for h in header]
            if not {"编号", "工作", "状态"} <= set(heads):
                continue
            i_id, i_st = heads.index("编号"), heads.index("状态")
            for row in rows:
                if len(row) == len(heads):
                    wid = strip_md(row[i_id])
                    if re.fullmatch(r"W\d+\.\d+", wid):
                        plan_status[wid] = strip_md(row[i_st])

    def add(bucket, rel, code, msg):
        bucket.append({"file": rel, "code": code, "message": msg})

    for path in files:
        rel = os.path.relpath(path, docs).replace(os.sep, "/")
        text = read(path)
        fm, body = parse_fm(text)
        if fm is None:
            add(errors, rel, "E1", "缺少 front-matter")
            continue

        layer = fm.get("layer", "")
        if layer not in layer_names:
            add(errors, rel, "E3", f"layer 非法: {layer!r}")
        else:
            per_layer[layer].append(rel)
            parent = rel.split("/")[0] if "/" in rel else ""
            if parent and parent in layers and layers[parent] != layer:
                add(errors, rel, "E3", f"文件在 {parent}/ 但 layer={layer}")

        for k in REQUIRED:
            if not fm.get(k):
                add(errors, rel, "E2", f"缺字段 {k}")

        if fm.get("status") and fm["status"] not in schema["status"]:
            add(errors, rel, "E3", f"status 非法: {fm['status']!r}")
        if str(fm.get("authority", "")) not in [str(x) for x in schema["authority"]]:
            add(errors, rel, "E3", f"authority 非法: {fm.get('authority')!r}")
        dom_enum = schema.get("domain")
        if dom_enum and fm.get("domain") and fm["domain"] not in dom_enum:
            add(errors, rel, "E3", f"domain 非法: {fm['domain']!r}")

        h1 = h1_of(body)
        if h1 and strip_md(h1) != strip_md(fm.get("title", "")):
            add(errors, rel, "E4", f"title≠H1：{fm.get('title')} / {h1}")

        summary = fm.get("summary", "")
        if not summary:
            add(errors, rel, "E5", "summary 空")
        elif len(summary) > 80:
            add(errors, rel, "E5", f"summary 过长 {len(summary)} 字（上限 80）")
        else:
            summaries.setdefault(summary, []).append(rel)

        upd = fm.get("updated", "")
        if not re.fullmatch(r"20\d{2}-\d{2}-\d{2}", upd):
            add(errors, rel, "E6", f"updated 非法: {upd!r}")
        elif upd > today:
            add(errors, rel, "E6", f"updated 是未来日期: {upd}")

        if fm.get("status") == "superseded" and not fm.get("superseded_by"):
            add(errors, rel, "E8", "superseded 缺 superseded_by")

        # ---- E14 文件名
        base = os.path.basename(path)
        if fm.get("status") != "superseded":
            if " " in base:
                add(errors, rel, "E14", "文件名含空格")
            if re.search(r"[-_]v\d+(\.\d+)?(\.|$)", base):
                add(errors, rel, "E14", f"文件名带版本号：{base}（版本走 front-matter 或 Git）")

        # ---- E28 表格行格数 ≠ 表头：cell 里未转义的竖线会让整行错位（ISS-070）
        for no, hn, rn in table_width_errors(strip_fences(body)):
            add(errors, rel, "E28",
                f"第 {no} 行有 {rn} 格、表头 {hn} 格：cell 里出现了未转义的竖线，整行会错位"
                f"（写成「A / B / C 三列」，或用 `\\|` 转义）")

        # ---- E29 想法候选：类别 / 原话逐字 / 落点编号（ISS-073、REQ-016）
        idea_seg, idea_scope = ideas_parts(body)
        if idea_seg is not None:
            idea_probs, idea_qs = ideas_problems(
                idea_seg, idea_scope, docs, repo_root, idea_cache, all_ids)
            for msg in idea_probs:
                add(errors, rel, "E29", msg)
            for q in idea_qs:
                idea_quotes.setdefault(q, []).append(rel)

        # ---- E30 语义门预审：形状 / 引文逐字 / 指向存在 / 不适用条目不写结论（REQ-019）
        pre_seg, pre_scope = precheck_parts(body)
        if pre_seg is not None:
            for msg in precheck_problems(
                    pre_seg, pre_scope, docs, repo_root, precheck_cache):
                add(errors, rel, "E30", msg)

        # ---- ADR 结构（E10 / E12 / E15）
        if decision_dir and rel.startswith(f"{decision_dir}/{names['adr_dir']}/"):
            adr_files.append(rel)
            prefix = re.escape(schema["ids"]["adr"])
            m_id = re.match(rf"^{prefix}-(\d+)-", base)
            if not m_id:
                add(errors, rel, "E10",
                    f"文件名应为 {schema['ids']['adr']}-<三位>-标题.md：{base}")
            else:
                adr_ids.setdefault(int(m_id.group(1)), []).append(rel)
                adr_states[int(m_id.group(1))] = fm.get("status", "")
            if not re.match(rf"^{prefix}-\d{{3}}", h1):
                add(errors, rel, "E10", f"H1 应以 {schema['ids']['adr']}-xxx 开头：{h1[:40]}")
            h2 = [l[3:].strip() for l in body.splitlines()
                  if l.startswith("## ") and not l[3:].strip().startswith("附录")]
            if h2 != schema["adr_sections"]:
                miss = [s for s in schema["adr_sections"] if not any(s in x for x in h2)]
                if miss:
                    add(errors, rel, "E10", "缺段：" + "、".join(miss))
                else:
                    add(errors, rel, "E10", "段顺序不符，应为：" + " → ".join(schema["adr_sections"]))
            adr_links[rel] = (fm.get("superseded_by", ""), fm.get("supersedes", ""))

        # ---- W3 占位段
        for line in body.splitlines():
            s = line.strip()
            if s.startswith(">") and PLACEHOLDER in s:
                add(warns, rel, "W3", "占位段待补：" + s[:40])
                break

        # ---- W5 补记缺日期戳
        for line in body.splitlines():
            s = line.strip()
            if (s.startswith(">") and "补记" in s and "补记进度" not in s
                    and not re.search(r"补记于\s*20\d{2}-\d{2}-\d{2}", s)):
                add(warns, rel, "W5", "「补记」缺日期戳：" + s[:40])
                break

        # ---- E13 契约层约束措辞
        if layer == "contract" and base != "README.md":
            if "必须" not in body:
                add(errors, rel, "E13", "契约层缺约束措辞「必须」")
            if not re.search(r"不得|不许", body):
                add(errors, rel, "E13", "契约层缺禁止措辞「不得/不许」")

        # ---- W7 EARS：带 REQ 编号的条款行必须有规范措辞
        # 只认「编号单元格就是一整个 REQ-nnn」的行：变更记录/说明表里顺带提到需求编号
        # 不是条款行（ISS-018：误报会让人把整条 W7 当噪声关掉）。
        if schema["ears"].get("enabled", True) and layer == "contract":
            req_re = re.compile(rf"{re.escape(schema['ids']['req'])}-\d+")
            for line in strip_code(body).splitlines():
                if not line.strip().startswith("|"):
                    continue
                cells = split_row(line)
                if not cells or not req_re.fullmatch(strip_md(cells[0])):
                    continue
                joined = " ".join(c for c in cells if not req_re.fullmatch(strip_md(c)))
                if joined and not any(cue in joined for cue in EARS_CUES):
                    add(warns, rel, "W7",
                        f"{req_re.fullmatch(strip_md(cells[0])).group(0)} 未见规范措辞/触发条件："
                        + joined[:40])

        # ---- E18 契约行缺 verify（T1.2.2）：只认「编号单元格就是一整个 REQ-nnn」的行，
        # 变更记录里顺带提到需求编号不算条款行（否则会重复 ISS-018 的误报）。
        if layer == "contract" and base != "README.md":
            req_id_re = re.compile(rf"{re.escape(schema['ids']['req'])}-\d+")
            for header, rows in read_tables(strip_fences(body)):
                vcol = verify_col(header)
                for row in rows:
                    ids = [strip_md(c) for c in row
                           if req_id_re.fullmatch(strip_md(c))]
                    if not ids:
                        continue
                    if vcol is None:
                        add(errors, rel, "E18",
                            f"{ids[0]} 所在表缺 verify: 列（应写可执行命令或测试路径）")
                    elif vcol >= len(row) or verify_missing(row[vcol]):
                        add(errors, rel, "E18",
                            f"{ids[0]} 缺 verify:（应写可执行命令或测试路径）")

            # ---- E22 状态词白名单 / E23 「已实现」必须指得出出处（G1/G3）
            # 需求的「实现」不能只改一个词：状态词要合法，且「依据」能指回 ADR /
            # 任务 / 文件——这是"先设计后实现"唯一能机器判的那一半（判不了先后，
            # 只判"声称实现了，就说得清依据是什么"）。
            for header, rows in read_tables(strip_fences(body)):
                heads = [strip_md(h) for h in header]
                if "状态" not in heads:
                    continue
                i_st = heads.index("状态")
                i_ref = heads.index("依据") if "依据" in heads else None
                i_cf = heads.index("确认") if "确认" in heads else None
                for row in rows:
                    if len(row) != len(heads) or not req_id_re.fullmatch(strip_md(row[0])):
                        continue
                    rid = strip_md(row[0])
                    st = strip_md(row[i_st])
                    if st not in REQ_STATES:
                        add(errors, rel, "E22",
                            f"{rid} 的状态词不在白名单：{st!r}"
                            f"（允许：{'、'.join(sorted(REQ_STATES))}）")
                    if st == "已实现":
                        ref = strip_md(row[i_ref]) if i_ref is not None and i_ref < len(row) else ""
                        if ref in REF_PLACEHOLDERS or not TRACE_REF_RE.search(ref):
                            add(errors, rel, "E23",
                                f"{rid} 标了「已实现」，但「依据」指不出设计出处："
                                f"{ref or '(空)'}（写 ADR- / ISS- / 任务号或文件路径）")
                        # 对齐门：这条需求"是不是用户要的那句话"，只有确认能证明。
                        if i_cf is None:
                            add(errors, rel, "E23",
                                f"需求表缺「确认」列：{rid} 标了「已实现」，"
                                f"却查不到用户确认过这句话")
                        else:
                            cf = strip_md(row[i_cf]) if i_cf < len(row) else ""
                            if cf in REF_PLACEHOLDERS:
                                add(errors, rel, "E23",
                                    f"{rid} 标了「已实现」，但没有用户确认："
                                    f"写 `复述✓ YYYY-MM-DD｜档案 §` 或 `采纳✓ …`；"
                                    f"先于确认门的存量行写 `—（历史）`")

        # ---- W9 取数：功能对照清单里的 F 行（供循环后判「已验收 → 有行」）
        for header, rows in read_tables(strip_fences(body)):
            heads = [strip_md(h) for h in header]
            if not any(h.startswith("该验什么") for h in heads):
                continue
            check_table_seen = True
            for row in rows:
                if row and re.fullmatch(r"F-\d+", strip_md(row[0])):
                    checked_features.add(strip_md(row[0]))

        # ---- E24 功能台账（需求 → 功能 → 入口 → 证据）
        # 一张表两种读法：待评审/已评审/实施中＝设计视图，已对照/已验收＝已实现清单。
        # 只判能机械判的：编号、状态词、需求引用存在、入口存在、已验收有 verify 与证据。
        for header, rows in read_tables(strip_fences(body)):
            heads = [strip_md(h) for h in header]
            if not {"ID", "功能", "满足的需求", "状态"} <= set(heads):
                continue
            i_id, i_req, i_st = heads.index("ID"), heads.index("满足的需求"), heads.index("状态")
            i_to = heads.index("代码入口") if "代码入口" in heads else None
            i_vf = next((i for i, h in enumerate(heads)
                         if h.lower().startswith("verify")), None)
            i_ev = heads.index("证据") if "证据" in heads else None
            i_rv = heads.index("评审") if "评审" in heads else None
            i_ac = next((i for i, h in enumerate(heads) if h.startswith("考核")), None)
            i_dn = heads.index("完成于") if "完成于" in heads else None
            req_pat = re.compile(rf"{re.escape(schema['ids']['req'])}-\d+")
            for row in rows:
                if len(row) != len(heads):
                    continue
                fid = strip_md(row[i_id])
                if not re.fullmatch(r"F-\d+", fid):
                    continue
                st = strip_md(row[i_st])
                reqcell = strip_md(row[i_req])
                if st == "已验收":
                    accepted_features[fid] = rel
                if st not in FEATURE_STATES:
                    add(errors, rel, "E24",
                        f"{fid} 的状态词不在白名单：{st!r}"
                        f"（允许：{'、'.join(sorted(FEATURE_STATES))}）")
                if reqcell in LEGACY_REQ:
                    if st != "已验收":
                        add(errors, rel, "E24",
                            f"{fid} 用「—（历史）」只在已验收时允许："
                            f"没挂需求的功能不能算已评审")
                else:
                    rids = [x for x in re.split(r"[、,，;；\s]+", reqcell) if x]
                    if not rids:
                        add(errors, rel, "E24",
                            f"{fid} 没写满足哪条需求（REQ-nnn，可多条用「、」分隔）")
                    for rid in rids:
                        if not req_pat.fullmatch(rid):
                            add(errors, rel, "E24",
                                f"{fid} 的「满足的需求」里有非法编号：{rid!r}")
                        elif rid not in req_ids:
                            add(errors, rel, "E24", f"{fid} 引用了不存在的需求 {rid}")
                        else:
                            feat_cover.add(rid)
                # 评审门（T5.1.2）：已评审及以后必须留下三问的结论；
                # 「—（历史）」只给未挂需求的存量行背书，不能给新功能背书。
                if st in ("已评审", "实施中", "已对照", "已验收"):
                    rv = strip_md(row[i_rv]) if i_rv is not None else ""
                    if rv in REF_PLACEHOLDERS:
                        add(errors, rel, "E24",
                            f"{fid} 是「{st}」却没有评审结论——"
                            f"先答三问（满足需求 / 可实现 / 代价合理）并写进「评审」列")
                    elif rv in LEGACY_REQ and reqcell not in LEGACY_REQ:
                        add(errors, rel, "E24",
                            f"{fid} 的评审写了「—（历史）」，但它挂着需求："
                            f"历史结论不能给新功能背书")
                if st in ("已对照", "已验收"):
                    tocell = strip_md(row[i_to]) if i_to is not None else ""
                    paths = [x for x in re.split(r"[、,，;；]+", tocell) if x] if tocell else []
                    paths = [x for x in paths if x not in ("—", "-", "无")]
                    if not paths:
                        add(errors, rel, "E24", f"{fid} 是「{st}」却没有代码入口")
                    for p in paths:
                        if not os.path.exists(os.path.join(repo_root, p)):
                            add(errors, rel, "E24", f"{fid} 的代码入口不存在：{p}")
                if st == "已验收":
                    if i_vf is None or verify_missing(row[i_vf]):
                        add(errors, rel, "E24", f"{fid} 已验收但缺 verify 命令")
                ev = strip_md(row[i_ev]) if i_ev is not None else ""
                if st == "已验收" and ev in REF_PLACEHOLDERS:
                    add(errors, rel, "E24", f"{fid} 已验收但没有证据（写命令/测试组号与日期）")
                # 证据里写「第 N 组」时，N 必须真的存在于 scripts/self_test.py
                if test_groups and ev:
                    for grp in re.findall(r"第\s*([\d、,，\s]+?)\s*组", ev):
                        for n in re.findall(r"\d+", grp):
                            if int(n) not in test_groups:
                                add(errors, rel, "E26",
                                    f"{fid} 的证据引用了不存在的自测组：第 {n} 组")
                # 考核门（E27）：考核下沉到任务后，功能行只留一行「考核汇总」——
                # 点名「各任务考核见 T…」加上整体一致 / 代价 / 结论；「完成于」仍是回滚锚点。
                # 存量行（—（历史））整行豁免：它们早于任务模型，不追溯。
                if st in ("已验收", "撤回") and reqcell not in LEGACY_REQ:
                    ac = strip_md(row[i_ac]) if i_ac is not None and i_ac < len(row) else ""
                    if ac in REF_PLACEHOLDERS:
                        add(errors, rel, "E27",
                            f"{fid} 是「{st}」却没有考核汇总：写一行 "
                            f"`各任务考核见 T1.1.1；整体一致：全｜代价：M（同估）｜结论：保留`")
                    elif not all(k in ac for k in ("一致", "代价", "结论")):
                        add(errors, rel, "E27",
                            f"{fid} 的考核汇总缺槽位：要同时写「整体一致 / 代价 / 结论」"
                            f"（四格在任务级，见 FEATURES 的「任务考核」表）")
                    elif st == "已验收" and "各任务考核见" not in ac:
                        add(errors, rel, "E27",
                            f"{fid} 的考核汇总没指出考核在哪：写「各任务考核见 T…」，"
                            f"让汇总可以逐条回溯到任务")
                    dn = strip_md(row[i_dn]) if i_dn is not None and i_dn < len(row) else ""
                    if st == "已验收" and (dn in REF_PLACEHOLDERS or dn == "待提交"):
                        add(errors, rel, "E27",
                            f"{fid} 已验收但没记「完成于」：写该功能验收时的 commit 短号"
                            f"（回滚到它之前就靠这个锚点；「待提交」不算记，ISS-046）")

        # ---- 契约增量（E19 / E20 / E21，T1.1.2）
        # 机器判据只覆盖 _delta/README.md 里能机械判的部分：目录与 status、
        # 锚点能否唯一匹配、归档后的 after 是否仍在目标里。README 本身不是 delta。
        if delta_prefix and rel.startswith(delta_prefix) and base != DELTA_README:
            archived = rel.startswith(delta_archive_prefix)
            status = fm.get("status", "")
            if archived and status != "snapshot":
                add(errors, rel, "E19",
                    f"归档 delta 的 status 应为 snapshot，实际 {status!r}"
                    f"（{DELTA_ARCHIVE}/ 是只读留档）")
            elif not archived and status != "proposed":
                add(errors, rel, "E19",
                    f"根目录只放未合并 delta（status 应为 proposed），实际 {status!r}；"
                    f"已合并的请移入 {DELTA_ARCHIVE}/ 并改 status: snapshot")
            elif not archived:
                add(errors, rel, "E19",
                    f"未合并的契约增量：{fm.get('delta_id') or base} 仍在根目录——"
                    f"先按锚点合并进 {fm.get('target') or '目标文件'}，"
                    f"再移入 {DELTA_ARCHIVE}/ 并改 status: snapshot")

            req_re = re.compile(rf"{re.escape(schema['ids']['req'])}-\d+")
            target = (fm.get("target") or "").strip()
            if not target:
                add(errors, rel, "E20", "缺 target（仓库根相对路径），无法核对锚点")
            elif not os.path.isfile(os.path.normpath(os.path.join(repo_root, target))):
                add(errors, rel, "E20", f"target 指向的文件不存在：{target}")
            else:
                ttext = read(os.path.normpath(os.path.join(repo_root, target)))
                changes, problems = parse_delta(body, schema["ids"]["req"])
                sup = (fm.get("superseded_by") or "").strip()
                if sup and sup not in delta_ids:
                    add(errors, rel, "E31",
                        f"superseded_by 指向不存在的 delta：{sup}"
                        f"（链条断了：被取代的一方要指到真实存在的 delta）")
                    sup = ""
                for c_code, msg in check_delta(changes, problems, ttext, archived, req_re,
                                               superseded=bool(sup)):
                    add(errors, rel, c_code, msg)
                header = requirement_header(ttext, req_re)
                row_code = "E21" if archived else "E20"
                for ch in changes:
                    for line in (ch["after"] or "").splitlines():
                        s = line.strip()
                        if not s.startswith("|"):
                            continue
                        cells = split_row(s)
                        ids = [strip_md(c) for c in cells if req_re.fullmatch(strip_md(c))]
                        if not ids:
                            continue
                        if header is None:
                            add(errors, rel, "E18",
                                f"{ids[0]} 增量行缺 verify:（目标表里没有 verify: 列）")
                            continue
                        if len(cells) != len(header):
                            add(errors, rel, row_code,
                                f"{ids[0]} 增量行有 {len(cells)} 列，主表是 {len(header)} 列")
                        vcol = verify_col(header)
                        if vcol is None:
                            add(errors, rel, "E18",
                                f"{ids[0]} 增量行缺 verify:（目标表里没有 verify: 列）")
                        elif vcol >= len(cells) or verify_missing(cells[vcol]):
                            add(errors, rel, "E18",
                                f"{ids[0]} 增量行缺 verify:（应写可执行命令或测试路径）")

        # ---- E16 术语旧称
        if aliases and layer in ALIAS_LAYERS and fm.get("status") not in ALIAS_SKIP_STATUS:
            for line in strip_code(body).splitlines():
                s = line.strip()
                if not s or not any(a in s for a in aliases):
                    continue
                if re.search(r"旧称|曾称|别名|原名|禁止写法|禁用别名", s):
                    continue
                bad = [a for a in aliases if a in s]
                add(errors, rel, "E16", "未登记的旧称 " + "、".join(bad) + "：" + s[:40])

        # ---- 链接（E7 / W6）
        for m in re.finditer(r"\]\(([^)\s]+)\)", strip_code(text)):
            target = m.group(1)
            if target.startswith(("http://", "https://", "mailto:", "#", "tel:")):
                continue
            clean = target.split("#")[0]
            if not clean:
                continue
            if os.path.isabs(clean) or re.match(r"^[A-Za-z]:[/\\]", clean):
                add(warns, rel, "W6", f"绝对路径：{target}")
                continue
            if not os.path.exists(os.path.normpath(
                    os.path.join(os.path.dirname(path), clean))):
                add(errors, rel, "E7", f"断链：{target}")

        # ---- W1 status 与正文自述冲突
        head = body[:300]
        decl = re.search(r"状态\s*[:：][^\n]{0,24}", head)
        if (fm.get("status") == "active" and decl
                and re.search(r"Proposed|提案|草案|待裁决|待评审|规划中|未实现|未实施", decl.group(0))):
            add(warns, rel, "W1", "status=active，但首段自述：" + decl.group(0).strip())

        # ---- ADR 索引里的链接（供 E11 双向比对）
        if adr_index_rel and rel == adr_index_rel:
            for m in re.finditer(r"\]\(([^)]*adr/[^)]+)\)", text):
                idx_links.add(os.path.basename(m.group(1)))

    # ---- W10 设计卡选项空间（REQ-021）：只判形状，不判广度
    design_path = os.path.join(docs, layer_dir(schema, "facade"),
                               names.get("design_card", "设计卡.md"))
    if os.path.exists(design_path):
        drel = os.path.relpath(design_path, docs).replace(os.sep, "/")
        for msg in design_card_problems(read(design_path), plan_status):
            add(warns, drel, "W10", msg)
        for msg in observability_problems(read(design_path), plan_status):
            add(warns, drel, "W12", msg)

    # ---- E11 索引双向一致
    if adr_index_rel and adr_files:
        actual = {os.path.basename(p) for p in adr_files}
        for name in sorted(actual - idx_links):
            add(errors, adr_index_rel, "E11", f"索引缺少 ADR 文件：{name}")
        for name in sorted(idx_links - actual):
            add(errors, adr_index_rel, "E11", f"索引指向不存在的 ADR 文件：{name}")

    # ---- E12 编号重复
    digits = schema["ids"]["digits"]
    for no, paths in sorted(adr_ids.items()):
        if len(paths) > 1:
            add(errors, ",".join(paths), "E12", f"{schema['ids']['adr']}-{no:0{digits}d} 编号重复")

    # ---- E15 取代链闭包
    ref_re = re.compile(rf"{re.escape(schema['ids']['adr'])}-(\d+)")
    for rel, (succ, sup) in sorted(adr_links.items()):
        if succ:
            ids = [int(n) for n in ref_re.findall(succ)]
            if not ids:
                if re.search(r"未标注|未记录|待补|待填", succ):
                    add(warns, rel, "W4", f"取代者未标注：{succ}")
                else:
                    add(errors, rel, "E15", f"superseded_by 不是 ADR 编号：{succ}")
            for n in ids:
                if n not in adr_states:
                    add(errors, rel, "E15", f"superseded_by 指向不存在的 ADR-{n:03d}")
                elif adr_states[n] == "superseded":
                    add(errors, rel, "E15", f"取代链未终止：ADR-{n:03d} 自己也是 superseded")
        if sup:
            for n in [int(x) for x in ref_re.findall(sup)]:
                if n not in adr_states:
                    add(errors, rel, "E15", f"supersedes 指向不存在的 ADR-{n:03d}")

    # ---- E29 同一原话在跨篇档案里重复建议
    for q, rels in idea_quotes.items():
        uniq = sorted(set(rels))
        if len(uniq) > 1:
            add(errors, uniq[-1], "E29",
                "同一原话在 %d 篇档案里重复建议：%s" % (len(uniq), q[:24]))

    # ---- W2 summary 重复
    for _s, rels in summaries.items():
        if len(rels) > 1:
            add(warns, ",".join(rels), "W2", "summary 重复")

    # ---- E9 层为空
    for lay, items in per_layer.items():
        if not items:
            d = layer_dir(schema, lay) or "?"
            add(errors, f"{d}/", "E9", f"层为空（{lay}）：加一篇，或从 _schema.json 删掉这层")

    # ---- W9 已验收 → 功能对照行（提醒不阻断：有行 ≠ 对照过；F-001–F-020 存量豁免）
    if check_table_seen:
        for fid in sorted(accepted_features):
            if int(fid.split("-")[1]) >= 21 and fid not in checked_features:
                add(warns, accepted_features[fid], "W9",
                    f"{fid} 已验收，但 40-运行/功能对照.md 没有它的行："
                    f"补一行对照，或写明为什么不需要；有行 ≠ 对照过")

    # ---- W8 需求 ↔ 功能对账：每条需求至少要有一个功能覆盖它（提醒不阻断：需求可以先写、功能后补）
    for rid in sorted(req_defs):
        if rid not in feat_cover:
            add(warns, req_defs[rid], "W8",
                f"{rid} 没有任何功能覆盖它：功能台账里没有引用这条需求")

    # ---- E17 棘轮基线
    baseline_path = os.path.join(docs, schema.get("baseline") or ".docs-baseline.json")
    cur = {c: sum(1 for x in errors + warns if x["code"] == c) for c in CODES}
    cur = {k: v for k, v in cur.items() if v}
    if update_baseline:
        with open(baseline_path, "w", encoding="utf-8", newline="\n") as fh:
            json.dump({"generated": today, "counts": cur}, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        print(f"baseline 已写入 {baseline_path}  {cur}")
        return 0
    if baseline_mode:
        if not os.path.exists(baseline_path):
            add(errors, "<baseline>", "E17", f"缺少基线文件 {baseline_path}，先跑 --update-baseline")
        else:
            try:
                base = json.loads(read(baseline_path)).get("counts", {})
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                add(errors, baseline_path, "E17",
                    f"基线文件解析失败：{exc}。删掉它再跑一次 --update-baseline")
                base = {}
            over = {c: n for c, n in cur.items() if n > base.get(c, 0)}
            for c, n in sorted(over.items()):
                add(errors, "<baseline>", "E17",
                    f"{c} 超出基线：{n} > {base.get(c, 0)}（存量债只许降；确属存量才 --update-baseline）")
            # 未超基线的存量错误降级为提醒：棘轮的意义是「今天不更坏」，不是「今天必须全绿」
            keep = []
            for e in errors:
                if e["code"] == "E17" or e["code"] in over:
                    keep.append(e)
                else:
                    e["message"] = "[存量] " + e["message"]
                    warns.append(e)
            errors[:] = keep

    # ---------------------------------------------------------------- 输出
    errors.sort(key=lambda x: (x["code"], x["file"]))
    warns.sort(key=lambda x: (x["code"], x["file"]))
    if as_json:
        print(json.dumps({
            "ok": not errors,
            "docs": len(files),
            "config": cfg_name,
            "per_layer": {k: len(v) for k, v in per_layer.items()},
            "errors": errors,
            "warnings": warns,
            "counts": cur,
        }, ensure_ascii=False, indent=2))
        return 1 if errors else 0

    print(f"docs: {len(files)} 篇   配置: {cfg_name or '内置默认'}")
    print("每层篇数: " + "  ".join(f"{k}={len(v)}" for k, v in per_layer.items()))
    if not quiet:
        for x in warns:
            print(f"  WARN  [{x['code']}] {x['file']}: {x['message']}")
        for x in errors:
            print(f"  ERROR [{x['code']}] {x['file']}: {x['message']}")
    print(f"errors={len(errors)}  warnings={len(warns)}")
    if any(w["code"] in ("W3", "W4", "W5") for w in warns):
        print("提示：W3/W4/W5 是待补类提醒，不阻断；收尾前应清零。")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
