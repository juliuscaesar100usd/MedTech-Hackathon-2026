import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';

export function Card({
  children,
  className = '',
  hoverable = false,
  padSm = false,
}: {
  children: ReactNode;
  className?: string;
  hoverable?: boolean;
  padSm?: boolean;
}) {
  const cls = ['card', hoverable ? 'hoverable' : '', padSm ? 'pad-sm' : '', className]
    .filter(Boolean)
    .join(' ');
  return <div className={cls}>{children}</div>;
}

/** A card that links somewhere; used for search/service/partner result lists. */
export function LinkCard({ to, children }: { to: string; children: ReactNode }) {
  return (
    <Link to={to} className="card hoverable result-card">
      {children}
    </Link>
  );
}
