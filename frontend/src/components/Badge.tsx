import type { ReactNode } from 'react';

export type BadgeTone = 'success' | 'warning' | 'danger' | 'info' | 'neutral' | 'primary';

export function Badge({
  tone = 'neutral',
  dot = false,
  children,
}: {
  tone?: BadgeTone;
  dot?: boolean;
  children: ReactNode;
}) {
  return (
    <span className={`badge badge-${tone}`}>
      {dot && <span className="dot" />}
      {children}
    </span>
  );
}

/** A verified / unverified pill driven by a boolean. */
export function VerifiedBadge({ verified }: { verified?: boolean }) {
  return verified ? (
    <Badge tone="success" dot>
      Verified
    </Badge>
  ) : (
    <Badge tone="neutral">Unverified</Badge>
  );
}

/** Map an arbitrary status string to a sensible tone. */
export function StatusBadge({ status }: { status?: string | null }) {
  const s = (status || 'unknown').toLowerCase();
  let tone: BadgeTone = 'neutral';
  if (/(done|matched|parsed|success|complete|ok|verified|auto)/.test(s)) tone = 'success';
  else if (/(pending|processing|queued|running|review|partial)/.test(s)) tone = 'warning';
  else if (/(error|failed|fail|unmatched|reject)/.test(s)) tone = 'danger';
  else if (/(manual|info)/.test(s)) tone = 'info';
  return <Badge tone={tone}>{status || 'unknown'}</Badge>;
}
