"""AWS tools. Everything here is a describe/get/filter call except `set_capacity`, which needs an approval."""
from __future__ import annotations

import time
from typing import Callable, List, Optional

from . import safety
from .approvals import ApprovalStore

ClientFactory = Callable[[str], object]


def default_client_factory() -> ClientFactory:
    import boto3
    return lambda service: boto3.client(service)


class AwsTools:
    def __init__(self, client: Optional[ClientFactory] = None, approvals: Optional[ApprovalStore] = None) -> None:
        self._factory = client
        self.approvals = approvals

    def _c(self, service: str):
        if self._factory is None:
            self._factory = default_client_factory()
        return self._factory(service)

    # ---- read only
    def asg_status(self, name: str) -> dict:
        safety.asg_name(name)
        groups = self._c("autoscaling").describe_auto_scaling_groups(AutoScalingGroupNames=[name])["AutoScalingGroups"]
        if not groups:
            return {"error": f"no Auto Scaling group named {name}"}
        g = groups[0]
        return {"name": g["AutoScalingGroupName"], "min": g["MinSize"], "max": g["MaxSize"], "desired": g["DesiredCapacity"],
                "health_check_type": g.get("HealthCheckType"),
                "instances": [{"id": i["InstanceId"], "az": i.get("AvailabilityZone"), "lifecycle": i["LifecycleState"],
                               "health": i["HealthStatus"]} for i in g.get("Instances", [])]}

    def target_health(self, target_group_arn: str) -> dict:
        safety.arn(target_group_arn)
        descs = self._c("elbv2").describe_target_health(TargetGroupArn=target_group_arn)["TargetHealthDescriptions"]
        return {"targets": [{"id": d["Target"]["Id"], "port": d["Target"].get("Port"), "state": d["TargetHealth"]["State"],
                             "reason": d["TargetHealth"].get("Reason"), "description": d["TargetHealth"].get("Description")} for d in descs]}

    def alarms(self, state: str = "ALARM", name_prefix: Optional[str] = None) -> dict:
        if state not in ("OK", "ALARM", "INSUFFICIENT_DATA"):
            raise safety.InvalidInput("state must be OK, ALARM or INSUFFICIENT_DATA")
        kwargs: dict = {"StateValue": state, "MaxRecords": 50}
        if name_prefix:
            kwargs["AlarmNamePrefix"] = safety.asg_name(name_prefix)
        found = self._c("cloudwatch").describe_alarms(**kwargs)["MetricAlarms"]
        return {"alarms": [{"name": a["AlarmName"], "state": a["StateValue"], "reason": a.get("StateReason"),
                            "metric": a.get("MetricName"), "since": str(a.get("StateUpdatedTimestamp"))} for a in found]}

    def instance_status(self, instance_ids: List[str]) -> dict:
        if not instance_ids or len(instance_ids) > 20:
            raise safety.InvalidInput("give between 1 and 20 instance ids")
        for i in instance_ids:
            safety.instance_id(i)
        st = self._c("ec2").describe_instance_status(InstanceIds=instance_ids, IncludeAllInstances=True)["InstanceStatuses"]
        return {"instances": [{"id": s["InstanceId"], "state": s["InstanceState"]["Name"], "system_status": s["SystemStatus"]["Status"],
                               "instance_status": s["InstanceStatus"]["Status"]} for s in st]}

    def recent_logs(self, log_group: str, minutes: int = 15, pattern: Optional[str] = None, limit: int = 50) -> dict:
        safety.log_group(log_group)
        safety.bounded(minutes, 1, 180, "minutes")
        safety.bounded(limit, 1, 200, "limit")
        if pattern is not None and len(pattern) > 200:
            raise safety.InvalidInput("pattern is longer than 200 characters")
        kwargs: dict = {"logGroupName": log_group, "startTime": int((time.time() - minutes * 60) * 1000), "limit": limit}
        if pattern:
            kwargs["filterPattern"] = pattern
        events = self._c("logs").filter_log_events(**kwargs)["events"]
        return {"events": [{"time": e["timestamp"], "stream": e.get("logStreamName"), "message": safety.clip(safety.redact(e["message"].rstrip()), 1000)}
                           for e in events]}

    # ---- changes state, only with an approval
    def set_capacity(self, name: str, desired: int, dry_run: bool = True, approval_id: Optional[str] = None) -> dict:
        safety.asg_name(name)
        safety.bounded(desired, 0, 1000, "desired")
        current = self.asg_status(name)
        if "error" in current:
            return current
        if not current["min"] <= desired <= current["max"]:
            return {"status": "refused", "reason": f"desired {desired} is outside the group's min {current['min']} and max {current['max']}; "
                                                   "this tool never changes min or max"}
        plan = {"name": name, "from": current["desired"], "to": desired}
        if dry_run:
            return {"status": "dry_run", "would_change": plan, "note": "call request_approval, have a person approve, then repeat with dry_run=false"}
        self.approvals.consume(approval_id, "aws_asg_set_capacity", {"name": name, "desired": desired})
        self._c("autoscaling").set_desired_capacity(AutoScalingGroupName=name, DesiredCapacity=desired, HonorCooldown=True)
        return {"status": "changed", "changed": plan}
