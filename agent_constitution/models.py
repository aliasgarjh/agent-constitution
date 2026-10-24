"""Core data types for agent-constitution."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


class Verdict(str, Enum):
    COMMIT = "commit"            # safe for the system to act autonomously
    ESCALATE = "escalate"        # a human with the right authority must decide
    BLOCK = "block"              # forbidden; no exception path exists
    REFRESH = "refresh_evidence" # evidence is stale/contradictory; re-read, then re-arbitrate


class ConflictKind(str, Enum):
    DATA = "data_and_freshness"
    CONCURRENCY = "concurrency_and_sequencing"
    POLICY = "policy_and_regulation"
    RESOURCE = "resources_and_capacity"
    PRIORITY = "goals_and_priorities"
    AUTHORITY = "authority_and_accountability"


@dataclass
class Evidence:
    """A claim about a subject, with provenance and freshness."""
    subject: str          # e.g. "supplier:A"
    key: str              # e.g. "risk_tier"
    value: Any
    source: str           # e.g. "grc_system"
    as_of: datetime

    def aware_as_of(self) -> datetime:
        return self.as_of if self.as_of.tzinfo else self.as_of.replace(tzinfo=timezone.utc)


@dataclass
class Proposal:
    """What an agent wants to do, and why. Agents propose; the arbiter disposes."""
    agent_id: str
    decision_class: str               # e.g. "award_contract"
    option: str                       # proposals with the same option are the same course of action
    subject: str                      # what the action is about, e.g. "supplier:A"
    action: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    evidence: list[Evidence] = field(default_factory=list)
    rationale: str = ""
    reversible: bool = True
    impact: float = 0.0
    state_version: Optional[str] = None   # version of shared state the agent read


@dataclass
class ConstraintHit:
    constraint_id: str
    kind: str
    description: str
    exception_approver: Optional[str]


@dataclass
class Authority:
    kind: str                         # "agent" | "human" | "forbidden"
    approver: Optional[str] = None


@dataclass
class Option:
    """A distinct course of action, aggregated from one or more proposals."""
    id: str
    decision_class: str
    subject: str
    supporters: list[str]
    params: dict[str, Any]
    reversible: bool
    impact: float
    facts: dict[str, Any] = field(default_factory=dict)
    hits: list[ConstraintHit] = field(default_factory=list)
    breakers: list[str] = field(default_factory=list)
    authority: Authority = field(default_factory=lambda: Authority("forbidden"))
    approvers: list[str] = field(default_factory=list)
    blocked_reasons: list[str] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        return not self.hits and not self.breakers and not self.blocked_reasons


@dataclass
class Conflict:
    kind: ConflictKind
    description: str
    parties: list[str] = field(default_factory=list)


@dataclass
class Resolution:
    verdict: Verdict
    chosen: Optional[Option]
    options: list[Option]
    conflicts: list[Conflict]
    approvers: list[str]
    evidence_notes: list[str]
    reasons: list[str]
    record_id: str

    def to_dict(self) -> dict[str, Any]:
        def opt(o: Option) -> dict[str, Any]:
            return {
                "id": o.id, "subject": o.subject, "supporters": o.supporters,
                "reversible": o.reversible, "impact": o.impact, "facts": o.facts,
                "exceptions_needed": [
                    {"constraint": h.constraint_id, "kind": h.kind, "approver": h.exception_approver}
                    for h in o.hits],
                "breakers": o.breakers, "authority": o.authority.kind,
                "approvers": o.approvers, "blocked": o.blocked_reasons,
            }
        return {
            "record_id": self.record_id,
            "verdict": self.verdict.value,
            "chosen": self.chosen.id if self.chosen else None,
            "options": [opt(o) for o in self.options],
            "conflicts": [{"kind": c.kind.value, "description": c.description, "parties": c.parties}
                          for c in self.conflicts],
            "approvers": self.approvers,
            "evidence_notes": self.evidence_notes,
            "reasons": self.reasons,
        }
