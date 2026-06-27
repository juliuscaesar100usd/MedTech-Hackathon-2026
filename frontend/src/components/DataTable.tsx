import type { ReactNode } from 'react';

export interface Column<T> {
  key: string;
  header: ReactNode;
  /** Render the cell. */
  render: (row: T) => ReactNode;
  /** Right-align numeric columns. */
  numeric?: boolean;
  /** Mark this column sortable; clicking the header calls onSort(key). */
  sortable?: boolean;
}

export interface SortState {
  key: string;
  dir: 'asc' | 'desc';
}

/**
 * A lightweight, generic data table. Sorting is controlled by the parent
 * (pass `sort` + `onSort`); it only renders the indicator + click handlers.
 */
export function DataTable<T>({
  columns,
  rows,
  rowKey,
  sort,
  onSort,
  emptyMessage = 'Нет данных.',
}: {
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T, index: number) => string | number;
  sort?: SortState;
  onSort?: (key: string) => void;
  emptyMessage?: string;
}) {
  return (
    <div className="table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            {columns.map((col) => {
              const isSorted = sort?.key === col.key;
              const clickable = col.sortable && onSort;
              const indicator = col.sortable && (
                <span className="sort-ind" aria-hidden="true">
                  {isSorted ? (sort!.dir === 'asc' ? '▲' : '▼') : ''}
                </span>
              );
              return (
                <th
                  key={col.key}
                  scope="col"
                  className={[col.numeric ? 'num' : '', clickable ? 'sortable' : '']
                    .filter(Boolean)
                    .join(' ')}
                  aria-sort={
                    col.sortable
                      ? isSorted
                        ? sort!.dir === 'asc'
                          ? 'ascending'
                          : 'descending'
                        : 'none'
                      : undefined
                  }
                >
                  {clickable ? (
                    <button type="button" className="th-sort-btn" onClick={() => onSort!(col.key)}>
                      {col.header}
                      {indicator}
                    </button>
                  ) : (
                    <>
                      {col.header}
                      {indicator}
                    </>
                  )}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr>
              <td colSpan={columns.length} className="muted" style={{ textAlign: 'center', padding: 28 }}>
                {emptyMessage}
              </td>
            </tr>
          ) : (
            rows.map((row, i) => (
              <tr key={rowKey(row, i)}>
                {columns.map((col) => (
                  <td key={col.key} className={col.numeric ? 'num' : ''}>
                    {col.render(row)}
                  </td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
