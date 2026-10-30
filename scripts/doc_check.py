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

# 码表：顺序即打印顺序，也用于 --json 的 counts
CODES = ["E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8", "E9", "E10",
         "E11", "E12", "E13", "E14", "E15", "E16", "E17", "E18",
         "E19", "E20", "E21",
         "W1", "W2", "W3", "W4", "W5", "W6", "W7"]


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


def read_tables(text):
    """极简 Markdown 表解析：返回 [(header, rows)]。"""
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
        for cell in s.strip("|").split("|"):
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


def check_delta(changes, problems, target_text, archived, req_re):
    """返回 [(code, message)]：proposed 按 _delta/README.md §5 判冲突，归档判合并结果。"""
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
                cells = [c.strip() for c in line.strip().strip("|").split("|")]
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
                for c_code, msg in check_delta(changes, problems, ttext, archived, req_re):
                    add(errors, rel, c_code, msg)
                header = requirement_header(ttext, req_re)
                row_code = "E21" if archived else "E20"
                for ch in changes:
                    for line in (ch["after"] or "").splitlines():
                        s = line.strip()
                        if not s.startswith("|"):
                            continue
                        cells = [c.strip() for c in s.strip("|").split("|")]
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

    # ---- W2 summary 重复
    for _s, rels in summaries.items():
        if len(rels) > 1:
            add(warns, ",".join(rels), "W2", "summary 重复")

    # ---- E9 层为空
    for lay, items in per_layer.items():
        if not items:
            d = layer_dir(schema, lay) or "?"
            add(errors, f"{d}/", "E9", f"层为空（{lay}）：加一篇，或从 _schema.json 删掉这层")

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
