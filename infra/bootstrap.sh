#!/usr/bin/env bash
# One-time setup so GitHub Actions can deploy Typecast to Azure.
#
# Run in Azure Cloud Shell (Bash) or anywhere `az login` has been done, as
# someone who can create resource groups and role assignments:
#
#   ./infra/bootstrap.sh <resource-group> <region> <github-owner/repo>
#   ./infra/bootstrap.sh typecast-rg eastus GrmpPnda/typecast
#
# Creates the resource group, a managed identity GitHub Actions signs in as
# (federated: no password or secret is stored anywhere), and gives that
# identity Contributor on this one resource group only. Prints the values to
# add to the GitHub repository, and saves them, so a dropped session loses
# nothing. Safe to re-run: existing resources are kept, and so are the
# generated secrets.
set -euo pipefail

if [ $# -ne 3 ]; then
  sed -n '4,9p' "$0" | sed 's/^# \{0,1\}//'
  exit 1
fi
RG="$1"; LOCATION="$2"; REPO="$3"
IDENTITY="${RG}-github-deployer"
PROVIDERS="Microsoft.App Microsoft.OperationalInsights Microsoft.DBforPostgreSQL Microsoft.Storage Microsoft.ManagedIdentity"

# Everything printed is also written here. Cloud Shell keeps $HOME across
# sessions, so a timed-out console can be recovered with `cat` on this file.
# It holds secrets: readable by you only, and delete it once they are in GitHub.
umask 077
OUT="$HOME/typecast-bootstrap-${RG}.txt"
SECRETS="$HOME/.typecast-bootstrap-${RG}.secrets"
exec > >(tee -a "$OUT") 2>&1
echo "=== $(date -u '+%Y-%m-%d %H:%M:%S UTC'): bootstrap $RG ($LOCATION) for $REPO ==="

echo "Registering resource providers (continues in the background)..."
for ns in $PROVIDERS; do
  # No --wait: registration can take several minutes per provider on a new
  # subscription, long enough for Cloud Shell to drop an idle session. It only
  # has to finish before the Infrastructure workflow runs; checked at the end.
  az provider register --namespace "$ns" --output none
done

echo "Resource group $RG in $LOCATION..."
az group create --name "$RG" --location "$LOCATION" --output none
RG_ID=$(az group show --name "$RG" --query id --output tsv)

echo "Managed identity $IDENTITY..."
if ! az identity show --name "$IDENTITY" --resource-group "$RG" --output none 2>/dev/null; then
  az identity create --name "$IDENTITY" --resource-group "$RG" --location "$LOCATION" --output none
fi
CLIENT_ID=$(az identity show --name "$IDENTITY" --resource-group "$RG" --query clientId --output tsv)
PRINCIPAL_ID=$(az identity show --name "$IDENTITY" --resource-group "$RG" --query principalId --output tsv)

# Workflows on main may sign in as this identity; nothing else may. Both the
# deploy and infrastructure workflows run from main.
echo "Federated credential for $REPO on main..."
if ! az identity federated-credential show --name github-main --identity-name "$IDENTITY" \
     --resource-group "$RG" --output none 2>/dev/null; then
  az identity federated-credential create \
    --name github-main --identity-name "$IDENTITY" --resource-group "$RG" \
    --issuer https://token.actions.githubusercontent.com \
    --subject "repo:${REPO}:ref:refs/heads/main" \
    --audiences api://AzureADTokenExchange --output none
fi

has_contributor() {
  [ -n "$(az role assignment list --assignee "$PRINCIPAL_ID" --role Contributor \
           --scope "$RG_ID" --query '[0].id' --output tsv 2>/dev/null)" ]
}

echo "Contributor on $RG only..."
# A new identity takes a minute or two to reach Entra ID, and assigning a role
# before then fails with PrincipalNotFound. The first version of this script
# hid that failure behind "(already assigned)", which left an identity that
# could sign in but do nothing.
if has_contributor; then
  echo "  already assigned"
else
  for attempt in 1 2 3 4 5 6 7 8 9 10; do
    if az role assignment create --assignee-object-id "$PRINCIPAL_ID" \
         --assignee-principal-type ServicePrincipal --role Contributor \
         --scope "$RG_ID" --output none 2>/tmp/typecast-role.err; then
      break
    fi
    echo "  not ready yet (attempt $attempt): $(head -1 /tmp/typecast-role.err)"
    sleep 15
  done
  rm -f /tmp/typecast-role.err
  if ! has_contributor; then
    echo "ERROR: could not give $IDENTITY Contributor on $RG. Re-run this script in a few minutes."
    exit 1
  fi
  echo "  assigned"
fi

# Generated once and reused on every re-run, so values already pasted into
# GitHub stay valid.
if [ ! -s "$SECRETS" ]; then
  {
    echo "TYPECAST_SECRET_KEY=$(openssl rand -base64 48 | tr -d '\n')"
    echo "POSTGRES_ADMIN_PASSWORD=$(openssl rand -base64 48 | tr -d '\n/+=' | cut -c1-32)"
  } > "$SECRETS"
fi
SECRET_KEY=$(sed -n 's/^TYPECAST_SECRET_KEY=//p' "$SECRETS")
PG_PASSWORD=$(sed -n 's/^POSTGRES_ADMIN_PASSWORD=//p' "$SECRETS")

PENDING=""
for ns in $PROVIDERS; do
  state=$(az provider show --namespace "$ns" --query registrationState --output tsv)
  [ "$state" = "Registered" ] || PENDING="$PENDING $ns($state)"
done

cat <<EOF

Done. In GitHub: ${REPO} -> Settings -> Secrets and variables -> Actions.

Variables (not secret):
  AZURE_CLIENT_ID        $CLIENT_ID
  AZURE_TENANT_ID        $(az account show --query tenantId --output tsv)
  AZURE_SUBSCRIPTION_ID  $(az account show --query id --output tsv)
  AZURE_RESOURCE_GROUP   $RG
  TYPECAST_ADMIN_EMAIL   <the email you will sign in with>

Secrets:
  TYPECAST_SECRET_KEY      $SECRET_KEY
  POSTGRES_ADMIN_PASSWORD  $PG_PASSWORD
  TYPECAST_ADMIN_PASSWORD  <only without single sign-on: your first password>

Saved to $OUT (yours only). Delete it, and $SECRETS,
once the secrets are in GitHub.
EOF

if [ -n "$PENDING" ]; then
  echo
  echo "Still registering:$PENDING"
  echo "Wait until 'az provider show -n <namespace> --query registrationState' says Registered"
  echo "for each, then run the Infrastructure workflow. Usually a few minutes."
else
  echo
  echo "All resource providers are registered. Next: run the \"Infrastructure\" workflow."
fi
