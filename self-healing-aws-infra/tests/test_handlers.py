"""Unit tests for the two Lambda handlers. boto3 is mocked: no AWS access needed."""
import importlib
import json
import os
import sys
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lambda"))
os.environ.setdefault("AWS_DEFAULT_REGION", "ap-south-1")


def _load(name, **env):
    with mock.patch.dict(os.environ, env):
        with mock.patch("boto3.client") as client:
            clients = {}
            client.side_effect = lambda svc, *a, **k: clients.setdefault(svc, mock.MagicMock())
            sys.modules.pop(name, None)
            mod = importlib.import_module(name)
    return mod, clients


def _sns(state, dims=None):
    msg = {"NewStateValue": state, "Trigger": {"Dimensions": dims or []}}
    return {"Records": [{"Sns": {"Message": json.dumps(msg)}}]}


def test_unhealthy_target_is_marked_unhealthy():
    mod, c = _load("remediate_unhealthy_instance", TARGET_GROUP_ARN="tg-arn")
    c["elbv2"].describe_target_health.return_value = {
        "TargetHealthDescriptions": [
            {"Target": {"Id": "i-bad"}, "TargetHealth": {"State": "unhealthy"}},
            {"Target": {"Id": "i-ok"}, "TargetHealth": {"State": "healthy"}},
        ]
    }
    c["autoscaling"].describe_auto_scaling_instances.return_value = {"AutoScalingInstances": [{}]}
    mod.handler(_sns("ALARM", [{"name": "TargetGroup", "value": "x"}]), None)
    c["autoscaling"].set_instance_health.assert_called_once_with(
        InstanceId="i-bad", HealthStatus="Unhealthy", ShouldRespectGracePeriod=False
    )
    c["cloudwatch"].put_metric_data.assert_called_once()


def test_ok_notification_does_nothing():
    mod, c = _load("remediate_unhealthy_instance", TARGET_GROUP_ARN="tg-arn")
    mod.handler(_sns("OK"), None)
    c["autoscaling"].set_instance_health.assert_not_called()
    c["elbv2"].describe_target_health.assert_not_called()


def test_instance_outside_asg_is_refused():
    mod, c = _load("remediate_unhealthy_instance")
    c["autoscaling"].describe_auto_scaling_instances.return_value = {"AutoScalingInstances": []}
    mod.handler(_sns("ALARM", [{"name": "InstanceId", "value": "i-1"}]), None)
    c["autoscaling"].set_instance_health.assert_not_called()


def _stop_event(state="stopped"):
    return {"detail": {"instance-id": "i-1", "state": state}}


def test_tagged_asg_instance_is_restarted():
    mod, c = _load("auto_recover_stopped_instance")
    c["autoscaling"].describe_auto_scaling_instances.return_value = {"AutoScalingInstances": [{}]}
    c["ec2"].describe_tags.return_value = {"Tags": [{"Key": "SelfHealing"}]}
    mod.handler(_stop_event(), None)
    c["ec2"].start_instances.assert_called_once_with(InstanceIds=["i-1"])


def test_untagged_instance_is_left_stopped():
    mod, c = _load("auto_recover_stopped_instance")
    c["autoscaling"].describe_auto_scaling_instances.return_value = {"AutoScalingInstances": [{}]}
    c["ec2"].describe_tags.return_value = {"Tags": []}
    mod.handler(_stop_event(), None)
    c["ec2"].start_instances.assert_not_called()


def test_other_states_are_ignored():
    mod, c = _load("auto_recover_stopped_instance")
    mod.handler(_stop_event("running"), None)
    c["ec2"].start_instances.assert_not_called()
