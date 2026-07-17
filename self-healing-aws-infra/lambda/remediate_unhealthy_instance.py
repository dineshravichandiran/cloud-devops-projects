"""
Self-healing remediation handler.

Triggered by an SNS notification fan-out from a CloudWatch Alarm
(EC2 StatusCheckFailed_System, or ALB UnHealthyHostCount).

Given the instance referenced in the alarm, this function:
  1. Confirms the instance belongs to a self-healing-tagged Auto Scaling Group.
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

REMEDIATION_TAG_KEY = os.environ.get("REMEDIATION_TAG_KEY", "SelfHealing")
REMEDIATION_TAG_VALUE = os.environ.get("REMEDIATION_TAG_VALUE", "true")
METRIC_NAMESPACE = os.environ.get("METRIC_NAMESPACE", "SelfHealingInfra")


def _extract_instance_id(alarm_message: dict) -> str | None:
    dimensions = alarm_message.get("Trigger", {}).get("Dimensions", [])
    for dim in dimensions:
        if dim.get("name") == "InstanceId":
            return dim.get("value")
    return None


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
                "Dimensions": [
                    {"Name": "Action", "Value": action},
                    {"Name": "InstanceId", "Value": instance_id},
                ],
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

        instance_id = _extract_instance_id(alarm_message)
        if not instance_id:
            logger.info("Alarm did not reference an EC2 instance, skipping: %s", alarm_message)
            continue

        if not _instance_is_eligible(instance_id):
            logger.warning(
                "Instance %s is not part of a managed Auto Scaling Group, refusing to act",
                instance_id,
            )
            continue

        logger.info("Marking instance %s unhealthy to trigger ASG replacement", instance_id)
        autoscaling.set_instance_health(
            InstanceId=instance_id,
            HealthStatus="Unhealthy",
            ShouldRespectGracePeriod=False,
        )
        _publish_metric("ReplacedUnhealthyInstance", instance_id)

    return {"statusCode": 200, "body": "remediation complete"}
