#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""技能自测：把 SKILL.md 的验收清单跑成断言。

用法：
    python scripts/self_test.py            # 全部跑一遍
    python scripts/self_test.py -v         # 打印每条断言

为什么要有这个文件：
    旧版包曾在 check-rules.md 里写了 W4/W5，代码却从未实现——因为验收清单只是「一段文字」，
    没人逐条跑过。把验收变成可执行断言，是防止规则与实现再次漂移的唯一可靠办法。
"""
from __future__ import annotations

import ast
import datetime
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import tokenize

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

SKILL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable
VERBOSE = "-v" in sys.argv

PASS, FAIL = [], []


def run(script, *args, cwd, timeout=180):
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    try:
        p = subprocess.run([PY, os.path.join("scripts", script), *args],
                           cwd=cwd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", env=env, timeout=timeout)
    except subprocess.TimeoutExpired:
        # 卡住必须变成一次明确失败，而不是让 CI 一直等（ISS-025）
        if VERBOSE:
            print(f"    $ {script} {' '.join(args)}  -> TIMEOUT {timeout}s")
        return 124, f"TIMEOUT after {timeout}s: {script} {' '.join(args)}"
    if VERBOSE:
        print(f"    $ {script} {' '.join(args)}  -> exit {p.returncode}")
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"   — {detail}" if detail and not cond else ""))


def read(p):
    with open(p, encoding="utf-8") as fh:
        return fh.read()


def write(p, s):
    with open(p, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(s)


FEATURE_ANCHOR = "| **F-001** |"
TASK_ANCHOR = "| **T1.1.1** |"


def insert_after(text, anchor, row):
    """把一行插到表里 anchor 之后。

    追加到文件末尾会落进**最后一张表**——FEATURES 现在有两张表，功能行会静默变成
    任务考核行，校验看不见它（这个坑就是这样暴露出来的）。
    """
    lines = text.splitlines()
    for i, ln in enumerate(lines):
        if ln.startswith(anchor):
            lines.insert(i + 1, row)
            return "\n".join(lines) + "\n"
    raise AssertionError("找不到锚点：" + anchor)


def codes(out):
    return set(re.findall(r"\[([EWDSP]\d+)\]", out)) | set(re.findall(r"\[([EWDSP]\d+)\]", out))


def main():
    tmp = tempfile.mkdtemp(prefix="ddd-selftest-")
    print(f"临时项目: {tmp}\n")
    try:
        # ---------------------------------------------------------------- 1
        print("\n1. 铺骨架后首跑全绿")
        run(os.path.join(SKILL, "scripts", "doc_init.py"), "--target", ".", "--full", cwd=tmp)
        c, out = run("doc_check.py", "--quiet", cwd=tmp)
        check("doc_init + doc_check 为 0 error", c == 0 and "errors=0" in out, out.strip()[-200:])
        check("_schema.json 已生成", os.path.exists(os.path.join(tmp, "docs", "_schema.json")))

        # ISS-052 / ISS-053：主干道第 8 格「对照」原先指向技能包内的模板，
        # 用户项目里根本不存在那个文件；现在随 doc_init 落地，且表头口径与 SKILL 一致。
        fc = os.path.join(tmp, "docs", "40-运行", "功能对照.md")
        check("功能对照清单随 doc_init 落地（ISS-052）", os.path.exists(fc))
        if os.path.exists(fc):
            with open(fc, encoding="utf-8") as fh:
                fc_body = fh.read()
            check("对照清单表头是四列、含「差异」（ISS-053）",
                  "| 结论 |" in fc_body and "差异" in fc_body,
                  fc_body.splitlines()[-2][:120] if len(fc_body.splitlines()) > 1 else "")

        # 结构默认值只在一处：assets/default-schema.json（ISS-067 / ISS-068）。
        # 以前 doc_init 自带 BASE_LAYERS / EXTRA_LAYERS / SCHEMA_TEMPLATE 一份副本，
        # 「加层只改 _schema.json」就成了假话——照规则改，新项目根本铺不出新层。
        dflt = os.path.join(SKILL, "assets", "default-schema.json")
        proj = os.path.join(tmp, "docs", "_schema.json")
        check("assets/default-schema.json 存在", os.path.exists(dflt))
        if os.path.exists(dflt) and os.path.exists(proj):
            with open(dflt, encoding="utf-8") as fh:
                d = json.load(fh)
            with open(proj, encoding="utf-8") as fh:
                p = json.load(fh)
            check("_schema.json 的枚举 / 段结构 / 文件名来自 assets/default-schema.json（ISS-068）",
                  all(p.get(k) == v for k, v in d["schema"].items()))
            check("--full 的层 = base + extra，两者同出一份 asset（ISS-068）",
                  p.get("layers") == {**d["layer_sets"]["base"], **d["layer_sets"]["extra"]})

        # 默认（不带 --full）只铺 5 层。这条路径曾因 layers 与内置 8 层合并而报 3 条假 E9，
        # 而本文件以前一律带 --full，所以 32 条断言全绿也没拦住它。
        tmp5 = tempfile.mkdtemp(prefix="ddd-selftest5-")
        try:
            run(os.path.join(SKILL, "scripts", "doc_init.py"), "--target", ".", cwd=tmp5)
            c, out = run("doc_check.py", "--quiet", cwd=tmp5)
            check("默认 5 层铺骨架首跑 0 error", c == 0 and "errors=0" in out, out.strip()[-200:])
            # 同一个项目后补 --full：层表必须跟着合并，否则三层文档全报 E3（A2 原缺陷）
            run(os.path.join(SKILL, "scripts", "doc_init.py"), "--target", ".", "--full", cwd=tmp5)
            c, out = run("doc_check.py", "--quiet", cwd=tmp5)
            check("已初始化项目补 --full 后仍 0 error", c == 0 and "errors=0" in out,
                  out.strip()[-200:])
        finally:
            shutil.rmtree(tmp5, ignore_errors=True)

        # ---------------------------------------------------------------- 2
        print("\n2. 建档编号与文件名")
        c, out = run("devlog.py", "new", "--title", "自测会话", "--scope", "自测", cwd=tmp)
        sess = os.path.join(tmp, "docs", "70-过程", "会话")
        files = sorted(os.listdir(sess)) if os.path.isdir(sess) else []
        check("建出 001 会话档案",
              len(files) == 1 and re.fullmatch(r"\d{4}-\d{2}-\d{2}-001-自测会话\.md", files[0] or ""),
              str(files))
        run("devlog.py", "new", "--title", "第二场", "--scope", "自测", cwd=tmp)
        files = sorted(os.listdir(sess))
        check("同日第二份递增到 002", any("-002-" in f for f in files), str(files))

        # ---------------------------------------------------------------- 3
        print("\n3. 五类错误都能报出（E7 / E10 / E5 / D1 / P4）")
        req = os.path.join(tmp, "docs", "20-契约", "requirements.md")
        write(req, read(req) + "\n[断链](不存在.md)\n")
        adr = os.path.join(tmp, "docs", "30-决策", "adr", "ADR-001-示例决策.md")
        write(adr, read(adr).split("## 撤销条件")[0])
        feat = os.path.join(tmp, "docs", "40-运行", "FEATURES.md")
        write(feat, re.sub(r'summary: "[^"]*"', 'summary: "' + "超" * 90 + '"', read(feat)))
        inbox = os.path.join(tmp, "docs", "70-过程", "问题收件箱.md")
        s = read(inbox).splitlines()
        row = ("| **ISS-002** | 2026-10-29 | 自测 | 风险 | 可关闭 | 甲 | 乙 | 实现关闭 "
               "| 关闭：已修 | — | — | 2026-10-29 |")
        s = [ln for ln in s]
        for i, ln in enumerate(s):
            if ln.startswith("| **ISS-001**"):
                s.insert(i + 1, row)
                break
        write(inbox, "\n".join(s).replace(
            "| — | — | — | — |",
            "| **ISS-002** | 已修 | commit abc1234 | 2026-10-29 |"))
        plan = os.path.join(tmp, "docs", "00-门面", "开发计划.md")
        write(plan, read(plan).replace(
            "| **T1.1.1** | （示例）跑通并记录 | F-001 | W1.1 | 待开工 | - | 5 | 5 | 4 | 3 | 4 | 3 |",
            "| **T1.1.1** | （示例）跑通并记录 | F-001 | W1.1 | 待开工 | - | 6 | 5 | 4 | 3 | 4 | 3 |"))

        _, out = run("doc_check.py", cwd=tmp)
        got = codes(out)
        check("E7 断链", "E7" in got, out[-300:])
        check("E10 ADR 缺段", "E10" in got)
        check("E5 summary 超长", "E5" in got)
        _, dout = run("devlog.py", "check", cwd=tmp)
        check("D1 收件箱编号重复", "D1" in dout, dout[-300:])
        _, pout = run("plan.py", "check", cwd=tmp)
        check("P4 分值越界（必须带码打印，供 CI grep）", "[P4]" in pout, pout[-300:])

        # E28：cell 里未转义的竖线会让整行错位（ISS-070）。这类错位以前只有 CI 的
        # verify 撞得到——本仓 REQ-014 就是带着 12 格的行跑了半天绿。
        tmp28 = tempfile.mkdtemp(prefix="ddd-selftest28-")
        try:
            run(os.path.join(SKILL, "scripts", "doc_init.py"),
                "--target", ".", "--full", cwd=tmp28)
            req28 = os.path.join(tmp28, "docs", "20-契约", "requirements.md")
            base28 = read(req28)
            write(req28, insert_after(base28, "| **REQ-001** |",
                  "| **REQ-098** | WHEN 甲 THE SYSTEM SHALL 乙 | 表头是 | ID | 状态 | | "
                  "`echo 1` | 已实现 | 甲 | 采纳✓ 2026-11-03｜自测 |"))
            _, out = run("doc_check.py", cwd=tmp28)
            check("E28 未转义竖线让整行错位（ISS-070）", "E28" in codes(out), out[-300:])
            write(req28, insert_after(base28, "| **REQ-001** |",
                  "| **REQ-098** | WHEN 甲 THE SYSTEM SHALL 乙 | 表头是 \\| ID \\| 状态 \\| 三列 | "
                  "`echo 1` | 已实现 | 甲 | 采纳✓ 2026-11-03｜自测 |"))
            _, out = run("doc_check.py", cwd=tmp28)
            check("转义后的竖线不再报 E28（切表与校验同口径）",
                  "E28" not in codes(out), out[-300:])
            write(req28, insert_after(base28, "| **REQ-001** |",
                  "| **REQ-098** | WHEN 甲 THE SYSTEM SHALL 乙 | 验收句 | `echo 1` | 已实现 | 甲 | 采纳✓ 2026-11-03｜自测"))
            _, out = run("doc_check.py", cwd=tmp28)
            check("E28 表尾截断（行首有竖线、行尾没有）报出且文案含「截断」",
                  "E28" in codes(out) and "截断" in out, out[-300:])
            write(req28, base28)
            _, out = run("doc_check.py", cwd=tmp28)
            check("补回行尾竖线后不再报 E28", "E28" not in codes(out), out[-300:])
        finally:
            shutil.rmtree(tmp28, ignore_errors=True)

        # ---------------------------------------------------------------- 4
        print("\n4. 生成区幂等")
        # 上一步故意留了非法分值，先修回来——plan index 在分值非法时拒绝写盘是正确行为
        write(plan, read(plan).replace(
            "| **T1.1.1** | （示例）跑通并记录 | F-001 | W1.1 | 待开工 | - | 6 | 5 | 4 | 3 | 4 | 3 |",
            "| **T1.1.1** | （示例）跑通并记录 | F-001 | W1.1 | 待开工 | - | 5 | 5 | 4 | 3 | 4 | 3 |"))
        c0, _ = run("plan.py", "index", "--check", cwd=tmp)
        run("plan.py", "index", cwd=tmp)
        c1, out1 = run("plan.py", "index", "--check", cwd=tmp)
        check("index --check 先报过时、重建后转 up-to-date",
              c0 != 0 and c1 == 0 and "up-to-date" in out1, out1)

        # ---------------------------------------------------------------- 5
        print("\n5. 时间线倒序且链接可点")
        run("devlog.py", "index", cwd=tmp)
        tl = read(os.path.join(tmp, "docs", "70-过程", "时间线.md"))
        rows = re.findall(r"^\| (\d{4}-\d{2}-\d{2}) \|", tl, flags=re.M)
        check("时间线列出全部会话", len(rows) >= 2, str(rows))
        check("时间线按日期倒序", rows == sorted(rows, reverse=True), str(rows))
        links = re.findall(r"\]\((\./会话/[^)]+)\)", tl)
        check("时间线链接指向存在的文件",
              bool(links) and all(
                  os.path.exists(os.path.join(tmp, "docs", "70-过程", l)) for l in links),
              str(links))

        # ---------------------------------------------------------------- 6
        print("\n6. 契约措辞与取代链")
        write(req, read(req).replace("必须", "应当"))
        _, out = run("doc_check.py", cwd=tmp)
        check("E13 契约层缺「必须」", "E13" in codes(out), out[-200:])
        write(adr, read(adr).replace("status: proposed", "status: superseded")
              .replace("adr_id: 001", "adr_id: 001\nsuperseded_by: ADR-099"))
        _, out = run("doc_check.py", cwd=tmp)
        check("E15 取代链指向不存在的 ADR", "E15" in codes(out), out[-200:])
        write(adr, read(adr).replace("superseded_by: ADR-099", "superseded_by: 待补"))
        _, out = run("doc_check.py", cwd=tmp)
        check("W4 取代者为占位", "W4" in codes(out), out[-200:])

        # ---------------------------------------------------------------- 7
        print("\n7. 目录改名不产生假通过")
        tmp2 = tempfile.mkdtemp(prefix="ddd-selftest2-")
        try:
            run(os.path.join(SKILL, "scripts", "doc_init.py"),
                "--target", ".", "--docs", "文档", "--full", cwd=tmp2)
            c, out = run("doc_check.py", "--docs", "文档", "--quiet", cwd=tmp2)
            check("doc_check 能定位 文档/", c == 0, out[-200:])
            c, out = run("devlog.py", "new", "--title", "改名测试", cwd=tmp2)
            check("devlog 能定位 文档/", c == 0 and "created" in out, out[-200:])
            c, out = run("plan.py", "index", cwd=tmp2)
            check("plan 能定位 文档/", c == 0, out[-200:])
            shutil.move(os.path.join(tmp2, "文档", "70-过程"),
                        os.path.join(tmp2, "文档", "70-过程.bak"))
            c, out = run("devlog.py", "check", cwd=tmp2)
            check("过程层缺失时 exit 2（不再假通过）", c == 2, f"exit={c} {out[-120:]}")
        finally:
            shutil.rmtree(tmp2, ignore_errors=True)

        # ---------------------------------------------------------------- 8
        print("\n8. 棘轮基线")
        run("doc_check.py", "--update-baseline", cwd=tmp)
        c, out = run("doc_check.py", "--baseline", "--quiet", cwd=tmp)
        check("基线内退出码为 0", c == 0, out[-200:])
        write(feat, read(feat) + "\n[再断一条](也没.md)\n")
        c, out = run("doc_check.py", "--baseline", cwd=tmp)
        check("超出基线时报 E17 且非 0", c != 0 and "E17" in codes(out), out[-300:])

        # ---------------------------------------------------------------- 9
        print("\n9. 跨天建档（v2.0.0 真实缺陷：doc_init 把模板里的 {{DATE}} 烤死在铺骨架那天）")
        tmp3 = tempfile.mkdtemp(prefix="ddd-selftest3-")
        try:
            run(os.path.join(SKILL, "scripts", "doc_init.py"), "--target", ".", "--full", cwd=tmp3)
            yest = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
            tpl = os.path.join(tmp3, "docs", "70-过程", "会话档案模板.md")
            # 模拟“骨架是昨天铺的”：模板里的日期停在昨天
            write(tpl, re.sub(r"(?m)^(updated|session_date): 20\d\d-\d\d-\d\d$",
                              lambda m: f"{m.group(1)}: {yest}", read(tpl)))
            c, out = run("devlog.py", "new", "--title", "今天开档", cwd=tmp3)
            c2, out2 = run("devlog.py", "check", cwd=tmp3)
            check("跨天开档后 devlog check 不再报 S7", c2 == 0 and "S7" not in out2,
                  f"exit={c2} {out2[-220:]}")
            sess_dir = os.path.join(tmp3, "docs", "70-过程", "会话")
            f3 = os.path.join(sess_dir, sorted(os.listdir(sess_dir))[-1])
            fm3 = dict(re.findall(r"(?m)^(session_date|session_no): (\S+)$", read(f3)))
            check("文件名前缀 = <session_date>-<session_no>-",
                  os.path.basename(f3).startswith(f"{fm3.get('session_date')}-{fm3.get('session_no')}-"),
                  f"{os.path.basename(f3)} {fm3}")
            run("devlog.py", "index", cwd=tmp3)
            row = [l for l in read(os.path.join(tmp3, "docs", "70-过程", "时间线.md")).splitlines()
                   if re.match(r"^\| \d{4}-\d\d-\d\d \|", l)]
            check("时间线日期列与档案 front-matter 同一天",
                  bool(row) and row[0].split("|")[1].strip() == fm3.get("session_date"), str(row[:1]))
            c3, out3 = run("devlog.py", "new", "--title", "补记昨天", "--date", yest, cwd=tmp3)
            c4, out4 = run("devlog.py", "check", cwd=tmp3)
            check("--date 补记历史日期后 check 仍 0 error", c4 == 0 and "S7" not in out4,
                  f"exit={c4} {out4[-220:]}")
            c5, out5 = run("doc_check.py", "--quiet", cwd=tmp3)
            check("跨天场景下 doc_check 仍 0 error（E6 未来日期没被引入）",
                  c5 == 0 and "errors=0" in out5, out5[-220:])
        finally:
            shutil.rmtree(tmp3, ignore_errors=True)

        # ---------------------------------------------------------------- 10
        print("\n10. 引用的存在性：前置编号、工作→方向（查不出来就会永久静默卡死）")
        ptext = read(plan)
        write(plan, ptext.replace("| 待开工 | - |", "| 待开工 | T8.8.8 |", 1))
        c, out = run("plan.py", "check", cwd=tmp)
        check("P11 前置编号不存在被报出", c != 0 and "[P11]" in out, out[-300:])
        write(plan, ptext)
        work_row = [l for l in ptext.splitlines() if l.startswith("| **W1.1**")]
        if work_row:
            write(plan, ptext.replace("| **W1.1** | （示例）端到端跑通一次 | D1",
                                      "| **W1.1** | （示例）端到端跑通一次 | D9", 1))
            c, out = run("plan.py", "check", cwd=tmp)
            check("P12 工作指向不存在的方向被报出", c != 0 and "[P12]" in out, out[-300:])
            write(plan, ptext)

        # ---------------------------------------------------------------- 11
        print("\n11. 配置损坏时不抛回溯")
        sch = os.path.join(tmp, "docs", "_schema.json")
        keep = read(sch)
        write(sch, "{ nope")
        for script, arg in (("doc_check.py", None), ("devlog.py", "check"),
                            ("plan.py", "check"), ("verify.py", None)):
            c, out = run(script, *([arg] if arg else []), cwd=tmp)
            check(f"{script} 配置损坏时给可读错误（不是 Traceback）",
                  "Traceback" not in out and c == 2, f"exit={c} {out[:160]}")
        write(sch, keep)

        # ---------------------------------------------------------------- 12
        print("\n12. 输入里的特殊字符与编码（标题引号 / 标题竖线 / UTF-8 BOM）")
        tmp4 = tempfile.mkdtemp(prefix="ddd-selftest4-")
        try:
            today = datetime.date.today().isoformat()
            run(os.path.join(SKILL, "scripts", "doc_init.py"), "--target", ".", "--full", cwd=tmp4)
            title = '他说"这样"行不行|A B'
            run("devlog.py", "new", "--title", title, "--scope", "重点: 引号", cwd=tmp4)
            sess_dir = os.path.join(tmp4, "docs", "70-过程", "会话")
            session = os.path.join(sess_dir, sorted(os.listdir(sess_dir))[0])
            text = read(session)
            m = re.search(r"(?m)^title: (.*)$", text)
            want = f"{today} · 001 · {title}"
            ok = False
            try:
                ok = m is not None and json.loads(m.group(1)) == want
            except ValueError:
                ok = False
            check("标题含双引号时 front-matter 仍是合法 YAML 字符串", ok,
                  (m.group(1) if m else "没有 title 行"))
            c, out = run("devlog.py", "check", cwd=tmp4)
            check("标题含双引号时 check 不误报 title≠H1", c == 0 and "S2" not in out, out[-220:])
            run("devlog.py", "index", cwd=tmp4)
            tl = read(os.path.join(tmp4, "docs", "70-过程", "时间线.md"))
            row = next((l for l in tl.splitlines() if l.startswith("| 2026")), "")
            cells = re.split(r"(?<!\\)\|", row.strip().strip("|")) if row else []
            check("标题含竖线时时间线仍是 7 列", len(cells) == 7,
                  f"{len(cells)} 列：{row[:90]}")
            bom = ("---\ntitle: \"BOM 文档\"\nlayer: facade\ndomain: 全局\nstatus: active\n"
                   f"authority: 2\nupdated: {today}\n"
                   "summary: \"带 BOM 的正文不该被当成缺 front-matter\"\ntags: []\n---\n\n"
                   "# BOM 文档\n\n正文。\n")
            with open(os.path.join(tmp4, "docs", "00-门面", "bom.md"), "wb") as fh:
                fh.write(b"\xef\xbb\xbf" + bom.encode("utf-8"))
            c, out = run("doc_check.py", cwd=tmp4)
            check("UTF-8 BOM 文件不报 E1", c == 0 and "errors=0" in out, out[-220:])
        finally:
            shutil.rmtree(tmp4, ignore_errors=True)

        # ---------------------------------------------------------------- 13
        print("\n13. 契约行的 verify: 缺失（T1.2.2）")
        tmp6 = tempfile.mkdtemp(prefix="ddd-selftest6-")
        try:
            run(os.path.join(SKILL, "scripts", "doc_init.py"),
                "--target", ".", "--full", cwd=tmp6)
            req6 = os.path.join(tmp6, "docs", "20-契约", "requirements.md")
            c, out = run("doc_check.py", "--quiet", cwd=tmp6)
            check("模板自带 verify: 时首跑不报 E18", c == 0 and "errors=0" in out,
                  out.strip()[-200:])

            original = read(req6)
            no_cell = original.replace("| `python tests/test_xxx.py` |", "|  |")
            check("确实删掉了示例行的 verify 单元格", no_cell != original)
            write(req6, no_cell)
            c, out = run("doc_check.py", cwd=tmp6)
            check("缺 verify 单元格 → exit 1 且报 E18",
                  c == 1 and "E18" in codes(out) and "REQ-001" in out, out[-300:])

            write(req6, original.replace("| `python tests/test_xxx.py` |", "| — |"))
            c, out = run("doc_check.py", cwd=tmp6)
            check("verify 写成占位「—」也算缺失（E18）",
                  c == 1 and "E18" in codes(out), out[-300:])

            # 变更记录里提到 REQ 编号不是条款行，不得误伤（ISS-018 的同类坑）
            write(req6, original + "\n| 2026-10-29 | 变更提到 REQ-003 | — |\n")
            c, out = run("doc_check.py", cwd=tmp6)
            check("非条款表提到 REQ-003 不报 E18", "E18" not in codes(out), out[-300:])
        finally:
            shutil.rmtree(tmp6, ignore_errors=True)

        # ---------------------------------------------------------------- 14
        print("\n14. 契约 verify 真跑（T1.2.3）")
        tmp7 = tempfile.mkdtemp(prefix="ddd-selftest7-")
        try:
            run(os.path.join(SKILL, "scripts", "doc_init.py"),
                "--target", ".", "--full", "--ci", cwd=tmp7)
            req7 = os.path.join(tmp7, "docs", "20-契约", "requirements.md")
            check("doc_init --ci 复制 verify.py",
                  os.path.exists(os.path.join(tmp7, "scripts", "verify.py")))
            ci7 = os.path.join(tmp7, ".github", "workflows", "docs.yml")
            check("模板 docs.yml 挂上 verify.py",
                  os.path.exists(ci7) and "verify.py" in read(ci7))

            c, out = run("verify.py", "--quiet", cwd=tmp7)
            check("示例行状态=待实现 时跳过，verify.py 0 退出",
                  c == 0 and "skipped=1" in out, out[-250:])

            original7 = read(req7)
            ok_cmd = f'"{PY}" -c "print(\'ok\')"'
            passing = original7.replace("| `python tests/test_xxx.py` |",
                                        f"| `{ok_cmd}` |").replace("| 待实现 |", "| 已实现 |", 1)
            check("测试夹具替换成功", f"`{ok_cmd}`" in passing and "| 已实现 |" in passing)
            write(req7, passing)
            c, out = run("verify.py", cwd=tmp7)
            check("verify 真跑并通过", c == 0 and "PASS" in out and "REQ-001" in out,
                  out[-250:])

            bad_cmd = f'"{PY}" -c "import sys; sys.exit(3)"'
            write(req7, passing.replace(ok_cmd, bad_cmd))
            c, out = run("verify.py", cwd=tmp7)
            check("verify 指向的测试失败 → exit 1",
                  c == 1 and "FAIL" in out and "REQ-001" in out, out[-300:])

            write(req7, passing.replace(f"| `{ok_cmd}` |", "|  |"))
            c, out = run("verify.py", cwd=tmp7)
            check("缺 verify 时 verify.py 也不假通过", c == 1 and "E18" in out, out[-300:])
        finally:
            shutil.rmtree(tmp7, ignore_errors=True)

        # ---------------------------------------------------------------- 15
        print("\n15. 契约增量：未合并 delta / 锚点冲突 / 归档不一致（T1.1.2）")
        tmp8 = tempfile.mkdtemp(prefix="ddd-selftest8-")
        try:
            run(os.path.join(SKILL, "scripts", "doc_init.py"),
                "--target", ".", "--full", cwd=tmp8)
            docs8 = os.path.join(tmp8, "docs")
            req8 = os.path.join(docs8, "20-契约", "requirements.md")
            delta_dir = os.path.join(docs8, "20-契约", "_delta")
            arch_dir = os.path.join(delta_dir, "_archive")
            os.makedirs(arch_dir)
            today8 = datetime.date.today().isoformat()
            base8 = read(req8)
            row1 = next(l for l in base8.splitlines() if l.startswith("| **REQ-001**"))
            row4 = row1.replace("REQ-001", "REQ-004", 1)
            row5 = row1.replace("REQ-001", "REQ-005", 1)

            def build_delta(no, status, changes, target="docs/20-契约/requirements.md"):
                return (
                    "---\n"
                    f'title: "DELTA-{no} · 自测增量"\n'
                    "layer: contract\ndomain: 全局\n"
                    f"status: {status}\nauthority: 1\n"
                    f"updated: {today8}\n"
                    f'summary: "自测增量 {no}：验证 doc_check 对 delta 的机器判据。"\n'
                    "tags: [契约, 增量]\n"
                    f"delta_id: DELTA-{no}\ntarget: {target}\n---\n\n"
                    f"# DELTA-{no} · 自测增量\n\n"
                    "本增量**必须**逐字应用锚点；**不得**手工凑合目标行。\n\n"
                    "## 2. 逐字变更\n\n" + changes
                )

            def put(no, status, changes, target="docs/20-契约/requirements.md", archived=False):
                d = arch_dir if archived else delta_dir
                p = os.path.join(d, f"DELTA-{no}-自测增量.md")
                write(p, build_delta(no, status, changes, target))
                return p

            added4 = (
                "**变更 1 · ADDED · REQ-004**\n\n"
                "位置：需求表末尾\n\n"
                "```markdown\n" + row4 + "\n```\n"
            )
            valid_mod = (
                "**变更 1 · MODIFIED · REQ-001**\n\n"
                "锚点（before，逐字，含首尾）：\n\n"
                "```markdown\n" + row1 + "\n```\n\n"
                "合并后（after，逐字）：\n\n"
                "```markdown\n" + row1.replace("待实现", "已实现") + "\n```\n"
            )

            p4 = put("004", "proposed", added4)
            c, out = run("doc_check.py", cwd=tmp8)
            check("根目录 status: proposed 的 delta → E19、exit 1",
                  c == 1 and "E19" in codes(out) and "DELTA-004" in out, out[-300:])
            check("同一篇的 ADDED 锚点合法时不报 E20（不误伤）",
                  "E20" not in codes(out), out[-300:])
            check("围栏内的增量行带 verify: → 不报 E18",
                  "E18" not in codes(out), out[-300:])

            os.remove(p4)
            put("004", "snapshot", added4, archived=True)
            c, out = run("doc_check.py", cwd=tmp8)
            check("归档 delta 的 after 未进目标 → E21、exit 1",
                  c == 1 and "E21" in codes(out), out[-300:])

            write(req8, base8.replace(row1 + "\n", row1 + "\n" + row4 + "\n", 1))
            merged8 = read(req8)
            c, out = run("doc_check.py", cwd=tmp8)
            check("合并后（目标含 after、delta 已归档）→ 0 error（W1.1 验收：主文件无冲突）",
                  c == 0 and "errors=0" in out, out[-300:])

            put("006", "proposed", added4)
            c, out = run("doc_check.py", cwd=tmp8)
            check("ADDED 的编号已存在于目标 → E20",
                  c == 1 and "E20" in codes(out) and "已出现" in out, out[-300:])
            os.remove(os.path.join(delta_dir, "DELTA-006-自测增量.md"))

            dup_before = (
                "**变更 1 · MODIFIED · REQ-001**\n\n"
                "锚点（before，逐字，含首尾）：\n\n"
                "```markdown\n| `python tests/test_xxx.py` | 待实现 |\n```\n\n"
                "合并后（after，逐字）：\n\n"
                "```markdown\n| `python tests/test_xxx.py` | 已实现 |\n```\n"
            )
            p7 = put("007", "proposed", dup_before)
            c, out = run("doc_check.py", cwd=tmp8)
            check("before 锚点出现 2 次 → E20（不唯一）",
                  c == 1 and "E20" in codes(out) and "2 次" in out, out[-300:])

            put("007", "proposed", dup_before.replace(
                "| `python tests/test_xxx.py` | 待实现 |",
                "| **REQ-009** | 目标里没有这一行 |"))
            c, out = run("doc_check.py", cwd=tmp8)
            check("before 锚点 0 次 → E20（不存在）",
                  c == 1 and "E20" in codes(out) and "0 次" in out, out[-300:])

            put("007", "proposed",
                "**变更 1 · MODIFIED · REQ-001**\n\n"
                "合并后（after，逐字）：\n\n"
                "```markdown\n| `python tests/test_xxx.py` | 已实现 |\n```\n")
            c, out = run("doc_check.py", cwd=tmp8)
            check("缺 before 代码块 → E20", c == 1 and "缺 before" in out, out[-300:])
            os.remove(p7)

            write(req8, merged8.replace(row4, row4.replace("待实现", "已实现"), 1))
            c, out = run("doc_check.py", cwd=tmp8)
            check("归档的 after 与目标不再一致 → E21",
                  c == 1 and "E21" in codes(out), out[-300:])

            write(req8, merged8 + "\n<<<<<<< HEAD\nx\n=======\ny\n>>>>>>> branch\n")
            p8 = put("008", "proposed", valid_mod)
            c, out = run("doc_check.py", cwd=tmp8)
            check("目标文件含合并冲突标记 → E20", c == 1 and "冲突标记" in out, out[-300:])
            write(req8, merged8)
            os.remove(p8)

            row5_bad = row5.replace("`python tests/test_xxx.py`", "—")
            p9 = put("009", "proposed",
                     "**变更 1 · ADDED · REQ-005**\n\n位置：需求表末尾\n\n"
                     "```markdown\n" + row5_bad + "\n```\n")
            c, out = run("doc_check.py", cwd=tmp8)
            check("围栏内增量行缺 verify: → 仍报 E18（围栏不是假通过通道）",
                  c == 1 and "E18" in codes(out) and "REQ-005" in out, out[-300:])
            os.remove(p9)

            p10 = put("010", "proposed", valid_mod, archived=True)
            c, out = run("doc_check.py", cwd=tmp8)
            check("归档目录里的 delta 仍是 proposed → E19",
                  c == 1 and "E19" in codes(out) and "snapshot" in out, out[-300:])
            os.remove(p10)

            removed4 = (
                "**变更 1 · REMOVED · REQ-004**\n\n"
                "锚点（before，逐字，含首尾）：\n\n"
                "```markdown\n" + row4 + "\n```\n"
            )
            p11 = put("011", "snapshot", removed4, archived=True)
            c, out = run("doc_check.py", cwd=tmp8)
            check("归档的 REMOVED 行仍在目标里 → E21",
                  c == 1 and "E21" in codes(out), out[-300:])
            os.remove(p11)

            p12 = put("012", "proposed", valid_mod,
                      target="docs/20-契约/不存在.md")
            c, out = run("doc_check.py", cwd=tmp8)
            check("target 指向不存在的文件 → E20",
                  c == 1 and "E20" in codes(out) and "不存在" in out, out[-300:])
            os.remove(p12)
        finally:
            shutil.rmtree(tmp8, ignore_errors=True)

        # ---------------------------------------------------------------- 16
        print("\n16. 改动分级不改变校验结果（T2.1.1）")
        skill_md = read(os.path.join(SKILL, "SKILL.md"))
        rules = [ln for ln in skill_md.splitlines()
                 if re.match(r"^\d+\. \*\*改动分级\*\*", ln)]
        check("SKILL.md 硬规则里恰有一条「改动分级」判据", len(rules) == 1,
              f"{len(rules)} 条")
        check("体量判据同时给出轻档与重档（判据只有一条，不按 diff 行数）",
              bool(rules) and "轻档" in rules[0] and "重档" in rules[0],
              rules[0][:120] if rules else "缺改动分级规则")

        tmp9 = tempfile.mkdtemp(prefix="ddd-selftest9-")
        try:
            run(os.path.join(SKILL, "scripts", "doc_init.py"),
                "--target", ".", "--full", cwd=tmp9)
            vision9 = os.path.join(tmp9, "docs", "00-门面", "vision.md")
            req9 = os.path.join(tmp9, "docs", "20-契约", "requirements.md")
            c0, out0 = run("doc_check.py", "--quiet", cwd=tmp9)
            d0, dout0 = run("devlog.py", "check", cwd=tmp9)
            p0, pout0 = run("plan.py", "check", cwd=tmp9)

            # 轻档：只改一段正文（措辞），不碰契约 / ADR / 计划 / 码表 / 脚本
            write(vision9, read(vision9) + "\n这句只改措辞，不改任何事实源。\n")
            c1, out1 = run("doc_check.py", "--quiet", cwd=tmp9)
            check("轻档改动后 doc_check 结论不变（0 error / 0 warning）",
                  c1 == 0 and "errors=0" in out1 and "warnings=0" in out1
                  and out1.strip() == out0.strip(), out1[-200:])
            d1, dout1 = run("devlog.py", "check", cwd=tmp9)
            p1, pout1 = run("plan.py", "check", cwd=tmp9)
            check("轻档改动不改变 devlog / plan 的结论",
                  (d1, dout1.strip()) == (d0, dout0.strip())
                  and (p1, pout1.strip()) == (p0, pout0.strip()), pout1[-160:])

            # 轻档不是豁免：同一处改动里制造断链，照样报 E7
            write(vision9, read(vision9) + "\n[断链](不存在.md)\n")
            c2, out2 = run("doc_check.py", cwd=tmp9)
            check("轻档改动里制造断链 → E7 照报、exit 1",
                  c2 == 1 and "E7" in codes(out2), out2[-250:])

            # 分级不看 diff 行数：只删一个单元格的条款，仍完整过 E18
            write(req9, read(req9).replace("| `python tests/test_xxx.py` |", "|  |"))
            c3, out3 = run("doc_check.py", cwd=tmp9)
            check("条款行只改一个单元格照样报 E18（分级不按改动大小放行）",
                  c3 == 1 and "E18" in codes(out3) and "REQ-001" in out3, out3[-250:])
        finally:
            shutil.rmtree(tmp9, ignore_errors=True)

        # ---------------------------------------------------------------- 17
        print("\n17. 交接锚点与计划表互校（T2.2.1）")
        tmp10 = tempfile.mkdtemp(prefix="ddd-selftest10-")
        try:
            run(os.path.join(SKILL, "scripts", "doc_init.py"),
                "--target", ".", "--full", cwd=tmp10)
            sess10 = os.path.join(tmp10, "docs", "70-过程", "会话")
            plan10 = os.path.join(tmp10, "docs", "00-门面", "开发计划.md")
            run("devlog.py", "new", "--title", "交接锚点", "--scope", "自测", cwd=tmp10)
            f10 = os.path.join(sess10, sorted(os.listdir(sess10))[0])
            base10 = read(f10)

            def handoff(body):
                write(f10, re.sub(r"(?ms)^## 7\..*$",
                                  "## 7. 交接（下次从这里开始）\n\n" + body + "\n", base10))

            # 正例：首行「下一步：T1.1.1」，T1.1.1 在计划表里
            handoff("- **下一步**（用计划文档的任务编号）：**T1.1.1** —— 跑通并记录。\n"
                    "- **现在在哪**：自测；交接段首行已经锚定计划表里的任务编号。\n")
            c, out = run("devlog.py", "check", cwd=tmp10)
            check("交接首行锚定计划表里的编号 → 0 error",
                  c == 0 and "S8" not in out and "S9" not in out, out[-300:])

            # 缺锚点：首行是正文，锚点退到第二行且没有编号
            handoff("- **现在在哪**：自测；这一段已经写满四十个字，用来模拟收尾时忘了写锚点。\n"
                    "- **下一步**（用计划文档的任务编号）：待定。\n")
            c, out = run("devlog.py", "check", cwd=tmp10)
            check("交接首行没有锚点 → S8、exit 1", c == 1 and "S8" in out, out[-300:])

            # 编号不存在：计划表里没有 T9.9.9
            handoff("- **下一步**：**T9.9.9** —— 计划表里没有这条任务。\n"
                    "- **现在在哪**：自测；故意写一个不存在的编号。\n")
            c, out = run("devlog.py", "check", cwd=tmp10)
            check("交接锚点不在计划表 → S9、exit 1",
                  c == 1 and "S9" in out and "T9.9.9" in out, out[-300:])

            # 「无」不是省略：计划表还有未完成任务时不允许
            handoff("- **下一步**：无（自测收口）。\n"
                    "- **现在在哪**：自测；计划表里仍有待开工任务，不能写无。\n")
            c, out = run("devlog.py", "check", cwd=tmp10)
            check("写「下一步：无」但计划表仍有未完成任务 → S9",
                  c == 1 and "S9" in out, out[-300:])

            # 全部完成时，「无」是允许的显式出口
            write(plan10, read(plan10).replace("| 待开工 |", "| 已完成 |"))
            handoff("- **下一步**：无（计划表全部完成，本方向收口）。\n"
                    "- **现在在哪**：自测；计划表里已没有可排任务，显式写明没有下一步。\n")
            c, out = run("devlog.py", "check", cwd=tmp10)
            check("计划表全部完成时「下一步：无」→ 0 error",
                  c == 0 and "S9" not in out, out[-300:])

            # 模板本身要示范格式：交接段首行就是锚点行
            tpl_md = read(os.path.join(tmp10, "docs", "70-过程", "会话档案模板.md"))
            m = re.search(r"(?ms)^## 7\.[^\n]*\n(.*)$", tpl_md)
            first = next((ln for ln in (m.group(1).splitlines() if m else []) if ln.strip()), "")
            check("会话模板交接段首行是「下一步」", "下一步" in first, first[:100])
        finally:
            shutil.rmtree(tmp10, ignore_errors=True)

        # ---------------------------------------------------------------- 18
        print("\n18. 开场简报：先读一条命令（T2.3.1）")
        tmp11 = tempfile.mkdtemp(prefix="ddd-selftest11-")
        try:
            run(os.path.join(SKILL, "scripts", "doc_init.py"),
                "--target", ".", "--full", cwd=tmp11)

            # 空项目也必须能用：开场第一件事就是跑它，此时还没有任何档案
            c, out = run("devlog.py", "brief", cwd=tmp11)
            check("无档案时 brief 可用并提示先建档",
                  c == 0 and "尚无会话档案" in out, out[-300:])

            docs11 = os.path.join(tmp11, "docs")

            def snapshot(root):
                snap = {}
                for base, _, files in os.walk(root):
                    for f in files:
                        p = os.path.join(base, f)
                        with open(p, "rb") as fh:
                            snap[p] = hashlib.sha256(fh.read()).hexdigest()
                return snap

            run("devlog.py", "new", "--title", "开场简报", "--scope", "自测", cwd=tmp11)
            sess11 = os.path.join(docs11, "70-过程", "会话")
            f11 = os.path.join(sess11, sorted(os.listdir(sess11))[0])
            write(f11, re.sub(r"(?m)^- \*\*下一步\*\*[^\n]*$",
                              "- **下一步**：**T1.1.1** —— 跑通并记录。",
                              read(f11), count=1))

            before = snapshot(docs11)
            c, out = run("devlog.py", "brief", cwd=tmp11)
            after = snapshot(docs11)
            check("brief 复述上一场交接首行",
                  c == 0 and "下一步" in out and "T1.1.1" in out, out[-300:])
            check("brief 列出计划未完成任务", "未完成" in out and "T1.1.1" in out, out[-300:])
            check("brief 只读：跑前跑后文档字节不变", c == 0 and before == after, "brief 改动了文件")

            inbox11 = os.path.join(docs11, "70-过程", "问题收件箱.md")
            row11 = ("| **ISS-002** | 2026-10-30 | 自测 | 风险 | 开放 | 甲 | 乙 | 确立 "
                     "| 确立：自测 | 未排期 | 需要时 | 2026-10-30 |")
            write(inbox11, read(inbox11).replace(
                "| **ISS-001**", row11 + "\n| **ISS-001**", 1))
            c, out = run("devlog.py", "brief", cwd=tmp11)
            check("brief 给出收件箱 确立 / 实施中 计数",
                  c == 0 and "确立 2" in out and "实施中 0" in out, out[-300:])

            plan11 = os.path.join(docs11, "00-门面", "开发计划.md")
            write(plan11, read(plan11).replace("| 待开工 |", "| 已完成 |"))
            c, out = run("devlog.py", "brief", cwd=tmp11)
            check("计划全部完成时 brief 报未完成 0",
                  c == 0 and "未完成 0" in out, out[-300:])
        finally:
            shutil.rmtree(tmp11, ignore_errors=True)

        # ---------------------------------------------------------------- 19
        print("\n19. 用户侧落点必填（S10）")
        tmp12 = tempfile.mkdtemp(prefix="ddd-selftest12-")
        try:
            run(os.path.join(SKILL, "scripts", "doc_init.py"),
                "--target", ".", "--full", cwd=tmp12)
            run("devlog.py", "new", "--title", "落点必填", "--scope", "自测", cwd=tmp12)
            sess12 = os.path.join(tmp12, "docs", "70-过程", "会话")
            f12 = os.path.join(sess12, sorted(os.listdir(sess12))[0])
            base12 = read(f12)
            place = "| 1 | | | | | |"
            # 模板占位行变了就让自测先红，别静默跳过整条断言
            assert place in base12, "模板 §2 占位行格式变了"

            c, out = run("devlog.py", "check", cwd=tmp12)
            check("模板占位的 §2 行不报 S10", c == 0 and "S10" not in out, out[-300:])

            def with_row(row):
                write(f12, base12.replace(place, row, 1))
                return run("devlog.py", "check", cwd=tmp12)

            c, out = with_row("| 1 | Q | 「会不会自动记？」 | 机制追问 |  | 已答 |")
            check("§2 已填类型但落点为空 → S10、exit 1",
                  c == 1 and "S10" in out, out[-300:])

            c, out = with_row("| 1 | Q | 「会不会自动记？」 | 机制追问 | — | 已答 |")
            check("落点写成「—」占位 → S10", c == 1 and "S10" in out, out[-300:])

            c, out = with_row("| 1 | Q | 「会不会自动记？」 | 机制追问 | 待补 | 已答 |")
            check("落点写成「待补」→ S10", c == 1 and "S10" in out, out[-300:])

            c, out = with_row("| 1 | Q | 「会不会自动记？」 | 机制追问 | §3.1 | 已答 |")
            check("落点有实际指向 → 不报 S10", c == 0 and "S10" not in out, out[-300:])
        finally:
            shutil.rmtree(tmp12, ignore_errors=True)

        # ---------------------------------------------------------------- 20
        print("\n20. 待分诊问题与开工门禁（T2.5.1）")
        tmp13 = tempfile.mkdtemp(prefix="ddd-selftest13-")
        try:
            run(os.path.join(SKILL, "scripts", "doc_init.py"),
                "--target", ".", "--full", cwd=tmp13)
            run("devlog.py", "new", "--title", "第一场", "--scope", "自测", cwd=tmp13)
            c, out = run("devlog.py", "ask", "要不要拆任务？", "--if", "计划里还是一个任务",
                         cwd=tmp13)
            check("ask 记下一条待分诊", c == 0 and "Q1" in out, out[-300:])
            c, out = run("devlog.py", "pending", cwd=tmp13)
            check("pending 列出该条", c == 0 and "Q1" in out and "要不要拆任务" in out, out[-300:])

            c, out = run("devlog.py", "new", "--title", "第二场", cwd=tmp13)
            check("有待分诊项时 new 被拒、exit 1", c == 1 and "Q1" in out, out[-300:])

            c, out = run("devlog.py", "pending", "--clear", "Q1", "--as", "drop",
                         "--note", "问题已过期", cwd=tmp13)
            check("--as drop 写回状态并留理由", c == 0 and "dropped" in out, out[-300:])
            c, out = run("devlog.py", "new", "--title", "第二场", cwd=tmp13)
            check("清完之后 new 通过", c == 0, out[-300:])

            # 延期不阻断，但超过 5 条要挡住开工
            for i in range(6):
                run("devlog.py", "ask", "问题%d" % i, "--if", "前提还在", cwd=tmp13)
            for i in range(1, 7):
                run("devlog.py", "pending", "--clear", "Q%d" % i,
                    "--as", "defer", cwd=tmp13)
            c, out = run("devlog.py", "new", "--title", "第三场", cwd=tmp13)
            check("延期超过 5 条 → new 仍拒绝", c == 1 and "延期" in out, out[-300:])

            c, out = run("devlog.py", "brief", cwd=tmp13)
            check("brief 首屏给出待分诊计数", "待分诊" in out and "deferred 6" in out, out[-300:])

            pend13 = os.path.join(tmp13, ".dd", "pending")
            check("分诊后的 pending 文件保留（不静默删除）",
                  os.path.isdir(pend13) and any(f.endswith(".md") for f in os.listdir(pend13)))
        finally:
            shutil.rmtree(tmp13, ignore_errors=True)

        # ---------------------------------------------------------------- 21
        print("\n21. 跨项目找目录 + 时间线同步（ISS-028 / ISS-030）")
        tmp14 = tempfile.mkdtemp(prefix="ddd-selftest14-")
        try:
            run(os.path.join(SKILL, "scripts", "doc_init.py"),
                "--target", ".", "--full", cwd=tmp14)
            repo_sess = os.path.join(SKILL, "docs", "70-过程", "会话")
            before = sorted(os.listdir(repo_sess)) if os.path.isdir(repo_sess) else []
            env = dict(os.environ, PYTHONIOENCODING="utf-8")
            p = subprocess.run([PY, os.path.join(SKILL, "scripts", "devlog.py"),
                                "new", "--title", "串档探针", "--scope", "自测"],
                               cwd=tmp14, capture_output=True, text=True,
                               encoding="utf-8", errors="replace", env=env)
            tmp_sess = os.path.join(tmp14, "docs", "70-过程", "会话")
            after = sorted(os.listdir(repo_sess)) if os.path.isdir(repo_sess) else []
            made = sorted(os.listdir(tmp_sess)) if os.path.isdir(tmp_sess) else []
            check("开发副本的脚本按 cwd 找 docs（ISS-028）",
                  p.returncode == 0 and len(made) == 1 and before == after,
                  f"rc={p.returncode} tmp={made} repo_diff={sorted(set(after) - set(before))}")

            c, out = run("devlog.py", "check", cwd=tmp14)
            check("新建档案后 check 报 S11（时间线陈旧）", "S11" in out, out[-300:])
            run("devlog.py", "index", cwd=tmp14)
            c, out = run("devlog.py", "check", cwd=tmp14)
            check("重建时间线后 S11 消失", "S11" not in out, out[-300:])
        finally:
            shutil.rmtree(tmp14, ignore_errors=True)

        # ---------------------------------------------------------------- 22
        print("\n22. 历史交接的「无」不追溯（ISS-032）")
        tmp15 = tempfile.mkdtemp(prefix="ddd-selftest15-")
        try:
            run(os.path.join(SKILL, "scripts", "doc_init.py"),
                "--target", ".", "--full", cwd=tmp15)
            sess15 = os.path.join(tmp15, "docs", "70-过程", "会话")

            def first_line(path, text):
                write(path, re.sub(r"(?m)^- \*\*下一步\*\*[^\n]*$", text, read(path), count=1))

            run("devlog.py", "new", "--title", "旧场", "--scope", "自测", cwd=tmp15)
            f_old = os.path.join(sess15, sorted(os.listdir(sess15))[0])
            first_line(f_old, "- **下一步**：无（当时计划确实清空）")
            run("devlog.py", "new", "--title", "新场", "--scope", "自测", cwd=tmp15)
            f_new = os.path.join(sess15, sorted(os.listdir(sess15))[1])
            first_line(f_new, "- **下一步**：**T1.1.1** —— 跑通并记录。")

            c, out = run("devlog.py", "check", cwd=tmp15)
            check("更早的档案写「无」不因后来插任务变红",
                  c == 0 and "S9" not in out, out[-300:])

            first_line(f_new, "- **下一步**：无（最新一篇也说没有下一步）")
            c, out = run("devlog.py", "check", cwd=tmp15)
            check("最新一篇写「无」而计划仍有任务 → S9", c == 1 and "S9" in out, out[-300:])
        finally:
            shutil.rmtree(tmp15, ignore_errors=True)

        # ---------------------------------------------------------------- 23
        print("\n23. 存量误报与假绿收敛（ISS-013 / ISS-018 / ISS-019）")
        tmp16 = tempfile.mkdtemp(prefix="ddd-selftest16-")
        try:
            run(os.path.join(SKILL, "scripts", "doc_init.py"),
                "--target", ".", "--full", cwd=tmp16)
            docs16 = os.path.join(tmp16, "docs")
            req16 = os.path.join(docs16, "20-契约", "requirements.md")
            base16 = read(req16)

            # W7 误报：变更记录里提到需求编号，不是条款行
            write(req16, base16 + "\n| 2026-10-31 | 调整了 REQ-001 的措辞 | — |\n")
            c, out = run("doc_check.py", cwd=tmp16)
            check("变更记录提到 REQ 不报 W7（ISS-018）", "W7" not in codes(out), out[-300:])

            # W7 真阳性：编号在首列、没有规范措辞的条款行仍要报
            write(req16, base16 + "\n| **REQ-009** | 性能要好 | 看跑分 | `python tests/t.py` | 待实现 | — |\n")
            c, out = run("doc_check.py", cwd=tmp16)
            check("真正的条款行缺措辞仍报 W7", c == 0 and "W7" in codes(out), out[-300:])

            # 跳过不等于通过（ISS-019）：模板那条 REQ-001 是「待实现」
            c, out = run("verify.py", "--quiet", cwd=tmp16)
            check("有跳过行时默认仍 0，但打印跳过数",
                  c == 0 and "skipped=1" in out and "跳过 1 条" in out, out[-300:])
            c, out = run("verify.py", "--strict", cwd=tmp16)
            check("--strict 下跳过行直接失败", c == 1, out[-300:])

            # 缺配置不猜层表（ISS-013）
            os.remove(os.path.join(docs16, "_schema.json"))
            c, out = run("doc_check.py", cwd=tmp16)
            check("缺 _schema.json 直接 exit 2 并说清原因",
                  c == 2 and "既没有" in out, out[-300:])
        finally:
            shutil.rmtree(tmp16, ignore_errors=True)

        # ---------------------------------------------------------------- 24
        print("\n24. 转正一步：查重 + 自动分配 ISS（ISS-031）")
        tmp17 = tempfile.mkdtemp(prefix="ddd-selftest17-")
        try:
            run(os.path.join(SKILL, "scripts", "doc_init.py"),
                "--target", ".", "--full", cwd=tmp17)
            run("devlog.py", "new", "--title", "转正", "--scope", "自测", cwd=tmp17)
            run("devlog.py", "ask", "契约层能不能只写增量改动？",
                "--if", "主文件仍要整篇改写", cwd=tmp17)

            c, out = run("devlog.py", "pending", "--clear", "Q1", "--as", "iss", cwd=tmp17)
            check("缺 --relation 先摆候选并拒绝（exit 2）",
                  c == 2 and "候选" in out and "--relation" in out, out[-400:])

            c, out = run("devlog.py", "pending", "--clear", "Q1", "--as", "iss",
                         "--relation", "new", "--type", "文档债", cwd=tmp17)
            check("--relation new 缺三格字段 → 拒绝", c == 2 and "--impact" in out, out[-300:])

            c, out = run("devlog.py", "pending", "--clear", "Q1", "--as", "iss",
                         "--relation", "new", "--type", "文档债",
                         "--impact", "改一节契约要重读全篇", "--to", "未排期", cwd=tmp17)
            inbox17 = read(os.path.join(tmp17, "docs", "70-过程", "问题收件箱.md"))
            check("--relation new 自动分配 ISS-002 并追加收件箱行",
                  c == 0 and "ISS-002" in out and "**ISS-002**" in inbox17, out[-300:])
            pend17 = os.path.join(tmp17, ".dd", "pending")
            ptext = "".join(read(os.path.join(pend17, f)) for f in os.listdir(pend17))
            check("待分诊行标成 →ISS-002", "→ISS-002" in ptext, ptext[-300:])

            run("devlog.py", "ask", "契约增量怎么合并？", "--if", "还没定合并流程", cwd=tmp17)
            c, out = run("devlog.py", "pending", "--clear", "Q2", "--as", "iss",
                         "--relation", "merge:ISS-001", cwd=tmp17)
            inbox17 = read(os.path.join(tmp17, "docs", "70-过程", "问题收件箱.md"))
            check("--relation merge 不新增收件箱行，只标合并",
                  c == 0 and "合并入 ISS-001" in out and inbox17.count("**ISS-") == 2, out[-300:])

            c, out = run("devlog.py", "inbox", "--similar", "层枚举硬编码在多处", cwd=tmp17)
            check("inbox --similar 能找到相关条目", c == 0 and "ISS-001" in out, out[-300:])

            inbox17 = os.path.join(tmp17, "docs", "70-过程", "问题收件箱.md")
            write(inbox17, read(inbox17).replace(
                "| — | — | — | — |",
                "| ISS-090 | 闭环示例 | commit abc1234 | 2026-10-31 |"))
            c, out = run("devlog.py", "inbox", cwd=tmp17)
            check("闭环表也计入统计（ISS-033）", c == 0 and "实现关闭 1" in out, out[-200:])
        finally:
            shutil.rmtree(tmp17, ignore_errors=True)

        # ---------------------------------------------------------------- 25
        print("\n25. 需求状态与出处（E22 / E23）")
        tmp18 = tempfile.mkdtemp(prefix="ddd-selftest18-")
        try:
            run(os.path.join(SKILL, "scripts", "doc_init.py"),
                "--target", ".", "--full", cwd=tmp18)
            req18 = os.path.join(tmp18, "docs", "20-契约", "requirements.md")
            base18 = read(req18)
            row = "| 待实现 | — |"

            c, out = run("doc_check.py", cwd=tmp18)
            check("骨架里的「待实现 + 依据 —」不报 E22/E23",
                  c == 0 and "E22" not in codes(out) and "E23" not in codes(out), out[-300:])

            write(req18, base18.replace(row, "| 做完了 | — |", 1))
            c, out = run("doc_check.py", cwd=tmp18)
            check("状态词不在白名单 → E22", c == 1 and "E22" in codes(out), out[-300:])

            write(req18, base18.replace(row, "| 已实现 | — |", 1))
            c, out = run("doc_check.py", cwd=tmp18)
            check("「已实现」但依据是占位 → E23", c == 1 and "E23" in codes(out), out[-300:])

            write(req18, base18.replace(row + " — |", "| 已实现 | ADR-001 | 复述✓ 2026-11-01｜档案 012 §2 |", 1))
            c, out = run("doc_check.py", cwd=tmp18)
            check("「已实现」且依据指得出出处 → 不报",
                  c == 0 and "E22" not in codes(out) and "E23" not in codes(out), out[-300:])
        finally:
            shutil.rmtree(tmp18, ignore_errors=True)

        # ---------------------------------------------------------------- 26
        print("\n26. 功能台账：需求 → 功能 → 入口 → 证据（E24）")
        tmp19 = tempfile.mkdtemp(prefix="ddd-selftest19-")
        try:
            run(os.path.join(SKILL, "scripts", "doc_init.py"),
                "--target", ".", "--full", cwd=tmp19)
            feat19 = os.path.join(tmp19, "docs", "40-运行", "FEATURES.md")
            base19 = read(feat19)

            c, out = run("doc_check.py", cwd=tmp19)
            check("骨架的功能台账不报 E24", c == 0 and "E24" not in codes(out), out[-300:])

            write(feat19, base19.replace("REQ-001", "REQ-999", 1))
            c, out = run("doc_check.py", cwd=tmp19)
            check("引用不存在的需求 → E24", c == 1 and "E24" in codes(out), out[-300:])

            write(feat19, base19.replace("| 待评审 |", "| 做完了 |", 1))
            c, out = run("doc_check.py", cwd=tmp19)
            check("状态词不在白名单 → E24", c == 1 and "E24" in codes(out), out[-300:])

            write(feat19, insert_after(base19, FEATURE_ANCHOR,
                  "| **F-002** | 示例 | REQ-001 | 口径 | `python -c pass` | S | 已验收"
                  " | 满足✓ | — | 自测跑过 | 各任务考核见 T1.1.1｜整体一致：全｜代价：S（同估）｜结论：保留 | abc1234 |"))
            c, out = run("doc_check.py", cwd=tmp19)
            check("已验收却没有代码入口 → E24", c == 1 and "E24" in codes(out), out[-300:])

            write(feat19, insert_after(base19, FEATURE_ANCHOR,
                  "| **F-002** | 示例 | REQ-001 | 口径 | `python -c pass` | S | 已验收"
                  " | 满足✓ | docs/20-契约/requirements.md | self_test 2026-10-31"
                  " | 各任务考核见 T1.1.1｜整体一致：全｜代价：S（同估）｜结论：保留 | abc1234 |"))
            c, out = run("doc_check.py", cwd=tmp19)
            check("已验收：入口存在 + verify + 证据 → 不报",
                  c == 0 and "E24" not in codes(out), out[-300:])
        finally:
            shutil.rmtree(tmp19, ignore_errors=True)

        # ---------------------------------------------------------------- 27
        print("\n27. 评审门：三问没答完不能推进（E24）")
        tmp20 = tempfile.mkdtemp(prefix="ddd-selftest20-")
        try:
            run(os.path.join(SKILL, "scripts", "doc_init.py"),
                "--target", ".", "--full", cwd=tmp20)
            feat20 = os.path.join(tmp20, "docs", "40-运行", "FEATURES.md")
            base20 = read(feat20)

            write(feat20, insert_after(base20, FEATURE_ANCHOR,
                  "| **F-002** | 示例 | REQ-001 | 口径 | `python -c pass` | S | 已评审"
                  " | — | — | — | — | — |"))
            c, out = run("doc_check.py", cwd=tmp20)
            check("推到「已评审」却没写评审结论 → E24",
                  c == 1 and "E24" in codes(out), out[-300:])

            write(feat20, insert_after(base20, FEATURE_ANCHOR,
                  "| **F-002** | 示例 | REQ-001 | 口径 | `python -c pass` | S | 已评审"
                  " | 满足✓ 可做✓ 代价S | — | — | — | — |"))
            c, out = run("doc_check.py", cwd=tmp20)
            check("三问结论写进「评审」列 → 不报", c == 0 and "E24" not in codes(out), out[-300:])

            write(feat20, insert_after(base20, FEATURE_ANCHOR,
                  "| **F-003** | 旧功能 | —（历史） | 口径 | `python -c pass` | S | 已验收"
                  " | —（历史） | docs/20-契约/requirements.md | 2026-10-31 跑过 | —（历史） | —（历史） |"))
            c, out = run("doc_check.py", cwd=tmp20)
            check("历史行带「—（历史）」评审 → 不报", c == 0 and "E24" not in codes(out), out[-300:])

            write(feat20, insert_after(base20, FEATURE_ANCHOR,
                  "| **F-004** | 新功能 | REQ-001 | 口径 | `python -c pass` | S | 已验收"
                  " | —（历史） | docs/20-契约/requirements.md | 2026-10-31 跑过 | —（历史） | —（历史） |"))
            c, out = run("doc_check.py", cwd=tmp20)
            check("挂需求的行拿「—（历史）」背书 → E24",
                  c == 1 and "E24" in codes(out), out[-300:])
        finally:
            shutil.rmtree(tmp20, ignore_errors=True)

        # ---------------------------------------------------------------- 28
        print("\n28. 功能对照的取数（devlog features）")
        tmp21 = tempfile.mkdtemp(prefix="ddd-selftest21-")
        try:
            run(os.path.join(SKILL, "scripts", "doc_init.py"),
                "--target", ".", "--full", cwd=tmp21)
            feat21 = os.path.join(tmp21, "docs", "40-运行", "FEATURES.md")
            base21 = read(feat21)

            c, out = run("devlog.py", "features", cwd=tmp21)
            check("features 列出骨架里的 F-001", c == 0 and "F-001" in out, out[-300:])

            c, out = run("devlog.py", "features", "--state", "实施中", cwd=tmp21)
            check("按状态筛无命中时说明清楚", c == 0 and "没有状态" in out, out[-300:])

            write(feat21, base21.replace("| 待评审 |", "| 实施中 |", 1))
            c, out = run("devlog.py", "features", "--state", "实施中", cwd=tmp21)
            check("筛选命中实施中的功能并给出对照清单路径",
                  c == 0 and "F-001" in out and "功能对照.md" in out, out[-300:])
        finally:
            shutil.rmtree(tmp21, ignore_errors=True)

        # ---------------------------------------------------------------- 29
        print("\n29. 主干道写进技能（需求→功能→工作→任务→实施→冒烟→对照→测试→回写）")
        skill_text = read(os.path.join(SKILL, "SKILL.md"))
        stages = ["需求", "功能", "工作", "任务", "实施", "冒烟", "对照", "测试", "回写"]
        check("SKILL 有「主干道」一节且九个阶段齐全",
              "## 主干道" in skill_text and all(s in skill_text for s in stages),
              "缺：" + "、".join(s for s in stages if s not in skill_text))
        check("主干道每格挂得上机器判据（E24 / verify / feature-check）",
              all(k in skill_text for k in ("E24", "verify.py", "feature-check")), skill_text[:0])
        check("写明对照在测试之前的理由",
              "对照在测试之前" in skill_text and "假通过" in skill_text, "")

        # 2026-11-03 对齐 README：README 说「五道门 + 两处决策」，SKILL 必须给出同一套；
        # 边界必须拆成「机器判不了的 / 交给别的技能的」，并写明并发假设（ISS-054 / 056）。
        check("SKILL 写明主干之外的两处决策",
              "两处决策" in skill_text and "开放问题收口" in skill_text
              and "发版与回滚" in skill_text, "")
        check("SKILL 的边界拆成两段（判不了 / 交给别的技能）",
              "机器判不了的" in skill_text and "交给别的技能的" in skill_text, "")
        check("SKILL 写明并发假设（同一工作区只留一个写者）",
              "一个会话" in skill_text and "并发" in skill_text and "加锁" in skill_text, "")

        # ---------------------------------------------------------------- 30
        print("\n30. 需求 × 功能 × 证据对账（W8 / E26）")
        tmp22 = tempfile.mkdtemp(prefix="ddd-selftest22-")
        try:
            run(os.path.join(SKILL, "scripts", "doc_init.py"),
                "--target", ".", "--full", cwd=tmp22)
            req22 = os.path.join(tmp22, "docs", "20-契约", "requirements.md")
            feat22 = os.path.join(tmp22, "docs", "40-运行", "FEATURES.md")
            base_req = read(req22)
            base_feat = read(feat22)

            c, out = run("doc_check.py", cwd=tmp22)
            check("骨架里需求都有功能覆盖、证据组号合法",
                  c == 0 and "W8" not in codes(out) and "E26" not in codes(out), out[-300:])

            write(req22, base_req.replace(
                "| **REQ-001** |",
                "| **REQ-009** | WHEN 触发 THE SYSTEM SHALL 行为 | 看命令"
                " | `python -c pass` | 待实现 | — | — |\n| **REQ-001** |", 1))
            c, out = run("doc_check.py", cwd=tmp22)
            check("需求没有任何功能覆盖 → W8", c == 0 and "W8" in codes(out), out[-300:])
            write(req22, base_req)

            os.makedirs(os.path.join(tmp22, "scripts"), exist_ok=True)
            write(os.path.join(tmp22, "scripts", "self_test.py"), 'print("\\n2. x")\n')
            write(feat22, base_feat.replace("| 待评审 | — | — | — |", "| 待评审 | — | — | 第 99 组 |", 1))
            c, out = run("doc_check.py", cwd=tmp22)
            check("证据引用了不存在的自测组 → E26", c == 1 and "E26" in codes(out), out[-300:])

            write(feat22, base_feat.replace("| 待评审 | — | — | — |", "| 待评审 | — | — | 第 2 组 |", 1))
            c, out = run("doc_check.py", cwd=tmp22)
            check("证据组号真实存在 → 不报 E26", c == 0 and "E26" not in codes(out), out[-300:])
        finally:
            shutil.rmtree(tmp22, ignore_errors=True)

        # ---------------------------------------------------------------- 31
        print("\n31. 对齐门 / 考核门 / 回滚锚点（E23 扩展 / E27）")
        tmp23 = tempfile.mkdtemp(prefix="ddd-selftest23-")
        try:
            run(os.path.join(SKILL, "scripts", "doc_init.py"),
                "--target", ".", "--full", cwd=tmp23)
            req23 = os.path.join(tmp23, "docs", "20-契约", "requirements.md")
            feat23 = os.path.join(tmp23, "docs", "40-运行", "FEATURES.md")
            base_req23 = read(req23)
            base_feat23 = read(feat23)

            c, out = run("doc_check.py", cwd=tmp23)
            check("骨架里「待实现」不需要确认、不报 E23/E27",
                  c == 0 and "E23" not in codes(out) and "E27" not in codes(out), out[-300:])

            write(req23, base_req23.replace("| 待实现 | — | — |", "| 已实现 | ADR-001 | — |", 1))
            c, out = run("doc_check.py", cwd=tmp23)
            check("「已实现」但没用户确认 → E23", c == 1 and "E23" in codes(out), out[-300:])

            write(req23, base_req23.replace("| 待实现 | — | — |",
                                            "| 已实现 | ADR-001 | 复述✓ 2026-11-01｜档案 012 §2 |", 1))
            c, out = run("doc_check.py", cwd=tmp23)
            check("「已实现」+ 确认（含日期与落点）→ 不报", c == 0 and "E23" not in codes(out), out[-300:])
            write(req23, base_req23)

            ok_row = ("| **F-002** | 示例 | REQ-001 | 口径 | `python -c pass` | S | 已验收"
                      " | 满足✓ | docs/20-契约/requirements.md | self_test 2026-11-01"
                      " | 各任务考核见 T1.1.1｜整体一致：全｜代价：S（同估）｜结论：保留 | abc1234 |\n")
            write(feat23, insert_after(base_feat23, FEATURE_ANCHOR, ok_row.rstrip("\n")))
            c, out = run("doc_check.py", cwd=tmp23)
            check("已验收：考核四格 + 完成于 → 不报 E27", c == 0 and "E27" not in codes(out), out[-300:])

            write(feat23, insert_after(base_feat23, FEATURE_ANCHOR,
                  ok_row.replace("各任务考核见 T1.1.1｜整体一致：全", "看着还行").rstrip("\n")))
            c, out = run("doc_check.py", cwd=tmp23)
            check("考核缺槽位 → E27", c == 1 and "E27" in codes(out), out[-300:])

            write(feat23, insert_after(base_feat23, FEATURE_ANCHOR,
                  ok_row.replace("| abc1234 |", "| — |").rstrip("\n")))
            c, out = run("doc_check.py", cwd=tmp23)
            check("已验收没记完成于 → E27（回滚无锚点）", c == 1 and "E27" in codes(out), out[-300:])

            write(feat23, insert_after(base_feat23, FEATURE_ANCHOR,
                  "| **F-003** | 旧功能 | REQ-001 | 口径 | `python -c pass` | S | 撤回"
                  " | 满足✓ | — | — | 整体一致：偏差｜代价：M（返工）｜结论：撤回 | abc1234 |"))
            c, out = run("doc_check.py", cwd=tmp23)
            check("「撤回」是合法状态，入口可为空但要写考核",
                  c == 0 and "E24" not in codes(out) and "E27" not in codes(out), out[-300:])
        finally:
            shutil.rmtree(tmp23, ignore_errors=True)

        # ---------------------------------------------------------------- 32
        print("\n32. 决策回顾的机器判（S12，只判最新一篇）")
        tmp24 = tempfile.mkdtemp(prefix="ddd-selftest24-")
        try:
            run(os.path.join(SKILL, "scripts", "doc_init.py"),
                "--target", ".", "--full", cwd=tmp24)
            sess24 = os.path.join(tmp24, "docs", "70-过程", "会话")

            def set_decision(path, body):
                text = read(path)
                text = re.sub(r"(?ms)^## 4\.[^\n]*\n.*?(?=^## 5\.)",
                              "## 4. 决策与选项对比\n\n" + body + "\n\n", text, count=1)
                write(path, text)

            head = ("### D1 · 选 X 还是 Y\n\n"
                    "| 选项 | 语义正确性 | 实现成本 | 改动半径 | 可逆性 | 长期维护 | 用户可感知 | 可验证性 | 风险 |\n"
                    "|---|---|---|---|---|---|---|---|---|\n"
                    "| A | 5 | 5 | 1 | 5 | 4 | 3 | 5 | 1 |\n\n"
                    "**结论**：选 A。\n**是否暂定**：否。\n")
            good = head + "**拍板**：用户。\n**依据**：「就选 A」（用户原话）。\n" \
                          "**撤销条件**：出现 X 时改选 B。\n"
            bad = head + "**拍板**：用户。\n**依据**：「就选 A」（用户原话）。\n"
            agent = head + "**拍板**：agent 自选。\n"

            run("devlog.py", "new", "--title", "决策回顾甲", "--scope", "自测", cwd=tmp24)
            f_a = os.path.join(sess24, sorted(os.listdir(sess24))[0])
            write(f_a, read(f_a).replace("## 2. 用户侧记录（分类）",
                                         "## 2. 用户侧记录（分类）\n\n- 用户原话：「就选 A」\n", 1))
            c, out = run("devlog.py", "check", cwd=tmp24)
            check("模板占位决策块不报 S12", c == 0 and "S12" not in out, out[-300:])

            set_decision(f_a, bad)
            c, out = run("devlog.py", "check", cwd=tmp24)
            check("用户决策缺「撤销条件」→ S12、exit 1", c == 1 and "S12" in out, out[-300:])

            set_decision(f_a, good)
            c, out = run("devlog.py", "check", cwd=tmp24)
            check("补上「依据 + 撤销条件」→ 0 error", c == 0 and "S12" not in out, out[-300:])

            run("devlog.py", "new", "--title", "决策回顾乙", "--scope", "自测", cwd=tmp24)
            f_b = os.path.join(sess24, sorted(os.listdir(sess24))[1])
            set_decision(f_a, bad)          # 旧档改坏：不应被追溯
            c, out = run("devlog.py", "check", cwd=tmp24)
            check("只判最新一篇：旧档缺字段不追溯", c == 0 and "S12" not in out, out[-300:])

            set_decision(f_b, agent)
            c, out = run("devlog.py", "check", cwd=tmp24)
            check("拍板 agent 自选的块可豁免", c == 0 and "S12" not in out, out[-300:])

            set_decision(f_b, bad)
            c, out = run("devlog.py", "check", cwd=tmp24)
            check("最新一篇的用户决策缺撤销条件 → S12、exit 1",
                  c == 1 and "S12" in out, out[-300:])
        finally:
            shutil.rmtree(tmp24, ignore_errors=True)

        # ---------------------------------------------------------------- 33
        print("\n33. 计划表被空行/断行截断 → P13（ISS-035）")
        tmp25 = tempfile.mkdtemp(prefix="ddd-selftest25-")
        try:
            run(os.path.join(SKILL, "scripts", "doc_init.py"),
                "--target", ".", "--full", cwd=tmp25)
            plan25 = os.path.join(tmp25, "docs", "00-门面", "开发计划.md")

            c, out = run("plan.py", "check", cwd=tmp25)
            check("正常计划不报 P13（不误伤）", c == 0 and "P13" not in out, out[-300:])

            row = ("| **T1.1.2** | 第二个任务 | F-001 | W1.1 | 待开工 | - | 1 | 1 | 1 | 1 | 1 | 1 "
                   "| `python scripts/doc_check.py` | — |")
            text = read(plan25)
            broken = text.replace("| **T1.1.1** |", row + "\n\n| **T1.1.1** |", 1)
            write(plan25, broken)
            c, out = run("plan.py", "check", cwd=tmp25)
            check("§5 表内空行 → [P13]、exit 1", c == 1 and "[P13]" in out, out[-400:])
            check("P13 指名被截断的那一行（T1.1.1）", c == 1 and "T1.1.1" in out, out[-400:])

            fixed = broken.replace(row + "\n\n| **T1.1.1** |", row + "\n| **T1.1.1** |", 1)
            write(plan25, fixed)
            c, out = run("plan.py", "check", cwd=tmp25)
            check("接回同一张表 → 0 error", c == 0 and "P13" not in out, out[-300:])

            # §8 的断行：一行没写完（不是表行），下一行表格行被当成表头。
            text = read(plan25).rstrip("\n") + (
                "\n| 2026-11-02 | 变更甲 |\n续行（这一行忘了写 | 收尾）\n"
                "| 2026-11-03 | 变更乙 |\n")
            write(plan25, text)
            c, out = run("plan.py", "check", cwd=tmp25)
            check("§8 行内断行 → [P13]、exit 1", c == 1 and "[P13]" in out, out[-400:])
        finally:
            shutil.rmtree(tmp25, ignore_errors=True)

        # ---------------------------------------------------------------- 34
        print("\n34. YAML 校验器随包走（frontmatter + metadata，正反例）")
        sys.path.insert(0, os.path.join(SKILL, "scripts"))
        try:
            import yaml_rules
            have_rules = True
        except ImportError:
            have_rules = False
        check("scripts/yaml_rules.py 随包存在且可导入", have_rules)
        if have_rules:
            skill_text = read(os.path.join(SKILL, "SKILL.md"))
            block = yaml_rules.frontmatter_block(skill_text)
            fm_problems = yaml_rules.frontmatter_problems(block) if block else ["缺 front-matter"]
            check("真实 SKILL.md front-matter 通过（不含真问题）", not fm_problems,
                  "；".join(fm_problems)[:300])
            bad_fm = [
                ("plain 值含「: 」", "description_en: for development: dual-sided"),
                ("引号未闭合", 'description_en: "dual-sided'),
                ("缩进块", "  nested: x"),
                ("空值", "name:"),
                ("重复键", "name: x\nname: y"),
            ]
            for label, body in bad_fm:
                check(f"front-matter 反例被拒：{label}", bool(yaml_rules.frontmatter_problems(body)))

            meta = read(os.path.join(SKILL, ".skill-metadata.yaml"))
            meta_problems = yaml_rules.metadata_problems(meta)
            check("真实 .skill-metadata.yaml 通过（不含真问题）", not meta_problems,
                  "；".join(meta_problems)[:300])
            bad_meta = [
                ("序列项里的空值键", "examples:\n  - id:\n"),
                ("缩进跳级", "examples:\n  - id: x\n   title: y\n"),
                ("制表符缩进", "examples:\n\t- id: x\n"),
                ("plain 值含「: 」", "examples:\n  - id: x\n    title: a: b\n"),
                ("引号未闭合", 'examples:\n  - id: x\n    title: "abc\n'),
                ("同级重复键", "examples:\n  - id: x\n    title: a\n    title: b\n"),
            ]
            for label, body in bad_meta:
                check(f"metadata 反例被拒：{label}",
                      bool(yaml_rules.metadata_problems(body)))

        # ---------------------------------------------------------------- 35
        print("\n35. 问题状态机：类型/性质/状态/依据（D3–D9）")
        tmp26 = tempfile.mkdtemp(prefix="ddd-selftest26-")
        try:
            run(os.path.join(SKILL, "scripts", "doc_init.py"),
                "--target", ".", "--full", cwd=tmp26)
            inbox26 = os.path.join(tmp26, "docs", "70-过程", "问题收件箱.md")
            base26 = read(inbox26)

            c, out = run("devlog.py", "check", cwd=tmp26)
            check("模板收件箱首跑 0 error", c == 0, out[-300:])

            def row26(nature="可关闭", state="确立", ev="确立：自测", typ="债"):
                return ("| **ISS-001** | 2026-11-02 | 自测 | %s | %s | 甲 | 乙 | %s "
                        "| %s | — | %s | 2026-11-02 |"
                        % (typ, nature, state, ev,
                           "需要时" if nature == "开放" else "—"))

            def set_row(text, row):
                lines = text.splitlines()
                for i, ln in enumerate(lines):
                    if ln.startswith("| **ISS-001** |"):
                        lines[i] = row
                        break
                return "\n".join(lines) + "\n"

            write(inbox26, set_row(base26, row26(nature="待定")))
            c, out = run("devlog.py", "check", cwd=tmp26)
            check("性质不在白名单 → D3", c == 1 and "[D3]" in out, out[-300:])

            write(inbox26, set_row(base26, row26(nature="开放", state="实现关闭",
                                                ev="关闭：已修")))
            c, out = run("devlog.py", "check", cwd=tmp26)
            check("开放问题不得实现关闭 → D5", c == 1 and "[D5]" in out, out[-300:])

            write(inbox26, set_row(base26, row26(state="实施中", ev="实施中：改了解析")))
            c, out = run("devlog.py", "check", cwd=tmp26)
            check("实施中缺关联任务 → D6", c == 1 and "[D6]" in out, out[-300:])

            write(inbox26, set_row(base26, row26(ev="已修")))
            c, out = run("devlog.py", "check", cwd=tmp26)
            check("依据没有状态前缀 → D4", c == 1 and "[D4]" in out, out[-300:])

            write(inbox26, base26.replace(
                "| — | — | — | — | — |",
                "| ISS-091 | — | 用户 | 2026-11-02 | — |"))
            c, out = run("devlog.py", "check", cwd=tmp26)
            check("拒绝缺理由/重新考虑条件 → D7", c == 1 and "[D7]" in out, out[-300:])

            write(inbox26, base26.replace(
                "| — | — | — | — |",
                "| ISS-092 | 已修 | commit abc1234 | — |"))
            c, out = run("devlog.py", "check", cwd=tmp26)
            check("闭环缺闭环日 → D8", c == 1 and "[D8]" in out, out[-300:])
        finally:
            shutil.rmtree(tmp26, ignore_errors=True)

        # ---------------------------------------------------------------- 36
        print("\n36. 任务双亲与考核下沉（P14–P16；E27 改判考核汇总）")
        tmp27 = tempfile.mkdtemp(prefix="ddd-selftest27-")
        try:
            run(os.path.join(SKILL, "scripts", "doc_init.py"),
                "--target", ".", "--full", cwd=tmp27)
            plan27 = os.path.join(tmp27, "docs", "00-门面", "开发计划.md")
            feat27 = os.path.join(tmp27, "docs", "40-运行", "FEATURES.md")
            base_plan27, base_feat27 = read(plan27), read(feat27)

            c, out = run("plan.py", "check", cwd=tmp27)
            check("骨架：任务挂 F-001、未完成不需要考核 → 0 error",
                  c == 0 and "[P14]" not in out and "[P15]" not in out, out[-400:])

            tpl_task = ("| **T1.1.1** | （示例）跑通并记录 | F-001 | W1.1 | 待开工 | - "
                        "| 5 | 5 | 4 | 3 | 4 | 3 | 有落库行 + 可复现命令 | — |")
            done_task = tpl_task.replace("| 待开工 |", "| 已完成 |")
            tpl_assess = "| **T1.1.1** | （这场改了什么、怎么改的） | 全 | S（同估） | 保留 | `abc1234` |"
            ok_assess = "| **T1.1.1** | 跑通并记录并贴了命令输出 | 全 | S（同估） | 保留 | abc1234 |"
            assert tpl_task in base_plan27 and tpl_assess in base_feat27

            write(plan27, base_plan27.replace(tpl_task, done_task))
            c, out = run("plan.py", "check", cwd=tmp27)
            check("已完成任务只留着模板占位的考核行 → P15",
                  c == 1 and "[P15]" in out and "T1.1.1" in out, out[-400:])

            write(feat27, base_feat27.replace(tpl_assess, ok_assess))
            c, out = run("plan.py", "check", cwd=tmp27)
            check("验收 + 四格 + 完成于齐 → 0 error", c == 0 and "[P15]" not in out, out[-400:])

            write(feat27, base_feat27.replace(tpl_assess, ""))
            c, out = run("plan.py", "check", cwd=tmp27)
            check("删掉考核行 → P15 指名缺行（不是静默通过）",
                  c == 1 and "[P15]" in out and "没有它" in out, out[-400:])
            write(feat27, base_feat27.replace(tpl_assess, ok_assess))

            write(plan27, base_plan27.replace(tpl_task, done_task.replace("| F-001 |", "| F-999 |")))
            c, out = run("plan.py", "check", cwd=tmp27)
            check("任务挂不存在的功能 → P14", c == 1 and "[P14]" in out, out[-400:])

            write(plan27, base_plan27.replace(tpl_task, tpl_task.replace("| F-001 |", "| —（历史） |")))
            c, out = run("plan.py", "check", cwd=tmp27)
            check("未完成的任务写「—（历史）」→ P14", c == 1 and "[P14]" in out, out[-400:])

            write(plan27, base_plan27)
            os.rename(feat27, feat27 + ".bak")
            c, out = run("plan.py", "check", cwd=tmp27)
            check("功能台账缺失 → P14（不能当成没有功能跳过）",
                  c == 1 and "[P14]" in out and "找不到功能台账" in out, out[-400:])
            os.rename(feat27 + ".bak", feat27)

            no_task_feat = ("| **F-009** | 第二个功能 | REQ-001 | 口径 | `python -c pass` | S | 已验收"
                            " | 满足✓ 可做✓ 代价S | docs/20-契约/requirements.md | self_test 2026-11-02"
                            " | 各任务考核见 T1.1.1｜整体一致：全｜代价：S（同估）｜结论：保留 | abc1234 |\n")
            write(feat27, insert_after(base_feat27.replace(tpl_assess, ok_assess),
                                       FEATURE_ANCHOR, no_task_feat.rstrip("\n")))
            c, out = run("plan.py", "check", cwd=tmp27)
            check("已验收功能没有任何任务挂它 → P16", c == 1 and "[P16]" in out, out[-400:])

            write(plan27, base_plan27.replace(tpl_task, done_task.replace("| F-001 |", "| F-009 |")))
            c, out = run("plan.py", "check", cwd=tmp27)
            check("汇总点名的任务真挂在这个功能下 → 0 error",
                  c == 0 and "[P16]" not in out, out[-400:])

            ghost = no_task_feat.replace("T1.1.1", "T9.9.9")
            write(feat27, insert_after(base_feat27.replace(tpl_assess, ok_assess),
                                       FEATURE_ANCHOR, ghost.rstrip("\n")))
            c, out = run("plan.py", "check", cwd=tmp27)
            check("汇总点名不存在的任务 → P16",
                  c == 1 and "[P16]" in out and "T9.9.9" in out, out[-400:])

            orphan = "| **T9.9.9** | 幽灵任务 | 全 | S（同估） | 保留 | abc1234 |"
            write(feat27, insert_after(base_feat27.replace(tpl_assess, ok_assess),
                                       TASK_ANCHOR, orphan))
            c, out = run("plan.py", "check", cwd=tmp27)
            check("任务考核表里的任务不在计划 §5 → P15",
                  c == 1 and "[P15]" in out and "T9.9.9" in out, out[-400:])

            # E27 改判「考核汇总」：四格留在任务级，功能只写一行
            write(feat27, insert_after(base_feat27.replace(tpl_assess, ok_assess), FEATURE_ANCHOR,
                                       no_task_feat.replace("各任务考核见 T1.1.1", "见任务").rstrip("\n")))
            c, out = run("doc_check.py", cwd=tmp27)
            check("功能的考核汇总没指出考核在哪 → E27", c == 1 and "E27" in codes(out), out[-300:])
        finally:
            shutil.rmtree(tmp27, ignore_errors=True)

        # ---------------------------------------------------------------- 37
        print("\n37. 方向卡：现状 / 成功状态 / 走通验收（P18）")
        tmp28 = tempfile.mkdtemp(prefix="ddd-selftest28-")
        try:
            run(os.path.join(SKILL, "scripts", "doc_init.py"),
                "--target", ".", "--full", cwd=tmp28)
            card28 = os.path.join(tmp28, "docs", "00-门面", "方向卡.md")
            base28 = read(card28)

            c, out = run("plan.py", "check", cwd=tmp28)
            check("骨架：计划 D1 与方向卡 D1 对上 → 0 error",
                  c == 0 and "[P18]" not in out, out[-400:])

            write(card28, base28.replace("（示例）只有落地页，注册后没有下一步", "—"))
            c, out = run("plan.py", "check", cwd=tmp28)
            check("现状为空 → P18 指名「现状」",
                  c == 1 and "[P18]" in out and "现状" in out, out[-400:])

            write(card28, base28.replace("（示例）「注册 → 建第一条记录 → 看到结果」全程走通", "—"))
            c, out = run("plan.py", "check", cwd=tmp28)
            check("成功状态为空 → P18", c == 1 and "[P18]" in out and "成功状态" in out, out[-400:])

            write(card28, base28.replace("在干净环境里按三步走一遍，每步记观察（@2026-12-31 复核）", "—"))
            c, out = run("plan.py", "check", cwd=tmp28)
            check("走通验收为空 → P18", c == 1 and "[P18]" in out and "走通验收" in out, out[-400:])

            # REQ-018：走通验收要带复核日期（@YYYY-MM-DD），否则到期提醒无从触发
            write(card28, base28.replace("（@2026-12-31 复核）", ""))
            c, out = run("plan.py", "check", cwd=tmp28)
            check("走通验收缺 @复核日 → P18（ISS-061）",
                  c == 1 and "[P18]" in out and "@" in out, out[-400:])

            # 接缝是步与步之间的分水岭；格空着，方向就退化成功能清单
            write(card28, base28.replace("注册成功后的空状态；记录保存失败的重试", "—"))
            c, out = run("plan.py", "check", cwd=tmp28)
            check("接缝为空 → P18（ISS-061）", c == 1 and "[P18]" in out and "接缝" in out, out[-400:])

            # 引用存在性：路径里的 F-nnn / W<n.m> / K<n> 必须真实存在
            write(card28, base28.replace("（F-001）", "（F-999）"))
            c, out = run("plan.py", "check", cwd=tmp28)
            check("路径引用不存在的 F-999 → P18（ISS-061）",
                  c == 1 and "[P18]" in out and "F-999" in out, out[-400:])

            orphan = ("| **D9** | 现状甲 | 现在不做就晚 | 用户 · 起点 | 成功状态甲 "
                      "| ① 一 → ② 二 | 接缝甲 | 不覆盖甲 | 走通一遍 | — |")
            # 追加在文件尾会落进「覆盖」表；孤儿行必须插进方向主表（主表后是「回看」节）
            write(card28, base28.replace(
                "\n\n## 回看", "\n" + orphan + "\n## 回看", 1))
            c, out = run("plan.py", "check", cwd=tmp28)
            check("卡里有 D9 但计划没有 → P18 孤儿方向",
                  c == 1 and "[P18]" in out and "D9" in out, out[-400:])

            write(card28, base28)
            os.rename(card28, card28 + ".bak")
            c, out = run("plan.py", "check", cwd=tmp28)
            check("方向卡缺失 → 一条 P18（不逐行刷屏）",
                  c == 1 and out.count("[P18]") == 1 and "找不到方向卡" in out, out[-400:])
            os.rename(card28 + ".bak", card28)

            write(card28, base28.replace("| **D1** |", "| D2 |").replace("| D2 |", "| D2x |"))
            # 计划有 D1、卡里只剩 D2x（非法编号，不会被识别）→ 卡里没有 D1
            c, out = run("plan.py", "check", cwd=tmp28)
            check("计划有 D1 而卡里没有 → P18 指名缺哪个方向",
                  c == 1 and "[P18]" in out and "D1" in out, out[-400:])
        finally:
            shutil.rmtree(tmp28, ignore_errors=True)

        # ---------------------------------------------------------------- 38
        print("\n38. 设计卡：接口 / 可替换点 / 失败边界（P19）")
        tmp29 = tempfile.mkdtemp(prefix="ddd-selftest29-")
        try:
            run(os.path.join(SKILL, "scripts", "doc_init.py"),
                "--target", ".", "--full", cwd=tmp29)
            card29 = os.path.join(tmp29, "docs", "00-门面", "设计卡.md")
            base29 = read(card29)

            c, out = run("plan.py", "check", cwd=tmp29)
            check("骨架：待开工的 W1.1 与示例设计卡对上 → 0 error",
                  c == 0 and "[P19]" not in out, out[-400:])

            write(card29, base29.replace(
                "- **接口**：一次真实调用的入口、输入与输出落点（哪张表、哪个字段）。",
                "- **接口**：—"))
            c, out = run("plan.py", "check", cwd=tmp29)
            check("接口为空 → P19 指名「接口」",
                  c == 1 and "[P19]" in out and "接口" in out, out[-400:])

            # 「无」是 PLACEHOLDER：没有可替换点必须写「无」+ 为什么，只写「无」等于没说
            write(card29, base29.replace(
                "- **可替换点**：数据源（现在直连数据库，以后换外部 API 只动取数函数一处）；"
                "没有可替换点的写「无」并说为什么。",
                "- **可替换点**：无"))
            c, out = run("plan.py", "check", cwd=tmp29)
            check("可替换点只写「无」→ P19（要写「无」+ 为什么）",
                  c == 1 and "[P19]" in out and "可替换点" in out, out[-400:])

            write(card29, base29.replace(
                "- **失败边界**：取数超时直接报错不重试；落库失败整体回滚，不留半条记录。",
                "- **失败边界**：（待补）"))
            c, out = run("plan.py", "check", cwd=tmp29)
            check("失败边界留模板占位 → P19",
                  c == 1 and "[P19]" in out and "失败边界" in out, out[-400:])

            orphan = ("\n## K9 · W9.9 · 幽灵卡\n\n- **接口**：x\n"
                      "- **可替换点**：无（这张卡是造的）\n- **失败边界**：x\n")
            write(card29, base29.rstrip("\n") + "\n" + orphan)
            c, out = run("plan.py", "check", cwd=tmp29)
            check("卡里的工作不在计划 §4 → P19 孤儿卡",
                  c == 1 and "[P19]" in out and "W9.9" in out, out[-400:])

            dup = ("\n## K2 · W1.1 · 第二张卡\n\n- **接口**：y\n"
                   "- **可替换点**：无（第二张）\n- **失败边界**：y\n")
            write(card29, base29.rstrip("\n") + "\n" + dup)
            c, out = run("plan.py", "check", cwd=tmp29)
            check("一个工作两张卡 → P19",
                  c == 1 and "[P19]" in out and "2 张设计卡" in out, out[-400:])

            write(card29, base29)
            os.rename(card29, card29 + ".bak")
            c, out = run("plan.py", "check", cwd=tmp29)
            check("设计卡缺失 → 一条 P19（不逐行刷屏）",
                  c == 1 and out.count("[P19]") == 1 and "找不到设计卡" in out, out[-400:])
            os.rename(card29 + ".bak", card29)

            # 已做完的工作不追溯：把 W1.1 标成已完成，卡删掉也不该报 P19
            plan29 = os.path.join(tmp29, "docs", "00-门面", "开发计划.md")
            write(plan29, read(plan29).replace("| D1 | 待开工 |", "| D1 | 已完成 |"))
            os.rename(card29, card29 + ".bak")
            c, out = run("plan.py", "check", cwd=tmp29)
            check("已做完的工作不追溯（无卡也不报 P19）",
                  c == 0 and "[P19]" not in out, out[-400:])
            os.rename(card29 + ".bak", card29)
        finally:
            shutil.rmtree(tmp29, ignore_errors=True)

        # ---------------------------------------------------------------- 39
        print("\n39. 反向判据会自己醒来（@日期）+ 完成于不许「待提交」（ISS-046 / ISS-050）")
        tmp30 = tempfile.mkdtemp(prefix="ddd-selftest30-")
        try:
            run(os.path.join(SKILL, "scripts", "doc_init.py"),
                "--target", ".", "--full", cwd=tmp30)
            inbox30 = os.path.join(tmp30, "docs", "70-过程", "问题收件箱.md")
            base30 = read(inbox30)
            past = base30.replace("| 抽单一常量（`docs/_schema.json`） | — |",
                                  "| 抽单一常量（`docs/_schema.json`） | @2020-01-01 |", 1)
            check("用例就位：回到条件里写了一个过去的 @日期", past != base30)
            write(inbox30, past)
            c, out = run("devlog.py", "brief", cwd=tmp30)
            check("brief 报出已到期的复核项（ISS-050）",
                  c == 0 and "已到期 1" in out and "ISS-001" in out, out[-400:])

            # 模板方向卡的示例自带 @2026-12-31；本组只测「收件箱的日期」是否冒充已到期，
            # 把方向卡那条推到 2099-12-31（晚于收件箱的 2099-01-01），让最近到期仍是收件箱那条。
            card30 = os.path.join(tmp30, "docs", "00-门面", "方向卡.md")
            write(card30, read(card30).replace("（@2026-12-31 复核）", "（@2099-12-31 复核）"))
            write(inbox30, past.replace("@2020-01-01", "@2099-01-01"))
            c, out = run("devlog.py", "brief", cwd=tmp30)
            check("没到期的只报「最近到期」，不冒充已到期",
                  c == 0 and "已到期" not in out and "2099-01-01" in out, out[-400:])

            # 完成于 = 「待提交」按没记算：任务级 P15 要报（模板里那行示例的锚点是 `abc1234`）
            plan30 = os.path.join(tmp30, "docs", "00-门面", "开发计划.md")
            feat30 = os.path.join(tmp30, "docs", "40-运行", "FEATURES.md")
            write(plan30, read(plan30).replace("| W1.1 | 待开工 |", "| W1.1 | 已完成 |", 1))
            checked_row = read(feat30).replace("| `abc1234` |", "| 待提交 |", 1).replace(
                "（这场改了什么、怎么改的）", "补了断言与码", 1)
            check("用例就位：考核行的完成于改成「待提交」", checked_row != read(feat30))
            write(feat30, checked_row)
            c, out = run("plan.py", "check", cwd=tmp30)
            check("任务考核的「完成于：待提交」→ P15（ISS-046）",
                  c == 1 and "[P15]" in out and "完成于" in out, out[-400:])

            write(feat30, checked_row.replace("| 待提交 |", "| abc1234 |", 1))
            c, out = run("plan.py", "check", cwd=tmp30)
            check("写成 commit 短号后 P15 消失",
                  c == 0 and "[P15]" not in out, out[-400:])
        finally:
            shutil.rmtree(tmp30, ignore_errors=True)

        # ---------------------------------------------------------------- 40
        print("\n40. 装机逐字节核对 + 历史残留清理（ISS-039）")
        # install.py 是仓库级工具，不随包分发——在解包后的自测里这一组只能跳过。
        installer31 = os.path.join(SKILL, "install.py")
        tmp31 = tempfile.mkdtemp(prefix="ddd-selftest31-")
        try:
            if not os.path.exists(installer31):
                print("  SKIP  包内不带 install.py（装机脚本不随包分发），这组在源码目录里跑")
            else:
                skills = os.path.join(tmp31, "skills")
                os.makedirs(skills, exist_ok=True)
                man31 = os.path.join(tmp31, "targets.json")
                write(man31, '{"skill": "doc-driven-development", "targets": '
                             '[{"id": "fake", "name": "假宿主", "paths": ["%s"]}]}'
                             % skills.replace("\\", "/"))
                c, out = run(installer31, "--manifest", man31, "--from", "worktree", cwd=tmp31)
                check("装机后逐字节核对 缺 0 / 不等 0",
                      c == 0 and "核对 缺 0 / 不等 0" in out, out[-400:])

                dest31 = os.path.join(skills, "doc-driven-development")
                write(os.path.join(dest31, "build.py"), "手工拷进来的旧文件")
                c, out = run(installer31, "--manifest", man31, "--from", "worktree", cwd=tmp31)
                check("历史残留被报出并清掉（ISS-039）",
                      c == 0 and "清理多余 1" in out
                      and not os.path.exists(os.path.join(dest31, "build.py")), out[-400:])
        finally:
            shutil.rmtree(tmp31, ignore_errors=True)

        # ---------------------------------------------------------------- 41
        print("\n41. 开发体验摩擦留痕 + 转正行 impact 落对列（REQ-013 / ISS-060）")
        tpl32 = os.path.join(SKILL, "assets", "templates", "session-record.md")
        check("档案模板含 §3.6 本轮摩擦（REQ-013）",
              os.path.exists(tpl32) and "### 3.6 本轮摩擦" in read(tpl32))
        tmp32 = tempfile.mkdtemp(prefix="ddd-selftest32-")
        try:
            run(os.path.join(SKILL, "scripts", "doc_init.py"),
                "--target", ".", "--full", cwd=tmp32)
            run("devlog.py", "new", "--title", "摩擦", "--scope", "自测", cwd=tmp32)
            run("devlog.py", "ask", "转正会不会丢影响列？",
                "--if", "改完仍丢", cwd=tmp32)
            c, out = run("devlog.py", "pending", "--clear", "Q1", "--as", "iss",
                         "--relation", "new", "--type", "缺陷",
                         "--impact", "转正丢影响列", "--to", "append_inbox_row", cwd=tmp32)
            inbox32 = read(os.path.join(tmp32, "docs", "70-过程", "问题收件箱.md"))
            rows32 = [ln for ln in inbox32.splitlines()
                      if ln.startswith("| **ISS-") and "转正丢影响列" in ln]
            check("转正 exit 0 且新行落在收件箱", c == 0 and len(rows32) == 1, out[-400:])
            if rows32:
                cells32 = [x.strip() for x in rows32[0].strip().strip("|").split("|")]
                check("impact 落进「影响」列，不是「—」（ISS-060）",
                      "转正丢影响列" in cells32, str(cells32))
        finally:
            shutil.rmtree(tmp32, ignore_errors=True)

        # ---------------------------------------------------------------- 42
        print("\n42. 已闭环表保留发现日（REQ-014）")
        tpl33 = os.path.join(SKILL, "assets", "templates", "inbox.md")
        check("归档模板的已闭环表含「发现日」列",
              os.path.exists(tpl33) and "| ID | 发现日 | 结论 | 闭环日 |" in read(tpl33))
        tmp34 = tempfile.mkdtemp(prefix="ddd-selftest34-")
        try:
            run(os.path.join(SKILL, "scripts", "doc_init.py"),
                "--target", ".", "--full", cwd=tmp34)
            inbox34 = os.path.join(tmp34, "docs", "70-过程", "问题收件箱.md")
            check("doc_init 铺出的实例也是同一表头",
                  os.path.exists(inbox34) and "| ID | 发现日 | 结论 | 闭环日 |" in read(inbox34))
        finally:
            shutil.rmtree(tmp34, ignore_errors=True)

        # ---------------------------------------------------------------- 43
        print("\n43. 计划树视图：D → W → T，另出单文件页面")
        # 读者是人，但页面必须是**生成物**：手写的视图会成为第二个事实源，
        # 那正是 ISS-064 那类「文档与仓库对不上」的温床。
        tmp35 = tempfile.mkdtemp(prefix="ddd-selftest35-")
        try:
            run(os.path.join(SKILL, "scripts", "doc_init.py"),
                "--target", ".", "--full", cwd=tmp35)
            c, out = run("plan.py", "tree", cwd=tmp35)
            check("tree 列出方向 / 工作 / 任务三层",
                  c == 0 and "D1" in out and "W1.1" in out and "T1.1.1" in out, out[-200:])
            c, out = run("plan.py", "tree", "--html", cwd=tmp35)
            check("tree --html 是单文件页面且写明不要手改",
                  c == 0 and out.lstrip().lower().startswith("<!doctype html>")
                  and "不要手改" in out, out[:120])
            check("tree --html 不引任何外部资源（离线可看）",
                  "http://" not in out and "https://" not in out)
            c, out = run("plan.py", "tree", "--json", cwd=tmp35)
            ok_json = False
            try:
                ok_json = json.loads(out)["tasks"] == 1
            except (ValueError, KeyError, TypeError):
                ok_json = False
            check("tree --json 给机读结构（tasks 计数）", c == 0 and ok_json, out[:150])
        finally:
            shutil.rmtree(tmp35, ignore_errors=True)

        # ---------------------------------------------------------------- 44
        print("\n44. 唯一出口：plan.py next；--help 只读、未知命令不落盘")
        tmp36 = tempfile.mkdtemp(prefix="ddd-selftest36-")
        try:
            run(os.path.join(SKILL, "scripts", "doc_init.py"),
                "--target", ".", "--full", cwd=tmp36)
            c, out = run("plan.py", "next", cwd=tmp36)
            check("next 给出 Top-1 与 方向→工作→任务 路径",
                  c == 0 and "下一步：T1.1.1" in out and "D1" in out and "W1.1" in out,
                  out[-200:])
            c, out = run("plan.py", "next", "--json", cwd=tmp36)
            ok_json = False
            try:
                ok_json = json.loads(out)["views"][0]["task"] == "T1.1.1"
            except (ValueError, KeyError, TypeError, IndexError):
                ok_json = False
            check("next --json 给机读结构（task / direction / work）",
                  c == 0 and ok_json, out[:150])
            # --help 必须只读：先把生成区弄脏，跑完 --help 还脏 → 说明没写；
            # 再跑 index 把它修好，作为对照组，防止这条断言恒真（ISS-050 同类）。
            plan36 = os.path.join(tmp36, "docs", "00-门面", "开发计划.md")
            dirty = read(plan36).replace("<!-- BEGIN:plan-rank -->",
                                         "<!-- BEGIN:plan-rank -->\nSTALE", 1)
            write(plan36, dirty)
            c, out = run("plan.py", "--help", cwd=tmp36)
            check("--help 只打用法、不写生成区",
                  c == 0 and "STALE" in read(plan36) and "plan-rank written" not in out,
                  out[-150:])
            c, out = run("plan.py", "index", cwd=tmp36)
            check("对照：index 才会重写生成区（STALE 被修掉）",
                  c == 0 and "STALE" not in read(plan36), out[-150:])
            c, out = run("plan.py", "bogus", cwd=tmp36)
            check("未知命令报错、不落盘", c == 2 and "未知命令" in out, out[-150:])
        finally:
            shutil.rmtree(tmp36, ignore_errors=True)

        # ---------------------------------------------------------------- 45
        print("\n45. 开场简报提醒「没写 @日期」的活跃问题")
        tmp37 = tempfile.mkdtemp(prefix="ddd-selftest37-")
        try:
            run(os.path.join(SKILL, "scripts", "doc_init.py"),
                "--target", ".", "--full", cwd=tmp37)
            c, out = run("devlog.py", "brief", cwd=tmp37)
            check("brief 列出没有 @日期 的活跃问题",
                  c == 0 and "回访：" in out and "ISS-001" in out, out[-200:])
            c, out = run("devlog.py", "brief", "--json", cwd=tmp37)
            ok_json = False
            try:
                ok_json = "ISS-001" in json.loads(out)["due"]["undated"]
            except (ValueError, KeyError, TypeError):
                ok_json = False
            check("brief --json 的 due.undated 给机读", c == 0 and ok_json, out[:150])
        finally:
            shutil.rmtree(tmp37, ignore_errors=True)

        # ---------------------------------------------------------------- 46
        print("\n46. 想法候选：原话逐字、落点存在、不重复（E29）")
        tmp38 = tempfile.mkdtemp(prefix="ddd-selftest38-")
        try:
            run(os.path.join(SKILL, "scripts", "doc_init.py"),
                "--target", ".", "--full", cwd=tmp38)
            run("devlog.py", "new", "--title", "想法候选", "--scope", "试", cwd=tmp38)

            def archives():
                d = os.path.join(tmp38, "docs", "70-过程", "会话")
                return sorted(os.path.join(d, f) for f in os.listdir(d) if f.endswith(".md"))

            block = (
                "\n\n### 3.7 想法候选（整理产物）\n\n"
                "| # | 类别 | 原话（逐字） | 出处 | 建议落点 | 裁决 |\n"
                "|---|---|---|---|---|---|\n"
                "| 1 | 需求 | 想法候选 | 本档 §2 | REQ-001 | 待裁 |\n"
            )
            a1 = archives()[-1]
            write(a1, read(a1) + block)
            c, out = run("doc_check.py", cwd=tmp38)
            check("合法想法建议：0 error", c == 0 and "[E29]" not in out, out[-200:])

            write(a1, read(a1).replace("| 1 | 需求 | 想法候选 |",
                                       "| 1 | 需求 | 想法候选改字 |"))
            c, out = run("doc_check.py", cwd=tmp38)
            check("原话被改一个字 → [E29]", c == 1 and "[E29]" in out, out[-200:])

            write(a1, read(a1).replace("| 1 | 需求 | 想法候选改字 |",
                                       "| 1 | 需求 | 想法候选 |")
                .replace("| REQ-001 |", "| REQ-999 |"))
            c, out = run("doc_check.py", cwd=tmp38)
            check("建议落点不存在 → [E29]", c == 1 and "[E29]" in out, out[-200:])

            write(a1, read(a1).replace("| REQ-999 |", "| REQ-001 |"))
            run("devlog.py", "new", "--title", "想法候选二", "--scope", "试", cwd=tmp38)
            a2 = archives()[-1]
            write(a2, read(a2) + block)
            c, out = run("doc_check.py", cwd=tmp38)
            check("同一原话第二篇重复建议 → [E29]", c == 1 and "[E29]" in out, out[-200:])
        finally:
            shutil.rmtree(tmp38, ignore_errors=True)

        # ---------------------------------------------------------------- 47
        print("\n47. 开场/收尾提醒「想法候选还没填」（S13）")
        tmp39 = tempfile.mkdtemp(prefix="ddd-selftest39-")
        try:
            run(os.path.join(SKILL, "scripts", "doc_init.py"),
                "--target", ".", "--full", cwd=tmp39)
            run("devlog.py", "new", "--title", "想法候选模板", "--scope", "试", cwd=tmp39)
            c, out = run("devlog.py", "brief", cwd=tmp39)
            check("brief 开场提醒 §3.7 还没填", c == 0 and "整理：" in out, out[-200:])
            c, out = run("devlog.py", "check", cwd=tmp39)
            check("check 给 WARN [S13]（不阻断收尾）", c == 0 and "[S13]" in out, out[-200:])

            d = os.path.join(tmp39, "docs", "70-过程", "会话")
            a = sorted(os.path.join(d, f) for f in os.listdir(d) if f.endswith(".md"))[-1]
            ph = "| | 目标 / 愿景 / 功能 / 需求 | | 本档 §2 | vision / D-n / REQ-nnn / F-nnn / 新建 | 待裁 / 已落位：<编号> / 丢弃 |"
            filled = "| 1 | 需求 | 想法候选 | 本档 §2 | REQ-001 | 待裁 |"
            write(a, read(a).replace(ph, filled))
            c, out = run("devlog.py", "brief", cwd=tmp39)
            check("填过一行后 brief 不再提醒", c == 0 and "整理：" not in out, out[-200:])
            c, out = run("devlog.py", "check", cwd=tmp39)
            check("填过一行后 check 不再报 S13", c == 0 and "[S13]" not in out, out[-200:])

            # ISS-118：模板允许「没有就写『无』」的散文式填法，S13 / brief 必须认它；
            # 但「散文里只是含无」不算——否则提醒会从「总响」变成「总不响」。
            def section37(body):
                return re.sub(r"(?ms)(^### 3\.7[^\n]*\n).*?(?=^### 3\.8)",
                              lambda m: m.group(1) + "\n" + body + "\n\n", read(a))

            write(a, section37("无"))
            c, out = run("devlog.py", "brief", cwd=tmp39)
            check("§3.7 写散文「无」→ brief 不再提醒", c == 0 and "整理：" not in out, out[-200:])
            c, out = run("devlog.py", "check", cwd=tmp39)
            check("§3.7 写散文「无」→ check 不报 S13", c == 0 and "[S13]" not in out, out[-200:])

            write(a, section37("无。"))
            c, out = run("devlog.py", "brief", cwd=tmp39)
            check("散文「无。」（带句号）仍算已填", c == 0 and "整理：" not in out, out[-200:])

            write(a, section37("本场没有要整理的想法"))
            c, out = run("devlog.py", "brief", cwd=tmp39)
            check("散文只是含「无」不算已填（反例）", c == 0 and "整理：" in out, out[-200:])

            skill_md = read(os.path.join(SKILL, "SKILL.md"))
            check("SKILL 硬规则含「开场先跑 brief + 收尾回填 §3.7」",
                  "开场先跑 `brief`" in skill_md and "§3.7" in skill_md, "")
        finally:
            shutil.rmtree(tmp39, ignore_errors=True)

        # ---------------------------------------------------------------- 48
        print("\n48. 状态转写子命令：输入校验、零写入与幂等（REQ-017）")
        tmp40 = tempfile.mkdtemp(prefix="ddd-selftest40-")
        try:
            run(os.path.join(SKILL, "scripts", "doc_init.py"),
                "--target", ".", "--full", cwd=tmp40)
            plan40 = os.path.join(tmp40, "docs", "00-门面", "开发计划.md")
            feat40 = os.path.join(tmp40, "docs", "40-运行", "FEATURES.md")

            def digest():
                return (hashlib.sha256(read(plan40).encode("utf-8")).hexdigest(),
                        hashlib.sha256(read(feat40).encode("utf-8")).hexdigest())

            def tree():
                got = []
                for root, _, names in os.walk(tmp40):
                    for n in names:
                        got.append(os.path.relpath(os.path.join(root, n), tmp40))
                return sorted(got)

            base, files = digest(), tree()
            review = "做法=自测｜一致=全｜代价=S｜结论=保留"
            c, out = run("plan.py", "set-status", "T1.1.1", "--to", "已完成",
                         "--commit", "abc1234", "--review", review, "--dry-run", cwd=tmp40)
            check("--dry-run 只打印清单、不落盘",
                  c == 0 and "dry-run" in out and digest() == base, out[-160:])

            c, out = run("plan.py", "set-status", "T9.9.9", "--to", "已完成",
                         "--commit", "abc1234", "--review", review, cwd=tmp40)
            check("任务号不在计划 §5 → 退出 1 且零写入",
                  c == 1 and digest() == base, out[-160:])

            c, out = run("plan.py", "set-status", "T1.1.1", "--to", "完成", cwd=tmp40)
            check("目标状态不在白名单 → 退出 1", c == 1 and "白名单" in out, out[-160:])

            c, out = run("plan.py", "set-status", "T1.1.1", "--to", "已完成",
                         "--review", review, cwd=tmp40)
            check("「已完成」缺完成于锚点 → 退出 1", c == 1 and "完成于" in out, out[-160:])

            c, out = run("plan.py", "set-status", "T1.1.1", "--to", "已完成",
                         "--commit", "待提交", "--review", review, cwd=tmp40)
            check("锚点写「待提交」→ 退出 1", c == 1 and digest() == base, out[-160:])

            c, out = run("plan.py", "set-status", "T1.1.1", "--to", "已完成",
                         "--commit", "abc1234", cwd=tmp40)
            check("「已完成」缺考核四格 → 退出 1", c == 1 and "四格" in out, out[-160:])

            c, out = run("plan.py", "set-status", "T1.1.1", "--to", "已完成",
                         "--commit", "abc1234", "--review", review, cwd=tmp40)
            after = digest()
            check("转写成功：状态与考核行一起写、清单可读",
                  c == 0 and "T1.1.1" in out and after != base
                  and "自测" in read(feat40), out[-200:])
            c, out = run("plan.py", "check", cwd=tmp40)
            check("转写后 plan.py check 0 error", c == 0 and "errors=0" in out, out[-200:])
            c, out = run("plan.py", "set-status", "T1.1.1", "--to", "已完成",
                         "--commit", "abc1234", "--review", review, cwd=tmp40)
            check("原样重跑 → 无改动、不落盘",
                  c == 0 and "无改动" in out and digest() == after, out[-160:])
            check("没有新增任何文件（不新增载体）",
                  tree() == files, str(sorted(set(tree()) - set(files))[:3]))
        finally:
            shutil.rmtree(tmp40, ignore_errors=True)

        # ---------------------------------------------------------------- 49
        print("\n49. 语义门预审：五列 / 引文逐字 / 表头无状态列（E30）")
        tmp41 = tempfile.mkdtemp(prefix="ddd-selftest41-")
        try:
            run(os.path.join(SKILL, "scripts", "doc_init.py"),
                "--target", ".", "--full", cwd=tmp41)
            run("devlog.py", "new", "--title", "预审记录", "--scope", "试", cwd=tmp41)
            d49 = os.path.join(tmp41, "docs", "70-过程", "会话")
            a49 = sorted(os.path.join(d49, f) for f in os.listdir(d49)
                         if f.endswith(".md"))[-1]
            block49 = (
                "\n\n### 3.8 预审记录（LLM 辅助，只出疑点）\n\n"
                "| 指向 | 逐字引文 | 疑点 | 建议动作 | 裁决 |\n"
                "|---|---|---|---|---|\n"
                "| 本档 §1 | 本次范围 | 需求与实现对不上 | 补证据 | 待裁决 |\n"
            )
            write(a49, read(a49) + block49)
            c, out = run("doc_check.py", cwd=tmp41)
            check("合法预审记录：0 error", c == 0 and "[E30]" not in out, out[-200:])

            # ISS-083：原文带行内代码，引文按去掉标记的字面引用时不能误报
            write(a49, read(a49).replace(
                "| 本档 §1 | 本次范围 |",
                "| 本档 §1 | 收尾时跑 python scripts/devlog.py check |"))
            c, out = run("doc_check.py", cwd=tmp41)
            check("引文跨行内代码（原文带反引号）→ 不误报",
                  c == 0 and "[E30]" not in out, out[-200:])
            write(a49, read(a49).replace(
                "| 本档 §1 | 收尾时跑 python scripts/devlog.py check |",
                "| 本档 §1 | 本次范围 |"))

            write(a49, read(a49).replace("| 本档 §1 | 本次范围 |", "| 本档 §1 | 本次范围改 |"))
            c, out = run("doc_check.py", cwd=tmp41)
            check("引文被改一个字 → [E30]", c == 1 and "[E30]" in out, out[-200:])

            write(a49, read(a49).replace("| 本档 §1 | 本次范围改 |", "| 本档 §1 | 本次范围 |")
                  .replace("| 裁决 |", "| 状态 |"))
            c, out = run("doc_check.py", cwd=tmp41)
            check("表头出现「状态」列 → [E30]", c == 1 and "[E30]" in out, out[-200:])

            write(a49, read(a49).replace("| 状态 |", "| 裁决 |")
                  .replace("| 本档 §1 | 本次范围 | 需求与实现对不上 | 补证据 | 待裁决 |",
                           "| 本档 §1 | 本次范围 | 需求与实现对不上 | 补证据 | 待裁决 |\n"
                           "| 对齐门 | — | 复述不能代 | 补证据 | 待裁决 |"))
            c, out = run("doc_check.py", cwd=tmp41)
            check("对齐门条目写建议 → [E30]", c == 1 and "[E30]" in out, out[-200:])

            write(a49, read(a49).replace(
                "| 对齐门 | — | 复述不能代 | 补证据 | 待裁决 |",
                "| 对齐门 | — | 复述不能代 | 不适用 | 待裁决 |"))
            c, out = run("doc_check.py", cwd=tmp41)
            check("对齐门改成「不适用」→ 0 error", c == 0 and "[E30]" not in out, out[-200:])

            # 已裁决的行是当时快照：修复改动原文后，引文不再逐字也放行（只对「待裁决」判逐字）。
            write(a49, read(a49)
                  .replace("| 本档 §1 | 本次范围 | 需求与实现对不上 | 补证据 | 待裁决 |",
                           "| 本档 §1 | 修复后已不存在的引文 | 需求与实现对不上 | 补证据 | 采纳 |")
                  .replace("| 对齐门 | — | 复述不能代 | 不适用 | 待裁决 |",
                           "| 对齐门 | — | 复述不能代 | 不适用 | 采纳 |"))
            c, out = run("doc_check.py", cwd=tmp41)
            check("已采纳的行：引文不再逐字也放行", c == 0 and "[E30]" not in out, out[-200:])
        finally:
            shutil.rmtree(tmp41, ignore_errors=True)

        # ---------------------------------------------------------------- 50
        print("\n50. 已验收 → 对照行：W9 提醒（REQ-020）")
        tmp50 = tempfile.mkdtemp(prefix="ddd-selftest50-")
        try:
            run(os.path.join(SKILL, "scripts", "doc_init.py"),
                "--target", ".", "--full", cwd=tmp50)
            feat50 = os.path.join(tmp50, "docs", "40-运行", "FEATURES.md")
            fc50 = os.path.join(tmp50, "docs", "40-运行", "功能对照.md")
            row50 = ("| **F-021** | 测试功能 | —（历史） | 有行 | "
                     "`python scripts/self_test.py -v` | S | 已验收 | —（历史） | "
                     "scripts/doc_check.py | self_test 第 1 组（2026-11-04） | —（历史） | —（历史） |")
            write(feat50, insert_after(read(feat50), FEATURE_ANCHOR, row50))
            c, out = run("doc_check.py", cwd=tmp50)
            check("F-021 已验收、对照清单无行 → [W9] 且 exit 0",
                  c == 0 and "[W9]" in out and "F-021" in out, out[-300:])
            check("W9 文案含「有行 ≠ 对照过」", "有行 ≠ 对照过" in out, out[-300:])

            write(fc50, insert_after(read(fc50), "| F-001 |", "| F-021 | 有行 | 一致 | 测试 |"))
            c, out = run("doc_check.py", cwd=tmp50)
            check("对照清单补 F-021 行后 W9 消失", c == 0 and "[W9]" not in out, out[-300:])

            row20 = row50.replace("F-021", "F-020")
            write(feat50, insert_after(read(feat50), FEATURE_ANCHOR, row20))
            c, out = run("doc_check.py", cwd=tmp50)
            check("F-020 存量豁免：无对照行也不报 W9", c == 0 and "[W9]" not in out, out[-300:])
        finally:
            shutil.rmtree(tmp50, ignore_errors=True)

        # ---------------------------------------------------------------- 51
        print("\n51. 设计卡选项空间：W10 形状检查（REQ-021）")
        tmp51 = tempfile.mkdtemp(prefix="ddd-selftest51-")
        try:
            run(os.path.join(SKILL, "scripts", "doc_init.py"),
                "--target", ".", "--full", cwd=tmp51)
            c, out = run("doc_check.py", cwd=tmp51)
            check("新项目首跑：模板示例卡无 [W10]", c == 0 and "[W10]" not in out, out[-300:])
            dc51 = os.path.join(tmp51, "docs", "00-门面", "设计卡.md")
            fm51 = read(dc51).split("---", 2)
            head51 = "---" + fm51[1] + "---\n\n# 设计卡\n\n"
            card51 = (
                "## K99 · W1.1 · 测试\n\n"
                "- **接口**：测试\n"
                "- **可替换点**：测试\n"
                "- **失败边界**：测试\n"
                "- **选项空间**：\n\n"
                "| 选项 | 轴 | 假设 | 失败模式 | 结论 | 回到条件 |\n"
                "|---|---|---|---|---|---|\n"
                "| A | 位置 | doc_check | 噪音 | 选中 | — |\n"
                "| B | 级别 | E 级 | 假行 | 被否 | 噪音大时 |\n"
                "| C 不做 | — | 靠人 | 会漏 | 被否 | 第 5 次漏时 |\n"
            )
            write(dc51, head51 + card51)
            c, out = run("doc_check.py", cwd=tmp51)
            check("合法设计卡：无 [W10]", c == 0 and "[W10]" not in out, out[-300:])

            write(dc51, head51 + card51.replace("- **选项空间**：", "- **选项**："))
            c, out = run("doc_check.py", cwd=tmp51)
            check("缺选项空间 → [W10]", c == 0 and "[W10]" in out, out[-300:])

            write(dc51, head51 + card51.replace(
                "| C 不做 | — | 靠人 | 会漏 | 被否 | 第 5 次漏时 |\n", ""))
            c, out = run("doc_check.py", cwd=tmp51)
            check("没有「不做 / 少做」→ [W10]", c == 0 and "[W10]" in out, out[-300:])

            write(dc51, head51 + card51.replace(
                "| B | 级别 | E 级 | 假行 | 被否 | 噪音大时 |\n"
                "| C 不做 | — | 靠人 | 会漏 | 被否 | 第 5 次漏时 |\n",
                "| B | 级别 | E 级 | 假行 | 被否 | — |\n"
                "| C 不做 | — | 靠人 | 会漏 | 被否 | — |\n"))
            c, out = run("doc_check.py", cwd=tmp51)
            check("被否方案无回到条件 → [W10]", c == 0 and "[W10]" in out, out[-300:])
        finally:
            shutil.rmtree(tmp51, ignore_errors=True)

        # ---------------------------------------------------------------- 52
        print("\n52. 方向线覆盖：brief 的 n/m（REQ-022）")
        tmp52 = tempfile.mkdtemp(prefix="ddd-selftest52-")
        try:
            run(os.path.join(SKILL, "scripts", "doc_init.py"),
                "--target", ".", "--full", cwd=tmp52)
            card52 = os.path.join(tmp52, "docs", "00-门面", "方向卡.md")
            c, out = run("devlog.py", "brief", cwd=tmp52)
            check("模板覆盖表无记录 → 覆盖：0/1 且 exit 0",
                  c == 0 and "覆盖：0/1" in out, out[-400:])

            write(card52, read(card52).replace(
                "| **D1** | —（未走通） | — | — |",
                "| **D1** | 2026-11-03 | 走通 | 本档 §1 |"))
            c, out = run("devlog.py", "brief", cwd=tmp52)
            check("补一条走通记录 → 覆盖：1/1",
                  c == 0 and "覆盖：1/1" in out, out[-400:])

            write(card52, read(card52).split("## 覆盖")[0].rstrip("\n") + "\n")
            c, out = run("devlog.py", "brief", cwd=tmp52)
            check("删掉覆盖节 → 覆盖：0/1 且 exit 0",
                  c == 0 and "覆盖：0/1" in out, out[-400:])
            check("覆盖行不误伤既有简报",
                  "计划：" in out and "收件箱：" in out and "复核：" in out, out[-400:])
        finally:
            shutil.rmtree(tmp52, ignore_errors=True)

        # ---------------------------------------------------------------- 53
        print("\n53. 走通待补：工作全完成但无走通记录（REQ-023）")
        tmp53 = tempfile.mkdtemp(prefix="ddd-selftest53-")
        try:
            run(os.path.join(SKILL, "scripts", "doc_init.py"),
                "--target", ".", "--full", cwd=tmp53)
            plan53 = os.path.join(tmp53, "docs", "00-门面", "开发计划.md")
            card53 = os.path.join(tmp53, "docs", "00-门面", "方向卡.md")
            write(plan53, read(plan53).replace(
                "| **W1.1** | （示例）端到端跑通一次 | D1 | 待开工 |",
                "| **W1.1** | （示例）端到端跑通一次 | D1 | 已完成 |"))
            c, out = run("devlog.py", "brief", cwd=tmp53)
            check("工作已完成、覆盖无记录 → 列出走通待补 D1",
                  c == 0 and "走通待补" in out and "D1" in out, out[-400:])

            write(card53, read(card53).replace(
                "| **D1** | —（未走通） | — | — |",
                "| **D1** | 2026-11-03 | 走通 | 本档 §1 |"))
            c, out = run("devlog.py", "brief", cwd=tmp53)
            check("补上覆盖记录 → 走通待补消失",
                  c == 0 and "走通待补" not in out, out[-400:])
        finally:
            shutil.rmtree(tmp53, ignore_errors=True)

        # ---------------------------------------------------------------- 54
        print("\n54. 增量取代链：superseded_by 让归档 delta 的行可以被后续 delta 删掉（E31）")
        tmp54 = tempfile.mkdtemp(prefix="ddd-selftest54-")
        try:
            run(os.path.join(SKILL, "scripts", "doc_init.py"),
                "--target", ".", "--full", cwd=tmp54)
            req54 = os.path.join(tmp54, "docs", "20-契约", "requirements.md")
            arc54 = os.path.join(tmp54, "docs", "20-契约", "_delta", "_archive")
            os.makedirs(arc54, exist_ok=True)

            added_row = ("| **REQ-002** | WHEN 调用跑一次 THE SYSTEM SHALL 输出 9 "
                         "| 跑一次 → 9 | `python t.py` | 待实现 | 示例 | 采纳✓ 2026-11-05 |")
            d1 = os.path.join(arc54, "DELTA-001-新增REQ-002.md")
            write(d1, "---\n"
                      'title: "DELTA-001 · 新增 REQ-002"\n'
                      "layer: contract\ndomain: 全局\nstatus: snapshot\nauthority: 4\n"
                      "updated: 2026-11-05\n"
                      'summary: "新增一条示例需求。"\ntags: [契约, 增量]\n'
                      "delta_id: DELTA-001\ntarget: docs/20-契约/requirements.md\n"
                      "superseded_by: DELTA-002\n"
                      "---\n\n# DELTA-001 · 新增 REQ-002\n\n"
                      "## 1. 变更清单\n\n| # | 操作 | 一句话 |\n|---|---|---|\n"
                      "| 1 | ADDED | 新增 REQ-002 |\n\n## 2. 逐字变更\n\n"
                      "**变更 1 · ADDED · REQ-002**\n\n位置：需求表末尾\n\n"
                      "```markdown\n" + added_row + "\n```\n\n"
                      "**合并要求**：本 delta **必须**按锚点合并，**不得**直接删除。\n")
            d2 = os.path.join(arc54, "DELTA-002-撤掉REQ-002.md")
            write(d2, "---\n"
                      'title: "DELTA-002 · 撤掉 REQ-002"\n'
                      "layer: contract\ndomain: 全局\nstatus: snapshot\nauthority: 4\n"
                      "updated: 2026-11-05\n"
                      'summary: "撤掉上一条需求。"\ntags: [契约, 增量]\n'
                      "delta_id: DELTA-002\ntarget: docs/20-契约/requirements.md\n"
                      "supersedes: DELTA-001\n"
                      "---\n\n# DELTA-002 · 撤掉 REQ-002\n\n"
                      "## 1. 变更清单\n\n| # | 操作 | 一句话 |\n|---|---|---|\n"
                      "| 1 | REMOVED | 撤掉 REQ-002 |\n\n## 2. 逐字变更\n\n"
                      "**变更 1 · REMOVED · REQ-002**\n\n锚点（before，逐字）：\n\n"
                      "```markdown\n" + added_row + "\n```\n\n"
                      "**合并要求**：本 delta **必须**按锚点合并，**不得**直接删除。\n")

            c, out = run("doc_check.py", cwd=tmp54)
            check("REQ-002 被后续 delta 删掉、DELTA-001 标了 superseded_by → 不报 E21",
                  c == 0 and "[E21]" not in out and "[E31]" not in out, out[-400:])

            write(d1, read(d1).replace("superseded_by: DELTA-002", "superseded_by: DELTA-999"))
            c, out = run("doc_check.py", cwd=tmp54)
            check("superseded_by 指向不存在的 delta → [E31]",
                  c == 1 and "[E31]" in out, out[-400:])

            write(d1, read(d1).replace("superseded_by: DELTA-999\n", ""))
            c, out = run("doc_check.py", cwd=tmp54)
            check("去掉 superseded_by → 回到 [E21]（合并丢失）",
                  c == 1 and "[E21]" in out, out[-400:])
        finally:
            shutil.rmtree(tmp54, ignore_errors=True)

        # ---------------------------------------------------------------- 55
        print("\n55. 活文档出处：带版本日期才放行（REQ-025）")
        tmp55 = tempfile.mkdtemp(prefix="ddd-selftest55-")
        try:
            run(os.path.join(SKILL, "scripts", "doc_init.py"),
                "--target", ".", "--full", cwd=tmp55)
            run("devlog.py", "new", "--title", "想法出处", "--scope", "试", cwd=tmp55)
            d55 = os.path.join(tmp55, "docs", "70-过程", "会话")
            a55 = sorted(os.path.join(d55, f) for f in os.listdir(d55)
                         if f.endswith(".md"))[-1]
            block55 = (
                "\n\n### 3.7 想法候选（整理产物）\n\n"
                "| # | 类别 | 原话（逐字） | 出处 | 建议落点 | 裁决 |\n"
                "|---|---|---|---|---|---|\n"
                "| 1 | 愿景 | 想法经由会话流入项目 | docs/00-门面/vision.md（2026-11-04） | — | 待定 |\n"
            )
            write(a55, read(a55) + block55)
            c, out = run("doc_check.py", cwd=tmp55)
            check("带版本日期的活文档出处 → 不核逐字（0 error）",
                  c == 0 and "[E29]" not in out, out[-300:])

            write(a55, read(a55).replace("vision.md（2026-11-04）", "vision.md"))
            c, out = run("doc_check.py", cwd=tmp55)
            check("活文档出处不带日期 → [E29]",
                  c == 1 and "[E29]" in out, out[-300:])

            write(a55, read(a55).replace("| docs/00-门面/vision.md |",
                                         "| docs/00-门面/vision.md（2026-13-40） |"))
            c, out = run("doc_check.py", cwd=tmp55)
            check("版本日期不合法 → [E29]",
                  c == 1 and "[E29]" in out, out[-300:])
        finally:
            shutil.rmtree(tmp55, ignore_errors=True)

        # ---------------------------------------------------------------- 56
        print("\n56. 复述门：用户拍板的决策要引用可查的原话（REQ-026）")
        tmp56 = tempfile.mkdtemp(prefix="ddd-selftest56-")
        try:
            run(os.path.join(SKILL, "scripts", "doc_init.py"),
                "--target", ".", "--full", cwd=tmp56)
            run("devlog.py", "new", "--title", "复述门", "--scope", "试", cwd=tmp56)
            d56 = os.path.join(tmp56, "docs", "70-过程", "会话")
            a56 = sorted(os.path.join(d56, f) for f in os.listdir(d56)
                         if f.endswith(".md"))[-1]
            base56 = read(a56)
            base56 = base56.replace(
                "## 2. 用户侧记录（分类）",
                "## 2. 用户侧记录（分类）\n\n- 用户原话：「确认后一律落到 L2」\n", 1)
            base56 = (base56
                      .replace("### D1 · （在决定什么）", "### D1 · 落哪一层")
                      .replace("**拍板**：（用户 / agent 自选；只有用户拍板的进收尾决策回顾）", "**拍板**：用户")
                      .replace("**依据**：（用户原话照抄，用 `「…」` 引起来——`S12` 会核它在正文里逐字可查；或 ADR / 任务号）",
                               "**依据**：「确认后一律落到 L2」")
                      .replace("**撤销条件**：（什么可观察的事实出现就推翻它；写不出就是断链）",
                               "**撤销条件**：若落到别层。"))
            write(a56, base56)
            c, out = run("devlog.py", "check", cwd=tmp56)
            check("依据引用本档原话 → 0 error", c == 0 and "S12" not in out, out[-400:])

            write(a56, read(a56).replace("**依据**：「确认后一律落到 L2」",
                                         "**依据**：「确认后一律落到 L3」"))
            c, out = run("devlog.py", "check", cwd=tmp56)
            check("引用的原话在本档查不到 → S12", c == 1 and "S12" in out, out[-400:])

            write(a56, read(a56).replace("**依据**：「确认后一律落到 L3」", "**依据**：用户说要落 L2"))
            c, out = run("devlog.py", "check", cwd=tmp56)
            check("依据没写引号原话 → S12", c == 1 and "S12" in out, out[-400:])
        finally:
            shutil.rmtree(tmp56, ignore_errors=True)

        # ---------------------------------------------------------------- 57
        print("\n57. 决策台账：生成 / 断链 / brief 提醒（REQ-028）")
        tmp57 = tempfile.mkdtemp(prefix="ddd-selftest57-")
        try:
            run(os.path.join(SKILL, "scripts", "doc_init.py"),
                "--target", ".", "--full", cwd=tmp57)
            run("devlog.py", "new", "--title", "决策台账", "--scope", "试", cwd=tmp57)
            d57 = os.path.join(tmp57, "docs", "70-过程", "会话")
            a57 = sorted(os.path.join(d57, f) for f in os.listdir(d57)
                         if f.endswith(".md"))[-1]
            base57 = read(a57)
            base57 = base57.replace(
                "### D1 · （在决定什么）", "### D1 · 落哪一层")
            base57 = (base57
                      .replace("**拍板**：（用户 / agent 自选；只有用户拍板的进收尾决策回顾）",
                               "**拍板**：用户")
                      .replace("**依据**：（用户原话照抄，用 `「…」` 引起来——`S12` 会核它在正文里逐字可查；或 ADR / 任务号）",
                               "**依据**：「就落 L2」")
                      .replace("**撤销条件**：（什么可观察的事实出现就推翻它；写不出就是断链）",
                               "**撤销条件**：若 ISS-999 闭合时重议。"))
            base57 = base57.replace("## 2. 用户侧记录（分类）",
                                    "## 2. 用户侧记录（分类）\n\n- 用户原话：「就落 L2」\n", 1)
            write(a57, base57)
            c, out = run("devlog.py", "decisions", cwd=tmp57)
            ledger = os.path.join(tmp57, "docs", "70-过程", "决策台账.md")
            text57 = read(ledger) if os.path.exists(ledger) else ""
            check("decisions 生成台账：1 条、断链 1 条",
                  c == 0 and "共 **1** 条决策" in text57 and "| 断链 |" in text57, out[-300:])

            c, out = run("devlog.py", "brief", cwd=tmp57)
            check("brief 提醒决策待复核", c == 0 and "决策待复核：1" in out, out[-300:])
        finally:
            shutil.rmtree(tmp57, ignore_errors=True)

        # ---------------------------------------------------------------- 58
        print("\n58. 产出对账：§6 列的路径要真实存在（W11）")
        tmp58 = tempfile.mkdtemp(prefix="ddd-selftest58-")
        try:
            run(os.path.join(SKILL, "scripts", "doc_init.py"),
                "--target", ".", "--full", cwd=tmp58)
            run("devlog.py", "new", "--title", "产出对账", "--scope", "试", cwd=tmp58)
            d58 = os.path.join(tmp58, "docs", "70-过程", "会话")
            a58 = sorted(os.path.join(d58, f) for f in os.listdir(d58)
                         if f.endswith(".md"))[-1]
            base58 = read(a58)
            block58 = ("\n\n| 类型 | 路径 | 说明 |\n|---|---|---|\n"
                       "| 代码 | `scripts/nope_missing.py` | 假路径 |\n")
            write(a58, base58.replace("## 6. 本次产出", "## 6. 本次产出" + block58, 1))
            c, out = run("devlog.py", "check", cwd=tmp58)
            check("§6 列了不存在的路径 → W11（不阻断）",
                  c == 0 and "W11" in out, out[-400:])

            write(a58, read(a58).replace("scripts/nope_missing.py", "scripts/doc_check.py"))
            c, out = run("devlog.py", "check", cwd=tmp58)
            check("路径都存在 → 无 W11", c == 0 and "W11" not in out, out[-400:])
        finally:
            shutil.rmtree(tmp58, ignore_errors=True)

        # ---------------------------------------------------------------- 59
        print("\n59. 成本台账：自报耗时 + 密度 + 环比（REQ-030）")
        tmp59 = tempfile.mkdtemp(prefix="ddd-selftest59-")
        try:
            run(os.path.join(SKILL, "scripts", "doc_init.py"),
                "--target", ".", "--full", cwd=tmp59)
            run("devlog.py", "new", "--title", "成本", "--scope", "试", cwd=tmp59)
            d59 = os.path.join(tmp59, "docs", "70-过程", "会话")
            a59 = sorted(os.path.join(d59, f) for f in os.listdir(d59)
                         if f.endswith(".md"))[-1]
            write(a59, read(a59).replace(
                "open_items: 0",
                "open_items: 0\ncost_minutes: 180\ncost_tool_minutes: 30\ncost_note: 卡在 X"))
            c, out = run("devlog.py", "cost", cwd=tmp59)
            ledger = os.path.join(tmp59, "docs", "70-过程", "成本台账.md")
            text59 = read(ledger) if os.path.exists(ledger) else ""
            check("cost 生成台账：总 180 / 工具 30 / 占比 16.7%",
                  c == 0 and "| 180 | 30 | 16.7% |" in text59, out[-300:])

            c, out = run("devlog.py", "cost", "--json", cwd=tmp59)
            check("--json 给出可读行", c == 0 and '"total": 180' in out, out[-300:])
        finally:
            shutil.rmtree(tmp59, ignore_errors=True)

        # ---------------------------------------------------------------- 60
        print("\n60. 五件套批量入口：plan.py new-feature（REQ-031）")
        tmp60 = tempfile.mkdtemp(prefix="ddd-selftest60-")
        try:
            run(os.path.join(SKILL, "scripts", "doc_init.py"),
                "--target", ".", "--full", cwd=tmp60)
            req60 = os.path.join(tmp60, "docs", "20-契约", "requirements.md")
            feats60 = os.path.join(tmp60, "docs", "40-运行", "FEATURES.md")
            plan60 = os.path.join(tmp60, "docs", "00-门面", "开发计划.md")
            card60 = os.path.join(tmp60, "docs", "00-门面", "设计卡.md")
            five = [req60, feats60, plan60, card60]

            # 正文里的反例编号（REQ-999 / F-999）不能被当成「已用到 999」——
            # 自动编号只认表格首列，否则下一个会变成 F-1000。
            write(req60, read(req60).replace(
                "## 1. 需求", "> 反例：REQ-999 只是正文，不是定义。\n\n## 1. 需求", 1))
            write(feats60, read(feats60).replace(
                "## 1. 功能", "> 反例：引用不存在的 F-999 会被 E24 拦下。\n\n## 1. 功能", 1))

            def hashes():
                return [hashlib.sha256(read(p).encode("utf-8")).hexdigest() for p in five]

            base = tuple([
                "new-feature",
                "--title", "五件套批量入口",
                "--req", "WHEN 运行 plan.py new-feature THE SYSTEM SHALL 一次写出 "
                         "REQ / F / W / T / K 五件套",
                "--accept", "临时项目跑一次 → 五处各多一行或一卡，plan check 0 error",
                "--verify", "`python scripts/self_test.py -v`（第 60 组）",
                "--direction", "D1",
                "--work", "五件套批量入口",
                "--task", "new-feature 子命令（断言先行）",
                "--scores", "3,4,4,3,5,3",
                "--cost", "S",
                "--design-interface", "一条 CLI：参数进，五份载体出；只增不改既有行",
                "--design-swappable", "输入形态（CLI / JSON）与落点位置是两处可替换点",
                "--design-failure", "参数缺失 / 撞号 / 分值越界 → exit 1 且五份文件零写入",
            ])

            h0 = hashes()
            c, out = run("plan.py", *base, cwd=tmp60)
            check("一次调用建出五个编号（REQ-002 / F-004 / W1.2 / T1.2.1 / K2）",
                  c == 0 and all(x in out for x in
                                 ("REQ-002", "F-004", "W1.2", "T1.2.1", "K2")), out[-500:])

            rq, ft, pl, dc = read(req60), read(feats60), read(plan60), read(card60)
            check("REQ 行落在需求表里（§2 之前）",
                  "**REQ-002**" in rq
                  and rq.index("**REQ-002**") < rq.index("## 2. 不得做的事"))
            check("F 行落在功能表里（任务考核之前，ISS-047）",
                  "**F-004**" in ft
                  and ft.index("**F-004**") < ft.index("## 2. 任务考核"))
            check("W 行在 §4、T 行在 §5，且任务双亲 F + W 齐全",
                  "**W1.2**" in pl and "**T1.2.1**" in pl
                  and "| F-004 | W1.2 |" in pl)
            check("设计卡 K2 挂 W1.2", "## K2 · W1.2 · " in dc)
            check("默认卡片含「观测四格」「回看」两节（四格写待补）",
                  "**观测四格**：观测对象=待补" in dc
                  and "**回看（拆分确立前）**：待补" in dc, dc[-500:])

            c, out = run("plan.py", "check", cwd=tmp60)
            check("五件套建完 plan check 0 error", c == 0 and "errors=0" in out, out[-300:])
            c, out = run("doc_check.py", "--quiet", cwd=tmp60)
            check("五件套建完 doc_check 0 error（无 E 码）",
                  c == 0 and "errors=0" in out, out[-400:])

            h1 = hashes()
            c, out = run("plan.py", *base, "--dry-run", "--json", cwd=tmp60)
            check("--dry-run --json：给出下一组五个编号且零写入",
                  c == 0 and '"dry_run": true' in out and '"written": false' in out
                  and all(x in out for x in
                          ("REQ-003", "F-005", "W1.3", "T1.3.1", "K3"))
                  and hashes() == h1, out[-500:])

            look = "「建卡时两节一次填齐」|临时项目里没有既有入口|与 W10 不重（那条管选项空间）"
            obs = "新建的 K 卡|两节是否一次建齐|卡片正文 + doc_check 输出|建卡那一次"
            c, out = run("plan.py", *base, "--design-lookback", look,
                         "--design-observe", obs, cwd=tmp60)
            dc = read(card60)
            check("--design-lookback / --design-observe：K3 两节一次填齐、四格无待补",
                  c == 0 and "## K3 · W1.3 · " in dc
                  and "**观测四格**：观测对象=新建的 K 卡" in dc
                  and "上游原句（逐字）：「建卡时两节一次填齐」" in dc, out[-500:])
            c2, out2 = run("doc_check.py", cwd=tmp60)
            check("填齐的 K3 不报 W12，默认卡 K2 仍报（占位照报）",
                  c2 == 0
                  and "W12] 00-门面/设计卡.md: K2（W1.2）" in out2
                  and "W12] 00-门面/设计卡.md: K3（W1.3）" not in out2,
                  out2[-700:])
            h_after = hashes()
            c, out = run("plan.py", *base, "--design-observe", "a|b|c", cwd=tmp60)
            check("--design-observe 段数不对 → exit 1 且零写入",
                  c == 1 and hashes() == h_after, out[-500:])

            h2 = hashes()
            c, out = run("plan.py", "new-feature", "--title", "缺需求", cwd=tmp60)
            check("缺 --req → exit 1 且五份文件零写入",
                  c == 1 and hashes() == h2, out[-400:])

            c, out = run("plan.py", *base, "--req-id", "REQ-001", cwd=tmp60)
            check("撞号 --req-id REQ-001 → exit 1 且零写入",
                  c == 1 and hashes() == h2, out[-400:])

            bad = [x if x != "3,4,4,3,5,3" else "1,2,3" for x in base]
            c, out = run("plan.py", *bad, cwd=tmp60)
            check("六维分值不足 6 个 → exit 1 且零写入",
                  c == 1 and hashes() == h2, out[-400:])

            c, out = run("plan.py", *base, "--work-id", "W9.1", cwd=tmp60)
            check("--work-id 指向不存在的工作 → exit 1 且零写入",
                  c == 1 and hashes() == h2, out[-400:])

            # 只替换 --title 的值；--work 的值保持无竖线，避免把标题的转义算进工作名
            piped = list(base)
            piped[piped.index("--title") + 1] = "五件|套"
            piped[piped.index("--work") + 1] = "管道转义"
            c, out = run("plan.py", *piped, cwd=tmp60)
            c2, out2 = run("doc_check.py", "--quiet", cwd=tmp60)
            check("标题含竖线被转义：不报 E28、doc_check 0 error",
                  c == 0 and "[E28]" not in out2 and "errors=0" in out2, out2[-400:])

            h3 = hashes()
            existing = list(base)
            existing[existing.index("--direction") + 1] = "D1"
            existing[existing.index("--work")] = "--work-id"
            existing[existing.index("--work-id") + 1] = "W1.1"
            existing[existing.index("--title") + 1] = "挂已有工作"
            c, out = run("plan.py", *existing, cwd=tmp60)
            check("--work-id 指向已有工作：不新建卡、任务落 T1.1.2",
                  c == 0 and "T1.1.2" in out and "K1" in out
                  and hashes()[3] == h3[3], out[-500:])

            # ISS-098：--work-id 的判据是「工作存在且方向一致」，不要求前缀数字 == 方向号
            pl60 = read(plan60).replace(
                "| **D1** | （示例）核心链路打通 | 方向卡.md | |",
                "| **D1** | （示例）核心链路打通 | 方向卡.md | |\n"
                "| **D2** | （测试）全局序号工作所在方向 | 方向卡.md | |", 1)
            pl60 = pl60.replace(
                "| **W1.1** | （示例）端到端跑通一次 | D1 | 待开工 | "
                "一次真实记录 + 落库行 | — | — |",
                "| **W1.1** | （示例）端到端跑通一次 | D1 | 待开工 | "
                "一次真实记录 + 落库行 | — | — |\n"
                "| **W26.3** | （测试）全局序号工作 | D2 | 进行中 | — | — | — |", 1)
            write(plan60, pl60)
            write(card60, read(card60).rstrip("\n") +
                  "\n\n## K99 · W26.3 · 全局序号工作\n\n"
                  "- **接口**：测试桩，只用来验证 --work-id 判据\n"
                  "- **可替换点**：无（测试桩，不替换）\n"
                  "- **失败边界**：无（测试桩，不判边界）\n")

            def work_args(wid, direction):
                args = list(base)
                args[args.index("--direction") + 1] = direction
                args[args.index("--work")] = "--work-id"
                args[args.index("--work-id") + 1] = wid
                args[args.index("--title") + 1] = f"挂 {wid}"
                return args

            h4 = hashes()
            c, out = run("plan.py", *work_args("W26.3", "D2"), cwd=tmp60)
            check("ISS-098：--work-id W26.3（全局序号）可给已有工作挂 REQ/F/T，"
                  "任务落 T26.3.1 且设计卡不动",
                  c == 0 and "T26.3.1" in out and hashes()[3] == h4[3], out[-500:])

            h5 = hashes()
            c, out = run("plan.py", *work_args("W26.3", "D1"), cwd=tmp60)
            check("已有工作方向与 --direction 不一致 → exit 1 且零写入",
                  c == 1 and hashes() == h5, out[-400:])

            h6 = hashes()
            c, out = run("plan.py", *work_args("W99.9", "D1"), cwd=tmp60)
            check("--work-id 指向不存在的工作 → exit 1 且零写入（不新建）",
                  c == 1 and hashes() == h6, out[-400:])

            c, out = run("plan.py", "--help", cwd=tmp60)
            check("--help 列出 new-feature（只读，不写盘）",
                  c == 0 and "new-feature" in out, out[-300:])
        finally:
            shutil.rmtree(tmp60, ignore_errors=True)

        # ---------------------------------------------------------------- 61
        print("\n61. 档案 H1 识别：跳过 front-matter（ISS-094）")
        tmp61 = tempfile.mkdtemp(prefix="ddd-selftest61-")
        try:
            run(os.path.join(SKILL, "scripts", "doc_init.py"),
                "--target", ".", "--full", cwd=tmp61)
            run("devlog.py", "new", "--title", "H1 识别", "--scope", "试", cwd=tmp61)
            d61 = os.path.join(tmp61, "docs", "70-过程", "会话")
            a61 = sorted(os.path.join(d61, f) for f in os.listdir(d61)
                         if f.endswith(".md"))[-1]
            # front-matter 里出现以 `# ` 开头的注释行（成本自报说明就长这样）。
            # 旧实现把全文第一个 `# ` 行当 H1，撞上注释就报 S2「title 与 H1 不一致」——
            # 每开一场新档都要人工消错一次（上一场为此改了 4 次档案），是典型假红。
            body61 = read(a61).replace(
                "open_items: 0", "open_items: 0\n# 成本自报（可选，收尾时填）", 1)
            write(a61, body61)
            c, out = run("devlog.py", "check", cwd=tmp61)
            check("front-matter 含 `# ` 注释行 → devlog check 0 error、无 S2",
                  c == 0 and "S2" not in codes(out), out[-400:])

            # 第二半不是缺陷，是格式坑：§4 的 `**依据**` 等字段必须各占一行
            # （取字段的正则按 `^` 锚定）。挤成一行会连报多条 S12——把它们
            # 固定成一条断言，免得下次再以为是「三个错」。
            sec4 = ("## 4. 决策与选项对比\n\n### D1 · 字段挤一行\n\n"
                    "**拍板**：用户 **依据**：「按推荐」 **撤销条件**：再出现假红就回退\n\n")
            i4, i5 = body61.index("## 4."), body61.index("## 5.")
            write(a61, body61[:i4] + sec4 + body61[i5:])
            c, out = run("devlog.py", "check", cwd=tmp61)
            check("§4 字段挤一行 → 报 S12 且不报 S2",
                  "S12" in codes(out) and "S2" not in codes(out), out[-500:])
        finally:
            shutil.rmtree(tmp61, ignore_errors=True)

        # ---------------------------------------------------------------- 62
        print("\n62. 项目侧观测载体：模板 + 四格 + W12")
        tmp62 = tempfile.mkdtemp(prefix="ddd-selftest62-")
        try:
            run(os.path.join(SKILL, "scripts", "doc_init.py"), "--target", ".", cwd=tmp62)
            obs62 = os.path.join(tmp62, "docs", "40-运行", "可观测性.md")
            check("基础 5 层 doc_init 铺出 40-运行/可观测性.md", os.path.exists(obs62))
            if os.path.exists(obs62):
                body62 = read(obs62)
                check("观测地图含四维 / 四问 / 系统级串联",
                      all(x in body62 for x in
                          ("可观测", "可解释", "可诊断", "可改进",
                           "运行的是什么", "预期是什么样的", "系统级")))
            plan62 = os.path.join(tmp62, "docs", "00-门面", "开发计划.md")
            card62 = os.path.join(tmp62, "docs", "00-门面", "设计卡.md")
            p62 = insert_after(read(plan62), "| **W1.1** |",
                               "| **W1.2** | 观测测试 | D1 | 待开工 | 缺四格 → W12 | — | — |")
            write(plan62, p62)
            write(card62, read(card62) + (
                "\n## K2 · W1.2 · 观测测试\n\n"
                "- **接口**：测试用。\n"
                "- **可替换点**：无（测试卡）。\n"
                "- **选项空间**：\n\n"
                "  | 选项 | 轴 | 假设 | 失败模式 | 结论 | 回到条件 |\n"
                "  |---|---|---|---|---|---|\n"
                "  | A 少做：不做 | 范围 | 零改动 | 测不出 | 被否 | 需要时 |\n"
                "  | B 做 | 范围 | 可测 | 多一行 | 选中 | — |\n"
                "  | C 另一条 | 范围 | 可测 | 多一行 | 被否 | 需要时 |\n\n"
                "- **失败边界**：测试用。\n"))
            c, out = run("doc_check.py", cwd=tmp62)
            check("待开工卡缺观测四格 → W12（exit 0）",
                  c == 0 and "W12" in codes(out), out[-500:])

            write(card62, read(card62).replace(
                "- **失败边界**：测试用。\n",
                "- **观测四格**：观测对象=组件；要回答的问题=卡在哪；信号=日志；窗口=终端。\n"
                "- **失败边界**：测试用。\n"))
            c, out = run("doc_check.py", cwd=tmp62)
            check("补齐观测四格 → 无 W12", "W12" not in codes(out), out[-400:])

            write(plan62, read(plan62).replace(
                "| **W1.2** | 观测测试 | D1 | 待开工 |",
                "| **W1.2** | 观测测试 | D1 | 已完成 |"))
            write(card62, read(card62).replace(
                "- **观测四格**：观测对象=组件；要回答的问题=卡在哪；信号=日志；窗口=终端。\n", ""))
            c, out = run("doc_check.py", cwd=tmp62)
            check("已完成卡缺观测四格不追溯（无 W12）", "W12" not in codes(out), out[-400:])

            write(obs62, read(obs62) + "\n<!-- keep-me -->\n")
            run(os.path.join(SKILL, "scripts", "doc_init.py"), "--target", ".", cwd=tmp62)
            check("重复 doc_init 不覆盖已有观测地图", "keep-me" in read(obs62))
        finally:
            shutil.rmtree(tmp62, ignore_errors=True)

        # ---------------------------------------------------------------- 63
        print("\n63. 自身参考实现：observe run / five-run / status")
        tmp63 = tempfile.mkdtemp(prefix="ddd-selftest63-")
        try:
            run(os.path.join(SKILL, "scripts", "doc_init.py"), "--target", ".", cwd=tmp63)
            shutil.copy(os.path.join(SKILL, "scripts", "observe.py"),
                        os.path.join(tmp63, "scripts", "observe.py"))
            c, out = run("observe.py", "run", "--name", "demo",
                         "--expected", "exit 0", "--",
                         PY, "-c", "print('[E12] bad'); raise SystemExit(1)", cwd=tmp63)
            check("observe run 不改变子命令退出码", c == 1, out[-300:])
            runs = os.path.join(tmp63, ".dd", "observe", "runs")
            files = sorted(os.listdir(runs)) if os.path.isdir(runs) else []
            check("observe run 留下一条运行记录", len(files) == 1, str(files))
            if files:
                rec = json.loads(read(os.path.join(runs, files[0])).splitlines()[0])
                check("记录含四问：argv / findings / expected / next_action",
                      bool(rec.get("argv")) and bool(rec.get("actual", {}).get("findings"))
                      and bool(rec.get("expected")) and bool(rec.get("next_action"))
                      and rec.get("record_status") == "ok",
                      json.dumps(rec, ensure_ascii=False)[:300])
                check("预期与实际并排：expected_status=not_met、exit_code=1",
                      rec.get("expected_status") == "not_met"
                      and rec.get("actual", {}).get("exit_code") == 1)
                check("finding.key 稳定（码:span）且不含行号",
                      rec["actual"]["findings"][0].get("key") == "E12:demo")
                c, out = run("observe.py", "show", rec["run_id"], cwd=tmp63)
                check("observe show 回看四问", c == 0 and "next:" in out and "expected=" in out,
                      out[-300:])

            c, out = run("observe.py", "five-run", cwd=tmp63)
            check("five-run 在干净骨架 0 error", c == 0 and "5/5" in out, out[-400:])
            c, out = run("observe.py", "status", cwd=tmp63)
            check("status 列出最近运行", c == 0 and "5 span" in out, out[-400:])
            c, out = run("observe.py", "status", "--check", cwd=tmp63)
            check("status --check 有记录时不报缺口", c == 0 and "证据缺口" not in out, out[-300:])

            bad_dir = os.path.join(tmp63, "not-a-dir")
            write(bad_dir, "x")
            c, out = run("observe.py", "run", "--observe-dir", bad_dir, "--",
                         PY, "-c", "raise SystemExit(1)", cwd=tmp63)
            check("观测写失败只降级、不改退出码",
                  c == 1 and "degraded" in out.lower(), out[-300:])

            shutil.rmtree(os.path.join(tmp63, ".dd", "observe"), ignore_errors=True)
            c, out = run("observe.py", "status", "--check", cwd=tmp63)
            check("无运行记录 → 证据缺口、exit 0",
                  c == 0 and "证据缺口" in out, out[-300:])
        finally:
            shutil.rmtree(tmp63, ignore_errors=True)

        # ---------------------------------------------------------------- 64
        print("\n64. 可改进：observe trend 跨 run 聚合")
        tmp64 = tempfile.mkdtemp(prefix="ddd-selftest64-")
        try:
            run(os.path.join(SKILL, "scripts", "doc_init.py"), "--target", ".", cwd=tmp64)
            shutil.copy(os.path.join(SKILL, "scripts", "observe.py"),
                        os.path.join(tmp64, "scripts", "observe.py"))
            for line in ("a.md:12", "a.md:15", "b.md:30", "c.md:40"):
                run("observe.py", "run", "--name", "demo", "--",
                    PY, "-c", f"print('[E12] {line} bad'); raise SystemExit(1)", cwd=tmp64)
            runs64 = os.path.join(tmp64, ".dd", "observe", "runs")
            before64 = sorted(os.listdir(runs64)) if os.path.isdir(runs64) else []
            c, out = run("observe.py", "trend", cwd=tmp64)
            check("trend 同一码+文件聚成 1 条、计数 2",
                  c == 0 and "E12:a.md" in out and "count=2" in out, out[-500:])
            check("trend 不同文件分开",
                  "E12:b.md" in out and "E12:c.md" in out and "count=1" in out, out[-500:])
            check("trend 行号漂移不拆条", out.count("E12:a.md") == 1, out[-500:])
            after64 = sorted(os.listdir(runs64)) if os.path.isdir(runs64) else []
            check("trend 不写运行记录", before64 == after64 and len(after64) == 4,
                  f"{before64} -> {after64}")
            c, out = run("observe.py", "trend", "--json", cwd=tmp64)
            data = json.loads(out) if c == 0 else {}
            keys = {k.get("key"): k for k in data.get("keys", [])}
            check("trend --json 计数与 runs",
                  keys.get("E12:a.md", {}).get("count") == 2
                  and keys.get("E12:a.md", {}).get("runs") == 2, out[-500:])
            check("trend --json 带首次 / 最近 / 版本",
                  bool(keys.get("E12:a.md", {}).get("first_seen"))
                  and bool(keys.get("E12:a.md", {}).get("last_seen"))
                  and bool(keys.get("E12:a.md", {}).get("versions")), out[-500:])
            c, out = run("observe.py", "trend", "--limit", "1", "--json", cwd=tmp64)
            data = json.loads(out) if c == 0 else {}
            check("--limit 1 只看最近一个 run",
                  [k.get("key") for k in data.get("keys", [])] == ["E12:c.md"], out[-400:])
            c, out = run("observe.py", "trend", "--since", "2099-01-01", "--json", cwd=tmp64)
            data = json.loads(out) if c == 0 else {}
            check("--since 过滤到窗口外", c == 0 and data.get("keys") == [], out[-400:])
            shutil.rmtree(os.path.join(tmp64, ".dd", "observe"), ignore_errors=True)
            c, out = run("observe.py", "trend", cwd=tmp64)
            check("无记录 → 证据缺口、exit 0", c == 0 and "证据缺口" in out, out[-300:])
        finally:
            shutil.rmtree(tmp64, ignore_errors=True)

        # ---------------------------------------------------------------- 65
        print("\n65. 随包脚本的 3.8 语法门（ISS-101）")

        def fstring_backslash_hits(name, src):
            """f-string 表达式里含反斜杠（3.8–3.11 不支持，PEP 701 才放开）。

            为什么不能只靠 `ast.parse(feature_version=(3, 8))`：在 3.12 上它只拦**语句级**
            新语法（如 `match`），不拦 PEP 701 的回退（实测 f-string 反斜杠照样 ok）。
            3.12 的 tokenizer 把 f-string 拆成 FSTRING_START / 表达式 token / FSTRING_MIDDLE，
            所以这里只在「表达式区间」里找反斜杠；< 3.12 时 `ast.parse` 自己就会拒，不必重复判。
            """
            if not hasattr(tokenize, "FSTRING_START"):
                return []
            skip = {tokenize.FSTRING_MIDDLE, tokenize.COMMENT, tokenize.NL,
                    tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT}
            hits, depth = [], 0
            try:
                for tok in tokenize.generate_tokens(io.StringIO(src).readline):
                    if tok.type == tokenize.FSTRING_START:
                        depth += 1
                    elif tok.type == tokenize.FSTRING_END:
                        depth = max(0, depth - 1)
                    elif depth and tok.type not in skip and "\\" in tok.string:
                        hits.append((name, tok.start[0],
                                     "f-string 表达式含反斜杠（3.8–3.11 不支持）"))
            except (tokenize.TokenError, IndentationError):
                pass
            return hits

        def py38_bad(sources):
            """[(文件名, 行号, 信息)]；sources = [(显示名, 源码)]。"""
            out = []
            for name, src in sources:
                try:
                    ast.parse(src, filename=name, feature_version=(3, 8))
                except SyntaxError as e:
                    out.append((name, e.lineno or 0, e.msg))
                out.extend(fstring_backslash_hits(name, src))
            return out

        scripts_dir = os.path.join(SKILL, "scripts")
        pkg_py = sorted(f for f in os.listdir(scripts_dir)
                        if f.endswith(".py") and os.path.isfile(os.path.join(scripts_dir, f)))
        check("扫到随包脚本（≥ 8 个且含 plan.py）",
              len(pkg_py) >= 8 and "plan.py" in pkg_py, f"{len(pkg_py)} 个：{pkg_py}")
        bad = py38_bad([(f, read(os.path.join(scripts_dir, f))) for f in pkg_py])
        check("全部随包脚本在 3.8 语法下可解析", not bad,
              "；".join("%s:%d %s" % b for b in bad))

        # 反例自证：3.12 才放开（PEP 701）的写法必须被判出——2.10.0 的 `plan.py` 就是这样炸的
        bad_sample = ('import re\n'
                      'x = "a1"\n'
                      's = f"{re.sub(r\'\\d\', \'\', x)}"\n')
        bad = py38_bad([("bad.py", bad_sample)])
        check("反例：f-string 表达式含反斜杠被判出", len(bad) == 1, f"{bad}")
        check("反例：报出 file:line（第 3 行）", [b[1] for b in bad] == [3], f"{bad}")
        # 反证：只把正则挪出表达式（同样求值）必须通过——检查器不能「一律报错」
        good_sample = ('import re\n'
                       'x = "a1"\n'
                       'PAT = r"\\d"\n'
                       's = f"{re.sub(PAT, \'\', x)}"\n')
        check("反证：正则挪出表达式后通过", py38_bad([("good.py", good_sample)]) == [])

        # ---------------------------------------------------------------- 66
        print("\n66. 问题链：源自 / 须先（D11–D14 / W13）")
        tmp66 = tempfile.mkdtemp(prefix="ddd-selftest66-")
        try:
            run(os.path.join(SKILL, "scripts", "doc_init.py"),
                "--target", ".", "--full", cwd=tmp66)
            inbox66 = os.path.join(tmp66, "docs", "70-过程", "问题收件箱.md")
            base66 = read(inbox66)

            def row66(iid, to, state="确立", date="2026-11-02"):
                ev = "确立：自测" if state == "确立" else f"{state}：自测｜T4.7.1"
                return ("| **%s** | %s | 自测 | 债 | 可关闭 | 甲 | 乙 | %s | %s | %s | — | %s |"
                        % (iid, date, state, ev, to, date))

            def with_rows(*rows):
                """把模板的 ISS-001 行换成给定行（模板只有这一行）。"""
                out, done = [], False
                for ln in base66.splitlines():
                    if ln.startswith("| **ISS-001** |") and not done:
                        out.extend(rows)
                        done = True
                        continue
                    out.append(ln)
                return "\n".join(out) + "\n"

            write(inbox66, with_rows(row66("ISS-001", "须先 ISS-002"), row66("ISS-002", "—")))
            c, out = run("devlog.py", "check", cwd=tmp66)
            check("须先 未关闭 + 本行确立 → 0 error", c == 0, out[-300:])

            write(inbox66, with_rows(row66("ISS-001", "须先 ISS-999")))
            c, out = run("devlog.py", "check", cwd=tmp66)
            check("须先 指向不存在 → D11", c == 1 and "[D11]" in out, out[-300:])

            write(inbox66, with_rows(row66("ISS-001", "源自 ISS-001")))
            c, out = run("devlog.py", "check", cwd=tmp66)
            check("指向自己 → D11", c == 1 and "[D11]" in out, out[-300:])

            write(inbox66, with_rows(row66("ISS-001", "须先 ISS-002"),
                                     row66("ISS-002", "须先 ISS-001")))
            c, out = run("devlog.py", "check", cwd=tmp66)
            check("须先 成环 → D12", c == 1 and "[D12]" in out, out[-300:])

            write(inbox66, with_rows(
                row66("ISS-001", "须先 ISS-002", state="实施中"),
                row66("ISS-002", "—")))
            c, out = run("devlog.py", "check", cwd=tmp66)
            check("被未关闭的须先挡住却实施中 → D13", c == 1 and "[D13]" in out, out[-300:])

            txt66 = with_rows(row66("ISS-002", "—"))
            txt66 = txt66.replace("| — | — | — | — |",
                                  "| ISS-001 | 2026-11-01 | 已修：自测；须先 ISS-002 | 2026-11-02 |", 1)
            write(inbox66, txt66)
            c, out = run("devlog.py", "check", cwd=tmp66)
            check("根因未关却把表象关掉 → D13", c == 1 and "[D13]" in out, out[-300:])

            write(inbox66, with_rows(
                row66("ISS-001", "源自 ISS-002", date="2026-11-01"),
                row66("ISS-002", "—", date="2026-11-02")))
            c, out = run("devlog.py", "check", cwd=tmp66)
            check("源自 时间倒挂 → D14", c == 1 and "[D14]" in out, out[-300:])

            txt66 = with_rows(row66("ISS-001", "须先 ISS-002"))
            txt66 = txt66.replace("| — | — | — | — |",
                                  "| ISS-002 | 2026-11-01 | 已修：自测 | 2026-11-02 |", 1)
            write(inbox66, txt66)
            c, out = run("devlog.py", "check", cwd=tmp66)
            check("须先 已闭环 → W13 唤醒", c == 0 and "[W13]" in out, out[-300:])
        finally:
            shutil.rmtree(tmp66, ignore_errors=True)

        # ---------------------------------------------------------------- 67
        print("\n67. 链路：串起 ≥2 个功能点与接缝（P20 / REQ-039–041）")
        tmp67 = tempfile.mkdtemp(prefix="ddd-selftest67-")
        try:
            run(os.path.join(SKILL, "scripts", "doc_init.py"),
                "--target", ".", "--full", cwd=tmp67)
            card67 = os.path.join(tmp67, "docs", "00-门面", "方向卡.md")
            base67 = read(card67)

            def chain67(f="F-001、F-002",
                        seam="注册成功后回填哪些字段；记录保存失败时重试把用户带回哪一步",
                        acc="注册 → 建记录 → 保存失败重试（@2026-12-31 复核）",
                        walk="—（未走通）", concl="—", ev="—"):
                return (f"| **L1** | 注册成功 | 建出第一条记录 | {f} | {seam} "
                        f"| {acc} | {walk} | {concl} | {ev} |")

            def with_chain67(row):
                out_lines, done = [], False
                for ln in base67.splitlines():
                    if ln.startswith("| **L1** |") and not done:
                        out_lines.append(row)
                        done = True
                        continue
                    out_lines.append(ln)
                return "\n".join(out_lines) + "\n"

            c, out = run("plan.py", "check", cwd=tmp67)
            check("模板链路：串起 2 个 F、五格齐 → 0 error",
                  c == 0 and "[P20]" not in out, out[-400:])

            write(card67, with_chain67(chain67(f="F-001")))
            c, out = run("plan.py", "check", cwd=tmp67)
            check("只涉及 1 个功能点 → P20",
                  c == 1 and "[P20]" in out and "2 个 F" in out, out[-400:])

            write(card67, with_chain67(chain67(f="F-001、F-999")))
            c, out = run("plan.py", "check", cwd=tmp67)
            check("涉及不存在的 F-999 → P20",
                  c == 1 and "[P20]" in out and "F-999" in out, out[-400:])

            write(card67, with_chain67(chain67(seam="—")))
            c, out = run("plan.py", "check", cwd=tmp67)
            check("关键接缝为空 → P20 指名「关键接缝」",
                  c == 1 and "[P20]" in out and "关键接缝" in out, out[-400:])

            write(card67, with_chain67(chain67(acc="注册 → 建记录 → 保存失败重试")))
            c, out = run("plan.py", "check", cwd=tmp67)
            check("走通验收缺 @复核日 → P20",
                  c == 1 and "[P20]" in out and "@" in out, out[-400:])

            write(card67, with_chain67(chain67(walk="2026-11-08")))
            c, out = run("plan.py", "check", cwd=tmp67)
            check("记了走通却缺结论与证据 → P20 各一条",
                  c == 1 and out.count("[P20]") == 2, out[-400:])
            c, out = run("devlog.py", "brief", cwd=tmp67)
            check("走通但缺结论/证据 → brief 计 1/1 且标「形式待修：L1」（ISS-105）",
                  c == 0 and "链路覆盖：1/1" in out and "形式待修：L1" in out, out[-500:])

            write(card67, with_chain67(chain67(walk="2026-11-08", concl="走通：自测", ev="第 67 组")))
            c, out = run("plan.py", "check", cwd=tmp67)
            check("走通 + 结论 + 证据 → 0 error",
                  c == 0 and "[P20]" not in out, out[-400:])

            c, out = run("devlog.py", "brief", cwd=tmp67)
            check("brief 出「链路覆盖：1/1」", c == 0 and "链路覆盖：1/1" in out, out[-500:])
            check("形式合格 → brief 不出「形式待修」", "形式待修" not in out, out[-500:])

            # ISS-105 核心场景：只涉及 1 个 F 但记了走通——plan.py check 判 P20 红，
            # brief 不再把它干干净净算进覆盖：计数照旧（1/1），单列「形式待修」，
            # 退出码 0（brief 只读不判语义）。两条命令对同一张表同红同绿。
            write(card67, with_chain67(chain67(f="F-001", walk="2026-11-08",
                                               concl="走通：自测", ev="第 67 组")))
            c, out = run("plan.py", "check", cwd=tmp67)
            check("1 个 F 走通 → plan 仍红（口径唯一）",
                  c == 1 and "[P20]" in out and "2 个 F" in out, out[-400:])
            c, out = run("devlog.py", "brief", cwd=tmp67)
            check("1 个 F 走通 → brief 计 1/1 且同标「形式待修：L1」（ISS-105 同红同绿）",
                  c == 0 and "链路覆盖：1/1" in out and "形式待修：L1" in out, out[-500:])

            write(card67, with_chain67(chain67()))
            c, out = run("devlog.py", "brief", cwd=tmp67)
            check("未走通 → 变 0/1 并列「接缝待验：L1」",
                  c == 0 and "链路覆盖：0/1" in out and "接缝待验：L1" in out, out[-500:])

            write(card67, base67.split("## 链路")[0])
            c, out = run("plan.py", "check", cwd=tmp67)
            check("缺链路表 → 不报 P20（棘轮）", c == 0 and "[P20]" not in out, out[-400:])
            c, out = run("devlog.py", "brief", cwd=tmp67)
            check("缺链路表 → brief 不报错、不出链路行",
                  c == 0 and "链路覆盖" not in out, out[-500:])
        finally:
            shutil.rmtree(tmp67, ignore_errors=True)

        # ---------------------------------------------------------------- 68
        print("\n68. 回复档位：默认强 / 可切换 / 非法值不落盘（REQ-042）")
        tmp68 = tempfile.mkdtemp(prefix="ddd-selftest68-")
        try:
            run(os.path.join(SKILL, "scripts", "doc_init.py"),
                "--target", ".", "--full", cwd=tmp68)
            tier68 = os.path.join(tmp68, ".dd", "reply-tier")

            c, out = run("devlog.py", "reply-tier", cwd=tmp68)
            check("无文件 → 默认「强」", c == 0 and "强" in out and "默认" in out, out[-300:])

            c, out = run("devlog.py", "brief", cwd=tmp68)
            check("brief 显示当前档位", c == 0 and "回复档位：强（默认）" in out, out[-300:])

            c, out = run("devlog.py", "reply-tier", "--set", "标准", cwd=tmp68)
            check("--set 标准 → 写入并生效",
                  c == 0 and os.path.exists(tier68) and read(tier68).strip() == "标准",
                  out[-300:])

            c, out = run("devlog.py", "reply-tier", "--set", "超强", cwd=tmp68)
            check("非法档位 → exit 1 且不写",
                  c == 1 and read(tier68).strip() == "标准", out[-300:])

            write(tier68, "乱写\n")
            c, out = run("devlog.py", "reply-tier", cwd=tmp68)
            check("文件值非法 → 回落「强」并提示",
                  c == 0 and "强" in out and "非法" in out, out[-300:])

            c, out = run("devlog.py", "brief", cwd=tmp68)
            check("brief 在回落后仍显示强",
                  c == 0 and "回复档位：强（值非法" in out, out[-300:])
        finally:
            shutil.rmtree(tmp68, ignore_errors=True)

        # ---------------------------------------------------------------- 69
        print("\n69. 真机验收台账：开单 / 记录 / 形式校验（V1–V6）")
        tmp69 = tempfile.mkdtemp(prefix="ddd-selftest69-")
        try:
            run(os.path.join(SKILL, "scripts", "doc_init.py"),
                "--target", ".", "--full", cwd=tmp69)
            rv69 = os.path.join(tmp69, "docs", "70-过程", "真机验收台账.md")
            check("doc_init 铺出真机验收台账", os.path.exists(rv69), rv69)
            c, out = run("devlog.py", "check", cwd=tmp69)
            check("模板示例行首跑 0 error", c == 0 and "[V" not in out, out[-400:])

            c, out = run("devlog.py", "rv", "new", "--object", "F-001 / W1.1",
                         "--kind", "场景", "--threshold", "2",
                         "--why", "只有真用两个场景才知道行不行",
                         "--review", "2027-01-01", cwd=tmp69)
            check("开单分配下一个编号", c == 0 and "RV-002" in out, out[-300:])

            c, out = run("devlog.py", "rv", "add", "RV-002", "--scene", "首次使用",
                         "--observed", "没出事", cwd=tmp69)
            check("第一条记录：不同场景 1/2", c == 0 and "1/2" in out, out[-300:])

            c, out = run("devlog.py", "rv", "add", "RV-002", "--scene", "首次使用",
                         "--observed", "还是没事", cwd=tmp69)
            check("同一场景不重复计数", c == 0 and "1/2" in out, out[-300:])

            c, out = run("devlog.py", "rv", "add", "RV-002", "--scene", "换个入口",
                         "--observed", "也顺", cwd=tmp69)
            check("到门槛会提示拍板", c == 0 and "到门槛" in out, out[-300:])

            before69 = read(rv69)
            c, out = run("devlog.py", "rv", "add", "RV-002", "--observed", "缺场景",
                         cwd=tmp69)
            check("add 缺 --scene → exit 1 且零写入",
                  c == 1 and read(rv69) == before69, out[-300:])

            write(rv69, read(rv69).replace("场景:2", "随便写", 1))
            c, out = run("devlog.py", "check", cwd=tmp69)
            check("判据格式坏 → V2", c == 1 and "[V2]" in out, out[-300:])

            write(rv69, read(rv69).replace("随便写", "场景:2", 1)
                  .replace("| 观察中 |", "| 看看 |", 1))
            c, out = run("devlog.py", "check", cwd=tmp69)
            check("状态词非法 → V3", c == 1 and "[V3]" in out, out[-300:])

            write(rv69, read(rv69).replace("| 看看 |", "| 已定论 |", 1))
            c, out = run("devlog.py", "check", cwd=tmp69)
            check("已定论却没有合法出口 → V4", c == 1 and "[V4]" in out, out[-300:])

            write(rv69, read(rv69).replace("| RV-002 |", "| RV-009 |", 1))
            c, out = run("devlog.py", "check", cwd=tmp69)
            check("观察记录指向不存在 → V5", c == 1 and "[V5]" in out, out[-300:])

            write(rv69, read(rv69).replace("| RV-009 |", "| RV-002 |", 1)
                  .replace("| @2027-01-01 |", "| 元旦 |", 1))
            c, out = run("devlog.py", "check", cwd=tmp69)
            check("回看日格式坏 → V6", c == 1 and "[V6]" in out, out[-300:])
        finally:
            shutil.rmtree(tmp69, ignore_errors=True)

        # ---------------------------------------------------------------- 70
        print("\n70. 定期减法：brief 数场次，§3.10 填了才复位（SKILL 硬规则 16）")
        tmp70 = tempfile.mkdtemp(prefix="ddd-selftest70-")
        try:
            run(os.path.join(SKILL, "scripts", "doc_init.py"),
                "--target", ".", "--full", cwd=tmp70)
            tpl70 = os.path.join(tmp70, "docs", "70-过程", "会话档案模板.md")
            check("模板含 §3.10 本轮减法", "### 3.10 本轮减法" in read(tpl70))

            c, out = run("devlog.py", "brief", cwd=tmp70)
            check("空项目：距上次 0 场、不报到点",
                  c == 0 and "减法：距上次 0 场 / 4" in out, out[-300:])

            for i in range(4):
                run("devlog.py", "new", "--title", f"第{i + 1}场", "--scope", "自测",
                    cwd=tmp70)
            c, out = run("devlog.py", "brief", cwd=tmp70)
            check("满 4 场报到点",
                  c == 0 and "减法：距上次 4 场" in out and "到点了" in out, out[-400:])

            sess70 = os.path.join(tmp70, "docs", "70-过程", "会话")
            last70 = sorted(os.listdir(sess70))[-1]
            last70 = os.path.join(sess70, last70)
            write(last70, read(last70) + "\n### 3.10 本轮减法（每 4 场一次）\n\n"
                  "| 对象 | 判据（哪条不成立 / 多久没用） | 结论 | 依据 |\n"
                  "|---|---|---|---|\n| | | 保持 / 合并 / 降为 reference / 删除 | |\n")
            c, out = run("devlog.py", "brief", cwd=tmp70)
            check("只有空占位行不算做过减法",
                  c == 0 and "减法：距上次 4 场" in out, out[-400:])

            write(last70, read(last70).replace(
                "| | | 保持 / 合并 / 降为 reference / 删除 | |",
                "| 硬规则 16 | 本轮首次建立，还没用过 | 保持 | — |"))
            c, out = run("devlog.py", "brief", cwd=tmp70)
            check("填了一行就复位到 0 场",
                  c == 0 and "减法：距上次 0 场 / 4" in out, out[-400:])

            c, out = run("devlog.py", "brief", "--json", cwd=tmp70)
            check("JSON 带 prune 状态（since / every / due）",
                  '"due": false' in out and '"every": 4' in out, out[-400:])
        finally:
            shutil.rmtree(tmp70, ignore_errors=True)

        # ---------------------------------------------------------------- 71
        print("\n71. 只读漏步检查：devlog.py flow 聚合本场欠项（REQ-055）")
        tmp71 = tempfile.mkdtemp(prefix="ddd-selftest71-")
        try:
            run(os.path.join(SKILL, "scripts", "doc_init.py"),
                "--target", ".", "--full", cwd=tmp71)
            docs71 = os.path.join(tmp71, "docs")

            c, out = run("devlog.py", "flow", cwd=tmp71)
            check("无档案：提示先 new 且 exit 0",
                  c == 0 and "devlog.py new" in out, out[-400:])

            run("devlog.py", "new", "--title", "漏步检查", "--scope", "自测", cwd=tmp71)
            sess71 = os.path.join(docs71, "70-过程", "会话")
            f71 = os.path.join(sess71, sorted(os.listdir(sess71))[-1])

            c, out = run("devlog.py", "flow", cwd=tmp71)
            check("模板档案：指出 §7 缺锚点",
                  c == 0 and "§7" in out and "锚点" in out, out[-400:])

            def snap71():
                d = {}
                for base, _, files in os.walk(docs71):
                    for f in files:
                        p = os.path.join(base, f)
                        with open(p, "rb") as fh:
                            d[p] = hashlib.sha256(fh.read()).hexdigest()
                return d

            before71 = snap71()
            c, out = run("devlog.py", "flow", cwd=tmp71)
            after71 = snap71()
            check("flow 只读：跑前跑后文档字节不变",
                  c == 0 and before71 == after71, "flow 改动了文件")

            anchor71 = re.sub(r"(?m)^- \*\*下一步\*\*[^\n]*$",
                              "- **下一步**：T1.1.1", read(f71), count=1)
            write(f71, anchor71)
            c, out = run("devlog.py", "flow", cwd=tmp71)
            check("锚点齐了：改报 §3.7 未填",
                  c == 0 and "§3.7" in out and "未填" in out, out[-400:])

            write(f71, read(f71).replace(
                "| | 目标 / 愿景 / 功能 / 需求 | | 本档 §2 | "
                "vision / D-n / REQ-nnn / F-nnn / 新建 | 待裁 / 已落位：<编号> / 丢弃 |",
                "| 1 | 需求 | 想要一个遵循技能的 agent | 本档 §2 | 新建 | 待裁 |", 1))
            c, out = run("devlog.py", "flow", cwd=tmp71)
            check("§3.7 填了就不再提醒",
                  c == 0 and "§3.7 想法候选：已填" in out, out[-400:])

            run("devlog.py", "ask", "要不要拆任务？", "--if", "计划只有一个任务",
                cwd=tmp71)
            c, out = run("devlog.py", "flow", cwd=tmp71)
            check("有待分诊 → 指出先分诊",
                  c == 0 and "待分诊" in out and "open 1" in out, out[-400:])

            c, out = run("devlog.py", "flow", "--json", cwd=tmp71)
            data71 = json.loads(out[out.index("{"):out.rindex("}") + 1])
            check("--json 给同一份数据（含 next_action）",
                  c == 0 and data71.get("next_action")
                  and data71.get("awaiting", {}).get("open") == 1, out[-400:])

            c, out = run("devlog.py", "flow", "--seen", "3", cwd=tmp71)
            check("--seen 3 而 §2 一行没落 → 报漏记",
                  c == 0 and "漏记" in out, out[-400:])

            c, out = run("devlog.py", "flow", "--seen", "0", cwd=tmp71)
            check("--seen 0 → 不报漏记", c == 0 and "可能漏记" not in out, out[-400:])
        finally:
            shutil.rmtree(tmp71, ignore_errors=True)

        # ---------------------------------------------------------------- 72
        print("\n72. 收尾有痕：five-run 与收尾五连跑同序、失败非零、留记录（REQ-057）")
        tmp72 = tempfile.mkdtemp(prefix="ddd-selftest72-")
        try:
            run(os.path.join(SKILL, "scripts", "doc_init.py"), "--target", ".", cwd=tmp72)
            shutil.copy(os.path.join(SKILL, "scripts", "observe.py"),
                        os.path.join(tmp72, "scripts", "observe.py"))
            canonical72 = ["devlog.check", "devlog.index", "plan.check",
                           "plan.index", "doc_check"]
            runs72 = os.path.join(tmp72, ".dd", "observe", "runs")

            def record72(out_text):
                m = re.search(r"run_id=(\S+)", out_text)
                if not m:
                    return None, []
                path = os.path.join(runs72, m.group(1) + ".jsonl")
                if not os.path.isfile(path):
                    return m.group(1), []
                recs = [json.loads(line) for line in read(path).splitlines() if line.strip()]
                return m.group(1), recs

            c, out = run("observe.py", "five-run", cwd=tmp72)
            rid72, recs72 = record72(out)
            check("five-run 干净骨架 5/5 且 exit 0", c == 0 and "5/5" in out, out[-400:])
            check("five-run 按收尾口径同序（doc_check 最后）",
                  [r.get("component") for r in recs72] == canonical72,
                  f"{rid72}: {[r.get('component') for r in recs72]}")

            write(os.path.join(tmp72, "docs", "00-门面", "bad.md"),
                  "# 坏档\n\n没有 front-matter。\n")
            c, out = run("observe.py", "five-run", cwd=tmp72)
            rid72b, recs72b = record72(out)
            check("任一步失败 → exit 1 且打印失败步",
                  c == 1 and "doc_check FAIL" in out, out[-400:])
            check("失败时仍按同序记录五步",
                  [r.get("component") for r in recs72b] == canonical72,
                  f"{rid72b}: {[r.get('component') for r in recs72b]}")
            check("失败落在最后一步 doc_check",
                  bool(recs72b) and recs72b[-1].get("component") == "doc_check"
                  and recs72b[-1].get("actual", {}).get("exit_code") == 1,
                  json.dumps(recs72b[-1] if recs72b else {}, ensure_ascii=False)[:300])
        finally:
            shutil.rmtree(tmp72, ignore_errors=True)

        # ---------------------------------------------------------------- 73
        print("\n73. 档案引用运行记录：S15 存在性 / W14 提醒（T13.3.2）")
        tmp73 = tempfile.mkdtemp(prefix="ddd-selftest73-")
        try:
            run(os.path.join(SKILL, "scripts", "doc_init.py"), "--target", ".", cwd=tmp73)
            run("devlog.py", "new", "--title", "引用运行记录", "--scope", "自测", cwd=tmp73)
            sess73 = os.path.join(tmp73, "docs", "70-过程", "会话")
            f73 = os.path.join(sess73, sorted(os.listdir(sess73))[-1])
            runs73 = os.path.join(tmp73, ".dd", "observe", "runs")
            os.makedirs(runs73, exist_ok=True)
            rid73 = "r-20260101-000000-abcdef"
            write(os.path.join(runs73, rid73 + ".jsonl"), "{}\n")

            with_id = read(f73).replace(
                "## 6. 本次产出\n",
                "## 6. 本次产出\n\n运行记录：" + rid73 + "\n", 1)
            write(f73, with_id)
            c, out = run("devlog.py", "check", cwd=tmp73)
            check("§6 引用的运行记录存在 → 无 S15 / W14",
                  c == 0 and "S15" not in out and "W14" not in out, out[-400:])

            write(f73, with_id.replace(rid73, "r-20260101-000000-badbad"))
            c, out = run("devlog.py", "check", cwd=tmp73)
            check("引用不存在的 run id → S15 且 exit 1",
                  c == 1 and "S15" in out, out[-400:])

            write(f73, with_id.replace("\n运行记录：" + rid73 + "\n", "\n"))
            c, out = run("devlog.py", "check", cwd=tmp73)
            check("最新一篇没写 run id → W14 提醒、不阻断",
                  c == 0 and "W14" in out and "S15" not in out, out[-400:])

            write(f73, read(f73).replace(
                "## 6. 本次产出\n", "## 6. 本次产出\n\n运行记录：无（分开跑）\n", 1))
            c, out = run("devlog.py", "check", cwd=tmp73)
            check("写「无（分开跑）」→ 不提醒",
                  c == 0 and "W14" not in out, out[-400:])

            run("devlog.py", "new", "--title", "更晚一篇", "--scope", "自测", cwd=tmp73)
            c, out = run("devlog.py", "check", cwd=tmp73)
            check("旧档没写 run id 不追溯（W14 只出现一次）",
                  c == 0 and out.count("[W14]") == 1, out[-500:])

            shutil.rmtree(os.path.join(tmp73, ".dd"), ignore_errors=True)
            c, out = run("devlog.py", "check", cwd=tmp73)
            check("没有记录库（新检出）→ 跳过 S15 / W14",
                  c == 0 and "S15" not in out and "W14" not in out, out[-400:])
        finally:
            shutil.rmtree(tmp73, ignore_errors=True)

        # ---------------------------------------------------------------- 74
        print("\n第 74 组：发版一条命令（release.py）")
        rel = os.path.join(SKILL, "release.py")
        if not os.path.exists(rel):
            print("  SKIP  这里没有 release.py（维护者工具，不进包；包内跑不到它）")
        else:
            def sha_tree(base):
                h = hashlib.sha256()
                for cur, dirs, names in os.walk(base):
                    dirs.sort()
                    for n in sorted(names):
                        p = os.path.join(cur, n)
                        h.update(os.path.relpath(p, base).replace("\\", "/").encode("utf-8"))
                        with open(p, "rb") as fh:
                            h.update(fh.read())
                return h.hexdigest()

            def run_release(*args):
                env = dict(os.environ, PYTHONIOENCODING="utf-8")
                p = subprocess.run([PY, rel, *args], cwd=SKILL, capture_output=True,
                                   text=True, encoding="utf-8", errors="replace",
                                   env=env, timeout=120)
                return p.returncode, (p.stdout or "") + (p.stderr or "")

            before = sha_tree(os.path.join(SKILL, "docs"))
            c, out = run_release("--dry-run")
            after = sha_tree(os.path.join(SKILL, "docs"))
            check("--dry-run 零写入（docs/ 字节不变）", before == after,
                  "docs/ 被改写了——只读命令不该落盘")
            check("--dry-run 给出预检 / 步骤 / 目标三块",
                  "预检" in out and "步骤" in out and "目标" in out, out[-300:])
            clean_tree = "包内改动已提交" in out

            c, out = run_release("--help")
            check("--help 写明不改版本、不提交、不推送",
                  c == 0 and "不提交" in out, out[-300:])
            c, out = run_release("--dry-run", "--jobs", "0")
            check("--jobs 0 → exit 2（参数问题，不是发版失败）", c == 2, f"exit {c}")

            probe = os.path.join(SKILL, "scripts", "_release_dirty_probe.py")
            try:
                write(probe, "# 只为一件事：让包内文件变脏\n")
                c, out = run_release("--dry-run")
                check("包内文件未提交 → 第一步就拒并说「先提交」",
                      c == 1 and "先提交" in out, out[-300:])
                os.remove(probe)
                if clean_tree:
                    c, out = run_release("--dry-run")
                    check("去掉脏文件 → 预检恢复通过", c == 0 and "包内改动已提交" in out,
                          out[-300:])
                else:
                    print("  SKIP  工作区本身有未提交的包内改动，跳过「干净态」断言")
            finally:
                if os.path.exists(probe):
                    os.remove(probe)

    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    total = len(PASS) + len(FAIL)
    print(f"\n{'=' * 52}")
    print(f"通过 {len(PASS)}/{total}")
    if FAIL:
        print("失败项：")
        for f in FAIL:
            print(f"  - {f}")
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(main())
