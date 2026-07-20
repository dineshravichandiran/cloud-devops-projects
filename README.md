# ☁️ Cloud & DevOps Projects

Production-grade automation and infrastructure-as-code projects that extend hands-on cloud
operations experience into repeatable, secure, self-service delivery.

> Built and maintained by **Dinesh Ravichandiran** — Cloud Services NOC Engineer, keeping
> Fortune 500 platforms running 24×7 (Kubernetes · AWS · Azure · Linux).

---

## Projects

| Project | What it demonstrates |
|---------|----------------------|
| 🔐 **[End-to-End DevSecOps CI Pipeline](devsecops-ci-pipeline)** | Security-integrated automated delivery — a GitHub Actions pipeline that gates every deployment behind secret scanning, SAST, dependency (SCA) auditing, container image scanning, and DAST. |
| ♻️ **[Self-Healing Infrastructure on AWS](self-healing-aws-infra)** | Auto-recovery and resilience — Terraform-provisioned VPC/ALB/Auto Scaling Group with CloudWatch alarms and Lambda-based auto-remediation that detects and recovers from failure with no human in the loop. |
| 🔄 **[End-to-End Azure DevOps Project](azure-devops-pipeline)** | Full CI/CD on Azure — a multi-stage Azure DevOps pipeline that builds, security-scans, provisions infrastructure with Bicep, and promotes releases through dev → staging → production with approvals and slot swaps. |

Each project folder has its own README with an architecture diagram, design rationale, and setup
instructions.

---

## Proof of work

The DevSecOps pipeline wasn't just written and left — it runs on every push, and it broke: every
run failed at the SAST step because CodeQL was configured to scan for JavaScript/TypeScript in a
repo that has none. Found the root cause, fixed it, and verified the pipeline runs past that point
now, live on GitHub Actions:

![DevSecOps CI Pipeline failing on every push due to a CodeQL language misconfiguration, root cause found, fixed, and reverified live](screenshots/devsecops-pipeline-bug-and-fix.png)

---

## 🔐 End-to-End DevSecOps CI Pipeline

A CI pipeline that shifts security **left** and enforces it as a required gate — a build cannot
reach staging without passing every check.

```
commit → Secret Scan (Gitleaks) → SAST (Semgrep + CodeQL) → SCA (OWASP Dependency-Check)
       → Build hardened container → Container Scan (Trivy) → DAST (OWASP ZAP)
       → Deploy to Staging → Security Policy Gate
```

Every scanner uploads **SARIF** to the GitHub Security tab, so findings become native code-scanning
alerts instead of being buried in build logs. Fail-fast ordering runs the cheap checks (secrets,
SAST) before the expensive build.

**Stack:** GitHub Actions · Gitleaks · Semgrep · CodeQL · OWASP Dependency-Check · Trivy · OWASP ZAP · hardened non-root Docker image

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
assumed. A chaos-test script validates the whole loop end-to-end.

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
├── devsecops-ci-pipeline/     # GitHub Actions security pipeline + hardened Dockerfile
├── self-healing-aws-infra/    # Terraform + Lambda auto-remediation
└── azure-devops-pipeline/     # Azure DevOps multi-stage pipeline + Bicep IaC
```
