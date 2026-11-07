import { useState } from 'react';
import { ArrowRight, Baby, Briefcase, Globe2, GraduationCap, Plane, Sparkles, Sunset, UserRound } from 'lucide-react';
import { useApp } from '../context/AppContext';
import { parseMoney } from '../utils/currency';
import { thisMonth } from '../features/coach/coachApi';

const PERSONAS = [
  ['international_student', 'International student', Globe2],
  ['student', 'UK student', GraduationCap],
  ['gig_worker', 'Gig or shift worker', Briefcase],
  ['single_parent', 'Single parent', Baby],
  ['pensioner', 'Pensioner', Sunset],
  ['new_migrant', 'New to the UK', Plane],
  ['working', 'Working', UserRound],
  ['other', 'Something else', Sparkles],
];

const toInput = (pence) => (pence ? String(pence / 100) : '');

function MoneyField({ label, hint, value, onChange, required }) {
  return (
    <label className="ob-field">
      <span>{label}{required && <i> *</i>}</span>
      <div className="ob-money"><b>£</b><input inputMode="decimal" value={value} onChange={(e) => onChange(e.target.value)} placeholder="0" required={required} /></div>
      {hint && <small>{hint}</small>}
    </label>
  );
}

/** First-visit welcome page. Also used from "Edit my details" (with `editing`). */
export default function Onboarding({ editing = false, onDone }) {
  const { profile, setProfile, setTransactions, setGoals, setAccounts, transactions } = useApp();
  const hasSampleData = transactions.some((t) => /^t\d$/.test(t.id));
  const p = profile || {};
  const [form, setForm] = useState({
    name: p.name || '', persona: p.persona || '', incomeType: p.incomeType || 'fixed', homeCountry: p.homeCountry || '',
    monthlyIncome: toInput(p.monthlyIncome), monthlyRent: toInput(p.monthlyRent), monthlyBills: toInput(p.monthlyBills),
    monthlyEveryday: toInput(p.monthlyEveryday), savings: toInput(p.savings), balance: '', goal: p.goal || '',
    fresh: hasSampleData, essentialsPaid: p.essentialsPaidMonth === thisMonth(),
  });
  const [error, setError] = useState('');
  const set = (key) => (value) => setForm((f) => ({ ...f, [key]: value }));
  const international = form.persona === 'international_student' || form.persona === 'new_migrant';

  const submit = (e) => {
    e.preventDefault();
    if (!form.persona) return setError('Pick the option that fits you best.');
    if (form.monthlyIncome === '') return setError('Add your monthly income (put 0 if you have none right now).');
    const next = {
      ...p,
      name: form.name.trim(), persona: form.persona, incomeType: form.incomeType,
      homeCountry: international ? form.homeCountry.trim() : '', goal: form.goal.trim(),
      monthlyIncome: parseMoney(form.monthlyIncome), monthlyRent: parseMoney(form.monthlyRent),
      monthlyBills: parseMoney(form.monthlyBills), monthlyEveryday: parseMoney(form.monthlyEveryday),
      savings: parseMoney(form.savings), facts: p.facts || [], createdAt: p.createdAt || new Date().toISOString(),
      essentialsPaidMonth: form.essentialsPaid ? thisMonth() : '',
    };
    if (!editing && form.fresh) {
      // Replace the demo data with the user's real starting point.
      setTransactions([]);
      setAccounts([{ id: 'main', name: 'Everyday account', type: 'Bank', openingBalance: parseMoney(form.balance) }]);
      setGoals(next.savings > 0 ? [{ id: 'g-savings', name: next.goal || 'Rainy day fund', target: next.savings, saved: next.savings, icon: '✳' }] : []);
    }
    setProfile(next);
    onDone?.();
  };

  return (
    <div className={editing ? 'ob-embedded' : 'ob-screen'}>
      <form className="ob-card" onSubmit={submit}>
        {!editing && (
          <div className="ob-brand"><span className="brand-mark">p.</span><span>pennywise</span></div>
        )}
        {!editing && <h1>Welcome! Let’s get to know you.</h1>}
        <p className="ob-lead">
          Your money coach and trip planner use this to give advice that fits <em>your</em> life. It stays in this browser.
          You can change it any time, and they’ll ask if they need to know more.
        </p>

        <label className="ob-field"><span>What should we call you?</span>
          <input value={form.name} onChange={(e) => set('name')(e.target.value)} placeholder="First name (optional)" maxLength={60} />
        </label>

        <div className="ob-field"><span>Which fits you best? <i>*</i></span>
          <div className="ob-personas">
            {PERSONAS.map(([id, label, Icon]) => (
              <button type="button" key={id} className={`ob-persona ${form.persona === id ? 'selected' : ''}`} onClick={() => set('persona')(id)}>
                <Icon size={20} strokeWidth={1.8} /><span>{label}</span>
              </button>
            ))}
          </div>
        </div>

        {international && (
          <label className="ob-field"><span>Where are you from?</span>
            <input value={form.homeCountry} onChange={(e) => set('homeCountry')(e.target.value)} placeholder="e.g. India" maxLength={60} />
            <small>Helps with visa rules, sending money home and trips back.</small>
          </label>
        )}

        <div className="ob-grid">
          <MoneyField label="Monthly income" hint="Wages, loan, stipend, benefits or pension" value={form.monthlyIncome} onChange={set('monthlyIncome')} required />
          <div className="ob-field"><span>Is it the same every month?</span>
            <div className="ob-toggle">
              <button type="button" className={form.incomeType === 'fixed' ? 'selected' : ''} onClick={() => set('incomeType')('fixed')}>Yes, fixed</button>
              <button type="button" className={form.incomeType === 'irregular' ? 'selected' : ''} onClick={() => set('incomeType')('irregular')}>No, it varies</button>
            </div>
          </div>
          <MoneyField label="Rent each month" value={form.monthlyRent} onChange={set('monthlyRent')} />
          <MoneyField label="Bills each month" hint="Energy, phone, internet, council tax" value={form.monthlyBills} onChange={set('monthlyBills')} />
          <MoneyField label="Everyday spending each month" hint="Food, travel and the rest, roughly" value={form.monthlyEveryday} onChange={set('monthlyEveryday')} />
          <MoneyField label="Savings" hint="Money put aside, not for this month" value={form.savings} onChange={set('savings')} />
          {!editing && form.fresh && (
            <MoneyField label="Money in your account right now" hint="So your balance is real from day one" value={form.balance} onChange={set('balance')} />
          )}
        </div>

        {(form.monthlyRent || form.monthlyBills) && (
          <label className="ob-check">
            <input type="checkbox" checked={form.essentialsPaid} onChange={(e) => set('essentialsPaid')(e.target.checked)} />
            <span>This month’s rent and bills are already paid <small>(so PennyWise doesn’t hold that money back from your balance)</small></span>
          </label>
        )}

        <label className="ob-field"><span>Anything you’re working towards?</span>
          <input value={form.goal} onChange={(e) => set('goal')(e.target.value)} placeholder="e.g. Flight home in June, a new laptop, getting out of my overdraft" maxLength={200} />
        </label>

        {!editing && hasSampleData && (
          <label className="ob-check">
            <input type="checkbox" checked={form.fresh} onChange={(e) => set('fresh')(e.target.checked)} />
            <span>Start fresh and remove the sample data <small>(recommended; the demo shows a made-up person’s money)</small></span>
          </label>
        )}

        {error && <div className="ob-error">{error}</div>}
        <div className="ob-actions">
          {editing && <button type="button" className="button button-outline" onClick={onDone}>Cancel</button>}
          <button className="button button-primary ob-submit">{editing ? 'Save details' : 'Start using PennyWise'} <ArrowRight size={17} /></button>
        </div>
        <p className="ob-small">Guidance, not regulated financial advice. We never approve credit.</p>
      </form>
    </div>
  );
}
