Picture a spreadsheet that never shipped: a directed acyclic graph of little cells, each one either a rational constant, a variable name, or one of a handful of operations. There are no floats anywhere in the story. Every value lives as an integer numerator over a strictly positive integer denominator, and you are supposed to keep cancelling gcds as you walk the graph so the integers do not explode when the tests throw large, tangled examples at you.

You work from two JSON files in `/app/`. `graph.json` points at a `root` id and a `nodes` table keyed by id. Each row has a `kind` that tells you what to do.

Constants are `const` rows with integer `num` and `den` where `den` is already positive; the fraction might still be sloppy (not reduced) and the numerator may be negative. Variables are `var` rows with a `name`; resolve that name inside `assignment.json` under `vars`, where each entry again looks like `{"num": ..., "den": ...}` with a positive denominator and no promise of being reduced.

The usual binary arithmetic nodes are `add`, `sub`, and `mul`, each with `left` and `right` ids. Unary `neg` negates. Unary `inv` reciprocates; the inputs are always valid, so you never reciprocate a value that is exactly zero. Unary `abs` is distance from zero on the line, so after reduction you end up with a non-negative numerator—`abs(-15/6)` should land on `5/2`.

`min` and `max` pick the smaller or larger rational in the ordinary order on ℚ. Compare two reduced-or-not values with positive denominators by integer cross products `n1*d2` against `n2*d1`, never by casting to float. If the two sides tie, either branch is fine as long as you still emit the canonical reduced pair for that single rational value.

Rounding comes in several flavours, all unary on a `child` id, and every answer that is “an integer” is written as a reduced rational with denominator `1`. `floor` heads toward negative infinity and `ceil` toward positive infinity, so `floor(-7/3)` is `-3` while `ceil(-7/3)` is `-2`. A handy trick if you implement one first is `ceil(x) = -floor(-x)`, still using only integers.

`trunc` chops toward zero, not toward negative infinity. The same `-7/3` example makes the point: `trunc(-7/3)` is `-2`, which is already different from `floor(-7/3)`. Finally, `sgn` reads the sign of its child and answers with exactly one of the reduced rationals `-1/1`, `0/1`, or `1/1`.

The graph may wire the same node id into more than one parent. Cache each id’s value the first time you finish it; otherwise the hidden nested pattern revisits the same tiny subgraph an obscene number of times and your program will crawl even though the JSON file still looks modest.

What you ship is `/app/evaluate.py`. It reads the graph and assignment, evaluates `root`, and writes `/app/result.json` containing only `{"num": <int>, "den": <int>}` with no extra keys, `den` positive, `gcd(abs(num), den) == 1`, and any negative sign parked on `num`.

Run it like this:

`python3 /app/evaluate.py [--graph PATH] [--assignment PATH] [--output PATH]`

With no flags, read `/app/graph.json` and `/app/assignment.json` and write `/app/result.json`. The checked-in graph is just a smoke test; behind the scenes there are long cancellation chains, big random mixes of every operator above (including `trunc` and `sgn` next to `inv`, ordering, and the infinity-rounding pair), and the nested memo stress case, so sloppy reduction or the wrong flavour of rounding will show up quickly.

Stick to the standard library, but know that the grader walks the AST: importing any of `fractions`, `decimal`, `numpy`, `sympy`, `gmpy2`, `importlib`, `inspect`, `ctypes`, `subprocess`, `multiprocessing`, `pickle`, `marshal`, `os`, `builtins`, `types`, `code`, `sqlite3`, `zlib`, `base64`, `ssl`, or `socket` as the top-level name in `import` / `from … import` will fail you, and so will bare calls to `eval`, `exec`, `compile`, or `__import__`. `math.gcd` is explicitly allowed for reduction.

If the default run still prints the bundled answer, the big random trials still agree with the reference, and nothing blows up when the graph deepens, you are pointed the right way.
