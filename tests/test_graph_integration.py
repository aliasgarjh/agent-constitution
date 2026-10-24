import pytest

from agent_constitution import Verdict
from agent_constitution.integrations.graph import make_arbiter_node, route_on_verdict
from conftest import award, tier


def test_node_and_router_work_on_plain_dict_state(arbiter):
    state = {"proposals": [award("p", "A", cost=10_000, evidence=[tier("supplier:A", 1)])]}
    state.update(make_arbiter_node(arbiter)(state))
    assert state["resolution"].verdict == Verdict.COMMIT
    assert route_on_verdict()(state) == "commit"


def test_works_inside_langgraph(arbiter):
    langgraph = pytest.importorskip("langgraph.graph")
    from typing import Any, TypedDict

    class S(TypedDict, total=False):
        proposals: list
        resolution: Any

    g = langgraph.StateGraph(S)
    g.add_node("arbiter", make_arbiter_node(arbiter))
    g.add_edge(langgraph.START, "arbiter")
    g.add_edge("arbiter", langgraph.END)
    out = g.compile().invoke({"proposals": [award("p", "A", cost=10_000, evidence=[tier("supplier:A", 1)])]})
    assert out["resolution"].verdict == Verdict.COMMIT
