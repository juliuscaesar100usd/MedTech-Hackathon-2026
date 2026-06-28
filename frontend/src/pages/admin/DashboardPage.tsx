import { Link } from 'react-router-dom';
import { api } from '../../lib/api';
import type { DashboardStats, BatchOut } from '../../lib/api';
import { useFetch } from '../../lib/useFetch';
import { Loading, ErrorState, EmptyState } from '../../components/States';
import { Card } from '../../components/Card';
import { StatusBadge } from '../../components/Badge';
import { formatInt, formatPercent, formatDateTime } from '../../lib/format';
import { Package } from '@phosphor-icons/react';

export function DashboardPage() {
  const { data, loading, error, reload } = useFetch<DashboardStats>(() => api.getDashboard(), []);

  if (loading) return <Loading label="Загрузка дашборда…" />;
  if (error) return <ErrorState error={error} onRetry={reload} />;
  if (!data) return null;

  const queueTotal = (data.items_needs_review ?? 0) + (data.items_unmatched ?? 0);

  return (
    <section>
      <div className="row between wrap" style={{ marginBottom: 16 }}>
        <h2 style={{ margin: 0 }}>Обзор</h2>
        <button className="btn btn-secondary btn-sm" onClick={reload}>
          ↻ Обновить
        </button>
      </div>

      {/* Headline stat cards */}
      <div className="stat-grid">
        <Stat label="Обработано документов" value={formatInt(data.documents_done)}
          sub={`${formatInt(data.documents)} всего · ${formatInt(data.documents_error)} ошибок`} />
        <Stat
          label="Уровень нормализации"
          value={formatPercent(data.normalization_rate)}
          sub={`${formatInt(data.items_matched_auto + data.items_matched_manual)} из ${formatInt(
            data.price_items,
          )} позиций`}
          accent
        />
        <Stat
          label="Авто-нормализация"
          value={formatPercent(data.auto_normalization_rate)}
          sub={`${formatInt(data.items_matched_auto)} авто-сопоставлено`}
        />
        <Stat
          label="Уровень верификации"
          value={formatPercent(data.verification_rate)}
          sub={`${formatInt(data.items_verified)} проверено`}
        />
        <Stat
          label="Требует проверки"
          value={formatInt(data.items_needs_review)}
          sub="ожидает верификации"
          tone={data.items_needs_review > 0 ? 'warn' : undefined}
          to="/admin/verification"
        />
        <Stat
          label="Несопоставленные"
          value={formatInt(data.items_unmatched)}
          sub="нет совпадения в каталоге"
          tone={data.items_unmatched > 0 ? 'danger' : undefined}
          to="/admin/unmatched"
        />
      </div>

      {/* Secondary counters */}
      <div className="stat-grid">
        <Stat label="Партнёры" value={formatInt(data.partners)} to="/partners" />
        <Stat label="Услуги" value={formatInt(data.services)} to="/services" />
        <Stat label="Позиции" value={formatInt(data.price_items)} />
        <Stat
          label="С аномалиями"
          value={formatInt(data.items_with_anomalies)}
          tone={data.items_with_anomalies > 0 ? 'warn' : undefined}
        />
        <Stat label="Итого в очереди" value={formatInt(queueTotal)} sub="проверка + несопоставленные" />
        <Stat label="Документы в очереди" value={formatInt(data.documents_pending)} />
      </div>

      {/* Distributions */}
      <div className="card-grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))' }}>
        <Card>
          <h3>По категориям</h3>
          <BarList data={data.by_category} emptyLabel="Нет данных по категориям." />
        </Card>
        <Card>
          <h3>По городам</h3>
          <BarList data={data.by_city} emptyLabel="Нет данных по городам." />
        </Card>
      </div>

      <div className="section" />

      <Card>
        <h3>Последние пакеты</h3>
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
      <EmptyState icon={<Package weight="duotone" />} title="Нет пакетов">
        Загрузите архив, чтобы увидеть здесь пакеты загрузки.
      </EmptyState>
    );

  return (
    <div className="table-wrap" style={{ marginTop: 12 }}>
      <table className="data-table">
        <thead>
          <tr>
            <th>Пакет</th>
            <th>Архив</th>
            <th>Статус</th>
            <th className="num">Файлы (готово / всего)</th>
            <th>Создан</th>
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
                {b.error_files ? ` (${formatInt(b.error_files)} ош.)` : ''}
              </td>
              <td className="faint">{formatDateTime(b.created_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
