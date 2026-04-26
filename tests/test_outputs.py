"""Verifier for rational-dag-evaluator — exact rational DAG evaluation without fractions.Decimal."""

import ast
import json
import math
import random
import subprocess
import tempfile
from fractions import Fraction
from pathlib import Path


EVALUATE = Path("/app/evaluate.py")
DEFAULT_GRAPH = Path("/app/graph.json")
DEFAULT_ASSIGN = Path("/app/assignment.json")
DEFAULT_RESULT = Path("/app/result.json")

FORBIDDEN_IMPORTS = {
    "fractions",
    "decimal",
    "numpy",
    "sympy",
    "gmpy2",
    "importlib",
    "inspect",
    "ctypes",
    "subprocess",
    "multiprocessing",
    "pickle",
    "marshal",
    "os",
    "builtins",
    "types",
    "code",
    "sqlite3",
    "zlib",
    "base64",
    "ssl",
    "socket",
}
FORBIDDEN_CALLS = {"eval", "exec", "compile", "__import__"}

# Bundled graph: (1/2+1/3)^2 - 2/7 = 103/252, times inv(4) = 103/1008
EXPECTED_BUNDLED = {"num": 103, "den": 1008}


def _oracle_fraction(graph: dict, assignment: dict) -> Fraction:
    nodes = graph["nodes"]
    root = graph["root"]
    var_fracs = {
        name: Fraction(int(v["num"]), int(v["den"]))
        for name, v in assignment["vars"].items()
    }
    memo: dict[str, Fraction] = {}

    def visit(nid: str) -> Fraction:
        if nid in memo:
            return memo[nid]
        n = nodes[nid]
        k = n["kind"]
        if k == "const":
            r = Fraction(int(n["num"]), int(n["den"]))
        elif k == "var":
            if n["name"] not in var_fracs:
                raise KeyError(n["name"])
            r = var_fracs[n["name"]]
        elif k == "neg":
            r = -visit(n["child"])
        elif k == "inv":
            c = visit(n["child"])
            r = Fraction(1, 1) / c
        elif k == "add":
            r = visit(n["left"]) + visit(n["right"])
        elif k == "sub":
            r = visit(n["left"]) - visit(n["right"])
        elif k == "mul":
            r = visit(n["left"]) * visit(n["right"])
        elif k == "abs":
            r = abs(visit(n["child"]))
        elif k == "min":
            a, b = visit(n["left"]), visit(n["right"])
            r = a if a <= b else b
        elif k == "max":
            a, b = visit(n["left"]), visit(n["right"])
            r = a if a >= b else b
        else:
            raise ValueError(f"unknown kind {k}")
        memo[nid] = r
        return r

    return visit(root)


def _collect_var_names(graph: dict) -> set[str]:
    seen: set[str] = set()
    stack = [graph["root"]]
    nodes = graph["nodes"]
    while stack:
        nid = stack.pop()
        n = nodes[nid]
        k = n["kind"]
        if k == "var":
            seen.add(n["name"])
        elif k in ("add", "sub", "mul", "min", "max"):
            stack.append(n["left"])
            stack.append(n["right"])
        elif k in ("neg", "inv", "abs"):
            stack.append(n["child"])
        else:
            assert k == "const", k
    return seen


def _assert_reduced(num: int, den: int) -> None:
    assert den > 0, "denominator must be positive"
    g = math.gcd(abs(num), den)
    assert g == 1, f"expected reduced fraction, got gcd={g} for {num}/{den}"


def _run_evaluate(
    graph_path: Path,
    assign_path: Path,
    out_path: Path,
    *,
    timeout_sec: float = 120.0,
) -> dict:
    proc = subprocess.run(
        [
            "python3",
            str(EVALUATE),
            "--graph",
            str(graph_path),
            "--assignment",
            str(assign_path),
            "--output",
            str(out_path),
        ],
        capture_output=True,
        text=True,
        timeout=timeout_sec,
    )
    assert proc.returncode == 0, f"evaluate.py failed:\nstdout={proc.stdout}\nstderr={proc.stderr}"
    assert out_path.is_file(), "output file not written"
    return json.loads(out_path.read_text(encoding="utf-8"))


def _check_ast_constraints() -> None:
    src = EVALUATE.read_text(encoding="utf-8", errors="strict")
    tree = ast.parse(src, filename=str(EVALUATE))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                assert top not in FORBIDDEN_IMPORTS, f"forbidden import: {top}"
        elif isinstance(node, ast.ImportFrom) and node.module:
            top = node.module.split(".")[0]
            assert top not in FORBIDDEN_IMPORTS, f"forbidden import from: {top}"
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in FORBIDDEN_CALLS, (
                f"forbidden call: {node.func.id}()"
            )


def _build_nested_mul_diamond(levels: int) -> dict:
    """Nested (add then mul) diamonds: each mul shares one add node; revisits explode without memo."""
    assert levels >= 1
    nodes: dict = {}
    c = "c0"
    nodes[c] = {"kind": "const", "num": 1, "den": 1}
    prev_m: str | None = None
    for k in range(levels):
        sk, mk = f"s{k}", f"m{k}"
        if k == 0:
            nodes[sk] = {"kind": "add", "left": c, "right": c}
        else:
            assert prev_m is not None
            nodes[sk] = {"kind": "add", "left": prev_m, "right": prev_m}
        nodes[mk] = {"kind": "mul", "left": sk, "right": sk}
        prev_m = mk
    assert prev_m is not None
    return {"root": prev_m, "nodes": nodes}


def _nested_mul_diamond_expected(levels: int) -> Fraction:
    """Closed form for _build_nested_mul_diamond: m0=4, m_{k} = (2*m_{k-1})^2."""
    m = Fraction(4, 1)
    for _ in range(1, levels):
        s = m + m
        m = s * s
    return m


def test_evaluate_script_exists():
    """Agent must create /app/evaluate.py before any functional checks."""
    assert EVALUATE.is_file(), "Missing /app/evaluate.py"


def test_ast_forbidden_imports_and_calls():
    """Banned stdlib shortcuts and dynamic execution must not appear in source."""
    assert EVALUATE.is_file()
    _check_ast_constraints()


def test_bundled_default_paths():
    """Default CLI paths must reproduce the reference value for shipped graph + assignment."""
    assert EVALUATE.is_file()
    if DEFAULT_RESULT.exists():
        DEFAULT_RESULT.unlink()
    proc = subprocess.run(
        ["python3", str(EVALUATE)],
        capture_output=True,
        text=True,
        timeout=120,
        cwd="/app",
    )
    assert proc.returncode == 0, proc.stderr
    data = json.loads(DEFAULT_RESULT.read_text(encoding="utf-8"))
    assert data == EXPECTED_BUNDLED
    _assert_reduced(data["num"], data["den"])


def test_bundled_matches_fraction_oracle():
    """Shipped graph.json + assignment.json must agree with the internal Fraction oracle."""
    graph = json.loads(DEFAULT_GRAPH.read_text(encoding="utf-8"))
    assign = json.loads(DEFAULT_ASSIGN.read_text(encoding="utf-8"))
    expected = _oracle_fraction(graph, assign)
    assert expected.numerator == EXPECTED_BUNDLED["num"]
    assert expected.denominator == EXPECTED_BUNDLED["den"]


def test_const_only_diamond():
    """Mul of identical sub-expression (shared DAG node) must equal 16."""
    graph = {
        "root": "r",
        "nodes": {
            "c": {"kind": "const", "num": 2, "den": 1},
            "s": {"kind": "add", "left": "c", "right": "c"},
            "r": {"kind": "mul", "left": "s", "right": "s"},
        },
    }
    assign = {"vars": {}}
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        gp, ap, op = td / "g.json", td / "a.json", td / "o.json"
        gp.write_text(json.dumps(graph), encoding="utf-8")
        ap.write_text(json.dumps(assign), encoding="utf-8")
        data = _run_evaluate(gp, ap, op)
    assert data["num"] == 16 and data["den"] == 1
    _assert_reduced(data["num"], data["den"])


def test_telescope_cancellation_chain():
    """Long chain of (1/k)*(k/1) products must stay 1/1 without overflow from lack of reduction."""
    nodes: dict = {}
    nodes["n0"] = {"kind": "const", "num": 1, "den": 1}
    prev = "n0"
    for k in range(1, 100):
        a, b, m, out = f"ca{k}", f"cb{k}", f"mk{k}", f"ac{k}"
        nodes[a] = {"kind": "const", "num": 1, "den": k + 1}
        nodes[b] = {"kind": "const", "num": k + 1, "den": 1}
        nodes[m] = {"kind": "mul", "left": a, "right": b}
        nodes[out] = {"kind": "mul", "left": prev, "right": m}
        prev = out
    graph = {"root": prev, "nodes": nodes}
    assign = {"vars": {}}
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        gp, ap, op = td / "g.json", td / "a.json", td / "o.json"
        gp.write_text(json.dumps(graph), encoding="utf-8")
        ap.write_text(json.dumps(assign), encoding="utf-8")
        data = _run_evaluate(gp, ap, op)
    assert data["num"] == 1 and data["den"] == 1
    _assert_reduced(data["num"], data["den"])


def test_neg_inv_fixture():
    """Hand-crafted neg(inv(const)) plus add checks sign handling and inv correctness."""
    graph = {
        "root": "out",
        "nodes": {
            "a": {"kind": "const", "num": 3, "den": 4},
            "b": {"kind": "inv", "child": "a"},
            "c": {"kind": "neg", "child": "b"},
            "d": {"kind": "const", "num": 1, "den": 6},
            "out": {"kind": "add", "left": "c", "right": "d"},
        },
    }
    assign = {"vars": {}}
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        gp, ap, op = td / "g.json", td / "a.json", td / "o.json"
        gp.write_text(json.dumps(graph), encoding="utf-8")
        ap.write_text(json.dumps(assign), encoding="utf-8")
        data = _run_evaluate(gp, ap, op)
    assert data["num"] == -7 and data["den"] == 6
    _assert_reduced(data["num"], data["den"])


def test_abs_negative_rational():
    """abs must return a non-negative numerator with positive denominator, fully reduced."""
    graph = {
        "root": "o",
        "nodes": {
            "n": {"kind": "const", "num": -15, "den": 6},
            "o": {"kind": "abs", "child": "n"},
        },
    }
    assign = {"vars": {}}
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        gp, ap, op = td / "g.json", td / "a.json", td / "o.json"
        gp.write_text(json.dumps(graph), encoding="utf-8")
        ap.write_text(json.dumps(assign), encoding="utf-8")
        data = _run_evaluate(gp, ap, op)
    assert data["num"] == 5 and data["den"] == 2
    _assert_reduced(data["num"], data["den"])


def test_min_negative_vs_positive():
    """min must pick the smaller rational when one branch is negative (cross-mul, not floats)."""
    graph = {
        "root": "lo",
        "nodes": {
            "a": {"kind": "const", "num": -1, "den": 2},
            "b": {"kind": "const", "num": 1, "den": 3},
            "lo": {"kind": "min", "left": "a", "right": "b"},
        },
    }
    assign = {"vars": {}}
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        gp, ap, op = td / "g.json", td / "a.json", td / "o.json"
        gp.write_text(json.dumps(graph), encoding="utf-8")
        ap.write_text(json.dumps(assign), encoding="utf-8")
        data = _run_evaluate(gp, ap, op)
    assert data["num"] == -1 and data["den"] == 2
    _assert_reduced(int(data["num"]), int(data["den"]))


def test_max_negative_vs_positive():
    """max must pick the larger rational when one branch is negative."""
    graph = {
        "root": "hi",
        "nodes": {
            "a": {"kind": "const", "num": -1, "den": 2},
            "b": {"kind": "const", "num": 1, "den": 3},
            "hi": {"kind": "max", "left": "a", "right": "b"},
        },
    }
    assign = {"vars": {}}
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        gp, ap, op = td / "g.json", td / "a.json", td / "o.json"
        gp.write_text(json.dumps(graph), encoding="utf-8")
        ap.write_text(json.dumps(assign), encoding="utf-8")
        data = _run_evaluate(gp, ap, op)
    assert data["num"] == 1 and data["den"] == 3
    _assert_reduced(int(data["num"]), int(data["den"]))


def test_max_of_min_and_max_recombines():
    """DAG reuses min/max of the same pair then maxes them — result is the larger branch."""
    graph = {
        "root": "mx",
        "nodes": {
            "a": {"kind": "const", "num": -1, "den": 2},
            "b": {"kind": "const", "num": 1, "den": 3},
            "lo": {"kind": "min", "left": "a", "right": "b"},
            "hi": {"kind": "max", "left": "a", "right": "b"},
            "mx": {"kind": "max", "left": "lo", "right": "hi"},
        },
    }
    assign = {"vars": {}}
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        gp, ap, op = td / "g.json", td / "a.json", td / "o.json"
        gp.write_text(json.dumps(graph), encoding="utf-8")
        ap.write_text(json.dumps(assign), encoding="utf-8")
        data = _run_evaluate(gp, ap, op)
    assert data["num"] == 1 and data["den"] == 3
    _assert_reduced(int(data["num"]), int(data["den"]))


def test_nested_mul_diamond_memo_required():
    """Deeply nested mul(add(m,m),...) diamonds revisit shared ids; naive re-walk is exponential."""
    levels = 11
    graph = _build_nested_mul_diamond(levels)
    assign = {"vars": {}}
    expected = _nested_mul_diamond_expected(levels)
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        gp, ap, op = td / "g.json", td / "a.json", td / "o.json"
        gp.write_text(json.dumps(graph), encoding="utf-8")
        ap.write_text(json.dumps(assign), encoding="utf-8")
        data = _run_evaluate(gp, ap, op, timeout_sec=55.0)
    got = Fraction(int(data["num"]), int(data["den"]))
    assert got == expected, f"expected {expected} got {got}"
    _assert_reduced(int(data["num"]), int(data["den"]))


def _random_graph(rng: random.Random, n_nodes: int) -> dict:
    """Random DAG: new nodes only reference older ids; mixes abs/min/max/inv/neg/binary ops."""
    nodes: dict = {}
    nodes["v0"] = {
        "kind": "const",
        "num": rng.randint(1, 9),
        "den": rng.randint(1, 9),
    }
    var_names = [f"x{i}" for i in range(10)]
    for j in range(1, min(6, n_nodes)):
        nodes[f"v{j}"] = {"kind": "var", "name": var_names[j - 1]}
    for i in range(6, n_nodes):
        nid = f"v{i}"
        choices = [f"v{k}" for k in range(i)]
        roll = rng.random()
        if roll < 0.48:
            left = rng.choice(choices)
            right = rng.choice(choices)
            op = rng.choice(["add", "sub", "mul"])
            nodes[nid] = {"kind": op, "left": left, "right": right}
        elif roll < 0.58:
            child = rng.choice(choices)
            nodes[nid] = {"kind": "abs", "child": child}
        elif roll < 0.72:
            left = rng.choice(choices)
            right = rng.choice(choices)
            op = rng.choice(["min", "max"])
            nodes[nid] = {"kind": op, "left": left, "right": right}
        elif roll < 0.84:
            child = rng.choice(choices)
            nodes[nid] = {"kind": "inv", "child": child}
        else:
            child = rng.choice(choices)
            nodes[nid] = {"kind": "neg", "child": child}
    return {"root": f"v{n_nodes - 1}", "nodes": nodes}


def _random_assignment(rng: random.Random, names: set[str]) -> dict:
    vars_: dict = {}
    for nm in sorted(names):
        vars_[nm] = {
            "num": rng.randint(1, 14),
            "den": rng.randint(1, 14),
        }
    return {"vars": vars_}


def test_random_graphs_match_oracle():
    """Many seeded random DAGs must match the Fraction oracle after resampling away inv-of-zero."""
    assert EVALUATE.is_file()
    for trial in range(180):
        rng = random.Random(410_000 + trial)
        n = rng.randint(32, 120)
        graph = None
        assign = None
        expected = None
        for _ in range(72):
            graph = _random_graph(rng, n)
            names = _collect_var_names(graph)
            assign = _random_assignment(rng, names)
            try:
                expected = _oracle_fraction(graph, assign)
                break
            except ZeroDivisionError:
                rng = random.Random(rng.randint(1, 2**31 - 1))
        assert graph is not None and assign is not None and expected is not None, (
            "could not sample a graph without inv-of-zero after several tries"
        )
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            gp, ap, op = td / "g.json", td / "a.json", td / "o.json"
            gp.write_text(json.dumps(graph), encoding="utf-8")
            ap.write_text(json.dumps(assign), encoding="utf-8")
            data = _run_evaluate(gp, ap, op)
        assert "num" in data and "den" in data
        _assert_reduced(int(data["num"]), int(data["den"]))
        got = Fraction(int(data["num"]), int(data["den"]))
        assert got == expected, f"trial {trial}: expected {expected} got {got}"
