// Talks to the PennyWise coach backend (FastAPI, proxied at /api by Vite).
// The website keeps money in pence; the backend works in pounds.

const toPounds = (pence) => Math.round(Math.abs(Number(pence) || 0)) / 100;

/** The website's own data, sent with each request so the coach sees what's on screen. */
export function websiteData({ transactions = [], goals = [] }, excludeTransactionId) {
  return {
    transactions: transactions
      .filter((t) => t.id !== excludeTransactionId && (t.type === 'income' || t.type === 'expense') && /^\d{4}-\d{2}-\d{2}/.test(t.date || ''))
      .slice(-5000)
      .map((t) => ({
        amount: toPounds(t.amount),
        type: t.type,
        category: (t.category || 'Other').slice(0, 50),
        name: (t.name || '').slice(0, 200),
        date: t.date.slice(0, 10),
      })),
    goals: goals.slice(0, 200).map((g) => ({ name: (g.name || '').slice(0, 200), target: toPounds(g.target), saved: toPounds(g.saved) })),
  };
}

async function request(path, options) {
  let res;
  try {
    res = await fetch(`/api${path}`, options);
  } catch {
    throw new Error("Can't reach the PennyWise coach. Is the backend running on port 8000?");
  }
  let data;
  try {
    data = await res.json();
  } catch {
    throw new Error("The PennyWise coach isn't responding. Start the backend on port 8000 and try again.");
  }
  if (!res.ok) {
    const detail = typeof data.detail === 'string' ? data.detail : data.detail?.[0]?.msg;
    throw new Error(detail || `Something went wrong (${res.status}).`);
  }
  return data;
}

export const coachApi = {
  post: (path, body) => request(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }),
  get: (path) => request(path),
};

export const thisMonth = () => new Date().toISOString().slice(0, 7);

const pounds = (pence) => (pence == null || pence === '' ? undefined : Math.round(Number(pence) || 0) / 100);

/** The user's PennyWise profile in the shape the backend expects (pounds, snake_case). */
export function profilePayload(profile, { transactions = [], accounts = [] } = {}, excludeTransactionId) {
  if (!profile) return undefined;
  // Money in their accounts right now = opening balances + every transaction since.
  const balancePence =
    accounts.reduce((s, a) => s + (Number(a.openingBalance) || 0), 0) +
    transactions
      .filter((t) => t.id !== excludeTransactionId)
      .reduce((s, t) => s + (t.type === 'income' ? Number(t.amount) || 0 : t.type === 'expense' ? -(Number(t.amount) || 0) : 0), 0);
  return {
    monthly_income: pounds(profile.monthlyIncome),
    monthly_rent: pounds(profile.monthlyRent),
    monthly_bills: pounds(profile.monthlyBills),
    monthly_everyday: pounds(profile.monthlyEveryday),
    savings: pounds(profile.savings),
    current_balance: Math.max(-1_000_000, balancePence / 100),
    essentials_paid_this_month: profile.essentialsPaidMonth === thisMonth(),
    about: {
      name: (profile.name || '').slice(0, 60),
      persona: profile.persona || 'other',
      income_type: profile.incomeType === 'irregular' ? 'irregular' : 'fixed',
      home_country: (profile.homeCountry || '').slice(0, 60),
      goal: (profile.goal || '').slice(0, 200),
      facts: (profile.facts || []).slice(-40).map((f) => String(f).slice(0, 300)),
    },
  };
}

/** Everything the bots need about this user, built from the website's state. */
export function coachContext(app, excludeTransactionId) {
  return {
    data: websiteData(app, excludeTransactionId),
    profile: profilePayload(app.profile, app, excludeTransactionId),
  };
}

/** Store facts the bots learned (e.g. "On a Student visa") in the profile. */
export function rememberFacts(setProfile, facts) {
  if (!facts?.length) return;
  setProfile((p) => (p ? { ...p, facts: [...(p.facts || []), ...facts.filter((f) => !(p.facts || []).includes(f))].slice(-40) } : p));
}
