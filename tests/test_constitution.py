import pytest

from agent_constitution import Constitution, ConstitutionError
from agent_constitution.conditions import evaluate


def test_conditions_basic():
    ctx = {"params": {"cost": 10}, "facts": {"tier": 3}}
    assert evaluate({"field": "params.cost", "op": "<=", "value": 10}, ctx)
    assert not evaluate({"field": "facts.missing", "op": ">", "value": 0}, ctx)  # missing never satisfies
    assert evaluate({"all": [{"field": "facts.tier", "op": "in", "value": [2, 3]},
                             {"not": {"field": "params.cost", "op": ">", "value": 10}}]}, ctx)


def test_invalid_constitution_is_rejected():
    with pytest.raises(ConstitutionError):
        Constitution.from_dict({"decision_rights": {"x": {"rules": []}}})  # no default
    with pytest.raises(ConstitutionError):
        Constitution.from_dict({"decision_rights": {"x": {"default": {"authority": "human"}}}})
    with pytest.raises(ValueError):
        Constitution.from_dict({"constraints": [
            {"id": "c", "when": {"field": "a", "op": "~~", "value": 1}}]})
