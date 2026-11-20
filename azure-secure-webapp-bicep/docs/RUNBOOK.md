# Runbook

Run in Azure Cloud Shell (bash), signed in to the subscription you want to use. All commands are in
`scripts/drill.sh`. Delete the resource group the same day.

1. `git clone https://github.com/dineshravichandiran/cloud-devops-projects && cd cloud-devops-projects/azure-secure-webapp-bicep`
2. `scripts/drill.sh deploy` - creates the resource group, runs `what-if`, deploys, uploads `app/app.py`.
   Note the times it prints and anything the deployment complains about.
3. `scripts/drill.sh prove` - shows the Key Vault reference status (expect `Resolved`) and calls `/health` and
   `/secret-check` (expect HTTP 200 and `resolved: true`).
4. `scripts/drill.sh deny` - deploys again with `grantKeyVaultAccess=false` (the role assignment is removed),
   restarts the app and shows the reference status and `/secret-check`. Expect the reference to stop resolving
   and `/secret-check` to return 503. This is the "managed identity lost access" failure.
5. `scripts/drill.sh restore` - puts the role assignment back and shows the app recover. Role propagation can take a few
   minutes, so the script retries.
6. `scripts/drill.sh destroy` - deletes the resource group and purges the soft-deleted vault.
7. `scripts/drill.sh sweep` - lists resource groups, resources and soft-deleted vaults. Everything for the lab should
   be gone. Write down what is left, if anything.

Write the real output into `docs/evidence/`. Only mark something "done" in the README if it ran.
