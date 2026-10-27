"""Running `check` code (written by a person or an LLM) with some guard rails.

This is defence in depth, NOT a security sandbox:
  1. a static AST guard rejects imports outside a math allow-list, dunder access,
     and builtins that reach the file system, the network, or the interpreter;
  2. the code runs in a separate, isolated interpreter (`python -I -B`) with a
     wall-clock timeout and, on POSIX, CPU / memory / file-size limits;
  3. the child's answer comes back as a sympy `srepr` string, which is
     structure-checked before the parent rebuilds it (so a child cannot make the
     parent evaluate arbitrary code).
If you run specs from people you do not trust, run mathcheck inside the Docker image.
"""
from __future__ import annotations

import ast
import json
import subprocess
import sys
import textwrap

import sympy as sp

ALLOWED_IMPORTS = {
    "sympy", "math", "cmath", "fractions", "decimal", "itertools", "functools",
    "statistics", "numbers", "operator", "collections",
}
BLOCKED_NAMES = {
    "open", "exec", "eval", "compile", "__import__", "input", "globals", "locals", "vars",
    "getattr", "setattr", "delattr", "breakpoint", "exit", "quit", "help", "memoryview",
    "parse_expr", "lambdify", "preview", "plot", "plot3d", "plot_implicit", "init_printing",
    "sys", "os", "subprocess", "importlib", "builtins",
}
STRING_EVAL_FUNCS = {"sympify", "S"}  # sympify("...") evaluates the string


class GuardError(ValueError):
    pass


def guard(code: str) -> None:
    """Raise GuardError if the code uses something outside the allowed subset."""
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        raise GuardError(f"syntax error on line {e.lineno}: {e.msg}") from None
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name.split(".")[0] not in ALLOWED_IMPORTS:
                    raise GuardError(f"import of '{a.name}'")
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".")[0] not in ALLOWED_IMPORTS or node.level:
                raise GuardError(f"import from '{node.module}'")
        elif isinstance(node, ast.Name) and node.id in BLOCKED_NAMES:
            raise GuardError(f"use of '{node.id}'")
        elif isinstance(node, ast.Attribute) and (node.attr.startswith("_") or node.attr in BLOCKED_NAMES):
            raise GuardError(f"attribute '.{node.attr}'")
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in STRING_EVAL_FUNCS:
            if any(isinstance(a, ast.Constant) and isinstance(a.value, str) for a in node.args):
                raise GuardError(f"{node.func.id}() with a string; build the expression with sympy objects")
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            raise GuardError("global/nonlocal")


RUNNER = r'''
import json, sys
try:
    import resource
    _cpu = int(sys.argv[1])
    resource.setrlimit(resource.RLIMIT_CPU, (_cpu, _cpu + 1))
    resource.setrlimit(resource.RLIMIT_AS, (2 << 30, 2 << 30))
    resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
except Exception:
    pass
from sympy import *
x, y, z, t, n, k, a, b, c = symbols("x y z t n k a b c")
_code = sys.stdin.read()
ns = {}
exec(compile(_code, "<check>", "exec"), globals(), ns)
if "result" not in ns:
    print(json.dumps({"error": "no_result"}))
else:
    r = ns["result"]
    if isinstance(r, (set, frozenset, tuple)):
        r = list(r)
    if isinstance(r, list):
        print(json.dumps({"result": [srepr(sympify(i)) for i in r]}))
    else:
        print(json.dumps({"result": srepr(sympify(r))}))
'''

# srepr output only ever contains calls to sympy classes with literal arguments.
_SYMPY_NAMES = {n for n in dir(sp) if not n.startswith("_") and isinstance(getattr(sp, n), type)}
_SYMPY_NAMES |= {"Integer", "Rational", "Float", "Symbol", "Dummy", "Tuple", "Interval", "FiniteSet",
                 "Union", "EmptySet", "oo", "zoo", "nan", "pi", "E", "I", "true", "false"}
_SYMPY_NAMES |= {n for n in ("sqrt", "exp", "log", "sin", "cos", "tan") if hasattr(sp, n)}


def safe_from_srepr(s: str):
    tree = ast.parse(s, mode="eval")
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if not (isinstance(node.func, ast.Name) and node.func.id in _SYMPY_NAMES):
                raise ValueError("unexpected call in result")
        elif isinstance(node, ast.Name):
            if node.id not in _SYMPY_NAMES:
                raise ValueError(f"unexpected name in result: {node.id}")
        elif isinstance(node, ast.Attribute):
            if node.attr.startswith("_") or not (isinstance(node.value, ast.Name) and node.value.id == "S"):
                raise ValueError("unexpected attribute in result")
        elif not isinstance(node, (ast.Expression, ast.Constant, ast.keyword, ast.Load, ast.UnaryOp, ast.USub,
                                   ast.Tuple, ast.List)):
            raise ValueError(f"unexpected syntax in result: {type(node).__name__}")
    ns = {k: getattr(sp, k) for k in _SYMPY_NAMES if hasattr(sp, k)}
    ns["S"] = sp.S
    return eval(compile(tree, "<srepr>", "eval"), {"__builtins__": {}}, ns)  # noqa: S307 (structure-checked)


_EXPR_NODES = (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant, ast.Name, ast.Load, ast.Call,
               ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.Mod, ast.USub, ast.UAdd, ast.Tuple, ast.List,
               ast.keyword, ast.FloorDiv)


def safe_parse_expr(text: str):
    """Parse an answer string like 'sqrt(2)/2' or '3x+1' into sympy without running arbitrary code."""
    import builtins
    import re

    text = str(text).replace("^", "**")
    for ident in re.findall(r"[A-Za-z_]\w*", text):
        if ident.startswith("_") or ident in BLOCKED_NAMES or (
            hasattr(builtins, ident) and not hasattr(sp, ident) and ident not in {"abs", "min", "max", "pow", "round"}
        ):
            raise ValueError(f"name not allowed in answer: {ident}")
    try:
        tree = ast.parse(text, mode="eval")
        for node in ast.walk(tree):
            if not isinstance(node, _EXPR_NODES):
                raise ValueError(f"unsupported syntax: {type(node).__name__}")
            if isinstance(node, ast.Name) and (node.id.startswith("_") or node.id in BLOCKED_NAMES):
                raise ValueError(f"name not allowed: {node.id}")
            if isinstance(node, ast.Call) and not isinstance(node.func, ast.Name):
                raise ValueError("only plain function calls are allowed")
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                raise ValueError("string literals are not allowed")
    except SyntaxError:
        # implicit multiplication like "3x" is not Python; only plain characters are allowed then
        if not all(ch.isalnum() or ch in " +-*/().,^" for ch in text):
            raise ValueError(f"cannot parse: {text}") from None
    from sympy.parsing.sympy_parser import implicit_multiplication_application, parse_expr, standard_transformations

    return parse_expr(text, transformations=standard_transformations + (implicit_multiplication_application,))


def run_check(code: str, timeout: int = 20) -> tuple[object | None, tuple[str, dict] | None]:
    """Returns (value, None) or (None, (issue_code, params))."""
    code = textwrap.dedent(code or "")
    try:
        guard(code)
    except GuardError as e:
        return None, ("math.blocked", {"detail": str(e)})
    try:
        p = subprocess.run(
            [sys.executable, "-I", "-B", "-c", RUNNER, str(timeout)],
            input=code, capture_output=True, text=True, timeout=timeout + 5,
            env={"PATH": "/usr/bin:/bin", "PYTHONHASHSEED": "0"},
        )
    except subprocess.TimeoutExpired:
        return None, ("math.timeout", {"timeout": timeout})
    if p.returncode != 0:
        if p.returncode < 0:  # killed by a resource limit (e.g. SIGXCPU)
            return None, ("math.timeout", {"timeout": timeout})
        last = (p.stderr.strip().splitlines() or ["unknown error"])[-1]
        return None, ("math.runtime_error", {"detail": last})
    try:
        out = json.loads(p.stdout.strip().splitlines()[-1])
    except Exception:
        return None, ("math.bad_output", {})
    if out.get("error") == "no_result":
        return None, ("math.no_result", {})
    try:
        r = out["result"]
        if isinstance(r, list):
            return [safe_from_srepr(s) for s in r], None
        return safe_from_srepr(r), None
    except Exception:
        return None, ("math.bad_output", {})
