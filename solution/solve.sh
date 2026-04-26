#!/bin/bash
set -euo pipefail

cat > /app/evaluate.py << 'PY'
#!/usr/bin/env python3
"""Reference evaluator: exact rationals with integer arithmetic only (no fractions module)."""

from __future__ import annotations

import argparse
import json
import math
from typing import Any


def norm(num: int, den: int) -> tuple[int, int]:
    if den == 0:
        raise ZeroDivisionError("zero denominator")
    if den < 0:
        num, den = -num, -den
    if num == 0:
        return 0, 1
    g = math.gcd(abs(num), den)
    return num // g, den // g


def rat_add(n1: int, d1: int, n2: int, d2: int) -> tuple[int, int]:
    return norm(n1 * d2 + n2 * d1, d1 * d2)


def rat_sub(n1: int, d1: int, n2: int, d2: int) -> tuple[int, int]:
    return norm(n1 * d2 - n2 * d1, d1 * d2)


def rat_mul(n1: int, d1: int, n2: int, d2: int) -> tuple[int, int]:
    return norm(n1 * n2, d1 * d2)


def rat_neg(n: int, d: int) -> tuple[int, int]:
    return norm(-n, d)


def rat_inv(n: int, d: int) -> tuple[int, int]:
    if n == 0:
        raise ZeroDivisionError("inv of zero")
    return norm(d, n)


def rat_abs(n: int, d: int) -> tuple[int, int]:
    return norm(abs(n), d)


def rat_cmp(n1: int, d1: int, n2: int, d2: int) -> int:
    """-1 if n1/d1 < n2/d2, 0 if equal, 1 if greater (denominators positive)."""
    lhs = n1 * d2
    rhs = n2 * d1
    if lhs < rhs:
        return -1
    if lhs > rhs:
        return 1
    return 0


def rat_min(n1: int, d1: int, n2: int, d2: int) -> tuple[int, int]:
    if rat_cmp(n1, d1, n2, d2) <= 0:
        return norm(n1, d1)
    return norm(n2, d2)


def rat_max(n1: int, d1: int, n2: int, d2: int) -> tuple[int, int]:
    if rat_cmp(n1, d1, n2, d2) >= 0:
        return norm(n1, d1)
    return norm(n2, d2)


def rat_floor(n: int, d: int) -> tuple[int, int]:
    assert d > 0
    return norm(n // d, 1)


def rat_ceil(n: int, d: int) -> tuple[int, int]:
    nn, dd = rat_neg(n, d)
    fn, fd = rat_floor(nn, dd)
    return rat_neg(fn, fd)


class Evaluator:
    def __init__(self, nodes: dict[str, Any], root: str, vars_: dict[str, dict[str, int]]):
        self.nodes = nodes
        self.root = root
        self.vars = vars_
        self.memo: dict[str, tuple[int, int]] = {}

    def eval_node(self, nid: str) -> tuple[int, int]:
        if nid in self.memo:
            return self.memo[nid]
        n = self.nodes[nid]
        k = n["kind"]
        if k == "const":
            out = norm(int(n["num"]), int(n["den"]))
        elif k == "var":
            v = self.vars[n["name"]]
            out = norm(int(v["num"]), int(v["den"]))
        elif k == "neg":
            a, b = self.eval_node(n["child"])
            out = rat_neg(a, b)
        elif k == "inv":
            a, b = self.eval_node(n["child"])
            out = rat_inv(a, b)
        elif k == "add":
            n1, d1 = self.eval_node(n["left"])
            n2, d2 = self.eval_node(n["right"])
            out = rat_add(n1, d1, n2, d2)
        elif k == "sub":
            n1, d1 = self.eval_node(n["left"])
            n2, d2 = self.eval_node(n["right"])
            out = rat_sub(n1, d1, n2, d2)
        elif k == "mul":
            n1, d1 = self.eval_node(n["left"])
            n2, d2 = self.eval_node(n["right"])
            out = rat_mul(n1, d1, n2, d2)
        elif k == "abs":
            a, b = self.eval_node(n["child"])
            out = rat_abs(a, b)
        elif k == "min":
            n1, d1 = self.eval_node(n["left"])
            n2, d2 = self.eval_node(n["right"])
            out = rat_min(n1, d1, n2, d2)
        elif k == "max":
            n1, d1 = self.eval_node(n["left"])
            n2, d2 = self.eval_node(n["right"])
            out = rat_max(n1, d1, n2, d2)
        elif k == "floor":
            a, b = self.eval_node(n["child"])
            out = rat_floor(a, b)
        elif k == "ceil":
            a, b = self.eval_node(n["child"])
            out = rat_ceil(a, b)
        else:
            raise ValueError(f"unknown kind {k!r}")
        self.memo[nid] = out
        return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--graph", default="/app/graph.json")
    ap.add_argument("--assignment", default="/app/assignment.json")
    ap.add_argument("--output", default="/app/result.json")
    args = ap.parse_args()
    with open(args.graph, encoding="utf-8") as f:
        graph = json.load(f)
    with open(args.assignment, encoding="utf-8") as f:
        assignment = json.load(f)
    ev = Evaluator(graph["nodes"], graph["root"], assignment["vars"])
    num, den = ev.eval_node(graph["root"])
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump({"num": num, "den": den}, f)
        f.write("\n")


if __name__ == "__main__":
    main()
PY

chmod +x /app/evaluate.py
python3 /app/evaluate.py
