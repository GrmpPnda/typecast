// Typecast on Azure Container Apps.
//
// One container app serving the frontend and API, PostgreSQL Flexible Server for
// the database, and an Azure Files share mounted at /data for uploads. Optional
// Microsoft Entra ID single sign-on through Container Apps authentication.
//
// Deployed by .github/workflows/infra.yml; safe to re-run. See infra/README.md.

targetScope = 'resourceGroup'

@description('Azure region. Defaults to the resource group\'s.')
param location string = resourceGroup().location

@description('Base name for resources. Lowercase letters and digits.')
@minLength(3)
@maxLength(16)
param appName string = 'typecast'

@description('Container image to run.')
param image string

@description('Email of the first administrator. Under single sign-on this account links on their first sign-in.')
param adminEmail string

@description('Password for the first administrator. Required without single sign-on; ignored with it.')
@secure()
param adminPassword string = ''

@description('Signs auth tokens and derives the key that encrypts stored API keys. Long and random; changing it makes stored API keys unreadable.')
@secure()
@minLength(32)
param secretKey string

@description('Region for the PostgreSQL server, when it differs from the app\'s. Some subscriptions cannot create Flexible Server in some regions, which fails as "The value of the \'Version\' should be in: []". Empty means the same region as the app.')
param postgresLocation string = ''

@description('PostgreSQL administrator login.')
param postgresAdminLogin string = 'typecast'

@secure()
@minLength(16)
param postgresAdminPassword string

@description('libpq sslmode for the database connection. verify-full checks the server certificate against the image\'s CA bundle; require only encrypts.')
@allowed(['verify-full', 'require'])
param postgresSslMode string = 'verify-full'

@description('Application (client) ID of the Entra ID app registration. Empty disables single sign-on, and the app uses its own passwords.')
param ssoClientId string = ''

@description('Client secret of that app registration.')
@secure()
param ssoClientSecret string = ''

@description('Entra ID tenant that signs people in.')
param tenantId string = subscription().tenantId

@description('Expiry of the SAS that lets the sign-in layer use its token store. Renew by re-running before then.')
param tokenStoreSasExpiry string = dateTimeAdd(utcNow(), 'P1Y')

@description('Your own hostname for the app, such as typecast.example.com. Needs a CNAME to the app\'s default address and an asuid TXT record first; see infra/README.md. Empty serves only the default address.')
param customHostname string = ''

@description('ID of the managed certificate already issued for customHostname. The Infrastructure workflow looks it up; empty attaches the hostname and requests one.')
param customHostnameCertificateId string = ''

@description('Registry credentials, only for a private image. Leave empty for a public ghcr.io package.')
param registryUsername string = ''
@secure()
param registryPassword string = ''

var sso = !empty(ssoClientId)
// A managed certificate can only be issued for a hostname already attached to
// the app, and the app can only serve HTTPS on it once the certificate exists.
// So the first run attaches it unbound and requests the certificate; the
// workflow then deploys again with the certificate's ID to bind it.
var customDomain = !empty(customHostname)
var requestCertificate = customDomain && empty(customHostnameCertificateId)
var publicHost = customDomain ? customHostname : app.properties.configuration.ingress.fqdn
var suffix = uniqueString(resourceGroup().id)
var storageName = take('${appName}${suffix}', 24)
var postgresName = '${appName}-pg-${suffix}'
var shareName = 'typecast-data'
var tokenContainerName = 'easyauth-tokens'

// --- logs -------------------------------------------------------------------------------

resource logs 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: '${appName}-logs'
  location: location
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
  }
}

// --- storage: uploads share and the sign-in token store ----------------------------------

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageName
  location: location
  sku: { name: 'Standard_LRS' }
  kind: 'StorageV2'
  properties: {
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
    allowBlobPublicAccess: false
    // Container Apps mounts Azure Files with the account key.
    allowSharedKeyAccess: true
  }
}

resource fileService 'Microsoft.Storage/storageAccounts/fileServices@2023-05-01' = {
  parent: storage
  name: 'default'
}

resource share 'Microsoft.Storage/storageAccounts/fileServices/shares@2023-05-01' = {
  parent: fileService
  name: shareName
  properties: { shareQuota: 32 }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: storage
  name: 'default'
}

resource tokenContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = if (sso) {
  parent: blobService
  name: tokenContainerName
  properties: { publicAccess: 'None' }
}

// Container Apps authentication forwards the signed ID token in
// X-MS-TOKEN-AAD-ID-TOKEN only when its token store is enabled, and the store
// needs a blob container SAS. Typecast verifies that token, which is what makes
// forged identity headers useless.
var tokenStoreSas = storage.listServiceSas('2023-05-01', {
  canonicalizedResource: '/blob/${storage.name}/${tokenContainerName}'
  signedResource: 'c'
  signedPermission: 'rwdl'
  signedExpiry: tokenStoreSasExpiry
  signedProtocol: 'https'
}).serviceSasToken
var tokenStoreSasUrl = 'https://${storage.name}.blob.${environment().suffixes.storage}/${tokenContainerName}?${tokenStoreSas}'

// --- database ---------------------------------------------------------------------------

resource postgres 'Microsoft.DBforPostgreSQL/flexibleServers@2024-08-01' = {
  name: postgresName
  location: empty(postgresLocation) ? location : postgresLocation
  sku: {
    name: 'Standard_B1ms'
    tier: 'Burstable'
  }
  properties: {
    version: '16'
    administratorLogin: postgresAdminLogin
    administratorLoginPassword: postgresAdminPassword
    storage: { storageSizeGB: 32 }
    backup: {
      backupRetentionDays: 7
      geoRedundantBackup: 'Disabled'
    }
    highAvailability: { mode: 'Disabled' }
    network: { publicNetworkAccess: 'Enabled' }
  }
}

resource database 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2024-08-01' = {
  parent: postgres
  name: 'typecast'
  properties: {
    charset: 'UTF8'
    collation: 'en_US.utf8'
  }
}

// Container Apps on the consumption plan has no fixed outbound address, so the
// server admits Azure-hosted clients. It still requires TLS and the password;
// moving both into a virtual network removes the public endpoint entirely.
resource allowAzure 'Microsoft.DBforPostgreSQL/flexibleServers/firewallRules@2024-08-01' = {
  parent: postgres
  name: 'AllowAzureServices'
  properties: {
    startIpAddress: '0.0.0.0'
    endIpAddress: '0.0.0.0'
  }
}

var databaseUrl = 'postgresql://${postgresAdminLogin}:${uriComponent(postgresAdminPassword)}@${postgres.properties.fullyQualifiedDomainName}:5432/${database.name}?sslmode=${postgresSslMode}'

// --- container apps environment ---------------------------------------------------------

resource containerEnv 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: '${appName}-env'
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logs.properties.customerId
        sharedKey: logs.listKeys().primarySharedKey
      }
    }
  }
}

resource environmentStorage 'Microsoft.App/managedEnvironments/storages@2024-03-01' = {
  parent: containerEnv
  name: shareName
  properties: {
    azureFile: {
      accountName: storage.name
      accountKey: storage.listKeys().keys[0].value
      shareName: share.name
      accessMode: 'ReadWrite'
    }
  }
}

// --- the app ----------------------------------------------------------------------------

var baseSecrets = [
  { name: 'secret-key', value: secretKey }
  { name: 'database-url', value: databaseUrl }
]
var adminSecrets = (!sso && !empty(adminPassword)) ? [{ name: 'admin-password', value: adminPassword }] : []
var registrySecrets = empty(registryPassword) ? [] : [{ name: 'registry-password', value: registryPassword }]
var ssoSecrets = sso
  ? [
      { name: 'microsoft-provider-authentication-secret', value: ssoClientSecret }
      { name: 'token-store-sas-url', value: tokenStoreSasUrl }
    ]
  : []

var baseEnv = [
  { name: 'TYPECAST_DATA_DIR', value: '/data' }
  { name: 'DATABASE_URL', secretRef: 'database-url' }
  { name: 'SECRET_KEY', secretRef: 'secret-key' }
  { name: 'TYPECAST_ADMIN_EMAIL', value: adminEmail }
  // The ingress terminates TLS; this redirects anything that arrives as HTTP and
  // sends HSTS. /api/health is exempt so probes are not redirected.
  { name: 'TYPECAST_FORCE_HTTPS', value: '1' }
  { name: 'TYPECAST_AUTH_MODE', value: sso ? 'proxy' : 'multi' }
]
var adminEnv = (!sso && !empty(adminPassword)) ? [{ name: 'TYPECAST_ADMIN_PASSWORD', secretRef: 'admin-password' }] : []
var ssoEnv = sso
  ? [
      // Both issuer forms, since Entra issues v1 or v2 tokens depending on how the
      // app registration is configured. Discovery uses the first.
      { name: 'TYPECAST_OIDC_ISSUER', value: '${environment().authentication.loginEndpoint}${tenantId}/v2.0,https://sts.windows.net/${tenantId}/' }
      { name: 'TYPECAST_OIDC_AUDIENCE', value: ssoClientId }
      { name: 'TYPECAST_PROXY_PRESET', value: 'easyauth' }
    ]
  : []

resource app 'Microsoft.App/containerApps@2024-03-01' = {
  name: appName
  location: location
  properties: {
    managedEnvironmentId: containerEnv.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 8000
        transport: 'auto'
        allowInsecure: false
        customDomains: customDomain
          ? [
              empty(customHostnameCertificateId)
                ? { name: customHostname, bindingType: 'Disabled' }
                : { name: customHostname, bindingType: 'SniEnabled', certificateId: customHostnameCertificateId }
            ]
          : []
      }
      registries: empty(registryUsername)
        ? []
        : [{ server: 'ghcr.io', username: registryUsername, passwordSecretRef: 'registry-password' }]
      secrets: concat(baseSecrets, adminSecrets, registrySecrets, ssoSecrets)
    }
    template: {
      containers: [
        {
          name: 'typecast'
          image: image
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          env: concat(baseEnv, adminEnv, ssoEnv)
          volumeMounts: [{ volumeName: 'data', mountPath: '/data' }]
          probes: [
            {
              // Migrations run at startup; give them time before liveness applies.
              type: 'Startup'
              httpGet: { path: '/api/health', port: 8000 }
              periodSeconds: 5
              failureThreshold: 36
            }
            {
              type: 'Liveness'
              httpGet: { path: '/api/health', port: 8000 }
              periodSeconds: 30
            }
            {
              type: 'Readiness'
              httpGet: { path: '/api/health', port: 8000 }
              periodSeconds: 10
            }
          ]
        }
      ]
      volumes: [
        {
          name: 'data'
          storageType: 'AzureFile'
          storageName: environmentStorage.name
        }
      ]
      // One replica at most: migrations run at startup and would race, and the
      // Google Drive sign-in keeps its state in memory. Zero when idle.
      scale: {
        minReplicas: 0
        maxReplicas: 1
      }
    }
  }
}

resource auth 'Microsoft.App/containerApps/authConfigs@2024-03-01' = if (sso) {
  parent: app
  name: 'current'
  properties: {
    platform: { enabled: true }
    globalValidation: {
      unauthenticatedClientAction: 'RedirectToLoginPage'
      redirectToProvider: 'azureactivedirectory'
      // Probes and the deploy workflow's check reach this without signing in.
      excludedPaths: ['/api/health']
    }
    identityProviders: {
      azureActiveDirectory: {
        enabled: true
        registration: {
          clientId: ssoClientId
          clientSecretSettingName: 'microsoft-provider-authentication-secret'
          openIdIssuer: 'https://sts.windows.net/${tenantId}/v2.0'
        }
        validation: {
          allowedAudiences: ['api://${ssoClientId}']
        }
      }
    }
    login: {
      tokenStore: {
        enabled: true
        azureBlobStorage: { sasUrlSettingName: 'token-store-sas-url' }
      }
    }
    httpSettings: { requireHttps: true }
  }
}

// Free, issued by DigiCert, and renewed by Azure. Validated through the CNAME.
resource certificate 'Microsoft.App/managedEnvironments/managedCertificates@2024-03-01' = if (requestCertificate) {
  parent: containerEnv
  name: take('${appName}-${replace(customHostname, '.', '-')}', 60)
  location: location
  properties: {
    subjectName: customHostname
    domainControlValidation: 'CNAME'
  }
  dependsOn: [app]
}

output appName string = app.name
output appUrl string = 'https://${publicHost}'
output defaultUrl string = 'https://${app.properties.configuration.ingress.fqdn}'
@description('Register this as a Web redirect URI on the Entra ID app registration.')
output ssoRedirectUri string = 'https://${publicHost}/.auth/login/aad/callback'
@description('Set when this run requested a certificate; the workflow deploys again with it to bind the hostname.')
output requestedCertificateId string = requestCertificate ? certificate.id : ''
output postgresServer string = postgres.properties.fullyQualifiedDomainName
output storageAccount string = storage.name
