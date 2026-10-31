#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""按清单把本技能装到各宿主应用的技能目录。

用法：
    python install.py --list        # 清单 + 探查结果（不写盘）
    python install.py --dry-run     # 同上，并列出将要写入的文件数
    python install.py               # 装全部启用的目标
    python install.py --only qwenworkcn,doubao
    python install.py --self-test   # 装完在目标目录里跑一次自测（慢，~分钟级）

为什么需要两份东西：
    **清单**（install-targets.json）维护「有哪些产品、各自的候选目录」；
    **脚本**只做探查与拷贝。各产品技能目录不同（千问办公 ~/.qwenworkcn/skills、
    DSH ~/.dsh/skills、豆包 ~/Doubao/skills、Qoder CN ~/.qoder-cn/skills），
    把任何一个写死在脚本里，都会在别的机器上变成「装成功但没人读」的假通过。
    加一个产品只改 JSON，不改代码。

安装源是**工作区源码**（不是 dist/ 里的旧产物）：装完会在目标目录写一份
.install.json，记下来源（source=worktree）、版本、commit 与文件数——否则
「装进去的到底是发版产物还是今天的源码」没人分得清。
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
import build  # 复用「哪些文件进包」的唯一清单：walk_package_files()

MANIFEST = os.path.join(ROOT, "install-targets.json")


def read_json(path: str) -> dict:
    with open(path, encoding="utf-8-sig") as fh:
        return json.load(fh)


def expand(p: str) -> str:
    return os.path.abspath(os.path.expanduser(os.path.expandvars(p)))


def probe(target: dict) -> tuple[str | None, str]:
    """返回 (技能根目录, 来源说明)。先环境变量、后候选路径；都没有 → (None, 原因)。"""
    for key in target.get("env", []):
        val = os.environ.get(key)
        if val:
            p = expand(val)
            if os.path.isdir(p):
                return p, f"环境变量 {key}"
            return None, f"环境变量 {key} 指向的目录不存在：{p}"
    for raw in target.get("paths", []):
        p = expand(raw)
        if os.path.isdir(p):
            return p, raw
    tried = "、".join(target.get("paths", []))
    return None, f"候选目录都不存在（试过：{tried}）"


def git_commit() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                             capture_output=True, text=True, timeout=10)
        return out.stdout.strip() if out.returncode == 0 else "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def materialize(source: str, artifact: str | None) -> tuple[list[tuple[str, bytes]], dict]:
    """把要装的东西读成 (相对路径, 字节) 列表。

    source=worktree：按 ``build.walk_package_files()`` 从工作区取，行尾归一；
    source=dist：从 ``dist/<skill>-<VERSION>.skill`` 解包，原样拷贝（包里已是 LF）。
    装什么、装的是哪一份，必须能回答——所以返回的 meta 会写进目标目录的 ``.install.json``。
    """
    version = open(os.path.join(ROOT, "VERSION"), encoding="utf-8").read().strip()
    if source == "worktree":
        files = build.walk_package_files()
        if "SKILL.md" not in files:
            raise SystemExit("ERROR 源目录里没有 SKILL.md，不装")
        entries = []
        for rel in files:
            data = open(os.path.join(ROOT, rel), "rb").read()
            if build.is_text(rel):
                data, _ = build.normalize(rel, data)   # 与打包同一条行尾规则（ISS-008）
            entries.append((rel, data))
        entries.append(("MANIFEST.txt", build.make_manifest(version, entries)))
        return entries, {"source": "worktree", "version": version, "commit": git_commit()}

    path = artifact or os.path.join(ROOT, "dist", "%s-%s.skill" % (SKILL_NAME, version))
    if not os.path.isfile(path):
        raise SystemExit("ERROR 找不到发版产物：%s（先跑 `python build.py`，或用 --artifact 指定）" % path)
    with zipfile.ZipFile(path) as zf:
        names = [n for n in zf.namelist() if not n.endswith("/")]
        entries = [(n, zf.read(n)) for n in names]
    man = dict(entries).get("MANIFEST.txt", b"").decode("utf-8", "replace")
    m = re.search(r"(?m)^version:\s*(\S+)", man)
    meta_version = m.group(1) if m else version
    return entries, {"source": "dist", "version": meta_version,
                     "artifact": os.path.relpath(path, ROOT).replace("\\", "/"),
                     "commit": git_commit()}


def install_one(target: dict, entries: list[tuple[str, bytes]], meta: dict,
                dry_run: bool) -> tuple[bool, str]:
    root, why = probe(target)
    if root is None:
        return False, why
    dest = os.path.join(root, target["skill"] if "skill" in target else SKILL_NAME)
    if dry_run:
        return True, f"将安装到 {dest}（{len(entries)} 个文件；来源：{why}）"

    if os.path.isdir(dest):
        shutil.rmtree(dest)
    os.makedirs(dest, exist_ok=True)
    for rel, data in entries:
        norm = os.path.normpath(rel)
        if norm.startswith("..") or os.path.isabs(norm):
            return False, f"包内路径越界：{rel}"
        out = os.path.join(dest, norm)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "wb") as fh:
            fh.write(data)

    marker = {
        "skill": SKILL_NAME,
        "version": meta["version"],
        "source": meta["source"],
        "commit": meta["commit"],
        "installed_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "files": len(entries) + 1,   # 含 .install.json 自身
    }
    if meta.get("artifact"):
        marker["artifact"] = meta["artifact"]
    with open(os.path.join(dest, ".install.json"), "w", encoding="utf-8") as fh:
        json.dump(marker, fh, ensure_ascii=False, indent=2)
    return True, (f"{dest}（{marker['files']} 个文件，v{marker['version']}，"
                  f"source={marker['source']}，commit {marker['commit']}）")


SKILL_NAME = "doc-driven-development"


def main() -> int:
    ap = argparse.ArgumentParser(description="按清单安装本技能到各宿主应用")
    ap.add_argument("--manifest", default=MANIFEST)
    ap.add_argument("--list", action="store_true", help="只看清单与探查结果")
    ap.add_argument("--dry-run", action="store_true", help="探查并打印，不写盘")
    ap.add_argument("--only", default="", help="只装这些 id（逗号分隔）")
    ap.add_argument("--self-test", action="store_true", help="装完在目标目录里跑自测")
    ap.add_argument("--from", dest="source", default="worktree",
                    choices=["worktree", "dist"],
                    help="装工作区源码（默认）还是 dist 里的发版产物")
    ap.add_argument("--artifact", default=None, help="--from dist 时显式指定 .skill 路径")
    args = ap.parse_args()

    try:
        man = read_json(args.manifest)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR 读不到清单 {args.manifest}：{exc}")
        return 2
    targets = man.get("targets", [])
    only = {s.strip() for s in args.only.split(",") if s.strip()}

    entries, meta = materialize(args.source, args.artifact)
    print(f"技能 {SKILL_NAME}  来源 {meta['source']} v{meta['version']}  "
          f"文件 {len(entries)}  清单 {args.manifest}")

    results, failed = [], 0
    for t in targets:
        name = t.get("name", t.get("id", "?"))
        if only and t.get("id") not in only:
            continue
        enabled = t.get("enabled", True)
        root, why = probe(t)
        state = "ok" if (root and enabled) else ("disabled" if not enabled else "skip")
        print(f"\n[{state}] {name}（{t.get('id')}）")
        print(f"  探查：{why}")
        if not enabled:
            continue
        if root is None:
            failed += 1
            continue
        if args.list:
            dest = os.path.join(root, SKILL_NAME)
            mark = os.path.join(dest, ".install.json")
            cur = ""
            if os.path.exists(mark):
                try:
                    cur = "  已装 v%s" % read_json(mark).get("version", "?")
                except (OSError, json.JSONDecodeError):
                    cur = "  已装（.install.json 读不出）"
            print(f"  将装到：{dest}{cur}")
            continue
        okk, detail = install_one(t, entries, meta, args.dry_run)
        print(("  " + ("dry-run" if args.dry_run else "installed") + "：" + detail))
        results.append((name, okk, detail))
        if not okk:
            failed += 1

    if args.self_test and not args.dry_run and not args.list:
        for t in targets:
            if not t.get("enabled", True) or (only and t.get("id") not in only):
                continue
            root, _ = probe(t)
            if root is None:
                continue
            dest = os.path.join(root, SKILL_NAME)
            print(f"\n自测：{dest}")
            p = subprocess.run([sys.executable, os.path.join(dest, "scripts", "self_test.py")],
                               cwd=dest, capture_output=True, text=True,
                               encoding="utf-8", errors="replace")
            tail = (p.stdout or "").strip().splitlines()[-1:] or [""]
            print(f"  {'ok' if p.returncode == 0 else 'FAIL'}  {tail[0]}")
            failed += 0 if p.returncode == 0 else 1

    print("\n" + "=" * 56)
    print(f"清单目标 {len(targets)}  已装/将装 {len(results) if not (args.list or args.dry_run) else '-'}  失败 {failed}")
    if failed:
        print("失败不等于“装成功但没人读”：先看上面的探查原因，别靠猜目录名。")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
