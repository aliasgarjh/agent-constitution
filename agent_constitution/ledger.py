"""Append-only, hash-chained decision ledger (tamper-evident, not tamper-proof)."""
from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Optional

GENESIS = "0" * 64


class Ledger:
    def __init__(self, path: Optional[str] = None):
        self.path = path
        self.entries: list[dict[str, Any]] = []
        if path and os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                self.entries = [json.loads(line) for line in f if line.strip()]

    @staticmethod
    def _digest(prev: str, record: dict[str, Any]) -> str:
        body = json.dumps(record, sort_keys=True, default=str)
        return hashlib.sha256((prev + body).encode()).hexdigest()

    def append(self, record: dict[str, Any]) -> dict[str, Any]:
        prev = self.entries[-1]["hash"] if self.entries else GENESIS
        entry = {"prev": prev, "hash": self._digest(prev, record), "record": record}
        self.entries.append(entry)
        if self.path:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, sort_keys=True, default=str) + "\n")
        return entry

    def verify(self) -> bool:
        prev = GENESIS
        for e in self.entries:
            if e["prev"] != prev or e["hash"] != self._digest(prev, e["record"]):
                return False
            prev = e["hash"]
        return True
