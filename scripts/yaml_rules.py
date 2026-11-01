#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""SKILL.md front-matter 与 .skill-metadata.yaml 的严格 YAML 子集校验（纯标准库）。

为什么是独立模块、为什么在包里：
    这两份文件分别被 5 个宿主和平台技能卡片解析，坏 YAML 的失败都是**静默**的——
    DSH 解析失败会丢掉整个技能（2.2.8 的 `description_en: … development: dual-sided …`
    就是这么消失的：文件装上了，技能列表里却没有）；平台卡片解析失败只会退回通用问句。
    规则只能有一份：`build.py` 体检、`install.py` 装机前、随包 `self_test.py` 都引用这里，
    不在别处复制。

子集边界（故意比通用 YAML 窄，够这两份文件用）：
- 只允许空格缩进，不出现制表符；
- front-matter 只允许顶层 `key: value`；metadata 允许嵌套映射与 `- ` 序列；
- 值要么是引号字符串，要么是不含 `: ` / ` #` / 制表符的 plain 标量；
- 支持 `|` / `|-` / `>` 块标量，内容只要缩进比所属键深就当作正文。
通用 YAML 里合法、但不在子集里的写法（flow 集合、多行 plain 标量、`- key:` 空值项等）
会被报出来——这是子集，不是解析器；规则窄，但「坏包走不到宿主」这件事靠它。
"""
from __future__ import annotations

import re

_KEY = re.compile(r"^([^\s:#][^:]*?):(?:[ \t]+(.*))?$")
_BLOCK = ("|", "|-", "|+", ">", ">-", ">+")


def frontmatter_block(text: str) -> str:
    """取出 `---` 包住的第一段；没有就返回空串。"""
    m = re.match(r"^---\r?\n(.*?)\r?\n---", text, re.S)
    return m.group(1) if m else ""


def frontmatter_problems(block: str) -> list[str]:
    """front-matter 必须能被严格 YAML 解析的最小检查（只用标准库）。

    为什么需要：SKILL.md 由 5 个宿主的加载器解析，DSH 走严格 YAML——解析失败会
    **静默丢弃整个技能**。这里只接受我们实际使用的子集：顶层 `key: value`，值要么是
    引号字符串，要么是不含 `: ` / ` #` / 制表符的 plain 标量；缩进块与重复键一律报。
    """
    problems = []
    seen = set()
    for no, raw in enumerate(block.splitlines(), 1):
        line = raw.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line[0].isspace():
            problems.append(f"第 {no} 行有缩进：front-matter 只允许顶层键值")
            continue
        m = _KEY.match(line)
        if not m:
            problems.append(f"第 {no} 行不是 `key: value`：{line[:50]}")
            continue
        key, val = m.group(1).strip(), (m.group(2) or "").rstrip()
        if key in seen:
            problems.append(f"第 {no} 行键重复：{key}")
        seen.add(key)
        if not val:
            problems.append(f"第 {no} 行 {key} 的值为空")
        elif val[0] in ("'", '"'):
            if len(val) < 2 or not val.endswith(val[0]):
                problems.append(f"第 {no} 行 {key} 的引号未闭合")
        else:
            _plain(no, key, val, problems.append)
    return problems


def metadata_problems(text: str) -> list[str]:
    """`.skill-metadata.yaml` 的结构检查：缩进层级、键重复、标量形态、块标量。

    它不判断「文案写得好不好」，只保证这份文件在平台侧不会被当成坏 YAML。
    返回逐行说明；空列表＝通过。
    """
    problems = []

    def bad(no, msg):
        problems.append(f"第 {no} 行：{msg}")

    stack = [{"indent": 0, "keys": set()}]   # 每层容器的「同级键起始缩进」
    block = None                             # 块标量所属键的缩进；None＝不在块里
    pending = False                          # 上一行开了子块，下一行必须更深

    for no, raw in enumerate(text.splitlines(), 1):
        line = raw.rstrip("\r")
        if block is not None:
            if not line.strip():
                continue
            ind = len(line) - len(line.lstrip(" "))
            if ind > block:
                if "\t" in line:
                    bad(no, "块标量内容含制表符")
                continue
            block = None
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if "\t" in line:
            bad(no, "含制表符：缩进与值都只允许空格")
            continue
        ind = len(line) - len(line.lstrip(" "))
        body = line[ind:]

        if ind < stack[-1]["indent"]:
            while len(stack) > 1 and ind < stack[-1]["indent"]:
                stack.pop()
            if ind != stack[-1]["indent"]:
                bad(no, f"缩进 {ind} 对不上任何一层（当前层 {stack[-1]['indent']}）")
                continue
        elif ind > stack[-1]["indent"]:
            if not pending:
                bad(no, "缩进跳级：上一行不是空值键或块标量开头")
                continue
            stack.append({"indent": ind, "keys": set()})
        pending = False

        if body.startswith("-"):
            rest = body[1:].lstrip()
            if not rest:
                pending = True
                continue
            if rest.startswith("-"):
                bad(no, "嵌套序列不在子集内")
                continue
            m = _KEY.match(rest)
            if m:
                key = m.group(1).strip()
                val = m.group(2)
                if val is None or not val.strip():
                    bad(no, "序列项里的空值键不在子集内：把 `- key` 改成 `key:` 换行写")
                    continue
                val = val.strip()
                stack.append({"indent": ind + 2, "keys": {key}})
                _scalar(no, bad, key, val)
                if val in _BLOCK:
                    block = ind
            else:
                val = rest.strip()
                if val[0] in ("'", '"'):
                    if len(val) < 2 or val[-1] != val[0]:
                        bad(no, "序列项的引号未闭合")
                elif ": " in val or " #" in val:
                    bad(no, "序列项的 plain 值含「: 」或「 #」")
            continue

        m = _KEY.match(body)
        if not m:
            bad(no, f"不是 `key: value`：{body[:50]}")
            continue
        key = m.group(1).strip()
        val = m.group(2)
        if key in stack[-1]["keys"]:
            bad(no, f"同级键重复：{key}")
        stack[-1]["keys"].add(key)
        if val is None or not val.strip():
            pending = True
            continue
        val = val.strip()
        _scalar(no, bad, key, val)
        if val in _BLOCK:
            block = ind
    return problems


def _plain(no, key, val, add):
    if ": " in val or val.endswith(":"):
        add(f"第 {no} 行 {key} 的 plain 值含 `: `，YAML 会当成嵌套映射并失败（给值加引号）")
    if " #" in val:
        add(f"第 {no} 行 {key} 的 plain 值含 ` #`，YAML 会把后半截当注释丢掉")
    if "\t" in val:
        add(f"第 {no} 行 {key} 的 plain 值含制表符，严格 YAML 会解析失败")


def _scalar(no, bad, key, val):
    """单个标量的形态检查（引号 / plain / 块标量开头）。"""
    if val in _BLOCK:
        return
    if val[0] in ("'", '"'):
        if len(val) < 2 or val[-1] != val[0]:
            bad(no, f"{key} 的引号未闭合")
        return
    if ": " in val or val.endswith(":"):
        bad(no, f"{key} 的 plain 值含「: 」，YAML 会当成嵌套映射并失败（给值加引号）")
    if " #" in val:
        bad(no, f"{key} 的 plain 值含「 #」，YAML 会把后半截当注释丢掉")
    if val[0] in "{[&*!|>@`":
        bad(no, f"{key} 的值以 YAML 保留字符开头（{val[0]}），不在子集内")
