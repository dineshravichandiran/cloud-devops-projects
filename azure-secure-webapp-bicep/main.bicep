targetScope = 'resourceGroup'

@description('Azure region. Central India keeps latency low from Pune.')
param location string = resourceGroup().location

@description('Short project name used in resource names (lower case, 3-12 chars).')
@minLength(3)
@maxLength(12)
param projectName string = 'secweb'

@description('App Service plan SKU. B1 is the cheapest paid Linux plan with Always On.')
@allowed([
  'B1'
  'B2'
  'S1'
  'P0v3'
])
param skuName string = 'B1'

@description('Set to false to leave the managed identity without access to Key Vault (used in the drill).')
param grantKeyVaultAccess bool = true

var suffix = take(uniqueString(resourceGroup().id), 5)
var prefix = '${projectName}-${suffix}'
var tags = {
  project: 'azure-secure-webapp-bicep'
  purpose: 'lab'
}

// Key Vault Secrets User: read secret values, nothing else.
var keyVaultSecretsUserRoleId = '4633458b-17de-408a-b874-0445c86b69e6'

module monitoring 'modules/monitoring.bicep' = {
  name: 'monitoring'
  params: {
    location: location
    prefix: prefix
    tags: tags
  }
}

module vault 'modules/keyvault.bicep' = {
  name: 'keyvault'
  params: {
    location: location
    name: take('kv-${replace(prefix, '-', '')}', 24)
    tags: tags
    workspaceId: monitoring.outputs.workspaceId
  }
}

module web 'modules/webapp.bicep' = {
  name: 'webapp'
  params: {
    location: location
    prefix: prefix
    tags: tags
    skuName: skuName
    appInsightsConnectionString: monitoring.outputs.appInsightsConnectionString
    secretUri: vault.outputs.secretUri
    workspaceId: monitoring.outputs.workspaceId
  }
}

resource existingVault 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: take('kv-${replace(prefix, '-', '')}', 24)
}

resource secretsUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (grantKeyVaultAccess) {
  name: guid(existingVault.id, prefix, keyVaultSecretsUserRoleId)
  scope: existingVault
  dependsOn: [
    vault
  ]
  properties: {
    principalId: web.outputs.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', keyVaultSecretsUserRoleId)
  }
}

output appName string = web.outputs.appName
output appUrl string = 'https://${web.outputs.hostName}'
output vaultName string = vault.outputs.vaultName
