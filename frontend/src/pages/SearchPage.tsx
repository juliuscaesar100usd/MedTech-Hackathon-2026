import { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { api } from '../lib/api';
import type { SearchResult } from '../lib/api';
import { useFetch } from '../lib/useFetch';
import { SearchBox } from '../components/SearchBox';
import { LinkCard } from '../components/Card';
import { Loading, ErrorState, EmptyState } from '../components/States';
import { Badge } from '../components/Badge';
import { formatKztRange, formatInt } from '../lib/format';

const EXAMPLES = ['МРТ головного мозга', 'УЗИ', 'Консультация терапевта', 'Анализ крови', 'КТ'];

export function SearchPage() {
  const [params, setParams] = useSearchParams();
  const q = params.get('q') ?? '';

  function runSearch(value: string) {
    if (value) setParams({ q: value });
    else setParams({});
  }

  return (
    <main className="page">
      <div className="hero">
        <h1>Найдите любую медицинскую услугу — и узнайте её стоимость</h1>
        <p className="lede">
          Ищите по загруженным архивам прайс-листов клиник — и узнавайте, какие партнёры
          оказывают услугу и по какой цене.
        </p>
        <div className="hero-form">
          <SearchBox
            hero
            autoFocus
            initial={q}
            placeholder='Поиск услуги или клиники, напр. «МРТ головного мозга»'
            onSearch={runSearch}
          />
          <div className="hero-hints">
            Попробуйте:{' '}
            {EXAMPLES.map((ex) => (
              <button key={ex} className="chip" onClick={() => runSearch(ex)}>
                {ex}
              </button>
            ))}
          </div>
        </div>
      </div>

      {q ? <SearchResults query={q} /> : <ProductExplainer />}
    </main>
  );
}

function ProductExplainer() {
  return (
    <section className="card-grid" style={{ maxWidth: 900, margin: '0 auto' }}>
      <div className="card">
        <h3>📥 Загрузка архивов</h3>
        <p className="muted">
          Загружайте ZIP-архивы прайс-листов клиник (PDF, сканы, Excel, Word). MedArchive
          автоматически обрабатывает и нормализует их.
        </p>
      </div>
      <div className="card">
        <h3>🔎 Поиск по услуге</h3>
        <p className="muted">
          Найдите нормализованную медицинскую услугу и сразу сравните, какие клиники-партнёры
          её предлагают и по каким ценам для резидентов / нерезидентов.
        </p>
      </div>
      <div className="card">
        <h3>🏥 Просмотр партнёров</h3>
        <p className="muted">
          Откройте любую клинику, чтобы увидеть контакты и полный прайс-лист с датами вступления
          в силу и статусом верификации.
        </p>
      </div>
    </section>
  );
}

function SearchResults({ query }: { query: string }) {
  const { data, loading, error, reload } = useFetch<SearchResult>(() => api.search(query), [query]);
  const [tab, setTab] = useState<'services' | 'partners'>('services');

  if (loading) return <Loading label={`Поиск «${query}»…`} />;
  if (error) return <ErrorState error={error} onRetry={reload} />;
  if (!data) return null;

  const services = data.services ?? [];
  const partners = data.partners ?? [];
  const total = services.length + partners.length;

  if (total === 0) {
    return (
      <EmptyState title={`Ничего не найдено по запросу «${query}»`}>
        Попробуйте более широкий запрос, другое написание или один из примеров выше.
      </EmptyState>
    );
  }

  return (
    <section>
      <div className="row wrap" style={{ marginBottom: 20 }}>
        <button
          className={`btn ${tab === 'services' ? 'btn-primary' : 'btn-secondary'} btn-sm`}
          onClick={() => setTab('services')}
        >
          Услуги ({services.length})
        </button>
        <button
          className={`btn ${tab === 'partners' ? 'btn-primary' : 'btn-secondary'} btn-sm`}
          onClick={() => setTab('partners')}
        >
          Партнёры ({partners.length})
        </button>
      </div>

      {tab === 'services' &&
        (services.length === 0 ? (
          <EmptyState icon="🩺" title="Услуги не найдены">
            Нормализованных услуг не найдено. Проверьте вкладку «Партнёры».
          </EmptyState>
        ) : (
          <div className="card-grid">
            {services.map((s) => (
              <LinkCard key={`svc-${s.service_id}`} to={`/services/${s.service_id}`}>
                <div className="rc-title">{s.service_name}</div>
                <div className="rc-meta">
                  {s.category && <Badge tone="primary">{s.category}</Badge>}
                  <span>{formatInt(s.partner_count)} партнёров</span>
                </div>
                <div className="rc-price">{formatKztRange(s.min_price_kzt, s.max_price_kzt)}</div>
              </LinkCard>
            ))}
          </div>
        ))}

      {tab === 'partners' &&
        (partners.length === 0 ? (
          <EmptyState icon="🏥" title="Партнёры не найдены">
            По запросу клиники не найдены.
          </EmptyState>
        ) : (
          <div className="card-grid">
            {partners.map((p) => (
              <LinkCard key={`prt-${p.partner_id}`} to={`/partners/${p.partner_id}`}>
                <div className="rc-title">{p.name}</div>
                <div className="rc-meta">
                  {p.city && <span>📍 {p.city}</span>}
                  <span>{formatInt(p.service_count)} услуг</span>
                </div>
              </LinkCard>
            ))}
          </div>
        ))}

      <p className="faint" style={{ marginTop: 24, textAlign: 'center' }}>
        Найдено: услуги и партнёры по запросу «{query}».{' '}
        <Link to="/services">Все услуги →</Link>
      </p>
    </section>
  );
}
