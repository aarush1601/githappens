import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { Brain, Pencil, RotateCcw, Send, ShoppingBag, Sparkles, X } from 'lucide-react';
import { useApp } from '../context/AppContext';
import { money, parseMoney } from '../utils/currency';
import { expenseCategories } from '../data/mockData';
import { Bubble } from '../features/coach/CoachMessage';
import { coachApi, coachContext, rememberFacts, thisMonth } from '../features/coach/coachApi';

const STORE = 'pw-coach-chat';
const SUGGESTIONS = [
  'How am I doing this month?',
  'Is a £123 espresso machine worth it?',
  'What if my phone breaks?',
  'Where will I be in a year?',
];

const PERSONA_TEXT = {
  international_student: 'International student', student: 'UK student', gig_worker: 'Gig or shift worker',
  single_parent: 'Single parent', pensioner: 'Pensioner', new_migrant: 'New to the UK', working: 'Working', other: 'Something else',
};

function greeting(profile) {
  const name = profile?.name ? `, ${profile.name}` : '';
  return `Hi${name}! I'm your PennyWise money coach. Ask me if you can afford something, whether it's worth it, or what happens if something changes. I use your own numbers from PennyWise, never made-up ones.`;
}

function loadChat(profile) {
  try {
    const saved = JSON.parse(sessionStorage.getItem(STORE));
    if (saved?.messages?.length) return saved;
  } catch { /* start fresh */ }
  return { messages: [{ role: 'assistant', text: greeting(profile) }], history: [] };
}

export default function Coach() {
  const app = useApp();
  const { profile, setProfile, transactions, currency } = app;
  const [chat, setChat] = useState(() => loadChat(profile));
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [remembered, setRemembered] = useState([]);
  const [check, setCheck] = useState({ item: '', price: '', category: 'Shopping' });
  const logRef = useRef(null);

  useEffect(() => { sessionStorage.setItem(STORE, JSON.stringify(chat)); }, [chat]);
  useEffect(() => { logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: 'smooth' }); }, [chat, busy]);

  const recentPurchases = [...transactions].filter((t) => t.type === 'expense').sort((a, b) => (b.date || '').localeCompare(a.date || '')).slice(0, 5);

  const learned = (facts) => {
    if (!facts?.length) return;
    rememberFacts(setProfile, facts);
    setRemembered(facts);
  };

  async function run(userText, call, toMessage) {
    setChat((c) => ({ ...c, messages: [...c.messages, { role: 'user', text: userText }] }));
    setBusy(true);
    setRemembered([]);
    try {
      const data = await call();
      const { text, history } = toMessage(data);
      setChat((c) => ({ messages: [...c.messages, { role: 'assistant', text, data }], history: [...c.history, ...history].slice(-40) }));
      learned(data.new_facts);
    } catch (err) {
      setChat((c) => ({ ...c, messages: [...c.messages, { role: 'error', text: err.message }] }));
    } finally {
      setBusy(false);
    }
  }

  const send = (text) => {
    const message = text.trim();
    if (!message || busy) return;
    setInput('');
    run(message,
      () => coachApi.post('/coach', { message, history: chat.history, ...coachContext(app) }),
      (data) => ({ text: data.reply, history: [{ role: 'user', content: message }, { role: 'assistant', content: data.reply }] }));
  };

  // Purchase tracker: talk about a purchase already in PennyWise, or one they're thinking about.
  const review = ({ item, pricePence, category, transactionId }) => {
    if (busy) return;
    const label = `${transactionId ? 'Is this worth it?' : 'Thinking about'} ${item} – ${money(pricePence, currency)}`;
    run(label,
      () => coachApi.post('/purchase-review', {
        item, price: pricePence / 100, category, status: transactionId ? 'bought' : 'planning', log_transaction: false,
        ...coachContext(app, transactionId), // leave the purchase itself out so it isn't counted twice
      }),
      (data) => ({ text: data.explanation, history: data.history || [] }));
  };

  const submitCheck = (e) => {
    e.preventDefault();
    const pricePence = parseMoney(check.price);
    if (!check.item.trim() || pricePence <= 0) return;
    review({ item: check.item.trim(), pricePence, category: check.category });
    setCheck({ item: '', price: '', category: check.category });
  };

  const reset = () => setChat({ messages: [{ role: 'assistant', text: greeting(profile) }], history: [] });
  const forget = (fact) => setProfile((p) => ({ ...p, facts: (p.facts || []).filter((f) => f !== fact) }));

  return (
    <div className="coach-layout">
      <section className="coach-chat">
        <div className="coach-chat-head">
          <div><span className="eyebrow">PENNYWISE AI</span><h2>Money Coach</h2></div>
          <button className="button button-outline" onClick={reset} title="Start a new chat"><RotateCcw size={15} /> New chat</button>
        </div>
        <div className="coach-log" ref={logRef}>
          {chat.messages.map((m, i) => <Bubble key={i} {...m} />)}
          {busy && <Bubble role="assistant" text="Thinking it through with your numbers…" pending />}
          {remembered.length > 0 && (
            <div className="coach-remembered"><Brain size={14} /> I’ll remember: {remembered.join(' · ')}</div>
          )}
        </div>
        {chat.messages.length <= 1 && (
          <div className="coach-suggestions">
            {SUGGESTIONS.map((s) => <button key={s} className="coach-chip" onClick={() => send(s)}>{s}</button>)}
          </div>
        )}
        <form className="coach-input" onSubmit={(e) => { e.preventDefault(); send(input); }}>
          <input value={input} onChange={(e) => setInput(e.target.value)} placeholder="Ask about your money…" maxLength={2000} disabled={busy} />
          <button className="button button-primary" disabled={busy || !input.trim()}><Send size={16} /></button>
        </form>
      </section>

      <aside className="coach-side">
        <section className="coach-card">
          <div className="coach-card-title"><ShoppingBag size={17} /><h3>Purchase tracker</h3></div>
          <p className="coach-muted">Check something before you buy it.</p>
          <form className="coach-check" onSubmit={submitCheck}>
            <input value={check.item} onChange={(e) => setCheck({ ...check, item: e.target.value })} placeholder="e.g. walking shoes" maxLength={200} />
            <div className="coach-check-row">
              <input value={check.price} onChange={(e) => setCheck({ ...check, price: e.target.value })} placeholder="£ price" inputMode="decimal" />
              <select value={check.category} onChange={(e) => setCheck({ ...check, category: e.target.value })}>
                {expenseCategories.map((c) => <option key={c}>{c}</option>)}
              </select>
            </div>
            <button className="button button-primary" disabled={busy}>Is it worth it?</button>
          </form>
          <div className="coach-recent">
            <span className="coach-muted">Your recent purchases</span>
            {recentPurchases.length === 0 && <p className="coach-muted">Nothing yet. Add a transaction and it’ll show here.</p>}
            {recentPurchases.map((t) => (
              <button key={t.id} className="coach-purchase" disabled={busy}
                onClick={() => review({ item: t.name || t.category, pricePence: t.amount, category: t.category, transactionId: t.id })}>
                <span><b>{t.name || t.category}</b><small>{t.category} · {t.date}</small></span>
                <span className="coach-purchase-price">{money(t.amount, currency)}<em>Worth it?</em></span>
              </button>
            ))}
          </div>
        </section>

        <section className="coach-card">
          <div className="coach-card-title"><Sparkles size={17} /><h3>What PennyWise knows about you</h3>
            <Link to="/profile" className="coach-edit" title="Edit my details"><Pencil size={14} /></Link>
          </div>
          {profile ? (
            <ul className="coach-facts">
              <li>{PERSONA_TEXT[profile.persona] || 'Something else'}{profile.homeCountry ? ` from ${profile.homeCountry}` : ''}</li>
              <li>{money(profile.monthlyIncome, currency)} a month ({profile.incomeType === 'irregular' ? 'varies' : 'fixed'})</li>
              {(profile.monthlyRent > 0 || profile.monthlyBills > 0) && (
                <li className="coach-fact">
                  <span>Rent {money(profile.monthlyRent || 0, currency)}, bills {money(profile.monthlyBills || 0, currency)}
                    <small className="coach-paid">{profile.essentialsPaidMonth === thisMonth() ? ' · paid this month ✓' : ' · not paid yet this month'}</small></span>
                  <button title="Toggle paid this month" className="coach-paid-toggle"
                    onClick={() => setProfile((p) => ({ ...p, essentialsPaidMonth: p.essentialsPaidMonth === thisMonth() ? '' : thisMonth() }))}>
                    {profile.essentialsPaidMonth === thisMonth() ? 'Undo' : 'Mark paid'}
                  </button>
                </li>
              )}
              {profile.goal && <li>Working towards: {profile.goal}</li>}
              {(profile.facts || []).map((f) => (
                <li key={f} className="coach-fact">{f}<button onClick={() => forget(f)} title="Forget this"><X size={12} /></button></li>
              ))}
            </ul>
          ) : <p className="coach-muted">No details yet.</p>}
          <p className="coach-muted coach-tiny">The coach and trip planner both use this, and add to it when you tell them more.</p>
        </section>
      </aside>
    </div>
  );
}
