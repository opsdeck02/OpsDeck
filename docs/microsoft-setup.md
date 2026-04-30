# Microsoft Graph Setup

Use this guide to connect OpsDeck to Microsoft 365, OneDrive, and SharePoint through Microsoft Graph OAuth.

1. Go to `portal.azure.com` and open Azure Active Directory / Microsoft Entra ID.
2. Open **App registrations** and choose **New registration**.
3. Set the name to `OpsDeck`.
4. Set supported account types to accounts in any organizational directory and personal Microsoft accounts.
5. Add redirect URIs:
   - Production: `https://opsdeck.in/api/microsoft/callback`
   - Local: `http://localhost:8000/api/v1/microsoft/callback`
6. Open **API permissions** and add delegated permissions:
   - `Files.Read`
   - `Files.Read.All`
   - `offline_access`
   - `User.Read`
7. Open **Certificates & secrets**, create a new client secret, and copy the value immediately.
8. Open **Overview** and copy the Application client ID and Directory tenant ID.
9. Add these values to the backend environment:

```bash
MICROSOFT_CLIENT_ID=...
MICROSOFT_CLIENT_SECRET=...
MICROSOFT_REDIRECT_URI=http://localhost:8000/api/v1/microsoft/callback
ENCRYPTION_KEY=...
```

Generate `ENCRYPTION_KEY` with:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

The redirect URI in `.env` must exactly match one of the Azure app registration redirect URIs. Tokens are encrypted at rest and are never returned by the OpsDeck API.
