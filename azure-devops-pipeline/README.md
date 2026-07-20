# 🔄 End-to-End Azure DevOps Project

A complete CI/CD pipeline on Azure DevOps that takes a change from commit to production: build, test, security gate, infrastructure provisioning, and a progressive dev → staging → production rollout with slot swaps and approval gates.

## Why this exists

A "full CI/CD on Azure" project should demonstrate the whole path a change takes — not just a build step. This pipeline provisions its own infrastructure with Bicep, promotes the same build artifact through three environments, and uses deployment slots plus smoke tests so a bad release never lands on production without warning.

## Pipeline flow

```
push to main/develop
        │
        ▼
┌───────────────┐
│    Build       │  restore → build → unit tests + code coverage → publish artifact
└───────┬───────┘
        ▼
┌───────────────┐
│ Security Scan  │  Mend/WhiteSource dependency scan + CredScan, breaks build on findings
└───────┬───────┘
        ▼
┌───────────────┐
│ Provision Dev  │  az group create + Bicep deploy (App Service, App Insights, Log Analytics)
└───────┬───────┘
        ▼
┌───────────────┐
│  Deploy Dev    │  deploy artifact → smoke test /health
└───────┬───────┘
        ▼
┌────────────────────┐
│  Deploy Staging     │  Bicep deploy (staging tier) → deploy to staging slot → smoke test
│  (manual approval)  │
└───────┬────────────┘
        ▼
┌────────────────────┐
│  Deploy Production  │  Bicep deploy (prod tier + autoscale) → slot swap → smoke test
│  (manual approval)  │
└─────────────────────┘
```

The same build artifact (`drop`) flows through every environment unchanged — what's tested in dev and validated in staging is exactly what reaches production.

## Repository layout

```
azure-devops-pipeline/
├── azure-pipelines.yml   # the full multi-stage pipeline
├── bicep/
│   └── main.bicep         # App Service Plan, Web App, staging slot, App Insights,
│                           # Log Analytics, diagnostics, prod autoscale rule
└── scripts/
    └── smoke_test.sh       # polls /health after each deployment stage
```

## Environment gates

`staging` and `prod` are modeled as Azure DevOps **Environments** with approval
checks configured outside the YAML (Project Settings → Environments →
Approvals and checks). This keeps who-can-approve-what a governance decision
rather than something baked into pipeline code.

| Environment | App Service tier | Deployment slot | Approval required |
|-------------|------------------|------------------|--------------------|
| dev         | B1 (Basic)        | No               | No                 |
| staging     | S1 (Standard)     | Yes              | Yes                |
| prod        | P1v3 (PremiumV3) + autoscale | Yes (swap into prod) | Yes |

## Design decisions

- **Infrastructure defined once, parameterized per environment**: `main.bicep` takes an `environmentName` parameter and derives SKU, retention, and whether a slot exists — one template, three environments, no drift between them.
- **Slot swap for prod, not a fresh deploy**: production receives a swap from a pre-warmed staging slot, so there's no cold-start gap during the release.
- **Smoke test after every stage, not just prod**: catching a bad build in dev is far cheaper than catching it after the prod swap.
- **Security gate before infrastructure spend**: dependency and credential scanning run before any Azure resources are provisioned, so a flagged build never gets the chance to consume cloud spend.

## Setting this up

1. Create an Azure DevOps service connection named `azure-service-connection` (Project Settings → Service connections) scoped to the target subscription.
2. Create three Environments (`dev`, `staging`, `prod`) and add approval checks to `staging` and `prod`.
3. Set the `subscriptionId` pipeline variable (or wire it via a variable group) to your Azure subscription ID.
4. Point `azure-pipelines.yml` at your actual `.csproj` paths if this is adapted to a different app than the placeholder .NET project referenced here.

## Current verification status

Written and reviewed, not yet run end-to-end — this one hasn't gone through the same live-testing pass as the other projects in this account, since it needs an Azure DevOps organization and subscription that wasn't available while building this. The YAML is internally consistent (stage dependencies, environment references, and variable usage all check out on read-through), but unlike `devsecops-ci-pipeline` (verified live in GitHub Actions after fixing 3 real bugs) or `ansible-zabbix-baseline` (verified in a real test environment), no claim is made here that this has actually executed successfully.
