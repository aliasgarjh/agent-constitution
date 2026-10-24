# agent-constitution

**Decision rights and arbitration for multi-agent systems. Who decides when your agents disagree?**

Read the introductory LinkedIn article: [When AI Agents Disagree, Who Decides?](https://www.linkedin.com/pulse/when-ai-agents-disagree-who-decides-hint-its-agent-ali-asgar-juzer-cd9ae).

Orchestration frameworks (LangGraph, LangChain, Microsoft Agent Framework and friends) decide *who does the work*.
`agent-constitution` decides *whose judgment prevails* when properly authorized agents propose incompatible actions.
It is the layer behind the idea that **access is not authority** and **orchestration is not arbitration**.

> Status: **alpha (0.1)**. A small, dependency-free decision layer with a tested reference implementation.
> It is not a sandbox or a security boundary: pair it with real enforcement at the tool/API layer.

## The problem in one scenario

A procurement agent finds a supplier that is 18% cheaper. A security agent flags its third-party risk. A delivery agent
warns that rejecting it jeopardizes a customer commitment. A finance agent notes that the safer alternative breaks the
budget. Nobody is malfunctioning. Everyone is defensible. The conclusions cannot all be executed.

```bash
pip install -e ".[dev]"
python examples/supplier_dispute.py
```

```
VERDICT: ESCALATE

Evidence notes:
  - supplier:A.risk_tier: grc_system (3) overrides vendor_questionnaire (2) by source precedence.

Decision package:
  Option A  (backed by procurement-agent, delivery-agent)
    needs exception 'risk-tier' from security_risk_owner
  Option B  (backed by security-agent)
    needs exception 'budget-envelope' from finance_director
  Option C  (backed by finance-agent)
    needs exception 'customer-commitment' from account_owner
```

The system did not vote, average, or ask an LLM to be the judge. It diagnosed the conflict, applied source precedence,
separated hard limits from exceptions, and handed the accountable humans a decision package, with a tamper-evident record.

## How it works

Agents emit `Proposal`s. The `Arbiter` resolves them against a `Constitution` and returns a `Resolution`.

| Step | What happens | Constitution section |
|---|---|---|
| 1. Concurrency | Did agents act on different versions of the same state? | n/a |
| 2. Evidence | Drop stale claims, apply source precedence, flag real contradictions, fail closed on missing evidence | `sources`, `constraints[].needs` |
| 3. Options | Merge proposals that are the same course of action | n/a |
| 4. Constraints | Hard limits (no exception path) vs. limits with a named exception approver | `constraints` |
| 5. Decision rights | Who may decide this class of decision, under which conditions? Deny by default | `decision_rights` |
| 6. Circuit breakers | Stop autonomous execution regardless (e.g. irreversible and high impact) | `breakers` |
| 7. Verdict | `commit`, `escalate` (with decision package), `block`, or `refresh_evidence` | n/a |
| 8. Record | Append to a hash-chained ledger | `Ledger` |

Conflict kinds diagnosed: data and freshness, concurrency and sequencing, policy, resources, priorities, and authority.
*Diagnose before you adjudicate.*

## The constitution

Plain YAML (or a dict). See [`examples/constitution.yaml`](examples/constitution.yaml).

```yaml
constraints:
  - id: risk-tier
    kind: policy                     # policy | resource | priority
    when: {field: facts.risk_tier, op: ">", value: 2}
    needs: [risk_tier]               # no evidence => fail closed
    exception_approver: security_risk_owner   # omit => hard limit, no exception path

decision_rights:
  award_contract:
    rules:
      - when: {field: params.cost, op: "<=", value: 50000}
        authority: agent
    default: {authority: human, approver: procurement_director}

sources:
  risk_tier:
    precedence: [grc_system, vendor_questionnaire, agent_inference]
    max_age_days: 90

breakers:
  - id: irreversible-high-impact
    when: {all: [{field: reversible, op: "==", value: false}, {field: impact, op: ">", value: 1000000}]}
    escalate_to: executive_sponsor
```

Conditions use a tiny declarative language (`==  !=  >  >=  <  <=  in  not_in  exists`, plus `all` / `any` / `not`).
There is no `eval`. Validate a file with `python -m agent_constitution validate examples/constitution.yaml`.

## Use it with an orchestrator

The arbiter is a plain function over state, so it drops into any graph framework as a node.

```python
from agent_constitution import Arbiter, Constitution
from agent_constitution.integrations.graph import make_arbiter_node, route_on_verdict

arbiter = Arbiter(Constitution.from_yaml("constitution.yaml"))

graph.add_node("arbiter", make_arbiter_node(arbiter))            # reads state["proposals"]
graph.add_conditional_edges("arbiter", route_on_verdict(),       # commit | escalate | block | refresh_evidence
    {"commit": "execute", "escalate": "human_review",
     "block": "reject", "refresh_evidence": "refresh_data"})
```

| Framework | Status |
|---|---|
| Plain Python / dict state | Tested |
| LangGraph | Tested (`tests/test_graph_integration.py`) |
| LangChain, Microsoft Agent Framework, others | Same pattern should work; not yet tested here. PRs welcome |

## Design principles

1. **Hard limits are not preferences.** A constraint without an exception approver cannot be argued past.
2. **Deny by default.** A decision class with no defined right is blocked.
3. **Fail closed on missing evidence.** If a constraint needs a fact nobody can source, nothing is committed.
4. **Source precedence over confidence of tone.** Authoritative, fresh evidence beats a persuasive agent.
5. **Humans at boundaries of accountability, not at every step.**
6. **Every resolution leaves a record** that a later reader can verify.

## Limitations (read these)

- It decides; it does not enforce. A compromised or buggy executor can ignore a verdict.
- The ledger is tamper-*evident* (hash chain), not tamper-proof. Anchor it externally for stronger guarantees.
- When several compliant options exist, there is no automatic ranking yet; it escalates.
- Rules are only as good as the organization's real decision rights. If those are unclear, this will make that visible.

## Roadmap

- Definition and interpretation conflicts (agents answering different questions)
- Objective ranking / weighted precedence between compliant options
- Async approval workflow and reversibility windows
- Adapters for more orchestrators; OpenTelemetry export of decision records

## Development

```bash
pip install -e ".[dev,langgraph]"
pytest -q
```

## Author

[Ali Asgar Juzer](https://linkedin.com/in/aliasgarjuzer)

MIT licensed.
