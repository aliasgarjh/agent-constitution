"""The arbiter: diagnose before adjudicating.

Pipeline
  1. Concurrency  - did agents act on different versions of the same state?
  2. Evidence     - drop stale claims, apply source precedence, flag real contradictions.
  3. Options      - merge proposals that are the same course of action.
  4. Constraints  - hard limits vs. limits that have an exception path.
  5. Rights       - who may decide this class of decision, under which conditions?
  6. Breakers     - should autonomous execution stop regardless?
  7. Verdict      - commit, escalate (with a decision package), block, or refresh evidence.
  8. Record       - every resolution is appended to a hash-chained ledger.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

from .conditions import evaluate
from .constitution import Constitution
from .ledger import Ledger
from .models import (Authority, Conflict, ConflictKind, ConstraintHit, Evidence, Option,
                     Proposal, Resolution, Verdict)

_KIND_TO_CONFLICT = {"policy": ConflictKind.POLICY, "resource": ConflictKind.RESOURCE,
                     "priority": ConflictKind.PRIORITY}


class Arbiter:
    def __init__(self, constitution: Constitution, ledger: Optional[Ledger] = None,
                 clock: Optional[Callable[[], datetime]] = None):
        self.constitution = constitution
        self.ledger = ledger
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    # ------------------------------------------------------------------ public
    def resolve(self, proposals: list[Proposal]) -> Resolution:
        if not proposals:
            raise ValueError("resolve() needs at least one proposal")
        now = self.clock()
        conflicts: list[Conflict] = []
        reasons: list[str] = []

        conflicts += self._concurrency_conflicts(proposals)
        facts, ev_conflicts, notes = self._resolve_evidence(proposals, now)
        conflicts += ev_conflicts

        options = self._build_options(proposals, facts)
        for opt in options:
            conflicts += self._missing_evidence(opt)

        # Diagnose before adjudicating: never arbitrate on bad data.
        if any(c.kind in (ConflictKind.DATA, ConflictKind.CONCURRENCY) for c in conflicts):
            reasons.append("Evidence or state is stale, missing or contradictory. "
                           "Re-read the system of record, then arbitrate again.")
            return self._finish(Verdict.REFRESH, None, options, conflicts, [], notes, reasons)

        for opt in options:
            self._evaluate_option(opt)

        viable = [o for o in options if not o.blocked_reasons]
        for o in options:
            for why in o.blocked_reasons:
                reasons.append(f"Option {o.id} is blocked: {why}")
        if not viable:
            return self._finish(Verdict.BLOCK, None, options, conflicts, [], notes, reasons)

        for o in viable:
            for h in o.hits:
                conflicts.append(Conflict(_KIND_TO_CONFLICT[h.kind],
                                          f"Option {o.id} violates '{h.constraint_id}': {h.description}",
                                          o.supporters))
            for b in o.breakers:
                conflicts.append(Conflict(ConflictKind.AUTHORITY,
                                          f"Option {o.id} trips circuit breaker '{b}'", o.supporters))

        clean = [o for o in viable if o.clean]
        if len(options) > 1 and len(clean) == 1:
            chosen: Optional[Option] = clean[0]
            reasons.append(f"Option {chosen.id} is the only one that needs no exception; "
                           "hard limits are not preferences, so it prevails.")
        elif len(options) > 1:
            chosen = None
            if len(clean) == 0:
                reasons.append("Every viable option needs an exception or trips a breaker. "
                               "Producing a decision package for the accountable humans.")
            else:
                conflicts.append(Conflict(ConflictKind.PRIORITY,
                                          "Several compliant options exist and the constitution "
                                          "defines no ranking between them.",
                                          [s for o in clean for s in o.supporters]))
                reasons.append("Several compliant options; a human must choose between objectives.")
        else:
            chosen = viable[0]

        if chosen is not None and chosen.clean and chosen.authority.kind == "agent":
            reasons.append(f"Option {chosen.id}: within the agent's decision rights, no exceptions needed.")
            return self._finish(Verdict.COMMIT, chosen, options, conflicts, [], notes, reasons)

        package = [chosen] if chosen is not None else viable
        if chosen is not None and chosen.authority.kind == "human":
            conflicts.append(Conflict(ConflictKind.AUTHORITY,
                                      f"Agents may recommend but not decide '{chosen.decision_class}' "
                                      f"here; {chosen.authority.approver} decides.", chosen.supporters))
        approvers = sorted({a for o in package for a in o.approvers})
        return self._finish(Verdict.ESCALATE, chosen, package, conflicts, approvers, notes, reasons)

    # ---------------------------------------------------------------- internals
    def _concurrency_conflicts(self, proposals: list[Proposal]) -> list[Conflict]:
        by_subject: dict[str, list[Proposal]] = {}
        for p in proposals:
            by_subject.setdefault(p.subject, []).append(p)
        out = []
        for subject, ps in by_subject.items():
            versions = {p.state_version for p in ps if p.state_version is not None}
            if len(versions) > 1:
                out.append(Conflict(ConflictKind.CONCURRENCY,
                                    f"Agents acted on different versions of {subject}: {sorted(versions)}",
                                    [p.agent_id for p in ps]))
        return out

    def _resolve_evidence(self, proposals: list[Proposal], now: datetime):
        groups: dict[tuple[str, str], list[Evidence]] = {}
        for p in proposals:
            for e in p.evidence:
                groups.setdefault((e.subject, e.key), []).append(e)

        facts: dict[str, dict[str, Any]] = {}
        conflicts: list[Conflict] = []
        notes: list[str] = []
        for (subject, key), evs in groups.items():
            policy = self.constitution.sources.get(key)
            fresh = list(evs)
            if policy and policy.max_age_days is not None:
                limit = timedelta(days=policy.max_age_days)
                fresh = [e for e in evs if now - e.aware_as_of() <= limit]
                for e in evs:
                    if all(e is not f for f in fresh):
                        notes.append(f"Ignored stale {subject}.{key} from {e.source} "
                                     f"(as of {e.aware_as_of():%Y-%m-%d}, max age {policy.max_age_days:g} days).")
                if not fresh:
                    conflicts.append(Conflict(ConflictKind.DATA,
                                              f"All evidence for {subject}.{key} is stale.",
                                              sorted({e.source for e in evs})))
                    continue

            def rank(e: Evidence) -> int:
                if policy and e.source in policy.precedence:
                    return policy.precedence.index(e.source)
                return len(policy.precedence) if policy else 0

            best = min(rank(e) for e in fresh)
            top = [e for e in fresh if rank(e) == best]
            if len({repr(e.value) for e in top}) > 1:
                conflicts.append(Conflict(
                    ConflictKind.DATA,
                    f"Unresolved disagreement on {subject}.{key}: "
                    + ", ".join(f"{e.source}={e.value!r}" for e in top),
                    sorted({e.source for e in top})))
                continue
            chosen = top[0]
            facts.setdefault(subject, {})[key] = chosen.value
            for e in fresh:
                if rank(e) > best and repr(e.value) != repr(chosen.value):
                    notes.append(f"{subject}.{key}: {chosen.source} ({chosen.value!r}) overrides "
                                 f"{e.source} ({e.value!r}) by source precedence.")
        return facts, conflicts, notes

    def _build_options(self, proposals: list[Proposal], facts: dict[str, dict[str, Any]]) -> list[Option]:
        grouped: dict[str, list[Proposal]] = {}
        for p in proposals:
            grouped.setdefault(p.option, []).append(p)
        options = []
        for oid, ps in grouped.items():
            first = ps[0]
            options.append(Option(
                id=oid, decision_class=first.decision_class, subject=first.subject,
                supporters=[p.agent_id for p in ps], params=dict(first.params),
                reversible=all(p.reversible for p in ps), impact=max(p.impact for p in ps),
                facts=dict(facts.get(first.subject, {}))))
        return options

    def _ctx(self, o: Option) -> dict[str, Any]:
        return {"decision_class": o.decision_class, "params": o.params, "facts": o.facts,
                "reversible": o.reversible, "impact": o.impact}

    def _applies(self, constraint, o: Option) -> bool:
        return constraint.decision_classes is None or o.decision_class in constraint.decision_classes

    def _missing_evidence(self, o: Option) -> list[Conflict]:
        out = []
        for c in self.constitution.constraints:
            if not self._applies(c, o):
                continue
            missing = [k for k in c.needs if k not in o.facts]
            if missing:
                out.append(Conflict(ConflictKind.DATA,
                                    f"Option {o.id}: constraint '{c.id}' needs {missing} for {o.subject}, "
                                    "but no usable evidence exists. Failing closed.", o.supporters))
        return out

    def _evaluate_option(self, o: Option) -> None:
        ctx = self._ctx(o)
        for c in self.constitution.constraints:
            if self._applies(c, o) and evaluate(c.when, ctx):
                o.hits.append(ConstraintHit(c.id, c.kind, c.description, c.exception_approver))
                if c.exception_approver is None:
                    o.blocked_reasons.append(f"hard limit '{c.id}' has no exception path")
        right = self.constitution.decision_rights.get(o.decision_class)
        if right is None:
            o.authority = Authority("forbidden")
            o.blocked_reasons.append(f"no decision right is defined for '{o.decision_class}' (deny by default)")
        else:
            rule = next((r for r in right.rules if evaluate(r.when, ctx)), right.default)
            o.authority = Authority(rule.authority, rule.approver)
        for b in self.constitution.breakers:
            if evaluate(b.when, ctx):
                o.breakers.append(b.id)
        approvers = {h.exception_approver for h in o.hits if h.exception_approver}
        if o.authority.kind == "human" and o.authority.approver:
            approvers.add(o.authority.approver)
        approvers |= {b.escalate_to for b in self.constitution.breakers if b.id in o.breakers}
        o.approvers = sorted(approvers)

    def _finish(self, verdict, chosen, options, conflicts, approvers, notes, reasons) -> Resolution:
        res = Resolution(verdict, chosen, options, conflicts, approvers, notes, reasons, str(uuid.uuid4()))
        if self.ledger is not None:
            record = res.to_dict()
            record["timestamp"] = self.clock().isoformat()
            self.ledger.append(record)
        return res
