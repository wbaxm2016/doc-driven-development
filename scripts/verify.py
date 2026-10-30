#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""按契约的 `verify:` 真跑可执行入口（T1.2.3）。

用法：
    python scripts/verify.py [--root .] [--docs docs] [--timeout 300] [--quiet] [--dry-run] [--strict]

做什么：
    * 读契约层里带 REQ 编号的表格行，取 `verify:` 单元格里**第一个反引号包住的命令**；
    * 逐条执行（同一命令只跑一次，多条需求共用同一条命令时合并结果）；
    * 任一命令失败、超时，或需求行缺 verify，退出码 1；环境/配置问题退出码 2。

不做什么：
    * 不判「有没有 verify:」——那是 doc_check 的 E18；这里只负责「跑」；
    * 不判测试写得对不对——命令自己退出 0 才算过，这是它唯一的口径。

跳过规则：需求行状态是 `待实现 / 待开工 / 未实现 / 阻塞 / 搁置` 时跳过。
这样铺完骨架的新项目不会因为示例行（指向尚不存在的测试）一上来就红；
状态改成「已实现」后，verify 必须真的跑通——状态只被证据推进。
**跳过不等于通过**（ISS-019）：每次都会打印跳过条数；`--strict` 下跳过即失败，
成熟项目应该用它，否则「全部实现」这件事永远缺证据。

设计：
    * 命令来自仓库自己的契约，等同代码评审的一部分；`--dry-run` 可先看要跑什么；
    * 每个子进程都带超时（默认 300 秒），超时按失败处理；
    * 只用标准库，兼容 Python 3.8；表格解析复用 doc_check，避免两套解析漂移。
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
try:
    import doc_check as dc
except ImportError:  # 安装不完整时给一句人话，不抛回溯
    print("ERROR 找不到 doc_check.py（应与 verify.py 同在 scripts/），无法解析契约表")
    sys.exit(2)

SKIP_STATES = {"待实现", "待开工", "未实现", "阻塞", "搁置"}
CMD_RE = re.compile(r"`([^`\n]+)`")


def find_docs(root, explicit):
    if explicit:
        return explicit if os.path.isabs(explicit) else os.path.join(root, explicit)
    for cand in ("docs", "文档", "documentation"):
        p = os.path.join(root, cand)
        if os.path.isdir(p):
            return p
    return None


def status_col(header):
    for i, h in enumerate(header):
        if "状态" in dc.strip_md(h):
            return i
    return None


def command_of(cell):
    m = CMD_RE.search(cell)
    return m.group(1).strip() if m else ""


def collect(docs, schema):
    """返回 [(REQ 编号, 文件, 状态, 命令或 None, 问题或 None)]。"""
    cdir = dc.layer_dir(schema, "contract")
    if not cdir:
        return []
    base = os.path.join(docs, cdir)
    req_re = re.compile(rf"{re.escape(schema['ids']['req'])}-\d+")
    out = []
    for dp, _dn, fn in os.walk(base):
        for f in sorted(fn):
            if not f.lower().endswith(".md") or f == "README.md":
                continue
            path = os.path.join(dp, f)
            rel = os.path.relpath(path, docs).replace(os.sep, "/")
            _fm, body = dc.parse_fm(dc.read(path))
            for header, rows in dc.read_tables(dc.strip_fences(body)):
                vcol = dc.verify_col(header)
                scol = status_col(header)
                for row in rows:
                    ids = [dc.strip_md(c) for c in row
                           if req_re.fullmatch(dc.strip_md(c))]
                    if not ids:
                        continue
                    status = (dc.strip_md(row[scol])
                              if scol is not None and scol < len(row) else "")
                    if status in SKIP_STATES:
                        out.append((ids[0], rel, status, None, None))
                        continue
                    if vcol is None or vcol >= len(row) or dc.verify_missing(row[vcol]):
                        out.append((ids[0], rel, status, None,
                                    "缺 verify:（doc_check 的 E18 负责判缺）"))
                        continue
                    cmd = command_of(row[vcol])
                    if not cmd:
                        out.append((ids[0], rel, status, None,
                                    "verify: 未用反引号包住命令，无法安全执行"))
                    elif "verify.py" in cmd:
                        out.append((ids[0], rel, status, None,
                                    "verify: 指向 verify.py 自己（会递归）"))
                    else:
                        out.append((ids[0], rel, status, cmd, None))
    return out


def run_command(cmd, root, timeout):
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    try:
        p = subprocess.run(cmd, shell=True, cwd=root, timeout=timeout,
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", env=env)
    except subprocess.TimeoutExpired:
        return None, f"超时（>{timeout}s）"
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def main():
    ap = argparse.ArgumentParser(description="按契约 verify: 真跑可执行入口")
    ap.add_argument("--root", default=os.path.dirname(HERE),
                    help="命令的工作目录（默认 scripts/ 的上一级）")
    ap.add_argument("--docs", default=None, help="文档目录（默认找 docs/ 文档/ documentation）")
    ap.add_argument("--timeout", type=int, default=300, help="每条命令的超时秒数（默认 300）")
    ap.add_argument("--quiet", action="store_true", help="只打印失败与汇总")
    ap.add_argument("--dry-run", action="store_true", help="只列出要跑的命令，不执行")
    ap.add_argument("--strict", action="store_true",
                    help="被状态跳过的需求也算失败（成熟项目用；默认只提醒）")
    args = ap.parse_args()

    root = os.path.abspath(args.root)
    docs = find_docs(root, args.docs)
    if not docs or not os.path.isdir(docs):
        print(f"ERROR 找不到文档目录（已试 docs/ 文档/ documentation）：{docs or '(无)'}。用 --docs 指定。")
        return 2
    try:
        schema, _cfg = dc.load_schema(docs)
    except dc.SchemaError as exc:
        print(f"ERROR {exc}")
        return 2

    items = collect(docs, schema)
    if not items:
        print("契约行 0 条：没有带 REQ 编号的需求表行，无可执行入口。")
        return 0

    # 先把「缺 verify / 无法执行」判失败：CI 不能把「没得跑」当成「跑过了」
    failures = 0
    skipped = 0
    pending = []
    for rid, rel, status, cmd, problem in items:
        if problem:
            failures += 1
            print(f"FAIL {rid}  {problem}  [{rel}]")
        elif cmd is None:
            skipped += 1
            if not args.quiet:
                print(f"SKIP {rid}  状态={status}")
        else:
            pending.append((rid, cmd))

    # 同一命令只跑一次：多条需求可以共用同一个测试入口
    by_cmd = {}
    for rid, cmd in pending:
        by_cmd.setdefault(cmd, []).append(rid)

    passed = 0
    for i, (cmd, rids) in enumerate(by_cmd.items(), 1):
        names = "、".join(sorted(rids))
        if args.dry_run:
            print(f"DRY  {names}  {cmd}")
            continue
        if not args.quiet:
            print(f"RUN  [{i}/{len(by_cmd)}] {names}  {cmd}")
        code, output = run_command(cmd, root, args.timeout)
        if code == 0:
            passed += len(rids)
            if not args.quiet:
                print(f"PASS {names}")
            continue
        failures += len(rids)
        print(f"FAIL {names}  " + (output.splitlines()[0] if code is None and output else f"exit={code}"))
        if output:
            print("  ---- 输出 ----")
            for line in output.rstrip().splitlines():
                print("  " + line)
            print("  ------------")

    if args.dry_run:
        print(f"verify: contracts={len(items)} commands={len(by_cmd)} "
              f"skipped={skipped} failures={failures}（dry-run，未执行）")
        return 1 if failures else 0

    print(f"verify: contracts={len(items)} commands={len(by_cmd)} "
          f"passed={passed} failed={failures} skipped={skipped}")
    # 跳过不等于通过：不把这句话打出来，"全部绿"就会把「没验过」也算进去（ISS-019）
    if skipped:
        print(f"WARN  跳过 {skipped} 条（状态=待实现/待开工/未实现/阻塞/搁置）："
              f"它们既没被验证，也没被算作失败；成熟项目用 --strict 让跳过直接失败")
    if args.strict and skipped:
        return 1
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
