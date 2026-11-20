#!/usr/bin/env bash
# Helper for docs/RUNBOOK.md. Run it in Azure Cloud Shell (bash) from the repo folder.
#   scripts/drill.sh deploy     what-if, deploy, push the app code
#   scripts/drill.sh prove      show the Key Vault reference status and call the app
#   scripts/drill.sh deny       deploy again without the role assignment, restart, show failure
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
    date -u +"%FT%TZ role assignment removed (grantKeyVaultAccess=false)"
    az deployment group create -g "$RG" -n main -f "$HERE/main.bicep" -p grantKeyVaultAccess=false --mode Complete -o none
    az webapp restart -g "$RG" -n "$(app_name)"
    sleep 60
    echo "## Key Vault reference status"; ref_status
    echo "## secret-check (expect failure)"; call /secret-check || true
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
