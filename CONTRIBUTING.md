# 参与开发

这个仓库是一个 Agent Skill 的源码：`SKILL.md` 给 Agent 读，`scripts/` 是校验脚本，`docs/` 是这个仓库自己的开发过程。欢迎修 bug、加检查规则、补宿主适配、改文档。

## 先跑起来

需要 Python 3.8+，只用标准库。

```bash
git clone https://github.com/wbaxm2016/doc-driven-development.git
cd doc-driven-development
python scripts/self_test.py     # 约 1 分钟；在临时目录跑，不碰你的项目
python build.py                 # 体检 → 自测 → 打包 → 验包
```

`self_test.py` 与 `build.py` 全绿，就是可以开始改的状态。

## 改哪里

| 你想改 | 改哪 | 还要动什么 |
|---|---|---|
| 一条检查规则 / 报错码 | `scripts/doc_check.py`、`devlog.py`、`plan.py`、`verify.py` | **先在 `scripts/self_test.py` 加正反例断言**，再改码表 `references/check-rules.md` 与 `SKILL.md` 的验收 |
| 初始化的目录 / 模板 | `scripts/doc_init.py`、`assets/templates/`、`docs/_schema.json` | `self_test` 里 doc_init 的首跑断言；默认 5 层与 `--full` 8 层都要绿 |
| 打包 / 安装 / 发版 | `build.py`、`install.py`、`install-targets.json` | `build.py` 验包；装到真实宿主后再核对 `MANIFEST.txt` |
| 给 Agent 的说明 / 触发词 | `SKILL.md`、`references/` | `build.py` 会核对：点名的路径必须存在、包内文件必须被提到 |
| 文档 / 错字 / 翻译 | `docs/`、`README.md` | 改完跑 `python scripts/doc_check.py` |

**加规则之前先想清楚**：这条规则判的是「会静默骗人」的失败吗？只判形式的规则也能加，但每条都要有码、要打印、要有正反例断言。没断言的规则不合并。

## 硬规则（会被 CI 与脚本检查）

1. **只用标准库，兼容 Python 3.8**——不引第三方运行时依赖（开发期也不引）。
2. **新增规则先立断言**：先写 `self_test` 的正反例，再写实现与文档。顺序反了，就会出现「文档写了、代码没实现」。
3. **一个事实一处**：同一件事只在一份文档里定义，其余引用。改结构只改 `docs/_schema.json`。
4. **不假装跑过**：找不到目录、配置坏了就 `exit 2` 并说清原因，不要回退成「0 error」。
5. **状态只被证据推进**：`已实现（未验收）` 不是 `已完成`。

## 改完怎么验

```bash
python scripts/self_test.py      # 断言（改了脚本或模板必跑）
python build.py                  # 体检 + 自测 + 打包 + 验包
python scripts/verify.py         # 按契约的 verify: 真跑（较慢，CI 会跑）
```

只改 `docs/` / `README.md` / `CHANGELOG.md` 时，至少跑：

```bash
python scripts/doc_check.py      # 全库字段与链接
```

## 提交与 PR

一次提交只做一件事；提交前缀：

| 前缀 | 用于 |
|---|---|
| `feat(check):` / `fix(check):` | 改 `doc_check` / `devlog` / `plan` / `verify` 或码表 |
| `docs:` | 只改 `docs/` 或 `README.md` |
| `release:` | 改 `VERSION`、`CHANGELOG.md`、`dist/` |
| `ci:` | 只改 `.github/` |

- PR 描述里写清：**改了什么 / 为什么 / 怎么验证的**（贴命令与结果）。
- CI 必须绿：Python 3.8 与 3.12 双版本、契约 verify、可重复构建（两次打包 sha256 相同）。
- 大改（新层、新状态词、改公开契约）先开 issue 对齐，再动手。

## 发版不由 PR 作者做

包内文件（`scripts/`、`references/`、`assets/`、`SKILL.md`、`VERSION`、`.skill-metadata.yaml`）变了，合并后由维护者按 README「发版」一节统一打包、装 5 端、提交 `dist/`。PR 里不要改 `VERSION` 或 `dist/`。

## 不做什么

- 不做语义判断（条款写得对不对、撤销条件是否成立，仍要人读）；
- 不替代合规追溯工具（要审计的场景用 StrictDoc / sphinx-needs）；
- 不做外链检查（交给 lychee）。

## 许可证

贡献即同意以 [MIT](./LICENSE) 发布。
