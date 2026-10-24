"""The supplier dispute from the article, end to end.

Run:  python examples/supplier_dispute.py
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone

from agent_constitution import Arbiter, Constitution, Evidence, Ledger, Proposal

HERE = os.path.dirname(__file__)
NOW = datetime.now(timezone.utc)


def build_proposals() -> list[Proposal]:
    def tier(subject, value, source, days_old):
        return Evidence(subject, "risk_tier", value, source, NOW - timedelta(days=days_old))

    return [
        # Procurement wants the cheap supplier and trusts the vendor's own questionnaire (tier 2).
        Proposal("procurement-agent", "award_contract", option="A", subject="supplier:A",
                 params={"cost": 400_000, "delay_days": 0},
                 evidence=[tier("supplier:A", 2, "vendor_questionnaire", 40)],
                 rationale="18% cheaper than the alternatives.", reversible=False, impact=400_000),
        # Delivery also backs A: it is the only option that is cheap AND on time.
        Proposal("delivery-agent", "award_contract", option="A", subject="supplier:A",
                 params={"cost": 400_000, "delay_days": 0},
                 rationale="Protects the customer commitment.", reversible=False, impact=400_000),
        # Security flags A (GRC tier 3) and proposes the safer supplier B.
        Proposal("security-agent", "award_contract", option="B", subject="supplier:B",
                 params={"cost": 620_000, "delay_days": 0},
                 evidence=[tier("supplier:A", 3, "grc_system", 5), tier("supplier:B", 1, "grc_system", 5)],
                 rationale="A carries elevated third-party risk.", reversible=False, impact=620_000),
        # Finance proposes C: safe and within budget, but late.
        Proposal("finance-agent", "award_contract", option="C", subject="supplier:C",
                 params={"cost": 450_000, "delay_days": 21},
                 evidence=[tier("supplier:C", 1, "grc_system", 8)],
                 rationale="Stays inside the approved envelope.", reversible=False, impact=450_000),
    ]


def main() -> None:
    constitution = Constitution.from_yaml(os.path.join(HERE, "constitution.yaml"))
    ledger = Ledger()  # pass a file path to persist: Ledger("decisions.jsonl")
    arbiter = Arbiter(constitution, ledger=ledger)

    res = arbiter.resolve(build_proposals())

    print(f"VERDICT: {res.verdict.value.upper()}\n")
    print("Evidence notes:")
    for n in res.evidence_notes:
        print(f"  - {n}")
    print("\nDecision package:")
    for o in res.options:
        print(f"  Option {o.id}  (backed by {', '.join(o.supporters)})")
        print(f"    cost=${o.params['cost']:,}  delay={o.params['delay_days']}d  facts={o.facts}")
        for h in o.hits:
            print(f"    needs exception '{h.constraint_id}' from {h.exception_approver}")
        print(f"    approvers: {', '.join(o.approvers)}")
    print("\nConflicts diagnosed:")
    for c in res.conflicts:
        print(f"  [{c.kind.value}] {c.description}")
    print(f"\nLedger intact: {ledger.verify()}  (entries: {len(ledger.entries)})")
    print("\nMachine-readable record:\n" + json.dumps(res.to_dict(), indent=2)[:600] + "\n  ...")


if __name__ == "__main__":
    main()
