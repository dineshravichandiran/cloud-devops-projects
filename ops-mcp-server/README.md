# ops-mcp-server

An [MCP](https://modelcontextprotocol.io) server that lets an AI agent look at AWS and Kubernetes while on call, and change something only when a person approves that exact change.

Reading is open. Writing is two steps the agent cannot do alone: it asks (`request_approval`), a person approves in a terminal, and only then does the write tool run, once.

## Tools

| Tool | Does | Changes anything? |
|---|---|---|
| `aws_asg_status` | Capacity and instance health of an Auto Scaling group | No |
| `aws_target_health` | State and reason for each target in a target group | No |
| `aws_alarms` | CloudWatch alarms in a state, optional name prefix | No |
| `aws_instance_status` | EC2 state, system and instance status (up to 20) | No |
| `aws_recent_logs` | Recent CloudWatch Logs events (up to 180 min, 200 events), secrets masked | No |
| `k8s_get` | Summarised pods, deployments, services, events, nodes, replicasets, namespaces | No |
| `k8s_logs` | Last lines of a pod's log, secrets masked | No |
| `request_approval` | Records a request for one write action with exact parameters | Only its own approval file |
| `k8s_rollout_restart` | Restart a deployment's pods. Dry-run by default | Yes, with approval |
| `aws_asg_set_capacity` | Set desired capacity within the group's existing min and max. Dry-run by default | Yes, with approval |

`OPS_MCP_READ_ONLY=1` registers only the first seven. The write tools do not exist in that mode, rather than existing and refusing.

## How the approval works

```
agent:   request_approval(k8s_rollout_restart, {namespace: shop, deployment: web}, "pods stuck in CrashLoopBackOff")
         -> {approval_id: apr-1a2b3c4d, status: pending}
person:  python -m ops_mcp pending
         python -m ops_mcp approve apr-1a2b3c4d        # shows the action, asks y/N, needs a real terminal
agent:   k8s_rollout_restart(shop, web, dry_run=false, approval_id=apr-1a2b3c4d)
         -> restarted, then waits for the rollout
```

An approval is **bound** to one action and its exact parameters (change the deployment or the number and it no longer matches), **single use** (consumed the first time it is used), and **short lived** (expires 15 minutes after a person approves). There is no MCP tool that approves, so a model using only this server cannot approve its own request. Every request, decision, call, refusal and error goes to `~/.ops-mcp/audit.jsonl` (`python -m ops_mcp audit`); set `OPS_MCP_STATE_DIR` to move it.

## Other guardrails

- **Fixed verbs.** kubectl runs from an argument list with no shell, and the only verbs used are `get`, `logs`, and for the approved write `rollout restart` and `rollout status`. A test asserts that `delete`, `apply`, `exec`, `edit`, `patch` and `scale` never appear.
- **Names are checked.** Kubernetes names must match the Kubernetes name pattern, so none can start with `-` and be read as a flag. Log groups, ARNs, instance ids and ASG names have their own patterns, and counts and sizes are bounded.
- **Protected namespaces.** `kube-system`, `kube-public`, `kube-node-lease` and anything in `OPS_MCP_PROTECTED_NAMESPACES` are never restarted, even with an approval.
- **Capacity stays inside min and max.** The server never changes min or max, and refuses a desired value outside them even when approved.
- **Secrets are masked in logs** for a few common patterns (AWS key ids, `password=`, `token=`, `api_key=`, bearer tokens). This is a safety net, not a guarantee; do not point it at logs that contain secrets in other shapes.
- **Errors do not crash the server.** AWS and kubectl errors come back as a result the model can read, and each is audited.

## Use it

```bash
pip install -r requirements.txt
python -m ops_mcp.server          # stdio; uses your AWS credentials and current kubectl context
```

```json
{ "mcpServers": { "ops": { "command": "python", "args": ["-m", "ops_mcp.server"], "cwd": "/path/to/ops-mcp-server" } } }
```

Give it credentials that can only read (for example the `ViewOnlyAccess` policy, plus `autoscaling:SetDesiredCapacity` on one group if you want that write). The server's checks are a second line of defence, not a replacement for least-privilege credentials. Set `OPS_MCP_KUBE_CONTEXT` to pin a kubectl context.

## What is tested, and what is not

33 tests, run in CI with no cloud access:

- AWS calls use botocore's `Stubber`, which checks every call and its arguments against the real API model, so a wrong parameter name fails the test.
- kubectl is a recording fake in unit tests, and a stand-in script on `PATH` in the stdio tests, which drive the real server as an MCP client would: tool list and hints, read-only mode, the full request, refuse, approve, run, refuse-reuse flow, and bad arguments.
- The approval rules (pending, once only, parameter mismatch, denied, expiry, audit with who did it) have their own tests.

**Checked against a real AWS account (read-only calls, 20 Nov 2026):** `aws_alarms`, the missing-group path of `aws_asg_status`, `aws_recent_logs` on a real log group, and input rejection all ran against the live APIs without error. That account had no Auto Scaling group, target group or instance at the time, so **`aws_asg_status` with instances, `aws_target_health`, `aws_instance_status` and the approved `aws_asg_set_capacity` have not been run against live resources**, only against the Stubber.

**Not run against a real cluster.** The kubectl tools have only seen a fake and a stand-in script. The pod summary reads standard `kubectl get -o json` output, but I have not run it against a live cluster, so expect to fix details the first time.

**The approval gate stops a client that only has this server's tools.** An agent that also has a shell on the same machine as the same user could run `python -m ops_mcp approve` itself, or edit the approvals file. Keep the agent's shell and the approving person's terminal separate, or run the server where the agent cannot reach the state directory.
