# Harbor — International Student Money Coach

Harbor is a synthetic-data end-to-end vertical slice for international student onboarding, daily money checks, trip affordability, and a structured financial coach API.

## Run locally

```bash
cd client && npm install && npm run dev
cd ../server && npm install && npm start
```

The Vite dev server proxies `/api` to Express on port `3001`. The production client is served by Express after `npm run build` in `client`.

## Included

- Consent/disclaimer onboarding using synthetic profile and transaction data.
- Quick-start profile picker for international students, gig workers, single parents, pensioners, and new migrants.
- Deterministic `rulesEngine` day-check, purchase verdict, and trip calculations; the API only explains supplied facts.
- International trip/study-abroad simulator with destination, purpose, one-time costs, monthly costs, 10% currency cushion, and inflation after six months.
- GO / THINK TWICE / SKIP FOR NOW verdicts, delay/cheaper-housing guidance, and budget-sync affordance.
- "Should I buy this?" traffic-light check with a cheaper/greener alternative.
- Purchase checks submit through `POST /api/purchase-verdict`; deterministic facts come from `rulesEngine.js` and the server validates the structured response.
- Validated `POST /api/coach` JSON endpoint with structured actions, consent enforcement, synthetic-data marker, and safety disclaimer.
- Provider-agnostic `server/coachProvider.js` adapter with a deterministic mock implementation; future providers must implement the same `{ answer, actions, provider }` contract.

All seed profiles, transactions, inputs, calculations, and displayed amounts use GBP/£.

Run targeted checks with:

```bash
cd client && npm test
cd ../server && npm test
```

The current coach provider is a deterministic local mock. It receives the user's message and calculated facts server-side, returns structured plain-English guidance, and does not call an external AI service. A Google AI Studio key is therefore not used by this scaffold; if a real provider is added later, its key must remain server-side and the deterministic GBP facts must remain the source of truth. The reserved provider env vars are placeholders only and are intentionally unused until a user-supplied adapter is reviewed and wired.