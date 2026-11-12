#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""自身参考实现：给本技能的组件与五连跑留一条可回看的运行记录。

用法：
    python scripts/observe.py run [--name N] [--run-id R] [--expected T] -- <命令...>
    python scripts/observe.py five-run [--run-id R]   # 与收尾五连跑同序：先重建生成区，最后全库校验
    python scripts/observe.py show <run_id> [--json]
    python scripts/observe.py status [--limit N] [--check]
    python scripts/observe.py trend [--limit N] [--since DATE] [--json]

记录落 `.dd/observe/runs/<run_id>.jsonl`，一行一个 span。v0 字段见
`docs/00-门面/设计卡.md` K27；四问是记录内容，四维是验收框架。

硬边界：
    - 观测是旁路：写记录失败只把 `record_status` 标成 `degraded`，**不改变**
      被包裹命令的退出码；`status --check` 只报证据缺口、exit 0。
    - 只用标准库，兼容 Python 3.8。
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import re
import subprocess
import sys
import uuid

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERSION_FILE = os.path.join(ROOT, "VERSION")
CODE_RE = re.compile(r"\[([EWDSP]\d+)\]")
FILE_RE = re.compile(r"((?:[\w\-.]+/)*[\w\-.]+\.(?:md|py|ya?ml|json)):(\d+)")


def now_iso():
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def tool_version():
    try:
        with open(VERSION_FILE, encoding="utf-8-sig") as fh:
            return fh.read().strip() or "unknown"
    except OSError:
        return "unknown"


def observe_dir(cwd, override=None):
    if override:
        return os.path.abspath(override)
    return os.path.join(os.path.abspath(cwd), ".dd", "observe")


def input_refs(cwd):
    """最小输入引用：有 docs/_schema.json 就记它的 sha256；没有就空。"""
    path = os.path.join(cwd, "docs", "_schema.json")
    if not os.path.exists(path):
        return []
    try:
        with open(path, "rb") as fh:
            digest = hashlib.sha256(fh.read()).hexdigest()
        return [{"path": "docs/_schema.json", "sha256": digest}]
    except OSError:
        return []


def findings_from(text, span):
    """从输出里抽规则码；`key` 只用 码:span，不用行号（行号会漂）。"""
    out = []
    for line in text.splitlines():
        m = CODE_RE.search(line)
        if not m:
            continue
        code = m.group(1)
        fm = FILE_RE.search(line)
        out.append({
            "key": f"{code}:{span}",
            "code": code,
            "file": fm.group(1) if fm else "",
            "line": int(fm.group(2)) if fm else 0,
            "message": line.strip(),
        })
    return out


def write_record(obs_dir, rec):
    """写一条记录；失败返回 degraded + 原因，不抛。"""
    try:
        runs = os.path.join(obs_dir, "runs")
        os.makedirs(runs, exist_ok=True)
        path = os.path.join(runs, rec["run_id"] + ".jsonl")
        with open(path, "a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return "ok", ""
    except OSError as exc:
        return "degraded", str(exc)


def resolve_command(cmd, cwd):
    """`python script.py` 的简写：首项以 .py 结尾且文件存在时补解释器。"""
    if not cmd:
        return cmd
    first = cmd[0]
    if first.endswith(".py") and first != "--":
        path = first if os.path.isabs(first) else os.path.join(cwd, first)
        if os.path.exists(path):
            return [sys.executable, path] + list(cmd[1:])
    return list(cmd)


def run_child(cmd, cwd, timeout):
    argv = resolve_command(cmd, cwd)
    started = now_iso()
    try:
        p = subprocess.run(argv, cwd=cwd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout)
        output = (p.stdout or "") + (p.stderr or "")
        return p.returncode, output, started, now_iso(), ""
    except subprocess.TimeoutExpired:
        return 124, "", started, now_iso(), f"TIMEOUT {timeout}s"
    except OSError as exc:
        return 127, "", started, now_iso(), str(exc)


def make_record(run_id, span, span_id, argv, code, output, started, ended, cwd,
                expected, expected_source, next_action="", next_ref="", err=""):
    findings = findings_from(output, span)
    ok = code == 0
    if not next_action:
        next_action = ("无（继续）" if ok else
                       "看第一条 finding 的 file:line；修完重跑")
    if not next_ref and findings:
        next_ref = findings[0].get("file", "")
    return {
        "run_id": run_id,
        "span_id": span_id,
        "parent_span": "",
        "component": span,
        "argv": argv,
        "input_refs": input_refs(cwd),
        "tool_version": tool_version(),
        "started_at": started,
        "ended_at": ended,
        "expected": expected,
        "expected_source": expected_source,
        "expected_status": "met" if ok else "not_met",
        "actual": {
            "exit_code": code,
            "result": "ok" if ok else "fail",
            "findings": findings,
            "skipped": [],
        },
        "next_action": next_action,
        "next_ref": next_ref,
        "record_status": "ok",
        "error": err,
    }


def emit(obs_dir, rec):
    status, err = write_record(obs_dir, rec)
    rec["record_status"] = status
    if err:
        rec["error"] = err
        print(f"observe: 记录失败（degraded）：{err}", file=sys.stderr)
    return status


def cmd_run(args):
    cmd = list(args.command)
    if cmd and cmd[0] == "--":
        cmd = cmd[1:]
    if not cmd:
        print("observe run: 缺少 `-- <命令>`", file=sys.stderr)
        return 2
    cwd = os.path.abspath(args.cwd or os.getcwd())
    run_id = args.run_id or ("r-" + datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
                             + "-" + uuid.uuid4().hex[:6])
    span = args.name or os.path.splitext(os.path.basename(cmd[0]))[0]
    code, output, started, ended, err = run_child(cmd, cwd, args.timeout)
    if output:
        sys.stdout.write(output)
    rec = make_record(run_id, span, "s-1", resolve_command(cmd, cwd), code, output,
                      started, ended, cwd, args.expected or "exit 0",
                      args.expected_source or "cli", args.next, args.next_ref, err)
    emit(observe_dir(cwd, args.observe_dir), rec)
    print(f"observe: run_id={run_id} span={span} result={rec['actual']['result']} "
          f"record={rec['record_status']}")
    return code


def cmd_five_run(args):
    cwd = os.path.abspath(args.cwd or os.getcwd())
    run_id = args.run_id or ("r-" + datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
                             + "-" + uuid.uuid4().hex[:6])
    # 顺序必须与 SKILL「日常三动作 · 收尾」一致：先重建生成区，最后全库校验
    # （ISS-122；self_test 第 72 组用独立期望序列盯住）。
    steps = [
        ("devlog.check", ["devlog.py", "check"], "errors=0"),
        ("devlog.index", ["devlog.py", "index"], "index 写出"),
        ("plan.check", ["plan.py", "check"], "errors=0"),
        ("plan.index", ["plan.py", "index"], "index 写出"),
        ("doc_check", ["doc_check.py"], "errors=0"),
    ]
    bad = 0
    for i, (span, cmd, expected) in enumerate(steps, 1):
        argv = [sys.executable, os.path.join(cwd, "scripts", cmd[0])] + cmd[1:]
        code, output, started, ended, err = run_child(argv, cwd, args.timeout)
        if code != 0:
            bad += 1
            print(f"[{i}/5] {span} FAIL")
            if output:
                sys.stdout.write(output)
        else:
            print(f"[{i}/5] {span} ok")
        rec = make_record(run_id, span, f"s-{i}", argv, code, output,
                          started, ended, cwd, expected, "gate:five-run",
                          "" if code == 0 else "看第一条 finding 的 file:line；修完重跑五连跑",
                          "", err)
        emit(observe_dir(cwd, args.observe_dir), rec)
    print(f"observe: run_id={run_id} {len(steps) - bad}/{len(steps)} ok")
    return 0 if bad == 0 else 1


def load_records(obs_dir, run_id):
    path = os.path.join(obs_dir, "runs", run_id + ".jsonl")
    if not os.path.exists(path):
        return []
    out = []
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    out.append(json.loads(line))
    except (OSError, ValueError):
        return []
    return out


def cmd_show(args):
    records = load_records(observe_dir(os.getcwd(), args.observe_dir), args.run_id)
    if not records:
        print(f"observe show: 没有这条运行记录：{args.run_id}")
        return 1
    if args.json:
        for rec in records:
            print(json.dumps(rec, ensure_ascii=False))
        return 0
    print(f"run_id: {args.run_id}")
    for rec in records:
        act = rec.get("actual", {})
        print(f"  - {rec.get('span_id')} {rec.get('component')} "
              f"{act.get('result')} exit={act.get('exit_code')} "
              f"expected={rec.get('expected_status')} "
              f"findings={len(act.get('findings') or [])}")
        print(f"    next: {rec.get('next_action')}")
    return 0


def cmd_status(args):
    obs = observe_dir(os.getcwd(), args.observe_dir)
    runs = os.path.join(obs, "runs")
    files = []
    if os.path.isdir(runs):
        files = [os.path.join(runs, f) for f in os.listdir(runs) if f.endswith(".jsonl")]
        files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    if not files:
        print("证据缺口：还没有运行记录（observe run / five-run 会写）")
        return 0
    for path in files[:max(1, args.limit)]:
        try:
            with open(path, encoding="utf-8") as fh:
                recs = [json.loads(x) for x in fh if x.strip()]
        except (OSError, ValueError):
            continue
        if not recs:
            continue
        run_id = recs[0].get("run_id", os.path.basename(path)[:-6])
        ok = sum(1 for r in recs if r.get("actual", {}).get("result") == "ok")
        print(f"{run_id}  {len(recs)} span  {ok}/{len(recs)} ok  "
              f"record={recs[0].get('record_status', '?')}  "
              f"started={recs[0].get('started_at', '?')}")
    if args.check:
        latest = files[0]
        try:
            with open(latest, encoding="utf-8") as fh:
                recs = [json.loads(x) for x in fh if x.strip()]
        except (OSError, ValueError):
            recs = []
        if not recs:
            print("证据缺口：最近一条运行记录读不出来")
        elif any(r.get("record_status") == "degraded" for r in recs):
            print("证据缺口：最近一次运行有记录降级")
    return 0


def _list_run_files(obs_dir):
    """按文件 mtime 倒序列出运行记录；trend 只读它。"""
    runs = os.path.join(obs_dir, "runs")
    if not os.path.isdir(runs):
        return []
    files = [os.path.join(runs, f) for f in os.listdir(runs) if f.endswith(".jsonl")]
    files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return files


def _read_run_lines(path):
    """读一条 run 记录；坏行计数，不抛。"""
    recs, bad = [], 0
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    recs.append(json.loads(line))
                except ValueError:
                    bad += 1
    except OSError:
        return [], 1
    return recs, bad


def _in_window(started, since):
    """ISO 字符串前缀比较；since 只写日期时按天过滤。"""
    if not since:
        return True
    return started[:len(since)] >= since


def cmd_trend(args):
    """只读跨 run 聚合：同一问题（码 + 目标文件）出现几次 / 首末 / 版本。"""
    obs = observe_dir(os.getcwd(), args.observe_dir)
    files = _list_run_files(obs)
    if args.limit and args.limit > 0:
        files = files[:args.limit]
    since = args.since or ""
    if not files:
        if args.json:
            print(json.dumps({
                "window": {"limit": args.limit, "since": since, "runs": 0,
                           "spans": 0, "findings": 0, "bad_lines": 0},
                "keys": [],
                "evidence_gap": "还没有运行记录（observe run / five-run 会写）",
            }, ensure_ascii=False, indent=2))
        else:
            print("证据缺口：还没有运行记录（observe run / five-run 会写）")
        return 0
    agg = {}
    total_runs = total_spans = total_findings = bad_lines = 0
    for path in files:
        recs, bad = _read_run_lines(path)
        bad_lines += bad
        run_counted = False
        for rec in recs:
            started = str(rec.get("started_at") or "")
            if not _in_window(started, since):
                continue
            run_counted = True
            total_spans += 1
            version = str(rec.get("tool_version") or "")
            component = str(rec.get("component") or "")
            run_id = str(rec.get("run_id") or "")
            for f in ((rec.get("actual") or {}).get("findings") or []):
                code = str(f.get("code") or "")
                if not code:
                    continue
                file_ = str(f.get("file") or "")
                key = f"{code}:{file_ or '?'}"
                a = agg.get(key)
                if a is None:
                    a = agg[key] = {
                        "key": key, "code": code, "file": file_, "count": 0,
                        "runs": set(), "first_seen": "", "last_seen": "",
                        "versions": set(), "components": set(),
                        "last_message": "", "last_ref": "",
                    }
                a["count"] += 1
                total_findings += 1
                if run_id:
                    a["runs"].add(run_id)
                if version:
                    a["versions"].add(version)
                if component:
                    a["components"].add(component)
                if started and (not a["first_seen"] or started < a["first_seen"]):
                    a["first_seen"] = started
                if started and (not a["last_seen"] or started >= a["last_seen"]):
                    a["last_seen"] = started
                    a["last_message"] = str(f.get("message") or "")
                    line = f.get("line") or 0
                    a["last_ref"] = f"{file_}:{line}" if file_ and line else file_
        if run_counted:
            total_runs += 1
    rows = list(agg.values())
    rows.sort(key=lambda a: a["last_seen"], reverse=True)
    rows.sort(key=lambda a: a["count"], reverse=True)
    if args.json:
        payload = {
            "window": {"limit": args.limit, "since": since, "runs": total_runs,
                       "spans": total_spans, "findings": total_findings,
                       "bad_lines": bad_lines},
            "keys": [
                {
                    "key": a["key"], "code": a["code"], "file": a["file"],
                    "count": a["count"], "runs": len(a["runs"]),
                    "first_seen": a["first_seen"], "last_seen": a["last_seen"],
                    "versions": sorted(a["versions"]),
                    "components": sorted(a["components"]),
                    "last_message": a["last_message"], "last_ref": a["last_ref"],
                }
                for a in rows
            ],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    if not rows:
        print(f"trend: 0 条问题（{total_runs} 个 run / {total_spans} 个 span；"
              f"窗口 limit={args.limit or 'all'} since={since or '—'}）")
        if bad_lines:
            print(f"（跳过坏行 {bad_lines} 条）")
        return 0
    print(f"trend: {len(rows)} 条问题 / {total_findings} 次出现 / {total_runs} 个 run "
          f"（窗口 limit={args.limit or 'all'} since={since or '—'}）")
    for a in rows:
        print(f"{a['key']}  count={a['count']}  runs={len(a['runs'])}  "
              f"first={a['first_seen'] or '?'}  last={a['last_seen'] or '?'}  "
              f"versions={','.join(sorted(a['versions'])) or '?'}")
        if a["last_message"]:
            print(f"    last: {a['last_message'][:200]}")
    if bad_lines:
        print(f"（跳过坏行 {bad_lines} 条）")
    return 0


def main():
    ap = argparse.ArgumentParser(description="运行记录（自身参考实现）")
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("run", help="包一条命令并写一条记录")
    p.add_argument("--name")
    p.add_argument("--run-id")
    p.add_argument("--expected", default="")
    p.add_argument("--expected-source", default="")
    p.add_argument("--next", default="")
    p.add_argument("--next-ref", default="")
    p.add_argument("--observe-dir")
    p.add_argument("--cwd")
    p.add_argument("--timeout", type=int, default=300)
    p.add_argument("command", nargs=argparse.REMAINDER)
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("five-run", help="串五连跑并写一条 trace")
    p.add_argument("--run-id")
    p.add_argument("--observe-dir")
    p.add_argument("--cwd")
    p.add_argument("--timeout", type=int, default=300)
    p.set_defaults(func=cmd_five_run)

    p = sub.add_parser("show", help="回看一条 run 的四问")
    p.add_argument("run_id")
    p.add_argument("--json", action="store_true")
    p.add_argument("--observe-dir")
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("status", help="看最近几次运行")
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--check", action="store_true")
    p.add_argument("--observe-dir")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("trend", help="跨 run 聚合同一问题（复发 / 趋势）")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--since", default="")
    p.add_argument("--json", action="store_true")
    p.add_argument("--observe-dir")
    p.set_defaults(func=cmd_trend)

    args = ap.parse_args()
    if not getattr(args, "func", None):
        ap.print_help()
        return 2
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
