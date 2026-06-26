import { useState } from 'react';
import { api, ApiError } from '../../lib/api';
import type { VerificationItemOut } from '../../lib/api';
import { useFetch } from '../../lib/useFetch';
import { Loading, ErrorState, EmptyState, Spinner } from '../../components/States';
import { Card } from '../../components/Card';
import { Badge, VerifiedBadge } from '../../components/Badge';
import { PriceTag } from '../../components/PriceTag';
import { useToast } from '../../components/Toast';
import { formatDate, toNumber } from '../../lib/format';

function errMessage(err: unknown): string {
  if (err instanceof ApiError)
    return err.status === 0 ? 'Could not reach the API.' : `${err.message} (HTTP ${err.status})`;
  if (err instanceof Error) return err.message;
  return 'Action failed.';
}

export function VerificationQueuePage() {
  const { data, loading, error, reload, setData } = useFetch<VerificationItemOut[]>(
    () => api.getVerification(100, 0),
    [],
  );

  const items = data ?? [];

  function removeItem(itemId: string | number) {
    setData((cur) => (cur ? cur.filter((it) => String(it.item_id) !== String(itemId)) : cur));
  }

  return (
    <section>
      <div className="row between wrap" style={{ marginBottom: 16 }}>
        <p className="faint" style={{ margin: 0 }}>
          {items.length} item{items.length === 1 ? '' : 's'} awaiting review
        </p>
        <button className="btn btn-secondary btn-sm" onClick={reload}>
          ↻ Refresh
        </button>
      </div>

      {loading ? (
        <Loading label="Loading verification queue…" />
      ) : error ? (
        <ErrorState error={error} onRetry={reload} />
      ) : items.length === 0 ? (
        <EmptyState icon="✅" title="Queue is clear">
          No price items currently need manual verification.
        </EmptyState>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {items.map((item) => (
            <VerificationRow key={String(item.item_id)} item={item} onResolved={removeItem} />
          ))}
        </div>
      )}
    </section>
  );
}

function VerificationRow({
  item,
  onResolved,
}: {
  item: VerificationItemOut;
  onResolved: (itemId: string | number) => void;
}) {
  const toast = useToast();
  const [busy, setBusy] = useState<null | 'approve' | 'reject'>(null);
  const [priceRes, setPriceRes] = useState<string>(
    toNumber(item.price_resident_kzt) !== null ? String(toNumber(item.price_resident_kzt)) : '',
  );
  const [priceNon, setPriceNon] = useState<string>(
    toNumber(item.price_nonresident_kzt) !== null
      ? String(toNumber(item.price_nonresident_kzt))
      : '',
  );
  const [serviceId, setServiceId] = useState<string>(
    item.service_id != null ? String(item.service_id) : '',
  );
  const [note, setNote] = useState('');

  const anomalies = item.anomaly_flags ?? [];

  async function submit(approve: boolean) {
    setBusy(approve ? 'approve' : 'reject');
    try {
      const res = toNumber(priceRes);
      const non = toNumber(priceNon);
      await api.verify({
        item_id: item.item_id,
        approve,
        service_id: serviceId.trim() ? serviceId.trim() : undefined,
        price_resident_kzt: res !== null ? res : undefined,
        price_nonresident_kzt: non !== null ? non : undefined,
        note: note.trim() || undefined,
        operator: 'web-admin',
      });
      toast.success(approve ? 'Approved.' : 'Rejected.');
      onResolved(item.item_id);
    } catch (err) {
      toast.error(errMessage(err));
    } finally {
      setBusy(null);
    }
  }

  return (
    <Card>
      <div className="row between wrap" style={{ alignItems: 'flex-start' }}>
        <div>
          <div className="row wrap" style={{ gap: 8 }}>
            <h3 style={{ marginBottom: 0 }}>
              {item.service_name_raw || `Item #${item.item_id}`}
            </h3>
            <VerifiedBadge verified={item.is_verified} />
          </div>
          <div className="cell-sub" style={{ marginTop: 4 }}>
            {item.partner_name || 'Unknown partner'}
            {item.effective_date ? ` · effective ${formatDate(item.effective_date)}` : ''}
            {item.currency_original ? ` · ${item.currency_original}` : ''}
          </div>
        </div>
        <div className="faint mono">item #{item.item_id}</div>
      </div>

      {anomalies.length > 0 && (
        <div className="tag-list" style={{ marginTop: 12 }}>
          {anomalies.map((a) => (
            <Badge key={a} tone="danger">
              ⚠ {a}
            </Badge>
          ))}
        </div>
      )}

      <div className="divider" />

      <div className="row wrap" style={{ gap: 24, alignItems: 'flex-start' }}>
        <div>
          <span className="pricetag-label">Extracted resident</span>
          <PriceTag value={item.price_resident_kzt} />
        </div>
        <div>
          <span className="pricetag-label">Extracted non-resident</span>
          <PriceTag value={item.price_nonresident_kzt} />
        </div>
        <div>
          <span className="pricetag-label">Proposed match</span>
          <div>
            {item.service_name ? (
              <Badge tone="primary">{item.service_name}</Badge>
            ) : (
              <Badge tone="warning">no proposal</Badge>
            )}
          </div>
        </div>
      </div>

      <div className="divider" />

      <div className="filters" style={{ marginBottom: 0 }}>
        <div className="field">
          <label className="field-label">Resident price (₸)</label>
          <input
            className="input"
            type="number"
            value={priceRes}
            onChange={(e) => setPriceRes(e.target.value)}
            placeholder="—"
          />
        </div>
        <div className="field">
          <label className="field-label">Non-resident price (₸)</label>
          <input
            className="input"
            type="number"
            value={priceNon}
            onChange={(e) => setPriceNon(e.target.value)}
            placeholder="—"
          />
        </div>
        <div className="field">
          <label className="field-label">Override service ID</label>
          <input
            className="input"
            value={serviceId}
            onChange={(e) => setServiceId(e.target.value)}
            placeholder="(keep proposed)"
          />
        </div>
        <div className="field grow">
          <label className="field-label">Note (optional)</label>
          <input
            className="input"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Reason / comment"
          />
        </div>
      </div>

      <div className="btn-row" style={{ marginTop: 16 }}>
        <button className="btn btn-success" disabled={busy !== null} onClick={() => submit(true)}>
          {busy === 'approve' ? <Spinner /> : null} Approve
        </button>
        <button className="btn btn-danger" disabled={busy !== null} onClick={() => submit(false)}>
          {busy === 'reject' ? <Spinner /> : null} Reject
        </button>
      </div>
    </Card>
  );
}
