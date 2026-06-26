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
        <h1>Find any medical service — and what it costs</h1>
        <p className="lede">
          Search across ingested clinic price-list archives to see which partners provide a service
          and at what price.
        </p>
        <div className="hero-form">
          <SearchBox
            hero
            autoFocus
            initial={q}
            placeholder="Search a service or clinic, e.g. “МРТ головного мозга”"
            onSearch={runSearch}
          />
          <div className="hero-hints">
            Try:{' '}
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
        <h3>📥 Ingest archives</h3>
        <p className="muted">
          Upload ZIP archives of clinic price lists (PDF, scans, Excel, Word). MedArchive parses and
          normalizes them automatically.
        </p>
      </div>
      <div className="card">
        <h3>🔎 Search by service</h3>
        <p className="muted">
          Find a normalized medical service and instantly compare which partner clinics offer it and
          their resident / non-resident prices.
        </p>
      </div>
      <div className="card">
        <h3>🏥 Browse partners</h3>
        <p className="muted">
          Open any clinic to view contacts and its full, deduplicated price list with effective
          dates and verification status.
        </p>
      </div>
    </section>
  );
}

function SearchResults({ query }: { query: string }) {
  const { data, loading, error, reload } = useFetch<SearchResult>(() => api.search(query), [query]);
  const [tab, setTab] = useState<'services' | 'partners'>('services');

  if (loading) return <Loading label={`Searching for “${query}”…`} />;
  if (error) return <ErrorState error={error} onRetry={reload} />;
  if (!data) return null;

  const services = data.services ?? [];
  const partners = data.partners ?? [];
  const total = services.length + partners.length;

  if (total === 0) {
    return (
      <EmptyState title={`No results for “${query}”`}>
        Try a broader term, a different spelling, or one of the example queries above.
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
          Services ({services.length})
        </button>
        <button
          className={`btn ${tab === 'partners' ? 'btn-primary' : 'btn-secondary'} btn-sm`}
          onClick={() => setTab('partners')}
        >
          Partners ({partners.length})
        </button>
      </div>

      {tab === 'services' &&
        (services.length === 0 ? (
          <EmptyState icon="🩺" title="No matching services">
            No normalized services matched. Check the partners tab.
          </EmptyState>
        ) : (
          <div className="card-grid">
            {services.map((s) => (
              <LinkCard key={`svc-${s.service_id}`} to={`/services/${s.service_id}`}>
                <div className="rc-title">{s.service_name}</div>
                <div className="rc-meta">
                  {s.category && <Badge tone="primary">{s.category}</Badge>}
                  <span>{formatInt(s.partner_count)} partners</span>
                </div>
                <div className="rc-price">{formatKztRange(s.min_price_kzt, s.max_price_kzt)}</div>
              </LinkCard>
            ))}
          </div>
        ))}

      {tab === 'partners' &&
        (partners.length === 0 ? (
          <EmptyState icon="🏥" title="No matching partners">
            No clinics matched the query directly.
          </EmptyState>
        ) : (
          <div className="card-grid">
            {partners.map((p) => (
              <LinkCard key={`prt-${p.partner_id}`} to={`/partners/${p.partner_id}`}>
                <div className="rc-title">{p.name}</div>
                <div className="rc-meta">
                  {p.city && <span>📍 {p.city}</span>}
                  <span>{formatInt(p.service_count)} services</span>
                </div>
              </LinkCard>
            ))}
          </div>
        ))}

      <p className="faint" style={{ marginTop: 24, textAlign: 'center' }}>
        Showing matched services and partners for “{query}”.{' '}
        <Link to="/services">Browse all services →</Link>
      </p>
    </section>
  );
}
