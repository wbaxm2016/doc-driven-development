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
| 文档 / 错字 / 翻译 | `docs/`、`README.md`、`README.en.md` | 中英两版同改（规则见 `AGENTS.md`）；改完跑 `python scripts/doc_check.py` |

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

只改 `docs/` / `README.md` / `README.en.md` / `CHANGELOG.md` 时，至少跑：

```bash
python scripts/doc_check.py      # 全库字段与链接
```

## 提交与 PR

一次提交只做一件事；提交前缀：

| 前缀 | 用于 |
|---|---|
| `feat(check):` / `fix(check):` | 改 `doc_check` / `devlog` / `plan` / `verify` 或码表 |
| `docs:` | 只改 `docs/`、`README.md` 或 `README.en.md` |
| `release:` | 改 `VERSION`、`CHANGELOG.md`、`dist/` |
| `ci:` | 只改 `.github/` |

- PR 描述里写清：**改了什么 / 为什么 / 怎么验证的**（贴命令与结果）。
- CI 必须绿：Python 3.8 与 3.12 双版本、契约 verify、可重复构建（两次打包 sha256 相同）。
- 大改（新层、新状态词、改公开契约）先开 issue 对齐，再动手。

## 发版与回滚

**发版不由 PR 作者做。** 包内文件（`scripts/`、`references/`、`assets/`、`SKILL.md`、`VERSION`、`.skill-metadata.yaml`）变了，合并后由维护者统一打包、按 `install-targets.json` 装到全部启用目标（当前 6 端）、提交 `dist/`；PR 里不要改 `VERSION` 或 `dist/`。

### 什么时候要发版

只有包内文件变了才要发版。只改 `docs/`、`README.md`、`README.en.md`、`CONTRIBUTING.md`、`CHANGELOG.md`、`build.py`、`install.py`、`install-targets.json` 不用发版，`dist/` 仍然有效。版本号规则：改规则 / 码表算 minor，破兼容算 major。

### 顺序：先提交、后打包

反过来会让产物来自脏工作区，说不清它对应哪个提交。

1. 平时改包内文件，先在 `CHANGELOG.md` 的 `## Unreleased` 里攒一笔。
2. 发版时把 `## Unreleased` 改名成 `## <新版本>`，改 `VERSION`。
3. **先提交**源码 + `VERSION` + `CHANGELOG`。
4. `python build.py`：体检 → 自测 → 打包 → 验包，写出 `dist/doc-driven-development-<版本>.skill` 与最新别名 `dist/doc-driven-development.skill`。
5. `python build.py --check-dist`：产物与 HEAD 的包内文件逐字节一致；包内文件有未提交改动会直接拒绝。
6. `python install.py --from dist`：按 `install-targets.json` 装各宿主，装完逐字节核对并打印「缺 0 / 不等 0」；各端 `.install.json` 记 `source=dist`、commit 与产物路径。
7. 提交 `dist/`，推远端。

### 发 GitHub Release

tag 不发满每个版本，只给「以后可能要回滚到这里」的打：现在是 `v2.3.2`、`v2.4.0`、`v2.4.8`、`v2.4.10`、`v2.5.3`；其余补丁只出产物、不打 tag。

发一个 release 的顺序：tag 指向包含产物与回写的提交 → 正文截 `CHANGELOG` 对应版本段（不另写摘要）→ 上传 `.skill` 资产 → 下载回核 sha256。

`gh` 没登录时不用交互登录，借 Git Credential Manager 里已有的凭据：

```bash
TOKEN=$(printf 'protocol=https\nhost=github.com\n\n' | git credential fill | awk -F= '/^password=/{print $2}')
GH_TOKEN="$TOKEN" gh release create v<版本> "dist/doc-driven-development-<版本>.skill" \
  --title "<版本>" --notes-file <从 CHANGELOG 截出来的正文>
```

release 还没发出去时改 tag 可以删了重打（`git tag -d v<版本>` → `git tag -a …` → `git push --force origin v<版本>`）；**发出去之后不要再动 tag**——资产和 digest 已经对外了。

### 回滚

- **回到某个功能之前**：功能行「完成于」记着验收时的 commit 短号——`git revert <commit>`（保留历史）或 `git checkout <commit>^ -- <文件>`（只回退文件）。
- **回到某个需求之前**：先在契约里用 `_delta` 的 `REMOVED` 作废它（编号作废不复用，`_archive/` 留档），再按功能的「完成于」回滚实现。**先改文档、再回滚代码**，否则会出现「代码回退了但需求还写着已实现」。
- **回到某个版本**：整仓回退用发版 tag（`v…`）；没有 tag 的版本（2.4.1–2.4.7、2.4.9、2.5.0–2.5.2）用对应 `release:` / `CHANGELOG` 段所指的提交。
- **只回退某个宿主**：`python install.py --from dist --artifact dist/doc-driven-development-<版本>.skill --only <id>`。

## 推送与网络

本机推送有三处隐性前提（ISS-040）：直连 `github.com:443` 可能不通（本机走 `127.0.0.1:7897`）；走代理时 schannel 后端会报 `SEC_E_NO_CREDENTIALS`，要 `http.sslBackend=openssl`；凭据由 Git Credential Manager 缓存（`credential.helper=manager` 就够——**别加 `GIT_TERMINAL_PROMPT=0`**，那会让它取不到凭据）。

判「本地领先几个提交」之前，先看远端真实 HEAD：

```bash
git ls-remote --heads origin              # 远端真实 HEAD
git fetch origin --prune && git status --short --branch
```

推不动时按顺序试，成了就停：

```bash
git push                                                          # 先直连（GCM 有缓存）
git -c http.proxy=http://127.0.0.1:7897 -c http.sslBackend=openssl push
git fetch origin && git merge --ff-only origin/main && git push   # 被 fetch first 拒时
```

`git pull` 报「Already up to date」**不等于**已经同步：拉完核对 `git rev-parse HEAD` 与 `git status --short --branch` 的 ahead/behind；对不上就退回 `git fetch && git merge --ff-only origin/main`。

## 不做什么

- 不做语义判断（条款写得对不对、撤销条件是否成立，仍要人读）；
- 不替代合规追溯工具（要审计的场景用 StrictDoc / sphinx-needs）；
- 不做外链检查（交给 lychee）。

## 许可证

贡献即同意以 [MIT](./LICENSE) 发布。
