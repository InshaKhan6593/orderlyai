# AGENTS.md — OrderlyAI

Context and working rules for any AI agent (Codex, Cursor, Claude Code, etc.) contributing to this repo.
Read this fully before making changes. It is the source of truth for **how** to work here; the product/design
source of truth lives in the design docs (see [§14](#14-roadmap--design-docs)).

---

## 1. What this project is

**OrderlyAI** is a multi-tenant SaaS that lets small food businesses (restaurants, cafés, bakeries, home
kitchens) run ordering over WhatsApp:

- **Business owners** manage their menu, modifiers, prices, hours, delivery zones, and incoming orders from a
  dashboard (a CMS).
- **Customers** message the business on WhatsApp; an **AI agent** (LangGraph) answers questions, shows the
  menu, and places orders — all written into the same database the dashboard reads.

It is built to be both a freelance/portfolio product and a real SaaS sold to many businesses (each business
is one **tenant**). Target scale: 100–150+ business tenants.

---

## 2. Current status

| Area | State |
|------|-------|
| **Backend CMS API** (`api/`) | ✅ Built, running, and tested (90 passing tests) |
| Database (Postgres 16 in Docker) | ✅ Schema + Alembic migrations applied |
| Auth (self-managed JWT) | ✅ Done |
| **Frontend** (Next.js) | 🚧 In progress in `web/` (Next.js 16 + Tailwind v4 + shadcn/ui). Auth plus onboarding steps 1–6 are built; business profile, fulfillment, menu builder, and AI assistant config are wired to the API |
| **WhatsApp AI agent** (LangChain v1 + Claude) | 🚧 Core agent built in `api/app/agent/` (graph, tenant-scoped tools, per-tenant prompt, middleware, Pydantic structured output) + tested. Not yet wired to the webhook/worker. See `docs/agent/ARCHITECTURE.md` |
| WhatsApp Cloud API integration | ❌ Not built yet |
| Billing (Stripe + `plan`/`subscription`) | ❌ Not built — schema is forward-compatible (`business.plan_code` exists) |

When you finish a unit of work, update this table if the status changed.

---

## 3. Golden rules (read first)

1. **Multi-tenancy is sacred.** Every tenant-owned row has `business_id`. The backend connects with a
   privileged DB role (no Postgres RLS locally), so **every query MUST be scoped by the authenticated
   `business_id`**. Use the `get_business` dependency — never accept a `business_id` from the body and trust it.
2. **Order pricing is server-authoritative.** Never trust prices/totals from the client. Compute
   `line_total = (product.price + Σ option price_deltas) × quantity` from the DB (see `services/order_service.py`).
3. **Match existing patterns.** Mirror the structure, naming, typing, and style already in `app/`. Don't
   introduce a new framework, ORM, auth scheme, or folder convention without a strong reason.
4. **Keep field names aligned** between SQLAlchemy models, Pydantic schemas, and migrations.
5. **Add tests for new behavior**, and **a tenant-isolation test for any new tenant resource**.
6. **Never commit secrets.** `.env` is gitignored. Don't log tokens or password hashes.
7. **Don't print emojis/Unicode in scripts** — the Windows console is cp1252 and will crash on them.
8. The backend stays in **Python**: the WhatsApp agent will be Python/LangGraph, so don't split the API into
   another language.
9. **Frontend work has its own local instructions.** Before editing `web/`, read `web/AGENTS.md`; it owns
   Next.js/shadcn commands, UI conventions, and onboarding-specific rules.

---

## 4. Tech stack & versions

- **Language/runtime:** Python 3.12+ (the uv venv uses CPython 3.13).
- **Web:** FastAPI 0.138, Starlette 1.x, Uvicorn.
- **DB/ORM:** PostgreSQL 16 (Docker), SQLAlchemy 2.0.51 **async** + asyncpg, Alembic 1.18 (async env).
- **Validation:** Pydantic v2 (2.13) + pydantic-settings.
- **Auth:** PyJWT (HS256) + argon2-cffi for password hashing. Bearer tokens (no Supabase, no OAuth).
- **Tooling:** `uv` (package manager), `pytest` + `httpx`/TestClient.
- Frontend (in progress, `web/`): Next.js 16 + TypeScript + Tailwind v4 + shadcn/ui (Base UI) + pnpm.

Pin nothing by hand — `uv` resolves from `pyproject.toml`. Use `uv add <pkg>` to add dependencies.

---

## 5. Repository layout

**Git remote:** `https://github.com/InshaKhan6593/orderlyai.git` (default branch `main`).
Clone/push over HTTPS. `.env` and `.venv/` are gitignored — never commit them.

```
orderlyai/
├── AGENTS.md                  # this file
├── README.md                  # human run instructions
├── .mcp.json                  # shadcn MCP server (project-scoped, for AI agents)
├── docker-compose.yml         # Postgres 16, host port 55432
├── screens/                   # design mockups (onboarding + dashboard PNG screens)
├── web/                       # Next.js 16 frontend (App Router, Tailwind v4, shadcn/ui)
│   ├── components.json        # shadcn config (style: base-nova, Base UI, lucide)
│   └── src/{app,components,lib}/
└── api/
    ├── pyproject.toml         # deps + pytest config (uv-managed)
    ├── uv.lock
    ├── alembic.ini
    ├── .env / .env.example    # config (DATABASE_URL, JWT_SECRET, CORS, …)
    ├── Dockerfile             # for later deployment
    ├── smoke.py               # end-to-end smoke script (uv run python smoke.py)
    ├── migrations/            # Alembic (async env.py)
    │   └── versions/
    ├── tests/                 # pytest: conftest + test_auth/test_orders/test_tenant_isolation
    └── app/
        ├── main.py            # FastAPI app: CORS, error handlers, /health, mounts api_router at /api/v1
        ├── core/
        │   ├── config.py      # Settings (pydantic-settings), get_settings(), settings
        │   ├── db.py          # async engine + get_db() session dependency
        │   ├── security.py    # hash/verify password (argon2), create/decode JWT
        │   ├── deps.py        # get_current_user, get_business (tenant gate), DbSession/CurrentUser/BusinessDep
        │   ├── errors.py      # AppError hierarchy + register_exception_handlers
        │   ├── logging.py     # structured logging config
        │   └── utils.py       # slugify, etc.
        ├── models/            # SQLAlchemy 2.0 models (Mapped/mapped_column). __init__ re-exports + registers all
        ├── schemas/           # Pydantic request/response models (ORMModel base = from_attributes)
        ├── services/          # business logic: auth_service, business_service, order_service
        └── api/               # routers, aggregated in api/router.py
```

---

## 6. Local development

**Prerequisites:** Docker, `uv`, and `pnpm`. There is a **native PostgreSQL 17 on port 5432**, so our
container uses **host port 55432** (`DATABASE_URL` already points there). Do not change this to 5432.

```bash
# from repo root
docker compose up -d                                          # Postgres on :55432

cd api
uv sync                                                       # install deps into api/.venv
uv run alembic upgrade head                                   # apply migrations
uv run uvicorn app.main:app --reload --reload-dir app --port 8000
#   ↑ --reload-dir app is REQUIRED: otherwise uvicorn watches .venv and reload-loops
```

- API docs: http://localhost:8000/docs  ·  Health: http://localhost:8000/health
- Tests: `uv run pytest`  (uses a separate `orderlyai_test` database, created/dropped per session)
- Smoke: `uv run python smoke.py`
- New migration: `uv run alembic revision --autogenerate -m "msg"` then review the file, then `upgrade head`.

Always run commands with `uv run …` from the `api/` directory (so `.env` and the `app` package resolve).

Frontend setup, checks, and UI conventions live in `web/AGENTS.md`. For frontend changes, follow that file
and run the relevant `pnpm` checks from `web/`.

---

## 7. Architecture & conventions

### Request lifecycle
`HTTP → FastAPI router → dependency (auth + tenant) → service (logic) → SQLAlchemy (async) → Pydantic response`.
The frontend and the WhatsApp agent both go through this same API/services layer.

### Multi-tenancy & security (critical)
- Tenant routes are nested: `/api/v1/businesses/{business_id}/<resource>`.
- Handlers depend on **`BusinessDep`** (`business: BusinessDep`), which runs `get_business`: it verifies the
  caller has a `Membership` for that `business_id` (→ 403 if not) and loads the `Business`. Use `business.id`
  to scope every query: `where(Model.business_id == business.id)`.
- Denormalized `business_id` exists even on child tables (e.g. `order_items`, `modifier_options`) so every
  query can be scoped without joins.
- RLS is **not** relied upon locally; app-layer scoping is the guard. (This mirrors the CVE-2024-10976 defense
  -in-depth note from the design docs.) If you add a tenant table, add a tenant-isolation test.

### Auth
- `POST /auth/register | /login | /refresh`, `GET /auth/me`. Tokens are JWT (HS256), `type` claim is
  `access` or `refresh`; access expires in 30 min, refresh in 14 days. Passwords hashed with argon2.
- Protected routes depend on `CurrentUser` (validates the bearer access token). Customers are **not** users —
  they're identified by WhatsApp phone (`customers.wa_phone`, unique per business).

### Database / models (SQLAlchemy 2.0 async)
- Declarative models use `Mapped[...]` + `mapped_column(...)`. Mixins: `UUIDMixin` (uuid PK), `TimestampMixin`
  (`created_at`/`updated_at`). Base sets a constraint naming convention — keep using it.
- **Async lazy-loading is disabled** — accessing an unloaded relationship raises. For responses that include
  relationships, **eager-load with `selectinload`** (see products → `option_groups.items`, orders →
  `items` + `status_history`). `expire_on_commit=False` is set, so objects stay usable after commit.
- Enumerated string columns use `CHECK` constraints (e.g. order `status`, `fulfillment`), not native PG enums.
- Money is `Numeric(12, 2)` → Python `Decimal`. Always compute with `Decimal`.

### Schemas (Pydantic v2)
- Response models inherit `ORMModel` (`schemas/common.py`, `from_attributes=True`).
- Input models use `Field(...)` constraints and regex `pattern=` for enums. `PATCH` bodies are all-optional;
  apply with `data.model_dump(exclude_unset=True)`.

### Services
- Non-trivial logic lives in `app/services/` and receives the `AsyncSession` from the route. Simple CRUD can
  stay in the router. Services own: registration/auth tokens, business creation (+owner membership + unique
  slug), and the order engine.

### Errors
- Raise `AppError` subclasses from `core/errors.py`: `NotFoundError` (404), `UnauthorizedError` (401),
  `ForbiddenError` (403), `ConflictError` (409), `BadRequestError` (400). They serialize to
  `{"error": {"code", "message"}}`. Validation errors → 422 automatically.
- ⚠️ `JSONResponse` takes **`content` first**: `JSONResponse(content=..., status_code=...)`.

### Migrations
- Alembic env is **async** and imports `Base.metadata` from `app.models`. After changing a model, autogenerate
  a revision, **read it** (autogenerate misses some things), then `upgrade head`. Never edit a model without a
  matching migration.

---

## 8. Data model (16 tables)

```
users ─< memberships >─ businesses ─┬─< categories ─< products ─< product_modifier_groups >─ modifier_groups ─< modifier_options
                                    │                                └─< product_modifier_option_prices
                                    ├─< agent_configs
                                    ├─< business_hours
                                    ├─< delivery_zones
                                    ├─< customers ─< orders ─< order_items
                                    └─────────────────────────< orders ─< order_status_history
```

Key points:
- **`businesses`** is the tenant root. Holds profile, fulfillment settings (`offers_delivery/pickup`,
  `min_order_amount`, `packaging_fee`), the `accepting_orders` kill-switch, `status`
  (`onboarding|active|paused|suspended`), `plan_code` (billing-ready), and `next_order_no` (the per-business
  order counter).
- **`agent_configs`** stores the per-business WhatsApp assistant setup used later by the agent runtime:
  English-only greeting, upsell toggle, human handoff phone, and extra instructions. Tone and auto-approval
  fields are intentionally not part of the schema.
- **`memberships`** = (user_id, business_id, role) with role `owner|manager|staff`.
- **`products`** have `tags text[]`, `is_available` (temporary sold-out), and `is_archived` (permanent removal).
  Modifier definitions can be reusable templates or dish-specific groups. They attach through
  `product_modifier_groups`; required/min/max/order and the enabled option subset, dish defaults, and optional
  per-dish prices live in `product_modifier_option_prices`. Missing option rows mean that option is unavailable
  for that dish. Group option prices are template defaults; assignment overrides are used when present.
- **`orders`**: `order_no` is unique per business; `order_items` **snapshot** `name_snapshot` + `price_snapshot`
  + chosen `options_json` so historical orders never change when the menu changes; `order_status_history`
  records every transition.
- pgvector/embeddings are intentionally **not** in the schema yet (added in the agent phase).

---

## 9. API reference (prefix `/api/v1`)

| Group | Endpoints |
|-------|-----------|
| Auth | `POST /auth/register`, `POST /auth/login`, `POST /auth/refresh`, `GET /auth/me` |
| Businesses | `POST /businesses`, `GET /businesses` (mine), `GET /businesses/{id}`, `PATCH /businesses/{id}` |
| Categories | `GET/POST /businesses/{id}/categories`, `PATCH/DELETE /…/categories/{cid}` |
| Products | `GET/POST /businesses/{id}/products`, `GET/PATCH/DELETE /…/products/{pid}` (modifier assignments; `?category_id=`, `?include_archived=`) |
| Modifier groups | `GET/POST /businesses/{id}/modifier-groups`, `GET/PATCH/DELETE /…/modifier-groups/{gid}` |
| Hours | `GET /businesses/{id}/hours`, `PUT /businesses/{id}/hours` (bulk replace) |
| Delivery zones | `GET/POST /businesses/{id}/delivery-zones`, `PATCH/DELETE /…/delivery-zones/{zid}` |
| Customers | `GET /businesses/{id}/customers`, `GET /…/customers/{cid}` |
| Orders | `GET /businesses/{id}/orders` (`?status=`, `?fulfillment=`), `POST /…/orders`, `GET /…/orders/{oid}`, `PATCH /…/orders/{oid}/status` |
| Agent config | `GET/PUT /businesses/{id}/agent-config` |

---

## 10. Business rules

- **Order status machine** (`order_service.TRANSITIONS`) is **fulfillment-aware** — `ready` and
  `out_for_delivery` are the parallel stage-4 states keyed by fulfillment (per design docs 07 §3): pickup is
  `pending → accepted → preparing → ready → completed`; delivery dispatches directly
  `pending → accepted → preparing → out_for_delivery → completed` (pickup never uses `out_for_delivery`;
  delivery has no `ready` stage). `rejected`/`cancelled` are early exits.
  Invalid jumps return 400. Every change appends an `order_status_history` row whose `changed_by` is the
  **authenticated user id** (derived server-side, never trusted from the request body). The status update
  loads the order `FOR UPDATE` so concurrent transitions serialize.
- **Pricing:** `unit = product.price + Σ(effective option price_delta)`, `line_total = unit × qty`,
  `subtotal = Σ line_totals`, `total = subtotal + delivery_fee + packaging_fee`. Delivery fee comes from the
  chosen `delivery_zone`; packaging fee from the business. Effective option prices come from the product's
  assignment override when present, otherwise the reusable group option default. Negative `price_delta`
  (discounts) is allowed, but a line whose `unit` would go **negative** is rejected (400).
- **Modifier validation:** on order creation, selected options are validated against the options explicitly
  enabled on that product assignment — required groups must be chosen, assignment `min_select`/`max_select` are honored, single-select groups accept
  at most one, duplicate option ids in a line are rejected, and options from another product/business are
  rejected (all → 400). See `order_service.create_order` (products are bulk-fetched in one query).
- **Category ownership:** a product's `category_id` must belong to the same business (validated on
  create/update → 400); app-layer scoping is the guard (no cross-tenant category references).
- **Delivery zones:** a provided `zone_id` must be owned by the business, **active**, and the `subtotal` must
  meet the zone's `min_order` (all → 400).
- **Order numbers** are assigned atomically via `UPDATE businesses SET next_order_no = next_order_no + 1
  … RETURNING` inside the create transaction.
- **`accepting_orders = false`** blocks `POST /orders` (the owner's instant kill-switch).
- **Customers** are upserted by `(business_id, wa_phone)` via PostgreSQL `ON CONFLICT` during order creation,
  and `order_count` is bumped with an atomic `UPDATE` (no read-modify-write race).
- **Business hours** allow at most one row per weekday — duplicate `day_of_week` is rejected (422), backed by
  `UNIQUE (business_id, day_of_week)`.
- **Pagination:** list endpoints for orders and customers take `?limit=` (1–200, default 50) and `?offset=`.

> **Deferred order validation (implement in the agent / order-flow phase, with tests):** the engine does
> **not** yet require a delivery **address** when `fulfillment="delivery"`, nor enforce the *business-level*
> `min_order_amount` (distinct from per-zone `min_order`, which **is** enforced), nor make a delivery `zone`
> mandatory. These tie into the WhatsApp ordering flow — add them when building the agent.
>
> **Also deferred (auth/roles hardening phase):** `get_business` authorizes any membership regardless of
> `owner|manager|staff` role — fine today because no endpoint creates non-owner memberships yet; add role
> gating when membership management ships. Auth rate-limiting and refresh-token rotation are not implemented.

---

## 11. Testing

- `tests/conftest.py` builds an isolated **`orderlyai_test`** DB (create_all/drop_all per session, NullPool
  engine), overrides `get_db`, and exposes a sync **`TestClient`** plus fixtures: **`client`**, **`owner`**
  (registered user → auth header), **`business`** (owner + created business → `(headers, business_id)`).
- Coverage today (**62 tests**): `test_auth.py` (register/login/me/dupe/wrong-pw/validation),
  `test_tenant_isolation.py` (outsiders get 403; `GET /businesses` only lists own), `test_orders.py`
  (pricing includes modifier deltas, `order_no` increments, invalid status transition rejected),
  `test_validation_and_crud.py` (enum/"dropdown" values rejected, required fields, business rules incl.
  **required-modifier enforcement**, and full CRUD lifecycle), `test_modifier_groups.py` (template/dish-specific
  creation, atomic assignment updates, enabled subsets, per-dish pricing, cleanup, unassigned-option rejection,
  and tenant isolation), and `test_review_fixes.py` (cross-tenant
  category rejected, negative/duplicate-option pricing rejected, delivery-zone active+min_order, fulfillment-
  aware status machine, audited `changed_by`, duplicate-hours 422, pagination, input caps).
- Frontend-specific test guidance lives in `web/AGENTS.md`. For frontend changes, run the relevant `pnpm`
  checks from `web/` before claiming the work is complete.
- **When you add a tenant resource, add an isolation test** (an outsider must get 403). When you add pricing or
  status logic, assert the numbers/transitions.

---

## 12. Common tasks (recipes)

**Add a new tenant resource (model → API):**
1. Model in `app/models/<x>.py` with `business_id` FK + relationships; export it in `app/models/__init__.py`.
2. `uv run alembic revision --autogenerate -m "add <x>"` → review → `uv run alembic upgrade head`.
3. Schemas in `app/schemas/<x>.py` (Create/Update/Out; Out inherits `ORMModel`).
4. (If logic) a service in `app/services/`.
5. Router in `app/api/<x>.py` with `prefix="/businesses/{business_id}/<x>"`, handlers using `BusinessDep` and
   scoping by `business.id`; include it in `app/api/router.py`.
6. Tests in `tests/` incl. a tenant-isolation case.

**Add an auth-only (non-tenant) endpoint:** use `CurrentUser` instead of `BusinessDep`.

**Change config:** add a field to `Settings` in `core/config.py` and to `.env.example` (and `.env`).

---

## 13. Known gotchas / environment quirks

- **Postgres port 55432**, not 5432 (native PG 17 owns 5432). Test DB is `orderlyai_test`.
- **Uvicorn reload:** always pass `--reload-dir app`, else it watches `.venv` and reload-loops on `.pyc` writes.
- **Starlette 1.x lazy routers:** `app.routes` shows few entries at import time (routers are `_IncludedRouter`
  placeholders resolved at build). Inspect routes via `/openapi.json` or a `TestClient`, not `len(app.routes)`.
- **`JSONResponse(content=..., status_code=...)`** — content is the first positional arg.
- **Validation-error details** can contain `Decimal`/`date` objects — pass `exc.errors()` through
  `jsonable_encoder` before returning (see `core/errors.py`), or the 422 handler itself 500s.
- **Windows console is cp1252** — no emojis in `print()` inside scripts.
- **Async relationships**: eager-load with `selectinload` or you'll hit `MissingGreenlet`/lazy-load errors.

---

## 14. Roadmap & design docs

**Next up (in order):** continue the frontend (`web/`) with onboarding steps 6–8, dashboard menu
management reuse, and dashboard screens → WhatsApp AI agent (LangGraph + Claude, inside `api/`) → WhatsApp Cloud API
webhook/worker → billing (Stripe).

**Full product/design source of truth** (research, architecture, exact schema, UI screen-generation prompts,
build prompts, dashboard prompts) lives **outside this repo** at:

```
C:\Users\Insha Khan\inshakh\whatsapp-ordering-saas\
  README.md                         # index
  01-research-findings.md           # WhatsApp API / BSP / pricing / framework comparisons
  02-architecture.md                # system architecture, multi-tenancy, deployment
  03-ai-agent-and-orders.md         # LangGraph agent + order flow design
  04-mvp-roadmap.md                 # MVP + roadmap + Fiverr packaging
  05-challenges-and-risks.md        # risks + mitigations
  06-testing-setup.md               # free WhatsApp test number setup
  07-cms-data-model-and-onboarding.md
  08-database-schema.md             # the schema this backend implements
  09-onboarding-screen-prompts.md   # UI generation prompts (design system in §A)
  10-codex-build-prompts.md         # ordered build prompts
  11-dashboard-screen-prompts.md    # dashboard UI prompts
```

If you're implementing a feature, read the relevant design doc first for the intended behavior. The WhatsApp
agent must do **concrete tasks** (show menu, take orders) — open-ended chat is disallowed by Meta's 2026 rules.

---

## 15. Do NOT

- Do not bypass `get_business` / leak cross-tenant data, or trust client-supplied prices.
- Do not use the native Postgres on 5432, or hardcode connection strings (use `settings`).
- Do not switch the backend off FastAPI/SQLAlchemy, add a second language, or introduce Supabase/an external
  auth provider — auth is self-managed JWT by design.
- Do not commit `.env`, real secrets, or generated `.venv`.
- Do not skip migrations when changing models, or skip tenant-isolation tests for new tenant resources.
