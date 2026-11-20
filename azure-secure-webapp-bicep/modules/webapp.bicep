@description('Azure region.')
param location string
param prefix string
param tags object
@description('App Service plan SKU, for example B1.')
param skuName string
param appInsightsConnectionString string
@description('Key Vault secret URI (without version) the app reads through a Key Vault reference.')
param secretUri string
param workspaceId string

resource plan 'Microsoft.Web/serverfarms@2023-12-01' = {
  name: '${prefix}-plan'
  location: location
  tags: tags
  kind: 'linux'
  sku: {
    name: skuName
  }
  properties: {
    reserved: true
  }
}

resource site 'Microsoft.Web/sites@2023-12-01' = {
  name: '${prefix}-app'
  location: location
  tags: tags
  kind: 'app,linux'
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    serverFarmId: plan.id
    httpsOnly: true
    clientAffinityEnabled: false
    siteConfig: {
      linuxFxVersion: 'PYTHON|3.12'
      appCommandLine: 'python app.py'
      minTlsVersion: '1.2'
      ftpsState: 'Disabled'
      http20Enabled: true
      healthCheckPath: '/health'
      alwaysOn: true
      appSettings: [
        {
          name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
          value: appInsightsConnectionString
        }
        {
          name: 'WEBSITES_PORT'
          value: '8000'
        }
        {
          name: 'SCM_DO_BUILD_DURING_DEPLOYMENT'
          value: 'false'
        }
        {
          // Key Vault reference: App Service resolves this with the app's managed identity.
          name: 'DEMO_SECRET'
          value: '@Microsoft.KeyVault(SecretUri=${secretUri})'
        }
      ]
    }
  }
}

resource diag 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'logs-to-law'
  scope: site
  properties: {
    workspaceId: workspaceId
    logs: [
      {
        category: 'AppServiceHTTPLogs'
        enabled: true
      }
      {
        category: 'AppServiceConsoleLogs'
        enabled: true
      }
      {
        category: 'AppServiceAppLogs'
        enabled: true
      }
    ]
  }
}

output appName string = site.name
output principalId string = site.identity.principalId
output hostName string = site.properties.defaultHostName
