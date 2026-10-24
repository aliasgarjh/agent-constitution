from datetime import timedelta

from agent_constitution import ConflictKind, Evidence, Ledger, Proposal, Verdict
from conftest import NOW, award, tier


def test_routine_decision_within_rights_commits(arbiter):
    p = award("procurement-agent", "A", cost=10_000, evidence=[tier("supplier:A", 1)])
    res = arbiter.resolve([p])
    assert res.verdict == Verdict.COMMIT
    assert res.chosen.id == "A" and res.approvers == []


def test_above_threshold_needs_named_human(arbiter):
    p = award("procurement-agent", "A", cost=100_000, evidence=[tier("supplier:A", 1)])
    res = arbiter.resolve([p])
    assert res.verdict == Verdict.ESCALATE
    assert res.approvers == ["procurement_director"]
    assert any(c.kind == ConflictKind.AUTHORITY for c in res.conflicts)


def test_supplier_dispute_escalates_with_three_options(arbiter):
    proposals = [
        award("procurement-agent", "A", cost=400_000, evidence=[tier("supplier:A", 2, "vendor_questionnaire", 40)]),
        award("delivery-agent", "A", cost=400_000),
        award("security-agent", "B", cost=620_000,
              evidence=[tier("supplier:A", 3), tier("supplier:B", 1)]),
        award("finance-agent", "C", cost=450_000, delay=21, evidence=[tier("supplier:C", 1)]),
    ]
    res = arbiter.resolve(proposals)
    assert res.verdict == Verdict.ESCALATE
    assert res.chosen is None
    by_id = {o.id: o for o in res.options}
    assert set(by_id) == {"A", "B", "C"}
    assert by_id["A"].supporters == ["procurement-agent", "delivery-agent"]
    assert "security_risk_owner" in by_id["A"].approvers
    assert "finance_director" in by_id["B"].approvers
    assert "account_owner" in by_id["C"].approvers
    # Source precedence: GRC (tier 3) beat the vendor questionnaire (tier 2).
    assert by_id["A"].facts["risk_tier"] == 3
    assert any("overrides vendor_questionnaire" in n for n in res.evidence_notes)
    kinds = {c.kind for c in res.conflicts}
    assert {ConflictKind.POLICY, ConflictKind.RESOURCE, ConflictKind.PRIORITY} <= kinds


def test_only_compliant_option_prevails_over_options_needing_exceptions(arbiter):
    proposals = [
        award("procurement-agent", "A", cost=40_000, evidence=[tier("supplier:A", 3)]),
        award("security-agent", "B", cost=40_000, evidence=[tier("supplier:B", 1)]),
    ]
    res = arbiter.resolve(proposals)
    assert res.chosen.id == "B"
    assert res.verdict == Verdict.COMMIT


def test_stale_evidence_is_ignored_and_triggers_refresh_if_nothing_fresh(arbiter):
    old = Evidence("supplier:A", "risk_tier", 1, "grc_system", NOW - timedelta(days=200))
    res = arbiter.resolve([award("procurement-agent", "A", evidence=[old])])
    assert res.verdict == Verdict.REFRESH
    assert any(c.kind == ConflictKind.DATA for c in res.conflicts)


def test_unresolved_contradiction_at_same_precedence_triggers_refresh(arbiter):
    e1 = tier("supplier:A", 1, "grc_system")
    e2 = tier("supplier:A", 3, "grc_system")
    res = arbiter.resolve([award("a1", "A", evidence=[e1]), award("a2", "A", evidence=[e2])])
    assert res.verdict == Verdict.REFRESH


def test_missing_evidence_fails_closed(arbiter):
    res = arbiter.resolve([award("procurement-agent", "A", cost=10_000)])  # no risk tier evidence
    assert res.verdict == Verdict.REFRESH
    assert any("Failing closed" in c.description for c in res.conflicts)


def test_hard_limit_without_exception_path_blocks(arbiter):
    p = award("procurement-agent", "A", cost=10_000, evidence=[tier("supplier:A", 1)])
    p.params["sanctioned"] = True
    res = arbiter.resolve([p])
    assert res.verdict == Verdict.BLOCK


def test_unknown_decision_class_is_denied_by_default(arbiter):
    p = Proposal("rogue-agent", "wire_transfer", option="X", subject="acct:1", params={"cost": 1})
    res = arbiter.resolve([p])
    assert res.verdict == Verdict.BLOCK


def test_concurrent_state_versions_trigger_refresh(arbiter):
    a = award("a1", "A", cost=10_000, evidence=[tier("supplier:A", 1)], state_version="v1")
    b = award("a2", "A", cost=10_000, state_version="v2")
    res = arbiter.resolve([a, b])
    assert res.verdict == Verdict.REFRESH
    assert any(c.kind == ConflictKind.CONCURRENCY for c in res.conflicts)


def test_circuit_breaker_stops_irreversible_high_impact_even_within_rights(constitution):
    from agent_constitution import Arbiter
    # Give the agent broad rights so only the breaker can stop it.
    constitution.decision_rights["award_contract"].rules[0].when = None
    arb = Arbiter(constitution, clock=lambda: NOW)
    p = award("procurement-agent", "A", cost=400_000, evidence=[tier("supplier:A", 1)],
              reversible=False, impact=2_000_000)
    res = arb.resolve([p])
    assert res.verdict == Verdict.ESCALATE
    assert "executive_sponsor" in res.approvers


def test_ledger_is_hash_chained_and_tamper_evident(constitution, tmp_path):
    from agent_constitution import Arbiter
    ledger = Ledger(str(tmp_path / "decisions.jsonl"))
    arb = Arbiter(constitution, ledger=ledger, clock=lambda: NOW)
    for i in range(3):
        arb.resolve([award("a", "A", cost=10_000, evidence=[tier("supplier:A", 1)])])
    assert ledger.verify() and len(ledger.entries) == 3
    reloaded = Ledger(str(tmp_path / "decisions.jsonl"))
    assert reloaded.verify()
    reloaded.entries[1]["record"]["verdict"] = "commit-but-forged"
    assert not reloaded.verify()
