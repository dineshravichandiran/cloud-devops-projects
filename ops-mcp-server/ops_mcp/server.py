"""MCP server over stdio.

    python -m ops_mcp.server                      # read tools, plus approval-gated write tools
    OPS_MCP_READ_ONLY=1 python -m ops_mcp.server  # read tools only: the write tools are not registered at all

Add to an MCP client:
    { "mcpServers": { "ops": { "command": "python", "args": ["-m", "ops_mcp.server"], "cwd": "/path/to/ops-mcp-server" } } }
"""
from __future__ import annotations

import os
from typing import Callable, List, Optional

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from . import safety
from .approvals import ApprovalError, ApprovalStore
from .audit import AuditLog
from .aws_tools import AwsTools
from .k8s_tools import K8sTools

READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True)
WRITES = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=True)
ASKS = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)

# The write actions and the exact parameters each one takes. An approval is bound to these.
WRITE_ACTIONS = {
    "k8s_rollout_restart": {"namespace": str, "deployment": str},
    "aws_asg_set_capacity": {"name": str, "desired": int},
}


def _validate_params(action: str, params: dict) -> dict:
    spec = WRITE_ACTIONS.get(action)
    if spec is None:
        raise safety.InvalidInput(f"action must be one of {', '.join(WRITE_ACTIONS)}")
    if set(params) != set(spec):
        raise safety.InvalidInput(f"{action} takes exactly: {', '.join(spec)}")
    for k, t in spec.items():
        if not isinstance(params[k], t) or isinstance(params[k], bool):
            raise safety.InvalidInput(f"{k} must be a {t.__name__}")
    if action == "k8s_rollout_restart":
        safety.k8s_name(params["namespace"], "namespace"); safety.k8s_name(params["deployment"], "deployment")
    else:
        safety.asg_name(params["name"]); safety.bounded(params["desired"], 0, 1000, "desired")
    return params


def build_server(aws: Optional[AwsTools] = None, k8s: Optional[K8sTools] = None, approvals: Optional[ApprovalStore] = None,
                 audit: Optional[AuditLog] = None, read_only: Optional[bool] = None) -> FastMCP:
    audit = audit or AuditLog()
    approvals = approvals or ApprovalStore(audit=audit)
    aws = aws or AwsTools(approvals=approvals)
    k8s = k8s or K8sTools(approvals=approvals)
    aws.approvals, k8s.approvals = aws.approvals or approvals, k8s.approvals or approvals
    if read_only is None:
        read_only = os.environ.get("OPS_MCP_READ_ONLY", "").lower() in ("1", "true", "yes")
    server = FastMCP("ops-mcp")

    def guarded(tool: str, fn: Callable[..., dict], **args) -> dict:
        """Run a tool, audit it, and turn expected failures into a result the model can read instead of a crash."""
        try:
            out = fn(**args)
            audit.write("agent", "tool_call", tool=tool, args=args, status=out.get("status", "ok") if isinstance(out, dict) else "ok")
            return out
        except (safety.InvalidInput, ApprovalError) as exc:
            audit.write("agent", "tool_refused", tool=tool, args=args, reason=str(exc))
            return {"status": "refused", "reason": str(exc)}
        except Exception as exc:   # AWS or kubectl errors: report them, never take the server down
            audit.write("agent", "tool_error", tool=tool, args=args, error=f"{type(exc).__name__}: {str(exc)[:300]}")
            return {"status": "error", "error": f"{type(exc).__name__}: {str(exc)[:300]}"}

    # ---- read only
    @server.tool(annotations=READ_ONLY)
    def aws_asg_status(name: str) -> dict:
        """Capacity and instance health of an Auto Scaling group."""
        return guarded("aws_asg_status", aws.asg_status, name=name)

    @server.tool(annotations=READ_ONLY)
    def aws_target_health(target_group_arn: str) -> dict:
        """Health of each target in an ALB/NLB target group, with the reason when unhealthy."""
        return guarded("aws_target_health", aws.target_health, target_group_arn=target_group_arn)

    @server.tool(annotations=READ_ONLY)
    def aws_alarms(state: str = "ALARM", name_prefix: Optional[str] = None) -> dict:
        """CloudWatch alarms in a state (ALARM by default), optionally filtered by name prefix."""
        return guarded("aws_alarms", aws.alarms, state=state, name_prefix=name_prefix)

    @server.tool(annotations=READ_ONLY)
    def aws_instance_status(instance_ids: List[str]) -> dict:
        """EC2 state, system status and instance status for up to 20 instances."""
        return guarded("aws_instance_status", aws.instance_status, instance_ids=instance_ids)

    @server.tool(annotations=READ_ONLY)
    def aws_recent_logs(log_group: str, minutes: int = 15, pattern: Optional[str] = None, limit: int = 50) -> dict:
        """Recent CloudWatch Logs events (up to 180 minutes, 200 events). Common secret patterns are masked."""
        return guarded("aws_recent_logs", aws.recent_logs, log_group=log_group, minutes=minutes, pattern=pattern, limit=limit)

    @server.tool(annotations=READ_ONLY)
    def k8s_get(kind: str, namespace: str = "default", name: Optional[str] = None) -> dict:
        """Summarised pods, deployments, services, events, nodes, replicasets or namespaces."""
        return guarded("k8s_get", k8s.get, kind=kind, namespace=namespace, name=name)

    @server.tool(annotations=READ_ONLY)
    def k8s_logs(namespace: str, pod: str, tail: int = 100, previous: bool = False) -> dict:
        """Last lines of a pod's log (or the previous container's with previous=true). Common secret patterns are masked."""
        return guarded("k8s_logs", k8s.logs, namespace=namespace, pod=pod, tail=tail, previous=previous)

    if read_only:
        return server

    # ---- writes: asking is free, acting needs a person's approval
    @server.tool(annotations=ASKS)
    def request_approval(action: str, params: dict, reason: str) -> dict:
        """Ask a person to approve one write action with exact parameters. Returns an approval id; a person approves it in a terminal
        (python -m ops_mcp approve <id>). Actions: k8s_rollout_restart {namespace, deployment}, aws_asg_set_capacity {name, desired}."""
        def ask(action: str, params: dict, reason: str) -> dict:
            if not reason.strip():
                raise safety.InvalidInput("give a reason")
            aid = approvals.request(action, _validate_params(action, params), reason)
            return {"status": "pending", "approval_id": aid, "next": f"a person must run: python -m ops_mcp approve {aid}"}
        return guarded("request_approval", ask, action=action, params=params, reason=reason)

    @server.tool(annotations=WRITES)
    def k8s_rollout_restart(namespace: str, deployment: str, dry_run: bool = True, approval_id: Optional[str] = None) -> dict:
        """Restart a deployment's pods one by one. Dry-run by default; dry_run=false needs a person-approved approval_id for exactly these arguments.
        Never touches kube-system, kube-public, kube-node-lease or any namespace in OPS_MCP_PROTECTED_NAMESPACES."""
        return guarded("k8s_rollout_restart", k8s.rollout_restart, namespace=namespace, deployment=deployment, dry_run=dry_run, approval_id=approval_id)

    @server.tool(annotations=WRITES)
    def aws_asg_set_capacity(name: str, desired: int, dry_run: bool = True, approval_id: Optional[str] = None) -> dict:
        """Set an Auto Scaling group's desired capacity, within its existing min and max (never changes those). Dry-run by default;
        dry_run=false needs a person-approved approval_id for exactly these arguments."""
        return guarded("aws_asg_set_capacity", aws.set_capacity, name=name, desired=desired, dry_run=dry_run, approval_id=approval_id)

    return server


if __name__ == "__main__":
    build_server().run()
