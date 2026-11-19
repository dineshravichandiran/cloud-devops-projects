# ♻️ Self-Healing Infrastructure on AWS

Infrastructure-as-code for a web tier that detects and recovers from failure without a human in the loop — combining native AWS self-healing primitives with custom Lambda-based remediation for the cases AWS doesn't cover out of the box.

## Why this exists

Auto Scaling Groups already replace instances that fail an ELB health check. But that's only one failure mode. This project layers in the other common ones: hypervisor/hardware faults, a process crashing without the OS noticing, and an instance being stopped by mistake — and closes the loop with alerting so every remediation is observable, not silent.

## Self-healing mechanisms

| Failure scenario                                   | Detection                                   | Automatic recovery action                                      |
|-----------------------------------------------------|----------------------------------------------|------------------------------------------------------------------|
| App fails HTTP health check (crash, deadlock)        | ALB target group health check                | ASG terminates & replaces the instance (native `health_check_type = "ELB"`) |
| ALB reports unhealthy targets                        | CloudWatch `UnHealthyHostCount` alarm → SNS  | Lambda asks the target group which targets are unhealthy and marks them `Unhealthy` via the ASG API, forcing replacement |
| Instance stopped unexpectedly (OOM kill, human error)| EventBridge `EC2 Instance State-change` rule | Lambda restarts the instance if it's tagged for self-healing    |
| Load spike                                            | Target-tracking scaling policy (CPU 60%)    | ASG scales out automatically                                    |

All remediation actions publish a `SelfHealingInfra/RemediationActionsTaken` CloudWatch metric, visualized on a dashboard, so "did healing actually happen" is answerable at a glance instead of guessed at from logs.

## Architecture

```
                       ┌──────────────────────┐
        users ───────► │   Application LB      │
                       └──────────┬───────────┘
                                  │ health checks
                       ┌──────────▼───────────┐
                       │  Auto Scaling Group   │◄── target-tracking scaling (CPU)
                       │  (public subnets)     │
                       └──────────┬───────────┘
                                                  │ CloudWatch alarm
                                                  ▼
                                    UnHealthyHostCount ≥ 1
                                                  │
                                    SNS topic (self-healing-alerts)
                                                  │
                                              ┌──────────┴──────────┐
                                              ▼                     ▼
                                     Lambda: remediate      Email subscription
                                     unhealthy instance      (ops on-call)
                                    (sets ASG instance
                                     health = Unhealthy)

   EventBridge (EC2 stopped) ──► Lambda: auto_recover_stopped_instance
                                  (ec2:StartInstances for tagged instances)
```

## Repository layout

```
self-healing-aws-infra/
├── terraform/
│   ├── versions.tf        # provider requirements
│   ├── variables.tf       # sizing, region, notification email, thresholds
│   ├── network.tf         # VPC, subnets, IGW, security group
│   ├── alb.tf              # ALB, target group, listener
│   ├── asg.tf              # launch template, Auto Scaling Group, scaling policy
│   ├── iam.tf              # least-privilege Lambda execution role
│   ├── lambda.tf           # remediation functions, SNS/EventBridge wiring
│   ├── monitoring.tf       # CloudWatch alarms, SNS topic, EventBridge rule, dashboard
│   └── outputs.tf
├── lambda/
│   ├── remediate_unhealthy_instance.py     # SNS-triggered: force ASG replacement
│   └── auto_recover_stopped_instance.py    # EventBridge-triggered: restart stopped instance
└── scripts/
    └── simulate_failure.sh                 # chaos-test helper to validate the loop end-to-end
```

> Changed after code review, before the first real apply: the native EC2 auto-recover alarm was
> removed (that action needs an alarm on one specific instance, which an Auto Scaling Group cannot
> declare), the unhealthy-target Lambda now resolves the instance from the target group (the alarm
> does not name one), instances carry the `SelfHealing=true` tag and an SSM role, and the metric
> dimensions match the dashboard. Handler logic is covered by `tests/` (`pytest tests`).

## Deploying

```bash
cd terraform
terraform init
terraform plan  -var="alarm_notification_email=you@example.com"   # region defaults to ap-south-1
terraform apply -var="alarm_notification_email=you@example.com"
```

Confirm the SNS email subscription (check your inbox) so remediation alerts actually reach you.

## Validating self-healing works

```bash
# Kill the web server process on one instance -> ALB marks it unhealthy ->
# alarm fires -> Lambda forces ASG replacement
./scripts/simulate_failure.sh self-healing-app kill-process

# Stop an instance outright -> EventBridge rule fires -> Lambda restarts it
./scripts/simulate_failure.sh self-healing-app stop-instance
```

Watch the `self-healing-app-self-healing` CloudWatch dashboard, or query the
`SelfHealingInfra` namespace directly, to confirm the remediation metric fired.

## Current verification status

Applied to a real AWS account (ap-south-1), drilled, then destroyed. What was checked:

- ✅ `terraform validate` passes and the handler tests pass (6 tests, mocked boto3)
- ✅ Applied live: VPC, ALB, ASG (2 instances), both Lambdas, alarm, dashboard, SNS
- ✅ Drill B: a stopped, tagged instance was restarted by the Lambda
- ✅ Drill C: alarm, Lambda, ASG replacement chain fired end to end, and the `SelfHealingInfra` custom metric recorded it
- ✅ Destroyed afterwards and checked for leftover resources
- 🔧 Running it found four defects that validation alone could not (AMI without SSM agent, alarm period, EC2 auto-recover on ASG members, missing `DescribeTargetHealth`); all fixed
- 📋 Not measured: clean detection-to-replacement time, cost, load-triggered scale-out

Details, timings and the defects are in [docs/evidence.md](docs/evidence.md).

## Design decisions

- **Layered, not single-point**: native AWS mechanisms (ELB health checks and the ASG replacing failed instances) handle the failure modes they're built for; Lambda only steps in for cases those mechanisms don't reach.
- **Least-privilege remediation**: the Lambda execution role can only set instance health on ASG-managed instances and start EC2 instances — it cannot terminate, modify security groups, or touch anything outside its narrow remit.
- **Tag-gated auto-restart**: `auto_recover_stopped_instance.py` only acts on instances explicitly tagged `SelfHealing=true`, so an intentional maintenance stop isn't silently undone.
- **Every action is observable**: remediation publishes a custom metric before returning, so "self-healing" is provable, not just assumed.
