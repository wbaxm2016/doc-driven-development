---
title: "过程层：记录协议"
layer: process
domain: 协作
status: reference
authority: 4
updated: {{DATE}}
summary: "本项目过程记录的落点与惯例：档案放哪、怎么开档、收尾跑什么。协议正文见技能 references。"
tags: [过程, 记录协议, 入口]
---

# 过程层：记录协议

> 本文件是**入口**，不复写协议：一次会话一份双侧档案、用户侧 8 类、AI 侧 6 项、八维选项对比、发现即登记。
> 协议正文的唯一来源是技能里的 `references/process-recording.md`（激活技能即可读到）；
> 这里的 `status: reference` + `authority: 4` 表示**本层永不参与裁决**。

## 1. 本项目的落点

| 想知道 | 看这里 |
|---|---|
| 某场会话发生了什么 | `会话/<日期>-<序号>-<主题>.md`（结构照抄 `会话档案模板.md`） |
| 有哪些问题还没处理 | `问题收件箱.md`（`ISS-nnn` 只增不复用） |
| 按时间回看演进 | `时间线.md`（生成区，由 `scripts/devlog.py index` 重建） |

## 2. 每场会话的固定动作

```bash
python scripts/devlog.py new --title "主题" --scope "范围"   # 开场建档
python scripts/devlog.py check                               # 收尾：七段/字段/ISS 引用
python scripts/devlog.py index                               # 收尾：重建时间线
python scripts/plan.py check && python scripts/plan.py index  # 收尾：计划与排序视图
python scripts/doc_check.py                                  # 收尾：全库字段与链接
```

全部 0 error 才算收尾完成。新建档案在填完 §7 前会报 1 条 `S6 交接段过短` WARN，属正常。

## 3. 本项目要补的惯例（留空即沿用技能默认）

- 主题命名：
- 与外部工具的关系（看板 / Issues）：
- 定期人工复核项（ADR 撤销条件是否已成立、语义重复）：
