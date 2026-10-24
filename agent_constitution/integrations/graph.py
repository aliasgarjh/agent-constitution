"""Framework-agnostic glue.

Most graph/workflow frameworks (LangGraph, Microsoft Agent Framework workflows, plain
asyncio pipelines) let you register a function that takes shared state and returns an update.
`make_arbiter_node` produces exactly that, and `route_on_verdict` gives you the label for a
conditional edge. Agents write `Proposal`s into state; the arbiter node writes a `Resolution`.
"""
from __future__ import annotations

from typing import Any, Callable

from ..arbiter import Arbiter
from ..models import Proposal


def make_arbiter_node(arbiter: Arbiter, proposals_key: str = "proposals",
                      resolution_key: str = "resolution") -> Callable[[dict[str, Any]], dict[str, Any]]:
    def node(state: dict[str, Any]) -> dict[str, Any]:
        proposals: list[Proposal] = state[proposals_key]
        return {resolution_key: arbiter.resolve(proposals)}
    return node


def route_on_verdict(resolution_key: str = "resolution") -> Callable[[dict[str, Any]], str]:
    def route(state: dict[str, Any]) -> str:
        return state[resolution_key].verdict.value
    return route
