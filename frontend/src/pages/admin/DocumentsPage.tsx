import { useEffect, useState } from 'react';
import { api } from '../../lib/api';
import type { PriceDocumentOut } from '../../lib/api';
import { useFetch } from '../../lib/useFetch';
import { Loading, ErrorState, EmptyState, Spinner } from '../../components/States';
import { DataTable, type Column } from '../../components/DataTable';
import { StatusBadge, Badge } from '../../components/Badge';
import { formatDate, formatDateTime, formatInt } from '../../lib/format';
import { FileText } from '@phosphor-icons/react';

const STATUS_OPTIONS = ['', 'pending', 'processing', 'done', 'error'];

const STATUS_LABELS: Record<string, string> = {
  '': 'Все статусы',
  pending: 'в очереди',
  processing: 'обработка',
  done: 'готово',
  error: 'ошибка',
};

function isPending(status: string | null | undefined): boolean {
  const s = (status || '').toLowerCase();
  return /pending|processing|queued|running/.test(s);
}

export function DocumentsPage() {
  const [status, setStatus] = useState('');
  const { data, loading, error, reload } = useFetch<PriceDocumentOut[]>(
    () => api.getDocuments({ status: status || undefined, limit: 200 }),
    [status],
  );

  const docs = data ?? [];
  const anyPending = docs.some((d) => isPending(d.parse_status));

  // Light auto-refresh every ~4s while any doc is still being processed.
  useEffect(() => {
    if (!anyPending) return;
    const t = window.setInterval(reload, 4000);
    return () => window.clearInterval(t);
  }, [anyPending, reload]);

  const columns: Column<PriceDocumentOut>[] = [
    {
      key: 'file_name',
      header: 'Файл',
      render: (d) => (
        <div>
          <span className="cell-strong">{d.file_name || `Документ #${d.doc_id}`}</span>
          <div className="cell-sub">
            {d.batch_id != null && <>пакет #{d.batch_id} · </>}
            {d.partner_id != null ? `партнёр #${d.partner_id}` : 'партнёр не назначен'}
          </div>
        </div>
      ),
    },
    {
      key: 'file_format',
      header: 'Формат',
      render: (d) => (d.file_format ? <Badge tone="neutral">{d.file_format}</Badge> : '—'),
    },
    {
      key: 'parse_status',
      header: 'Статус',
      render: (d) => <StatusBadge status={d.parse_status} />,
    },
    {
      key: 'language',
      header: 'Язык',
      render: (d) => <span className="muted">{d.language || '—'}</span>,
    },
    {
      key: 'items',
      header: 'Сопоставлено / Позиций',
      numeric: true,
      render: (d) => (
        <span className="mono">
          {formatInt(d.n_matched)} / {formatInt(d.n_items)}
        </span>
      ),
    },
    {
      key: 'effective_date',
      header: 'Актуально с',
      render: (d) => <span className="muted">{formatDate(d.effective_date)}</span>,
    },
    {
      key: 'parsed_at',
      header: 'Обработано в',
      render: (d) => <span className="faint">{formatDateTime(d.parsed_at)}</span>,
    },
  ];

  return (
    <section>
      <div className="row between wrap" style={{ marginBottom: 18 }}>
        <div className="field" style={{ minWidth: 220 }}>
          <label className="field-label" htmlFor="doc-status">
            Фильтр по статусу
          </label>
          <select
            id="doc-status"
            className="select"
            value={status}
            onChange={(e) => setStatus(e.target.value)}
          >
            {STATUS_OPTIONS.map((s) => (
              <option key={s} value={s}>
                {STATUS_LABELS[s] ?? s}
              </option>
            ))}
          </select>
        </div>
        <div className="row" style={{ alignSelf: 'flex-end' }}>
          {anyPending && (
            <span className="row" style={{ gap: 6 }}>
              <Spinner />
              <span className="faint">автообновление…</span>
            </span>
          )}
          <button className="btn btn-secondary btn-sm" onClick={reload}>
            ↻ Обновить
          </button>
        </div>
      </div>

      {loading && docs.length === 0 ? (
        <Loading label="Загрузка документов…" />
      ) : error ? (
        <ErrorState error={error} onRetry={reload} />
      ) : docs.length === 0 ? (
        <EmptyState icon={<FileText weight="duotone" />} title="Нет документов">
          Загрузите архив, чтобы заполнить список.
        </EmptyState>
      ) : (
        <>
          <p className="faint" style={{ marginBottom: 10 }}>
            {docs.length}{' '}
            {docs.length % 100 >= 11 && docs.length % 100 <= 14
              ? 'документов'
              : docs.length % 10 === 1
              ? 'документ'
              : docs.length % 10 >= 2 && docs.length % 10 <= 4
              ? 'документа'
              : 'документов'}
          </p>
          <DataTable<PriceDocumentOut>
            columns={columns}
            rows={docs}
            rowKey={(d) => String(d.doc_id)}
          />
        </>
      )}
    </section>
  );
}
