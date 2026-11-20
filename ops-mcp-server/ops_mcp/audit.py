"""Append-only JSON-lines audit log: every tool call, with who asked and what came of it."""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
from typing import List, Optional


def default_dir() -> Path:
    return Path(os.environ.get("OPS_MCP_STATE_DIR") or Path.home() / ".ops-mcp")


class AuditLog:
    def __init__(self, directory: Optional[Path] = None) -> None:
        self.dir = Path(directory or default_dir())
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path = self.dir / "audit.jsonl"

    def write(self, actor: str, event: str, **fields) -> None:
        line = {"at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "actor": actor, "event": event, **fields}
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(line, default=str) + "\n")

    def lines(self) -> List[dict]:
        return [json.loads(l) for l in self.path.read_text().splitlines() if l.strip()] if self.path.exists() else []
