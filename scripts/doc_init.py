#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""在一个项目里铺开文档体系（新项目初始化 / 已有项目补齐）。

用法：
    python scripts/doc_init.py --target . [--docs docs] [--full] [--ci]

做什么：
    1. 建层目录（默认 5 层：门面/契约/决策/运行/过程；--full 再加 架构/术语/规范）
    2. 落 README、开发计划、需求清单、问题收件箱、时间线、会话模板、过程层 README、ADR 示例、别名表
    3. 写 <docs>/_schema.json —— 层 / 枚举 / 段结构 / 编号规则 / 路径的唯一来源
    4. 复制 scripts/{doc_check,devlog,plan,verify}.py 到 <target>/scripts
    5. --ci 时另写 .pre-commit-config.yaml 与 .github/workflows/docs.yml

不覆盖已存在的文件（幂等，可反复跑）。
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

SKILL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TPL = os.path.join(SKILL, "assets", "templates")
CI = os.path.join(SKILL, "assets", "ci")
DEFAULTS = os.path.join(SKILL, "assets", "default-schema.json")


def load_defaults():
    """层表与枚举的默认值只来自 assets/default-schema.json，脚本里不留副本。

    ISS-067 / ISS-068：结构在脚本里再存一份，等于「加层要改脚本」，与硬规则 11 打架。
    """
    if not os.path.exists(DEFAULTS):
        sys.exit(f"缺 assets/default-schema.json：{DEFAULTS}\n"
                 "它是层表与枚举的默认来源（doc_init 不再内置副本），从发布包里拷回来再跑。")
    try:
        with open(DEFAULTS, encoding="utf-8-sig") as fh:
            data = json.load(fh)
        base = dict(data["layer_sets"]["base"])
        extra = dict(data["layer_sets"]["extra"])
        body = dict(data["schema"])
    except (OSError, ValueError, KeyError, TypeError) as exc:
        sys.exit(f"assets/default-schema.json 读不出来（{exc}）：它是结构默认值的唯一来源，"
                 f"先修它再跑 doc_init")
    return base, extra, body

BASE = os.getcwd()


def show(path):
    try:
        return os.path.relpath(path, BASE)
    except ValueError:
        return path


def write_if_absent(path, text):
    if os.path.exists(path):
        print(f"  skip (exists): {show(path)}")
        return False
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    print(f"  created: {show(path)}")
    return True


def fm(title, layer, summary, date, authority="2", status="active"):
    return (f'---\ntitle: "{title}"\nlayer: {layer}\ndomain: 全局\n'
            f'status: {status}\nauthority: {authority}\nupdated: {date}\n'
            f'summary: "{summary}"\ntags: []\n---\n\n# {title}\n\n（待填）\n')


def copy_tpl(name, dest, date, extra=None):
    src = os.path.join(TPL, name)
    if not os.path.exists(src):
        print(f"  WARN 模板缺失: {name}")
        return
    with open(src, encoding="utf-8") as fh:
        text = fh.read().replace("{{DATE}}", date)
    for k, v in (extra or {}).items():
        text = text.replace(k, v)
    write_if_absent(dest, text)


def ensure_schema(path, layers, body):
    """写层表；已存在时只**合并层**，不动其它键。

    「先默认 5 层、以后补 --full」是 SKILL.md 教的用法。若只在文件不存在时才写，
    补 --full 会变成"层目录建了、配置没更新"，三个新层的文档立刻报 E3 layer 非法。
    """
    if not os.path.exists(path):
        schema = json.loads(json.dumps(body))
        schema["layers"] = layers
        write_if_absent(path, json.dumps(schema, ensure_ascii=False, indent=2) + "\n")
        return
    try:
        with open(path, encoding="utf-8-sig") as fh:
            schema = json.load(fh)
        if not isinstance(schema, dict):
            raise ValueError("顶层不是对象")
    except (ValueError, OSError) as exc:
        print(f"  WARN 读不动 {show(path)}（{exc}）；层表未更新，请手工补 layers")
        return
    old = schema.get("layers") if isinstance(schema.get("layers"), dict) else {}
    added = {d: v for d, v in layers.items() if d not in old}
    if not added:
        print(f"  skip (layers 已齐): {show(path)}")
        return
    old.update(added)
    schema["layers"] = old
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(schema, ensure_ascii=False, indent=2) + "\n")
    print(f"  updated: {show(path)}  (+{'、'.join(added)})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", default=".")
    ap.add_argument("--docs", default="docs")
    ap.add_argument("--full", action="store_true", help="额外建 架构/术语/规范 三层")
    ap.add_argument("--ci", action="store_true", help="另写 pre-commit 与 GitHub Actions")
    args = ap.parse_args()

    root = os.path.abspath(args.target)
    global BASE
    BASE = root
    docs = os.path.join(root, args.docs)
    date = datetime.date.today().isoformat()
    base_layers, extra_layers, schema_body = load_defaults()
    layers = dict(base_layers)
    if args.full:
        layers.update(extra_layers)

    print(f"target: {root}")
    for d in layers:
        os.makedirs(os.path.join(docs, d), exist_ok=True)

    ensure_schema(os.path.join(docs, "_schema.json"), layers, schema_body)

    copy_tpl("docs-README.md", os.path.join(docs, "README.md"), date)
    copy_tpl("dev-plan.md", os.path.join(docs, "00-门面", "开发计划.md"), date)
    copy_tpl("requirements.md", os.path.join(docs, "20-契约", "requirements.md"), date)
    copy_tpl("inbox.md", os.path.join(docs, "70-过程", "问题收件箱.md"), date)
    copy_tpl("timeline.md", os.path.join(docs, "70-过程", "时间线.md"), date)
    copy_tpl("session-record.md", os.path.join(docs, "70-过程", "会话档案模板.md"), date)
    copy_tpl("process-readme.md", os.path.join(docs, "70-过程", "README.md"), date)
    copy_tpl("adr.md", os.path.join(docs, "30-决策", "adr", "ADR-001-示例决策.md"), date,
             {"{{NO}}": "001", "{{TITLE}}": "示例决策", "{{DOMAIN}}": "全局",
              "{{SLUG}}": "示例决策，可删除", "{{SUPERSEDES}}": ""})

    os.makedirs(os.path.join(docs, "70-过程", "会话"), exist_ok=True)
    os.makedirs(os.path.join(docs, "30-决策", "adr"), exist_ok=True)

    write_if_absent(os.path.join(docs, "00-门面", "vision.md"),
                    fm("产品定位", "facade", "这个产品是什么、为什么做。", date, authority="1"))
    copy_tpl("features.md", os.path.join(docs, "40-运行", "FEATURES.md"), date)
    copy_tpl("feature-check.md", os.path.join(docs, "40-运行", "功能对照.md"), date)
    copy_tpl("observability.md", os.path.join(docs, "40-运行", "可观测性.md"), date)
    copy_tpl("direction.md", os.path.join(docs, "00-门面", "方向卡.md"), date)
    copy_tpl("design.md", os.path.join(docs, "00-门面", "设计卡.md"), date)
    write_if_absent(os.path.join(docs, "30-决策", "decisions.md"),
                    fm("决策索引", "decision",
                       "ADR 的唯一入口：一文件一决策，编号只增不复用。", date, authority="1")
                    + "\n| 编号 | 日期 | 决策 | 状态 | 文件 |\n|---|---|---|---|---|\n"
                    + f"| 001 | {date} | 示例决策（可删除） | proposed "
                      f"| [ADR-001-示例决策.md](./adr/ADR-001-示例决策.md) |\n")

    if args.full:
        write_if_absent(os.path.join(docs, "10-架构", "technical-design.md"),
                        fm("技术设计", "architecture", "系统怎么搭、机制为何这样。", date))
        copy_tpl("alias-table.md", os.path.join(docs, "50-术语", "别名表.md"), date)
        write_if_absent(os.path.join(docs, "60-规范", "文档组织管理规范.md"),
                        fm("文档组织管理规范", "norm", "人怎么协作、文档怎么组织与校验。", date))

    scripts_dir = os.path.join(root, "scripts")
    os.makedirs(scripts_dir, exist_ok=True)
    for name in ("doc_check.py", "devlog.py", "plan.py", "verify.py"):
        src = os.path.join(SKILL, "scripts", name)
        with open(src, encoding="utf-8") as fh:
            write_if_absent(os.path.join(scripts_dir, name), fh.read())

    if args.ci:
        for src_name, dest in (
            ("pre-commit-config.yaml", os.path.join(root, ".pre-commit-config.yaml")),
            ("github-workflow-docs.yml", os.path.join(root, ".github", "workflows", "docs.yml")),
        ):
            src = os.path.join(CI, src_name)
            if os.path.exists(src):
                with open(src, encoding="utf-8") as fh:
                    write_if_absent(dest, fh.read())
            else:
                print(f"  WARN CI 模板缺失: {src_name}")

    print("\n完成。下一步：")
    print(f"  python scripts/doc_check.py --docs {args.docs}")
    print('  python scripts/devlog.py new --title "第一场会话"')
    print("  然后按 SKILL.md 的「日常三动作」运行。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
