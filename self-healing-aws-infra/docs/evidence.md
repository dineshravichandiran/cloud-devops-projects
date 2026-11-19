# Live run evidence

Applied to a real AWS account (ap-south-1), drilled with real failures, then destroyed
(`terraform destroy`: 30 resources, and a check for leftover ALB, ASG, EC2, NAT, EIP,
Lambda, SNS, IAM roles, VPC and alarms found none). Times are UTC, 19 Nov 2026.

## What was observed

| Drill | Failure injected | What happened |
|---|---|---|
| A | An instance failed the ELB health check | The ASG took it out of service ("ELB system health check failure", 22:47:18) and launched a replacement a second later. The native mechanism acted first, so Lambda was not needed. This drill overlapped with an instance refresh I had started, so it is not a clean timing. |
| B | An instance tagged `SelfHealing=true` was stopped | The restart Lambda started it again. The `RemediationActionsTaken` metric (namespace `SelfHealingInfra`, `Action=RestartedStoppedInstance`) recorded 1 at 22:49. |
| C | ASG health-check replacement suspended, Apache stopped on one instance | Alarm `unhealthy-target-hosts` went to ALARM, the Lambda marked the instance unhealthy (22:54:28), the ASG took it out of service "in response to a user health-check" (22:54:36) and launched a replacement (22:54:38). The metric `Action=ReplacedUnhealthyInstance` recorded 1 at 22:54 and 22:55. The `HealthCheck` process was resumed afterwards. |

## Defects found only by running it

1. The minimal Amazon Linux 2023 image has no SSM agent, so Session Manager could not reach the instances. Fixed by using the full AL2023 AMI and attaching an instance profile.
2. The alarm period must be a multiple of 60 seconds for the per-minute ALB metric. With a 30 s period it never breached twice in a row. Fixed to 60 s.
3. EC2 auto-recover alarms cannot be declared for ASG members, so that alarm was removed (the ASG replaces failed instances itself).
4. The alarm names no instance, so the Lambda needed `elasticloadbalancing:DescribeTargetHealth` to find the unhealthy targets from the target group.

## Not measured

- Detection-to-replacement time under a clean run (Drill A was contaminated by an instance refresh).
- Cost of the run. Read it from Cost Explorer before quoting a number.
- Load-triggered scale-out (target tracking at 60% CPU) was not exercised.

Raw timelines were saved from the run; the alarm flapped OK to ALARM twice (22:54:27 and 22:55:07) because the replacement instances were still warming up.
