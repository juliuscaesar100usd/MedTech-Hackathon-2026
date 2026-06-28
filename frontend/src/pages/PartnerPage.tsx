import { useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { api } from '../lib/api';
import type { PartnerOut, ServicePriceOut, TreeNode } from '../lib/api';
import { useFetch } from '../lib/useFetch';
import { Loading, ErrorState, EmptyState } from '../components/States';
import { Card } from '../components/Card';
import { Badge, VerifiedBadge } from '../components/Badge';
import { PriceTag } from '../components/PriceTag';
import { CategoryTree, filterTree, countLeaves } from '../components/CategoryTree';
import { formatDate } from '../lib/format';

export function PartnerPage() {
  const { id = '' } = useParams();

  const partnerState = useFetch<PartnerOut>(() => api.getPartner(id), [id]);
  // Flat list powers the search-filter fallback table; the section_path tree is
  // the primary (N-level) view. Both load in parallel; either can cover the other.
  const servicesState = useFetch<ServicePriceOut[]>(() => api.getPartnerServices(id), [id]);
  const treeState = useFetch<TreeNode<ServicePriceOut>[]>(() => api.getPartnerTree(id), [id]);

  const partner = partnerState.data;

  return (
    <main className="page">
      <Link to="/partners" className="back-link">
        ← Все партнёры
      </Link>

      {partnerState.loading ? (
        <Loading label="Загрузка партнёра…" />
      ) : partnerState.error ? (
        <ErrorState error={partnerState.error} onRetry={partnerState.reload} />
      ) : partner ? (
        <>
          <header className="page-header">
            <div className="eyebrow">Клиника-партнёр</div>
            <div className="row wrap" style={{ gap: 12 }}>
              <h1 style={{ marginBottom: 0 }}>{partner.name}</h1>
              {partner.is_active ? (
                <Badge tone="success" dot>
                  Активна
                </Badge>
              ) : (
                <Badge tone="neutral">Неактивна</Badge>
              )}
            </div>
          </header>

          <div className="two-col">
            <Card>
              <h2>Контакты</h2>
              <ul className="contact-list">
                <li>
                  <span className="ci-label">Город</span>
                  <span>{partner.city || '—'}</span>
                </li>
                <li>
                  <span className="ci-label">Адрес</span>
                  <span>{partner.address || '—'}</span>
                </li>
                <li>
                  <span className="ci-label">Эл. почта</span>
                  <span>
                    {partner.contact_email ? (
                      <a href={`mailto:${partner.contact_email}`}>{partner.contact_email}</a>
                    ) : (
                      '—'
                    )}
                  </span>
                </li>
                <li>
                  <span className="ci-label">Телефон</span>
                  <span>
                    {partner.contact_phone ? (
                      <a href={`tel:${partner.contact_phone}`}>{partner.contact_phone}</a>
                    ) : (
                      '—'
                    )}
                  </span>
                </li>
              </ul>
            </Card>

            <div>
              <PriceList treeState={treeState} flatState={servicesState} />
            </div>
          </div>
        </>
      ) : null}
    </main>
  );
}

/** Case-insensitive search over an item's normalized/raw/category/section text. */
function makeMatcher(query: string): (it: ServicePriceOut) => boolean {
  const t = query.trim().toLowerCase();
  return (it: ServicePriceOut) => {
    if (!t) return true;
    const hay = [
      it.service_name || '',
      it.service_name_raw || '',
      it.category || '',
      ...(it.section_path || []),
    ]
      .join(' ')
      .toLowerCase();
    return hay.includes(t);
  };
}

function PriceList({
  treeState,
  flatState,
}: {
  treeState: ReturnType<typeof useFetch<TreeNode<ServicePriceOut>[]>>;
  flatState: ReturnType<typeof useFetch<ServicePriceOut[]>>;
}) {
  const [text, setText] = useState('');

  const treeNodes = treeState.data ?? [];
  const useTree = !treeState.error && treeNodes.length > 0;
  const searching = text.trim().length > 0;

  // --- Tree view (primary): prune nodes/leaves to the search query ----------
  const visibleNodes = useMemo(
    () => (searching ? filterTree(treeNodes, makeMatcher(text)) : treeNodes),
    [treeNodes, text, searching],
  );
  const visibleCount = useMemo(
    () => visibleNodes.reduce((n, node) => n + countLeaves(node), 0),
    [visibleNodes],
  );

  // --- Flat fallback: master's single-level category table ------------------
  const flatItems = flatState.data ?? [];
  const grouped = useMemo(() => {
    const match = makeMatcher(text);
    const filtered = flatItems.filter(match);
    const map = new Map<string, ServicePriceOut[]>();
    for (const it of filtered) {
      const cat = it.category || 'Без категории';
      if (!map.has(cat)) map.set(cat, []);
      map.get(cat)!.push(it);
    }
    return Array.from(map.entries()).sort((a, b) => a[0].localeCompare(b[0], 'ru'));
  }, [flatItems, text]);

  // Gate loading/errors on whichever source we will actually render.
  if (treeState.loading) return <Loading label="Загрузка прайс-листа…" />;
  if (!useTree && flatState.loading) return <Loading label="Загрузка прайс-листа…" />;
  if (!useTree && flatState.error)
    return <ErrorState error={flatState.error} onRetry={flatState.reload} />;

  const hasAnyData = useTree ? treeNodes.length > 0 : flatItems.length > 0;

  const searchBox = (
    <div className="row between wrap" style={{ marginBottom: 14 }}>
      <h2 style={{ marginBottom: 0 }}>Прайс-лист</h2>
      <input
        className="input"
        style={{ maxWidth: 260 }}
        type="search"
        aria-label="Фильтр услуг"
        placeholder="Фильтр услуг…"
        value={text}
        onChange={(e) => setText(e.target.value)}
      />
    </div>
  );

  if (!hasAnyData) {
    return (
      <section>
        {searchBox}
        <EmptyState icon="📋" title="Нет позиций прайс-листа">
          Для этого партнёра ещё не загружено ни одной позиции.
        </EmptyState>
      </section>
    );
  }

  return (
    <section>
      {searchBox}

      {useTree ? (
        visibleNodes.length === 0 ? (
          <EmptyState icon="🔍" title="Ничего не найдено" />
        ) : (
          <div className="card pad-sm">
            <p className="faint" style={{ marginBottom: 10 }}>
              {visibleCount} {visibleCount === 1 ? 'услуга' : 'услуг'}
            </p>
            <CategoryTree<ServicePriceOut>
              // Remount when crossing the search boundary so matches auto-expand.
              key={searching ? 'search' : 'browse'}
              nodes={visibleNodes}
              defaultExpandedDepth={searching ? 99 : 0}
              leafKey={(it) => String(it.item_id)}
              renderLeaf={(it) => <PriceLeaf item={it} />}
            />
          </div>
        )
      ) : grouped.length === 0 ? (
        <EmptyState icon="🔍" title="Ничего не найдено" />
      ) : (
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Услуга</th>
                <th className="num">Резидент</th>
                <th className="num">Нерезидент</th>
                <th>Актуально с</th>
                <th>Статус</th>
              </tr>
            </thead>
            <tbody>
              {grouped.map(([cat, rows]) => (
                <CategoryGroup key={cat} category={cat} rows={rows} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

/** One service row inside the N-level tree: name + prices + verification. */
function PriceLeaf({ item }: { item: ServicePriceOut }) {
  const normalized = item.service_name;
  const raw = item.service_name_raw;
  const showRaw = raw && raw !== normalized;
  return (
    <div className="price-leaf">
      <span className="price-leaf-main">
        <span className="cell-strong">{normalized || raw || '—'}</span>
        {showRaw && <span className="cell-sub">исходное: «{raw}»</span>}
        {!normalized && item.match_status && (
          <span className="cell-sub">
            <Badge tone="warning">{item.match_status}</Badge>
          </span>
        )}
      </span>
      <span className="price-leaf-prices">
        <PriceTag value={item.price_resident_kzt} />
        <PriceTag value={item.price_nonresident_kzt} />
        <VerifiedBadge verified={item.is_verified} />
      </span>
    </div>
  );
}

function CategoryGroup({ category, rows }: { category: string; rows: ServicePriceOut[] }) {
  return (
    <>
      <tr className="group-row">
        <td colSpan={5}>
          {category} <span className="faint">({rows.length})</span>
        </td>
      </tr>
      {rows.map((it) => {
        const normalized = it.service_name;
        const raw = it.service_name_raw;
        const showRaw = raw && raw !== normalized;
        return (
          <tr key={String(it.item_id)}>
            <td>
              <span className="cell-strong">{normalized || raw || '—'}</span>
              {showRaw && <div className="cell-sub">исходное: «{raw}»</div>}
              {!normalized && it.match_status && (
                <div className="cell-sub">
                  <Badge tone="warning">{it.match_status}</Badge>
                </div>
              )}
            </td>
            <td className="num">
              <PriceTag value={it.price_resident_kzt} />
            </td>
            <td className="num">
              <PriceTag value={it.price_nonresident_kzt} />
            </td>
            <td className="muted">{formatDate(it.effective_date)}</td>
            <td>
              <VerifiedBadge verified={it.is_verified} />
            </td>
          </tr>
        );
      })}
    </>
  );
}
