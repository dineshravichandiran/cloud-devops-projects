import pytest

from ops_mcp import safety
from ops_mcp.approvals import ApprovalError
from tests.conftest import pods_json


def test_get_pods_summarises_crashloop(k8s, kubectl):
    kubectl.answers[("get", "pods")] = (0, pods_json(), "")
    items = k8s.get("pods", "shop")["items"]
    assert items[1] == {"name": "web-2", "phase": "Running", "ready": "0/1", "restarts": 7, "reasons": ["CrashLoopBackOff"], "node": "n1"}
    assert kubectl.calls[0] == ["get", "pods", "-n", "shop", "-o", "json"]


def test_only_known_kinds_and_safe_names(k8s):
    with pytest.raises(safety.InvalidInput):
        k8s.get("secrets", "shop")
    with pytest.raises(safety.InvalidInput):
        k8s.get("pods", "--all-namespaces")
    with pytest.raises(safety.InvalidInput):
        k8s.logs("shop", "-f")
    with pytest.raises(safety.InvalidInput):
        k8s.logs("shop", "pod; rm -rf /")


def test_logs_are_masked_and_bounded(k8s, kubectl):
    kubectl.answers[("logs",)] = (0, "login ok token=abc123 Authorization: Bearer eyJhbGci.x.y\n", "")
    out = k8s.logs("shop", "web-1", tail=50)["log"]
    assert "abc123" not in out and "eyJhbGci" not in out
    assert kubectl.calls[0] == ["logs", "web-1", "-n", "shop", "--tail=50"]
    with pytest.raises(safety.InvalidInput):
        k8s.logs("shop", "web-1", tail=100000)


def test_kubectl_failure_is_an_error_message(k8s, kubectl):
    kubectl.answers[("get", "pods")] = (1, "", "Error from server (Forbidden)")
    with pytest.raises(RuntimeError, match="Forbidden"):
        k8s.get("pods", "shop")


def test_restart_dry_run_uses_server_dry_run_and_changes_nothing(k8s, kubectl):
    kubectl.answers[("rollout", "restart")] = (0, "deployment.apps/web\n", "")
    out = k8s.rollout_restart("shop", "web")
    assert out["status"] == "dry_run" and "--dry-run=server" in kubectl.calls[0]


def test_restart_needs_an_approval(k8s, kubectl):
    with pytest.raises(ApprovalError):
        k8s.rollout_restart("shop", "web", dry_run=False)
    assert kubectl.calls == []


def test_restart_with_matching_approval_runs_and_waits(k8s, kubectl, approvals):
    aid = approvals.request("k8s_rollout_restart", {"namespace": "shop", "deployment": "web"}, "stuck")
    approvals.decide(aid, True, "dinesh")
    kubectl.answers[("rollout", "restart")] = (0, "deployment.apps/web restarted\n", "")
    kubectl.answers[("rollout", "status")] = (0, "successfully rolled out\n", "")
    out = k8s.rollout_restart("shop", "web", dry_run=False, approval_id=aid)
    assert out["status"] == "restarted"
    assert [c[:2] for c in kubectl.calls] == [["rollout", "restart"], ["rollout", "status"]]


def test_restart_reports_when_the_wait_fails_after_the_restart(k8s, kubectl, approvals):
    aid = approvals.request("k8s_rollout_restart", {"namespace": "shop", "deployment": "web"}, "stuck")
    approvals.decide(aid, True, "dinesh")
    kubectl.answers[("rollout", "status")] = (1, "", "timed out")
    assert k8s.rollout_restart("shop", "web", dry_run=False, approval_id=aid)["status"] == "restarted_not_confirmed"


def test_protected_namespaces_are_refused_even_with_approval(k8s, kubectl, approvals):
    aid = approvals.request("k8s_rollout_restart", {"namespace": "kube-system", "deployment": "coredns"}, "r")
    approvals.decide(aid, True, "dinesh")
    assert k8s.rollout_restart("kube-system", "coredns", dry_run=False, approval_id=aid)["status"] == "refused"
    assert kubectl.calls == []


def test_only_get_logs_and_rollout_verbs_are_ever_used(k8s, kubectl, approvals):
    kubectl.answers[("get", "pods")] = (0, pods_json(), "")
    k8s.get("pods", "shop"); k8s.logs("shop", "web-1")
    k8s.rollout_restart("shop", "web")
    assert {c[0] for c in kubectl.calls} <= {"get", "logs", "rollout"}
    assert not any(a in c for c in kubectl.calls for a in ("delete", "apply", "exec", "edit", "patch", "scale"))
