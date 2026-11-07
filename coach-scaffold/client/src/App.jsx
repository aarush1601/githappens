import { useMemo, useState } from "react";
import { askCoach, submitPurchase } from "./lib/api";
import { calculateTrip, evaluatePurchase, getDayCheck } from "./lib/rulesEngine";
import profiles from "./data/profiles.json";
import transactions from "./data/transactions.json";

const money = (value, currency = "GBP") => new Intl.NumberFormat("en-GB", {
  style: "currency",
  currency,
  maximumFractionDigits: 0
}).format(value);

function Metric({ label, value, detail }) {
  return <div className="metric"><span>{label}</span><strong>{value}</strong><small>{detail}</small></div>;
}

export default function App() {
  const [selectedId, setSelectedId] = useState("international-student");
  const [user, setUser] = useState(null);
  const [consent, setConsent] = useState(false);
  const [tab, setTab] = useState("Overview");
  const [trip, setTrip] = useState({
    destination: "Toronto",
    purpose: "Study Abroad",
    oneTimeCosts: 1450,
    monthlyCosts: 1200,
    months: 6
  });
  const [purchase, setPurchase] = useState({ item: "", amount: "", category: "flexible" });
  const [purchaseFeedback, setPurchaseFeedback] = useState(null);
  const [chat, setChat] = useState("");
  const [reply, setReply] = useState(null);
  const [loading, setLoading] = useState(false);
  const [synced, setSynced] = useState(false);

  const profile = profiles.find((item) => item.id === selectedId) ?? profiles[0];
  const day = useMemo(() => getDayCheck(profile), [profile]);
  const purchaseResult = useMemo(() => evaluatePurchase({
    ...purchase,
    balance: profile.balance,
    billsDue: profile.billsDue,
    safeToSpend: day.safeToSpend
  }), [purchase, profile, day.safeToSpend]);
  const tripResult = useMemo(() => calculateTrip({
    ...trip,
    balance: profile.balance,
    monthlyIncome: profile.monthlyIncome,
    monthlyCosts: profile.monthlyCosts
  }), [trip, profile]);
  const currency = profile.currency;

  if (!user) {
    return <main className="auth">
      <div className="brand-mark">H</div>
      <p className="eyebrow">HARBOR MONEY COACH</p>
      <h1>A calmer way to settle in.</h1>
      <p className="lede">A private, practical guide for international students and anyone building confidence with money.</p>
      <div className="card onboarding">
        <h2>Choose a starting point</h2>
        <p>Every profile is editable. This demo uses synthetic data only and never connects to a bank.</p>
        <label>Quick start profile
          <select value={selectedId} onChange={(event) => setSelectedId(event.target.value)}>
            {profiles.map((item) => <option value={item.id} key={item.id}>{item.profileLabel}</option>)}
          </select>
        </label>
        <label className="consent"><input type="checkbox" checked={consent} onChange={(event) => setConsent(event.target.checked)} /> You control what is shared. I understand this is educational guidance, not regulated financial advice.</label>
        <button disabled={!consent} onClick={() => setUser(profile)}>Enter your dashboard <span>→</span></button>
      </div>
      <small className="muted">Synthetic demo data · no credit approval · no payday loans</small>
    </main>;
  }

  const updateTrip = (key, value) => setTrip((current) => ({ ...current, [key]: key === "destination" || key === "purpose" ? value : Number(value) }));
  async function sendCoach() {
    if (!chat.trim()) return;
    setLoading(true);
    try {
      setReply(await askCoach({ message: chat, profile, facts: { day, trip: tripResult, purchase: purchaseResult }, consent: true }));
    } catch (error) {
      setReply({ answer: error.message, actions: [] });
    } finally {
      setLoading(false);
    }
  }

  async function checkPurchase(event) {
    event.preventDefault();
    setPurchaseFeedback(null);
    if (!purchase.item.trim() || Number(purchase.amount) <= 0) {
      setPurchaseFeedback({ type: "error", message: "Add an item and an amount in pounds first." });
      return;
    }
    try {
      const result = await submitPurchase({
        item: purchase.item.trim(),
        amount: Number(purchase.amount),
        category: purchase.category,
        currency: "GBP",
        facts: purchaseResult
      });
      setPurchaseFeedback({ type: "success", message: result.message });
    } catch (error) {
      setPurchaseFeedback({ type: "error", message: error.message });
    }
  }

  return <div className="shell">
    <aside>
      <div className="logo"><span>H</span> harbor</div>
      <div className="profile-mini"><div className="avatar">{profile.name.split(" ").map((part) => part[0]).join("")}</div><div><b>{profile.name}</b><small>{profile.profileLabel}</small></div></div>
      <nav>{["Overview", "Day check", "Trip simulator", "Coach"].map((item) => <button className={tab === item ? "active" : ""} onClick={() => setTab(item)} key={item}><span>{item === "Overview" ? "◈" : item === "Day check" ? "◷" : item === "Trip simulator" ? "⌁" : "✦"}</span>{item}</button>)}</nav>
      <div className="aside-note"><b>Small steps count.</b><p>Check in before your next big decision.</p></div>
    </aside>
    <main className="dashboard">
      <header><div><p className="eyebrow">MONEY COACH · SYNTHETIC DATA</p><h1>Good morning, {profile.name.split(" ")[0]} <span>✦</span></h1></div><button className="icon-btn" aria-label="Privacy information">◎</button></header>
      {tab === "Overview" && <><section className="hero-grid"><div className="card balance-card"><div className="card-top"><span>AVAILABLE BALANCE</span><span className="status-dot">● Healthy</span></div><strong>{money(profile.balance, currency)}</strong><p>Across your demo accounts · nothing is connected</p><div className="balance-line"><span style={{ width: "72%" }} /></div><small>72% of your monthly safety target</small></div><div className="card day-card"><div className="card-top"><span>YOUR DAY CHECK</span><span>Today</span></div><h2>{money(day.safeToSpend, currency)}</h2><p>safe to spend after bills and essentials</p><button className="text-btn" onClick={() => setTab("Day check")}>See the breakdown →</button></div></section><section className="section-head"><div><p className="eyebrow">MONEY SNAPSHOT</p><h2>Make the next decision easier.</h2></div><span className="updated">{profile.incomeFrequency}</span></section><section className="metrics"><Metric label="Monthly inflow" value={money(profile.monthlyIncome, currency)} detail={profile.incomeFrequency} /><Metric label="Monthly essentials" value={money(profile.monthlyCosts, currency)} detail="Rent, food, transport" /><Metric label="Safety buffer" value={money(profile.balance - profile.monthlyCosts, currency)} detail="Protected before flexible spend" /></section><section className="lower-grid"><div className="card transactions"><div className="card-top"><b>Recent activity</b><button className="text-btn">View all</button></div>{transactions.map((transaction) => <div className="transaction" key={transaction.merchant}><div className="transaction-icon">{transaction.category[0]}</div><div><b>{transaction.merchant}</b><small>{transaction.category} · {transaction.date}</small></div><strong>−{money(transaction.amount, currency)}</strong></div>)}</div><div className="card nudge"><span className="spark">✦</span><p className="eyebrow">A NOTE FROM YOUR COACH</p><h3>Your essentials come first.</h3><p>Use the simulator before committing to flights, tuition, deposits, or sending money home.</p><button onClick={() => setTab("Trip simulator")}>Plan it safely →</button></div></section></>}
      {tab === "Day check" && <section className="page"><p className="eyebrow">YOUR DAY CHECK</p><h2>How much can you spend today?</h2><div className="card big-number"><span>SAFE TO SPEND</span><strong>{money(day.safeToSpend, currency)}</strong><p>After setting aside {money(profile.billsDue, currency)} in upcoming bills and {money(day.essentialsReserve, currency)} for essentials.</p></div><div className="card checklist"><h3>Should I buy this?</h3><form className="purchase-row" onSubmit={checkPurchase}><input required value={purchase.item} onChange={(event) => setPurchase({ ...purchase, item: event.target.value })} placeholder="e.g. new trainers" aria-label="Item" /><input required min="0.01" step="0.01" type="number" value={purchase.amount} onChange={(event) => setPurchase({ ...purchase, amount: event.target.value })} placeholder="£ amount" aria-label="Amount in pounds" /><select value={purchase.category} onChange={(event) => setPurchase({ ...purchase, category: event.target.value })}><option value="flexible">Flexible</option><option value="food">Food</option><option value="transport">Transport</option><option value="study">Study</option></select><button type="submit" className="check-button">Check purchase</button></form>{purchaseFeedback && <p className={`purchase-feedback ${purchaseFeedback.type}`}>{purchaseFeedback.message}</p>}{purchase.item && Number(purchase.amount) > 0 && <><p className={`inline-verdict ${purchaseResult.verdict.toLowerCase().replaceAll(" ", "-")}`}><b>{purchaseResult.verdict}</b> · {purchaseResult.reason}</p><p>{purchaseResult.alternative}</p><p>After buying, today's planned amount would be {money(purchaseResult.impact, currency)}.</p></>}</div></section>}
      {tab === "Trip simulator" && <section className="page"><p className="eyebrow">INTERNATIONAL TRIP & STUDY ABROAD</p><h2>Can your plan travel with you?</h2><p className="lede">Include one-time costs, monthly living costs, a 10% currency cushion, and inflation for stays longer than six months.</p><div className="simulator-grid"><div className="card form-card"><label>Destination city<input value={trip.destination} onChange={(event) => updateTrip("destination", event.target.value)} /><small>Flights, visa and local costs vary by city.</small></label><label>Purpose<select value={trip.purpose} onChange={(event) => updateTrip("purpose", event.target.value)}><option>Study Abroad</option><option>Travel</option><option>Nomad</option></select></label><label>One-time upfront costs<input type="number" value={trip.oneTimeCosts} onChange={(event) => updateTrip("oneTimeCosts", event.target.value)} /><small>Visa, flights, deposit, health insurance.</small></label><label>Monthly living costs<input type="number" value={trip.monthlyCosts} onChange={(event) => updateTrip("monthlyCosts", event.target.value)} /><small>Rent, food and transit.</small></label><label>Stay duration<input type="range" min="1" max="24" value={trip.months} onChange={(event) => updateTrip("months", event.target.value)} /><b>{trip.months} months</b></label><button className="sync-button" onClick={() => setSynced(true)}>Sync target savings to today's safe-to-spend →</button>{synced && <small className="sync-note">Synced: keep today's limit at {money(Math.max(0, day.safeToSpend - tripResult.total / Math.max(1, trip.months * 30)), currency)} while you save.</small>}</div><div className={`card verdict ${tripResult.verdict.toLowerCase().replaceAll(" ","-")}`}><span className="verdict-label">RECOMMENDATION FOR {tripResult.destination.toUpperCase()}</span><strong>{tripResult.verdict}</strong><p>{tripResult.reason}</p><div className="breakdown"><div><span>One-time upfront</span><b>{money(tripResult.oneTime, currency)}</b></div><div><span>Inflation-adjusted monthly</span><b>{money(tripResult.inflatedMonthly, currency)}</b></div><div><span>10% currency cushion</span><b>{money(tripResult.cushion, currency)}</b></div><div><span>Total plan</span><b>{money(tripResult.total, currency)}</b></div><div><span>Buffer after plan</span><b>{money(tripResult.afterTrip, currency)}</b></div></div><small>{tripResult.verdict === "SKIP FOR NOW" ? `Try delaying about ${tripResult.suggestedDelayMonths} month(s), shortening the stay, or choosing a cheaper housing tier.` : `Based on your synthetic balance, income and ${tripResult.horizon}-month ${tripResult.purpose.toLowerCase()} plan.`}</small></div></div></section>}
      {tab === "Coach" && <section className="page"><p className="eyebrow">FINANCIAL COACH</p><h2>Ask a question. Get a next step.</h2><div className="card coach"><div className="coach-message"><span className="coach-avatar">✦</span><p>{reply?.answer || "I explain the numbers already calculated by Harbor. Try asking about rent, sending money home, or your next trip."}</p></div>{reply?.actions?.map((action) => <button className="action" key={action}>{action} →</button>)}<div className="composer"><input value={chat} onChange={(event) => setChat(event.target.value)} onKeyDown={(event) => event.key === "Enter" && sendCoach()} placeholder="e.g. Can I afford a weekend trip?" /><button onClick={sendCoach} disabled={loading}>{loading ? "…" : "Send"}</button></div><small className="muted">You control what is shared. Guidance, not regulated financial advice. We never approve credit.</small></div></section>}
      <footer>Harbor uses synthetic data only. Guidance, not regulated financial advice. We never approve credit.</footer>
    </main>
  </div>;
}
