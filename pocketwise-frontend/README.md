# Pocketwise

A beginner-friendly, frontend-only personal finance app built with React, JavaScript and Vite. The app currently runs on local browser data and includes API service modules ready for a future backend.

## Start

```sh
npm install
npm run dev
```

For a production build, run `npm run build` and serve the generated `dist` folder.

## Data and privacy

Sample data is provided on first launch. Transactions, budgets, goals, accounts and preferences are saved in this browser's `localStorage`. This is convenient for a prototype, but it is not encrypted cloud storage or a backup. Use Settings to export/import a JSON backup. Transactions can also be exported as CSV.

Changing the currency changes the display format only. No foreign exchange conversion is performed. There is no login or backend.

## Future API connection

Copy `.env.example` to `.env` and set `VITE_API_BASE_URL` when your API is available. Resource modules live in `src/services/`. No backend endpoints are assumed or contacted while the URL is unset. The current UI uses local state and mock data.
