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
| Sign-in | Typecast passwords, or Microsoft Entra ID single sign-on through Container Apps authentication |
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
| `TYPECAST_ADMIN_PASSWORD` | only without single sign-on: the first administrator's password. Without it, whoever reaches the new site first can claim the administrator account through the setup page |

### 4. Create the infrastructure

**Actions** → **Infrastructure** → **Run workflow**. The first run takes ten to
fifteen minutes, most of it PostgreSQL. The run summary shows the app's URL and
the single sign-on redirect URI. From now on, every push to `main` deploys.

### 5. Move your works in

On your local install, **Settings → Backup & Restore → Download Backup**. On the
new site, sign in as the administrator and choose **Import into my account**.
Then re-enter your AI provider keys and reconnect Google Drive, neither of which
can move between servers.

## Single sign-on with Microsoft Entra ID (optional)

Sign-in moves to Microsoft, and Typecast has no passwords at all. Do this after
step 4, because the app registration needs the app's address.

1. In the [Entra admin center](https://entra.microsoft.com): **App registrations** →
   **New registration**. Name it Typecast, choose **Accounts in this
   organizational directory only**, and set a **Web** redirect URI to the
   `SSO redirect URI` from the Infrastructure run summary
   (`https://<app>/.auth/login/aad/callback`).
2. On the new registration: **Authentication** → tick **ID tokens**. Then
   **Certificates & secrets** → **New client secret**, and copy its value.
3. In GitHub, add the variable `SSO_CLIENT_ID` (the registration's **Application
   (client) ID**) and the secret `SSO_CLIENT_SECRET`. Run **Infrastructure**
   again.
4. **Restrict who can sign in.** **Enterprise applications** → Typecast →
   **Properties** → **Assignment required** → **Yes**, then add people under
   **Users and groups**. Without this, everyone in your tenant can sign in.

`TYPECAST_ADMIN_EMAIL` becomes the administrator the first time that person signs
in. Add everyone else in **Settings → Users** by the email they sign in with.

The template turns on Container Apps authentication with its token store, which
is what forwards the signed ID token that Typecast verifies. If sign-in loops or
every page shows "Your sign-in needs renewing", the token is not arriving:
check **Authentication** on the container app, and the logs below.

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
- Uploaded images and fonts are reachable by anyone with their exact URL, which
  contains random IDs. Under single sign-on that stops too: nothing reaches the
  container without signing in, apart from `/api/health`.
