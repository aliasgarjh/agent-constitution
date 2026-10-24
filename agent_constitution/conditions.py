"""A tiny, safe condition language (no eval). Conditions are plain dicts so they can live in YAML."""
from __future__ import annotations

import operator
from typing import Any

_OPS = {"==": operator.eq, "!=": operator.ne, ">": operator.gt,
        ">=": operator.ge, "<": operator.lt, "<=": operator.le}
VALID_OPS = set(_OPS) | {"in", "not_in", "exists"}


def lookup(ctx: dict[str, Any], path: str) -> Any:
    cur: Any = ctx
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


def evaluate(cond: dict[str, Any] | None, ctx: dict[str, Any]) -> bool:
    """Evaluate a condition against a context. Missing fields never satisfy a comparison."""
    if not cond:
        return True
    if "all" in cond:
        return all(evaluate(c, ctx) for c in cond["all"])
    if "any" in cond:
        return any(evaluate(c, ctx) for c in cond["any"])
    if "not" in cond:
        return not evaluate(cond["not"], ctx)
    actual = lookup(ctx, cond["field"])
    op, value = cond["op"], cond.get("value")
    if op == "exists":
        return (actual is not None) == (True if value is None else bool(value))
    if op == "in":
        return actual in value
    if op == "not_in":
        return actual not in value
    if op in _OPS:
        if actual is None:
            return op == "!="
        try:
            return bool(_OPS[op](actual, value))
        except TypeError:
            return False
    raise ValueError(f"unknown operator: {op}")


def validate(cond: dict[str, Any] | None, where: str = "condition") -> None:
    if not cond:
        return
    if not isinstance(cond, dict):
        raise ValueError(f"{where}: condition must be a mapping")
    for combo in ("all", "any"):
        if combo in cond:
            for i, c in enumerate(cond[combo]):
                validate(c, f"{where}.{combo}[{i}]")
            return
    if "not" in cond:
        validate(cond["not"], f"{where}.not")
        return
    if "field" not in cond or "op" not in cond:
        raise ValueError(f"{where}: needs 'field' and 'op' (or all/any/not)")
    if cond["op"] not in VALID_OPS:
        raise ValueError(f"{where}: unknown operator {cond['op']!r}")
