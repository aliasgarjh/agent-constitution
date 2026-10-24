"""The constitution: constraints, decision rights, source precedence and circuit breakers."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .conditions import validate

CONSTRAINT_KINDS = {"policy", "resource", "priority"}


class ConstitutionError(ValueError):
    pass


@dataclass
class Constraint:
    id: str
    kind: str                                   # policy | resource | priority
    description: str
    when: dict[str, Any]                        # true => the constraint is violated
    exception_approver: Optional[str] = None    # None => hard limit, no exception path
    decision_classes: Optional[list[str]] = None
    needs: list[str] = field(default_factory=list)  # facts that must exist to evaluate safely


@dataclass
class Rule:
    when: Optional[dict[str, Any]]
    authority: str                              # agent | human
    approver: Optional[str] = None


@dataclass
class DecisionRight:
    decision_class: str
    rules: list[Rule]
    default: Rule


@dataclass
class SourcePolicy:
    precedence: list[str] = field(default_factory=list)   # most authoritative first
    max_age_days: Optional[float] = None


@dataclass
class Breaker:
    id: str
    when: dict[str, Any]
    escalate_to: str


@dataclass
class Constitution:
    constraints: list[Constraint]
    decision_rights: dict[str, DecisionRight]
    sources: dict[str, SourcePolicy]
    breakers: list[Breaker]
    version: int = 1

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Constitution":
        constraints, seen = [], set()
        for raw in data.get("constraints", []):
            c = Constraint(
                id=raw["id"], kind=raw.get("kind", "policy"), description=raw.get("description", ""),
                when=raw["when"], exception_approver=raw.get("exception_approver"),
                decision_classes=raw.get("decision_classes"), needs=raw.get("needs", []))
            if c.id in seen:
                raise ConstitutionError(f"duplicate constraint id: {c.id}")
            seen.add(c.id)
            if c.kind not in CONSTRAINT_KINDS:
                raise ConstitutionError(f"constraint {c.id}: kind must be one of {sorted(CONSTRAINT_KINDS)}")
            validate(c.when, f"constraint {c.id}.when")
            constraints.append(c)

        rights = {}
        for cls_name, raw in data.get("decision_rights", {}).items():
            def mk(r: dict[str, Any], label: str, _n: str = cls_name) -> Rule:
                if r.get("authority") not in {"agent", "human"}:
                    raise ConstitutionError(f"decision_rights.{_n}.{label}: authority must be agent|human")
                if r["authority"] == "human" and not r.get("approver"):
                    raise ConstitutionError(f"decision_rights.{_n}.{label}: human authority needs an approver")
                validate(r.get("when"), f"decision_rights.{_n}.{label}.when")
                return Rule(r.get("when"), r["authority"], r.get("approver"))
            if "default" not in raw:
                raise ConstitutionError(f"decision_rights.{cls_name}: a default is required")
            rights[cls_name] = DecisionRight(
                cls_name, [mk(r, f"rules[{i}]") for i, r in enumerate(raw.get("rules", []))],
                mk(raw["default"], "default"))

        sources = {k: SourcePolicy(v.get("precedence", []), v.get("max_age_days"))
                   for k, v in data.get("sources", {}).items()}

        breakers = []
        for raw in data.get("breakers", []):
            validate(raw["when"], f"breaker {raw['id']}.when")
            breakers.append(Breaker(raw["id"], raw["when"], raw["escalate_to"]))

        return cls(constraints, rights, sources, breakers, data.get("version", 1))

    @classmethod
    def from_yaml(cls, path: str) -> "Constitution":
        try:
            import yaml
        except ImportError as e:  # pragma: no cover
            raise ImportError("pip install pyyaml to load YAML constitutions") from e
        with open(path, "r", encoding="utf-8") as f:
            return cls.from_dict(yaml.safe_load(f))
