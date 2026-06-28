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
import { CheckCircle, Warning } from '@phosphor-icons/react';

function errMessage(err: unknown): string {
  if (err instanceof ApiError)
    return err.status === 0 ? 'Не удалось связаться с API.' : `${err.message} (HTTP ${err.status})`;
  if (err instanceof Error) return err.message;
  return 'Действие не выполнено.';
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
          {items.length}{' '}
          {items.length % 100 >= 11 && items.length % 100 <= 14
            ? 'позиций'
            : items.length % 10 === 1
            ? 'позиция'
            : items.length % 10 >= 2 && items.length % 10 <= 4
            ? 'позиции'
            : 'позиций'}{' '}
          на проверке
        </p>
        <button className="btn btn-secondary btn-sm" onClick={reload}>
          ↻ Обновить
        </button>
      </div>

      {loading ? (
        <Loading label="Загрузка очереди верификации…" />
      ) : error ? (
        <ErrorState error={error} onRetry={reload} />
      ) : items.length === 0 ? (
        <EmptyState icon={<CheckCircle weight="duotone" />} title="Очередь пуста">
          Нет позиций, требующих ручной проверки.
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
    if (!approve && !window.confirm('Отклонить эту позицию? Действие нельзя отменить.')) {
      return;
    }
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
      toast.success(approve ? 'Подтверждено.' : 'Отклонено.');
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
            <h2 style={{ marginBottom: 0, fontSize: 18 }}>
              {item.service_name_raw || `Позиция #${item.item_id}`}
            </h2>
            <VerifiedBadge verified={item.is_verified} />
          </div>
          <div className="cell-sub" style={{ marginTop: 4 }}>
            {item.partner_name || 'Партнёр не указан'}
            {item.effective_date ? ` · актуально с ${formatDate(item.effective_date)}` : ''}
            {item.currency_original ? ` · ${item.currency_original}` : ''}
          </div>
        </div>
        <div className="faint mono">позиция #{item.item_id}</div>
      </div>

      {anomalies.length > 0 && (
        <div className="tag-list" style={{ marginTop: 12 }}>
          {anomalies.map((a) => (
            <Badge key={a} tone="danger">
              <Warning size={12} weight="fill" aria-hidden="true" style={{ verticalAlign: '-1px', marginRight: 4 }} />
              {a}
            </Badge>
          ))}
        </div>
      )}

      <div className="divider" />

      <div className="row wrap" style={{ gap: 24, alignItems: 'flex-start' }}>
        <div>
          <span className="pricetag-label">Цена для резидента (извлечено)</span>
          <PriceTag value={item.price_resident_kzt} />
        </div>
        <div>
          <span className="pricetag-label">Цена для нерезидента (извлечено)</span>
          <PriceTag value={item.price_nonresident_kzt} />
        </div>
        <div>
          <span className="pricetag-label">Предложенное сопоставление</span>
          <div>
            {item.service_name ? (
              <Badge tone="primary">{item.service_name}</Badge>
            ) : (
              <Badge tone="warning">нет предложения</Badge>
            )}
          </div>
        </div>
      </div>

      <div className="divider" />

      <div className="filters" style={{ marginBottom: 0 }}>
        <label className="field">
          <span className="field-label">Цена для резидента (₸)</span>
          <input
            className="input"
            type="number"
            value={priceRes}
            onChange={(e) => setPriceRes(e.target.value)}
            placeholder="—"
          />
        </label>
        <label className="field">
          <span className="field-label">Цена для нерезидента (₸)</span>
          <input
            className="input"
            type="number"
            value={priceNon}
            onChange={(e) => setPriceNon(e.target.value)}
            placeholder="—"
          />
        </label>
        <label className="field">
          <span className="field-label">ID услуги (изменить)</span>
          <input
            className="input"
            value={serviceId}
            onChange={(e) => setServiceId(e.target.value)}
            placeholder="(оставить предложенное)"
          />
        </label>
        <label className="field grow">
          <span className="field-label">Примечание (необязательно)</span>
          <input
            className="input"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Причина / комментарий"
          />
        </label>
      </div>

      <div className="btn-row" style={{ marginTop: 16 }}>
        <button className="btn btn-success" disabled={busy !== null} onClick={() => submit(true)}>
          {busy === 'approve' ? <Spinner /> : null} Подтвердить
        </button>
        <button className="btn btn-danger" disabled={busy !== null} onClick={() => submit(false)}>
          {busy === 'reject' ? <Spinner /> : null} Отклонить
        </button>
      </div>
    </Card>
  );
}
