---
title: "已实现能力清单"
layer: operation
domain: 全局
status: active
authority: 2
updated: 2026-10-31
summary: "现在能做到什么；只记已验收的，不记计划。当前版本 2.2.0。"
tags: [能力, 验收]
---

# 已实现能力清单

> 只记**已验收**的能力。计划中的在 [开发计划](../00-门面/开发计划.md) 里，不写在这里。

当前版本：`VERSION` = 2.2.0（`dist/doc-driven-development-2.2.0.skill`）。下表 E18–E21、`verify.py`、契约增量、改动分级、交接锚点、开场简报、§2 落点必填、待分诊门禁与清单化安装已随 2.2.0 发版。

| 能力 | 一条判据 | 证据 |
|---|---|---|
| 铺骨架 | `doc_init.py --target . --full` 幂等，不覆盖已有文件 | 本仓库自举：14 篇、首跑 `errors=0` |
| 全库校验 | `doc_check.py` 的 E1–E21 / W1–W7（E18 判 `verify:` 缺失；E19–E21 判 delta 未合并 / 锚点冲突 / 归档不一致） | `self_test.py` 第 13、15 组 |
| 契约增量 | `_delta/` 只写增量：根目录 `proposed`（E19 阻断）、`_archive/` 是 `snapshot`；合并后归档且 `after` 仍在目标 | `self_test.py` 第 15 组 |
| 改动分级 | `SKILL.md` 硬规则 12：只改措辞 / 错字且不碰事实源＝轻档（不建档、不跑五连跑，但 `doc_check` 照跑） | `self_test.py` 第 16 组（66→72） |
| 交接锚点 | `devlog check` 要求 §7 首行「下一步：<任务编号>」，编号必须存在于计划 §5；不存在 / 写「无」但计划未完成 → `S9` | `self_test.py` 第 17 组（72→78） |
| 开场简报 | `devlog.py brief` 只读输出：上一场交接首行 + 计划未完成任务 + 收件箱 `open`/`deferred` 计数 + 最近三场 | `self_test.py` 第 18 组（78→84） |
| 用户侧落点 | `devlog check` 的 `S10`：§2 已填类型的行必须有落点，空值 / `—` / `待补` / `无` 即报；模板占位不报 | `self_test.py` 第 19 组（84→89） |
| 待分诊与门禁 | `devlog ask` 记一条要用户定的问题（不占 ISS 号）；`pending --clear` 分诊（ISS / §5 / drop / defer）；未清完 `new` 拒绝（exit 1），延期 >5 条也拒 | `self_test.py` 第 20 组（89→97） |
| 清单化安装 | `install.py` 按 `install-targets.json` 探查各宿主技能目录并安装；装完写 `MANIFEST.txt` + `.install.json`，可逐文件核对 | 本机四目标（千问办公 / DSH / 豆包 / Qoder CN）各 29 文件、0 缺失 0 不一致 |
| 缺配置不猜 | `_schema.json` 与 `_layers.json` 都缺 → `doc_check` exit 2 并给出补齐命令，不再用内置 8 层猜层表 | `self_test.py` 第 23 组 |
| 契约回检 | `verify.py` 按 `verify:` 真跑；失败/超时 exit 1，`待实现/阻塞` 行跳过并打印跳过数；`--strict` 下跳过也算失败 | `self_test.py` 第 14、23 组；CI 步骤 `.github/workflows/build.yml` |
| 会话档案 | `devlog.py new` 编号与文件名正确；七段/S5 引用/文件名前缀可判 | `self_test.py` 第 2、9 组 |
| 时间线 | `devlog.py index` 按日期倒序、链接可点 | `self_test.py` 第 5 组 |
| 计划排序 | `plan.py index` 三视角加权；改一行后 `--check` 报过时 | `self_test.py` 第 4 组 |
| 带码报错 | 三份带码脚本（`doc_check` / `devlog` / `plan`）的错误行都带 `[E/W/D/S/P]` 码；`verify.py` 用退出码 | `self_test.py` 第 3 组（`[P4]` 必带码） |
| 引用存在性 | 前置编号 P11、工作→方向 P12 会被报出 | `self_test.py` 第 10 组 |
| 存量债棘轮 | `--update-baseline` 接入，`--baseline` 只许降 | `self_test.py` 第 8 组 |
| 跨天建档 | 模板日期停在昨天时开档仍自洽（2.1.0 修复） | `self_test.py` 第 9 组 |
| 配置损坏不抛回溯 | `_schema.json` 非法时四份脚本 exit 2 + 一行说明 | `self_test.py` 第 11 组 |
| 打包与验包 | `build.py` 体检→自测→打包→验包，包内文件与源仓库逐一一致 | 2.1.0 构建：27 条目、26 个哈希吻合 |
| 按包安装 | `--skills-dir` 指定根目录，安装后按 MANIFEST 逐文件核对 | 本机安装：不符 0 / 缺失 0 / 多余 0 |
