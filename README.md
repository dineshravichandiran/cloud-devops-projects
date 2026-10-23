# ☁️ Cloud & DevOps Projects

Production-grade automation and infrastructure-as-code projects that extend hands-on cloud
operations experience into repeatable, secure, self-service delivery.

> Built and maintained by **Dinesh Ravichandiran** — Cloud Services NOC Engineer, keeping
> Fortune 500 platforms running 24×7 (Kubernetes · AWS · Azure · Linux).

---

## Projects

| Project | What it demonstrates |
|---------|----------------------|
| 🔐 **[End-to-End DevSecOps CI Pipeline](https://github.com/dineshravichandiran/devsecops-ci-pipeline)** | Now in its own repository: a GitHub Actions pipeline that runs secret scanning, SAST, dependency (SCA) auditing, container image scanning, and DAST on every push, with findings in the GitHub Security tab. |
| ♻️ **[Self-Healing Infrastructure on AWS](self-healing-aws-infra)** | Auto-recovery and resilience — Terraform-provisioned VPC/ALB/Auto Scaling Group with CloudWatch alarms and Lambda-based auto-remediation designed to detect and recover from failure without a human in the loop. Validated with `terraform validate` and code review; not yet applied to a live AWS account. |
| ☸️ **[EKS GitOps Platform](eks-gitops-platform)** | Terraform for a small EKS cluster (private nodes, KMS-encrypted secrets, IRSA) with an Argo CD bootstrap plan. **Validated with `terraform validate`, mocked-provider tests and checkov; NOT applied to any AWS account.** |
| 🔄 **[End-to-End Azure DevOps Project](azure-devops-pipeline)** | Full CI/CD on Azure — a multi-stage Azure DevOps pipeline that builds, security-scans, provisions infrastructure with Bicep, and promotes releases through dev → staging → production with approvals and slot swaps. |

Each project folder has its own README with an architecture diagram, design rationale, and setup
instructions.

---

## Moved: DevSecOps CI pipeline

The DevSecOps pipeline now has its own repository, with its proof-of-work screenshot and a plain
description of which scans block the pipeline and which only report:
**[dineshravichandiran/devsecops-ci-pipeline](https://github.com/dineshravichandiran/devsecops-ci-pipeline)**

---

## ♻️ Self-Healing Infrastructure on AWS

Infrastructure that detects and recovers from failure automatically, layering custom remediation on
top of native AWS primitives.

| Failure scenario | Detection | Automatic recovery |
|------------------|-----------|--------------------|
| App fails HTTP health check | ALB target group health check | ASG replaces the instance |
| Underlying host/hardware fault | CloudWatch `StatusCheckFailed_System` | Native EC2 auto-recover |
| ALB reports unhealthy targets | CloudWatch alarm → SNS | Lambda forces ASG replacement |
| Instance stopped unexpectedly | EventBridge state-change rule | Lambda restarts tagged instance |
| Load spike | Target-tracking scaling policy | ASG scales out |

Every remediation publishes a custom CloudWatch metric, so self-healing is **provable**, not
assumed. A chaos-test script is included to exercise the loop, but this has not yet been run against a live AWS account.

**Stack:** Terraform · AWS VPC/ALB/Auto Scaling · CloudWatch · SNS · EventBridge · Lambda (Python) · least-privilege IAM

---

## 🔄 End-to-End Azure DevOps Project

A complete CI/CD path on Azure DevOps: build → security gate → infrastructure provisioning →
progressive dev → staging → production rollout.

```
Build & Test → Security Scan (CredScan + dependency scan) → Provision (Bicep)
            → Deploy Dev → Deploy Staging (approval) → Deploy Prod (approval + slot swap)
```

The same build artifact flows through every environment unchanged, `main.bicep` is parameterized
per environment (SKU, retention, autoscale), and production receives a pre-warmed slot swap so
there's no cold-start gap.

**Stack:** Azure DevOps Pipelines · Bicep · Azure App Service · Application Insights · Log Analytics · deployment slots · environment approvals

---

## Repository layout

```
cloud-devops-projects/
├── self-healing-aws-infra/    # Terraform + Lambda auto-remediation
└── azure-devops-pipeline/     # Azure DevOps multi-stage pipeline + Bicep IaC
```
