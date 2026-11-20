"""Approvals for write actions.

The agent can only *ask*: `request()` creates a pending approval for one action with exact parameters.
A person approves it from a terminal (`python -m ops_mcp approve <id>`); no MCP tool can do that, so a model
cannot approve its own request. An approval is:

  bound      to one action and the exact parameters it was requested with (change a number and it no longer matches)
  single use consumed the first time it is used, whether the action then succeeds or not
  short      expires after `ttl_s` seconds (default 15 minutes) from the moment a person approves it
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import time
from pathlib import Path
from typing import Dict, Optional

from .audit import AuditLog, default_dir


class ApprovalError(Exception):
    pass


def fingerprint(action: str, params: dict) -> str:
    return hashlib.sha256(json.dumps({"a": action, "p": params}, sort_keys=True).encode()).hexdigest()[:16]


class ApprovalStore:
    def __init__(self, directory: Optional[Path] = None, audit: Optional[AuditLog] = None, ttl_s: int = 900, clock=time.time) -> None:
        self.dir = Path(directory or default_dir())
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path = self.dir / "approvals.json"
        self.audit = audit or AuditLog(self.dir)
        self.ttl_s, self.clock = ttl_s, clock

    def _load(self) -> Dict[str, dict]:
        return json.loads(self.path.read_text()) if self.path.exists() else {}

    def _save(self, data: Dict[str, dict]) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=1))
        os.replace(tmp, self.path)

    # ---- the agent's side: ask
    def request(self, action: str, params: dict, reason: str) -> str:
        data = self._load()
        approval_id = "apr-" + secrets.token_hex(4)
        data[approval_id] = {"action": action, "params": params, "fingerprint": fingerprint(action, params), "reason": reason[:300],
                             "status": "pending", "requested_at": self.clock()}
        self._save(data)
        self.audit.write("agent", "approval_requested", approval_id=approval_id, action=action, params=params, reason=reason[:300])
        return approval_id

    # ---- the person's side: decide
    def decide(self, approval_id: str, approve: bool, by: str) -> dict:
        data = self._load()
        rec = data.get(approval_id)
        if rec is None:
            raise ApprovalError(f"no approval {approval_id}")
        if rec["status"] != "pending":
            raise ApprovalError(f"{approval_id} is already {rec['status']}")
        rec["status"] = "approved" if approve else "denied"
        rec["decided_by"], rec["decided_at"] = by, self.clock()
        self._save(data)
        self.audit.write("human:" + by, "approval_" + rec["status"], approval_id=approval_id, action=rec["action"], params=rec["params"])
        return rec

    def pending(self) -> Dict[str, dict]:
        return {k: v for k, v in self._load().items() if v["status"] == "pending"}

    # ---- the server's side: check and consume, just before acting
    def consume(self, approval_id: Optional[str], action: str, params: dict) -> dict:
        if not approval_id:
            raise ApprovalError("this action needs an approval id from a person; call request_approval first")
        data = self._load()
        rec = data.get(approval_id)
        if rec is None:
            raise ApprovalError("unknown approval id")
        if rec["status"] != "approved":
            raise ApprovalError(f"approval is {rec['status']}" + (", a person has not approved it yet" if rec["status"] == "pending" else ""))
        if rec["fingerprint"] != fingerprint(action, params):
            raise ApprovalError("this approval was issued for a different action or different parameters")
        if self.clock() - rec["decided_at"] > self.ttl_s:
            rec["status"] = "expired"
            self._save(data)
            raise ApprovalError("approval expired; request a new one")
        rec["status"], rec["used_at"] = "used", self.clock()
        self._save(data)
        return rec
