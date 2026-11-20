import pytest

from ops_mcp.approvals import ApprovalError

P = {"namespace": "shop", "deployment": "web"}


def test_a_request_is_pending_and_cannot_be_used(approvals):
    aid = approvals.request("k8s_rollout_restart", P, "pods stuck")
    with pytest.raises(ApprovalError, match="has not approved"):
        approvals.consume(aid, "k8s_rollout_restart", P)


def test_missing_and_unknown_ids_are_refused(approvals):
    with pytest.raises(ApprovalError, match="needs an approval id"):
        approvals.consume(None, "k8s_rollout_restart", P)
    with pytest.raises(ApprovalError, match="unknown"):
        approvals.consume("apr-nope", "k8s_rollout_restart", P)


def test_approved_works_once_only(approvals):
    aid = approvals.request("k8s_rollout_restart", P, "r")
    approvals.decide(aid, True, "dinesh")
    assert approvals.consume(aid, "k8s_rollout_restart", P)["status"] == "used"
    with pytest.raises(ApprovalError, match="used"):
        approvals.consume(aid, "k8s_rollout_restart", P)


def test_changed_parameters_or_action_do_not_match(approvals):
    aid = approvals.request("k8s_rollout_restart", P, "r")
    approvals.decide(aid, True, "dinesh")
    with pytest.raises(ApprovalError, match="different"):
        approvals.consume(aid, "k8s_rollout_restart", {**P, "deployment": "db"})
    with pytest.raises(ApprovalError, match="different"):
        approvals.consume(aid, "aws_asg_set_capacity", P)
    assert approvals.consume(aid, "k8s_rollout_restart", P)["status"] == "used"   # a mismatch does not burn it


def test_denied_cannot_be_used_or_reversed(approvals):
    aid = approvals.request("k8s_rollout_restart", P, "r")
    approvals.decide(aid, False, "dinesh")
    with pytest.raises(ApprovalError, match="denied"):
        approvals.consume(aid, "k8s_rollout_restart", P)
    with pytest.raises(ApprovalError, match="already denied"):
        approvals.decide(aid, True, "dinesh")


def test_approval_expires_after_the_ttl_from_the_decision(approvals, clock):
    aid = approvals.request("k8s_rollout_restart", P, "r")
    clock.t += 3600                      # a long wait before the person looks is fine
    approvals.decide(aid, True, "dinesh")
    clock.t += 901
    with pytest.raises(ApprovalError, match="expired"):
        approvals.consume(aid, "k8s_rollout_restart", P)


def test_every_step_is_audited_with_who_did_it(approvals, audit):
    aid = approvals.request("k8s_rollout_restart", P, "r")
    approvals.decide(aid, True, "dinesh")
    events = [(l["actor"], l["event"]) for l in audit.lines()]
    assert events == [("agent", "approval_requested"), ("human:dinesh", "approval_approved")]
