import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, ROOT)

from agent_constitution import Arbiter, Constitution, Evidence, Proposal  # noqa: E402

NOW = datetime(2026, 10, 20, 9, 0, tzinfo=timezone.utc)


@pytest.fixture
def constitution():
    return Constitution.from_yaml(os.path.join(ROOT, "examples", "constitution.yaml"))


@pytest.fixture
def arbiter(constitution):
    return Arbiter(constitution, clock=lambda: NOW)


def tier(subject, value, source="grc_system", days_old=5):
    return Evidence(subject, "risk_tier", value, source, NOW - timedelta(days=days_old))


def award(agent, option, cost=40_000, delay=0, subject=None, evidence=None, **kw):
    return Proposal(agent, "award_contract", option=option, subject=subject or f"supplier:{option}",
                    params={"cost": cost, "delay_days": delay}, evidence=evidence or [], **kw)
