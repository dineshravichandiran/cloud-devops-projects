# Live run evidence

Applied to a real AWS account (ap-south-1), drilled with three real failures, then destroyed.
Times are UTC, 20 Nov 2026. `terraform destroy` removed all 30 resources (finished 00:46:07),
and a check for leftovers (ASG, ALB, target group, EC2, Lambda, alarms, SNS, IAM roles, VPC,
NAT gateway, Elastic IP, EventBridge rule, dashboard) found none. The two Lambda log groups,
which Lambda creates itself and Terraform does not track, were deleted by hand.

An earlier run on 19 Nov was thrown away: one drill overlapped with an instance refresh, so its
timings were not clean. The numbers below are from a second, clean apply (ASG of 2 instances,
no other changes in flight during the drills).

## Clean drills

| Drill | Failure injected | Result |
|---|---|---|
| A | Apache stopped on one instance through SSM (ASG health check left on) | Started 00:10:56. The ELB health check failed the instance; the ASG took it out of service at 00:12:54 ("ELB system health check failure") and launched a replacement at 00:12:55. About 2 minutes to act, about 3 minutes until the replacement was healthy behind the ALB. The native mechanism acted first. |
| B | An instance tagged `SelfHealing=true` was stopped | Started 00:19:09. EventBridge saw the stopped state and the restart Lambda started it: pending at 00:19:40 (about 31 s), running at 00:20:09 (about 1 minute). `RemediationActionsTaken` with `Action=RestartedStoppedInstance` recorded it. |
| C | ASG health-check replacement suspended, then Apache stopped on one instance | Started 00:26:29. Alarm `unhealthy-target-hosts` went to ALARM at 00:31:59 (about 5 min 26 s). The remediation Lambda ran at 00:32:00 and marked the instance unhealthy (invocation 837 ms), the ASG took it out of service "in response to a user health-check" at 00:32:13 and launched a replacement at 00:32:14, healthy behind the ALB about 6 min 47 s after the failure. `Action=ReplacedUnhealthyInstance` recorded 1 at 00:32. The alarm returned to OK at 00:36:59 and the Lambda was invoked again and correctly did nothing ("Alarm state is OK, nothing to do"). `HealthCheck` was resumed afterwards. |

Drill C is the one that proves the CloudWatch alarm, SNS and Lambda path on its own, because
the ASG's own health check was switched off for it. Drill A shows that with the ASG health check
on, the ASG gets there first, so the Lambda is a second line, not the first.

## Reading the timings

- The alarm path is slow by design: the ALB has to fail the target first, the metric is published
  once a minute, and the alarm needs two consecutive 60 s periods to breach. About 5 minutes to
  alarm is what this configuration gives, not a tuned figure.
- Replacement draining is slower than it looks because the ALB deregistration delay is about 300 s.

## Defects found only by running it

1. The minimal Amazon Linux 2023 image has no SSM agent, so Session Manager could not reach the instances. Fixed by using the full AL2023 AMI and attaching an instance profile.
2. The alarm period must be a multiple of 60 seconds for the per-minute ALB metric. With a 30 s period it never breached twice in a row. Fixed to 60 s.
3. EC2 auto-recover alarms cannot be declared for ASG members, so that alarm was removed (the ASG replaces failed instances itself).
4. The alarm names no instance, so the Lambda needed `elasticloadbalancing:DescribeTargetHealth` to find the unhealthy targets from the target group.

## Not measured

- Cost of the run. Read it from Cost Explorer before quoting a number.
- Load-triggered scale-out (target tracking at 60% CPU) was not exercised.
- Each drill was run once, so the timings are single observations, not averages.
