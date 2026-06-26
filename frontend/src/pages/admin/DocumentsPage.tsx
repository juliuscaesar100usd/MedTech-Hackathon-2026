import { useEffect, useState } from 'react';
import { api } from '../../lib/api';
import type { PriceDocumentOut } from '../../lib/api';
import { useFetch } from '../../lib/useFetch';
import { Loading, ErrorState, EmptyState, Spinner } from '../../components/States';
import { DataTable, type Column } from '../../components/DataTable';
import { StatusBadge, Badge } from '../../components/Badge';
import { formatDate, formatDateTime, formatInt } from '../../lib/format';

const STATUS_OPTIONS = ['', 'pending', 'processing', 'done', 'error'];

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
      header: 'File',
      render: (d) => (
        <div>
          <span className="cell-strong">{d.file_name || `Doc #${d.doc_id}`}</span>
          <div className="cell-sub">
            {d.batch_id != null && <>batch #{d.batch_id} · </>}
            {d.partner_id != null ? `partner #${d.partner_id}` : 'unassigned partner'}
          </div>
        </div>
      ),
    },
    {
      key: 'file_format',
      header: 'Format',
      render: (d) => (d.file_format ? <Badge tone="neutral">{d.file_format}</Badge> : '—'),
    },
    {
      key: 'parse_status',
      header: 'Status',
      render: (d) => <StatusBadge status={d.parse_status} />,
    },
    {
      key: 'language',
      header: 'Lang',
      render: (d) => <span className="muted">{d.language || '—'}</span>,
    },
    {
      key: 'items',
      header: 'Matched / Items',
      numeric: true,
      render: (d) => (
        <span className="mono">
          {formatInt(d.n_matched)} / {formatInt(d.n_items)}
        </span>
      ),
    },
    {
      key: 'effective_date',
      header: 'Effective',
      render: (d) => <span className="muted">{formatDate(d.effective_date)}</span>,
    },
    {
      key: 'parsed_at',
      header: 'Parsed at',
      render: (d) => <span className="faint">{formatDateTime(d.parsed_at)}</span>,
    },
  ];

  return (
    <section>
      <div className="row between wrap" style={{ marginBottom: 18 }}>
        <div className="field" style={{ minWidth: 220 }}>
          <label className="field-label" htmlFor="doc-status">
            Filter by status
          </label>
          <select
            id="doc-status"
            className="select"
            value={status}
            onChange={(e) => setStatus(e.target.value)}
          >
            {STATUS_OPTIONS.map((s) => (
              <option key={s} value={s}>
                {s === '' ? 'All statuses' : s}
              </option>
            ))}
          </select>
        </div>
        <div className="row" style={{ alignSelf: 'flex-end' }}>
          {anyPending && (
            <span className="row" style={{ gap: 6 }}>
              <Spinner />
              <span className="faint">auto-refreshing…</span>
            </span>
          )}
          <button className="btn btn-secondary btn-sm" onClick={reload}>
            ↻ Refresh
          </button>
        </div>
      </div>

      {loading && docs.length === 0 ? (
        <Loading label="Loading documents…" />
      ) : error ? (
        <ErrorState error={error} onRetry={reload} />
      ) : docs.length === 0 ? (
        <EmptyState icon="📄" title="No documents">
          Upload an archive to populate this list.
        </EmptyState>
      ) : (
        <>
          <p className="faint" style={{ marginBottom: 10 }}>
            {docs.length} document{docs.length === 1 ? '' : 's'}
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
