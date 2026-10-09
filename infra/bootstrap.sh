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
# add to the GitHub repository. Safe to re-run.
set -euo pipefail

if [ $# -ne 3 ]; then
  sed -n '4,9p' "$0" | sed 's/^# \{0,1\}//'
  exit 1
fi
RG="$1"; LOCATION="$2"; REPO="$3"
IDENTITY="${RG}-github-deployer"

echo "Registering resource providers (first use in a subscription can take a few minutes)..."
for ns in Microsoft.App Microsoft.OperationalInsights Microsoft.DBforPostgreSQL Microsoft.Storage Microsoft.ManagedIdentity; do
  az provider register --namespace "$ns" --wait --output none
done

echo "Resource group $RG in $LOCATION..."
az group create --name "$RG" --location "$LOCATION" --output none
RG_ID=$(az group show --name "$RG" --query id --output tsv)

echo "Managed identity $IDENTITY..."
az identity create --name "$IDENTITY" --resource-group "$RG" --location "$LOCATION" --output none
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

echo "Contributor on $RG only..."
az role assignment create --assignee-object-id "$PRINCIPAL_ID" \
  --assignee-principal-type ServicePrincipal --role Contributor --scope "$RG_ID" \
  --output none 2>/dev/null || echo "  (already assigned)"

cat <<EOF

Done. In GitHub: ${REPO} -> Settings -> Secrets and variables -> Actions.

Variables (not secret):
  AZURE_CLIENT_ID        $CLIENT_ID
  AZURE_TENANT_ID        $(az account show --query tenantId --output tsv)
  AZURE_SUBSCRIPTION_ID  $(az account show --query id --output tsv)
  AZURE_RESOURCE_GROUP   $RG
  TYPECAST_ADMIN_EMAIL   <the email you will sign in with>

Secrets (generate fresh values; these were made just now and are shown once):
  TYPECAST_SECRET_KEY      $(openssl rand -base64 48 | tr -d '\n')
  POSTGRES_ADMIN_PASSWORD  $(openssl rand -base64 32 | tr -d '\n/+=' | cut -c1-32)
  TYPECAST_ADMIN_PASSWORD  <only without single sign-on: your first password>

Then run the "Infrastructure" workflow. See infra/README.md.
EOF
