# Azure Secure Web App with Bicep

A small, secure web app on Azure written as Bicep: an App Service (Linux, Python) that reads a secret
from Key Vault through a **Key Vault reference**, using its own **system-assigned managed identity**
(no passwords or connection strings in the code or the deployment). Logs and metrics go to Log Analytics
and Application Insights.

> **Status: applied once to a real Azure subscription, drilled, destroyed (2026-11-20).** Evidence, with times, is in
> [`docs/evidence/real-deploy-2026-11-20.txt`](docs/evidence/real-deploy-2026-11-20.txt). It ran on an Azure free account in
> Central India (B1 plan) and was deleted the same day; leftover check clean.

## What running it showed

| Step | Result |
|---|---|
| Deploy | Infrastructure deployment succeeded in about 3 minutes; the app answered `/health` with 200 after the code upload |
| Key Vault reference | `Resolved`; `/secret-check` 200 with `resolved: true` (the secret is never returned) |
| Remove the role assignment | Access was lost only after about 12.5 minutes: `/secret-check` 503 and reference status `AccessToKeyVaultDenied` |
| Put it back | Recovered in about 4.5 minutes, 200 again |
| Destroy | Resource group deleted in about 80 seconds, vault purged, sweep found nothing left |

Things the run found that I had got wrong or had not expected:

- **My deny step did not deny anything.** I redeployed in Complete mode with the role switched off and the script said
  "role assignment removed", but the role was still on the vault. Complete mode does not delete that extension
  resource. The script now deletes the role explicitly. The rewritten script has not been re-run end to end.
- **Revoking a role is not instant for a Key Vault reference.** The reference kept resolving for about 12 minutes after the
  delete and a restart. I also saved the app setting again before the first failure and cannot tell from one run which
  of the two caused it.
- **The secret changes on every deployment.** The template generates it with `newGuid()`, so each redeploy rotates it
  (the hash prefix changed between deployments). Fine for a demo, wrong for a real secret.
- The container failed its first start before the code was uploaded, then came up after the zip deploy.

## Not done

- Log Analytics and Application Insights were created but I did not query them, so the audit and request logs are unverified.
- No cost figure yet (Cost Management had not been read).
- Single instance, single region, no autoscale, public network access on the vault (no private endpoint).
- One lint warning (`no-unnecessary-dependson`) is still there. No CI deployment; the pipeline only lints and builds.

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
