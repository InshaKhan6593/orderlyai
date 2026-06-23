<!-- BEGIN:nextjs-agent-rules -->
# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` before writing any code. Heed deprecation notices.
<!-- END:nextjs-agent-rules -->

# AGENTS.md — OrderlyAI Frontend

Frontend-specific working rules for `web/`. Also read the root `../AGENTS.md` for product context,
multi-tenancy rules, backend contracts, and roadmap/design-doc locations.

## Current State

- Stack: Next.js 16.2.9 App Router, React 19.2, TypeScript, Tailwind v4, shadcn/ui Base UI, lucide icons,
  pnpm.
- Implemented routes: `/`, `/login`, `/signup`, `/onboarding`, `/onboarding/business-profile`,
  `/onboarding/hours`, `/onboarding/fulfillment`, `/onboarding/menu`, and `/onboarding/assistant`.
- Auth, sign-in/sign-up, and onboarding steps 1-6 are built.
- Business profile, fulfillment/delivery zones, the menu builder, and AI assistant config are wired to the FastAPI API.
- Business hours are currently client-side only. Persist them to the API when the ordering/agent flow needs
  authoritative hours.
- The menu step now supports categories, products, reusable modifier templates, dish-specific groups,
  per-dish option availability/defaults/prices, template management, sample seeding, and the drawer from
  `screens/05-onboarding-menu-modifiers-drawer.png`. The AI assistant step stores English-only config without
  tone or auto-approval fields. Onboarding steps 7-8, dashboard menu reuse, dashboard screens, and WhatsApp
  connection are still pending.

## Local Development

```bash
cd web
pnpm install
cp .env.example .env.local     # NEXT_PUBLIC_API_URL defaults to http://localhost:8000/api/v1
pnpm dev                       # http://localhost:3000
```

Use `NEXT_PUBLIC_API_URL` for the backend base URL, including `/api/v1`. Do not hardcode API origins in
components.

## Checks

```bash
cd web
pnpm test
pnpm build
pnpm lint
```

- Run `pnpm test` for helper/form/onboarding changes.
- Run `pnpm build` before claiming a route, type, or Next.js integration is working.
- Run `pnpm lint` when changing component code or imports.

## Frontend Rules

1. **Keep onboarding UI consistent.** For onboarding steps, reuse
   `src/components/onboarding/onboarding-step-ui.tsx` (`OnboardingStepHeader`, `OnboardingCard`, and shared
   shell width/spacing constants) plus `OnboardingShell`.
2. **Use the existing shadcn/Base UI components first.** Check `src/components/ui/` and `components.json`
   before writing custom primitives.
3. **Use shadcn form composition.** Prefer `FieldGroup`, `Field`, `FieldLabel`, `FieldError`,
   `InputGroup`, `ToggleGroup`, `Select`/`SelectGroup`, `Switch`, `Table`, `Badge`, and `Separator` over
   hand-rolled markup.
4. **Use semantic theme tokens.** Prefer `bg-background`, `text-muted-foreground`, `border-border`,
   `bg-primary`, etc. Avoid raw color utilities unless matching an existing screen-specific design token.
5. **Use lucide icons in buttons with `data-icon`.** Do not manually size icons inside shadcn buttons unless
   an existing component pattern does it.
6. **Do not add new design systems or styling frameworks.** Tailwind v4 + shadcn/ui is the frontend stack.
7. **Do not bypass the API contract.** Tenant-owned data comes from backend routes scoped under
   `/businesses/{business_id}/...`; never trust or invent client-side totals/prices for ordering flows.
8. **Keep auth limitations explicit.** Tokens are currently stored in web storage for scaffold/testability.
   Do not treat this as production-hardening; future auth hardening should move toward httpOnly cookies and
   refresh rotation.

## shadcn Notes

- `components.json` uses `style: base-nova`, Base UI, Tailwind v4, and lucide.
- Add components from `web/` with `pnpm dlx shadcn@latest add <component>`.
- After adding or updating a component, read the generated file and keep imports aligned with the aliases in
  `components.json`.

## Testing Notes

- Vitest tests live beside the code in `src/**/*.test.ts(x)`.
- Current coverage includes onboarding progress, business profile payloads, business-hours helpers/layout,
  and fulfillment validation/persistence helpers.
- Add tests for form payload mapping, validation, resume/progress behavior, and any new API helper that
  translates frontend state to backend field names.
