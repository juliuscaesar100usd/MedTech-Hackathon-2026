import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { Stethoscope, MagnifyingGlass, Barcode, CaretRight } from '@phosphor-icons/react';
import { api } from '../lib/api';
import type { ServiceOut, TreeNode } from '../lib/api';
import { useFetch } from '../lib/useFetch';
import { ErrorState } from '../components/States';
import { Badge } from '../components/Badge';
import { formatInt } from '../lib/format';
import { CategoryTree } from '../components/CategoryTree';

type View = 'list' | 'tree';

/* MedArchive catalog — the normalized service catalog, grouped by category.
   Each category is a collapsible section (native <details>, no JS) whose
   services list underneath as .sp-result rows — the same row shape as the
   Search page, so the two surfaces read as one product (one teal hue,
   Phosphor icons, AA contrast). ServiceOut carries no price, so rows stay
   identity-forward; price lives one click deeper on Service→Partners. */

const UNCATEGORIZED = 'Без категории';

/* Russian plural: 1 услуга, 2 услуги, 5 услуг. Standard one/few/many rule. */
function pluralRu(n: number, [one, few, many]: [string, string, string]): string {
  const m10 = n % 10;
  const m100 = n % 100;
  if (m10 === 1 && m100 !== 11) return one;
  if (m10 >= 2 && m10 <= 4 && (m100 < 10 || m100 >= 20)) return few;
  return many;
}

export function ServicesPage() {
  const [text, setText] = useState('');
  const [view, setView] = useState<View>('list');

  // Fetch a generous page of services once; filter client-side for snappy UX.
  // This flat list powers the List view and is the graceful fallback when the
  // (optional) tree endpoint is unavailable or returns no taxonomy.
  const { data, loading, error, reload } = useFetch<ServiceOut[]>(
    () => api.getServices({ limit: 5000 }),
    [],
  );

  // The N-level taxonomy (Лаборатория → Анализ крови → … or specialty grouping
  // when the catalogue is flat) is fetched lazily — only when Tree is selected.
  const treeState = useFetch<TreeNode<ServiceOut>[]>(
    () => (view === 'tree' ? api.getServicesTree() : Promise.resolve([])),
    [view],
  );

  const services = data ?? [];
  const treeNodes = treeState.data ?? [];
  const showTree = view === 'tree' && !treeState.error && treeNodes.length > 0;

  const filtered = useMemo(() => {
    const t = text.trim().toLowerCase();
    if (!t) return services;
    return services.filter((s) => {
      const hay = [s.service_name, ...(s.synonyms || []), s.icd_code || '']
        .join(' ')
        .toLowerCase();
      return hay.includes(t);
    });
  }, [services, text]);

  // Group the (filtered) services by category. Uncategorized sinks to the end;
  // everything else sorts alphabetically (ru-aware).
  const groups = useMemo(() => {
    const map = new Map<string, ServiceOut[]>();
    for (const s of filtered) {
      const key = s.category || UNCATEGORIZED;
      const bucket = map.get(key);
      if (bucket) bucket.push(s);
      else map.set(key, [s]);
    }
    return Array.from(map.entries()).sort(([a], [b]) => {
      if (a === UNCATEGORIZED) return 1;
      if (b === UNCATEGORIZED) return -1;
      return a.localeCompare(b, 'ru');
    });
  }, [filtered]);

  return (
    <main className="sp">
      <section className="sp-band sp-band--compact">
        <div className="sp-band-inner">
          <span className="sp-eyebrow">Каталог</span>
          <h1 className="sp-title">Медицинские услуги</h1>
          <p className="sp-lede">
            Нормализованный каталог услуг по категориям. Откройте услугу, чтобы сравнить цены
            клиник-партнёров.
          </p>
        </div>
      </section>

      <div className="sp-container">
        <div className="svc-catalog">
          <div className="svc-toolbar-row">
            <div className="field grow svc-toolbar">
              <label className="field-label" htmlFor="svc-q">
                Поиск услуг
              </label>
              <input
                id="svc-q"
                className="input"
                placeholder="Фильтр по названию, синониму или коду МКБ…"
                value={text}
                onChange={(e) => setText(e.target.value)}
              />
            </div>
            <div className="seg-toggle" role="tablist" aria-label="Вид каталога">
              <button
                type="button"
                role="tab"
                aria-selected={view === 'list'}
                className={`seg-btn${view === 'list' ? ' active' : ''}`}
                onClick={() => setView('list')}
              >
                Список
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={view === 'tree'}
                className={`seg-btn${view === 'tree' ? ' active' : ''}`}
                onClick={() => setView('tree')}
              >
                Дерево
              </button>
            </div>
          </div>

          {view === 'tree' && treeState.loading ? (
            <ServicesSkeleton />
          ) : showTree ? (
            <CategoryTree<ServiceOut>
              nodes={treeNodes}
              defaultExpandedDepth={0}
              leafKey={(s) => String(s.service_id)}
              renderLeaf={(s) => (
                <Link to={`/services/${s.service_id}`} className="cat-leaf-link">
                  <span className="cat-leaf-name">{s.service_name}</span>
                  {s.icd_code && <span className="cat-leaf-meta">МКБ: {s.icd_code}</span>}
                </Link>
              )}
            />
          ) : loading ? (
            <ServicesSkeleton />
          ) : error ? (
            <ErrorState error={error} onRetry={reload} />
          ) : groups.length === 0 ? (
            <div className="sp-empty">
              <span className="sp-empty-icon">
                <MagnifyingGlass size={30} weight="bold" aria-hidden="true" />
              </span>
              <h2 className="sp-empty-title">Услуги не найдены</h2>
              <p className="sp-empty-body">
                {services.length === 0
                  ? 'В каталоге пока нет услуг. Загрузите каталог из раздела «Админ».'
                  : 'По вашему запросу ничего нет. Попробуйте другое написание.'}
              </p>
            </div>
          ) : (
            <>
              <p className="sp-results-count">
                {formatInt(filtered.length)}{' '}
                {pluralRu(filtered.length, ['услуга', 'услуги', 'услуг'])} в{' '}
                {formatInt(groups.length)}{' '}
                {pluralRu(groups.length, ['категории', 'категориях', 'категориях'])}
              </p>

              {groups.map(([category, items]) => (
                <details key={category} className="svc-group" open>
                  <summary className="svc-group-head">
                    <CaretRight className="svc-group-caret" size={16} weight="bold" aria-hidden="true" />
                    <span className="svc-group-name">{category}</span>
                    <span className="svc-group-count">
                      {formatInt(items.length)}{' '}
                      {pluralRu(items.length, ['услуга', 'услуги', 'услуг'])}
                    </span>
                  </summary>

                  <div className="svc-grid">
                    {items.map((s) => (
                      <Link
                        key={s.service_id}
                        to={`/services/${s.service_id}`}
                        className="sp-result"
                      >
                        <span className="sp-result-icon">
                          <Stethoscope size={22} weight="duotone" aria-hidden="true" />
                        </span>
                        <span className="sp-result-body">
                          <span className="sp-result-title">{s.service_name}</span>
                          <span className="sp-result-meta">
                            {!s.is_active && <Badge tone="neutral">Неактивна</Badge>}
                            {s.icd_code && (
                              <span className="sp-meta-chip">
                                <Barcode size={15} weight="bold" aria-hidden="true" />
                                МКБ: {s.icd_code}
                              </span>
                            )}
                            {s.synonyms && s.synonyms.length > 0 && (
                              <span className="sp-meta-chip">
                                синонимы: {s.synonyms.slice(0, 3).join(', ')}
                              </span>
                            )}
                          </span>
                        </span>
                        <CaretRight
                          className="sp-result-caret"
                          size={18}
                          weight="bold"
                          aria-hidden="true"
                        />
                      </Link>
                    ))}
                  </div>
                </details>
              ))}
            </>
          )}
        </div>
      </div>
    </main>
  );
}

/* Skeleton mirrors the catalog-row shape (skeletons over spinners >300ms). */
function ServicesSkeleton() {
  return (
    <div className="sp-list" aria-busy="true" aria-label="Загрузка услуг">
      {Array.from({ length: 6 }).map((_, i) => (
        <div key={i} className="sp-result sp-result--skeleton" aria-hidden="true">
          <span className="sp-result-icon sk" />
          <span className="sp-result-body">
            <span className="sk sk-line sk-title" />
            <span className="sk sk-line sk-meta" />
          </span>
        </div>
      ))}
    </div>
  );
}
