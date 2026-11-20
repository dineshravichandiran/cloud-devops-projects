import pytest

from ops_mcp import safety

ASG = "web-asg"


def asg_response(desired=2, mn=1, mx=4):
    return {"AutoScalingGroups": [{"AutoScalingGroupName": ASG, "MinSize": mn, "MaxSize": mx, "DesiredCapacity": desired, "DefaultCooldown": 300,
                                   "AvailabilityZones": ["ap-south-1a"], "HealthCheckType": "ELB", "CreatedTime": "2026-11-20T00:00:00Z",
                                   "Instances": [{"InstanceId": "i-0123456789abcdef0", "AvailabilityZone": "ap-south-1a", "LifecycleState": "InService",
                                                  "HealthStatus": "Healthy", "ProtectedFromScaleIn": False}]}]}


def test_asg_status_summarises(aws, aws_stubs):
    aws_stubs.stub("autoscaling").add_response("describe_auto_scaling_groups", asg_response(), {"AutoScalingGroupNames": [ASG]})
    out = aws.asg_status(ASG)
    assert (out["min"], out["max"], out["desired"]) == (1, 4, 2) and out["instances"][0]["health"] == "Healthy"


def test_asg_status_unknown_group(aws, aws_stubs):
    aws_stubs.stub("autoscaling").add_response("describe_auto_scaling_groups", {"AutoScalingGroups": []}, {"AutoScalingGroupNames": [ASG]})
    assert "error" in aws.asg_status(ASG)


def test_target_health_reports_reason(aws, aws_stubs):
    arn = "arn:aws:elasticloadbalancing:ap-south-1:123456789012:targetgroup/web/abc123"
    aws_stubs.stub("elbv2").add_response("describe_target_health", {"TargetHealthDescriptions": [
        {"Target": {"Id": "i-0123456789abcdef0", "Port": 80}, "TargetHealth": {"State": "unhealthy", "Reason": "Target.Timeout", "Description": "timed out"}}]},
        {"TargetGroupArn": arn})
    assert aws.target_health(arn)["targets"][0]["reason"] == "Target.Timeout"


def test_alarms_and_bad_state(aws, aws_stubs):
    aws_stubs.stub("cloudwatch").add_response("describe_alarms", {"MetricAlarms": [{"AlarmName": "web-unhealthy", "StateValue": "ALARM", "StateReason": "x",
                                                                                   "MetricName": "UnHealthyHostCount"}]}, {"StateValue": "ALARM", "MaxRecords": 50})
    assert aws.alarms()["alarms"][0]["name"] == "web-unhealthy"
    with pytest.raises(safety.InvalidInput):
        aws.alarms("BROKEN")


def test_recent_logs_masks_secrets_and_limits(aws, aws_stubs):
    aws_stubs.stub("logs").add_response("filter_log_events", {"events": [
        {"timestamp": 1, "logStreamName": "s", "message": "connect failed password=hunter2 key AKIAABCDEFGHIJKLMNOP\n"}]})
    msg = aws.recent_logs("/aws/lambda/fn")["events"][0]["message"]
    assert "hunter2" not in msg and "AKIAABCDEFGHIJKLMNOP" not in msg and "[redacted" in msg
    with pytest.raises(safety.InvalidInput):
        aws.recent_logs("/aws/lambda/fn", limit=5000)
    with pytest.raises(safety.InvalidInput):
        aws.recent_logs("bad group; rm", minutes=5)


def test_instance_ids_are_validated(aws):
    with pytest.raises(safety.InvalidInput):
        aws.instance_status(["i-0123456789abcdef0", "not-an-instance"])
    with pytest.raises(safety.InvalidInput):
        aws.instance_status([])


def test_set_capacity_dry_run_changes_nothing(aws, aws_stubs):
    st = aws_stubs.stub("autoscaling")
    st.add_response("describe_auto_scaling_groups", asg_response(), {"AutoScalingGroupNames": [ASG]})
    out = aws.set_capacity(ASG, 3)
    assert out["status"] == "dry_run" and out["would_change"] == {"name": ASG, "from": 2, "to": 3}
    st.assert_no_pending_responses()   # set_desired_capacity was never queued, so a call would have raised


def test_set_capacity_outside_min_max_is_refused_even_with_approval(aws, aws_stubs, approvals):
    aws_stubs.stub("autoscaling").add_response("describe_auto_scaling_groups", asg_response(mx=4), {"AutoScalingGroupNames": [ASG]})
    aid = approvals.request("aws_asg_set_capacity", {"name": ASG, "desired": 9}, "r")
    approvals.decide(aid, True, "dinesh")
    out = aws.set_capacity(ASG, 9, dry_run=False, approval_id=aid)
    assert out["status"] == "refused" and "max 4" in out["reason"]


def test_set_capacity_with_approval_calls_the_api_once(aws, aws_stubs, approvals):
    st = aws_stubs.stub("autoscaling")
    st.add_response("describe_auto_scaling_groups", asg_response(), {"AutoScalingGroupNames": [ASG]})
    st.add_response("set_desired_capacity", {}, {"AutoScalingGroupName": ASG, "DesiredCapacity": 3, "HonorCooldown": True})
    aid = approvals.request("aws_asg_set_capacity", {"name": ASG, "desired": 3}, "traffic")
    approvals.decide(aid, True, "dinesh")
    assert aws.set_capacity(ASG, 3, dry_run=False, approval_id=aid)["status"] == "changed"
    st.assert_no_pending_responses()


def test_set_capacity_without_approval_raises_before_changing(aws, aws_stubs):
    from ops_mcp.approvals import ApprovalError
    aws_stubs.stub("autoscaling").add_response("describe_auto_scaling_groups", asg_response(), {"AutoScalingGroupNames": [ASG]})
    with pytest.raises(ApprovalError):
        aws.set_capacity(ASG, 3, dry_run=False)
