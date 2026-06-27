import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../lib/api';
import type { ServiceOut } from '../lib/api';
import { useFetch } from '../lib/useFetch';
import { Loading, ErrorState, EmptyState } from '../components/States';
import { Badge } from '../components/Badge';

export function ServicesPage() {
  const [text, setText] = useState('');
  const [category, setCategory] = useState('');

  // Fetch a generous page of services once; filter client-side for snappy UX.
  const { data, loading, error, reload } = useFetch<ServiceOut[]>(
    () => api.getServices({ limit: 500 }),
    [],
  );

  const services = data ?? [];

  const categories = useMemo(() => {
    const set = new Set<string>();
    services.forEach((s) => s.category && set.add(s.category));
    return Array.from(set).sort();
  }, [services]);

  const filtered = useMemo(() => {
    const t = text.trim().toLowerCase();
    return services.filter((s) => {
      if (category && s.category !== category) return false;
      if (!t) return true;
      const hay = [s.service_name, ...(s.synonyms || []), s.icd_code || '']
        .join(' ')
        .toLowerCase();
      return hay.includes(t);
    });
  }, [services, text, category]);

  return (
    <main className="page">
      <header className="page-header">
        <div className="eyebrow">Каталог</div>
        <h1>Медицинские услуги</h1>
        <p className="subtitle">
          Нормализованный каталог услуг. Выберите услугу, чтобы сравнить цены партнёров.
        </p>
      </header>

      <div className="filters">
        <div className="field grow">
          <label className="field-label" htmlFor="svc-q">
            Поиск услуг
          </label>
          <input
            id="svc-q"
            className="input"
            placeholder="Фильтр по названию, синониму или коду МКБ…"
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
        </div>
        <div className="field">
          <label className="field-label" htmlFor="svc-cat">
            Категория
          </label>
          <select
            id="svc-cat"
            className="select"
            value={category}
            onChange={(e) => setCategory(e.target.value)}
          >
            <option value="">Все категории</option>
            {categories.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </div>
      </div>

      {loading ? (
        <Loading label="Загрузка услуг…" />
      ) : error ? (
        <ErrorState error={error} onRetry={reload} />
      ) : filtered.length === 0 ? (
        <EmptyState icon="🩺" title="Услуги не найдены">
          {services.length === 0
            ? 'В каталоге пока нет услуг. Загрузите каталог из раздела «Админ».'
            : 'Услуги не найдены по выбранным фильтрам. Попробуйте сбросить фильтры.'}
        </EmptyState>
      ) : (
        <>
          <p className="faint" style={{ marginBottom: 12 }}>
            {filtered.length} {filtered.length === 1 ? 'услуга' : 'услуг'}
            {category ? ` в ${category}` : ''}
          </p>
          <div className="card-grid">
            {filtered.map((s) => (
              <Link key={s.service_id} to={`/services/${s.service_id}`} className="card hoverable result-card">
                <div className="rc-title">{s.service_name}</div>
                <div className="rc-meta">
                  {s.category && <Badge tone="primary">{s.category}</Badge>}
                  {!s.is_active && <Badge tone="neutral">Неактивна</Badge>}
                  {s.icd_code && <span className="mono">ICD: {s.icd_code}</span>}
                </div>
                {s.synonyms && s.synonyms.length > 0 && (
                  <div className="rc-meta" style={{ marginTop: 8 }}>
                    <span className="faint">синонимы: {s.synonyms.slice(0, 3).join(', ')}</span>
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
