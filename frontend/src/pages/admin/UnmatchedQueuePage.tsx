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
    return err.status === 0 ? 'Could not reach the API.' : `${err.message} (HTTP ${err.status})`;
  if (err instanceof Error) return err.message;
  return 'Action failed.';
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
          {items.length} unmatched item{items.length === 1 ? '' : 's'}
        </p>
        <button className="btn btn-secondary btn-sm" onClick={reload}>
          ↻ Refresh
        </button>
      </div>

      {loading ? (
        <Loading label="Loading unmatched queue…" />
      ) : error ? (
        <ErrorState error={error} onRetry={reload} />
      ) : items.length === 0 ? (
        <EmptyState icon="✅" title="Nothing unmatched">
          Every ingested price item has been mapped to a catalog service.
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
      toast.error('Pick a candidate or create a new service.');
      return;
    }
    if (creatingNew && !newName.trim()) {
      toast.error('New service needs a name.');
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
      toast.success('Matched.');
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
          <h3 style={{ marginBottom: 2 }}>{item.service_name_raw || `Item #${item.item_id}`}</h3>
          <div className="cell-sub">
            {item.partner_name || 'Unknown partner'}
            {item.service_code_source ? ` · code ${item.service_code_source}` : ''}
          </div>
        </div>
        <div className="row" style={{ gap: 12 }}>
          <div style={{ textAlign: 'right' }}>
            <span className="pricetag-label">Resident</span>
            <PriceTag value={item.price_resident_kzt} />
          </div>
          {item.match_status && <Badge tone="danger">{item.match_status}</Badge>}
        </div>
      </div>

      <div className="divider" />

      <div className="field-label" style={{ marginBottom: 8 }}>
        Suggested catalog services
      </div>
      {candidates.length === 0 ? (
        <p className="faint">No automatic suggestions — create a new service below.</p>
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
                    {active && <Badge tone="primary">selected</Badge>}
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
        Create a new catalog service instead
      </label>

      {creatingNew && (
        <div className="filters" style={{ marginTop: 12, marginBottom: 0 }}>
          <div className="field grow">
            <label className="field-label">Service name</label>
            <input
              className="input"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="Canonical service name"
            />
          </div>
          <div className="field">
            <label className="field-label">Category</label>
            <input
              className="input"
              value={newCategory}
              onChange={(e) => setNewCategory(e.target.value)}
              placeholder="e.g. Diagnostics"
            />
          </div>
          <div className="field">
            <label className="field-label">ICD code</label>
            <input
              className="input"
              value={newIcd}
              onChange={(e) => setNewIcd(e.target.value)}
              placeholder="(optional)"
            />
          </div>
          <div className="field grow">
            <label className="field-label">Synonyms (comma-separated)</label>
            <input
              className="input"
              value={newSynonyms}
              onChange={(e) => setNewSynonyms(e.target.value)}
              placeholder="alias 1, alias 2"
            />
          </div>
        </div>
      )}

      <div className="btn-row" style={{ marginTop: 16 }}>
        <button
          className="btn btn-primary"
          disabled={busy || (!creatingNew && !selected)}
          onClick={submit}
        >
          {busy ? <Spinner /> : null} {creatingNew ? 'Create & match' : 'Confirm match'}
        </button>
      </div>
    </Card>
  );
}
