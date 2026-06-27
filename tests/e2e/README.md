# Sales Cockpit Playwright E2E

Suite Playwright exécutable pour automatiser progressivement `docs/PLAYWRIGHT_E2E_PROTOCOL.md`.

Par défaut, la suite cible staging en lecture seule :

```powershell
$env:NODE_PATH = (Resolve-Path ".Codex\playwright-runner\node_modules").Path
cd .Codex\playwright-runner
npx playwright test --config ..\..\tests\e2e\playwright.config.cjs
```

Pour lancer les tests authentifiés, fournir les credentials staging :

```powershell
$env:SC_E2E_ADMIN_EMAIL = "francois.dupuis@essr.ch"
$env:SC_E2E_SETTER1_EMAIL = "service.etudiants@essr.ch"
$env:SC_E2E_SETTER2_EMAIL = "setter2@essr.ch"
$env:SC_E2E_CLOSER_EMAIL = "yasmine@essr.ch"
$env:SC_E2E_SHARED_PASSWORD = "<mot de passe affiché sur la page de login>"
```

Si un compte a un mot de passe différent, définir aussi `SC_E2E_ADMIN_PASSWORD`, `SC_E2E_SETTER1_PASSWORD`, `SC_E2E_SETTER2_PASSWORD` ou `SC_E2E_CLOSER_PASSWORD`.

Les tests mutateurs restent désactivés sauf :

```powershell
$env:SC_E2E_ALLOW_MUTATION = "true"
```

Les tests ne cliquent pas sur un envoi WhatsApp réel sauf flag dédié dans les futures specs :

```powershell
$env:SC_E2E_ALLOW_WHATSAPP_SEND = "true"
```
