# ♻️ Self-Healing Infrastructure on AWS

Infrastructure-as-code for a web tier that detects and recovers from failure without a human in the loop — combining native AWS self-healing primitives with custom Lambda-based remediation for the cases AWS doesn't cover out of the box.

## Why this exists

Auto Scaling Groups already replace instances that fail an ELB health check. But that's only one failure mode. This project layers in the other common ones: hypervisor/hardware faults, a process crashing without the OS noticing, and an instance being stopped by mistake — and closes the loop with alerting so every remediation is observable, not silent.

## Self-healing mechanisms

| Failure scenario                                   | Detection                                   | Automatic recovery action                                      |
|-----------------------------------------------------|----------------------------------------------|------------------------------------------------------------------|
| App fails HTTP health check (crash, deadlock)        | ALB target group health check                | ASG terminates & replaces the instance (native `health_check_type = "ELB"`) |
| Underlying host/hardware failure                     | CloudWatch `StatusCheckFailed_System` alarm  | Native EC2 auto-recover action (`arn:aws:automate:region:ec2:recover`) |
| ALB reports unhealthy targets                        | CloudWatch `UnHealthyHostCount` alarm → SNS  | Lambda marks the instance `Unhealthy` via the ASG API, forcing replacement |
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
                                  │ CloudWatch alarms
              ┌───────────────────┼────────────────────┐
              ▼                                         ▼
   StatusCheckFailed_System                  UnHealthyHostCount ≥ 1
              │                                         │
   EC2 auto-recover (native)                 SNS topic (self-healing-alerts)
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

## Deploying

```bash
cd terraform
terraform init
terraform plan  -var="alarm_notification_email=you@example.com"
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

Being upfront about exactly what's been checked here, not what's assumed:

- ✅ `terraform validate` passes clean against this configuration
- ✅ Both Lambda handlers reviewed line-by-line for correct boto3/AWS API usage (correct client calls, correct parameters, least-privilege IAM matching what each function actually touches)
- 📋 **Not yet deployed to a real AWS account** — no `terraform apply` has been run against live infrastructure, so the simulated-failure scripts above haven't been executed and the CloudWatch dashboard hasn't actually shown a real remediation event yet. The code is sound; it hasn't been proven end-to-end against real AWS the way the other projects in this account have.

## Design decisions

- **Layered, not single-point**: native AWS mechanisms (ELB health checks, EC2 auto-recover) handle the failure modes they're built for; Lambda only steps in for cases those mechanisms don't reach.
- **Least-privilege remediation**: the Lambda execution role can only set instance health on ASG-managed instances and start EC2 instances — it cannot terminate, modify security groups, or touch anything outside its narrow remit.
- **Tag-gated auto-restart**: `auto_recover_stopped_instance.py` only acts on instances explicitly tagged `SelfHealing=true`, so an intentional maintenance stop isn't silently undone.
- **Every action is observable**: remediation publishes a custom metric before returning, so "self-healing" is provable, not just assumed.
