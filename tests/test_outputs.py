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
        elif k in ("add", "sub", "mul"):
            stack.append(n["left"])
            stack.append(n["right"])
        elif k in ("neg", "inv"):
            stack.append(n["child"])
        else:
            assert k == "const", k
    return seen


def _assert_reduced(num: int, den: int) -> None:
    assert den > 0, "denominator must be positive"
    g = math.gcd(abs(num), den)
    assert g == 1, f"expected reduced fraction, got gcd={g} for {num}/{den}"


def _run_evaluate(graph_path: Path, assign_path: Path, out_path: Path) -> dict:
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
        timeout=120,
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


def test_evaluate_script_exists():
    assert EVALUATE.is_file(), "Missing /app/evaluate.py"


def test_ast_forbidden_imports_and_calls():
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
    for k in range(1, 55):
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


def test_neg_inv_fixture():
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
    # -4/3 + 1/6 = -8/6 + 1/6 = -7/6
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        gp, ap, op = td / "g.json", td / "a.json", td / "o.json"
        gp.write_text(json.dumps(graph), encoding="utf-8")
        ap.write_text(json.dumps(assign), encoding="utf-8")
        data = _run_evaluate(gp, ap, op)
    assert data["num"] == -7 and data["den"] == 6
    _assert_reduced(data["num"], data["den"])


def _random_graph(rng: random.Random, n_nodes: int) -> dict:
    """Build a random DAG (reverse topological: each new node only references older ids)."""
    nodes: dict = {}
    nodes["v0"] = {
        "kind": "const",
        "num": rng.randint(1, 9),
        "den": rng.randint(1, 9),
    }
    var_names = [f"x{i}" for i in range(8)]
    for j in range(1, min(5, n_nodes)):
        nodes[f"v{j}"] = {"kind": "var", "name": var_names[j - 1]}
    for i in range(5, n_nodes):
        nid = f"v{i}"
        choices = [f"v{k}" for k in range(i)]
        roll = rng.random()
        if roll < 0.78:
            left = rng.choice(choices)
            right = rng.choice(choices)
            op = rng.choice(["add", "sub", "mul"])
            nodes[nid] = {"kind": op, "left": left, "right": right}
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
    assert EVALUATE.is_file()
    for trial in range(72):
        rng = random.Random(9001 + trial)
        n = rng.randint(18, 48)
        graph = _random_graph(rng, n)
        names = _collect_var_names(graph)
        assign = _random_assignment(rng, names)
        expected = _oracle_fraction(graph, assign)
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
