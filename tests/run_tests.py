#!/usr/bin/env python3
"""
Tests for Order.

    python3 tests/run_tests.py

Three kinds:

  * programs whose measured growth curve must come out as a given class
  * a program whose printed output must match exactly
  * programs that must be refused, with a phrase from the message
"""

import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ORDER = os.path.join(ROOT, "order.py")
EXAMPLES = os.path.join(ROOT, "examples")
PYTHON = sys.executable


# Program -> (time class, space class) its measurement must report.
GROWTH = [
    ("constant.order", "O(1)", "O(1)"),
    ("binary.order", "O(log n)", "O(1)"),
    ("linear.order", "O(n)", "O(1)"),
    ("merge.order", "O(n log n)", "O(log n)"),
    ("bubble.order", "O(n^2)", "O(1)"),
    ("fib.order", "O(2^n)", "O(n)"),
]

EXACT = {
    "basics.order": """[1, 2, 3]
[2, 5, 9]
{"a": 2, "b": 1}
a,b
2
ell
true
true
HI
[0, 1, 2]
["b", "a", "c"]
3
""",
    # Trees: a node is [value, left, right], an empty tree is nothing.
    "tree_problems.order": """[1, 3, 4, 6, 7, 8, 10, 13, 14]
[8, 3, 1, 6, 4, 7, 10, 14, 13]
[8, 3, 10, 1, 6, 14, 4, 7, 13]
9
66
4
7
true
false
6
3
""",
}


def run(path):
    return subprocess.run(
        [PYTHON, ORDER, "run", path],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
    )


def main():
    passed = 0
    failed = 0

    for name, time_order, space_order in GROWTH:
        path = os.path.join(EXAMPLES, name)
        result = run(path)
        if result.returncode != 0:
            failed += 1
            print("FAIL %s: exit %d\n%s" % (name, result.returncode, result.stderr))
            continue
        wanted = ("time   grows like  " + time_order,
                  "space  grows like  " + space_order)
        missing = [w for w in wanted if w not in result.stdout]
        if missing:
            failed += 1
            print("FAIL %s: expected %r, got:" % (name, missing))
            print(result.stdout)
            continue
        passed += 1
        print("ok   %-16s time %-11s space %s"
              % (name, time_order, space_order))

    for name, expected in sorted(EXACT.items()):
        path = os.path.join(EXAMPLES, name)
        result = run(path)
        if result.returncode != 0:
            failed += 1
            print("FAIL %s: exit %d\n%s"
                  % (name, result.returncode, result.stderr))
            continue
        if result.stdout != expected:
            failed += 1
            print("FAIL %s: output did not match" % name)
            print("  expected: %r" % expected)
            print("  actual:   %r" % result.stdout)
            continue
        passed += 1
        print("ok   %-20s prints what it should" % name)

    print()

    for name, _time, _space in GROWTH:
        path = os.path.join(EXAMPLES, name)
        result = subprocess.run([PYTHON, ORDER, "check", path],
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                universal_newlines=True)
        if result.returncode != 0:
            failed += 1
            print("FAIL %s: check refused it\n%s" % (name, result.stderr))
        else:
            passed += 1
            print("ok   %-16s passes check" % name)

    print()
    print("%d passed, %d failed" % (passed, failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
