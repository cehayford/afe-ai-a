# Afe frontend

SvelteKit 2 + Svelte 5 web app for Afe. It is a separate app from the API: every page is rendered here, and this app's
server talks to the backend's `/api/v1` endpoints.

## How it talks to the API

- **Sign-in tokens stay on the server.** After sign-in, the access token (15 min) and refresh token (30 days) are kept
  in httpOnly cookies (`afe_at`, `afe_rt`). `src/lib/server/api.ts` adds the bearer token to every API call and
  refreshes it once per request when it's about to expire.
- **Pages load and act on the server.** `+page.server.ts` loads call the API; forms post to SvelteKit form actions
  (`use:enhance` for no-reload submits), which call the API and return errors for the form to show.
- **One narrow browser-side path.** The field app's offline photo queue can't be a form action, so it posts to
  `/api/v1/verify/...` on this site (`src/routes/api/v1/[...path]/+server.ts`), which forwards only field-visit
  endpoints with the verifier's token. Cross-site form posts are refused by SvelteKit's origin check.
- **Types** in `src/lib/api/types.ts` mirror `backend/app/api/schemas.py`; the API's `/api/openapi.json` is the
  source of truth.

## Pages

| Area | Routes |
|---|---|
| Everyone | `/` landing page (what Afe checks, protected rent, Check before you pay, landlords, the app); old `/?area=` links redirect to `/homes` |
| Renters | `/homes` search (and save it as an alert), `/areas/[slug]` (neighbourhood rent ranges and homes), `/rent-index` (Accra verified rent index), `/homes/[reference]` (save, message, book a viewing, landlord rating and reviews), `/check` (Check before you pay, report a scam) |
| Everyone signed in | `/account` (profile, devices, download my data, close my account), `/account/messages`, `/account/viewings`, `/account/saved`, `/account/alerts`, `/account/appeals`, `/account/home` (a tenant's own records), `/account/notifications`, `/tenancies` and `/tenancies/[reference]` (accept and pay, confirm move-in, raise a problem, review, agreement PDF) |
| Landlords and agents | `/landlord` dashboard, `/landlord/verify` (Ghana Card), `/landlord/homes/new` (map pin), `/landlord/homes/[id]` (documents, fee, listings), `/landlord/listings/[id]` (edit, feature), `/landlord/offer/[viewing]` (offer a tenancy), `/landlord/payouts`, `/landlord/rentals` (tenants, rent, plan) and `/rentals/[id]` (shared with the tenant: payments, receipts, repairs, agreements, renewals) |
| Reviewers | `/review` queue, `/review/people/[id]`, `/review/homes/[id]`, `/review/documents/[id]` (private documents, every read logged), `/review/money` (releases, disputes, reconciliation), `/review/rules` (two-person rule changes), `/review/reports` (scam reports), `/review/detection` (models: mode, evaluation against the rules, training), `/review/verifiers` (verifier quality), `/review/insights` (targets), `/review/workload`, `/review/visit-plan`, `/review/appeals`, `/review/label-checks`, a linked-accounts graph on person pages, `/review/staff` and `/review/areas` (admins: staff, and opening new areas); model notes and linked accounts on the person and home pages |
| Development only | `/pay/test/[reference]` and `/pay/test-tenancy/[reference]` stand in for the payment partners' checkouts |
| Field verifiers | `/field` worklist, `/field/assignments/[id]` (check in by location), `/field/visits/[id]` (camera, offline queue, checklist) |
| Sign-in | `/signin` (SMS code or staff password, then authenticator), `/signup` (must accept the privacy notice and terms) |
| Legal | `/privacy` (privacy notice), `/terms` (terms of use). Both are drafts until counsel reviews them |

## Develop

```bash
npm ci
cp .env.example .env     # AFE_API_URL defaults to http://127.0.0.1:8000
npm run dev              # http://localhost:5173 (start the API first)
npm run check            # svelte-check / TypeScript
npx vitest run           # unit tests
npm run build && node build   # production server on :3000
```

Production needs `ORIGIN` (the public https URL), `AFE_API_URL` and `BODY_SIZE_LIMIT=20M` (uploads pass through this
server). The field app's camera and location need https on real phones.

Maps use Leaflet with OpenStreetMap tiles, loaded only on pages that show a map: the add-home page, the Map view of
search results and area pages (circles around approximate positions, never exact addresses). Switch to a commercial
tile provider before public launch (OSM's tile usage policy).

A content security policy is set in `vite.config.ts` (scripts only from this site; images from any https source for
listing photos and map tiles; forms only to this site and the payment partner's checkout). Add a source there before
loading anything from a new domain.

## Languages

Core renter text lives in `src/lib/i18n.ts`. English is complete; a professional translator fills the Twi
catalogue (decision B17) and native speakers review every scam warning. The language switch stays hidden until
`TWI_READY` is set, and any missing Twi string falls back to English.
