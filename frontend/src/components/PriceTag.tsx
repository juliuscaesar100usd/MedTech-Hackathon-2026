import { formatKzt, type Money } from '../lib/format';

export function PriceTag({
  value,
  label,
}: {
  value: Money;
  label?: string;
}) {
  const formatted = formatKzt(value);
  const muted = formatted === '—';
  return (
    <span>
      {label && <span className="pricetag-label">{label}</span>}
      <span className={`pricetag${muted ? ' muted' : ''}`}>{formatted}</span>
    </span>
  );
}
