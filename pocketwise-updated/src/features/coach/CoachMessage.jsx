import { Bot, User } from 'lucide-react';

export const AFFORD_LABEL = { GO: 'Go', THINK_TWICE: 'Think twice', SKIP: 'Skip for now' };
export const WORTH_LABEL = { WORTH_IT: 'Worth it', DEPENDS: 'Depends', NOT_WORTH_IT: 'Probably not worth it' };
const TONE = { GO: 'good', WORTH_IT: 'good', THINK_TWICE: 'warn', DEPENDS: 'warn', SKIP: 'bad', NOT_WORTH_IT: 'bad' };

function inline(text) {
  // **bold** only; everything is rendered as text, never as HTML.
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
    part.startsWith('**') && part.endsWith('**') ? <strong key={i}>{part.slice(2, -2)}</strong> : part.replace(/^\*(.+)\*$/, '$1'),
  );
}

/** Renders the coach's simple markdown: paragraphs, "- " bullet lists and **bold**. */
export function RichText({ text = '' }) {
  const blocks = [];
  let list = null;
  for (const raw of text.split('\n')) {
    const line = raw.trim();
    if (/^[-•]\s+/.test(line)) {
      if (!list) blocks.push((list = { type: 'ul', items: [] }));
      list.items.push(line.replace(/^[-•]\s+/, ''));
    } else {
      list = null;
      if (line) blocks.push({ type: 'p', text: line });
    }
  }
  return (
    <div className="rich-text">
      {blocks.map((b, i) =>
        b.type === 'ul' ? (
          <ul key={i}>{b.items.map((item, j) => <li key={j}>{inline(item)}</li>)}</ul>
        ) : (
          <p key={i} className={/^\*[^*].*\*$/.test(b.text) ? 'fine-print' : ''}>{inline(b.text)}</p>
        ),
      )}
    </div>
  );
}

export function VerdictBadge({ verdict, label, prefix }) {
  if (!verdict) return null;
  return <span className={`verdict-badge verdict-${TONE[verdict] || 'warn'}`}>{prefix ? `${prefix} ` : ''}{label || verdict}</span>;
}

/** Badges for whatever the coach worked out in this reply. */
export function ResultBadges({ data }) {
  if (!data) return null;
  const trip = data.trip_plan?.affordability?.verdict;
  const tt = data.time_travel;
  return (
    <div className="badge-row">
      {data.purchase_check && <VerdictBadge verdict={data.purchase_check.verdict} prefix="Can you afford it?" label={AFFORD_LABEL[data.purchase_check.verdict]} />}
      {data.worth_check && <VerdictBadge verdict={data.worth_check.worth_verdict} prefix="Worth it?" label={WORTH_LABEL[data.worth_check.worth_verdict]} />}
      {trip && <VerdictBadge verdict={trip} prefix="Trip:" label={AFFORD_LABEL[trip]} />}
      {tt && (
        <span className={`verdict-badge verdict-${tt.what_if_runs_out_in_month == null ? 'good' : 'bad'}`}>
          {tt.scenario_label}: {tt.what_if_runs_out_in_month == null ? "money doesn't run out" : `runs out in month ${tt.what_if_runs_out_in_month}`}
        </span>
      )}
    </div>
  );
}

export function Bubble({ role, text, data, pending }) {
  return (
    <div className={`bubble-row ${role}`}>
      <div className="bubble-avatar">{role === 'user' ? <User size={15} /> : <Bot size={15} />}</div>
      <div className={`bubble ${role} ${pending ? 'pending' : ''}`}>
        {role === 'error' ? <p>{text}</p> : <RichText text={text} />}
        <ResultBadges data={data} />
      </div>
    </div>
  );
}
