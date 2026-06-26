import { useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { api } from '../lib/api';
import type { PartnerOut, ServicePriceOut } from '../lib/api';
import { useFetch } from '../lib/useFetch';
import { Loading, ErrorState, EmptyState } from '../components/States';
import { Card } from '../components/Card';
import { Badge, VerifiedBadge } from '../components/Badge';
import { PriceTag } from '../components/PriceTag';
import { formatDate } from '../lib/format';

export function PartnerPage() {
  const { id = '' } = useParams();

  const partnerState = useFetch<PartnerOut>(() => api.getPartner(id), [id]);
  const servicesState = useFetch<ServicePriceOut[]>(() => api.getPartnerServices(id), [id]);

  const partner = partnerState.data;

  return (
    <main className="page">
      <Link to="/partners" className="back-link">
        ← All partners
      </Link>

      {partnerState.loading ? (
        <Loading label="Loading partner…" />
      ) : partnerState.error ? (
        <ErrorState error={partnerState.error} onRetry={partnerState.reload} />
      ) : partner ? (
        <>
          <header className="page-header">
            <div className="eyebrow">Partner clinic</div>
            <div className="row wrap" style={{ gap: 12 }}>
              <h1 style={{ marginBottom: 0 }}>{partner.name}</h1>
              {partner.is_active ? (
                <Badge tone="success" dot>
                  Active
                </Badge>
              ) : (
                <Badge tone="neutral">Inactive</Badge>
              )}
            </div>
          </header>

          <div className="two-col">
            <Card>
              <h3>Contacts</h3>
              <ul className="contact-list">
                <li>
                  <span className="ci-label">City</span>
                  <span>{partner.city || '—'}</span>
                </li>
                <li>
                  <span className="ci-label">Address</span>
                  <span>{partner.address || '—'}</span>
                </li>
                <li>
                  <span className="ci-label">Email</span>
                  <span>
                    {partner.contact_email ? (
                      <a href={`mailto:${partner.contact_email}`}>{partner.contact_email}</a>
                    ) : (
                      '—'
                    )}
                  </span>
                </li>
                <li>
                  <span className="ci-label">Phone</span>
                  <span>
                    {partner.contact_phone ? (
                      <a href={`tel:${partner.contact_phone}`}>{partner.contact_phone}</a>
                    ) : (
                      '—'
                    )}
                  </span>
                </li>
              </ul>
            </Card>

            <div>
              <PriceList state={servicesState} />
            </div>
          </div>
        </>
      ) : null}
    </main>
  );
}

function PriceList({
  state,
}: {
  state: ReturnType<typeof useFetch<ServicePriceOut[]>>;
}) {
  const [text, setText] = useState('');
  const items = state.data ?? [];

  // Group items by category for a readable, sectioned price list.
  const grouped = useMemo(() => {
    const t = text.trim().toLowerCase();
    const filtered = items.filter((it) => {
      if (!t) return true;
      const hay = [it.service_name || '', it.service_name_raw || '', it.category || '']
        .join(' ')
        .toLowerCase();
      return hay.includes(t);
    });
    const map = new Map<string, ServicePriceOut[]>();
    for (const it of filtered) {
      const cat = it.category || 'Uncategorized';
      if (!map.has(cat)) map.set(cat, []);
      map.get(cat)!.push(it);
    }
    return Array.from(map.entries()).sort((a, b) => a[0].localeCompare(b[0]));
  }, [items, text]);

  if (state.loading) return <Loading label="Loading price list…" />;
  if (state.error) return <ErrorState error={state.error} onRetry={state.reload} />;

  return (
    <section>
      <div className="row between wrap" style={{ marginBottom: 14 }}>
        <h3 style={{ marginBottom: 0 }}>Price list</h3>
        <input
          className="input"
          style={{ maxWidth: 260 }}
          placeholder="Filter services…"
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
      </div>

      {items.length === 0 ? (
        <EmptyState icon="📋" title="No price items">
          No price items have been ingested for this partner yet.
        </EmptyState>
      ) : grouped.length === 0 ? (
        <EmptyState icon="🔍" title="No services match the filter" />
      ) : (
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Service</th>
                <th className="num">Resident</th>
                <th className="num">Non-resident</th>
                <th>Effective</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {grouped.map(([cat, rows]) => (
                <CategoryGroup key={cat} category={cat} rows={rows} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function CategoryGroup({ category, rows }: { category: string; rows: ServicePriceOut[] }) {
  return (
    <>
      <tr className="group-row">
        <td colSpan={5}>
          {category} <span className="faint">({rows.length})</span>
        </td>
      </tr>
      {rows.map((it) => {
        const normalized = it.service_name;
        const raw = it.service_name_raw;
        const showRaw = raw && raw !== normalized;
        return (
          <tr key={String(it.item_id)}>
            <td>
              <span className="cell-strong">{normalized || raw || '—'}</span>
              {showRaw && <div className="cell-sub">raw: “{raw}”</div>}
              {!normalized && it.match_status && (
                <div className="cell-sub">
                  <Badge tone="warning">{it.match_status}</Badge>
                </div>
              )}
            </td>
            <td className="num">
              <PriceTag value={it.price_resident_kzt} />
            </td>
            <td className="num">
              <PriceTag value={it.price_nonresident_kzt} />
            </td>
            <td className="muted">{formatDate(it.effective_date)}</td>
            <td>
              <VerifiedBadge verified={it.is_verified} />
            </td>
          </tr>
        );
      })}
    </>
  );
}
