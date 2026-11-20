# Azure Secure Web App with Bicep

A small, secure web app on Azure written as Bicep: an App Service (Linux, Python) that reads a secret
from Key Vault through a **Key Vault reference**, using its own **system-assigned managed identity**
(no passwords or connection strings in the code or the deployment). Logs and metrics go to Log Analytics
and Application Insights.

> **Status: written, not applied yet.** `main.bicep` has not been deployed to a real subscription as of this
> commit. This page is updated with what was actually run (and what was not) after the first real deployment.

## What it builds

| Piece | What it is for |
|---|---|
| App Service plan + web app (Linux, Python 3.12) | Runs `app/app.py`. HTTPS only, TLS 1.2 minimum, FTPS off, health check on `/health` |
| System-assigned managed identity | The app's identity. No secret is needed to reach Key Vault |
| Key Vault (Azure RBAC, soft delete on) | Holds `demo-secret` (a random value generated per deployment, never committed) |
| Role assignment: Key Vault Secrets User | Lets the app's identity read secret values and nothing else. A parameter switches it off for the drill |
| Log Analytics + Application Insights | App logs, request telemetry, Key Vault audit logs |

The app has two routes: `/health`, and `/secret-check`, which says whether the Key Vault reference resolved
(and the length of the value) but never returns the secret.

## Layout

```
main.bicep               resource-group deployment, wires the modules and the role assignment
modules/monitoring.bicep Log Analytics + Application Insights
modules/keyvault.bicep   Key Vault, the demo secret, audit diagnostic setting
modules/webapp.bicep     plan, web app, managed identity, Key Vault reference, diagnostic setting
app/app.py               the web app (standard library only)
scripts/drill.sh         deploy, prove, deny, restore, destroy, sweep (run in Azure Cloud Shell)
docs/RUNBOOK.md          the procedure
```

## Checks

`az bicep lint` and `az bicep build` run in CI on every change to this folder (see
`.github/workflows/azure-bicep-validate.yml`). That proves the templates compile and pass the linter. It does
not prove Azure accepts every setting; only a real deployment does.

## Cost

A B1 plan is the main cost while it exists. The runbook deletes the resource group the same day. No cost figure
is quoted here until it has been read from Cost Management.
