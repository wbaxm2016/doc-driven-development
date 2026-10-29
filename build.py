#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把本仓库打包成可分发的 .skill（本质是 zip），并在打包前后各做一遍验证。

用法：
    python build.py                  # 体检 + 跑自测 + 打包 + 验包
    python build.py --no-test        # 跳过自测（仅调试打包逻辑时用）
    python build.py --install        # 打完再覆盖安装到技能根目录（依次找 .qwenworkcn / .workbuddy）
    python build.py --install --skills-dir ~/.qwenworkcn/skills   # 指定根目录
    python build.py --out DIR        # 改输出目录（默认 dist/）
    python build.py --json           # 机器可读结果，给 CI 用

为什么需要这个脚本：
    上一版 dist/*.skill 是手工打的快照。源仓库后来补了 8 条规则（E13-E17/W1/W4/W5），
    包没重新生成，安装方拿到的还是老版本——而且没人会发现，因为"打包"没有单一入口，
    也没有任何检查比对过包内文件与源文件是否一致。
    现在的规则很简单：dist/ 里的一切都只能由本脚本生成，且必须通过验包才能交付。
    打包前还会把文本文件的行尾统一成 LF：仓库 .gitattributes 是 `eol=lf`，开发机工作区
    却是 CRLF，不归一的话同一提交在两台机器上算出的 MANIFEST 哈希不同（ISS-008）。

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
# 进入包的文件：根目录只允许 SKILL.md / VERSION / MANIFEST.txt / .skill-metadata.yaml，
# 其余按目录整体收入
INCLUDE_DIRS = ("scripts", "references", "assets")
ROOT_FILES = ("SKILL.md", "VERSION", ".skill-metadata.yaml")
# 平台元数据不是“技能资源”，不需要在 SKILL.md 里被点名
SELF_STATED = {"SKILL.md", "VERSION", ".skill-metadata.yaml"}
EXCLUDE_NAMES = {"__pycache__", ".DS_Store", "Thumbs.db", ".pytest_cache"}
EXCLUDE_SUFFIX = (".pyc", ".pyo", ".swp", ".orig", ".rej", "~")

# 进包前统一行尾。仓库 .gitattributes 是 `* text=auto eol=lf`，干净克隆拿到的源码是 LF，
# 而开发机工作区常是 CRLF：不归一就打包，同一提交在两台机器上算出的 MANIFEST 哈希不同，
# "同样输入产出同样字节"就成了只在本机成立的假话（ISS-008）。
TEXT_SUFFIX = (".md", ".py", ".yaml", ".yml", ".json", ".txt", ".toml", ".cfg", ".ini", ".sh")

# 安装根目录候选：产品各用一个目录，写死任何一个都会造成“装成功但没人读”的假通过。
# 顺序：显式环境变量 → 千问办公 → 其他 Agent 目录 → 旧值兜底。
SKILL_ROOT_CANDIDATES = (
    ("QWENWORK_SKILLS", None),
    ("WORKBUDDY_SKILLS", None),
    (None, os.path.join(".qwenworkcn", "skills")),
    (None, os.path.join(".workbuddy", "skills")),
)

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

    # 平台可见技能要求双语元数据；只配中文时，英文界面会退化到中文串。
    for key in ("name_en", "name_zh", "description_en", "description_zh",
                "argument-hint", "argument-hint_en", "argument-hint_zh", "user-invocable"):
        if not fm.get(key):
            err(f"SKILL.md front-matter 缺 {key}")
    if fm.get("user-invocable") and fm["user-invocable"].lower() not in ("true", "false"):
        err(f"user-invocable 必须是 true/false，实际 {fm['user-invocable']!r}")

    md = os.path.join(ROOT, ".skill-metadata.yaml")
    if not os.path.exists(md):
        err("缺 .skill-metadata.yaml：用户点「使用」时只会预填通用问句，等于浪费这个文件")
    else:
        with open(md, encoding="utf-8") as fh:
            meta = fh.read()
        n_ex = len(re.findall(r"(?m)^\s*- id:", meta))
        if n_ex < 2:
            err(f".skill-metadata.yaml 只有 {n_ex} 条示例，主要能力应各有一条（2–5 条）")
        for lang in ("zh", "en"):
            if len(re.findall(rf"(?m)^\s*{lang}:", meta)) < max(2, n_ex * 2):
                err(f".skill-metadata.yaml 的 {lang} 文案不完整（title/description/prompt 都要双语）")
        if "{{" not in meta:
            warn(".skill-metadata.yaml 没有 {{占位符}}：确认每条 query 都留了用户必填的位置")
        else:
            ok(f".skill-metadata.yaml：{n_ex} 条示例，双语齐")

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
        if f in SELF_STATED:
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


def is_text(name: str) -> bool:
    """进包的文本文件：按后缀判定，外加无后缀的 VERSION。"""
    return name == "VERSION" or name.lower().endswith(TEXT_SUFFIX)


def normalize(name: str, data: bytes) -> tuple[bytes, bool]:
    """文本文件统一成 LF；返回 (归一后的字节, 是否改动过)。二进制与非 UTF-8 原样返回。"""
    if not is_text(name):
        return data, False
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return data, False
    out = text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")
    return out, out != data


def make_manifest(version: str, entries: list[tuple[str, bytes]]) -> bytes:
    lines = [
        f"skill: {SKILL_NAME}",
        f"version: {version}",
        "runtime: python >= 3.8, 仅标准库",
        f"payload_files: {len(entries)}",
        # 含本 MANIFEST.txt 自身；MANIFEST 不给自己算哈希，所以两个数会差 1
        f"files_in_package: {len(entries) + 1}",
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
    entries, rewritten = [], 0
    for f in files:
        with open(os.path.join(ROOT, f), "rb") as fh:
            data, changed = normalize(f, fh.read())
        rewritten += 1 if changed else 0
        entries.append((f, data))
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
    ok(f"{len(entries)} 个文件（未发布，等验包；行尾统一为 LF，{rewritten} 个文件被改写）")
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
            if zf.read("SKILL.md") != normalize("SKILL.md", fh.read())[0]:
                err("包内 SKILL.md 与源文件不一致")
                return False
        # 行尾必须已经归一：包里有 CR 就说明这台机器的工作区是 CRLF，且归一漏了某个文件
        crlf = [n for n in names if is_text(n) and b"\r" in zf.read(n)]
        if crlf:
            err(f"包内仍有 CRLF 行尾，跨机器不可复现：{crlf[:5]}")
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
    ok(f"结构、版本、SKILL.md 字节一致，{len(listed)} 个文件哈希吻合，包内无 CRLF")

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
def resolve_skills_root(explicit: str | None) -> tuple[str, str]:
    """返回 (skills_root, 来源说明)。写死单一产品目录会造成“装成功但没人读”的假通过。"""
    if explicit:
        return os.path.abspath(os.path.expanduser(explicit)), "--skills-dir"
    for env_key, sub in SKILL_ROOT_CANDIDATES:
        if env_key:
            val = os.environ.get(env_key)
            if val:
                return os.path.abspath(os.path.expanduser(val)), f"环境变量 {env_key}"
        else:
            cand = os.path.join(os.path.expanduser("~"), sub)
            if os.path.isdir(cand):
                return cand, f"默认目录 {sub}"
    cand = os.path.join(os.path.expanduser("~"), ".qwenworkcn", "skills")
    return cand, "默认首选（目录不存在，将创建）"


def install(artifact: str, skills_root: str | None = None) -> bool:
    root, why = resolve_skills_root(skills_root)
    dest = os.path.join(root, SKILL_NAME)
    print(f"\n5. 安装到 {dest}   （根目录来源：{why}）")
    if not os.path.isdir(root):
        warn(f"技能根目录不存在：{root}")
    tmp = tempfile.mkdtemp(prefix="ddd-install-")
    try:
        with zipfile.ZipFile(artifact) as zf:
            zf.extractall(tmp)
        if os.path.isdir(dest):
            shutil.rmtree(dest)
        shutil.copytree(tmp, dest)
        if not os.path.exists(os.path.join(dest, "SKILL.md")):
            err(f"安装后 {dest} 里没有 SKILL.md，等于没装上")
            return False
        ok(f"已覆盖安装：{dest}")
        print(f"         提示：技能列表通常要重开会话/窗口才会刷新；"
              f"确认方式是重启后能看到 {SKILL_NAME}，而不是本脚本打印成功")
        return run_self_test(dest, "安装后自测")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    ap = argparse.ArgumentParser(description="打包 doc-driven-development 为 .skill")
    ap.add_argument("--out", default=os.path.join(ROOT, "dist"))
    ap.add_argument("--no-test", action="store_true")
    ap.add_argument("--install", action="store_true")
    ap.add_argument("--skills-dir", default=None,
                    help="技能根目录；不给就按 QWENWORK_SKILLS / WORKBUDDY_SKILLS / "
                         "~/.qwenworkcn/skills / ~/.workbuddy/skills 依次找")
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
        if args.install and not install(artifact, args.skills_dir):
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
