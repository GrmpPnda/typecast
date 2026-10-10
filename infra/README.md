# Deploying Typecast to Azure

Every push to `main` is tested, built into a container image on GitHub Container
Registry, and rolled out to Azure Container Apps. The Azure resources themselves
are declared in [`main.bicep`](main.bicep) and applied by a workflow you run by
hand.

| | |
| --- | --- |
| App | Azure Container Apps: one container serving the frontend and API, scaling to zero when idle |
| Database | Azure Database for PostgreSQL Flexible Server, Burstable B1ms, TLS required |
| Uploads | Azure Files share mounted at `/data` |
| Sign-in | Typecast's own sign-in page: passwords, plus Microsoft and Google when configured |
| CI/CD | `.github/workflows/ci.yml`, `deploy.yml`, `infra.yml` |

Expect roughly $15–20 a month, nearly all of it the PostgreSQL server, which runs
continuously. The container app sits inside the consumption plan's free monthly
grant at personal-use traffic.

## One-time setup

Do these in order. The deploy workflow skips the Azure rollout until step 3's
variables exist, so pushes before then only publish images.

### 1. Publish the first image

Push to `main` (or run the **Deploy** workflow). It builds
`ghcr.io/<owner>/typecast:latest`. Azure pulls it anonymously, so it must be
public. A package published from a public repository inherits public visibility;
check with `docker pull ghcr.io/<owner>/typecast:latest` from a machine that is
not signed in to GitHub. If that fails, open your GitHub profile → **Packages** →
**typecast** → **Package settings** → **Change visibility** → **Public**. The image
holds only this repository's GPL code; secrets are injected by Azure at runtime
and never baked in.

To keep it private instead, create a personal access token with `read:packages`
and set it as the `REGISTRY_PASSWORD` secret, with your GitHub username as the
`REGISTRY_USERNAME` variable.

### 2. Let GitHub Actions sign in to Azure

In [Azure Cloud Shell](https://shell.azure.com) (Bash), from a clone of this
repository:

```bash
./infra/bootstrap.sh typecast-rg eastus GrmpPnda/typecast
```

It creates the resource group and a managed identity that only workflows on
`main` of this repository can sign in as. The trust is federated, so no Azure
password or secret is stored in GitHub. The identity gets **Contributor on that
resource group only**. The script prints the values for the next step, including
freshly generated secrets, which are shown once.

If the workflow's Azure sign-in fails with `AADSTS700213: No matching federated
identity record`, compare the subject in the error with
`az identity federated-credential list --identity-name <rg>-github-deployer -g <rg> -o table`.
GitHub names the repository either as `owner/repo` or with its numeric IDs
(`owner@123/repo@456`); the script registers both, and re-running it fixes a
missing one.

### 3. Add variables and secrets to GitHub

Repository → **Settings** → **Secrets and variables** → **Actions**. Add them as **repository**
values, not under an environment. Each can go on either the **Variables** or the **Secrets** tab; the
workflows read both, and check that everything is present before touching Azure.

| Variable | Value |
| --- | --- |
| `AZURE_CLIENT_ID` | from the script |
| `AZURE_TENANT_ID` | from the script |
| `AZURE_SUBSCRIPTION_ID` | from the script |
| `AZURE_RESOURCE_GROUP` | the resource group, e.g. `typecast-rg` |
| `TYPECAST_ADMIN_EMAIL` | the email you sign in with |

| Secret | Value |
| --- | --- |
| `TYPECAST_SECRET_KEY` | from the script. **Never change it later**: stored API keys are encrypted with a key derived from it |
| `POSTGRES_ADMIN_PASSWORD` | from the script |
| `TYPECAST_ADMIN_PASSWORD` | only if the administrator signs in with a password: their first password. Leave it unset to have them claim the account by signing in with Microsoft or Google. Without it, whoever reaches the new site first can claim the administrator account through the setup page |

### 4. Create the infrastructure

**Actions** → **Infrastructure** → **Run workflow**. The first run takes ten to
fifteen minutes, most of it PostgreSQL. The run summary shows the app's URL and
the redirect URIs for Microsoft and Google sign-in. From now on, every push to `main` deploys.

If it fails with `ParameterOutOfRange: The value of the 'Version' should be in: []`,
your subscription cannot create PostgreSQL servers in that region. Confirm with
`az postgres flexible-server list-skus --location <region> -o table`, find a region
where it can (`eastus2` is a common choice), set it as the `POSTGRES_LOCATION`
variable, and run the workflow again. Only the database moves; a neighbouring
region adds a few milliseconds per query.

### 5. Move your works in

On your local install, **Settings → Backup & Restore → Download Backup**. On the
new site, sign in as the administrator and choose **Import into my account**.
Then re-enter your AI provider keys and reconnect Google Drive, neither of which
can move between servers.

## Your own hostname (optional)

Azure issues and renews a free certificate for it. The default
`*.azurecontainerapps.io` address keeps working alongside.

1. Find the two values the DNS records need:

   ```bash
   az containerapp show -n typecast -g typecast-rg \
     --query "{cname: properties.configuration.ingress.fqdn, txt: properties.customDomainVerificationId}" -o table
   ```

2. At your DNS provider, for `typecast.example.com`:

   | Type | Name | Value |
   | --- | --- | --- |
   | CNAME | `typecast` | the `cname` value |
   | TXT | `asuid.typecast` | the `txt` value |

   On Cloudflare, set the CNAME to **DNS only**: a proxied record hides the
   CNAME, and the certificate cannot be validated. If the domain has CAA records,
   one must allow `digicert.com`. Check with `dig +short CNAME typecast.example.com`
   and `dig +short TXT asuid.typecast.example.com`.
3. Set the repository variable `CUSTOM_HOSTNAME` to `typecast.example.com` and run
   **Infrastructure**. The first run deploys twice, because the certificate can
   only be requested once the hostname is attached; issuing it can take up to
   twenty minutes. Later runs bind the existing certificate in one pass.
4. With Microsoft sign-in, add the new address as a redirect URI, keeping the
   default one (for Google, add it to the OAuth client in the Google Cloud console):

   ```bash
   APP_ID=$(az ad app list --display-name Typecast --query "[0].appId" -o tsv)
   az ad app update --id "$APP_ID" --web-redirect-uris \
     "https://typecast.example.com/api/auth/oidc/microsoft/callback" \
     $(az ad app show --id "$APP_ID" --query "web.redirectUris[]" -o tsv)
   ```

## Sign in with Microsoft or Google (optional)

Typecast's sign-in page offers a password, plus a button for each provider you
configure. Each account signs in exactly one way:

- An account created by signing in with a provider always uses that provider.
- A password account switches to a provider the first time its owner signs in
  with it using the same email, and its password stops working. Signing in with
  the password afterwards says which provider to use.
- An administrator's **Set password** in **Settings → Users** switches an
  account back to a password. That is the way back in for someone who loses
  their Microsoft or Google account.

Only people with an account can sign in: add them in **Settings → Users** by the
email they sign in with, choosing how they sign in. `TYPECAST_ADMIN_EMAIL` is
created ready to be claimed by the administrator's first sign-in. An email is
only used to find an account when the provider vouches for it: Google's must be
verified, and Microsoft's must come from your own directory or be a personal
Microsoft account.

Do this after step 4, because each provider needs the app's address. The
Infrastructure run summary lists the exact redirect URIs. With your own
hostname, register both it and the default address, or sign-in works on only
one of them.

### Microsoft

In Cloud Shell, create the app registration, require assignment, and assign
yourself. Without assignment required, everyone in your directory can sign in.

```bash
HOST=typecast.example.com   # or the default *.azurecontainerapps.io address
APP_ID=$(az ad app create --display-name Typecast --sign-in-audience AzureADMyOrg \
  --web-redirect-uris "https://$HOST/api/auth/oidc/microsoft/callback" --query appId -o tsv)
SP_ID=$(az ad sp create --id "$APP_ID" --query id -o tsv)
# The tag makes it appear under Enterprise applications; the CLI omits it.
az ad sp update --id "$SP_ID" --set appRoleAssignmentRequired=true \
  --add tags WindowsAzureActiveDirectoryIntegratedApp
az rest --method POST \
  --uri "https://graph.microsoft.com/v1.0/servicePrincipals/$SP_ID/appRoleAssignedTo" \
  --body "{\"principalId\":\"$(az ad signed-in-user show --query id -o tsv)\",\"resourceId\":\"$SP_ID\",\"appRoleId\":\"00000000-0000-0000-0000-000000000000\"}"
echo "SSO_CLIENT_ID      $APP_ID"
echo "SSO_CLIENT_SECRET  $(az ad app credential reset --id "$APP_ID" --display-name github --years 1 --query password -o tsv)"
```

Add the variable `SSO_CLIENT_ID` and the secret `SSO_CLIENT_SECRET` in GitHub.
Assign other people under **Enterprise applications** → Typecast → **Users and
groups**. The secret expires in a year: re-run the last line, update the GitHub
secret, and run **Infrastructure**.

**Already set up for the earlier Easy Auth sign-in?** Keep the registration and
its secret, and add the new redirect URI next to the old one:

```bash
APP_ID=$(az ad app list --display-name Typecast --query "[0].appId" -o tsv)
az ad app update --id "$APP_ID" --web-redirect-uris \
  "https://typecast.example.com/api/auth/oidc/microsoft/callback" \
  $(az ad app show --id "$APP_ID" --query "web.redirectUris[]" -o tsv)
```

The next Infrastructure run switches Easy Auth off and Typecast's own sign-in
on. Accounts that signed in through Easy Auth carry over.

### Google

1. In the [Google Cloud console](https://console.cloud.google.com), create or pick
   a project. Under **APIs & Services → OAuth consent screen**, choose
   **External**, fill in the app name and your email, and add only the scopes
   `openid`, `email`, and `profile`. These are not sensitive scopes, so Google
   does not need to review the app. While it stays in **Testing**, only the
   Google accounts listed under **Test users** can sign in, which is a useful
   second gate for a personal install.
2. Under **Credentials → Create credentials → OAuth client ID**, choose **Web
   application** and add the authorised redirect URI
   `https://typecast.example.com/api/auth/oidc/google/callback`.
3. Add the variable `GOOGLE_CLIENT_ID` and the secret `GOOGLE_CLIENT_SECRET` in
   GitHub, and run **Infrastructure**.

If a sign-in fails, the sign-in page shows why. `AADSTS50105` means the person
is not assigned to the app in Entra ID; `redirect_uri_mismatch` (Google) or
`AADSTS50011` (Microsoft) means the address you used is not registered.

## Operating it

```bash
# Recent logs
az containerapp logs show -n typecast -g typecast-rg --tail 100

# What is running
az containerapp revision list -n typecast -g typecast-rg -o table
curl https://<app>/api/health        # {"status":"ok","version":"<commit>"}
```

- **Database backups**: Flexible Server keeps 7 days of point-in-time restore.
  Typecast's own **Download Backup** also works against PostgreSQL and includes the
  uploads.
- **Rolling back**: re-run **Deploy** from an older commit, or point the app at an
  earlier image: `az containerapp update -n typecast -g typecast-rg --image ghcr.io/<owner>/typecast:<sha>`.
  Migrations only move forward, so a rollback across a schema change needs a
  database restore.
- **The token store's access expires after a year.** Re-run **Infrastructure**
  before then to issue a new one.

## Security notes

- The PostgreSQL server accepts connections from Azure-hosted clients, because
  Container Apps on the consumption plan has no fixed outbound address. It
  requires TLS, and the app verifies the server's certificate
  (`postgresSslMode=verify-full`). Moving both into a virtual network would
  remove the public endpoint.
- One replica at most. Migrations run at startup and would race between
  replicas, and Google Drive's sign-in flow keeps its state in memory.
- Uploaded images are served only to the account that owns them, and fonts to any
  signed-in account. Browsers load them with an HttpOnly cookie scoped to
  `/uploads`, which the API does not accept, so it cannot be used to act as you.
