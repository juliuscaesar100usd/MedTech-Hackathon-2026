import { useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import {
  QueryClient,
  QueryClientProvider,
  useQuery,
} from '@tanstack/react-query';
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { api, API_BASE } from '../lib/api';
import type { PartnerPriceOut } from '../lib/api';
import { useFetch } from '../lib/useFetch';
import { Loading, ErrorState, EmptyState } from '../components/States';
import { DataTable, type Column, type SortState } from '../components/DataTable';
import { VerifiedBadge, Badge } from '../components/Badge';
import { PriceTag } from '../components/PriceTag';
import {
  formatConfidence,
  formatDate,
  formatInt,
  formatKzt,
  toNumber,
  type Money,
} from '../lib/format';

// The rest of the app fetches via the custom `useFetch` hook; the price-history
// widget is opted into react-query as requested. App.tsx is owned by another
// lane, so rather than mount a provider at the root we scope a QueryClient to
// this page — nested QueryClientProviders are supported and conflict-free.
const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 30_000, retry: 1 } },
});

// ---------------------------------------------------------------------------
// Price-history endpoint (GET /services/{id}/partners/{pid}/history)
// ---------------------------------------------------------------------------

interface PriceHistoryPoint {
  effective_date: string | null;
  price_resident_kzt: Money;
  price_nonresident_kzt: Money;
  is_anomaly: boolean;
  version?: number;
}

async function fetchPriceHistory(
  serviceId: string,
  partnerId: string,
): Promise<PriceHistoryPoint[]> {
  const res = await fetch(
    `${API_BASE}/services/${encodeURIComponent(serviceId)}/partners/${encodeURIComponent(
      partnerId,
    )}/history`,
  );
  if (!res.ok) throw new Error(`Price history request failed (${res.status})`);
  return (await res.json()) as PriceHistoryPoint[];
}

/** Recharts dot that paints a red marker on points flagged as a >50% anomaly. */
function AnomalyDot(props: {
  cx?: number;
  cy?: number;
  payload?: { is_anomaly?: boolean };
}) {
  const { cx, cy, payload } = props;
  if (cx == null || cy == null) return null;
  if (payload?.is_anomaly) {
    // A diamond (not just a red circle) so an anomaly is distinguishable by
    // SHAPE, not colour alone — colour-blind-safe, alongside the text caption.
    const r = 6.5;
    return (
      <polygon
        points={`${cx},${cy - r} ${cx + r},${cy} ${cx},${cy + r} ${cx - r},${cy}`}
        fill="#dc2626"
        stroke="#fff"
        strokeWidth={1.5}
      />
    );
  }
  return <circle cx={cx} cy={cy} r={3.5} fill="#0e7490" />;
}

function PriceHistoryChart({
  serviceId,
  partnerId,
}: {
  serviceId: string;
  partnerId: string;
}) {
  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['price-history', serviceId, partnerId],
    queryFn: () => fetchPriceHistory(serviceId, partnerId),
    enabled: Boolean(serviceId && partnerId),
  });

  const points = useMemo(
    () =>
      (data ?? []).map((p) => ({
        label: formatDate(p.effective_date),
        resident: toNumber(p.price_resident_kzt),
        nonresident: toNumber(p.price_nonresident_kzt),
        is_anomaly: p.is_anomaly,
        version: p.version,
      })),
    [data],
  );

  const hasAnomaly = points.some((p) => p.is_anomaly);
  const anomalyCount = points.filter((p) => p.is_anomaly).length;
  const chartSummary =
    `График динамики цен: ${points.length} точек. ` +
    (anomalyCount > 0
      ? `Аномалий цены: ${anomalyCount} (изменение более 50% от предыдущей версии).`
      : 'Аномалий цены не обнаружено.');

  if (isLoading) return <Loading label="Загрузка истории цен…" />;
  if (isError) return <ErrorState error={error} onRetry={() => refetch()} />;
  if (points.length === 0) {
    return (
      <EmptyState icon="📈" title="История цен пока отсутствует">
        Как только будет загружено более одного прайс-листа с датами для этого партнёра,
        здесь появится динамика цен.
      </EmptyState>
    );
  }

  return (
    <div>
      <div role="img" aria-label={chartSummary}>
      <ResponsiveContainer width="100%" height={320}>
        <LineChart data={points} margin={{ top: 16, right: 24, bottom: 8, left: 8 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(0,0,0,0.08)" />
          <XAxis dataKey="label" fontSize={12} />
          <YAxis
            width={72}
            fontSize={12}
            tickFormatter={(v: number) => formatInt(v)}
          />
          <Tooltip
            formatter={(value, name) => [formatKzt(value as Money), name]}
            labelFormatter={(label) => `Актуально с: ${String(label)}`}
          />
          <Legend />
          <Line
            type="monotone"
            dataKey="resident"
            name="Резидент (₸)"
            stroke="#0e7490"
            strokeWidth={2}
            dot={<AnomalyDot />}
            activeDot={{ r: 6 }}
            connectNulls
          />
          <Line
            type="monotone"
            dataKey="nonresident"
            name="Нерезидент (₸)"
            stroke="#94a3b8"
            strokeWidth={2}
            strokeDasharray="5 3"
            dot={<AnomalyDot />}
            connectNulls
          />
        </LineChart>
      </ResponsiveContainer>
      </div>
      <p className="muted" style={{ marginTop: 8, fontSize: 13 }}>
        {hasAnomaly ? (
          <>
            <span style={{ color: '#dc2626', fontWeight: 600 }}>◆ Красный ромб</span> обозначает
            аномалию цены — изменение более чем на 50% по сравнению с предыдущей версией,
            требует проверки.
          </>
        ) : (
          'Аномалий цен для этого партнёра не обнаружено. Красный ромб отметил бы любой скачок >50%.'
        )}
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

function ServicePartnersPageInner() {
  const { id = '' } = useParams();
  const { data, loading, error, reload } = useFetch<PartnerPriceOut[]>(
    () => api.getServicePartners(id),
    [id],
  );
  const [sort, setSort] = useState<SortState>({ key: 'price_resident_kzt', dir: 'asc' });
  const [pickedPartner, setPickedPartner] = useState<string>('');

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

  // Catalogue path of the matched service (Лаборатория › Анализ крови › …),
  // shown as a breadcrumb above the title when the catalogue carries hierarchy.
  const categoryPath = useMemo(
    () => rows.find((r) => r.category_path && r.category_path.length)?.category_path ?? [],
    [rows],
  );

  // Default the history chart to the first (cheapest) partner once data lands.
  const activePartnerId = useMemo(() => {
    if (pickedPartner && rows.some((r) => String(r.partner.partner_id) === pickedPartner)) {
      return pickedPartner;
    }
    return rows[0] ? String(rows[0].partner.partner_id) : '';
  }, [pickedPartner, rows]);

  const columns: Column<PartnerPriceOut>[] = [
    {
      key: 'partner',
      header: 'Партнёр',
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
      header: 'Резидент',
      numeric: true,
      sortable: true,
      render: (r) => <PriceTag value={r.price_resident_kzt} />,
    },
    {
      key: 'price_nonresident_kzt',
      header: 'Нерезидент',
      numeric: true,
      sortable: true,
      render: (r) => <PriceTag value={r.price_nonresident_kzt} />,
    },
    {
      key: 'effective_date',
      header: 'Актуально с',
      sortable: true,
      render: (r) => <span className="muted">{formatDate(r.effective_date)}</span>,
    },
    {
      key: 'match_confidence',
      header: 'Уверенность',
      numeric: true,
      render: (r) => {
        const c = toNumber(r.match_confidence as number | string | null);
        const tone = c === null ? 'neutral' : c >= 0.85 ? 'success' : c >= 0.6 ? 'warning' : 'danger';
        return <Badge tone={tone}>{formatConfidence(r.match_confidence as number | string | null)}</Badge>;
      },
    },
    {
      key: 'is_verified',
      header: 'Статус',
      render: (r) => <VerifiedBadge verified={r.is_verified} />,
    },
  ];

  const activePartnerName = rows.find(
    (r) => String(r.partner.partner_id) === activePartnerId,
  )?.partner.name;

  return (
    <main className="page">
      <Link to="/services" className="back-link">
        ← Все услуги
      </Link>

      {loading ? (
        <Loading label="Загрузка партнёров…" />
      ) : error ? (
        <ErrorState error={error} onRetry={reload} />
      ) : (
        <>
          <header className="page-header">
            <div className="eyebrow">Услуга</div>
            {categoryPath.length > 0 && (
              <nav className="breadcrumb" aria-label="Категория услуги">
                {categoryPath.map((crumb, i) => (
                  <span key={`${crumb}-${i}`}>
                    {i > 0 && <span className="crumb-sep" aria-hidden="true">›</span>}
                    <span className="crumb">{crumb}</span>
                  </span>
                ))}
              </nav>
            )}
            <h1>{serviceName}</h1>
            <p className="subtitle">
              {rows.length} {rows.length === 1 ? 'партнёр предоставляет' : 'партнёров предоставляют'} эту услугу. Сортируйте по цене для сравнения.
            </p>
          </header>

          {rows.length === 0 ? (
            <EmptyState icon="🏥" title="Пока нет партнёров, предлагающих эту услугу">
              Как только будут загружены прайс-листы, ссылающиеся на эту услугу, здесь появятся партнёры.
            </EmptyState>
          ) : (
            <>
              <DataTable<PartnerPriceOut>
                columns={columns}
                rows={rows}
                rowKey={(r) => String(r.item_id)}
                sort={sort}
                onSort={toggleSort}
              />

              <section className="card" style={{ marginTop: 24 }}>
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'baseline',
                    justifyContent: 'space-between',
                    flexWrap: 'wrap',
                    gap: 12,
                    marginBottom: 12,
                  }}
                >
                  <div>
                    <div className="eyebrow">История цен</div>
                    <h2 style={{ margin: '4px 0 0' }}>Динамика цен</h2>
                  </div>
                  <label style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span className="muted" style={{ fontSize: 13 }}>
                      Партнёр
                    </span>
                    <select
                      className="select"
                      value={activePartnerId}
                      onChange={(e) => setPickedPartner(e.target.value)}
                    >
                      {rows.map((r) => (
                        <option key={String(r.item_id)} value={String(r.partner.partner_id)}>
                          {r.partner.name}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>

                {activePartnerId ? (
                  <PriceHistoryChart
                    key={activePartnerId}
                    serviceId={String(id)}
                    partnerId={activePartnerId}
                  />
                ) : null}

                {activePartnerName ? (
                  <p className="muted" style={{ fontSize: 13, marginTop: 4 }}>
                    Полная история версий для{' '}
                    <strong>{activePartnerName}</strong>.
                  </p>
                ) : null}
              </section>
            </>
          )}
        </>
      )}
    </main>
  );
}

export function ServicePartnersPage() {
  return (
    <QueryClientProvider client={queryClient}>
      <ServicePartnersPageInner />
    </QueryClientProvider>
  );
}
