#!/usr/bin/env bash
# Chaos-testing helper for the self-healing stack.
#
# Picks a random running instance from the project's Auto Scaling Group and
# either kills the web server process (triggers the ALB unhealthy-host alarm)
# or stops the instance outright (triggers the EventBridge auto-recover path),
# so you can observe the self-healing loop end-to-end.
#
# Usage:
#   ./simulate_failure.sh <project_name> [kill-process|stop-instance]

set -euo pipefail

PROJECT_NAME="${1:?Usage: simulate_failure.sh <project_name> [kill-process|stop-instance]}"
MODE="${2:-kill-process}"

ASG_NAME="${PROJECT_NAME}-asg"

INSTANCE_ID=$(aws autoscaling describe-auto-scaling-groups \
  --auto-scaling-group-names "${ASG_NAME}" \
  --query "AutoScalingGroups[0].Instances[?LifecycleState=='InService'].InstanceId | [0]" \
  --output text)

if [[ -z "${INSTANCE_ID}" || "${INSTANCE_ID}" == "None" ]]; then
  echo "No in-service instances found in ${ASG_NAME}" >&2
  exit 1
fi

echo "Target instance: ${INSTANCE_ID}"

case "${MODE}" in
  kill-process)
    echo "Killing httpd via SSM Run Command to trigger the ALB health check failure..."
    aws ssm send-command \
      --instance-ids "${INSTANCE_ID}" \
      --document-name "AWS-RunShellScript" \
      --parameters 'commands=["systemctl stop httpd"]'
    echo "Watch the ALB target group and CloudWatch alarm ${PROJECT_NAME}-unhealthy-target-hosts."
    ;;
  stop-instance)
    echo "Stopping instance to trigger the EventBridge auto-recover path..."
    aws ec2 stop-instances --instance-ids "${INSTANCE_ID}"
    echo "Watch for the instance to restart automatically within ~1-2 minutes."
    ;;
  *)
    echo "Unknown mode: ${MODE} (expected kill-process or stop-instance)" >&2
    exit 1
    ;;
esac
