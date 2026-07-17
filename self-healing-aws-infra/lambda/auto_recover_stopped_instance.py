"""
Self-healing handler for accidental/unexpected instance stops.

Triggered by an EventBridge rule matching EC2 "Instance State-change
Notification" events with state == "stopped". If the instance carries the
self-healing tag and is a member of a monitored Auto Scaling Group, it is
restarted automatically and the action is recorded as a CloudWatch metric.

Instances stopped intentionally (e.g. via a maintenance runbook) should have
their self-healing tag removed first, or this function will start them
back up.
"""
import logging
import os

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

ec2 = boto3.client("ec2")
autoscaling = boto3.client("autoscaling")
cloudwatch = boto3.client("cloudwatch")

REMEDIATION_TAG_KEY = os.environ.get("REMEDIATION_TAG_KEY", "SelfHealing")
METRIC_NAMESPACE = os.environ.get("METRIC_NAMESPACE", "SelfHealingInfra")


def _is_tagged_for_self_healing(instance_id: str) -> bool:
    response = ec2.describe_tags(
        Filters=[
            {"Name": "resource-id", "Values": [instance_id]},
            {"Name": "key", "Values": [REMEDIATION_TAG_KEY]},
        ]
    )
    return len(response.get("Tags", [])) > 0


def _is_in_managed_asg(instance_id: str) -> bool:
    response = autoscaling.describe_auto_scaling_instances(InstanceIds=[instance_id])
    return len(response.get("AutoScalingInstances", [])) == 1


def handler(event, context):
    detail = event.get("detail", {})
    instance_id = detail.get("instance-id")
    state = detail.get("state")

    if not instance_id or state != "stopped":
        logger.info("Ignoring event, not a relevant stop transition: %s", event)
        return {"statusCode": 200, "body": "ignored"}

    if not _is_in_managed_asg(instance_id) or not _is_tagged_for_self_healing(instance_id):
        logger.info("Instance %s is not managed for self-healing, ignoring", instance_id)
        return {"statusCode": 200, "body": "not managed"}

    logger.info("Restarting stopped instance %s", instance_id)
    ec2.start_instances(InstanceIds=[instance_id])

    cloudwatch.put_metric_data(
        Namespace=METRIC_NAMESPACE,
        MetricData=[
            {
                "MetricName": "RemediationActionsTaken",
                "Dimensions": [
                    {"Name": "Action", "Value": "RestartedStoppedInstance"},
                    {"Name": "InstanceId", "Value": instance_id},
                ],
                "Value": 1,
                "Unit": "Count",
            }
        ],
    )

    return {"statusCode": 200, "body": f"restarted {instance_id}"}
