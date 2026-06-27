// Centralized formatting helpers for money, dates, numbers and percentages.

/** A money value may arrive as a number, a Decimal-string, null or undefined. */
export type Money = number | string | null | undefined;

/**
 * Coerce a defensively-typed money value into a finite number, or null.
 */
export function toNumber(value: Money): number | null {
  if (value === null || value === undefined || value === '') return null;
  if (typeof value === 'number') return Number.isFinite(value) ? value : null;
  // strings may contain spaces, commas or a currency symbol
  const cleaned = value.replace(/[^\d.,-]/g, '').replace(/\s/g, '');
  if (cleaned === '') return null;
  // Treat comma as decimal separator only if there's no dot.
  const normalized = cleaned.includes('.') ? cleaned.replace(/,/g, '') : cleaned.replace(/,/g, '.');
  const n = Number(normalized);
  return Number.isFinite(n) ? n : null;
}

/**
 * Format a tenge amount as e.g. "12 500 ₸". Returns an em-dash for missing values.
 */
export function formatKzt(value: Money): string {
  const n = toNumber(value);
  if (n === null) return '—';
  const rounded = Math.round(n);
  const grouped = rounded
    .toString()
    .replace(/\B(?=(\d{3})+(?!\d))/g, ' '); // non-breaking space thousands separator
  return `${grouped} ₸`;
}

/**
 * Format a price range, collapsing to a single value when min === max.
 */
export function formatKztRange(min: Money, max: Money): string {
  const a = toNumber(min);
  const b = toNumber(max);
  if (a === null && b === null) return '—';
  if (a !== null && b !== null) {
    if (Math.round(a) === Math.round(b)) return formatKzt(a);
    return `${formatKzt(a)} – ${formatKzt(b)}`;
  }
  return formatKzt(a ?? b);
}

/**
 * Format an ISO-ish date string into a readable local date. Returns em-dash if absent.
 */
export function formatDate(value: string | null | undefined): string {
  if (!value) return '—';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value; // show raw if unparseable
  return d.toLocaleDateString('ru-RU', {
    year: 'numeric',
    month: 'short',
    day: '2-digit',
  });
}

/**
 * Format a datetime string into date + time.
 */
export function formatDateTime(value: string | null | undefined): string {
  if (!value) return '—';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString('ru-RU', {
    year: 'numeric',
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

/**
 * Format a 0..1 fraction as a percent, e.g. 0.873 -> "87%".
 */
export function formatPercent(value: number | string | null | undefined, digits = 0): string {
  const n = typeof value === 'string' ? Number(value) : value;
  if (n === null || n === undefined || !Number.isFinite(n)) return '—';
  // accept either 0..1 fractions or already-scaled 0..100 values
  const pct = n <= 1 ? n * 100 : n;
  return `${pct.toFixed(digits)}%`;
}

/**
 * Format a confidence score (0..1) as a percentage string.
 */
export function formatConfidence(value: number | string | null | undefined): string {
  const n = typeof value === 'string' ? Number(value) : value;
  if (n === null || n === undefined || !Number.isFinite(n)) return '—';
  const pct = n <= 1 ? n * 100 : n;
  return `${Math.round(pct)}%`;
}

/**
 * Format a plain integer with thousands separators.
 */
export function formatInt(value: number | string | null | undefined): string {
  const n = typeof value === 'string' ? Number(value) : value;
  if (n === null || n === undefined || !Number.isFinite(n)) return '—';
  return Math.round(n)
    .toString()
    .replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
}
