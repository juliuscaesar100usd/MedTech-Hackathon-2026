import { useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { api } from '../lib/api';
import type { PartnerPriceOut } from '../lib/api';
import { useFetch } from '../lib/useFetch';
import { Loading, ErrorState, EmptyState } from '../components/States';
import { DataTable, type Column, type SortState } from '../components/DataTable';
import { VerifiedBadge, Badge } from '../components/Badge';
import { PriceTag } from '../components/PriceTag';
import { formatDate, formatConfidence, toNumber } from '../lib/format';

export function ServicePartnersPage() {
  const { id = '' } = useParams();
  const { data, loading, error, reload } = useFetch<PartnerPriceOut[]>(
    () => api.getServicePartners(id),
    [id],
  );
  const [sort, setSort] = useState<SortState>({ key: 'price_resident_kzt', dir: 'asc' });

  const rows = useMemo(() => {
    const list = [...(data ?? [])];
    const dir = sort.dir === 'asc' ? 1 : -1;
    list.sort((a, b) => {
      switch (sort.key) {
        case 'price_resident_kzt': {
          const av = toNumber(a.price_resident_kzt);
          const bv = toNumber(b.price_resident_kzt);
          if (av === null) return 1; // nulls last
          if (bv === null) return -1;
          return (av - bv) * dir;
        }
        case 'price_nonresident_kzt': {
          const av = toNumber(a.price_nonresident_kzt);
          const bv = toNumber(b.price_nonresident_kzt);
          if (av === null) return 1;
          if (bv === null) return -1;
          return (av - bv) * dir;
        }
        case 'partner':
          return a.partner.name.localeCompare(b.partner.name) * dir;
        case 'effective_date':
          return (
            ((a.effective_date || '') < (b.effective_date || '') ? -1 : 1) * dir
          );
        default:
          return 0;
      }
    });
    return list;
  }, [data, sort]);

  function toggleSort(key: string) {
    setSort((cur) =>
      cur.key === key ? { key, dir: cur.dir === 'asc' ? 'desc' : 'asc' } : { key, dir: 'asc' },
    );
  }

  // Derive a service title from the first row's category if present.
  const serviceName = useMemo(() => {
    const raw = rows.find((r) => r.service_name_raw)?.service_name_raw;
    return raw || `Service #${id}`;
  }, [rows, id]);

  const columns: Column<PartnerPriceOut>[] = [
    {
      key: 'partner',
      header: 'Partner',
      sortable: true,
      render: (r) => (
        <div>
          <Link to={`/partners/${r.partner.partner_id}`} className="cell-strong">
            {r.partner.name}
          </Link>
          <div className="cell-sub">
            {r.partner.city || '—'}
            {r.service_name_raw ? ` · “${r.service_name_raw}”` : ''}
          </div>
        </div>
      ),
    },
    {
      key: 'price_resident_kzt',
      header: 'Resident',
      numeric: true,
      sortable: true,
      render: (r) => <PriceTag value={r.price_resident_kzt} />,
    },
    {
      key: 'price_nonresident_kzt',
      header: 'Non-resident',
      numeric: true,
      sortable: true,
      render: (r) => <PriceTag value={r.price_nonresident_kzt} />,
    },
    {
      key: 'effective_date',
      header: 'Effective',
      sortable: true,
      render: (r) => <span className="muted">{formatDate(r.effective_date)}</span>,
    },
    {
      key: 'match_confidence',
      header: 'Confidence',
      numeric: true,
      render: (r) => {
        const c = toNumber(r.match_confidence as number | string | null);
        const tone = c === null ? 'neutral' : c >= 0.85 ? 'success' : c >= 0.6 ? 'warning' : 'danger';
        return <Badge tone={tone}>{formatConfidence(r.match_confidence as number | string | null)}</Badge>;
      },
    },
    {
      key: 'is_verified',
      header: 'Status',
      render: (r) => <VerifiedBadge verified={r.is_verified} />,
    },
  ];

  return (
    <main className="page">
      <Link to="/services" className="back-link">
        ← All services
      </Link>

      {loading ? (
        <Loading label="Loading partners…" />
      ) : error ? (
        <ErrorState error={error} onRetry={reload} />
      ) : (
        <>
          <header className="page-header">
            <div className="eyebrow">Service</div>
            <h1>{serviceName}</h1>
            <p className="subtitle">
              {rows.length} partner{rows.length === 1 ? '' : 's'} provide this service. Sort by price
              to compare.
            </p>
          </header>

          {rows.length === 0 ? (
            <EmptyState icon="🏥" title="No partners offer this service yet">
              Once price lists referencing this service are ingested, partners will appear here.
            </EmptyState>
          ) : (
            <DataTable<PartnerPriceOut>
              columns={columns}
              rows={rows}
              rowKey={(r) => String(r.item_id)}
              sort={sort}
              onSort={toggleSort}
            />
          )}
        </>
      )}
    </main>
  );
}
