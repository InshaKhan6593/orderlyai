# 09 · Onboarding Screen Generation Prompts

Copy-paste prompts for an AI UI generator (**v0 / Lovable / Bolt / Cursor / Claude**) to build the
post-signup onboarding wizard for **OrderlyAI**. Every field maps to the schema in `08-database-schema.md`
so the UI and DB stay aligned.

**How to use:** paste **§A (Design System)** once as global/project context (or prepend it to each
screen prompt), then generate screens one at a time with §B → §C1…C7. Stack assumed: **Next.js (App
Router) + TypeScript + Tailwind + shadcn/ui + react-hook-form + zod**.

The flow:
```
Sign up ▶ 0 Welcome ▶ 1 Business profile ▶ 2 Hours ▶ 3 Fulfillment & delivery
        ▶ 4 Menu builder ▶ 5 AI assistant ▶ 6 Connect WhatsApp ▶ 7 Review & go live ▶ Dashboard
```
Screens **1–4** are functional now (CMS). **5–6** can be generated now but wired later (agent/WhatsApp
phase). All steps are **skippable & resumable**; `business.status` stays `onboarding` until step 7.

---

## §A — Design System (paste once as global context)

```
You are building the in-app UI for "OrderlyAI", an AI-powered WhatsApp ordering + CMS SaaS for small
food businesses (restaurants, cafés, bakeries, home kitchens). Match this design system exactly on
every screen:

BRAND & THEME
- Light, clean in-app theme (the marketing page is dark; the app is light).
- Primary: emerald/WhatsApp green (#16A34A) for buttons/active states; deep forest green (#0F3D2E)
  for headings and dark UI; soft gold (#D9A441) as a sparing accent only.
- Surfaces: white cards (#FFFFFF) on a light background (#F6F8F7); subtle 1px borders (#E6EAE8);
  soft shadows; rounded-2xl corners; generous whitespace.
- Success = green, warning = amber, danger = red; muted gray text for hints.

TYPOGRAPHY
- Display serif for large headings (e.g. "Fraunces" or "Playfair Display").
- "Inter" (or Geist) for all UI text and inputs.

COMPONENTS & TECH
- Next.js App Router + TypeScript + Tailwind + shadcn/ui. Forms with react-hook-form + zod.
- Use shadcn Card, Input, Textarea, Select, Switch, Checkbox, RadioGroup, Button, Badge, Tabs,
  Dialog/Drawer, Tooltip, Progress, Sonner (toasts), Avatar, Skeleton.
- Inputs: clear labels above field, helper text below, inline validation errors in red, required
  marked with *. Primary button is full-width green with a right arrow; secondary is outline.
- Image uploads: drag-and-drop dropzone with preview; for now store a LOCAL file path/URL string
  (no S3/Supabase yet) — just emit the value, backend swaps storage later.

UX RULES
- Friendly, encouraging microcopy. Mobile-first responsive. WCAG AA contrast.
- Autosave on blur with a small "Saved" indicator; never lose progress.
- Show empty states with a helpful illustration + primary action.
- Use the OrderlyAI logo (green chat-bubble) top-left.
```

---

## §B — Wizard Shell (generate first; it wraps every step)

```
Build an onboarding wizard SHELL/layout for OrderlyAI that wraps 8 steps (0 Welcome, 1 Business
Profile, 2 Hours, 3 Fulfillment & Delivery, 4 Menu, 5 AI Assistant, 6 Connect WhatsApp, 7 Review).

LAYOUT (desktop):
- Left vertical sidebar (280px): OrderlyAI logo at top, then a numbered vertical stepper listing the 8
  steps. Completed steps show a green check, current step is highlighted green, future steps are muted.
  Each step shows its title + 1-line subtitle. Bottom of sidebar: "Save & exit" link.
- Right content area: centered, max-width 720px. Top: step title (serif) + short description.
  Middle: the step's form (slot/children). Bottom sticky footer: "Back" (outline, hidden on step 0),
  "Skip for now" (ghost link, hidden where the step is required), and "Continue →" (primary, right).
- A thin top progress bar showing % complete.

LAYOUT (mobile): hide the sidebar; show the top progress bar + "Step X of 8 · {title}". Footer buttons
stack full-width.

BEHAVIOR: steps are resumable (load saved progress); "Continue" validates the current step then advances;
autosave per field; a small "Saved ✓" pill appears after save. Provide a <OnboardingShell currentStep>
component with children for the step body.
```

---

## §C1 — Step 1: Business Profile  → writes `business`

```
Build the "Business Profile" onboarding step inside the OnboardingShell. Heading: "Tell us about your
business". Subtitle: "This is what your customers will see."

LAYOUT: two-column on desktop (left: logo + cover upload; right: text fields), single column on mobile.

FIELDS:
- Business name *  — text, placeholder "e.g. The Green Bistro".
- Business type *  — segmented cards/radio with icons: Restaurant, Café, Bakery, Home Kitchen, Other.
- Logo            — image dropzone (square preview), local path for now.
- Cover image     — image dropzone (wide 16:9 preview), optional.
- Tagline / description — textarea (max 160 chars, show counter).
- Timezone *      — searchable select, auto-detect default (e.g. Asia/Karachi).
- Currency *      — select (PKR, USD, INR, AED, GBP, EUR…), default PKR; show symbol.
- Languages       — multi-select chips (English, Urdu, Hindi, Arabic…), default English.
SECTION "Contact & info" (shown to customers / used by the assistant):
- Helpline phone  — tel input with country code.
- Public email    — email.
- Address         — textarea.
- Google Maps link — url, optional.

VALIDATION (zod): name & type & timezone & currency required. Continue disabled until valid.
```

---

## §C2 — Step 2: Business Hours & Availability  → writes `business_hours` + `business.accepting_orders`

```
Build the "Business Hours" onboarding step. Heading: "When are you open?". Subtitle: "Customers can only
order during open hours."

LAYOUT: a weekly schedule list, one row per day (Monday→Sunday).
PER-DAY ROW:
- Day label + an "Open / Closed" Switch.
- When open: an "Open time" and "Close time" time-picker pair.
- "+ Add time slot" to add a second slot per day (e.g. lunch 12–3, dinner 7–11). Removable rows.
QUICK ACTIONS (top): "Apply Monday's hours to all days" button; "Mark weekend closed".
TOP CARD: a master Switch "Accepting orders now" (default ON) with helper text: "Turn off to instantly
pause new orders even during open hours — useful when the kitchen is busy."

VALIDATION: if a day is open, both times required and close > open. Timezone (from step 1) shown read-only.
```

---

## §C3 — Step 3: Fulfillment & Delivery  → writes `business` settings + `delivery_zone`

```
Build the "Fulfillment & Delivery" onboarding step. Heading: "How do customers get their food?"

LAYOUT: top = fulfillment toggles + order settings; below = delivery zones table (only visible if
Delivery is enabled).

FULFILLMENT TOGGLES (Switches): Delivery (default ON), Pickup (default ON), Dine-in (optional, default OFF).
ORDER SETTINGS (grid):
- Minimum order amount — currency input (uses business currency), default 0.
- Default prep time    — number input, minutes, default 30.
- Packaging fee        — currency input, optional, default 0.
DELIVERY ZONES (repeatable rows; "+ Add zone"):
- Zone name *      — text, placeholder "e.g. Gulshan, DHA Phase 5".
- Delivery fee *   — currency input.
- Min order        — currency input, optional (overrides global).
- ETA (minutes)    — number, optional.
- Active toggle + remove (trash) button per row.
EMPTY STATE for zones: "Add the areas you deliver to and the fee for each."

VALIDATION: at least one of Delivery/Pickup must be ON. If Delivery ON, require ≥1 zone with name + fee.
```

---

## §C4 — Step 4: Menu Builder  → writes `category`, `product`, `product_option_group`, `product_option_item`

```
Build the "Menu" onboarding step — the most important screen. Heading: "Build your menu".

LAYOUT (desktop): left column = category list (reorderable, ~260px); main area = dishes in the selected
category as a responsive card grid. Top-right: "Add category" and "Add dish" buttons. Provide a
"✨ Seed sample menu" button for empty state so users see value instantly.

CATEGORY (inline add / edit): name, drag-to-reorder, active toggle, delete.

DISH CARD: photo thumbnail, name, price, availability dot, tag badges, edit/delete. "Available" Switch
on the card for quick sold-out toggling.

ADD/EDIT DISH (open in a Drawer/Dialog):
- Photo        — image dropzone (local path for now).
- Name *       — text.
- Description  — textarea.
- Price *      — currency input (business currency).
- Category *   — select (prefilled with current).
- Available    — Switch, default ON.
- Tags         — multi-select chips: veg, vegan, halal, spicy, bestseller, gluten-free.
- Prep time    — number minutes, optional (overrides default).
- MODIFIERS (collapsible "Add options", repeatable option GROUPS):
    Group: name (e.g. "Size", "Add-ons"), type = Single/Multi (radio), Required (switch),
           min/max select (numbers, for multi).
    Items within group (repeatable): item name (e.g. "Large", "Extra cheese") + price delta
           (currency, can be 0), default toggle, remove.
    "+ Add option group", "+ Add item".

EMPTY STATE: "No dishes yet — add your first dish or seed a sample menu."
VALIDATION: dish needs name + price + category; option group with type=single & required should have ≥2 items.
```

---

## §C5 — Step 5: AI Assistant Setup  → writes `agent_config`  *(generate now, wire later)*

```
Build the "AI Assistant" onboarding step. Heading: "Set up your WhatsApp assistant". Add a small badge
"You can finish this later". Subtitle: "Customize how your AI replies to customers on WhatsApp."

LAYOUT: two columns — left = settings form; right = a LIVE WhatsApp-style chat PREVIEW (green bubbles)
that updates as the user types the greeting/tone, showing a sample customer message + the assistant's
greeting. (Preview is illustrative only.)

FIELDS:
- Greeting message — textarea, prefilled default: "Hi! Welcome to {business_name} 👋 I can show you our
  menu and take your order. What would you like today?"
- Tone             — select: Friendly (default), Professional, Playful.
- Languages        — multi-select chips (default from step 1).
- Order approval   — RadioGroup: "Auto-confirm orders" vs "I'll approve each order" (default: approve).
- Upsell suggestions — Switch (default ON), helper "Let the assistant suggest add-ons like drinks/fries."
- Human handoff number — tel, helper "Where to route customers who ask to talk to a person."
- FAQ / extra info — textarea, helper "Anything the assistant should know: parking, catering, payment
  methods, etc."

NOTE: this step is optional/skippable. Save to agent_config.
```

---

## §C6 — Step 6: Connect WhatsApp  → writes `whatsapp_channel`  *(stub now)*

```
Build the "Connect WhatsApp" onboarding step. Heading: "Connect your WhatsApp number". Mark it skippable
("Skip for now").

LAYOUT: centered card with an illustration, a primary "Connect WhatsApp" button (for now show it as
"Coming soon" / disabled with a tooltip, since real connection is added later), and a "Skip for now" link.

IMPORTANT INFO CALLOUT (amber): "⚠️ The number you connect can't also be used in the normal WhatsApp or
WhatsApp Business app — it gets dedicated to the API. We recommend using a separate/spare number for your
bot." Include a "Learn more" link.

ADVANCED / DEVELOPER (collapsible, for testing now): a section "Use a test number (developer)" with:
- Phone number ID — text.
- Access token    — password input (helper: stored encrypted).
- Display name    — text.
- "Save test connection" button.
Show a connection STATUS pill: Disconnected / Pending / Connected / Error.

NOTE: real self-serve "Embedded Signup" replaces the disabled button later; keep this screen's layout.
```

---

## §C7 — Step 7: Review & Go Live  → sets `business.status = 'active'`

```
Build the "Review & Go Live" final onboarding step. Heading: "You're almost ready 🎉".

LAYOUT: a checklist summary card listing each setup area with a status (✓ done / ⚠ incomplete) and an
"Edit" link that jumps back to that step:
- Business profile (name, type, contact)
- Hours (X days configured)
- Fulfillment (delivery/pickup, X zones)
- Menu (X categories, Y dishes)
- AI assistant (configured / skipped)
- WhatsApp (connected / skipped)

PRIMARY ACTION: a big green "Go live →" button. Required-to-go-live: business profile + ≥1 dish.
If requirements unmet, disable "Go live" and show what's missing.
SECONDARY: "I'll finish later" → go to dashboard with status still 'onboarding'.

ON SUCCESS: confetti + success state "Your store is live!" then redirect to /dashboard. Set
business.status = 'active'.
```

---

## §D — Generation order & tips
1. Generate **§B shell** first, then drop each step's body into it.
2. Generate steps **1 → 4** first (these are functional now); stub **5 → 6**; finish with **7**.
3. After generating, wire each form's submit to your FastAPI endpoints (`POST/PATCH /businesses`,
   `/categories`, `/products`, `/delivery-zones`, `/business-hours`, `/agent-config`,
   `/whatsapp-channel`) — all tenant-scoped.
4. Keep field names matching `08-database-schema.md` columns to avoid mapping bugs.
```
