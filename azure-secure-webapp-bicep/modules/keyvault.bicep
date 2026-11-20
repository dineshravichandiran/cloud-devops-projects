@description('Azure region.')
param location string
@description('Globally unique Key Vault name (3-24 chars).')
param name string
param tags object
@description('Log Analytics workspace for audit logs.')
param workspaceId string

@description('Value stored as the demo secret. Generated per deployment, never committed.')
@secure()
param demoSecretValue string = newGuid()

resource vault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: name
  location: location
  tags: tags
  properties: {
    tenantId: tenant().tenantId
    sku: {
      family: 'A'
      name: 'standard'
    }
    // Access is granted with Azure RBAC role assignments, not access policies.
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 7
    // Purge protection is not set, on purpose, so the lab vault can be purged after the drill.
    // For anything real, turn it on.
    publicNetworkAccess: 'Enabled'
    networkAcls: {
      defaultAction: 'Allow'
      bypass: 'AzureServices'
    }
  }
}

resource demoSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: vault
  name: 'demo-secret'
  properties: {
    value: demoSecretValue
  }
}

resource audit 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'audit-to-law'
  scope: vault
  properties: {
    workspaceId: workspaceId
    logs: [
      {
        categoryGroup: 'audit'
        enabled: true
      }
    ]
  }
}

output vaultName string = vault.name
output vaultId string = vault.id
output secretUri string = demoSecret.properties.secretUri
