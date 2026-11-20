"""Talk to the real server over stdio, with a stand-in `kubectl` on PATH so the real subprocess path runs."""
import asyncio
import json
import os
import stat
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from ops_mcp.approvals import ApprovalStore

READ_TOOLS = {"aws_alarms", "aws_asg_status", "aws_instance_status", "aws_recent_logs", "aws_target_health", "k8s_get", "k8s_logs"}
WRITE_TOOLS = {"aws_asg_set_capacity", "k8s_rollout_restart", "request_approval"}

FAKE_KUBECTL = """#!/bin/sh
echo "$@" >> "$FAKE_KUBECTL_LOG"
case "$*" in
  *--dry-run=server*) echo "deployment.apps/web" ;;
  "rollout status"*) echo "deployment web successfully rolled out" ;;
  "rollout restart"*) echo "deployment.apps/web restarted" ;;
esac
"""


def _env(tmp_path, **extra):
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    k = bindir / "kubectl"
    k.write_text(FAKE_KUBECTL)
    k.chmod(k.stat().st_mode | stat.S_IEXEC)
    return {**os.environ, "PATH": f"{bindir}:{os.environ['PATH']}", "OPS_MCP_STATE_DIR": str(tmp_path / "state"),
            "FAKE_KUBECTL_LOG": str(tmp_path / "kubectl.log"), "AWS_DEFAULT_REGION": "ap-south-1", **extra}


def _run(env, coro):
    async def go():
        params = StdioServerParameters(command=sys.executable, args=["-m", "ops_mcp.server"], env=env)
        async with stdio_client(params) as (r, w):
            async with ClientSession(r, w) as s:
                await s.initialize()
                return await coro(s)
    return asyncio.run(go())


def _payload(result):
    return result.structuredContent or json.loads(result.content[0].text)


def test_tools_and_annotations(tmp_path):
    tools = _run(_env(tmp_path), lambda s: s.list_tools()).tools
    assert {t.name for t in tools} == READ_TOOLS | WRITE_TOOLS
    by = {t.name: t.annotations for t in tools}
    for name in READ_TOOLS:
        assert by[name].readOnlyHint and not by[name].destructiveHint, name
    for name in ("k8s_rollout_restart", "aws_asg_set_capacity"):
        assert not by[name].readOnlyHint and by[name].destructiveHint, name


def test_read_only_mode_does_not_register_any_write_tool(tmp_path):
    tools = _run(_env(tmp_path, OPS_MCP_READ_ONLY="1"), lambda s: s.list_tools()).tools
    assert {t.name for t in tools} == READ_TOOLS


def test_the_agent_cannot_approve_and_the_whole_flow_is_gated(tmp_path):
    env = _env(tmp_path)
    args = {"namespace": "shop", "deployment": "web"}

    async def ask(s):
        return _payload(await s.call_tool("request_approval", {"action": "k8s_rollout_restart", "params": args, "reason": "pods stuck"}))
    asked = _run(env, ask)
    aid = asked["approval_id"]
    assert asked["status"] == "pending"

    async def try_real(s, approval_id):
        return _payload(await s.call_tool("k8s_rollout_restart", {**args, "dry_run": False, "approval_id": approval_id}))

    # not approved yet: refused, and kubectl never saw a real restart
    assert _run(env, lambda s: try_real(s, aid))["status"] == "refused"
    # a dry run is allowed and uses the server-side dry run
    dry = _run(env, lambda s: s.call_tool("k8s_rollout_restart", args))
    assert _payload(dry)["status"] == "dry_run"
    log = (tmp_path / "kubectl.log").read_text().splitlines()
    assert all("--dry-run=server" in l for l in log)

    # a person approves (the only way: the store / CLI, not an MCP tool)
    ApprovalStore(tmp_path / "state").decide(aid, True, "dinesh")
    done = _run(env, lambda s: try_real(s, aid))
    assert done["status"] == "restarted"
    assert any(l.startswith("rollout restart") and "--dry-run" not in l for l in (tmp_path / "kubectl.log").read_text().splitlines())
    # single use
    assert _run(env, lambda s: try_real(s, aid))["status"] == "refused"

    events = [json.loads(l)["event"] for l in (tmp_path / "state" / "audit.jsonl").read_text().splitlines()]
    assert "approval_requested" in events and "approval_approved" in events and "tool_refused" in events


def test_bad_arguments_are_refused_not_crashed(tmp_path):
    env = _env(tmp_path)

    async def go(s):
        a = _payload(await s.call_tool("k8s_logs", {"namespace": "shop", "pod": "--all-containers"}))
        b = _payload(await s.call_tool("request_approval", {"action": "delete_everything", "params": {}, "reason": "x"}))
        c = _payload(await s.call_tool("request_approval", {"action": "aws_asg_set_capacity", "params": {"name": "g", "desired": "3"}, "reason": "x"}))
        d = _payload(await s.call_tool("request_approval", {"action": "k8s_rollout_restart", "params": {"namespace": "a", "deployment": "b"}, "reason": " "}))
        return a, b, c, d
    for out in _run(env, go):
        assert out["status"] == "refused", out
