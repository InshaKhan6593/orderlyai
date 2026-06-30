# 11 · Dashboard Screen Generation Prompts

Copy-paste prompts for the **daily-use app owners see after "Go live"** — the dashboard. Same approach as
the onboarding pack (`09`): prepend the **§A Design System block from `09-onboarding-screen-prompts.md`**
to each screen (or set it as global context), then generate one screen at a time.

The dashboard:
```
Overview (landing) · Orders (the workhorse) · Menu · Customers (later) · Settings
```
Default landing after login = **Orders board** (a restaurant lives on orders). Reuse onboarding
components where noted — don't rebuild.

---

## §E — Dashboard Shell (generate first; wraps every page)

```
Build the authenticated DASHBOARD SHELL/layout for OrderlyAI (the app owners use after going live).
Match the §A design system from docs/09 (light theme, green accents, serif headings, shadcn/ui).

LAYOUT (desktop):
- Left sidebar nav (240px): OrderlyAI logo at top; nav items with icons — Overview, Orders (with a live
  count badge of new orders), Menu, Customers, Settings. Active item highlighted green. Bottom of sidebar:
  a business switcher (current business name + dropdown to switch businesses) and a user avatar menu
  (Profile, Log out).
- Top bar: current page title on the left; on the right — a prominent "Accepting orders" ON/OFF toggle
  (global kill-switch), a notification bell with a new-order badge, and the business name/avatar.
- Content area: light background; pages render here.

LAYOUT (mobile): sidebar collapses to a hamburger drawer (or bottom tab bar); the top bar keeps the
"Accepting orders" toggle and the bell.

BEHAVIOR: the "Accepting orders" toggle PATCHes business.accepting_orders and shows a toast. The Orders
nav badge and the bell reflect the live count of new (pending) orders.

Provide a <DashboardShell> component with the nav + top bar and a content slot for child pages.
```

---

## §F1 — Orders Board (the primary daily screen)  → `GET /orders`, `PATCH /orders/{id}/status`

```
Build the ORDERS BOARD inside the DashboardShell — the most-used screen. Page title "Orders".

DEFAULT VIEW: a kanban board with 5 columns by status, each with a header + live count:
1) New   2) Accepted   3) Preparing   4) Ready / Out for delivery   5) Completed
(Rejected/Cancelled are NOT columns — reachable via a filter.)

PAGE TOOLBAR: date filter (default Today), fulfillment filter (All / Delivery / Pickup), a search box
(order # or customer name), a Board/List view toggle, and a sound-notification toggle for new orders.

ORDER CARD (in each column):
- Order number (#1024), time-ago ("4 min ago"), customer name.
- Fulfillment badge: "Delivery · {zone}" or "Pickup".
- Items summary: "2× Margherita, 1× Coke" (modifiers truncated).
- Total (₨), a payment badge (COD / Paid), and a notes icon if notes exist.
- NEW cards (pending) get a highlighted border + unread dot + subtle pulse, and play a sound on arrival.
- Action buttons per status:
    New        → [Accept] [Reject]
    Accepted   → [Start preparing] [Cancel]
    Preparing  → [Mark ready] (pickup) or [Out for delivery] (delivery) [Cancel]
    Ready/Out  → [Complete]
    Completed  → view only

ORDER DETAIL (right Drawer when a card is clicked):
- Full item list with chosen modifiers and per-line prices.
- Subtotal, delivery fee, packaging fee, Total.
- Customer name + phone with a "Message on WhatsApp" button.
- Delivery address + zone (or "Pickup"); payment method + status.
- An order TIMELINE (status history with timestamps).
- The same status-advance + Cancel/Reject actions.

REALTIME: new orders appear live (Supabase Realtime on the orders table filtered by business_id, or poll
every few seconds) with sound + bell badge; cards move columns automatically when status changes.

ALSO provide a LIST/table view (via the toggle): columns #, time, customer, items, total, fulfillment,
status, actions.

EMPTY STATE: "No orders yet — when customers order on WhatsApp, they'll show up here live."
```

---

## §F2 — Menu Management  → reuses onboarding Step 5  → `/categories`, `/products`

```
Build the MENU MANAGEMENT page inside the DashboardShell. REUSE THE EXACT components from onboarding
Step 5 (docs/09 §C4): categories sidebar + dish grid + add/edit-dish drawer WITH the options & modifiers
editor. Do not rebuild them — share the same components.

Differences from onboarding:
- Page header "Menu" with "+ Add category" / "+ Add dish" (no wizard progress bar or Back/Continue footer).
- Changes save immediately with a toast ("Saved"), not a wizard Continue step.
- Keep search + category filter, the per-dish availability toggle (quick sold-out management), and
  drag-to-reorder for categories and dishes.
- Keep the empty state with "Seed sample menu".
```

---

## §F3 — Settings  → reuses onboarding forms  → `PATCH /businesses`, etc.

```
Build the SETTINGS page inside the DashboardShell. Page title "Settings". Use a left sub-nav with tabs:
Business Profile · Hours · Fulfillment & Delivery · Delivery Zones · AI Assistant · WhatsApp ·
Plan & Billing · Team.

Each tab REUSES the corresponding onboarding form (docs/09 §C1, §C2, §C3, §C5, §C6) but as a standalone
editable section with its own "Save changes" button + toast (immediate save — NOT a wizard flow).
- Plan & Billing: placeholder only — "Current plan: Free" with a disabled "Upgrade (coming soon)".
  No Stripe yet.
- Team: placeholder — "Invite teammates (coming soon)".
- Surface the "Accepting orders" toggle here too, kept in sync with the top bar.
```

---

## §F4 — Overview / Home (light landing — full analytics later)  → `GET /orders` (aggregates)

```
Build a light OVERVIEW/HOME page inside the DashboardShell (the landing after login). Keep it LIGHT —
deep analytics come later.
- Top row: 4 stat cards — Today's orders, Today's sales (₨), Orders needing attention (pending count),
  Avg prep time.
- A banner "X orders need your attention →" linking to the Orders board (show only when pending > 0).
- "Recent orders" list (last 8): #, customer, total, status, click-through to the order drawer.
- "Top items this week": simple list of item name + order count.
- A placeholder card "Analytics coming soon" — do NOT add trend charts or date-range analytics yet.
```

---

## §G — Generation order, reuse & build mapping

**Generate in this order:** §E shell → §F1 Orders → §F2 Menu → §F3 Settings → §F4 Overview.

**Reuse (don't rebuild):**
- Menu page = onboarding Step 5 components.
- Settings tabs = onboarding form components (§C1/C2/C3/C5/C6).
- The "Accepting orders" toggle appears in the top bar *and* Settings — one shared state.

**Wire to the API (names per `08-database-schema.md`):**
| Screen | Endpoints |
|---|---|
| Orders | `GET /orders` (filters), `GET /orders/{id}`, `PATCH /orders/{id}/status` (+ realtime) |
| Menu | `/categories`, `/products` (+ option groups/items) |
| Settings | `PATCH /businesses`, `PUT /business-hours`, `/delivery-zones`, `/agent-config`, `/whatsapp-channel` |
| Overview | `GET /orders` (today's aggregates + recent) |

**Standing rules (carry over from onboarding):** every field labeled; toasts on save; realtime/notify on
new orders so the owner never misses one; mobile-responsive; keep field names matching the schema.

**Note on realtime:** for a live-ordering business the owner MUST notice new orders — implement the
Supabase Realtime subscription (or short polling) + sound + bell badge early; it's not optional polish.
```
