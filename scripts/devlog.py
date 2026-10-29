#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""过程档案工具：建档 / 校验 / 时间线。

用法：
    python scripts/devlog.py new --title "主题" [--date 2026-10-29] [--scope 范围]
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
    "names": {"inbox": "问题收件箱.md", "timeline": "时间线.md",
              "session_template": "会话档案模板.md", "sessions_dir": "会话"},
    "ids": {"issue": "ISS", "digits": 3},
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
    if arg:
        return arg if os.path.isdir(arg) else None
    here = os.path.dirname(os.path.abspath(__file__))
    for root in (os.path.dirname(here), os.getcwd()):
        for name in ("docs", "文档", "documentation"):
            p = os.path.join(root, name)
            if os.path.isdir(p):
                return p
    return None


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
        self.docs = docs
        self.pdir = os.path.join(docs, pdir)
        n = schema["names"]
        self.sess = os.path.join(self.pdir, n["sessions_dir"])
        self.inbox = os.path.join(self.pdir, n["inbox"])
        self.timeline = os.path.join(self.pdir, n["timeline"])
        self.template = os.path.join(self.pdir, n["session_template"])
        self.schema = schema

    def sessions(self):
        if not os.path.isdir(self.sess):
            return []
        return sorted(os.path.join(self.sess, f)
                      for f in os.listdir(self.sess) if f.endswith(".md"))


# ---------------------------------------------------------------- new
def cmd_new(ctx, args):
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


def cmd_check(ctx, as_json=False):
    errors, warns = [], []
    sections = ctx.schema["session_sections"]
    ids, rows, dups = parse_inbox(ctx)

    for d in dups:
        errors.append({"file": os.path.basename(ctx.inbox), "code": "D1",
                       "message": f"{d} 编号重复（done 条目应移入「已闭环」并从主表删除）"})
    for r in rows:
        if r["state"] == "deferred" and not r["back"]:
            errors.append({"file": os.path.basename(ctx.inbox), "code": "D2",
                           "message": f"{r['id']} 为 deferred 但缺「回到条件」"})

    for path in ctx.sessions():
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

        m = re.search(r"(?ms)^##\s+[^\n]*交接[^\n]*\n(.*)$", text)
        if m and len(re.sub(r"[>\-*#\s]", "", m.group(1))) < 40:
            warns.append({"file": rel, "code": "S6", "message": "交接段过短，可能没写可执行下一步"})

        base = os.path.basename(path)
        expect = f"{fm.get('session_date', '')}-{fm.get('session_no', '')}-"
        if fm.get("session_date") and not base.startswith(expect):
            errors.append({"file": rel, "code": "S7", "message": f"文件名应以 {expect} 开头"})

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
    if args.cmd == "check":
        return cmd_check(ctx, as_json)
    return cmd_index(ctx, args.check)


if __name__ == "__main__":
    sys.exit(main())
