# OrderlyAI

AI-powered WhatsApp ordering + CMS platform for small food businesses
(restaurants, cafés, bakeries, home kitchens). Multi-tenant SaaS.

> **Status:** Backend (CMS API) built and tested. Frontend (Next.js) is **in progress** in
> `web/` with shadcn/ui, auth, and onboarding steps 1–6 including the backend-wired menu builder and AI assistant config. The LangGraph
> WhatsApp agent and billing follow. Design docs live in `../inshakh/whatsapp-ordering-saas/`.

## Stack (current)

| Layer | Tech |
|-------|------|
| Backend | **FastAPI** (Python 3.12) · SQLAlchemy 2.0 async · asyncpg · Alembic · Pydantic v2 |
| Auth | **Self-managed JWT** (access + refresh) · argon2 password hashing |
| Database | **PostgreSQL 16** in Docker |
| Multi-tenancy | `business_id` on every row + app-layer scoping (`get_business` gate) |
| Frontend | **Next.js 16** (App Router, TS) · Tailwind v4 · **shadcn/ui** (Base UI) · pnpm — _in progress_ |

## Prerequisites
- [Docker](https://www.docker.com/) (for Postgres)
- [uv](https://docs.astral.sh/uv/) (Python package manager)

## Run it locally

```bash
# 0. Clone
git clone https://github.com/InshaKhan6593/orderlyai.git
cd orderlyai

# 1. Start Postgres (host port 55432 → avoids your native PostgreSQL on 5432)
docker compose up -d

# 2. Install backend deps
cd api
uv sync

# 3. Apply database migrations
uv run alembic upgrade head

# 4. Run the API (hot reload — watch only app/, not .venv)
uv run uvicorn app.main:app --reload --reload-dir app --port 8000
```

Then open:
- **API docs (Swagger):** http://localhost:8000/docs
- **Health:** http://localhost:8000/health

> `api/.env` is pre-filled for local dev (`DEBUG=true`). `DEBUG` defaults to **false**
> when unset — set a strong `JWT_SECRET` before deploying.

## Run the frontend (web)

The Next.js app lives in `web/` (App Router, Tailwind v4, shadcn/ui). It talks to the
FastAPI backend above via `NEXT_PUBLIC_API_URL`.

```bash
cd web
pnpm install
cp .env.example .env.local     # points at http://localhost:8000/api/v1 by default
pnpm dev                       # http://localhost:3000
```

Currently built: the brand design system, sign-in/sign-up flows, and onboarding through
the backend-wired AI assistant setup. Business profile, fulfillment settings, menu data,
and assistant config are wired to the API; hours remains client-side until the agent
ordering phase. WhatsApp connection and dashboard screens are next.

> **shadcn MCP:** `.mcp.json` registers the shadcn MCP server so an AI agent can browse and
> add components. After it's approved, run `pnpm dlx shadcn@latest add <component>` from `web/`.

## Tests

```bash
cd api
uv run pytest            # 65 tests: auth, tenant isolation, validation, enums, CRUD,
                         #           pricing/status, + security/correctness regressions
uv run python smoke.py   # end-to-end smoke against the running DB
```

## Project layout

```
orderlyai/
├── AGENTS.md                   # working rules / source of truth for contributors
├── .mcp.json                   # shadcn MCP server (project-scoped, for AI agents)
├── docker-compose.yml          # Postgres 16 (host :55432)
├── screens/                    # design mockups (onboarding + dashboard)
├── web/                        # Next.js 16 frontend (App Router, Tailwind v4, shadcn/ui)
│   └── src/
│       ├── app/               # routes: / (landing), /login, layout, globals.css (theme)
│       ├── components/        # ui/ (shadcn) + brand/ (logo)
│       └── lib/               # utils (cn), api (backend base URL)
└── api/
    ├── app/
    │   ├── main.py             # FastAPI app (CORS, error handlers, routers)
    │   ├── core/              # config, db, security (JWT/argon2), deps, errors
    │   ├── models/            # SQLAlchemy 2.0 models (15 tables)
    │   ├── schemas/           # Pydantic request/response models
    │   ├── services/          # auth, business, order engine (pricing, status machine)
    │   └── api/               # routers: auth, businesses, categories, products,
    │                          #          hours, delivery-zones, customers, orders
    ├── migrations/            # Alembic (async)
    ├── tests/                 # pytest suite
    └── pyproject.toml
```

## API surface (v1, prefix `/api/v1`)

| Group | Endpoints |
|-------|-----------|
| Auth | `POST /auth/register · /auth/login · /auth/refresh` · `GET /auth/me` |
| Businesses | `POST/GET /businesses` · `GET/PATCH /businesses/{id}` |
| Menu | `…/categories` (CRUD) · `…/products` (CRUD + modifier assignments) · `…/modifier-groups` (reusable library CRUD) |
| Ops | `…/hours` (GET/PUT) · `…/delivery-zones` (CRUD) |
| Agent | `…/agent-config` (GET/PUT assistant setup) |
| Customers | `…/customers` (read, paginated) |
| Orders | `GET/POST …/orders` · `GET …/orders/{id}` · `PATCH …/orders/{id}/status` |

All tenant routes live under `/businesses/{business_id}/…` and require the caller
to be a member of that business. List endpoints for orders and customers accept
`?limit=` (1–200, default 50) and `?offset=`.

## Notes
- **Order pricing is server-authoritative:** line total = `(product price + Σ option
  deltas) × qty`, computed in `services/order_service.py` — never trusted from the client.
  A line whose price would go negative is rejected, and duplicate option ids are refused.
- **Order numbers** are a per-business sequence assigned atomically.
- **Status machine is fulfillment-aware:** pickup is
  `pending → accepted → preparing → ready → completed`; delivery dispatches directly
  `pending → accepted → preparing → out_for_delivery → completed` (+ `rejected`/`cancelled`).
  Invalid jumps are rejected, and `changed_by` in the audit trail is the authenticated user.
- **Tenant safety:** every query is scoped by `business_id`; a product's `category_id`
  and an order's `zone_id` (active, meets `min_order`) must belong to the same business.
- A `Dockerfile` is included for later deployment; local dev runs via uvicorn.
