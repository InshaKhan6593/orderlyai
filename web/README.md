# OrderlyAI Web

Next.js 16 frontend for the OrderlyAI owner dashboard and onboarding flow.

## Run locally

```bash
pnpm install
pnpm dev
```

The app runs at `http://localhost:3000` and expects the API at
`http://localhost:8000/api/v1` unless `NEXT_PUBLIC_API_URL` overrides it.

## Checks

```bash
pnpm lint
pnpm build
```

Current routes:

- `/` and `/login`: sign in
- `/signup`: account registration
- `/onboarding`: onboarding welcome screen
- `/onboarding/business-profile`: business profile
- `/onboarding/hours`: business hours
- `/onboarding/fulfillment`: fulfillment and delivery
- `/onboarding/menu`: backend-wired menu builder and modifier drawer
