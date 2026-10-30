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

import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

SKILL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable
VERBOSE = "-v" in sys.argv

PASS, FAIL = [], []


def run(script, *args, cwd):
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    p = subprocess.run([PY, os.path.join("scripts", script), *args],
                       cwd=cwd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=env)
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


def codes(out):
    return set(re.findall(r"\[([EWDSP]\d+)\]", out)) | set(re.findall(r"\[([EWDSP]\d+)\]", out))


def main():
    tmp = tempfile.mkdtemp(prefix="ddd-selftest-")
    print(f"临时项目: {tmp}\n")
    try:
        # ---------------------------------------------------------------- 1
        print("1. 铺骨架后首跑全绿")
        run(os.path.join(SKILL, "scripts", "doc_init.py"), "--target", ".", "--full", cwd=tmp)
        c, out = run("doc_check.py", "--quiet", cwd=tmp)
        check("doc_init + doc_check 为 0 error", c == 0 and "errors=0" in out, out.strip()[-200:])
        check("_schema.json 已生成", os.path.exists(os.path.join(tmp, "docs", "_schema.json")))

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
        row = "| **ISS-002** | 2026-10-29 | 自测 | 风险 | 甲 | 乙 | `done` | — | — |"
        s = [ln for ln in s]
        for i, ln in enumerate(s):
            if ln.startswith("| **ISS-001**"):
                s.insert(i + 1, row)
                break
        write(inbox, "\n".join(s).replace("| — | — | — |", "| **ISS-002** | 已修 | 2026-10-29 |"))
        plan = os.path.join(tmp, "docs", "00-门面", "开发计划.md")
        write(plan, read(plan).replace(
            "| **T1.1.1** | （示例）跑通并记录 | W1.1 | 待开工 | - | 5 | 5 | 4 | 3 | 4 | 3 |",
            "| **T1.1.1** | （示例）跑通并记录 | W1.1 | 待开工 | - | 6 | 5 | 4 | 3 | 4 | 3 |"))

        _, out = run("doc_check.py", cwd=tmp)
        got = codes(out)
        check("E7 断链", "E7" in got, out[-300:])
        check("E10 ADR 缺段", "E10" in got)
        check("E5 summary 超长", "E5" in got)
        _, dout = run("devlog.py", "check", cwd=tmp)
        check("D1 收件箱编号重复", "D1" in dout, dout[-300:])
        _, pout = run("plan.py", "check", cwd=tmp)
        check("P4 分值越界（必须带码打印，供 CI grep）", "[P4]" in pout, pout[-300:])

        # ---------------------------------------------------------------- 4
        print("\n4. 生成区幂等")
        # 上一步故意留了非法分值，先修回来——plan index 在分值非法时拒绝写盘是正确行为
        write(plan, read(plan).replace(
            "| **T1.1.1** | （示例）跑通并记录 | W1.1 | 待开工 | - | 6 | 5 | 4 | 3 | 4 | 3 |",
            "| **T1.1.1** | （示例）跑通并记录 | W1.1 | 待开工 | - | 5 | 5 | 4 | 3 | 4 | 3 |"))
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
            row11 = "| **ISS-002** | 2026-10-30 | 自测 | 风险 | 甲 | 乙 | `deferred` | 未排期 | 需要时 |"
            write(inbox11, read(inbox11).replace(
                "| **ISS-001**", row11 + "\n| **ISS-001**", 1))
            c, out = run("devlog.py", "brief", cwd=tmp11)
            check("brief 给出收件箱 open / deferred 计数",
                  c == 0 and "open 1" in out and "deferred 1" in out, out[-300:])

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
