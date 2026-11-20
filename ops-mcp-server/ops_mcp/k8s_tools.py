"""Kubernetes tools, run through kubectl with a fixed verb for each tool and no shell.

Every command is built from a list, every name is checked (so none can start with '-' and become a flag), and the
only verbs ever used are get, logs and, for the approved write, rollout restart and rollout status.
"""
from __future__ import annotations

import json
import os
import subprocess
from typing import Callable, List, Optional, Tuple

from . import safety
from .approvals import ApprovalStore

Runner = Callable[[List[str]], Tuple[int, str, str]]
KINDS = ("pods", "deployments", "services", "events", "nodes", "replicasets", "namespaces")
DEFAULT_PROTECTED = ("kube-system", "kube-public", "kube-node-lease")


def subprocess_runner(args: List[str]) -> Tuple[int, str, str]:
    cmd = ["kubectl"]
    if os.environ.get("OPS_MCP_KUBE_CONTEXT"):
        cmd += ["--context", safety.k8s_name(os.environ["OPS_MCP_KUBE_CONTEXT"], "context")]
    p = subprocess.run(cmd + args, capture_output=True, text=True, timeout=30)
    return p.returncode, p.stdout, p.stderr


class K8sTools:
    def __init__(self, runner: Optional[Runner] = None, approvals: Optional[ApprovalStore] = None,
                 protected_namespaces: Optional[Tuple[str, ...]] = None) -> None:
        self.run = runner or subprocess_runner
        self.approvals = approvals
        extra = tuple(n for n in os.environ.get("OPS_MCP_PROTECTED_NAMESPACES", "").split(",") if n)
        self.protected = tuple(protected_namespaces) if protected_namespaces is not None else DEFAULT_PROTECTED + extra

    def _kubectl(self, args: List[str]) -> str:
        rc, out, err = self.run(args)
        if rc != 0:
            raise RuntimeError(safety.clip(f"kubectl {args[0]} failed: {err.strip() or out.strip()}", 600))
        return out

    # ---- read only
    def get(self, kind: str, namespace: str = "default", name: Optional[str] = None) -> dict:
        if kind not in KINDS:
            raise safety.InvalidInput(f"kind must be one of {', '.join(KINDS)}")
        safety.k8s_name(namespace, "namespace")
        args = ["get", kind] + ([] if kind in ("nodes", "namespaces") else ["-n", namespace])
        if name:
            args.append(safety.k8s_name(name))
        data = json.loads(self._kubectl(args + ["-o", "json"]))
        items = data["items"] if data.get("kind") == "List" else [data]
        return {"kind": kind, "namespace": namespace, "items": [self._summarise(kind, i) for i in items][:100]}

    @staticmethod
    def _summarise(kind: str, o: dict) -> dict:
        meta = {"name": o["metadata"]["name"]}
        st = o.get("status", {})
        if kind == "pods":
            cs = st.get("containerStatuses", [])
            reasons = [(c["state"].get("waiting") or c["state"].get("terminated") or {}).get("reason") for c in cs]
            return {**meta, "phase": st.get("phase"), "ready": f"{sum(1 for c in cs if c.get('ready'))}/{len(cs)}",
                    "restarts": sum(c.get("restartCount", 0) for c in cs), "reasons": [r for r in reasons if r], "node": o.get("spec", {}).get("nodeName")}
        if kind == "deployments":
            return {**meta, "desired": o.get("spec", {}).get("replicas"), "ready": st.get("readyReplicas", 0), "updated": st.get("updatedReplicas", 0),
                    "available": st.get("availableReplicas", 0)}
        if kind == "events":
            return {**meta, "type": o.get("type"), "reason": o.get("reason"), "object": o.get("involvedObject", {}).get("name"),
                    "message": safety.clip(safety.redact(o.get("message", "")), 300), "count": o.get("count")}
        if kind == "nodes":
            ready = next((c["status"] for c in st.get("conditions", []) if c["type"] == "Ready"), None)
            return {**meta, "ready": ready}
        return meta

    def logs(self, namespace: str, pod: str, tail: int = 100, previous: bool = False) -> dict:
        safety.k8s_name(namespace, "namespace")
        safety.k8s_name(pod, "pod")
        safety.bounded(tail, 1, 500, "tail")
        args = ["logs", pod, "-n", namespace, f"--tail={tail}"] + (["--previous"] if previous else [])
        return {"pod": pod, "log": safety.clip(safety.redact(self._kubectl(args)))}

    # ---- changes state, only with an approval
    def rollout_restart(self, namespace: str, deployment: str, dry_run: bool = True, approval_id: Optional[str] = None) -> dict:
        safety.k8s_name(namespace, "namespace")
        safety.k8s_name(deployment, "deployment")
        if namespace in self.protected:
            return {"status": "refused", "reason": f"namespace {namespace} is protected; this tool does not change it"}
        target = ["rollout", "restart", f"deployment/{deployment}", "-n", namespace]
        if dry_run:
            return {"status": "dry_run", "server_says": self._kubectl(target + ["--dry-run=server", "-o", "name"]).strip(),
                    "note": "call request_approval, have a person approve, then repeat with dry_run=false"}
        self.approvals.consume(approval_id, "k8s_rollout_restart", {"namespace": namespace, "deployment": deployment})
        out = self._kubectl(target).strip()
        try:
            rollout = self._kubectl(["rollout", "status", f"deployment/{deployment}", "-n", namespace, "--timeout=60s"]).strip()
        except RuntimeError as exc:   # the restart was issued; only the wait failed, so say that rather than raise
            return {"status": "restarted_not_confirmed", "kubectl": out, "rollout": str(exc)}
        return {"status": "restarted", "kubectl": out, "rollout": rollout}
