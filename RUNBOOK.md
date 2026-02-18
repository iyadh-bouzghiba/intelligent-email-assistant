# Intelligent Email Assistant — Operational Runbook (DOC-RUNBOOK-01)

## Environment
`<HOST>` = Backend base URL (protocol + domain, no trailing slash)

Example (current production):
https://intelligent-email-assistant-3e1a.onrender.com

---

## Control Contract (Evidence-first)
- No secrets: never share tokens/keys, encrypted payloads, or raw email bodies.
- Evidence only: logs, SQL counts, and screenshots (safe fields only).

---

## Windows PowerShell Networking (Forever Rule)
### Use curl.exe (NOT curl)
PowerShell aliases `curl` to `Invoke-WebRequest`. Always use `curl.exe`.

#### Placeholder form (portable)
```powershell
curl.exe -i "https://<HOST>/healthz"
curl.exe -i "https://<HOST>/health"
curl.exe -i "https://<HOST>/api/accounts"
curl.exe -i -X POST "https://<HOST>/api/sync-now?account_id=default"