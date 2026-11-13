#!/usr/bin/env python3
"""一条命令发版：包内改动已提交之后的打包、验包、装 6 端与逐端核对。

**这只是编排，不是第二份判据。** 打包与验包的判据在 `build.py`，装机的判据在
`install.py`，本脚本一行都不重写它俩；它负责的是「谁先谁后」和「失败就停」。

它**不做**这些事：改版本号、改 CHANGELOG、`git commit`、`git push`、打 tag、发 Release。
那些是人的决定（见 `CONTRIBUTING.md`「发版与回滚」）。

用法：
    python release.py --dry-run        # 只打印计划与预检结论，零写入
    python release.py                  # 全链路：预检 → 双自测并行 → 验包 → 装 6 端
    python release.py --skip-install   # 只到验包（只想看看产物时）
    python release.py --jobs 1         # 两个自测串行跑（排障时看完整输出）

退出码：0 全绿；1 某一步失败（停在原地，`dist/` 保持上一版）；2 参数或环境问题。
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
TARGETS_FILE = os.path.join(ROOT, "install-targets.json")
CHANGELOG = os.path.join(ROOT, "CHANGELOG.md")
VERSION_FILE = os.path.join(ROOT, "VERSION")

ERRORS: list = []


def read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8-sig") as fh:
        return fh.read()


def ok(msg: str) -> None:
    print(f"[ok] {msg}")


def warn(msg: str) -> None:
    print(f"[提醒] {msg}")


def bad(msg: str) -> None:
    print(f"[失败] {msg}")
    ERRORS.append(msg)


def read_version() -> str:
    if not os.path.exists(VERSION_FILE):
        return ""
    return read_text(VERSION_FILE).strip()


def changelog_section(version: str) -> bool:
    """CHANGELOG 里有没有这一版的段落——没有就说明人还没改名 / 还没改版本。"""
    if not os.path.exists(CHANGELOG):
        return False
    head = f"## {version}"
    return any(line.strip().startswith(head) for line in read_text(CHANGELOG).splitlines())


def targets() -> list:
    """按 install-targets.json 列出 (id, 名字)；读不出来就是环境问题，不猜。"""
    with open(TARGETS_FILE, "r", encoding="utf-8-sig") as fh:
        data = json.load(fh)
    out = []
    for t in data.get("targets") or []:
        if isinstance(t, dict) and t.get("id"):
            out.append((t["id"], t.get("name") or t["id"]))
    return out


def dirty_package() -> str:
    """包内文件（build.py 认定的那批）有没有未提交改动。

    判据与 `build.py --check-dist` 同源：直接借它的 INCLUDE_DIRS / ROOT_FILES，
    不在这里再抄一份文件清单（一处一个权威）。
    """
    import build  # 延迟导入：--dry-run 不执行打包，也就不需要 build 能被加载

    paths = list(build.INCLUDE_DIRS) + list(build.ROOT_FILES)
    p = subprocess.run(["git", "status", "--porcelain", "--", *paths],
                       cwd=ROOT, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if p.returncode != 0:
        return "（拿不到 git 状态：%s）" % (p.stderr or "").strip()[:200]
    return p.stdout.strip()


def precheck() -> tuple:
    """人话预检：版本、CHANGELOG 段、包内是否已提交、清单里有没有目标。"""
    print("1. 预检")
    version = read_version()
    if not version:
        bad("读不到 VERSION")
    else:
        ok(f"版本 {version}")

    if version and not changelog_section(version):
        bad(f"CHANGELOG.md 里没有「## {version}」这一段：发版第一步是把 Unreleased 改名成这个版本号")

    dirty = ""
    try:
        dirty = dirty_package()
    except Exception as exc:  # noqa: BLE001 - 预检要给人话，不要回溯
        bad(f"检查包内改动时出错：{exc}")
    if dirty:
        if dirty.startswith("（拿不到 git 状态"):
            bad(dirty)
        else:
            bad("包内文件还有未提交改动，先提交再打包：\n  "
                + dirty.replace("\n", "\n  "))
    elif not ERRORS:
        ok("包内改动已提交")

    try:
        found = targets()
    except Exception as exc:  # noqa: BLE001
        found = []
        bad(f"读不到 install-targets.json：{exc}")
    if not found:
        bad("装机清单里一个目标都没有：装到 0 端不算发版成功")
    else:
        ok(f"装机目标 {len(found)} 端：" + "、".join(n for _, n in found))
    return version, dirty, found


def dry_run(version: str, found: list, jobs: int) -> int:
    print("\n发版计划（--dry-run：只读，零写入）")
    print(f"  版本     {version or '（读不到）'}")
    print(f"  目标     {len(found)} 端：" + ("、".join(n for _, n in found) or "—"))
    print(f"  并行     {'开（源目录自测 ∥ 打包 + 解包后自测）' if jobs > 1 else '关（--jobs 1，串行）'}")
    print("  步骤     1 预检（VERSION / CHANGELOG 段 / 包内已提交 / 目标任务）")
    print("           2 体检（SKILL 点名、语法、包内混入检查，判据在 build.py）")
    print("           3 源目录自测 ∥ 打包 + 解包后自测")
    print("           4 验包（结构 / 版本 / 哈希 / 无 CRLF / 解包后自测）")
    print("           5 dist 与 HEAD 逐字节一致（与 build.py --check-dist 同一判据）")
    print("           6 装各端并逐端核对（install.py --from dist）")
    print("           7 打印产物路径 / 大小 / sha256 与「可以提交 dist」")
    print("  不写     dist/、宿主目录、VERSION、CHANGELOG；不提交、不推送、不打 tag")
    if ERRORS:
        print(f"\n预检未通过（{len(ERRORS)} 处）：先修上面这些，再跑真的那一次。")
        return 1
    print("\n预检通过：可以去掉 --dry-run 跑真的一次。")
    return 0


def run_parallel(version: str, jobs: int) -> tuple:
    """源目录自测与（打包 + 解包后自测）互不依赖：能并行就不串着等。"""
    import build

    state = {"src": False}

    def src_selftest() -> None:
        state["src"] = build.run_self_test(build.ROOT, "源目录自测")

    thread = None
    if jobs > 1:
        thread = threading.Thread(target=src_selftest, daemon=True)
        thread.start()

    tmp = build.build(version)
    pack_ok = build.verify(tmp, version)

    if thread is not None:
        thread.join()
        src_ok = bool(state["src"])
    else:
        src_ok = build.run_self_test(build.ROOT, "源目录自测")

    if not (src_ok and pack_ok):
        import shutil
        shutil.rmtree(os.path.dirname(tmp), ignore_errors=True)
        errs = []
        if not src_ok:
            errs.append("源目录自测")
        if not pack_ok:
            errs.append("打包 / 验包")
        bad("、".join(errs) + " 没过：产物未发布，dist/ 保持上一版")
        return "", False
    return tmp, True


def main() -> int:
    ap = argparse.ArgumentParser(
        description="一条命令发版（编排 build.py 与 install.py；不改版本、不提交、不推送）")
    ap.add_argument("--dry-run", action="store_true", help="只打印计划与预检结论，零写入")
    ap.add_argument("--skip-install", action="store_true", help="只到验包，不装各端")
    ap.add_argument("--jobs", type=int, default=2, help="两个自测的并行度：1 = 串行（默认 2）")
    ap.add_argument("--json", action="store_true", help="结尾多打一行机读结果")
    args = ap.parse_args()

    if args.jobs < 1:
        print("--jobs 至少是 1（1 = 串行）", file=sys.stderr)
        return 2
    if not os.path.isdir(ROOT) or not os.path.exists(VERSION_FILE):
        print(f"这里不像技能仓库根目录：{ROOT}", file=sys.stderr)
        return 2

    print(f"仓库 {ROOT}\n")
    version, _dirty, found = precheck()

    if args.dry_run:
        return dry_run(version, found, args.jobs)
    if ERRORS:
        print(f"\n预检未通过（{len(ERRORS)} 处），未打包、未装任何宿主。")
        return 1

    import build  # 真跑才需要（--dry-run 只读）

    print("\n2. 体检")
    build.preflight()
    if build.ERRORS:
        bad(f"体检 {len(build.ERRORS)} 处未过：未打包、未装任何宿主")
        return 1

    print("\n3. 自测与打包" + ("（并行）" if args.jobs > 1 else "（串行）"))
    tmp, good = run_parallel(version, args.jobs)
    if not good:
        print(f"\n失败（{len(ERRORS)} 处）：dist/ 与各宿主都没有动。")
        return 1

    artifact = ""
    try:
        artifact = build.publish(tmp, version, os.path.join(ROOT, "dist"))
    finally:
        import shutil
        shutil.rmtree(os.path.dirname(tmp), ignore_errors=True)

    print("\n5. dist 与 HEAD 逐字节")
    if build.check_dist(version) != 0:
        bad("dist 与 HEAD 不一致：产物已写，但这一版说不清对应哪个提交")
        return 1

    if args.skip_install:
        warn("--skip-install：各宿主没有动")
    else:
        print("\n6. 装各端并逐端核对")
        p = subprocess.run([PY, os.path.join(ROOT, "install.py"), "--from", "dist"],
                           cwd=ROOT, text=True, encoding="utf-8", errors="replace")
        if p.returncode != 0:
            bad("装机没通过：dist/ 已写，宿主可能半新半旧——修好后重跑本命令（幂等）")
            return 1

    size = os.path.getsize(artifact)
    with open(artifact, "rb") as fh:
        import hashlib
        digest = hashlib.sha256(fh.read()).hexdigest()

    print("\n" + "=" * 56)
    print(f"版本   {version}")
    print(f"产物   {artifact}")
    print(f"大小   {size / 1024:.1f} KB")
    print(f"sha256 {digest}")
    if args.skip_install:
        print("宿主   未动（--skip-install）")
    else:
        print(f"宿主   {len(found)} 端已装并逐端核对（明细见上）")
    print("\n下一步（由人做）：")
    print(f"  git add dist && git commit -m \"release: {version} 产物（{len(found)} 端已装）\"")
    print("  git push")
    if args.json:
        print(json.dumps({"version": version, "artifact": artifact, "size": size,
                          "sha256": digest, "targets": [t[0] for t in found],
                          "installed": not args.skip_install}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
