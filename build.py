#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把本仓库打包成可分发的 .skill（本质是 zip），并在打包前后各做一遍验证。

用法：
    python build.py                  # 体检 + 跑自测 + 打包 + 验包
    python build.py --no-test        # 跳过自测（仅调试打包逻辑时用）
    python build.py --install        # 打完再覆盖安装到 ~/.workbuddy/skills/
    python build.py --out DIR        # 改输出目录（默认 dist/）
    python build.py --json           # 机器可读结果，给 CI 用

为什么需要这个脚本：
    上一版 dist/*.skill 是手工打的快照。源仓库后来补了 8 条规则（E13-E17/W1/W4/W5），
    包没重新生成，安装方拿到的还是老版本——而且没人会发现，因为"打包"没有单一入口，
    也没有任何检查比对过包内文件与源文件是否一致。
    现在的规则很简单：dist/ 里的一切都只能由本脚本生成，且必须通过验包才能交付。

退出码：0 成功；1 体检或自测失败；2 环境/参数问题。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import py_compile
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable

SKILL_NAME = "doc-driven-development"
# 进入包的文件：根目录只允许 SKILL.md / VERSION / MANIFEST.txt，其余按目录整体收入
INCLUDE_DIRS = ("scripts", "references", "assets")
ROOT_FILES = ("SKILL.md", "VERSION")
EXCLUDE_NAMES = {"__pycache__", ".DS_Store", "Thumbs.db", ".pytest_cache"}
EXCLUDE_SUFFIX = (".pyc", ".pyo", ".swp", ".orig", ".rej", "~")

ZIP_DATE = (1980, 1, 1, 0, 0, 0)  # 固定时间戳，保证同样输入产出同样字节

ERRORS: list[str] = []
WARNS: list[str] = []


def rel(p: str) -> str:
    return os.path.relpath(p, ROOT).replace("\\", "/")


def err(msg: str) -> None:
    ERRORS.append(msg)
    print(f"  ERROR  {msg}")


def warn(msg: str) -> None:
    WARNS.append(msg)
    print(f"  WARN   {msg}")


def ok(msg: str) -> None:
    print(f"  ok     {msg}")


# ---------------------------------------------------------------- 体检
def parse_frontmatter(text: str) -> dict:
    m = re.match(r"^---\r?\n(.*?)\r?\n---", text, re.S)
    if not m:
        return {}
    fm, key = {}, None
    for line in m.group(1).splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if re.match(r"^\s+\S", line) and key:  # 嵌套块（metadata 之类）忽略
            continue
        k, _, v = line.partition(":")
        key = k.strip()
        fm[key] = v.strip().strip('"').strip("'")
    return fm


def walk_package_files() -> list[str]:
    files = []
    for f in ROOT_FILES:
        if os.path.exists(os.path.join(ROOT, f)):
            files.append(f)
    for d in INCLUDE_DIRS:
        base = os.path.join(ROOT, d)
        for cur, dirs, names in os.walk(base):
            dirs[:] = sorted(x for x in dirs if x not in EXCLUDE_NAMES and not x.startswith("."))
            for n in sorted(names):
                if n in EXCLUDE_NAMES or n.endswith(EXCLUDE_SUFFIX) or n.startswith("."):
                    continue
                files.append(rel(os.path.join(cur, n)))
    return sorted(files)


def preflight() -> str:
    print("1. 体检")
    vp = os.path.join(ROOT, "VERSION")
    if not os.path.exists(vp):
        err("缺少 VERSION 文件")
        return "0.0.0"
    with open(vp, encoding="utf-8") as fh:
        version = fh.read().strip()
    if not re.fullmatch(r"\d+\.\d+\.\d+([-.][0-9A-Za-z.]+)?", version):
        err(f"VERSION 不是合法语义版本：{version!r}")
    else:
        ok(f"版本 {version}")

    skill_md = os.path.join(ROOT, "SKILL.md")
    if not os.path.exists(skill_md):
        err("缺少 SKILL.md")
        return version
    with open(skill_md, encoding="utf-8") as fh:
        text = fh.read()
    fm = parse_frontmatter(text)

    name = fm.get("name", "")
    if not name:
        err("SKILL.md 缺 name")
    elif name != SKILL_NAME:
        err(f"name 必须等于目录名 {SKILL_NAME}，实际 {name!r}")
    elif not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", name):
        err(f"name 只能是小写字母/数字/连字符：{name!r}")
    elif len(name) > 64:
        err(f"name 超长（{len(name)} > 64）")
    else:
        ok(f"name = {name}")

    desc = fm.get("description", "")
    if not desc:
        err("SKILL.md 缺 description")
    elif not (10 <= len(desc) <= 1024):
        err(f"description 长度 {len(desc)}，要求 10–1024")
    else:
        ok(f"description {len(desc)} 字符")

    if len(text.splitlines()) > 500:
        warn(f"SKILL.md {len(text.splitlines())} 行，超过 500 行会让常驻上下文偏重")

    # SKILL.md 里点名的文件必须真实存在
    refs = set(re.findall(
        r"(?:references|assets|scripts)/[A-Za-z0-9_./\-\u4e00-\u9fff]+\.(?:md|py|ya?ml)", text))
    for r in sorted(refs):
        if not os.path.exists(os.path.join(ROOT, r)):
            err(f"SKILL.md 引用了不存在的文件：{r}")
    if refs:
        ok(f"SKILL.md 引用的 {len(refs)} 个路径都存在")

    # 反过来：包里有、SKILL.md 从不提及的文件，多半是忘了写进"按需加载"表
    # 注意：目录级引用（如 `assets/ci/`）要算提到，但 `scripts/doc_check.py` 里的
    # "scripts/" 只是文件路径的前缀，不能让同目录下的孤儿文件蒙混过关。
    files = walk_package_files()
    for f in files:
        if f in ("SKILL.md", "VERSION"):
            continue
        stem = os.path.basename(f)
        d = os.path.dirname(f)
        dir_named = bool(d) and re.search(
            re.escape(d) + r"/[^A-Za-z0-9_.\-]", text) is not None
        if f not in text and stem not in text and not dir_named:
            warn(f"未被 SKILL.md 提及：{f}")

    # 语法体检：语法错的脚本装进去只会在用户机器上炸
    for f in files:
        if f.endswith(".py"):
            try:
                py_compile.compile(os.path.join(ROOT, f), doraise=True,
                                   cfile=os.path.join(tempfile.gettempdir(), "ddd-pyc-check"))
            except py_compile.PyCompileError as exc:
                err(f"{f} 语法错误：{exc}")
    ok(f"{len([f for f in files if f.endswith('.py')])} 个脚本语法通过")

    # 防止把上一版构建产物或缓存打进包
    for bad in ("dist", "__pycache__", ".git"):
        if any(f.startswith(bad + "/") for f in files):
            err(f"包内混入了 {bad}/")
    return version


# ---------------------------------------------------------------- 自测
def run_self_test(skill_dir: str, label: str) -> bool:
    script = os.path.join(skill_dir, "scripts", "self_test.py")
    if not os.path.exists(script):
        err(f"{label}：找不到 scripts/self_test.py")
        return False
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    p = subprocess.run([PY, script], cwd=skill_dir, capture_output=True,
                       text=True, encoding="utf-8", errors="replace", env=env)
    tail = [ln for ln in (p.stdout or "").strip().splitlines() if ln.strip()][-3:]
    if p.returncode == 0:
        ok(f"{label}：{tail[-1].strip() if tail else '通过'}")
        return True
    err(f"{label}：自测失败（exit {p.returncode}）")
    for ln in tail:
        print(f"         {ln.strip()}")
    return False


# ---------------------------------------------------------------- 打包
def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def make_manifest(version: str, entries: list[tuple[str, bytes]]) -> bytes:
    lines = [
        f"skill: {SKILL_NAME}",
        f"version: {version}",
        "runtime: python >= 3.8, 仅标准库",
        f"files: {len(entries) + 1}",
        "",
        "# sha256  path",
    ]
    for name, data in entries:
        lines.append(f"{sha256(data)}  {name}")
    return ("\n".join(lines) + "\n").encode("utf-8")


def build(version: str) -> str:
    """先打到临时文件。验包通过后才允许落到 dist/，避免坏产物混进发布目录。"""
    print("\n3. 打包")
    files = walk_package_files()
    entries = []
    for f in files:
        with open(os.path.join(ROOT, f), "rb") as fh:
            entries.append((f, fh.read()))
    manifest = make_manifest(version, entries)
    entries.append(("MANIFEST.txt", manifest))
    entries.sort(key=lambda x: x[0])

    tmp = os.path.join(tempfile.mkdtemp(prefix="ddd-build-"), f"{SKILL_NAME}.skill")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for name, data in entries:
            zi = zipfile.ZipInfo(name, date_time=ZIP_DATE)
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = (0o644 & 0xFFFF) << 16
            zi.create_system = 3
            zf.writestr(zi, data)
    ok(f"{len(entries)} 个文件（未发布，等验包）")
    return tmp


def publish(tmp: str, version: str, out_dir: str) -> str:
    os.makedirs(out_dir, exist_ok=True)
    stable = os.path.join(out_dir, f"{SKILL_NAME}.skill")
    versioned = os.path.join(out_dir, f"{SKILL_NAME}-{version}.skill")
    shutil.copyfile(tmp, stable)
    shutil.copyfile(tmp, versioned)
    ok(f"已发布 {os.path.basename(stable)} 与 {os.path.basename(versioned)}")
    return stable


# ---------------------------------------------------------------- 验包
def verify(artifact: str, version: str) -> bool:
    print("\n4. 验包（解包后按安装方视角再验一遍）")
    with zipfile.ZipFile(artifact) as zf:
        names = zf.namelist()
        bad = zf.testzip()
        if bad:
            err(f"zip 损坏于 {bad}")
            return False
        if "SKILL.md" not in names:
            err("SKILL.md 不在包根目录——安装方会识别不到技能")
            return False
        if any(n.startswith(("/", "\\")) or ".." in n.split("/") for n in names):
            err("包含不安全路径")
            return False
        duplicate = {n for n in names if names.count(n) > 1}
        if duplicate:
            err(f"重复条目：{sorted(duplicate)}")
            return False
        with open(os.path.join(ROOT, "SKILL.md"), "rb") as fh:
            if zf.read("SKILL.md") != fh.read():
                err("包内 SKILL.md 与源文件不一致")
                return False
        man = zf.read("MANIFEST.txt").decode("utf-8")
        if f"version: {version}" not in man:
            err("MANIFEST 版本与 VERSION 不一致")
            return False
        listed = {}
        for line in man.splitlines():
            m = re.fullmatch(r"([0-9a-f]{64})  (.+)", line.strip())
            if m:
                listed[m.group(2)] = m.group(1)
        if not listed:
            err("MANIFEST 里没有可解析的哈希行")
            return False
        wrong = [n for n, h in listed.items()
                 if n not in names or sha256(zf.read(n)) != h]
        if wrong:
            err(f"MANIFEST 哈希与实际内容不符：{wrong[:5]}")
            return False
        if set(listed) | {"MANIFEST.txt"} != set(names):
            err("MANIFEST 未覆盖全部文件")
            return False
    ok(f"结构、版本、SKILL.md 字节一致，{len(listed)} 个文件哈希吻合")

    tmp = tempfile.mkdtemp(prefix="ddd-verify-")
    try:
        with zipfile.ZipFile(artifact) as zf:
            zf.extractall(tmp)
        # 逐文件比对：包内容必须与源仓库完全一致，不多不少
        with zipfile.ZipFile(artifact) as zf:
            packed = sorted(n for n in zf.namelist() if n != "MANIFEST.txt")
        expected = walk_package_files()
        if packed != expected:
            missing = sorted(set(expected) - set(packed))
            extra = sorted(set(packed) - set(expected))
            err(f"包内文件与源不一致  缺={missing} 多={extra}")
            return False
        ok(f"文件清单与源仓库一致（{len(packed)} 个）")
        return run_self_test(tmp, "解包后自测")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------- 安装
def install(artifact: str) -> bool:
    target_root = os.environ.get("WORKBUDDY_SKILLS") or os.path.join(
        os.path.expanduser("~"), ".workbuddy", "skills")
    dest = os.path.join(target_root, SKILL_NAME)
    print(f"\n5. 安装到 {dest}")
    tmp = tempfile.mkdtemp(prefix="ddd-install-")
    try:
        with zipfile.ZipFile(artifact) as zf:
            zf.extractall(tmp)
        if os.path.isdir(dest):
            shutil.rmtree(dest)
        shutil.copytree(tmp, dest)
        ok("已覆盖安装（旧的 __pycache__ 一并清掉）")
        return run_self_test(dest, "安装后自测")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    ap = argparse.ArgumentParser(description="打包 doc-driven-development 为 .skill")
    ap.add_argument("--out", default=os.path.join(ROOT, "dist"))
    ap.add_argument("--no-test", action="store_true")
    ap.add_argument("--install", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    print(f"源码目录 {ROOT}\n")
    version = preflight()
    if ERRORS:
        print(f"\n体检未通过（{len(ERRORS)} 处），未打包。")
        return 1

    if args.no_test:
        print("\n2. 自测 —— 已按 --no-test 跳过")
    else:
        print("\n2. 自测（源目录）")
        if not run_self_test(ROOT, "源目录"):
            print("\n自测未通过，未打包。")
            return 1

    tmp = build(version)
    try:
        if not verify(tmp, version):
            print("\n验包未通过，产物未发布（dist/ 保持上一次的好版本）。")
            return 1
        artifact = publish(tmp, version, args.out)
        if args.install and not install(artifact):
            return 1
    finally:
        shutil.rmtree(os.path.dirname(tmp), ignore_errors=True)

    size = os.path.getsize(artifact)
    with open(artifact, "rb") as fh:
        digest = sha256(fh.read())
    print("\n" + "=" * 56)
    print(f"版本   {version}")
    print(f"产物   {artifact}")
    print(f"大小   {size / 1024:.1f} KB")
    print(f"sha256 {digest}")
    if WARNS:
        print(f"提示   {len(WARNS)} 条 WARN 未阻断打包，建议逐条确认")
    if args.json:
        print(json.dumps({"version": version, "artifact": artifact, "size": size,
                          "sha256": digest, "warnings": WARNS}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
