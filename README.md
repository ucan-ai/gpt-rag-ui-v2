# Enterprise RAG Web UI

Part of the [GPT-RAG](https://github.com/Azure/gpt-rag) solution.

This project provides a user interface built with [Chainlit](https://www.chainlit.io/) to interact with GPT-powered retrieval-augmented generation systems. It is designed to work seamlessly with the Orchestrator backend and supports customization and theming.

---

## 🚀 Quickstart – Run Locally

### **Pre-requisites**

- Python 3.11+
- [Azure CLI](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli)

### **1. Setup Environment and Install Dependencies**

```bash
python -m venv .venv
source .venv/bin/activate       # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 🔧 **2. Environment Variable Configuration**

Before running the application, make sure to configure all required environment variables. These can be defined in a `.env` file or set manually in your environment or App Service configuration panel.

#### ✅ **Required Variables**

| Variable | Description |
|---------|-------------|
| `ORCHESTRATOR_STREAM_ENDPOINT` | URL of the orchestrator streaming endpoint (e.g., `https://<your-func>.azurewebsites.net/api/orcstream`) |
| `AZURE_SUBSCRIPTION_ID` | Azure subscription ID used for function key retrieval |
| `AZURE_RESOURCE_GROUP_NAME` | Resource group where the orchestrator function app is deployed |
| `AZURE_ORCHESTRATOR_FUNC_NAME` | Name of the orchestrator Function App |
| `BLOB_STORAGE_ACCOUNT_NAME` | Azure Storage account name where documents are stored |
| `BLOB_STORAGE_CONTAINER` | Container name within the blob storage account |

#### 🔐 **Session Configuration (Chainlit UI)**

| Variable | Description |
|---------|-------------|
| `CHAINLIT_SECRET_KEY` | Secret key for securing sessions in Chainlit (define any strong random value) |

#### 🔑 **(Optional) Authentication Settings**

If you want to enable Entra ID-based authentication (optional), configure the variables below and set `ENABLE_AUTHENTICATION=true`:

| Variable | Description |
|---------|-------------|
| `CLIENT_ID` | Application (client) ID registered in Entra ID |
| `AUTHORITY` | Entra ID authority URL (e.g., `https://login.microsoftonline.com/<tenant-id>`) |
| `APP_SERVICE_CLIENT_SECRET` | Client secret used in Azure App Service authentication |
| `REDIRECT_PATH` | Redirect path used in OAuth flow (e.g., `/getAToken`) |
| `ENABLE_AUTHENTICATION` | Set to `true` to enable authentication (default is `false`) |

> 💡 You can create a `.env` file with all these variables and Chainlit will automatically load them when starting the app locally.  
> Start by copying the `.env.template` file:
```bash
cp .env.template .env
```

#### Example `.env` file (values for illustration only):
```ini
# Required settings
ORCHESTRATOR_STREAM_ENDPOINT=https://your-func.azurewebsites.net/api/orcstream
AZURE_SUBSCRIPTION_ID=your-subscription-id
AZURE_RESOURCE_GROUP_NAME=your-resource-group
AZURE_ORCHESTRATOR_FUNC_NAME=your-function-app-name
BLOB_STORAGE_ACCOUNT_NAME=your-storage-account
BLOB_STORAGE_CONTAINER=your-container

# Chainlit session key
CHAINLIT_SECRET_KEY=your-secret-key

# Optional authentication
CLIENT_ID=your-client-id
AUTHORITY=https://login.microsoftonline.com/your-tenant-id
APP_SERVICE_CLIENT_SECRET=your-client-secret
REDIRECT_PATH=/getAToken
ENABLE_AUTHENTICATION=false
```

### **3. Run the Application Locally**

```bash
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

---

## ☁️ Deploy to Azure

You can deploy the UI to Azure App Service using either:

### **Option 1: Deploy via Azure App Service Extension (VS Code or Portal)**

Use the App Service extension to deploy the code folder.

> ⚠️ **Important:** After deployment, set the **Startup Command** as:
```
python -m uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
```

### **Option 2: Deploy via Azure CLI**

#### 2.3. Zip the source code

- **Linux/Mac:**
```bash
rm -f deploy.zip && zip -r ./deploy.zip *
```

- **Windows:**
```powershell
Remove-Item -Force deploy.zip; tar -a -c -f ./deploy.zip *
```

#### 2.4. Deploy to Web App

```bash
az webapp deploy \
  --subscription <SUBSCRIPTION_ID> \
  --resource-group <RESOURCE_GROUP_NAME> \
  --name <WEB_APP_NAME> \
  --src-path deploy.zip \
  --type zip \
  --async true
```

---

## 🔐 Required Permissions

Ensure that the user running the UI locally or accessing it via deployment has the following Azure role assignments:

### **Orchestrator Function App**

```bash
az role assignment create \
  --assignee <principalId> \
  --role "Contributor" \
  --scope "/subscriptions/<subscriptionId>/resourceGroups/<resourceGroupName>/providers/Microsoft.Web/sites/<functionAppName>"
```

### **Storage Account**

```bash
az role assignment create \
  --assignee <principalId> \
  --role "Storage Blob Data Reader" \
  --scope "/subscriptions/<subscriptionId>/resourceGroups/<resourceGroupName>/providers/Microsoft.Storage/storageAccounts/<storageAccountName>"
```

### **Key Vault**

```bash
az role assignment create \
  --assignee <principalId> \
  --role "Key Vault Secrets User" \
  --scope "/subscriptions/<subscriptionId>/resourceGroups/<resourceGroupName>/providers/Microsoft.KeyVault/vaults/<keyVaultName>"
```

---

## 🎨 Customization

### **1. Styling and Theme**

- Customize colors and fonts in `public/theme.json`
- Customize CSS styles in `public/custom.css`
- Replace logos and icons directly in the `public/` folder

### **2. Additional Chainlit Configurations**

Edit `.chainlit/config.toml` to configure:
- Session timeout
- Allowed origins
- UI behavior (e.g., themes, assistant name, custom links)

Refer to the official [Chainlit documentation](https://docs.chainlit.io/) for more customization options.

---

## 🤝 Contributing

We welcome contributions! Please see [CONTRIBUTING.md](https://github.com/Azure/GPT-RAG/blob/main/CONTRIBUTING.md) for guidelines.

---

## 📄 Trademarks

This project may include Microsoft trademarks or logos. Use must comply with [Microsoft's Trademark & Brand Guidelines](https://www.microsoft.com/en-us/legal/intellectualproperty/trademarks/usage/general). Third-party trademarks are subject to their respective policies.
```