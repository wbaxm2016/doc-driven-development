#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""代码地图：把「代码怎么走」抽成一份只读文档（REQ-068 / D24 / K57）。

为什么要有它：
    设计卡讲「为什么这样设计」、契约讲「必须成立什么」，都不讲**代码静态上怎么走**。
    想知道「`brief` 印出那一屏读了什么」，只能读 2550 行。这份地图把三件事抽出来：
    入口链（命令 → 处理函数 → 可达函数）、函数速查表（谁调我 / 我调谁 / 干什么）、
    对象速查表（类、模块级常量）。说明文字不猜，来自人写的 `代码地图-旁注.md`。

两条铁律：
    1. **生成的别手改**：`代码地图.md` 整篇由 `build` 重写；手改会在下次 `check` 报陈旧。
    2. **说明文字只有一处**：所有「干什么 / 从哪进来 / 失败时怎样 / 改它谁被牵连」写在旁注源里，
       地图只搬运。`check` 判三件事——覆盖率（有没有漏函数）、悬空（有没有指向不存在的函数）、
       陈旧（代码或旁注改了而地图没重跑），另报「同名重复定义」（ISS-142）。

机器判不了、也不假装判的（ADR-004 同款口径）：
    - 旁注写得对不对、是不是废话：人读。
    - 运行时才出现的调用（`getattr`、插件注册、装饰器注入）：`ast` 看不见，只能由入口表人工声明。
    - 纯开关脚本（`doc_check` / `verify` 这类）没有子命令：入口就是 `main`，入口表写「（无子命令）」。

用法：
    python scripts/codemap.py build [--docs DIR] [--code DIR] [--out PATH]
    python scripts/codemap.py check [--docs DIR] [--code DIR] [--json]

退出码：build 恒 0（除非输入缺失）；check 一致 0、不一致 1、输入缺失 2。
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys

# 旁注源与生成物的文件名（改这里一处，两边同时生效）
NOTES_NAME = "代码地图-旁注.md"
MAP_NAME = "代码地图.md"

# 旁注的四个说明格（顺序即渲染顺序；「干什么」必须写职责，不写代码步骤）
NOTE_CELLS = ("干什么", "从哪进来", "失败时怎样", "改它谁被牵连")


def die(msg, code=2):
    print("ERROR %s" % msg)
    return code


# ---------------------------------------------------------------- 定位

def find_docs(arg):
    """文档目录：显式参数 > 三个候选目录；找不到就返回 None（不假装找到了）。"""
    if arg:
        return arg if os.path.isdir(arg) else None
    for cand in ("docs", "文档", "documentation"):
        if os.path.isdir(cand):
            return cand
    return None


def arch_dir(docs):
    """架构层目录。层名从 `_schema.json` 读；读不到就退回 `10-架构`（不静默换地方）。"""
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(here)
    cfg = os.path.join(docs, "_schema.json")
    if os.path.exists(cfg):
        try:
            with open(cfg, encoding="utf-8") as fh:
                schema = json.load(fh)
            name = (schema.get("layers") or {}).get("architecture")
            if name:
                return os.path.join(docs, name)
        except (ValueError, OSError):
            pass
    return os.path.join(docs, "10-架构")


# ---------------------------------------------------------------- 抽代码

def module_functions(tree):
    """模块级函数 + 类方法；返回 [(限定名, 节点)]。函数体内的嵌套函数不收（它们没有独立身份）。"""
    out = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out.append((node.name, node))
        elif isinstance(node, ast.ClassDef):
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    out.append(("%s.%s" % (node.name, sub.name), sub))
    return out


def names_in(node):
    """函数体里出现的本地函数名：(被调用, 只被引用)。类方法按短名收，`ctx.load()` 也算 `load`。"""
    called, refd = set(), set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            fn = sub.func
            if isinstance(fn, ast.Name):
                called.add(fn.id)
            elif isinstance(fn, ast.Attribute):
                called.add(fn.attr)
                if isinstance(fn.value, ast.Name):
                    called.add("%s.%s" % (fn.value.id, fn.attr))
        elif isinstance(sub, ast.Name):
            refd.add(sub.id)
    return called, refd


def scan_module(path):
    """一个脚本的全部结构。返回 dict；解析失败抛 SyntaxError 由调用方兜。"""
    src = open(path, encoding="utf-8").read()
    tree = ast.parse(src)
    funcs = module_functions(tree)
    fq = [q for q, _ in funcs]
    short2q = {}
    for q in fq:
        short2q.setdefault(q.split(".")[-1], set()).add(q)

    calls, refs = {}, {}
    for qual, node in funcs:
        c, r = names_in(node)
        tgt = set()
        for x in c:
            tgt |= {q for q in short2q.get(x, set()) if q != qual}
            if x in fq and x != qual:
                tgt.add(x)
        calls[qual] = tgt
        refs[qual] = {q for x in (r - c) for q in short2q.get(x, set()) if q != qual}

    callers = {q: set() for q in fq}
    for src_q, dsts in calls.items():
        for d in dsts:
            callers[d].add(src_q)

    classes = [n.name for n in tree.body if isinstance(n, ast.ClassDef)]
    consts = []
    for n in tree.body:
        if isinstance(n, ast.Assign):
            for t in n.targets:
                if isinstance(t, ast.Name) and t.id.isupper():
                    consts.append((t.id, n.lineno))
    const_users = {}
    for cname, _ln in consts:
        users = {q for q, node in funcs if cname in names_in(node)[0] | names_in(node)[1]}
        const_users[cname] = users

    dup = {}
    for q in fq:
        dup[q] = fq.count(q)

    return {
        "file": os.path.basename(path),
        "lines": len(src.splitlines()),
        "funcs": funcs,
        "fq": fq,
        "calls": calls,
        "callers": callers,
        "refs": refs,
        "classes": classes,
        "consts": consts,
        "const_users": const_users,
        "dup": {k: v for k, v in dup.items() if v > 1},
        "parser_subs": parser_subs(tree),
    }


def parser_subs(tree):
    """`add_parser("x")` 建出来的子命令名，用于和入口表对账。"""
    subs = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr == "add_parser" and node.args:
            a0 = node.args[0]
            if isinstance(a0, ast.Constant) and isinstance(a0.value, str):
                subs.append(a0.value)
    return subs


def reach(mod, root):
    """从 root 出发沿调用边做传递闭包。"""
    seen, stack = set(), [root]
    while stack:
        cur = stack.pop()
        for nxt in mod["calls"].get(cur, ()):
            if nxt not in seen:
                seen.add(nxt)
                stack.append(nxt)
    return seen


# ---------------------------------------------------------------- 读旁注

def split_row(line):
    """切表格行：按未转义的 `|` 切，`\\|` 还原成 `|`。与 devlog / doc_check 同口径（ISS-070）。"""
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|") and not s.endswith("\\|"):
        s = s[:-1]
    out, cur, i = [], "", 0
    while i < len(s):
        if s[i] == "\\" and i + 1 < len(s) and s[i + 1] == "|":
            cur += "|"
            i += 2
            continue
        if s[i] == "|":
            out.append(cur.strip())
            cur = ""
        else:
            cur += s[i]
        i += 1
    out.append(cur.strip())
    return out


def is_sep(cells):
    return all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c != "")


def read_notes(path):
    """解析旁注源：入口表 + 每个脚本一节函数旁注。缺文件返回 None。"""
    if not os.path.exists(path):
        return None
    text = open(path, encoding="utf-8").read()
    entries, notes = [], {}
    section, current = None, None
    fence = False
    for raw in text.splitlines():
        line = raw.rstrip()
        # 围栏里的内容是「怎么写」的示例，不是声明本身：跳过，免得示例被当成真入口
        if line.startswith("```"):
            fence = not fence
            continue
        if fence:
            continue
        if line.startswith("## "):
            section = line[3:].strip()
            current = None
            continue
        if line.startswith("### "):
            current = line[4:].strip()
            continue
        if not line.strip().startswith("|"):
            continue
        cells = split_row(line)
        if is_sep(cells) or cells and cells[0] in ("脚本", "函数"):
            continue
        if section == "入口表" and len(cells) >= 3:
            entries.append((cells[0].strip("`"), cells[1].strip("`"), cells[2].strip("`")))
        elif section == "函数旁注" and current:
            notes[(current, cells[0].strip("`"))] = cells[1:]
    return {"entries": entries, "notes": notes, "path": path}


# ---------------------------------------------------------------- 渲染

def esc(s):
    return (s or "").replace("|", "\\|")


def inputs_date(code_dir, notes_path):
    """`updated` 取「最新一份输入」的日期：代码与旁注源里最新的文件 mtime。

    不取今天——取今天会让同一份代码在不同日期生成出不同文本，`check` 每天误报陈旧。
    """
    import datetime
    stamps = []
    for name in os.listdir(code_dir):
        if name.endswith(".py"):
            stamps.append(os.path.getmtime(os.path.join(code_dir, name)))
    if os.path.exists(notes_path):
        stamps.append(os.path.getmtime(notes_path))
    if not stamps:
        return datetime.date.today().isoformat()
    d = datetime.date.fromtimestamp(max(stamps))
    today = datetime.date.today()
    return (d if d <= today else today).isoformat()


def render(mods, notes, entries, updated="", ):
    out = []
    out.append("---")
    out.append('title: "代码地图"')
    out.append("layer: architecture")
    out.append("domain: 全局")
    out.append("status: active")
    out.append("authority: 3")
    out.append("updated: %s" % (updated or ""))
    out.append('summary: "生成区：入口链 / 函数速查表 / 对象速查表；源是代码与代码地图-旁注.md。"')
    out.append("tags: [架构, 代码地图, 生成区]")
    out.append("---")
    out.append("")
    out.append("# 代码地图")
    out.append("")
    out.append("> **生成区，勿手改。** 由 `python scripts/codemap.py build` 从代码与")
    out.append("> `%s` 重算；手改会在下次 `check` 报陈旧。" % NOTES_NAME)
    out.append(">")
    out.append("> 四格的读法：**干什么**（一句话职责）/ **从哪进来**（输入从哪到它）/"
               "**失败时怎样**（出错时停在哪）/ **改它谁被牵连**（反向依赖）。")
    out.append("> 「谁调我 / 我调谁」由代码静态抽出，含「被当值传出」的引用；运行时动态派发抽不到，")
    out.append("> 那部分靠 `%s` 的入口表人工声明。" % NOTES_NAME)
    out.append("")

    total_f = sum(len(mo["fq"]) for mo in mods)
    noted = sum(1 for mo in mods for q in mo["fq"] if (mo["file"], q) in notes["notes"])
    out.append("## 总览")
    out.append("")
    out.append("| 脚本 | 行 | 函数 | 命令 | 有旁注 | 类 | 常量 |")
    out.append("|---|---|---|---|---|---|---|")
    for mo in mods:
        cmds = [c for (s, c, h) in entries if s == mo["file"]]
        got = sum(1 for q in mo["fq"] if (mo["file"], q) in notes["notes"])
        out.append("| %s | %d | %d | %d | %d/%d | %d | %d |"
                   % (mo["file"], mo["lines"], len(mo["fq"]), len(cmds), got,
                      len(mo["fq"]), len(mo["classes"]), len(mo["consts"])))
    out.append("| **合计** | %d | %d | %d | %d/%d | %d | %d |"
               % (sum(m["lines"] for m in mods), total_f,
                  len(entries), noted, total_f,
                  sum(len(m["classes"]) for m in mods),
                  sum(len(m["consts"]) for m in mods)))
    out.append("")

    for mo in mods:
        out.append("## %s" % mo["file"])
        out.append("")
        cmds = [(c, h) for (s, c, h) in entries if s == mo["file"]]
        if cmds:
            out.append("**入口**")
            out.append("")
            out.append("| 命令 | 处理函数 | 从它出发可达 |")
            out.append("|---|---|---|")
            for c, h in cmds:
                if h in mo["calls"]:
                    out.append("| `%s` | `%s` | %d 个函数 |" % (c, h, len(reach(mo, h)) + 1))
                else:
                    out.append("| `%s` | `%s` | — 入口表点名的函数不存在 |" % (c, h))
            out.append("")
        else:
            out.append("> 入口表里没有这个脚本的命令声明。")
            out.append("")

        out.append("**函数速查表**")
        out.append("")
        out.append("| 函数 | 行 | 干什么 | 从哪进来 | 失败时怎样 | 改它谁被牵连 | 谁调我 | 我调谁 |")
        out.append("|---|---|---|---|---|---|---|---|")
        for qual, node in mo["funcs"]:
            cell = notes["notes"].get((mo["file"], qual), [""] * len(NOTE_CELLS))
            cell = list(cell) + [""] * (len(NOTE_CELLS) - len(cell))
            callers = sorted(mo["callers"].get(qual, ()))
            callees = sorted(mo["calls"].get(qual, ()))
            mark = "（重复定义 ×%d）" % mo["dup"][qual] if qual in mo["dup"] else ""
            out.append("| `%s`%s | %d | %s | %s | %s | %s | %s | %s |" % (
                qual, mark, node.lineno,
                esc(cell[0]), esc(cell[1]), esc(cell[2]), esc(cell[3]),
                esc("、".join(callers)) or "—",
                esc("、".join(callees)) or "—",
            ))
        out.append("")

        if mo["classes"] or mo["consts"]:
            out.append("**对象速查表**")
            out.append("")
            out.append("| 名字 | 种类 | 行 | 谁在用 |")
            out.append("|---|---|---|---|")
            for cname in mo["classes"]:
                users = sorted(q for q in mo["fq"]
                               if cname in (names_in(dict(mo["funcs"])[q])[0]
                                            | names_in(dict(mo["funcs"])[q])[1]))
                out.append("| `%s` | 类 | — | %s |"
                           % (cname, esc("、".join(users)) or "—"))
            for cname, ln in mo["consts"]:
                users = sorted(mo["const_users"].get(cname, ()))
                out.append("| `%s` | 常量 | %d | %s |"
                           % (cname, ln, esc("、".join(users)) or "—"))
            out.append("")

    return "\n".join(out) + "\n"


# ---------------------------------------------------------------- 校验

def check_all(mods, notes, entries):
    """五类问题：缺旁注源 / 覆盖 / 悬空 / 重复定义 / 入口表对不上。返回 (errors, warnings)。

    **覆盖范围由入口表声明**：只有入口表里出现过的脚本才要求「每个函数都有一行说明」。
    这样新项目里被 `doc_init` 拷进来的工具脚本（还没人写旁注）只提醒、不阻断——
    否则 `check` 会在一个新项目里永远红，门禁从第一天就被绕过。
    """
    errors, warnings = [], []
    if notes is None:
        return (["找不到旁注源 `%s`：先建它，再跑 build（不猜、不生成空说明）" % NOTES_NAME],
                warnings)

    scope = {s for (s, _c, _h) in entries}
    known = set()
    for mo in mods:
        for q in mo["fq"]:
            known.add((mo["file"], q))

    # 0) 范围声明：没进入口表的脚本只提醒
    for mo in mods:
        if mo["file"] not in scope:
            warnings.append("%s 没进入口表：不纳入地图（要纳入就在入口表里声明它的入口）"
                            % mo["file"])

    # 1) 覆盖：范围内的每个函数都要有一行
    for mo in mods:
        if mo["file"] not in scope:
            continue
        miss = [q for q in mo["fq"] if (mo["file"], q) not in notes["notes"]]
        if miss:
            errors.append("%s：%d 个函数在旁注里没有说明（%s%s）"
                          % (mo["file"], len(miss), "、".join(miss[:5]),
                             " …" if len(miss) > 5 else ""))

    # 2) 悬空：旁注指向不存在的函数
    for key in sorted(notes["notes"]):
        if key not in known:
            errors.append("旁注里的 `%s · %s` 在代码里不存在：函数改名或删了，旁注没跟上"
                          % (key[0], key[1]))

    # 3) 重复定义（ISS-142）
    for mo in mods:
        for q, n in sorted(mo["dup"].items()):
            errors.append("%s 的 `%s` 定义了 %d 次：后一个静默覆盖前一个，改前一个不会生效"
                          % (mo["file"], q, n))

    # 4) 入口表点名的函数必须存在
    for script, cmd, handler in entries:
        mod = next((m for m in mods if m["file"] == script), None)
        if mod is None:
            errors.append("入口表里的脚本 `%s` 不存在" % script)
        elif handler not in ("（无）", "—") and handler not in mod["fq"]:
            errors.append("入口表 `%s · %s` 指向的 `%s` 不存在" % (script, cmd, handler))

    # 5) 代码里有子命令、入口表里没有 → 提醒（不阻断：默认分支靠兜底，机器认不出）
    for mo in mods:
        declared = {c for (s, c, _h) in entries if s == mo["file"]}
        for sub in mo["parser_subs"]:
            if sub not in declared:
                warnings.append("%s 有子命令 `%s` 但入口表没登记（机器认不出它的处理函数，得人写）"
                                % (mo["file"], sub))
    return errors, warnings


# ---------------------------------------------------------------- 主流程

def load_modules(code_dir):
    mods = []
    for name in sorted(os.listdir(code_dir)):
        if not name.endswith(".py"):
            continue
        path = os.path.join(code_dir, name)
        mods.append(scan_module(path))
    return mods


def main(argv=None):
    ap = argparse.ArgumentParser(description="代码地图：从代码与旁注生成 / 校验实现文档")
    ap.add_argument("action", choices=("build", "check"))
    ap.add_argument("--docs", default=None, help="文档目录（默认自动探测 docs / 文档 / documentation）")
    ap.add_argument("--code", default="scripts", help="被扫描的代码目录（默认 scripts）")
    ap.add_argument("--json", action="store_true", help="只给机读结论")
    args = ap.parse_args(argv)

    docs = find_docs(args.docs)
    if docs is None:
        return die("找不到文档目录（docs/ 文档/ documentation）。用 --docs 指定。")
    if not os.path.isdir(args.code):
        return die("找不到代码目录：%s。用 --code 指定。" % args.code)

    adir = arch_dir(docs)
    notes_path = os.path.join(adir, NOTES_NAME)
    map_path = os.path.join(adir, MAP_NAME)
    updated = inputs_date(args.code, notes_path)

    try:
        mods = load_modules(args.code)
    except SyntaxError as exc:
        return die("代码解析失败：%s（%s）" % (exc.msg, exc.filename))

    notes = read_notes(notes_path)
    entries = (notes or {}).get("entries", [])
    scoped = [mo for mo in mods if mo["file"] in {s for (s, _c, _h) in entries}]
    errors, warnings = check_all(mods, notes, entries)

    if args.action == "check":
        stale = False
        if notes is None or not scoped:
            # 旁注还没声明任何入口（新项目刚铺骨架）：没有要渲染的东西，不要求地图存在
            pass
        else:
            text = render(scoped, notes, notes["entries"], updated)
            if not os.path.exists(map_path):
                errors.append("还没有 `%s`：先跑一次 build" % os.path.relpath(map_path, docs))
            else:
                stale = open(map_path, encoding="utf-8").read() != text
                if stale:
                    errors.append("`%s` 与当前代码 / 旁注不一致：跑一次 build" %
                                  os.path.relpath(map_path, docs))
        if args.json:
            print(json.dumps({"ok": not errors, "errors": errors, "warnings": warnings},
                             ensure_ascii=False, indent=2))
        else:
            for e in errors:
                print("ERROR %s" % e)
            for w in warnings:
                print("WARN  %s" % w)
            print("errors=%d warnings=%d" % (len(errors), len(warnings)))
        return 0 if not errors else 1

    if notes is None:
        return die("找不到旁注源 `%s`：先建它（入口表 + 每个函数一行），再跑 build。"
                   % os.path.relpath(notes_path, docs))
    text = render(scoped, notes, notes["entries"], updated)
    os.makedirs(os.path.dirname(map_path), exist_ok=True)
    with open(map_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    for w in warnings:
        print("WARN  %s" % w)
    print("built: %s（%d 个脚本 / %d 个函数）"
          % (os.path.relpath(map_path, docs), len(mods), sum(len(m["fq"]) for m in mods)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
