const clamp = (n, min, max) => Math.min(max, Math.max(min, n));
const numeric = (value) => Math.max(0, Number(value) || 0);

export function getDayCheck({ balance, billsDue = 0, monthlyCosts = 0, dailySpend = 0, daysRemaining = 30 }) {
  const essentialsReserve = numeric(monthlyCosts) / clamp(Number(daysRemaining) || 30, 1, 31);
  const safeToSpend = Math.max(0, numeric(balance) - numeric(billsDue) - essentialsReserve - numeric(dailySpend));
  return {
    safeToSpend,
    essentialsReserve,
    status: safeToSpend > 25 ? "steady" : safeToSpend > 0 ? "tight" : "pause"
  };
}

export function evaluatePurchase({ balance, billsDue = 0, safeToSpend, amount, category = "flexible" }) {
  const price = numeric(amount);
  const availableToday = safeToSpend === undefined
    ? Math.max(0, numeric(balance) - numeric(billsDue))
    : numeric(safeToSpend);
  const categoryIsEssential = ["rent", "food", "transport", "health", "study"].includes(category.toLowerCase());
  const ratio = availableToday === 0 ? Infinity : price / availableToday;
  const verdict = categoryIsEssential && price <= availableToday * 1.25
    ? "GO"
    : ratio <= 0.35
      ? "GO"
      : ratio <= 0.75
        ? "THINK TWICE"
        : "SKIP FOR NOW";
  const saving = Math.round(price * 0.35);
  return {
    amount: price,
    verdict,
    impact: Math.round(Math.max(0, availableToday - price)),
    reason: verdict === "GO"
      ? "This fits within today's planned spending."
      : verdict === "THINK TWICE"
        ? "This uses a large share of today's flexible budget. Check your upcoming bills first."
        : "This would use most of today's flexible budget and put your buffer under pressure.",
    alternative: categoryIsEssential ? "Compare a lower-cost option before paying." : `Try a second-hand or lower-cost option and save about £${saving}.`
  };
}

export function calculateTrip({
  balance,
  monthlyIncome,
  monthlyCosts = 0,
  oneTimeCosts = 0,
  months,
  destination = "your destination",
  purpose = "Travel",
  inflation = 0.045,
  currencyCushionRate = 0.10
}) {
  const horizon = clamp(Number(months) || 1, 1, 60);
  const oneTime = numeric(oneTimeCosts);
  const monthly = numeric(monthlyCosts);
  const inflationMonths = Math.max(0, horizon - 6);
  const inflationMultiplier = Math.pow(1 + inflation, inflationMonths / 12);
  const inflatedMonthly = monthly * inflationMultiplier;
  const recurring = inflatedMonthly * horizon;
  const subtotal = oneTime + recurring;
  const cushion = subtotal * currencyCushionRate;
  const total = subtotal + cushion;
  const available = numeric(balance) + numeric(monthlyIncome) * horizon;
  const safetyBuffer = Math.max(250, numeric(monthlyCosts) * 1.5);
  const afterTrip = available - total;
  const flexibleBudget = Math.max(0, numeric(monthlyIncome) - numeric(monthlyCosts));
  const verdict = afterTrip >= safetyBuffer && total <= flexibleBudget * horizon + numeric(balance) * 0.35
    ? "GO"
    : afterTrip >= 0 && afterTrip >= safetyBuffer * 0.5
      ? "THINK TWICE"
      : "SKIP FOR NOW";
  return {
    destination, purpose, horizon, oneTime, monthly, inflationMultiplier, inflatedMonthly,
    recurring, subtotal, cushion, currencyCushionRate, total, available, safetyBuffer,
    afterTrip, verdict,
    suggestedDelayMonths: verdict === "SKIP FOR NOW" ? Math.max(1, Math.ceil((total - numeric(balance)) / Math.max(1, numeric(monthlyIncome) - numeric(monthlyCosts)))) : 0,
    reason: verdict === "GO"
      ? `This ${purpose.toLowerCase()} plan keeps your safety buffer intact.`
      : verdict === "THINK TWICE"
        ? "This is possible, but it needs a tighter discretionary budget or cheaper housing."
        : "This plan would drain your rent buffer or require debt. Consider delaying or reducing housing and trip length."
  };
}