import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../lib/api';
import type { PartnerOut } from '../lib/api';
import { useFetch } from '../lib/useFetch';
import { Loading, ErrorState, EmptyState } from '../components/States';
import { Badge } from '../components/Badge';

export function PartnersPage() {
  const [text, setText] = useState('');
  const [city, setCity] = useState('');
  const [activeOnly, setActiveOnly] = useState(false);

  const { data, loading, error, reload } = useFetch<PartnerOut[]>(
    () => api.getPartners({ limit: 500 }),
    [],
  );

  const partners = data ?? [];

  const cities = useMemo(() => {
    const set = new Set<string>();
    partners.forEach((p) => p.city && set.add(p.city));
    return Array.from(set).sort();
  }, [partners]);

  const filtered = useMemo(() => {
    const t = text.trim().toLowerCase();
    return partners.filter((p) => {
      if (city && p.city !== city) return false;
      if (activeOnly && !p.is_active) return false;
      if (!t) return true;
      const hay = [p.name, p.city || '', p.address || ''].join(' ').toLowerCase();
      return hay.includes(t);
    });
  }, [partners, text, city, activeOnly]);

  return (
    <main className="page">
      <header className="page-header">
        <div className="eyebrow">Сеть</div>
        <h1>Клиники-партнёры</h1>
        <p className="subtitle">Все клиники, прайс-листы которых были загружены.</p>
      </header>

      <div className="filters">
        <div className="field grow">
          <label className="field-label" htmlFor="prt-q">
            Поиск партнёров
          </label>
          <input
            id="prt-q"
            className="input"
            placeholder="Фильтр по названию или адресу…"
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
        </div>
        <div className="field">
          <label className="field-label" htmlFor="prt-city">
            Город
          </label>
          <select
            id="prt-city"
            className="select"
            value={city}
            onChange={(e) => setCity(e.target.value)}
          >
            <option value="">Все города</option>
            {cities.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </div>
        <label className="toggle">
          <input
            type="checkbox"
            checked={activeOnly}
            onChange={(e) => setActiveOnly(e.target.checked)}
          />
          Только активные
        </label>
      </div>

      {loading ? (
        <Loading label="Загрузка партнёров…" />
      ) : error ? (
        <ErrorState error={error} onRetry={reload} />
      ) : filtered.length === 0 ? (
        <EmptyState icon="🏥" title="Партнёры не найдены">
          {partners.length === 0
            ? 'Партнёры пока отсутствуют. Загрузите архив из раздела «Админ» для начала работы.'
            : 'Нет партнёров, соответствующих фильтрам.'}
        </EmptyState>
      ) : (
        <>
          <p className="faint" style={{ marginBottom: 12 }}>
            {filtered.length} {filtered.length === 1 ? 'партнёр' : 'партнёров'}
            {city ? ` в ${city}` : ''}
          </p>
          <div className="card-grid">
            {filtered.map((p) => (
              <Link key={p.partner_id} to={`/partners/${p.partner_id}`} className="card hoverable result-card">
                <div className="rc-title">{p.name}</div>
                <div className="rc-meta">
                  {p.city && <span>📍 {p.city}</span>}
                  {p.is_active ? (
                    <Badge tone="success" dot>
                      Активна
                    </Badge>
                  ) : (
                    <Badge tone="neutral">Неактивна</Badge>
                  )}
                </div>
                {p.address && (
                  <div className="rc-meta" style={{ marginTop: 8 }}>
                    <span className="faint">{p.address}</span>
                  </div>
                )}
              </Link>
            ))}
          </div>
        </>
      )}
    </main>
  );
}
