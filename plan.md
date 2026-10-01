Complete Codgen Rebrand + Muapi Server-Side Migration Map
What changes and where
Two separate concerns:

Rebrand — "Open Higgsfield AI" → "Codgen", remove all Muapi-visible references from UI

Architecture shift — Muapi key moves from client localStorage to server-side (CodeGen backend holds it)

Every file that needs touching
Branding / UI text (Next.js app):

File	Change
app/layout.js	Title + description → Codgen
app/studio/page.js	Title → Codgen
components/ApiKeyModal.js	Remove entirely — users won't enter a Muapi key anymore
components/StandaloneShell.js	App name, STORAGE_KEY, settings modal text — replace with Codgen auth (JWT/session)
Branding / UI text (Vite/Electron app — src/):

File	Change
src/components/AuthModal.js	Remove Muapi key input — replace with Codgen login
src/components/SettingsModal.js	Remove muapi_key localStorage — replace with Codgen account settings
src/components/Header.js	Logo/brand text if any
src/lib/pendingJobs.js	PENDING_KEY rename from muapi_pending_jobs → codgen_pending_jobs
API layer (the core architectural change):

File	Change
packages/studio/src/muapi.js	Replace BASE_URL + auth header — point to your CodeGen backend instead of api.muapi.ai directly. Remove x-api-key from client. Use Authorization: Bearer {jwt} instead
src/lib/muapi.js	Same — replace base URL + auth
Package metadata:

File	Change
package.json	name, description, productName, appId → codgen
The key architectural change in muapi.js
Currently (client calls Muapi directly):

Browser → api.muapi.ai (with user's Muapi key in header)

Copy

Insert at cursor
After (client calls Codgen backend):

Browser → your-codgen-backend.com/api/v1/... (with user's JWT)
         → CodeGen backend → api.muapi.ai (with YOUR Muapi key, server-side only)

Copy

Insert at cursor
The function signatures in muapi.js stay identical — generateImage(params), generateVideo(params) etc. Only the BASE_URL and auth header change. The studio components don't change at all.

What the backend needs to do (Phase 1 minimal)
A thin proxy — FastAPI or Next.js API routes — that:

Validates the user's JWT

Forwards the request to api.muapi.ai with the server-side Muapi key

Returns the response

That's it for Phase 1. Auth, quotas, S3, projects layer on top of this working core.

