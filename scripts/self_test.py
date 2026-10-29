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
        for script, arg in (("doc_check.py", None), ("devlog.py", "check"), ("plan.py", "check")):
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
