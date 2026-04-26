Imagine a tiny spreadsheet nobody ever shipped the UI for: a directed acyclic graph where each cell is either a rational constant, a variable, or a small set of operations. Nothing becomes a float—every intermediate stays as an integer numerator over a strictly positive integer denominator, and you are expected to cancel common factors as you go so the numbers stay manageable when the harness throws big graphs at you.

You get two JSON files under `/app/`. `graph.json` names a `root` node id and a `nodes` map. Each node has a `kind`:

Constants (`const`) carry integer `num` and `den` with `den > 0`; the pair need not already be reduced, and `num` may be negative. Variables (`var`) carry a `name` string; look it up under `vars` in `assignment.json`, where every binding is again `{"num": ..., "den": ...}` with a positive denominator (also not guaranteed pre-reduced).

Binary nodes `add`, `sub`, and `mul` point to `left` and `right` child ids. Unary `neg` flips the sign. Unary `inv` takes the reciprocal; inputs are always valid, so you will never invert an expression that evaluates to zero. Unary `abs` sends a rational to its distance from zero on the number line—think `abs(-15/6)` ending up as the reduced `5/2`.

`min` and `max` compare two children in the usual order on the rationals. With both denominators positive, compare `n1/d1` and `n2/d2` by cross-multiplying with integers (`n1*d2` versus `n2*d1`) and **do not** cast to float. If the two values tie, you may return either side’s value, but the pair you write must still be the canonical reduced fraction for that rational.

`floor` and `ceil` are unary. They round toward negative or positive infinity, and the answer is always an integer expressed as a reduced rational with denominator `1`—for instance `floor(-7/3)` is `-3` and `ceil(-7/3)` is `-2`. Stay in integer land; if it helps, `ceil(x) = -floor(-x)` is a dependable identity to implement.

The graph may fan back into the same node id from more than one parent. Treat each id as a single memoized value once you know it, or you will redo work exponentially on the hidden stress pattern even though the JSON stays small.

Ship `/app/evaluate.py` that reads the graph and assignment, evaluates `root`, and writes `/app/result.json` as exactly `{"num": <int>, "den": <int>}`—no extra keys—with `den > 0`, `gcd(abs(num), den) == 1`, and any negative sign carried on `num`.

Command line shape:

`python3 /app/evaluate.py [--graph PATH] [--assignment PATH] [--output PATH]`

If you omit the flags, default to `/app/graph.json`, `/app/assignment.json`, and `/app/result.json`. The bundled files are only a sanity check; the grader also runs large random DAGs, long cancellation chains, and the nested memo torture case, so reduction habits and memoization matter in practice.

Standard library only, but the checker parses your file: any `import` / `from … import` whose top-level module name is `fractions`, `decimal`, `numpy`, `sympy`, `gmpy2`, `importlib`, `inspect`, `ctypes`, `subprocess`, `multiprocessing`, `pickle`, `marshal`, `os`, `builtins`, `types`, `code`, `sqlite3`, `zlib`, `base64`, `ssl`, or `socket` will fail you (so `from fractions import Fraction` is out for the same reason). Do not call `eval`, `exec`, `compile`, or `__import__` by bare name anywhere in the module. `math.gcd` is fair game for reduction.

If you can run the script with defaults, delete nothing critical from your logic when the graph grows, and still match the oracle on weird mixes of `inv`, ordering, and rounding, you are in the right neighborhood.
