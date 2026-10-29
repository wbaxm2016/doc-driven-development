#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""docs/ 全库校验：front-matter / 链接 / ADR 结构 / 取代链 / 术语 / 棘轮基线。

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

# 码表：顺序即打印顺序，也用于 --json 的 counts
CODES = ["E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8", "E9", "E10",
         "E11", "E12", "E13", "E14", "E15", "E16", "E17",
         "W1", "W2", "W3", "W4", "W5", "W6", "W7"]


# ---------------------------------------------------------------- 基础工具
def read(path):
    with open(path, encoding="utf-8") as fh:
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
        data[m.group(1)] = val
    return data, body


def strip_code(text):
    """剔除围栏代码块与行内代码，链接检查只看真实正文。"""
    text = re.sub(r"(?ms)^[ \t]*(```|~~~).*?^[ \t]*\1", "", text)
    return re.sub(r"`[^`\n]*`", "", text)


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


# ---------------------------------------------------------------- 配置
def load_schema(docs):
    for name in ("_schema.json", "_layers.json"):
        cfg = os.path.join(docs, name)
        if os.path.exists(cfg):
            raw = json.loads(read(cfg))
            merged = json.loads(json.dumps(DEFAULT_SCHEMA))
            for k, v in raw.items():
                if isinstance(v, dict) and isinstance(merged.get(k), dict):
                    merged[k].update(v)
                else:
                    merged[k] = v
            return merged, name
    return json.loads(json.dumps(DEFAULT_SCHEMA)), None


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

    schema, cfg_name = load_schema(docs)
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
        if schema["ears"].get("enabled", True) and layer == "contract":
            req_re = re.compile(rf"{re.escape(schema['ids']['req'])}-\d+")
            for line in strip_code(body).splitlines():
                if not req_re.search(line) or not line.strip().startswith("|"):
                    continue
                cells = [c.strip() for c in line.strip().strip("|").split("|")]
                joined = " ".join(c for c in cells if not req_re.fullmatch(strip_md(c)))
                if joined and not any(cue in joined for cue in EARS_CUES):
                    add(warns, rel, "W7",
                        f"{req_re.search(line).group(0)} 未见规范措辞/触发条件：" + joined[:40])

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
            base = json.loads(read(baseline_path)).get("counts", {})
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
