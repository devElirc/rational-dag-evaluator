I have a small spreadsheet-like graph in `/app`. 
There is no UI. Each node is either a rational number, a variable, or a simple math operation.

Please write `/app/evaluate.py`.

It should read `/app/graph.json` and `/app/assignment.json`, evaluate the graph root, and write the final answer to `/app/result.json`.

All math must stay exact. Do not use floats. 
Store every value as an integer numerator and a positive integer denominator. 
Reduce fractions as you go so large hidden tests do not get slow.

`graph.json` contains the root node id to evaluate and a `nodes` object where each key is a node id.

Each node has a `kind`.

A `const` node has `num` and `den`. The denominator is positive, but the fraction may not be reduced.

A `var` node has `name`. Look up that name in `assignment.json` under `vars`.

`add`, `sub`, and `mul` nodes have `left` and `right` child ids.

A `neg` node has `child` and means the value should be negated.

An `inv` node has `child` and means the value should be inverted. 
Inputs are valid, so you will not need to invert zero.

`assignment.json` has a `vars` object. Each variable maps to `{"num": ..., "den": ...}` with a positive denominator. These fractions may also be unreduced.

The graph is acyclic (no cycles) and may reuse the same node id from multiple parents. 
Cache each evaluated node id so the same subgraph is only evaluated once.

The script should run like this:

`python3 /app/evaluate.py [--graph PATH] [--assignment PATH] [--output PATH]`

When no flags are provided, it should read `/app/graph.json` and `/app/assignment.json`, then write the result to `/app/result.json`.

The result file must be a single JSON object with exactly those two keys, `num` and `den` (both integers). The bundled smoke test loads the JSON and checks for exact equality with the reference object, so extra keys will fail that check.

The denominator must always be positive. 
The fraction must be reduced (`gcd(abs(num), den) == 1`). If the result is negative, keep the negative sign on `num`.

Use the standard library only. The verifier parses `evaluate.py` with the AST and rejects the solution if the **top-level** module name of any `import` or `from … import` is one of: `fractions`, `decimal`, `numpy`, `sympy`, `gmpy2`, `importlib`, `inspect`, `ctypes`, `subprocess`, `multiprocessing`, `pickle`, `marshal`, `os`, `builtins`, `types`, `code`, `sqlite3`, `zlib`, `base64`, `ssl`, or `socket` (for example `from fractions import Fraction` is forbidden because the first segment is `fractions`).

Also do not call `eval`, `exec`, `compile`, or `__import__` by bare name anywhere in the file.

You can use `math.gcd`. The bundled graph is only a small smoke test. 
The verifier will also run larger random graphs, so exact arithmetic, reduction, and memoization are important.