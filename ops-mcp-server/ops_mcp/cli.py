"""The person's side: see what the agent asked for, approve or deny it, read the audit log.

    python -m ops_mcp pending
    python -m ops_mcp approve apr-1a2b3c4d      # shows the action and asks you to confirm
    python -m ops_mcp deny apr-1a2b3c4d
    python -m ops_mcp audit
"""
from __future__ import annotations

import argparse
import getpass
import json
import sys

from .approvals import ApprovalError, ApprovalStore
from .audit import AuditLog


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="ops_mcp")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("pending")
    for n in ("approve", "deny"):
        s = sub.add_parser(n)
        s.add_argument("approval_id")
    sub.add_parser("audit")
    args = p.parse_args(argv)
    audit = AuditLog()
    store = ApprovalStore(audit=audit)
    if args.cmd == "pending":
        for aid, rec in store.pending().items():
            print(f"{aid}  {rec['action']} {json.dumps(rec['params'])}\n   reason: {rec['reason']}")
        return 0
    if args.cmd == "audit":
        for line in audit.lines():
            print(json.dumps(line))
        return 0
    rec = store._load().get(args.approval_id)
    if rec is None:
        print(f"no approval {args.approval_id}")
        return 1
    print(f"{rec['action']} {json.dumps(rec['params'])}\n  reason given by the agent: {rec['reason']}")
    if not sys.stdin.isatty():
        print("this needs a person at a terminal to confirm")
        return 1
    if input(f"{args.cmd} this? [y/N] ").strip().lower() not in ("y", "yes"):
        print("left pending")
        return 0
    try:
        store.decide(args.approval_id, args.cmd == "approve", by=getpass.getuser())
    except ApprovalError as exc:
        print(exc)
        return 1
    print(f"{args.cmd}d")
    return 0
