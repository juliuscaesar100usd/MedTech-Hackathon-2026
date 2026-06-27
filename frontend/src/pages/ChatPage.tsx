import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../lib/api';
import type {
  AssistantChatMessage,
  AssistantOffer,
  AssistantPartnerResult,
  AssistantReply,
  AssistantServiceResult,
  AssistantStatus,
} from '../lib/api';
import { Badge } from '../components/Badge';
import { formatKzt, formatKztRange, formatInt } from '../lib/format';

const EXAMPLES = [
  'Анализ крови в Алматы дешевле 5000 ₸',
  'Самое дешёвое УЗИ',
  'Консультация терапевта для нерезидента',
  'Клиники в Астане',
  'МРТ головного мозга',
];

type Turn =
  | { id: number; role: 'user'; content: string }
  | { id: number; role: 'assistant'; reply: AssistantReply }
  | { id: number; role: 'assistant'; pending: true }
  | { id: number; role: 'assistant'; error: string };

let _seq = 0;
const nextId = () => ++_seq;

export function ChatPage() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [status, setStatus] = useState<AssistantStatus | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api.assistantStatus().then(setStatus).catch(() => setStatus(null));
  }, []);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [turns]);

  async function send(text: string) {
    const message = text.trim();
    if (!message || sending) return;
    setInput('');
    setSending(true);

    // History from completed turns (oldest first), capped for the request.
    const history: AssistantChatMessage[] = [];
    for (const t of turns) {
      if (t.role === 'user') history.push({ role: 'user', content: t.content });
      else if ('reply' in t) history.push({ role: 'assistant', content: t.reply.reply });
    }
    const trimmedHistory = history.slice(-8);

    const pendingId = nextId();
    setTurns((prev) => [
      ...prev,
      { id: nextId(), role: 'user', content: message },
      { id: pendingId, role: 'assistant', pending: true },
    ]);

    try {
      const reply = await api.assistantChat(message, trimmedHistory);
      setTurns((prev) =>
        prev.map((t) => (t.id === pendingId ? { id: pendingId, role: 'assistant', reply } : t)),
      );
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Запрос не выполнен.';
      setTurns((prev) =>
        prev.map((t) => (t.id === pendingId ? { id: pendingId, role: 'assistant', error: msg } : t)),
      );
    } finally {
      setSending(false);
    }
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    void send(input);
  }

  return (
    <main className="page chat-page">
      <div className="chat-head">
        <div>
          <h1>AI-ассистент</h1>
          <p className="lede">
            Опишите, что вам нужно, простыми словами — услуга, бюджет, город, цены для резидента
            или нерезидента — и сразу получите подходящие клиники с ценами.
          </p>
        </div>
        {status && (
          <span className={`assistant-mode ${status.llm_available ? 'live' : 'local'}`}>
            {status.llm_available ? `✨ Claude (${status.model})` : '⚡ Умный парсер'}
          </span>
        )}
      </div>

      <div className="chat-window">
        {turns.length === 0 ? (
          <Welcome onPick={send} />
        ) : (
          turns.map((t) => <TurnView key={t.id} turn={t} onPick={send} />)
        )}
        <div ref={endRef} />
      </div>

      <form className="chat-input" onSubmit={onSubmit}>
        <input
          className="input"
          value={input}
          placeholder='Например: «УЗИ щитовидной железы дешевле 8000 ₸ в Алматы»'
          autoFocus
          disabled={sending}
          onChange={(e) => setInput(e.target.value)}
          aria-label="Введите запрос"
        />
        <button className="btn btn-primary" type="submit" disabled={sending || !input.trim()}>
          {sending ? '…' : 'Отправить'}
        </button>
      </form>
    </main>
  );
}

function Welcome({ onPick }: { onPick: (t: string) => void }) {
  return (
    <div className="chat-welcome">
      <div className="chat-bubble assistant">
        <p style={{ margin: 0 }}>
          👋 Привет! Расскажите, какая медицинская услуга вас интересует и какие у вас пожелания —
          ценовой лимит, город, резидент или нерезидент. Например:
        </p>
      </div>
      <div className="chat-examples">
        {EXAMPLES.map((ex) => (
          <button key={ex} className="chip" onClick={() => onPick(ex)} type="button">
            {ex}
          </button>
        ))}
      </div>
    </div>
  );
}

function TurnView({ turn, onPick }: { turn: Turn; onPick: (t: string) => void }) {
  if (turn.role === 'user') {
    return (
      <div className="chat-row user">
        <div className="chat-bubble user">{turn.content}</div>
      </div>
    );
  }
  if ('pending' in turn) {
    return (
      <div className="chat-row assistant">
        <div className="chat-bubble assistant typing">
          <span /> <span /> <span />
        </div>
      </div>
    );
  }
  if ('error' in turn) {
    return (
      <div className="chat-row assistant">
        <div className="chat-bubble assistant error">⚠️ {turn.error}</div>
      </div>
    );
  }
  return (
    <div className="chat-row assistant">
      <div className="chat-bubble assistant">
        <p className="chat-reply">{turn.reply.reply}</p>
        <PreferenceChips reply={turn.reply} />
        <Results reply={turn.reply} />
        {turn.reply.suggestions.length > 0 && (
          <div className="chat-suggestions">
            {turn.reply.suggestions.map((s) => (
              <button key={s} className="chip chip-sm" type="button" onClick={() => onPick(s)}>
                {s}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function PreferenceChips({ reply }: { reply: AssistantReply }) {
  const p = reply.preferences;
  const chips: { label: string; tone?: 'primary' | 'info' | 'neutral' }[] = [];
  if (p.raw_query) chips.push({ label: `🔎 ${p.raw_query}`, tone: 'primary' });
  if (p.city) chips.push({ label: `📍 ${p.city}`, tone: 'info' });
  if (p.max_price_kzt != null) chips.push({ label: `≤ ${formatKzt(p.max_price_kzt)}` });
  if (p.min_price_kzt != null) chips.push({ label: `≥ ${formatKzt(p.min_price_kzt)}` });
  if (p.resident !== 'any')
    chips.push({ label: p.resident === 'nonresident' ? 'Нерезидент' : 'Резидент' });
  if (p.sort !== 'relevance') chips.push({ label: p.sort === 'cheapest' ? '⬇ Дешевле' : '⬆ Премиум' });

  if (chips.length === 0) return null;
  return (
    <div className="pref-chips">
      <span className="pref-label">Распознано:</span>
      {chips.map((c, i) => (
        <Badge key={i} tone={c.tone ?? 'neutral'}>
          {c.label}
        </Badge>
      ))}
      <span className="pref-parser">{reply.used_llm ? 'через Claude' : 'через умный парсер'}</span>
    </div>
  );
}

function Results({ reply }: { reply: AssistantReply }) {
  if (reply.services.length > 0) {
    return (
      <div className="chat-results">
        {reply.services.map((s) => (
          <ServiceCard key={String(s.service_id)} service={s} resident={reply.preferences.resident} />
        ))}
      </div>
    );
  }
  if (reply.partners.length > 0) {
    return (
      <div className="chat-results partners">
        {reply.partners.map((p) => (
          <PartnerCard key={String(p.partner_id)} partner={p} />
        ))}
      </div>
    );
  }
  return null;
}

function ServiceCard({
  service,
  resident,
}: {
  service: AssistantServiceResult;
  resident: string;
}) {
  return (
    <div className="card pad-sm result-card-static">
      <div className="rc-head">
        <Link to={`/services/${service.service_id}`} className="rc-title-link">
          {service.service_name}
        </Link>
        {service.category && <Badge tone="primary">{service.category}</Badge>}
      </div>
      <div className="rc-meta">
        <span>{formatInt(service.partner_count)} клиник</span>
        <span className="rc-price">{formatKztRange(service.min_price_kzt, service.max_price_kzt)}</span>
      </div>
      <table className="offers-table">
        <tbody>
          {service.offers.map((o) => (
            <OfferRow key={String(o.item_id)} offer={o} resident={resident} />
          ))}
        </tbody>
      </table>
    </div>
  );
}

function OfferRow({ offer, resident }: { offer: AssistantOffer; resident: string }) {
  const priceLabel = resident === 'nonresident' ? 'нерезидент' : 'резидент';
  return (
    <tr>
      <td>
        <Link to={`/partners/${offer.partner_id}`}>{offer.partner_name}</Link>
        {offer.city && <span className="offer-city"> · {offer.city}</span>}
      </td>
      <td className="offer-price">
        <strong>{formatKzt(offer.price_shown_kzt)}</strong>
        <span className="offer-price-label"> {priceLabel}</span>
      </td>
      <td className="offer-verified">
        {offer.is_verified && (
          <Badge tone="success" dot>
            ✓
          </Badge>
        )}
      </td>
    </tr>
  );
}

function PartnerCard({ partner }: { partner: AssistantPartnerResult }) {
  return (
    <Link to={`/partners/${partner.partner_id}`} className="card hoverable result-card">
      <div className="rc-title">{partner.name}</div>
      <div className="rc-meta">
        {partner.city && <span>📍 {partner.city}</span>}
        <span>{formatInt(partner.service_count)} услуг</span>
      </div>
    </Link>
  );
}
