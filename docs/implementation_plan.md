# Implementation Plan — HomeConnect Africa API Infrastructure Layer

This document outlines the design and step-by-step plan for building the complete, robust API infrastructure layer for the HomeConnect Africa SvelteKit 2.x frontend. This layer will sit between the UI components and the 11 FastAPI backend microservices.

---

## User Review Required

> [!IMPORTANT]
> **Svelte 5 Runes in Svelte 4 Environment**:
> The `package.json` in `frontend/` currently lists `"svelte": "^4.2.8"`. However, the API prompt document mandates Svelte 5 runes (`$state`, `$derived`, `$bindable`) and files ending in `.svelte.ts` for reactive composables.
> **We need to install/upgrade `svelte` to version 5 in the frontend package.**
> We propose running the following command after your approval:
> `npm install svelte@next --save-dev` or `npm install svelte@5 --save-dev` to enable Svelte 5 support.

> [!WARNING]
> **MSW and Vitest Installation**:
> The prompt specifies MSW 2.x for API mocking and Vitest for testing. Neither package is currently present in `package.json`.
> We will need to install `msw` and `vitest` to run tests and enable dev mocking:
> `npm install msw@latest vitest@latest @vitest/coverage-v8 --save-dev`

---

## Open Questions

> [!IMPORTANT]
> 1. **Do we proceed with Svelte 5 Upgrade?** Can we run the upgrade to Svelte 5 (`npm install svelte@5`) in the `frontend` directory?
> 2. **MSW Service Worker registration**: MSW 2.x requires a service worker file (`mockServiceWorker.js`) in the public folder. Can we run `npx msw init static --save` in the frontend directory to initialize this?
> 3. **Environment files**: The prompt asks us to configure `.env.local` with gateway URLs. Are there actual gateway servers we should connect to in staging/production, or will we proceed with MSW dev mocks for all services?

---

## Proposed Changes

We will build the entire API infrastructure layer inside `frontend/src/lib/` according to the 10 detailed prompt specifications. We will replace any legacy files in `src/lib/api` to cleanly implement the standardized architecture.

### 0. Core Definitions (Shared Types & Design Tokens)

These provide a single source of truth for the entire frontend application, eliminating inconsistencies across various documents.

#### [NEW] [shared.ts](file:///c:/Users/YOGA/Desktop/yc-afe/afe/frontend/src/lib/types/shared.ts)
- Implement canonical types: `FilterOperator`, `FilterDef`, `BBoxValue`, `RadiusValue`, `FilterSchemaType`, `FilterSchema`, `SortState`, `PaginationStrategy`, `CursorPage`, `OffsetPage`, `PageState`, `SelectionState`, `UserRole`, `AuthUser`, `ListingStatus`, `ListingType`, `ListingData`, `EscrowState`, and `ApiResponse<T>`.

#### [NEW] [design-tokens.ts](file:///c:/Users/YOGA/Desktop/yc-afe/afe/frontend/src/lib/tokens/design-tokens.ts)
- Implement standard typography, breakpoints, spacing (`SPACING`), border radius (`RADIUS`), shadow styles (`SHADOW`), z-indices (`Z_INDEX`), colors (`COLOR`), animations (`ANIMATION`), and country currency symbols (`CURRENCY_SYMBOL`).

---

### 1. Base HTTP & Auth Client

This forms the fundamental layer for all fetch calls, centralizing error parsing, auth headers, silent refresh, and retries.

#### [NEW] [constants.ts](file:///c:/Users/YOGA/Desktop/yc-afe/afe/frontend/src/lib/api/constants.ts)
- Add global API constants: `TIMEOUT_DEFAULT`, `TIMEOUT_MUTATION`, `TIMEOUT_AI`, `TIMEOUT_GPS`, `TIMEOUT_LENDER`, `TIMEOUT_UPLOAD`, `RETRY_DELAYS`, and `WS_RECONNECT_DELAYS`.

#### [MODIFY] [client.ts](file:///c:/Users/YOGA/Desktop/yc-afe/afe/frontend/src/lib/api/client.ts)
- Rebuild base fetch client `apiRequest<T>()` utilizing Native `fetch` (no Axios).
- Implement timeout using `AbortController` + `setTimeout` (throwing `TimeoutError`).
- Inject auth bearer tokens from Svelte 5 auth store, `X-Country-ID` (from user claim), `X-Correlation-ID` (for tracing), and optional `Idempotency-Key` (required for payment mutations).
- Handle 401: trigger silent token refresh using `POST /auth/refresh`, update store, and retry original request. Clear token and redirect to `/login` if refresh also fails.
- Implement exponential retry on GET requests for 503 or network errors.
- Throw detailed `ApiError` extending `Error` (with status, custom code, correlationId, and endpoint).
- Unwrap FastAPI response envelope `{ data: T, meta?, error? }`.

#### [NEW] [authStore.svelte.ts](file:///c:/Users/YOGA/Desktop/yc-afe/afe/frontend/src/lib/stores/authStore.svelte.ts)
- Svelte 5 module-level `$state` store.
- Shape: `user`, `accessToken`, `isLoading`, `mfaRequired`, `mfaPurpose`.
- Computed properties via `$derived`: `isAuthenticated`, `isAdmin`, `countryId`, `currencyCode`, `locale`.
- Actions: `setTokens()`, `clearTokens()`, `requireMfa()`, `clearMfa()`.
- Decode JWT on token set to establish silent refresh timer.

---

### 2. Localization, Websockets, Pagination & Caching

These files handle UI support features: caching data dynamically, receiving server-sent real-time Kafka events over WebSockets, serializing filters/sorting to backend criteria, and localizing all dates and numbers.

#### [NEW] [locale.ts](file:///c:/Users/YOGA/Desktop/yc-afe/afe/frontend/src/lib/api/locale.ts)
- Create localized helper functions (`formatCurrency`, `formatDate`, `formatNumber`, `getWeekStart`, `getCurrencySymbol`, `getLocale`, `getTimezone`).
- Export a `$derived` locale helper based on `authStore.countryId` for easy inline Svelte interpolation: `{locale.formatCurrency(item.price)}`.

#### [NEW] [websocket.ts](file:///c:/Users/YOGA/Desktop/yc-afe/afe/frontend/src/lib/api/websocket.ts)
- Create singleton `WebSocketManager` mapping 14 typed event channels.
- Connect, auto-reconnect (exponential backoff up to 5 times), heartbeat checks (25s ping/5s pong), and automatic re-authentication + re-subscription upon reconnection.
- Export `wsStatus` as a readable store.

#### [NEW] [pagination.ts](file:///c:/Users/YOGA/Desktop/yc-afe/afe/frontend/src/lib/api/pagination.ts)
- Helper functions: `cursorParams()`, `offsetParams()`, `parsePageMeta()`, `hasNextPage()`.
- Create Svelte 5 reactive pagination state factory `createPagination()`.

#### [NEW] [filters.ts](file:///c:/Users/YOGA/Desktop/yc-afe/afe/frontend/src/lib/api/filters.ts)
- Create serialisers for `FilterDef[]` (`filtersToParams`), `SortState` (`sortToParams`), and merging them (`buildParams`). Include reverse parser `paramsToFilters` to restore filter forms from URLs.

#### [NEW] [cache.ts](file:///c:/Users/YOGA/Desktop/yc-afe/afe/frontend/src/lib/api/cache.ts)
- In-memory `ResponseCache` with a TTL map mapped by endpoint patterns (properties search, market intelligence, neighborhood intelligence, agent performance, similar properties, etc.).
- Support Glob-pattern invalidation (`invalidate('/properties/*')`) for mutations.
- Integrate Stale-While-Revalidate (SWR) logic in `client.ts`.

---

### 3. Service Clients (12 Modules)

A modular client directory providing clean, strongly-typed asynchronous interfaces for every service without exposing auth or custom fetch logic.

#### [MODIFY] [auth.ts](file:///c:/Users/YOGA/Desktop/yc-afe/afe/frontend/src/lib/api/services/auth.ts)
- Implement endpoints for credentials register/login, verification of MFA TOTP tokens, silent token refresh, logout, password change, account deletion, profile settings, and data exports.

#### [NEW] [properties.ts](file:///c:/Users/YOGA/Desktop/yc-afe/afe/frontend/src/lib/api/services/properties.ts)
- Endpoint integrations for search, listing detail, reviews, saved listings, transaction logs, and property-specific market intelligence.

#### [NEW] [gps.ts](file:///c:/Users/YOGA/Desktop/yc-afe/afe/frontend/src/lib/api/services/gps.ts)
- GPS check-in (8s timeout, no retries) and check-in token validation.

#### [NEW] [ai.ts](file:///c:/Users/YOGA/Desktop/yc-afe/afe/frontend/src/lib/api/services/ai.ts)
- AI matching engines, price predictions, neighborhood safety analyses, photo quality optimizers, description staging, and staging timelines. (All utilize 15s timeout).

#### [NEW] [payments.ts](file:///c:/Users/YOGA/Desktop/yc-afe/afe/frontend/src/lib/api/services/payments.ts)
- Escrow flow: payment initiation, confirmation webhooks, disputes, refunds, and payment transaction summaries/trends.

#### [NEW] [agents.ts](file:///c:/Users/YOGA/Desktop/yc-afe/afe/frontend/src/lib/api/services/agents.ts)
- Agent profiles, reviews, viewing booking slots, pipeline tracking, and performance dashboards.

#### [NEW] [kyc.ts](file:///c:/Users/YOGA/Desktop/yc-afe/afe/frontend/src/lib/api/services/kyc.ts)
- Landlord verification document uploads, verification progress state, and approvals.

#### [NEW] [notifications.ts](file:///c:/Users/YOGA/Desktop/yc-afe/afe/frontend/src/lib/api/services/notifications.ts)
- Listing notifications, toggling alerts, marking items read, and setting user alert frequencies.

#### [NEW] [compliance.ts](file:///c:/Users/YOGA/Desktop/yc-afe/afe/frontend/src/lib/api/services/compliance.ts)
- Legal agreement validation and regulatory rules per country.

#### [NEW] [finance.ts](file:///c:/Users/YOGA/Desktop/yc-afe/afe/frontend/src/lib/api/services/finance.ts)
- Mortgage and affordability calculators, matching lender mortgage products, and lender uploads.

#### [NEW] [intelligence.ts](file:///c:/Users/YOGA/Desktop/yc-afe/afe/frontend/src/lib/api/services/intelligence.ts)
- Market forecasts, neighborhood demographics, pricing indexes, and localized transport data.

#### [NEW] [messages.ts](file:///c:/Users/YOGA/Desktop/yc-afe/afe/frontend/src/lib/api/services/messages.ts)
- Direct thread messages, templates, media uploads, and AI message assistance.

---

### 4. Composables & Dev Mock Layer

High-level reactive API tools for developers to build clean pages rapidly, and a Mock Service Worker (MSW) harness to emulate real-world latency and data flows.

#### [NEW] [composables.svelte.ts](file:///c:/Users/YOGA/Desktop/yc-afe/afe/frontend/src/lib/api/composables.svelte.ts)
- Implement `useQuery<T>`: wraps reactive status, polling intervals, stale-time, skeleton triggers, and deduplication of parallel queries (50ms window).
- Implement `useMutation<TInput, TOutput>`: executes POST/PUT/DELETE, handles loading states, error boundaries, and triggers cache invalidation upon completion.
- Implement `usePaginatedQuery<T>`: merges query operations with cursor/offset factories.

#### [NEW] [handlers.ts](file:///c:/Users/YOGA/Desktop/yc-afe/afe/frontend/src/lib/api/mock/handlers.ts)
- Create MSW 2.x request handlers.
- Support forced error injection via `window.__MSW_FORCE_ERROR = { endpoint: '...', status: 503 }`.
- Simulate delay (100ms - 400ms) for real-world representation.
- Mock specialized operations: check-in GPS transitions, mortgage lender timeouts (1.5s), and async WebSocket triggers.

#### [NEW] [setup.ts](file:///c:/Users/YOGA/Desktop/yc-afe/afe/frontend/src/lib/api/mock/setup.ts)
- Establish the browser worker instantiation script.

#### [NEW] [fixtures/](file:///c:/Users/YOGA/Desktop/yc-afe/afe/frontend/src/lib/api/mock/fixtures/)
- Write high-quality mock data JSON files for all 10 core fields matching the frontend typing requirements.

---

## Verification Plan

### Automated Tests
1. **Vitest unit tests**:
   - Write tests for:
     - `src/lib/api/client.test.ts` (Happy path, timeout abort, 401 refresh mechanism, 503 GET retries, mutation retries skip, `ApiError` code extraction)
     - `src/lib/api/cache.test.ts` (TTL expirations, bypass POST, pattern matching `invalidate`, stable parameter cache keys)
     - `src/lib/api/locale.test.ts` (Currency outputs, Swahili/English EAT date/time offsets, week starts)
     - `src/lib/api/filters.test.ts` (Multiple filters, bbox spatial mapping, round-tripping parameters back to filters)
     - `src/lib/api/websocket.test.ts` (Heartbeat, subscription filters, auto-reconnect backoff)
     - `src/lib/api/composables.test.ts` (useQuery mounting, status transitions, useMutation caching hooks)
   - Run via `npm run test` or `vitest run` and review outcomes.

### Manual Verification
1. **Developer gateway inspection**:
   - Run SvelteKit in development (`npm run dev`) and assert MSW mock intercept operations.
   - Verify request correlation headers, country routing headers, and query performance in browser dev console logging.
2. **WebSocket connection tests**:
   - Perform local simulated Kafka WS payloads and verify live Reactivity update bindings in layout modules.
