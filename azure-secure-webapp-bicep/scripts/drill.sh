#!/usr/bin/env bash
# Helper for docs/RUNBOOK.md. Run it in Azure Cloud Shell (bash) from the repo folder.
#   scripts/drill.sh deploy     what-if, deploy, push the app code
#   scripts/drill.sh prove      show the Key Vault reference status and call the app
#   scripts/drill.sh deny       delete the role assignment, restart, poll until the reference fails
#   scripts/drill.sh restore    deploy again with the role assignment, restart, show recovery
#   scripts/drill.sh destroy    delete the resource group and purge the soft-deleted vault
#   scripts/drill.sh sweep      list what is left in the subscription
set -euo pipefail

RG="${RG:-rg-secweb-lab}"
LOCATION="${LOCATION:-centralindia}"
HERE="$(cd "$(dirname "$0")/.." && pwd)"

app_name()   { az deployment group show -g "$RG" -n main --query properties.outputs.appName.value -o tsv; }
app_url()    { az deployment group show -g "$RG" -n main --query properties.outputs.appUrl.value -o tsv; }
vault_name() { az deployment group show -g "$RG" -n main --query properties.outputs.vaultName.value -o tsv; }

ref_status() {
  local app sub
  app=$(app_name); sub=$(az account show --query id -o tsv)
  az rest --method get \
    --url "https://management.azure.com/subscriptions/$sub/resourceGroups/$RG/providers/Microsoft.Web/sites/$app/config/configreferences/appsettings?api-version=2023-12-01" \
    --query "value[].{setting:name, status:properties.status, details:properties.details}" -o json
}

call() {
  local url code
  url=$(app_url)
  for i in 1 2 3 4 5 6; do
    code=$(curl -s -o /tmp/body.json -w '%{http_code}' --max-time 20 "$url$1" || true)
    echo "attempt $i: GET $1 -> HTTP $code $(cat /tmp/body.json 2>/dev/null)"
    [ "$code" = "200" ] && return 0
    sleep 15
  done
  return 1
}

case "${1:-}" in
  deploy)
    az group create -n "$RG" -l "$LOCATION" -o none
    date -u +"%FT%TZ what-if started"
    az deployment group what-if -g "$RG" -n main -f "$HERE/main.bicep" --no-pretty-print -o none || true
    date -u +"%FT%TZ deployment started"
    az deployment group create -g "$RG" -n main -f "$HERE/main.bicep" -o table
    date -u +"%FT%TZ deployment finished"
    (cd "$HERE/app" && zip -qr /tmp/app.zip app.py)
    az webapp deploy -g "$RG" -n "$(app_name)" --src-path /tmp/app.zip --type zip --restart true -o none
    echo "app deployed: $(app_url)"
    ;;
  prove)
    date -u +"%FT%TZ"
    echo "## Key Vault reference status"; ref_status
    echo "## health";       call /health
    echo "## secret-check"; call /secret-check
    ;;
  deny)
    # A Complete-mode redeploy with grantKeyVaultAccess=false does NOT remove the role assignment (it is an
    # extension resource on the vault), so the role is deleted explicitly. Key Vault also keeps authorizing for
    # a while after the delete. In the one real run the reference kept resolving for about 12 minutes after the
    # delete and a restart; the first 503 came about 2.5 minutes after the app setting was saved again. One run
    # cannot say whether the save or the passing time caused it, so the script does both and polls.
    # This version of the phase has not been re-run end to end.
    app=$(app_name); V=$(vault_name)
    vid=$(az keyvault show -n "$V" --query id -o tsv)
    pid=$(az webapp identity show -g "$RG" -n "$app" --query principalId -o tsv)
    date -u +"%FT%TZ deleting role assignment"
    az role assignment delete --assignee "$pid" --role "Key Vault Secrets User" --scope "$vid"
    echo "role assignments left on the vault: $(az role assignment list --scope "$vid" --query 'length(@)' -o tsv)"
    az webapp restart -g "$RG" -n "$app"
    ref=$(az webapp config appsettings list -g "$RG" -n "$app" --query "[?name=='DEMO_SECRET'].value|[0]" -o tsv)
    for i in $(seq 1 40); do
      if [ "$i" = "30" ]; then
        date -u +"%FT%TZ saving the app setting again to force a new lookup"
        az webapp config appsettings set -g "$RG" -n "$app" --settings "DEMO_SECRET=$ref" -o none
      fi
      code=$(curl -s -o /tmp/body.json -w '%{http_code}' --max-time 30 "$(app_url)/secret-check" || true)
      echo "$(date -u +%T) secret-check -> HTTP $code $(cut -c1-100 /tmp/body.json 2>/dev/null)"
      [ "$code" = "503" ] && break
      sleep 20
    done
    echo "## Key Vault reference status"; ref_status
    ;;
  restore)
    date -u +"%FT%TZ role assignment restored"
    az deployment group create -g "$RG" -n main -f "$HERE/main.bicep" -p grantKeyVaultAccess=true -o none
    az webapp restart -g "$RG" -n "$(app_name)"
    sleep 60
    echo "## Key Vault reference status"; ref_status
    echo "## secret-check"; call /secret-check
    ;;
  destroy)
    V=$(vault_name)
    date -u +"%FT%TZ destroy started"
    az group delete -n "$RG" --yes
    date -u +"%FT%TZ resource group deleted"
    az keyvault purge --name "$V" --location "$LOCATION" || echo "purge: $V not purgeable or already gone"
    ;;
  sweep)
    date -u +"%FT%TZ"
    echo "## resource groups";           az group list --query "[].name" -o tsv
    echo "## resources (all groups)";    az resource list --query "[].{name:name,type:type,rg:resourceGroup}" -o table
    echo "## soft-deleted vaults";       az keyvault list-deleted --query "[].name" -o tsv
    ;;
  *)
    sed -n 2,9p "$0"; exit 1;;
esac
