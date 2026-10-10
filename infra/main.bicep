// Typecast on Azure Container Apps.
//
// One container app serving the frontend and API, PostgreSQL Flexible Server for
// the database, and an Azure Files share mounted at /data for uploads. Optional
// "Sign in with Microsoft" and "Sign in with Google", run by Typecast itself.
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

@description('Application (client) ID of the Entra ID app registration for "Sign in with Microsoft". Empty: no Microsoft button.')
param microsoftClientId string = ''

@description('Client secret of that app registration.')
@secure()
param microsoftClientSecret string = ''

@description('Entra ID directory whose accounts may sign in with Microsoft. Emails from it are trusted to match existing accounts.')
param tenantId string = subscription().tenantId

@description('OAuth client ID from Google Cloud for "Sign in with Google". Empty: no Google button.')
param googleClientId string = ''

@description('Client secret of that Google OAuth client.')
@secure()
param googleClientSecret string = ''

@description('Expiry of the SAS behind the retired Easy Auth token store secret; see the note on legacySecrets.')
param tokenStoreSasExpiry string = dateTimeAdd(utcNow(), 'P1Y')

@description('Your own hostname for the app, such as typecast.example.com. Needs a CNAME to the app\'s default address and an asuid TXT record first; see infra/README.md. Empty serves only the default address.')
param customHostname string = ''

@description('ID of the managed certificate already issued for customHostname. The Infrastructure workflow looks it up; empty attaches the hostname and requests one.')
param customHostnameCertificateId string = ''

@description('Registry credentials, only for a private image. Leave empty for a public ghcr.io package.')
param registryUsername string = ''
@secure()
param registryPassword string = ''

var microsoft = !empty(microsoftClientId)
var google = !empty(googleClientId)
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

resource tokenContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = if (microsoft) {
  parent: blobService
  name: tokenContainerName
  properties: { publicAccess: 'None' }
}

// Easy Auth's token store, from before sign-in moved into the app. Kept only so
// the secret it was configured with still exists while an install switches
// Easy Auth off (see legacySecrets); remove once no install still has it on.
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
var adminSecrets = empty(adminPassword) ? [] : [{ name: 'admin-password', value: adminPassword }]
var registrySecrets = empty(registryPassword) ? [] : [{ name: 'registry-password', value: registryPassword }]
// The Microsoft secret keeps the name Easy Auth used, and the token store secret
// stays, so neither disappears while the old Easy Auth configuration that names
// them is being switched off in the same deployment.
var microsoftSecrets = microsoft
  ? [
      { name: 'microsoft-provider-authentication-secret', value: microsoftClientSecret }
      { name: 'token-store-sas-url', value: tokenStoreSasUrl }
    ]
  : []
var googleSecrets = google ? [{ name: 'google-client-secret', value: googleClientSecret }] : []

var baseEnv = [
  { name: 'TYPECAST_DATA_DIR', value: '/data' }
  { name: 'DATABASE_URL', secretRef: 'database-url' }
  { name: 'SECRET_KEY', secretRef: 'secret-key' }
  { name: 'TYPECAST_ADMIN_EMAIL', value: adminEmail }
  // The ingress terminates TLS; this redirects anything that arrives as HTTP and
  // sends HSTS. /api/health is exempt so probes are not redirected.
  { name: 'TYPECAST_FORCE_HTTPS', value: '1' }
  // Typecast shows its own sign-in page: password, plus Microsoft and Google
  // when configured. The app, not the edge, decides who gets in.
  { name: 'TYPECAST_AUTH_MODE', value: 'multi' }
]
var adminEnv = empty(adminPassword) ? [] : [{ name: 'TYPECAST_ADMIN_PASSWORD', secretRef: 'admin-password' }]
var microsoftEnv = microsoft
  ? [
      { name: 'TYPECAST_MICROSOFT_CLIENT_ID', value: microsoftClientId }
      { name: 'TYPECAST_MICROSOFT_CLIENT_SECRET', secretRef: 'microsoft-provider-authentication-secret' }
      { name: 'TYPECAST_MICROSOFT_TENANT', value: tenantId }
    ]
  : []
var googleEnv = google
  ? [
      { name: 'TYPECAST_GOOGLE_CLIENT_ID', value: googleClientId }
      { name: 'TYPECAST_GOOGLE_CLIENT_SECRET', secretRef: 'google-client-secret' }
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
      secrets: concat(baseSecrets, adminSecrets, registrySecrets, microsoftSecrets, googleSecrets)
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
          env: concat(baseEnv, adminEnv, microsoftEnv, googleEnv)
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

// Container Apps authentication (Easy Auth), switched off explicitly. An install
// that ran the earlier template has it on, and a deployment never deletes a
// resource just because the template stopped declaring it: left alone, it would
// keep sending everyone to Microsoft before Typecast's own sign-in page.
resource auth 'Microsoft.App/containerApps/authConfigs@2024-03-01' = {
  parent: app
  name: 'current'
  properties: {
    platform: { enabled: false }
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
@description('Register as a Web redirect URI on the Entra ID app registration.')
output microsoftRedirectUri string = 'https://${publicHost}/api/auth/oidc/microsoft/callback'
@description('Register as an authorised redirect URI on the Google OAuth client.')
output googleRedirectUri string = 'https://${publicHost}/api/auth/oidc/google/callback'
@description('Set when this run requested a certificate; the workflow deploys again with it to bind the hostname.')
output requestedCertificateId string = requestCertificate ? certificate.id : ''
output postgresServer string = postgres.properties.fullyQualifiedDomainName
output storageAccount string = storage.name
