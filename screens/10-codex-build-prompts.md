# 10 · Build Sequence — Prompts to Send Codex

Ordered, copy-paste prompts to build OrderlyAI with a coding agent (Codex CLI / Codex cloud / Cursor).
Send them **one at a time, in order**, reviewing the diff and running the app after each.

---

## Before you start (5 min setup)

1. **Create a Git repo** (e.g. `orderlyai`) and open it with Codex.
2. **Copy these design docs into the repo** under `docs/` — Codex will read them as the source of truth:
   - `docs/08-database-schema.md`  ← the schema (most important)
   - `docs/09-onboarding-screen-prompts.md`
   - `docs/02-architecture.md`, `docs/03-ai-agent-and-orders.md`
3. **Accounts/tools:** a Supabase project (free), Node 20 + pnpm, Python 3.12 + `uv`, Supabase CLI.
   (On Windows, run the CLIs in PowerShell or WSL — either works.)

**Architecture Codex must follow (this is baked into the prompts below):**
- **Monorepo:** `/web` (Next.js) · `/api` (FastAPI) · `/supabase` (migrations) · `/docs`.
- **Auth:** Supabase Auth (email/password) on the frontend; **FastAPI verifies the Supabase JWT** and
  resolves the user's `business_id`(s) via the `membership` table.
- **DB from FastAPI:** SQLAlchemy 2.0 async + asyncpg over `DATABASE_URL`. The service connection
  **bypasses RLS**, so **every query MUST filter by `business_id`** from the authenticated user
  (defense-in-depth per `docs/08`).
- **Frontend talks only to FastAPI** (except Supabase Auth for login + Storage later). TanStack Query.
- **Validation:** pydantic v2 (api) and zod + react-hook-form (web). Tests: pytest.

> Tip: keep all field/column names identical to `docs/08-database-schema.md` to avoid mapping bugs.

---

## STEP 0 — Scaffold the monorepo

```
Read docs/02-architecture.md and docs/08-database-schema.md first.

Scaffold a monorepo for "OrderlyAI" with this structure:
- /web  — Next.js 15 (App Router, TypeScript), Tailwind, shadcn/ui, TanStack Query, react-hook-form, zod,
          Supabase JS client. Add a clean folder layout (app/, components/, lib/, hooks/).
- /api  — FastAPI (Python 3.12) managed with uv. SQLAlchemy 2.0 async + asyncpg, pydantic v2,
          pydantic-settings. Layout: app/main.py, app/core (config, db, auth), app/routers,
          app/schemas, app/models, app/services. Add pytest.
- /supabase — for CLI migrations (empty migrations dir for now).
- root — README.md, .gitignore, .env.example (SUPABASE_URL, SUPABASE_ANON_KEY,
         SUPABASE_SERVICE_ROLE_KEY, SUPABASE_JWT_SECRET, DATABASE_URL, NEXT_PUBLIC_API_URL),
         and a docker-compose.yml with local Postgres + Redis for optional local dev.

Add a /api health endpoint (GET /health) and a /web landing page that says "OrderlyAI" and links to
/login. Add README run instructions for both apps. Don't implement features yet — just a clean,
runnable skeleton for both apps.
```

---

## STEP 1 — Database schema (Supabase migration) + tenant-isolation test

```
Using docs/08-database-schema.md as the EXACT source of truth, create a Supabase migration in
/supabase/migrations that creates: all extensions, the set_updated_at + assign_order_no functions and
triggers, every table (business, profile, membership, category, product, product_option_group,
product_option_item, business_hours, delivery_zone, customer, "order", order_item,
order_status_history, agent_config, whatsapp_channel, conversation, message), all indexes, and all RLS
policies including the current_business_ids() SECURITY DEFINER helper.

Do NOT create the plan/subscription tables yet (those are Phase 2 in the doc).

Also add the seed example from §11 of the doc as a separate seed file.

Add a pytest in /api/tests/test_tenant_isolation.py that: creates two businesses with two users, inserts
data for each, and asserts that querying as user A returns ZERO rows belonging to business B for
product, "order", and customer. This test protects against the CVE-2024-10976 pooling leak noted in the
doc. Document how to run the migration with the Supabase CLI in the README.
```

---

## STEP 2 — FastAPI foundation (config, db, auth, tenant scoping)

```
In /api, build the foundation (no business endpoints yet):
- app/core/config.py: pydantic-settings loading the env vars from .env.example.
- app/core/db.py: async SQLAlchemy engine + session dependency over DATABASE_URL.
- app/core/auth.py: a FastAPI dependency get_current_user that verifies the Supabase JWT using
  SUPABASE_JWT_SECRET (HS256), extracts the user id (sub), and a get_current_membership dependency that
  loads the user's business_id(s) from the membership table. Provide a require_business(business_id)
  dependency that 403s if the user is not a member.
- Helper: a CurrentTenant context (user_id + business_id + role) injected into routes.
- CORS for the web origin, structured error handling (consistent JSON errors), request logging,
  and OpenAPI docs at /docs.
- A protected GET /me endpoint returning the user + their businesses, to verify auth end-to-end.

Reminder: this service uses the service-role DB connection which bypasses RLS, so EVERY query in later
endpoints must filter by the authenticated business_id. Add a short note in app/core/auth.py docstring.
Write pytest for the auth dependency (valid/invalid/missing token).
```

---

## STEP 3 — FastAPI CMS endpoints (the backend for onboarding + dashboard)

```
In /api, implement tenant-scoped REST endpoints (all require auth + filter by business_id). Use pydantic
v2 schemas matching docs/08-database-schema.md column names. Add pytest for each resource (happy path +
cross-tenant 403).

Resources:
- Businesses:   POST /businesses (create + add membership owner), GET /businesses/{id}, PATCH /businesses/{id}
                (profile + fulfillment settings + accepting_orders + status).
- Categories:   CRUD /categories (scoped to business), with sort_order.
- Products:     CRUD /products (incl. tags[], is_available, is_archived, image_url string, sort_order)
                and nested option groups/items: /products/{id}/option-groups and .../option-items.
- Business hours: PUT /business-hours (bulk upsert the weekly schedule).
- Delivery zones: CRUD /delivery-zones.
- Customers:    GET/list + GET /customers/{id} (read-only for now; created by the agent later).
- Orders:       GET list (filter by status, date), GET /orders/{id}, PATCH /orders/{id}/status
                (validates the status state machine in docs/03 and writes order_status_history).
                Include a POST /orders for manual/test order creation that computes totals server-side
                and assigns order_no via the DB trigger.

Keep business logic in app/services. Return clean pydantic response models.
```

---

## STEP 4 — Next.js: email auth + protected app shell (wire your existing login)

```
In /web, implement authentication and the authenticated app shell:
- Supabase Auth with EMAIL/PASSWORD ONLY (no Google/Apple/WhatsApp for now). Sign in + Create account
  (+ email verification) + forgot password. Use the existing login design (dark split-screen left,
  white auth card right, OrderlyAI green branding) — match docs/09 §A design system.
- Session handling, a typed API client (lib/api.ts) that attaches the Supabase JWT as a Bearer token to
  all FastAPI calls, and a TanStack Query setup.
- Route protection: unauthenticated users → /login; authenticated users with business.status='onboarding'
  → /onboarding; otherwise → /dashboard.
- An authenticated app layout with a top bar (logo, business switcher placeholder, user menu/logout) and
  a left nav (Dashboard, Orders, Menu, Settings) — light theme per the design system.
- A /dashboard placeholder page that calls GET /me to prove the auth → API flow works end to end.
```

---

## STEP 5 — Next.js: onboarding wizard (steps 1–4, wired to the API)

```
Build the onboarding wizard in /web per docs/09-onboarding-screen-prompts.md (§B shell + §C1–§C4),
matching the §A design system. Implement and WIRE TO THE API:
- The wizard shell (§B): left numbered stepper, top progress, Back/Skip/Continue, resumable, autosave.
- Step 1 Business Profile → POST/PATCH /businesses.
- Step 2 Hours → PUT /business-hours; the "Accepting orders now" switch → PATCH /businesses.
- Step 3 Fulfillment & Delivery → PATCH /businesses (settings) + CRUD /delivery-zones.
- Step 4 Menu Builder → /categories and /products (+ option groups/items), with the "seed sample menu"
  action and a local-file image dropzone that stores a path string for now.
- Step 7 Review & Go Live → PATCH /businesses {status:'active'} (requires profile + >=1 dish), then
  redirect to /dashboard.
Generate steps 5 (AI Assistant) and 6 (Connect WhatsApp) as UI only per docs/09 (skippable, not wired
yet). Use zod validation and show inline errors. Keep field names matching the schema.
```

---

## STEP 6 — Next.js: the dashboard (orders, menu, settings)

```
Build the main authenticated dashboard pages in /web (light theme, design system from docs/09 §A),
wired to the API:
- /orders: a live orders board grouped by status (pending, accepted, preparing, ready/out_for_delivery,
  completed). Each order card shows order_no, customer, items, total, time. Status-advance buttons call
  PATCH /orders/{id}/status following the state machine in docs/03. Add filters (status, date) and an
  order detail drawer. (Realtime via Supabase can come later; poll with TanStack Query for now.)
- /menu: manage categories + products (same components as onboarding step 4, reused), incl. availability
  toggles and the modifier editor.
- /settings: edit business profile, hours, fulfillment, delivery zones, and the "Accepting orders" switch
  (reuse onboarding forms). A read-only "Plan: Free" badge (placeholder for subscriptions later).
Seed a few fake orders (via POST /orders) so the board isn't empty while testing.
```

---

## STEP 7 — (LATER, agent phase) LangGraph agent + tools

```
In /api, add the AI agent per docs/03-ai-agent-and-orders.md:
- A LangGraph create_react_agent with a PostgresSaver checkpointer (thread_id = business_id:phone).
- Tenant-scoped tools bound to a business_id: get_menu, search_menu, check_availability,
  get_business_hours, check_delivery_area, create_order (validates items/prices/hours/area server-side,
  writes via the existing order service).
- Use Claude via langchain-anthropic (model from env), system prompt rendered per business from
  agent_config. Add a POST /agent/dev/message endpoint that runs the agent for a given business_id +
  text, so it can be tested WITHOUT WhatsApp. Add tests with a fake LLM.
```

---

## STEP 8 — (LATER, WhatsApp phase) webhook + gateway + worker

```
In /api, add WhatsApp per docs/02 (§6) and docs/03:
- A WhatsAppGateway interface with a MetaCloudGateway implementation (send text/buttons/list/image).
- POST/GET /webhooks/whatsapp: GET verify challenge; POST verifies X-Hub-Signature-256, dedupes on
  wa_message_id, maps phone_number_id → business_id (whatsapp_channel), enqueues to Redis (ARQ), returns
  200 fast.
- An ARQ worker that consumes the queue, runs the agent, sends the reply, and logs to conversation/
  message. Serialize per thread_id to avoid races. Encrypt stored tokens.
- Wire onboarding Step 6 to save a test-number connection (phone_number_id + token).
```

---

## Working rules for every step
- **Review the diff** and **run the app** before sending the next prompt.
- Ask Codex to **run the tests** at the end of each step; fix failures before moving on.
- **Commit per step** with a clear message.
- If Codex drifts from the schema/architecture, point it back to `docs/08` / this file.
- Don't start Step 7/8 until the CMS (Steps 0–6) works end to end.
```
