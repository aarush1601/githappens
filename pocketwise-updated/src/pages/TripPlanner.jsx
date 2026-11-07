import { useEffect, useState } from 'react';
import { Brain, Calendar, Home, Plane, Send, Wallet } from 'lucide-react';
import { useApp } from '../context/AppContext';
import { AFFORD_LABEL, Bubble, RichText, VerdictBadge } from '../features/coach/CoachMessage';
import { coachApi, coachContext, rememberFacts } from '../features/coach/coachApi';

const gbp = (pounds) => new Intl.NumberFormat('en-GB', { style: 'currency', currency: 'GBP' }).format(pounds || 0);
const title = (s) => s.replace(/\b\w/g, (c) => c.toUpperCase());
const stayText = (months) => {
  if (months < 1) { const w = Math.round(months * 4.345 * 2) / 2; return `${w} week${w === 1 ? '' : 's'}`; }
  if (months >= 12 && Number.isInteger(months / 12)) return `${months / 12} year${months === 12 ? '' : 's'}`;
  return `${months} month${months === 1 ? '' : 's'}`;
};
const LABELS = { flights_return: 'Return flights', visa: 'Visa', housing_deposit: 'Housing deposit', health_insurance: 'Health insurance' };

export default function TripPlanner() {
  const app = useApp();
  const { profile, setProfile } = app;
  const [destinations, setDestinations] = useState([]);
  const [form, setForm] = useState({
    destination: 'barcelona', duration_value: '2', duration_unit: 'weeks',
    purpose: profile?.persona === 'international_student' ? 'study' : 'travel', months_until_departure: '3', housing_tier: 'standard',
  });
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [followUps, setFollowUps] = useState([]);
  const [history, setHistory] = useState([]);
  const [question, setQuestion] = useState('');
  const [remembered, setRemembered] = useState([]);

  useEffect(() => {
    coachApi.get('/trip-destinations').then((d) => setDestinations(d.destinations)).catch((e) => setError(e.message));
  }, []);

  const set = (key) => (e) => setForm({ ...form, [key]: e.target.value });
  const learned = (facts) => { if (facts?.length) { rememberFacts(setProfile, facts); setRemembered(facts); } };

  const plan = async (e) => {
    e?.preventDefault();
    setBusy(true); setError(''); setFollowUps([]); setRemembered([]);
    try {
      const body = { ...form, duration_value: Number(form.duration_value), months_until_departure: Number(form.months_until_departure), ...coachContext(app) };
      const data = await coachApi.post('/trip-plan', body);
      setResult(data);
      learned(data.new_facts);
      const asked = `Plan ${form.duration_value} ${form.duration_unit} in ${title(form.destination)} (${form.purpose}), leaving in ${form.months_until_departure} months, ${form.housing_tier} housing.`;
      setHistory([{ role: 'user', content: asked }, { role: 'assistant', content: data.explanation }]);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const ask = async (e) => {
    e.preventDefault();
    const message = question.trim();
    if (!message || busy) return;
    setQuestion(''); setBusy(true); setRemembered([]);
    setFollowUps((f) => [...f, { role: 'user', text: message }]);
    try {
      const data = await coachApi.post('/coach', { message, history, ...coachContext(app) });
      setFollowUps((f) => [...f, { role: 'assistant', text: data.reply, data }]);
      setHistory((h) => [...h, { role: 'user', content: message }, { role: 'assistant', content: data.reply }].slice(-40));
      learned(data.new_facts);
    } catch (err) {
      setFollowUps((f) => [...f, { role: 'error', text: err.message }]);
    } finally {
      setBusy(false);
    }
  };

  const a = result?.affordability;
  const sync = result?.budget_sync;

  return (
    <div className="trip-layout">
      <form className="coach-card trip-form" onSubmit={plan}>
        <div className="coach-card-title"><Plane size={17} /><h3>Plan a trip or a term abroad</h3></div>
        <label className="trip-field"><span>Where to?</span>
          <select value={form.destination} onChange={set('destination')}>
            {destinations.map((d) => <option key={d} value={d}>{title(d)}</option>)}
          </select>
        </label>
        <div className="trip-row">
          <label className="trip-field"><span>How long?</span>
            <input type="number" min="0.5" step="0.5" max="520" value={form.duration_value} onChange={set('duration_value')} required />
          </label>
          <label className="trip-field"><span>&nbsp;</span>
            <select value={form.duration_unit} onChange={set('duration_unit')}><option>weeks</option><option>months</option><option>years</option></select>
          </label>
        </div>
        <div className="trip-field"><span>What for?</span>
          <div className="ob-toggle">
            {['travel', 'study'].map((p) => (
              <button type="button" key={p} className={form.purpose === p ? 'selected' : ''} onClick={() => setForm({ ...form, purpose: p })}>{p === 'travel' ? 'Travel' : 'Study abroad'}</button>
            ))}
          </div>
        </div>
        <label className="trip-field"><span>Leaving in (months)</span>
          <input type="number" min="0" max="120" step="1" value={form.months_until_departure} onChange={set('months_until_departure')} required />
        </label>
        <div className="trip-field"><span>Housing</span>
          <div className="ob-toggle">
            {['standard', 'budget'].map((h) => (
              <button type="button" key={h} className={form.housing_tier === h ? 'selected' : ''} onClick={() => setForm({ ...form, housing_tier: h })}>{title(h)}</button>
            ))}
          </div>
        </div>
        <button className="button button-primary" disabled={busy || !destinations.length}>{busy && !result ? 'Working it out…' : 'Can I afford it?'}</button>
        {error && <div className="ob-error">{error}</div>}
        <p className="coach-muted coach-tiny">Costs are demo estimates in GBP, not live prices.</p>
      </form>

      <section className="trip-results">
        {!result && !busy && (
          <div className="coach-card trip-empty">
            <Plane size={28} />
            <h3>Where would you like to go?</h3>
            <p className="coach-muted">Pick a city and dates. The Trip Planner works out upfront and monthly costs, adds a 10% currency buffer, and checks it against your own budget.</p>
          </div>
        )}
        {busy && !result && <div className="coach-card trip-empty"><p className="coach-muted">Costing your trip with your numbers…</p></div>}
        {result && (
          <>
            <div className="coach-card trip-summary">
              <div>
                <span className="eyebrow">{result.destination} · {stayText(result.stay_months)} · {result.purpose === 'study' ? 'study abroad' : 'travel'}</span>
                <div className="trip-total">{gbp(result.total_cost)}</div>
                <span className="coach-muted">total, including a {gbp(result.currency_buffer_10_percent)} currency buffer</span>
              </div>
              <VerdictBadge verdict={a.verdict} label={AFFORD_LABEL[a.verdict]} prefix="Verdict:" />
            </div>

            <div className="trip-cards">
              <div className="coach-card">
                <div className="coach-card-title"><Wallet size={16} /><h3>One-time upfront</h3></div>
                {Object.entries(result.one_time_upfront).map(([k, v]) => <div className="trip-line" key={k}><span>{LABELS[k] || k}</span><b>{gbp(v)}</b></div>)}
                <div className="trip-line total"><span>Total</span><b>{gbp(result.one_time_upfront_total)}</b></div>
              </div>
              <div className="coach-card">
                <div className="coach-card-title"><Home size={16} /><h3>Monthly living</h3></div>
                {['rent', 'food', 'transit'].map((k) => <div className="trip-line" key={k}><span>{title(k)}</span><b>{gbp(result.monthly_living[k])}</b></div>)}
                <div className="trip-line total"><span>Per month</span><b>{gbp(result.monthly_living.total)}</b></div>
              </div>
              <div className="coach-card">
                <div className="coach-card-title"><Calendar size={16} /><h3>Getting there</h3></div>
                {sync?.leaving_now ? (
                  <div className="trip-line"><span>Needed from savings now</span><b>{gbp(sync.amount_needed_from_savings)}</b></div>
                ) : (
                  <>
                    <div className="trip-line"><span>Save per day</span><b>{gbp(sync.save_per_day)}</b></div>
                    <div className="trip-line"><span>Save per month</span><b>{gbp(sync.save_per_month)}</b></div>
                    <div className="trip-line"><span>Safe to spend each day</span><b>{gbp(sync.safe_to_spend_daily_now)} → {gbp(sync.safe_to_spend_daily_with_trip_saving)}</b></div>
                  </>
                )}
                <div className="trip-line"><span>Savings by departure</span><b>{gbp(a.projected_savings_by_departure)}</b></div>
              </div>
            </div>

            <div className="coach-card trip-explain">
              <div className="coach-card-title"><Plane size={16} /><h3>Trip Planner says</h3></div>
              <RichText text={result.explanation} />
              {followUps.map((m, i) => <Bubble key={i} {...m} />)}
              {busy && <Bubble role="assistant" text="Thinking…" pending />}
              {remembered.length > 0 && <div className="coach-remembered"><Brain size={14} /> I’ll remember: {remembered.join(' · ')}</div>}
              <form className="coach-input" onSubmit={ask}>
                <input value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="Ask a follow-up, e.g. what if I went for 1 week instead?" maxLength={2000} disabled={busy} />
                <button className="button button-primary" disabled={busy || !question.trim()}><Send size={16} /></button>
              </form>
            </div>
          </>
        )}
      </section>
    </div>
  );
}
