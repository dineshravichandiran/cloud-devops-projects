"""
Self-healing remediation handler.

Triggered by an SNS notification fan-out from a CloudWatch Alarm on the ALB
UnHealthyHostCount metric. That alarm is per target group, so it does not name
an instance: the function asks the target group which targets are unhealthy.

For each unhealthy target (or the InstanceId dimension, if an alarm has one):
  1. Confirms the instance belongs to an Auto Scaling Group.
  2. Marks the instance as Unhealthy via the Auto Scaling API, which causes
     the ASG to terminate it and launch a replacement automatically.
  3. Emits a CloudWatch custom metric so remediation actions are auditable.

This is intentionally conservative: it never terminates instances directly
and never touches anything outside an Auto Scaling Group, so a bad alarm
can't cause a wider outage than "one extra instance replacement".
"""
import json
import logging
import os

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

autoscaling = boto3.client("autoscaling")
cloudwatch = boto3.client("cloudwatch")
elbv2 = boto3.client("elbv2")

REMEDIATION_TAG_KEY = os.environ.get("REMEDIATION_TAG_KEY", "SelfHealing")
REMEDIATION_TAG_VALUE = os.environ.get("REMEDIATION_TAG_VALUE", "true")
METRIC_NAMESPACE = os.environ.get("METRIC_NAMESPACE", "SelfHealingInfra")
TARGET_GROUP_ARN = os.environ.get("TARGET_GROUP_ARN", "")


def _extract_instance_id(alarm_message: dict) -> str | None:
    dimensions = alarm_message.get("Trigger", {}).get("Dimensions", [])
    for dim in dimensions:
        if dim.get("name") == "InstanceId":
            return dim.get("value")
    return None


def _unhealthy_targets(target_group_arn: str) -> list[str]:
    response = elbv2.describe_target_health(TargetGroupArn=target_group_arn)
    return [
        d["Target"]["Id"]
        for d in response.get("TargetHealthDescriptions", [])
        if d.get("TargetHealth", {}).get("State") == "unhealthy"
    ]


def _instance_is_eligible(instance_id: str) -> bool:
    response = autoscaling.describe_auto_scaling_instances(InstanceIds=[instance_id])
    instances = response.get("AutoScalingInstances", [])
    return len(instances) == 1


def _publish_metric(action: str, instance_id: str) -> None:
    cloudwatch.put_metric_data(
        Namespace=METRIC_NAMESPACE,
        MetricData=[
            {
                "MetricName": "RemediationActionsTaken",
                "Dimensions": [{"Name": "Action", "Value": action}],
                "Value": 1,
                "Unit": "Count",
            }
        ],
    )


def handler(event, context):
    for record in event.get("Records", []):
        message_raw = record["Sns"]["Message"]
        try:
            alarm_message = json.loads(message_raw)
        except json.JSONDecodeError:
            logger.warning("Could not parse SNS message as JSON: %s", message_raw)
            continue

        # The alarm also notifies on recovery (OK): never act on that.
        if alarm_message.get("NewStateValue") != "ALARM":
            logger.info("Alarm state is %s, nothing to do", alarm_message.get("NewStateValue"))
            continue

        instance_id = _extract_instance_id(alarm_message)
        instance_ids = [instance_id] if instance_id else []
        if not instance_ids and TARGET_GROUP_ARN:
            instance_ids = _unhealthy_targets(TARGET_GROUP_ARN)
        if not instance_ids:
            logger.info("No unhealthy instance found for this alarm, skipping")
            continue

        for iid in instance_ids:
            if not _instance_is_eligible(iid):
                logger.warning(
                    "Instance %s is not part of a managed Auto Scaling Group, refusing to act", iid
                )
                continue

            logger.info("Marking instance %s unhealthy to trigger ASG replacement", iid)
            autoscaling.set_instance_health(
                InstanceId=iid,
                HealthStatus="Unhealthy",
                ShouldRespectGracePeriod=False,
            )
            _publish_metric("ReplacedUnhealthyInstance", iid)

    return {"statusCode": 200, "body": "remediation complete"}
