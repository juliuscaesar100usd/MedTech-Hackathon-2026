import { Link } from 'react-router-dom';
import { api } from '../../lib/api';
import type { DashboardStats, BatchOut } from '../../lib/api';
import { useFetch } from '../../lib/useFetch';
import { Loading, ErrorState, EmptyState } from '../../components/States';
import { Card } from '../../components/Card';
import { StatusBadge } from '../../components/Badge';
import { formatInt, formatPercent, formatDateTime } from '../../lib/format';

export function DashboardPage() {
  const { data, loading, error, reload } = useFetch<DashboardStats>(() => api.getDashboard(), []);

  if (loading) return <Loading label="Loading dashboard…" />;
  if (error) return <ErrorState error={error} onRetry={reload} />;
  if (!data) return null;

  const queueTotal = (data.items_needs_review ?? 0) + (data.items_unmatched ?? 0);

  return (
    <section>
      <div className="row between wrap" style={{ marginBottom: 16 }}>
        <h2 style={{ margin: 0 }}>Overview</h2>
        <button className="btn btn-secondary btn-sm" onClick={reload}>
          ↻ Refresh
        </button>
      </div>

      {/* Headline stat cards */}
      <div className="stat-grid">
        <Stat label="Documents processed" value={formatInt(data.documents_done)}
          sub={`${formatInt(data.documents)} total · ${formatInt(data.documents_error)} errors`} />
        <Stat
          label="Normalization rate"
          value={formatPercent(data.normalization_rate)}
          sub={`${formatInt(data.items_matched_auto + data.items_matched_manual)} of ${formatInt(
            data.price_items,
          )} items`}
          accent
        />
        <Stat
          label="Auto-normalization"
          value={formatPercent(data.auto_normalization_rate)}
          sub={`${formatInt(data.items_matched_auto)} auto-matched`}
        />
        <Stat
          label="Verification rate"
          value={formatPercent(data.verification_rate)}
          sub={`${formatInt(data.items_verified)} verified`}
        />
        <Stat
          label="Needs review"
          value={formatInt(data.items_needs_review)}
          sub="awaiting verification"
          tone={data.items_needs_review > 0 ? 'warn' : undefined}
          to="/admin/verification"
        />
        <Stat
          label="Unmatched"
          value={formatInt(data.items_unmatched)}
          sub="no catalog match"
          tone={data.items_unmatched > 0 ? 'danger' : undefined}
          to="/admin/unmatched"
        />
      </div>

      {/* Secondary counters */}
      <div className="stat-grid">
        <Stat label="Partners" value={formatInt(data.partners)} to="/partners" />
        <Stat label="Services" value={formatInt(data.services)} to="/services" />
        <Stat label="Price items" value={formatInt(data.price_items)} />
        <Stat
          label="With anomalies"
          value={formatInt(data.items_with_anomalies)}
          tone={data.items_with_anomalies > 0 ? 'warn' : undefined}
        />
        <Stat label="Queue total" value={formatInt(queueTotal)} sub="review + unmatched" />
        <Stat label="Pending docs" value={formatInt(data.documents_pending)} />
      </div>

      {/* Distributions */}
      <div className="card-grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))' }}>
        <Card>
          <h3>By category</h3>
          <BarList data={data.by_category} emptyLabel="No category data yet." />
        </Card>
        <Card>
          <h3>By city</h3>
          <BarList data={data.by_city} emptyLabel="No city data yet." />
        </Card>
      </div>

      <div className="section" />

      <Card>
        <h3>Recent batches</h3>
        <RecentBatches batches={data.recent_batches} />
      </Card>
    </section>
  );
}

function Stat({
  label,
  value,
  sub,
  accent,
  tone,
  to,
}: {
  label: string;
  value: string;
  sub?: string;
  accent?: boolean;
  tone?: 'warn' | 'danger';
  to?: string;
}) {
  const cls = ['stat-card', accent ? 'accent' : '', tone || ''].filter(Boolean).join(' ');
  const inner = (
    <>
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value}</div>
      {sub && <div className="stat-sub">{sub}</div>}
    </>
  );
  if (to)
    return (
      <Link to={to} className={cls} style={{ display: 'block', textDecoration: 'none' }}>
        {inner}
      </Link>
    );
  return <div className={cls}>{inner}</div>;
}

function BarList({ data, emptyLabel }: { data: Record<string, number>; emptyLabel: string }) {
  const entries = Object.entries(data || {})
    .filter(([, v]) => Number.isFinite(v))
    .sort((a, b) => b[1] - a[1])
    .slice(0, 10);

  if (entries.length === 0) return <p className="faint">{emptyLabel}</p>;

  const max = Math.max(...entries.map(([, v]) => v), 1);

  return (
    <div className="bar-list">
      {entries.map(([name, value]) => (
        <div className="bar-row" key={name}>
          <div className="bar-head">
            <span className="bar-name">{name}</span>
            <span className="bar-val">{formatInt(value)}</span>
          </div>
          <div className="bar-track">
            <div className="bar-fill" style={{ width: `${(value / max) * 100}%` }} />
          </div>
        </div>
      ))}
    </div>
  );
}

function RecentBatches({ batches }: { batches: BatchOut[] }) {
  if (!batches || batches.length === 0)
    return (
      <EmptyState icon="📦" title="No batches yet">
        Upload an archive to see ingestion batches here.
      </EmptyState>
    );

  return (
    <div className="table-wrap" style={{ marginTop: 12 }}>
      <table className="data-table">
        <thead>
          <tr>
            <th>Batch</th>
            <th>Archive</th>
            <th>Status</th>
            <th className="num">Files (done / total)</th>
            <th>Created</th>
          </tr>
        </thead>
        <tbody>
          {batches.map((b) => (
            <tr key={String(b.batch_id)}>
              <td className="mono">#{b.batch_id}</td>
              <td className="cell-strong">{b.archive_name || '—'}</td>
              <td>
                <StatusBadge status={b.status} />
              </td>
              <td className="num mono">
                {formatInt(b.processed_files)} / {formatInt(b.total_files)}
                {b.error_files ? ` (${formatInt(b.error_files)} err)` : ''}
              </td>
              <td className="faint">{formatDateTime(b.created_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
