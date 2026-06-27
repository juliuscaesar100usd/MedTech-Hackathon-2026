import { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import {
  MagnifyingGlass,
  Tray,
  Buildings,
  Stethoscope,
  MapPin,
  CaretRight,
} from '@phosphor-icons/react';
import { api } from '../lib/api';
import type { SearchResult } from '../lib/api';
import { useFetch } from '../lib/useFetch';
import { SearchBox } from '../components/SearchBox';
import { ErrorState } from '../components/States';
import { Badge } from '../components/Badge';
import { formatKztRange, formatInt } from '../lib/format';

/* MedArchive search — the in-product search surface.
   Redesign per taste-skill: same trust-first clinical language as the landing
   (one teal hue, Phosphor icons — no emoji, AA contrast, restrained motion).
   The search band compacts once a query is active so results sit close; result
   rows are price-forward (price is the whole point) with tabular figures.
   Russian тире (—) is correct, required punctuation here. */

const EXAMPLES = ['МРТ головного мозга', 'УЗИ', 'Консультация терапевта', 'Анализ крови', 'КТ'];

/* Russian plural: 1 услуга, 2 услуги, 5 услуг. Standard one/few/many rule. */
function pluralRu(n: number, [one, few, many]: [string, string, string]): string {
  const m10 = n % 10;
  const m100 = n % 100;
  if (m10 === 1 && m100 !== 11) return one;
  if (m10 >= 2 && m10 <= 4 && (m100 < 10 || m100 >= 20)) return few;
  return many;
}

export function SearchPage() {
  const [params, setParams] = useSearchParams();
  const q = params.get('q') ?? '';

  function runSearch(value: string) {
    if (value) setParams({ q: value });
    else setParams({});
  }

  return (
    <main className="sp">
      <section className={`sp-band${q ? ' sp-band--compact' : ''}`}>
        <div className="sp-band-inner">
          {!q && <span className="sp-eyebrow">Поиск по каталогу</span>}
          <h1 className="sp-title">
            Найдите любую медицинскую услугу — и узнайте её стоимость
          </h1>
          {!q && (
            <p className="sp-lede">
              Ищите по загруженным архивам прайс-листов клиник — и узнавайте, какие партнёры
              оказывают услугу и по какой цене.
            </p>
          )}
          <div className="sp-search">
            <SearchBox
              hero
              autoFocus
              initial={q}
              placeholder="Поиск услуги или клиники, напр. «МРТ головного мозга»"
              onSearch={runSearch}
            />
          </div>
          <div className="sp-hints">
            <span className="sp-hints-label">Попробуйте:</span>
            {EXAMPLES.map((ex) => (
              <button key={ex} type="button" className="chip" onClick={() => runSearch(ex)}>
                {ex}
              </button>
            ))}
          </div>
        </div>
      </section>

      <div className="sp-container">
        {q ? <SearchResults query={q} /> : <Steps />}
      </div>
    </main>
  );
}

const STEPS = [
  {
    icon: Tray,
    title: 'Загрузка архивов',
    body: 'ZIP-архивы прайс-листов клиник (PDF, сканы, Excel, Word) обрабатываются и нормализуются автоматически.',
  },
  {
    icon: MagnifyingGlass,
    title: 'Поиск по услуге',
    body: 'Найдите нормализованную услугу и сразу сравните, какие клиники-партнёры её предлагают — для резидентов и нерезидентов.',
  },
  {
    icon: Buildings,
    title: 'Просмотр партнёров',
    body: 'Откройте клинику — увидите контакты и полный прайс-лист с датами вступления в силу и статусом верификации.',
  },
];

function Steps() {
  return (
    <ol className="sp-steps" aria-label="Как это работает">
      {STEPS.map((s, i) => (
        <li key={s.title} className="sp-step">
          <span className="sp-step-icon">
            <s.icon size={24} weight="duotone" aria-hidden="true" />
          </span>
          <span className="sp-step-num" aria-hidden="true">
            0{i + 1}
          </span>
          <h2 className="sp-step-title">{s.title}</h2>
          <p className="sp-step-body">{s.body}</p>
        </li>
      ))}
    </ol>
  );
}

function SearchResults({ query }: { query: string }) {
  const { data, loading, error, reload } = useFetch<SearchResult>(() => api.search(query), [query]);
  const [tab, setTab] = useState<'services' | 'partners'>('services');

  if (loading) return <ResultsSkeleton />;
  if (error) return <ErrorState error={error} onRetry={reload} />;
  if (!data) return null;

  const services = data.services ?? [];
  const partners = data.partners ?? [];
  const total = services.length + partners.length;

  if (total === 0) {
    return (
      <div className="sp-empty">
        <span className="sp-empty-icon">
          <MagnifyingGlass size={30} weight="bold" aria-hidden="true" />
        </span>
        <h2 className="sp-empty-title">Ничего не найдено по запросу «{query}»</h2>
        <p className="sp-empty-body">
          Попробуйте более широкий запрос, другое написание или один из примеров выше.
        </p>
      </div>
    );
  }

  const showServices = tab === 'services';

  return (
    <section className="sp-results">
      <p className="sp-results-count">
        {total} {pluralRu(total, ['результат', 'результата', 'результатов'])} по запросу{' '}
        <b>«{query}»</b>
      </p>

      <div className="sp-segment" role="group" aria-label="Тип результатов">
        <button
          type="button"
          className={`sp-seg${showServices ? ' is-active' : ''}`}
          aria-pressed={showServices}
          onClick={() => setTab('services')}
        >
          Услуги <span className="sp-seg-n">{services.length}</span>
        </button>
        <button
          type="button"
          className={`sp-seg${!showServices ? ' is-active' : ''}`}
          aria-pressed={!showServices}
          onClick={() => setTab('partners')}
        >
          Партнёры <span className="sp-seg-n">{partners.length}</span>
        </button>
      </div>

      {showServices ? (
        services.length === 0 ? (
          <EmptyTab>Нормализованных услуг не найдено. Проверьте вкладку «Партнёры».</EmptyTab>
        ) : (
          <div className="sp-list">
            {services.map((s) => (
              <Link
                key={`svc-${s.service_id}`}
                to={`/services/${s.service_id}`}
                className="sp-result"
              >
                <span className="sp-result-icon">
                  <Stethoscope size={22} weight="duotone" aria-hidden="true" />
                </span>
                <span className="sp-result-body">
                  <span className="sp-result-title">{s.service_name}</span>
                  <span className="sp-result-meta">
                    {s.category && <Badge tone="primary">{s.category}</Badge>}
                    <span className="sp-meta-chip">
                      <Buildings size={15} weight="bold" aria-hidden="true" />
                      {formatInt(s.partner_count)}{' '}
                      {pluralRu(Number(s.partner_count) || 0, ['партнёр', 'партнёра', 'партнёров'])}
                    </span>
                  </span>
                </span>
                <span className="sp-result-price">
                  <span className="sp-price-label">Цена</span>
                  <span className="sp-price">
                    {formatKztRange(s.min_price_kzt, s.max_price_kzt)}
                  </span>
                </span>
                <CaretRight className="sp-result-caret" size={18} weight="bold" aria-hidden="true" />
              </Link>
            ))}
          </div>
        )
      ) : partners.length === 0 ? (
        <EmptyTab>По запросу клиники не найдены.</EmptyTab>
      ) : (
        <div className="sp-list">
          {partners.map((p) => (
            <Link
              key={`prt-${p.partner_id}`}
              to={`/partners/${p.partner_id}`}
              className="sp-result sp-result--partner"
            >
              <span className="sp-result-icon">
                <Buildings size={22} weight="duotone" aria-hidden="true" />
              </span>
              <span className="sp-result-body">
                <span className="sp-result-title">{p.name}</span>
                <span className="sp-result-meta">
                  {p.city && (
                    <span className="sp-meta-chip">
                      <MapPin size={15} weight="bold" aria-hidden="true" />
                      {p.city}
                    </span>
                  )}
                  <span className="sp-meta-chip">
                    <Stethoscope size={15} weight="bold" aria-hidden="true" />
                    {formatInt(p.service_count)}{' '}
                    {pluralRu(Number(p.service_count) || 0, ['услуга', 'услуги', 'услуг'])}
                  </span>
                </span>
              </span>
              <CaretRight className="sp-result-caret" size={18} weight="bold" aria-hidden="true" />
            </Link>
          ))}
        </div>
      )}

      <p className="sp-results-foot">
        <Link to="/services">Смотреть весь каталог услуг <CaretRight size={14} weight="bold" /></Link>
      </p>
    </section>
  );
}

function EmptyTab({ children }: { children: React.ReactNode }) {
  return (
    <div className="sp-empty sp-empty--tab">
      <span className="sp-empty-icon">
        <MagnifyingGlass size={26} weight="bold" aria-hidden="true" />
      </span>
      <p className="sp-empty-body">{children}</p>
    </div>
  );
}

/* Skeleton mirrors the result-row shape (rule: skeletons over spinners >300ms). */
function ResultsSkeleton() {
  return (
    <section className="sp-results" aria-busy="true" aria-label="Загрузка результатов">
      <div className="sp-skeleton-bar" />
      <div className="sp-list">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="sp-result sp-result--skeleton" aria-hidden="true">
            <span className="sp-result-icon sk" />
            <span className="sp-result-body">
              <span className="sk sk-line sk-title" />
              <span className="sk sk-line sk-meta" />
            </span>
            <span className="sk sk-price" />
          </div>
        ))}
      </div>
    </section>
  );
}
