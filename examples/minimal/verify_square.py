"""极简示例项目的唯一实现：把输入的数平方后打印。

它存在的目的不是当库用，而是给 `examples/minimal` 一个**真能跑**的验收入口：
`python verify_square.py 7` → 输出 49、退出码 0；`--bad` 用于演示失败路径。
"""

import sys


def square(n):
    return n * n


def main(argv):
    if len(argv) != 1 or not argv[0].lstrip("-").isdigit():
        print("用法：python verify_square.py <整数>")
        return 2
    n = int(argv[0])
    print(square(n))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
