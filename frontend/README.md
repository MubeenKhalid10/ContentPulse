# ContentPulse — web app

Next.js 16 (App Router) + TypeScript, Tailwind v4, shadcn/ui (Base UI), TanStack Query,
React Hook Form + Zod. See the [root README](../README.md) for the full setup.

```bash
npm install
npm run dev          # http://localhost:3000 (API must be on :8000, or set API_URL)
npm run lint
npm run typecheck
npm run test:e2e     # Playwright; needs API + web running. First run: npx playwright install chromium
```

## How it talks to the API

`next.config.ts` rewrites `/api/v1/*` to `API_URL`, so the browser only ever calls this
origin and the backend's httpOnly `cp_session` cookie is first-party. `src/proxy.ts` does an
optimistic redirect to `/login` when the cookie is missing; the backend verifies the token on
every request and enforces all permissions — the UI only hides controls.

## Layout

```
src/
├── app/
│   ├── (auth)/      login, register, invite/[token], onboarding
│   └── (app)/       dashboard, organization/*, team, settings, activity (inside the app shell)
├── components/      feature components + ui/ (shadcn)
├── hooks/           TanStack Query hooks, keyed by active organization
├── lib/             api client, auth hooks, formatting, option lists
├── schemas/         Zod form schemas
└── types/           API types mirroring backend schemas
```
