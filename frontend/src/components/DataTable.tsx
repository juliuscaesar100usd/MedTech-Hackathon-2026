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
  emptyMessage = 'No rows.',
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
              return (
                <th
                  key={col.key}
                  className={[col.numeric ? 'num' : '', clickable ? 'sortable' : '']
                    .filter(Boolean)
                    .join(' ')}
                  onClick={clickable ? () => onSort!(col.key) : undefined}
                >
                  {col.header}
                  {col.sortable && (
                    <span className="sort-ind">
                      {isSorted ? (sort!.dir === 'asc' ? '▲' : '▼') : ''}
                    </span>
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
