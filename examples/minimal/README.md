# examples/minimal —— 极简模拟项目

这是一个**故意做小**的项目，用来演练本技能的一整套流程：铺骨架 → 定需求 → 写功能 → 排任务 →
建档 → 过门 → 对照 / 考核 → 收尾五连跑。它不复制 `scripts/`（脚本仍用仓库根的那一份），
所以命令都从本目录用相对路径调用。

## 它长什么样

```
examples/minimal/
├── verify_square.py          # 唯一实现：输入 n，输出 n²，退出码 0
├── README.md                 # 本文件
└── docs/                     # doc_init --full 铺出来的骨架（已填成一个小场景）
```

## 场景

- 需求 `REQ-001`：`WHEN 调用 python verify_square.py 7 THE SYSTEM SHALL 输出 49 并以 0 退出`
- 功能 `F-001`：平方计算（入口 `verify_square.py`）
- 方向 `D1` / 工作 `W1.1` / 任务 `T1.1.1`
- 一场会话档案在 `docs/70-过程/会话/` 下：带决策块、摩擦、想法候选与预审记录

## 怎么跑（在本目录下）

```bash
python ../../scripts/doc_check.py      # 文档校验，期望 errors=0
python ../../scripts/devlog.py brief   # 开场简报
python ../../scripts/devlog.py check   # 会话校验，期望 errors=0
python ../../scripts/plan.py check     # 计划校验，期望 errors=0
python ../../scripts/plan.py tree      # 方向 → 工作 → 任务
python verify_square.py 7              # 验收命令，期望输出 49
```

> **为什么脚本不复制进项目**：技能包里的 `scripts/` 是唯一权威（一处一个权威）；
> 复制一份进示例会立刻变成第二份，迟早漂移。真实项目由 `doc_init` 复制，示例故意不复制。
