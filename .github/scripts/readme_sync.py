#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""中英 README 结构同步检查（只在本仓库跑，不进 .skill 包）。

为什么需要：
    README.md 是源、README.en.md 跟随（AGENTS.md「文档约定」）。这条规则原先只靠自觉：
    改了一版忘了另一版，两边就会慢慢说两件事——写在文档里的规则，等于没有规则。

检查什么（只判结构，不判语义；译文本来就不一样）：
    R1 标题骨架：H1–H6 的层级序列（数量与顺序）一致
    R2 项目名：首个 H1 的标题文本一致（不翻译）
    R3 代码块：围栏语言序列一致；带语言的块逐行比「命令」（去行内注释、把 <占位> 与
       中文段归一成 <x>）；纯文本块只比行数（示意图里的标签是翻译过的）
    R4 表格形状：每张表的 (列数, 行数) 序列一致
    R5 数字事实：正文数字 token 的多重集合一致（`0 error` / `1–3` / `63 / 64` …）
    R6 链接集合：`](目标)` 的多重集合一致；语言互链 README.md / README.en.md 天然不对称，排除
    R7 语言互链：中文版链到 README.en.md，英文版链到 README.md
    R8 列表条目：逐节比 `- ` 与 `1. ` 的条目数（加/删一条要点必须两版同时改）

「只改一版应红」不靠嘴说：`--self-check` 现场造 8 组样本自证（同步的对子 0，各轴单独改一版 1）。

用法：
    python .github/scripts/readme_sync.py                 # 比对仓库根的 README.md / README.en.md
    python .github/scripts/readme_sync.py --zh a.md --en b.md
    python .github/scripts/readme_sync.py --self-check    # 检查器自证（CI 与本地都跑）
    python .github/scripts/readme_sync.py --quiet        # 只打结论行
    python .github/scripts/readme_sync.py --json         # 机器可读

退出码：0 同步；1 不同步；2 文件缺失 / 参数错误。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_ZH = os.path.join(ROOT, "README.md")
DEFAULT_EN = os.path.join(ROOT, "README.en.md")

FENCE_RE = re.compile(r"^\s{0,3}(```+|~~~+)\s*(\S*)")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
LINK_RE = re.compile(r"\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
INLINE_CODE_RE = re.compile(r"`[^`\n]*`")
BULLET_RE = re.compile(r"^\s{0,2}[-*+]\s+")
ORDERED_RE = re.compile(r"^\s{0,2}\d+[.)]\s+")
DIGIT_RE = re.compile(r"(?<![\w.])\d+(?:\.\d+)*(?![\w.])")
CJK_RE = re.compile(r"[\u3000-\u303f\u2e80-\u9fff\uff00-\uffef]+")
ANGLE_RE = re.compile(r"<[^<>\n]*>")
COMMENT_RE = re.compile(r"\s+#.*$")
# 语言互链天然不对称：中文版指向 en，英文版指向 zh（R7 单独判，R6 里排除）
LANG_SELF = {"readme.md", "readme.en.md"}


def read(path):
    # utf-8-sig：Windows 编辑器容易写 BOM，BOM 会让首行标题匹配不上
    with open(path, encoding="utf-8-sig") as fh:
        return fh.read().replace("\r\n", "\n").replace("\r", "\n")


def split_fences(text):
    """返回 (无围栏正文, [(语言, 起始行号, 正文行)])；围栏内容用空行占位，行号保持对齐。"""
    plain, blocks, lines, i = [], [], text.splitlines(), 0
    while i < len(lines):
        m = FENCE_RE.match(lines[i])
        if not m:
            plain.append(lines[i])
            i += 1
            continue
        lang, start, body = m.group(2), i + 1, []
        i += 1
        while i < len(lines) and not FENCE_RE.match(lines[i]):
            body.append(lines[i])
            i += 1
        blocks.append((lang, start, body))
        plain.extend([""] * (len(body) + 2))  # 开围栏 + 内容 + 收围栏
        i += 1
    return "\n".join(plain), blocks


def headings(plain):
    out = []
    for no, line in enumerate(plain.splitlines(), 1):
        m = HEADING_RE.match(line)
        if m:
            out.append((len(m.group(1)), m.group(2), no))
    return out


def commands_of(body):
    """把代码行归一成「命令」：去行内注释、<占位> 与中文段归一成 <x>、压空白。"""
    out = []
    for offset, line in enumerate(body):
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        s = COMMENT_RE.sub("", s)
        s = ANGLE_RE.sub("<x>", s)
        s = CJK_RE.sub("<x>", s)
        s = re.sub(r"\s+", " ", s).strip()
        if s:
            out.append((s, offset))
    return out


def _is_sep(line):
    s = line.strip()
    if not s.startswith("|"):
        return False
    s = s.strip("|")
    return bool(s) and "-" in s and set(s) <= set(" :-|")


def tables(plain):
    """每张表 (列数, 数据行数, 表头行号)。"""
    out, lines, i = [], plain.splitlines(), 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("|") and i + 1 < len(lines) and _is_sep(lines[i + 1]):
            cols = line.strip("|").split("|")
            j, rows = i + 2, 0
            while j < len(lines) and lines[j].strip().startswith("|"):
                rows += 1
                j += 1
            out.append((len(cols), rows, i + 1))
            i = j
        else:
            i += 1
    return out


def is_lang_link(target):
    return os.path.basename(target).lower() in LANG_SELF


def section_lists(plain):
    """逐节统计 (无序条目数, 有序条目数, 本节起始行号)；第 0 节是首个标题之前的引言。"""
    out, bullets, ordered, start = [], 0, 0, 1
    for no, line in enumerate(plain.splitlines(), 1):
        if HEADING_RE.match(line):
            out.append((bullets, ordered, start))
            bullets, ordered, start = 0, 0, no
            continue
        if BULLET_RE.match(line):
            bullets += 1
        elif ORDERED_RE.match(line):
            ordered += 1
    out.append((bullets, ordered, start))
    return out


def links(plain):
    body = INLINE_CODE_RE.sub("", plain)
    return [t for t in LINK_RE.findall(body) if not is_lang_link(t)]


def digits(plain):
    # 行内代码里的数字也是事实（如 `0 error`），不剔除；围栏内容已在 split_fences 里置空
    return DIGIT_RE.findall(plain)


def line_of(plain, needle):
    for no, line in enumerate(plain.splitlines(), 1):
        if needle in line:
            return no
    return 0


def token_line(plain, token):
    pat = re.compile(r"(?<![\w.])" + re.escape(token) + r"(?![\w.])")
    for no, line in enumerate(plain.splitlines(), 1):
        if pat.search(line):
            return no
    return 0


def _fmt(zh_line, en_line, zh_name, en_name):
    parts = []
    if zh_line:
        parts.append("%s:%d" % (zh_name, zh_line))
    if en_line:
        parts.append("%s:%d" % (en_name, en_line))
    return " | ".join(parts)


def check_pair(zh_text, en_text, zh_name="README.md", en_name="README.en.md"):
    """返回 findings 列表：{code, message, zh_line, en_line}。空列表 = 同步。"""
    findings = []
    zh_plain, zh_blocks = split_fences(zh_text)
    en_plain, en_blocks = split_fences(en_text)

    def add(code, message, zh_line=0, en_line=0):
        findings.append({"code": code, "message": message,
                         "zh_line": zh_line, "en_line": en_line})

    # R2 项目名
    zh_h, en_h = headings(zh_plain), headings(en_plain)
    if not zh_h or not en_h:
        add("R1", "缺少 H1 标题：%s %d 个 / %s %d 个"
            % (zh_name, len(zh_h), en_name, len(en_h)),
            zh_h[0][2] if zh_h else 1, en_h[0][2] if en_h else 1)
    elif zh_h[0][1] != en_h[0][1]:
        add("R2", "H1 标题不一致：中文「%s」vs 英文「%s」" % (zh_h[0][1], en_h[0][1]),
            zh_h[0][2], en_h[0][2])

    # R1 标题骨架
    zh_levels = [h[0] for h in zh_h]
    en_levels = [h[0] for h in en_h]
    if zh_levels != en_levels:
        common = min(len(zh_levels), len(en_levels))
        for k in range(common):
            if zh_levels[k] != en_levels[k]:
                add("R1", "第 %d 个标题层级不一致：中文 h%d「%s」vs 英文 h%d「%s」"
                    % (k + 1, zh_levels[k], zh_h[k][1], en_levels[k], en_h[k][1]),
                    zh_h[k][2], en_h[k][2])
                break
        else:
            longer_zh = len(zh_levels) > len(en_levels)
            side_h = zh_h[common] if longer_zh else en_h[common]
            add("R1", "标题数量不一致：中文 %d 个 / 英文 %d 个；多出来的是 %s 的 h%d「%s」"
                % (len(zh_levels), len(en_levels), "中文" if longer_zh else "英文",
                   side_h[0], side_h[1]),
                side_h[2] if longer_zh else 0, side_h[2] if not longer_zh else 0)

    # R3 代码块
    zh_langs = [b[0] for b in zh_blocks]
    en_langs = [b[0] for b in en_blocks]
    if zh_langs != en_langs:
        add("R3", "代码块序列不一致：中文 %s vs 英文 %s"
            % (zh_langs, en_langs),
            zh_blocks[min(len(zh_blocks), len(en_blocks))][1] if zh_blocks else 0,
            en_blocks[min(len(zh_blocks), len(en_blocks))][1] if en_blocks else 0)
    else:
        for idx, (zb, eb) in enumerate(zip(zh_blocks, en_blocks)):
            (zlang, zstart, zbody), (elang, estart, ebody) = zb, eb
            if not zlang:
                if len(zbody) != len(ebody):
                    add("R3", "第 %d 个代码块行数不一致（纯文本块）：中文 %d 行 / 英文 %d 行"
                        % (idx + 1, len(zbody), len(ebody)), zstart, estart)
                continue
            zc, ec = commands_of(zbody), commands_of(ebody)
            if [c[0] for c in zc] == [c[0] for c in ec]:
                continue
            common = min(len(zc), len(ec))
            k = 0
            while k < common and zc[k][0] == ec[k][0]:
                k += 1
            if k < common:
                add("R3", "第 %d 个代码块第 %d 条命令不一致：中文「%s」vs 英文「%s」"
                    % (idx + 1, k + 1, zc[k][0], ec[k][0]),
                    zstart + 1 + zc[k][1], estart + 1 + ec[k][1])
            else:
                more_zh = len(zc) > len(ec)
                more = zc[common] if more_zh else ec[common]
                add("R3", "第 %d 个代码块命令条数不一致：中文 %d 条 / 英文 %d 条；%s 多一条「%s」"
                    % (idx + 1, len(zc), len(ec), "中文" if more_zh else "英文", more[0]),
                    zstart + 1 + more[1] if more_zh else 0,
                    estart + 1 + more[1] if not more_zh else 0)

    # R4 表格形状
    zt, et = tables(zh_plain), tables(en_plain)
    zshape = [(t[0], t[1]) for t in zt]
    eshape = [(t[0], t[1]) for t in et]
    if zshape != eshape:
        common = min(len(zt), len(et))
        for k in range(common):
            if zshape[k] != eshape[k]:
                add("R4", "第 %d 张表形状不一致：中文 %d 列 × %d 行 vs 英文 %d 列 × %d 行"
                    % (k + 1, zt[k][0], zt[k][1], et[k][0], et[k][1]),
                    zt[k][2], et[k][2])
                break
        else:
            more_zh = len(zt) > len(et)
            t = zt[common] if more_zh else et[common]
            add("R4", "表格数量不一致：中文 %d 张 / 英文 %d 张；%s 多一张（%d 列 × %d 行）"
                % (len(zt), len(et), "中文" if more_zh else "英文", t[0], t[1]),
                t[2] if more_zh else 0, t[2] if not more_zh else 0)

    # R5 数字事实（多重集合）
    from collections import Counter
    zd, ed = Counter(digits(zh_plain)), Counter(digits(en_plain))
    only_zh = zd - ed
    only_en = ed - zd
    if only_zh or only_en:
        zt_ = sorted(only_zh)
        et_ = sorted(only_en)
        add("R5", "数字事实不一致：只在中文 %s；只在英文 %s"
            % (dict(sorted(only_zh.items())), dict(sorted(only_en.items()))),
            token_line(zh_plain, zt_[0]) if zt_ else 0,
            token_line(en_plain, et_[0]) if et_ else 0)

    # R6 链接集合（多重集合，排除语言互链）
    zl, el = Counter(links(zh_plain)), Counter(links(en_plain))
    if zl != el:
        zonly = sorted(zl - el)
        eonly = sorted(el - zl)
        add("R6", "链接集合不一致：只在中文 %s；只在英文 %s"
            % (dict(sorted((zl - el).items())), dict(sorted((el - zl).items()))),
            line_of(zh_plain, zonly[0]) if zonly else 0,
            line_of(en_plain, eonly[0]) if eonly else 0)

    # R7 语言互链
    zh_all = LINK_RE.findall(INLINE_CODE_RE.sub("", zh_plain))
    en_all = LINK_RE.findall(INLINE_CODE_RE.sub("", en_plain))
    if not any(t.lower().endswith("readme.en.md") for t in zh_all):
        add("R7", "中文版没有链到 README.en.md（语言互链丢了）", 1, 0)
    if not any(t.lower().endswith("readme.md") and not t.lower().endswith("readme.en.md")
               for t in en_all):
        add("R7", "英文版没有链到 README.md（语言互链丢了）", 0, 1)

    # R8 逐节列表条目数
    zs, es = section_lists(zh_plain), section_lists(en_plain)
    for k in range(min(len(zs), len(es))):
        if zs[k][0] != es[k][0] or zs[k][1] != es[k][1]:
            add("R8", "第 %d 节列表条目不一致：中文 %d 条无序 / %d 条有序 vs 英文 %d 条无序 / %d 条有序"
                % (k + 1, zs[k][0], zs[k][1], es[k][0], es[k][1]),
                zs[k][2], es[k][2])
            break
    if len(zs) != len(es):
        add("R8", "分节数不一致：中文 %d 节 / 英文 %d 节（标题骨架应先过 R1）"
            % (len(zs), len(es)), 0, 0)

    return findings


def print_findings(findings, zh_name, en_name, quiet):
    if not quiet:
        for f in findings:
            loc = _fmt(f["zh_line"], f["en_line"], zh_name, en_name)
            print("  ERROR [%s] %s%s" % (f["code"], f["message"],
                                         ("  (" + loc + ")") if loc else ""))
    counts = {}
    for f in findings:
        counts[f["code"]] = counts.get(f["code"], 0) + 1
    detail = " ".join("%s=%d" % (c, counts[c]) for c in sorted(counts))
    print("README 同步：errors=%d%s" % (len(findings), ("  " + detail) if detail else ""))
    return 1 if findings else 0


# ---------------------------------------------------------------- 自证（反例）
BASE_ZH = """\
# demo

**中文** | [English](./README.en.md)

## 这是什么

一段说明，判定 `0 error` 才算过。

| 想知道 | 读 |
|---|---|
| 定位 | [SKILL.md](./SKILL.md) |

## 四条承诺

- 一处定义
- 可回溯

## 快速开始

```bash
python scripts/self_test.py   # 跑一遍自测
cd <你的项目根目录>
```
"""

BASE_EN = """\
# demo

[中文](./README.md) | **English**

## What This Is

Some text; `0 error` is required.

| To learn | Read |
|---|---|
| Positioning | [SKILL.md](./SKILL.md) |

## Four Promises

- One definition
- Traceable

## Quick Start

```bash
python scripts/self_test.py   # run the self-test
cd <your-project-root>
```
"""


def self_check():
    """检查器也吃反例：好对子必须 0，每个轴单独改一版必须红。"""
    cases = []

    def expect(name, zh, en, code):
        findings = check_pair(zh, en)
        got = sorted({f["code"] for f in findings})
        ok = (got == [] if code is None else code in got)
        cases.append((name, ok, got, code))

    expect("两份同构 → 通过", BASE_ZH, BASE_EN, None)
    expect("只改中文：多一节 → R1",
           BASE_ZH + "\n## 新增一节\n\n说明。\n", BASE_EN, "R1")
    expect("只改英文：代码块少一条命令 → R3",
           BASE_ZH, BASE_EN.replace("cd <your-project-root>\n", ""), "R3")
    expect("只改中文：表格多一行 → R4",
           BASE_ZH.replace("| 定位 | [SKILL.md](./SKILL.md) |",
                           "| 定位 | [SKILL.md](./SKILL.md) |\n| 命令 | `doc_check` |"),
           BASE_EN, "R4")
    expect("只改英文：数字改掉 → R5",
           BASE_ZH, BASE_EN.replace("`0 error`", "`1 error`"), "R5")
    expect("只改中文：多一个链接 → R6",
           BASE_ZH.replace("[SKILL.md](./SKILL.md)",
                           "[SKILL.md](./SKILL.md) [LICENSE](./LICENSE)"), BASE_EN, "R6")
    expect("只改英文：语言互链丢了 → R7",
           BASE_ZH, BASE_EN.replace("[中文](./README.md) | ", ""), "R7")
    expect("只改英文：少一条要点 → R8",
           BASE_ZH, BASE_EN.replace("- Traceable\n", ""), "R8")

    print("README 同步检查器自证（--self-check）")
    failed = 0
    for name, ok, got, code in cases:
        print("  %s  %s%s" % ("PASS" if ok else "FAIL", name,
                              "" if ok else "   — 得到 %s，期望 %s" % (got, code or "通过")))
        failed += 0 if ok else 1
    print("自证：%d/%d 通过" % (len(cases) - failed, len(cases)))
    return 1 if failed else 0


def main():
    ap = argparse.ArgumentParser(description="中英 README 结构同步检查")
    ap.add_argument("--zh", default=DEFAULT_ZH, help="中文版（默认仓库根 README.md）")
    ap.add_argument("--en", default=DEFAULT_EN, help="英文版（默认仓库根 README.en.md）")
    ap.add_argument("--self-check", action="store_true", help="用样本自证检查器会红")
    ap.add_argument("--quiet", action="store_true", help="只打结论行")
    ap.add_argument("--json", action="store_true", help="机器可读输出")
    args = ap.parse_args()

    if args.self_check:
        return self_check()

    missing = [p for p in (args.zh, args.en) if not os.path.exists(p)]
    if missing:
        print("找不到文件：%s（--zh/--en 可指定）" % "、".join(missing))
        return 2

    zh_name = os.path.basename(args.zh)
    en_name = os.path.basename(args.en)
    findings = check_pair(read(args.zh), read(args.en), zh_name, en_name)

    if args.json:
        print(json.dumps({
            "ok": not findings,
            "zh": zh_name,
            "en": en_name,
            "errors": findings,
        }, ensure_ascii=False, indent=2))
        return 1 if findings else 0

    if not args.quiet:
        print("README 同步检查：%s ↔ %s" % (zh_name, en_name))
    if not findings and not args.quiet:
        print("  标题骨架 / 项目名 / 代码块命令 / 表格形状 / 数字事实 / 链接集合 一致")
    return print_findings(findings, zh_name, en_name, args.quiet)


if __name__ == "__main__":
    sys.exit(main())
