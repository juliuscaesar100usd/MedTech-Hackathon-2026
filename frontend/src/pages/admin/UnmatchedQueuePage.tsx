import { useState } from 'react';
import { api, ApiError } from '../../lib/api';
import type { UnmatchedItemOut, MatchCandidate } from '../../lib/api';
import { useFetch } from '../../lib/useFetch';
import { Loading, ErrorState, EmptyState, Spinner } from '../../components/States';
import { Card } from '../../components/Card';
import { Badge } from '../../components/Badge';
import { PriceTag } from '../../components/PriceTag';
import { useToast } from '../../components/Toast';
import { formatConfidence } from '../../lib/format';

function errMessage(err: unknown): string {
  if (err instanceof ApiError)
    return err.status === 0 ? 'Не удалось связаться с API.' : `${err.message} (HTTP ${err.status})`;
  if (err instanceof Error) return err.message;
  return 'Действие не выполнено.';
}

export function UnmatchedQueuePage() {
  const { data, loading, error, reload, setData } = useFetch<UnmatchedItemOut[]>(
    () => api.getUnmatched(100, 0),
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
            ? 'несопоставленных позиций'
            : items.length % 10 === 1
            ? 'несопоставленная позиция'
            : items.length % 10 >= 2 && items.length % 10 <= 4
            ? 'несопоставленные позиции'
            : 'несопоставленных позиций'}
        </p>
        <button className="btn btn-secondary btn-sm" onClick={reload}>
          ↻ Обновить
        </button>
      </div>

      {loading ? (
        <Loading label="Загрузка несопоставленных позиций…" />
      ) : error ? (
        <ErrorState error={error} onRetry={reload} />
      ) : items.length === 0 ? (
        <EmptyState icon="✅" title="Нет несопоставленных">
          Все загруженные позиции сопоставлены с услугами каталога.
        </EmptyState>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {items.map((item) => (
            <UnmatchedRow key={String(item.item_id)} item={item} onResolved={removeItem} />
          ))}
        </div>
      )}
    </section>
  );
}

function UnmatchedRow({
  item,
  onResolved,
}: {
  item: UnmatchedItemOut;
  onResolved: (itemId: string | number) => void;
}) {
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const [selected, setSelected] = useState<string>('');
  const [creatingNew, setCreatingNew] = useState(false);
  const [newName, setNewName] = useState(item.service_name_raw || '');
  const [newCategory, setNewCategory] = useState('');
  const [newSynonyms, setNewSynonyms] = useState(item.service_name_raw || '');
  const [newIcd, setNewIcd] = useState('');

  const candidates = item.candidates ?? [];

  function pickCandidate(c: MatchCandidate) {
    setCreatingNew(false);
    setSelected(String(c.service_id));
  }

  async function submit() {
    if (!creatingNew && !selected) {
      toast.error('Выберите кандидата или создайте новую услугу.');
      return;
    }
    if (creatingNew && !newName.trim()) {
      toast.error('Укажите название новой услуги.');
      return;
    }
    setBusy(true);
    try {
      await api.match({
        item_id: item.item_id,
        service_id: !creatingNew ? selected : undefined,
        new_service: creatingNew
          ? {
              service_name: newName.trim(),
              synonyms: newSynonyms
                .split(',')
                .map((s) => s.trim())
                .filter(Boolean),
              category: newCategory.trim() || null,
              icd_code: newIcd.trim() || null,
            }
          : undefined,
        operator: 'web-admin',
      });
      toast.success('Сопоставлено.');
      onResolved(item.item_id);
    } catch (err) {
      toast.error(errMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <div className="row between wrap" style={{ alignItems: 'flex-start' }}>
        <div>
          <h2 style={{ marginBottom: 2, fontSize: 18 }}>{item.service_name_raw || `Позиция #${item.item_id}`}</h2>
          <div className="cell-sub">
            {item.partner_name || 'Партнёр не указан'}
            {item.service_code_source ? ` · код ${item.service_code_source}` : ''}
          </div>
        </div>
        <div className="row" style={{ gap: 12 }}>
          <div style={{ textAlign: 'right' }}>
            <span className="pricetag-label">Резидент</span>
            <PriceTag value={item.price_resident_kzt} />
          </div>
          {item.match_status && <Badge tone="danger">{item.match_status}</Badge>}
        </div>
      </div>

      <div className="divider" />

      <div className="field-label" style={{ marginBottom: 8 }}>
        Предложения из каталога
      </div>
      {candidates.length === 0 ? (
        <p className="faint">Автоматических предложений нет — создайте новую услугу ниже.</p>
      ) : (
        <div className="tag-list" style={{ gap: 8, flexDirection: 'column' }}>
          {candidates.map((c) => {
            const active = !creatingNew && selected === String(c.service_id);
            return (
              <button
                key={String(c.service_id)}
                className={`card pad-sm hoverable`}
                style={{
                  textAlign: 'left',
                  cursor: 'pointer',
                  borderColor: active ? 'var(--c-primary-600)' : undefined,
                  background: active ? 'var(--c-primary-50)' : undefined,
                  width: '100%',
                }}
                onClick={() => pickCandidate(c)}
              >
                <div className="row between wrap">
                  <div>
                    <span className="cell-strong">{c.service_name}</span>
                    {c.category && (
                      <span className="cell-sub"> · {c.category}</span>
                    )}
                  </div>
                  <div className="row" style={{ gap: 8 }}>
                    {c.method && <Badge tone="neutral">{c.method}</Badge>}
                    <Badge tone={Number(c.score) >= 0.85 ? 'success' : 'warning'}>
                      {formatConfidence(c.score)}
                    </Badge>
                    {active && <Badge tone="primary">выбрано</Badge>}
                  </div>
                </div>
              </button>
            );
          })}
        </div>
      )}

      <div className="divider" />

      <label className="toggle">
        <input
          type="checkbox"
          checked={creatingNew}
          onChange={(e) => {
            setCreatingNew(e.target.checked);
            if (e.target.checked) setSelected('');
          }}
        />
        Создать новую услугу в каталоге
      </label>

      {creatingNew && (
        <div className="filters" style={{ marginTop: 12, marginBottom: 0 }}>
          <label className="field grow">
            <span className="field-label">Название услуги</span>
            <input
              className="input"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="Каноническое название"
            />
          </label>
          <label className="field">
            <span className="field-label">Категория</span>
            <input
              className="input"
              value={newCategory}
              onChange={(e) => setNewCategory(e.target.value)}
              placeholder="напр. Диагностика"
            />
          </label>
          <label className="field">
            <span className="field-label">Код МКБ</span>
            <input
              className="input"
              value={newIcd}
              onChange={(e) => setNewIcd(e.target.value)}
              placeholder="(необязательно)"
            />
          </label>
          <label className="field grow">
            <span className="field-label">Синонимы (через запятую)</span>
            <input
              className="input"
              value={newSynonyms}
              onChange={(e) => setNewSynonyms(e.target.value)}
              placeholder="синоним 1, синоним 2"
            />
          </label>
        </div>
      )}

      <div className="btn-row" style={{ marginTop: 16 }}>
        <button
          className="btn btn-primary"
          disabled={busy || (!creatingNew && !selected)}
          onClick={submit}
        >
          {busy ? <Spinner /> : null} {creatingNew ? 'Создать и сопоставить' : 'Назначить'}
        </button>
      </div>
    </Card>
  );
}
