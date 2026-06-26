import type { ReactNode } from 'react';
import { ApiError } from '../lib/api';

export function Spinner({ large = false }: { large?: boolean }) {
  return <span className={`spinner${large ? ' lg' : ''}`} aria-label="Loading" />;
}

export function Loading({ label = 'Loading…' }: { label?: string }) {
  return (
    <div className="center-state">
      <Spinner large />
      <div className="muted">{label}</div>
    </div>
  );
}

export function EmptyState({
  icon = '🔍',
  title,
  children,
}: {
  icon?: string;
  title: string;
  children?: ReactNode;
}) {
  return (
    <div className="center-state empty-state">
      <div className="es-icon">{icon}</div>
      <div className="es-title">{title}</div>
      {children && <div className="muted">{children}</div>}
    </div>
  );
}

export function ErrorState({
  error,
  onRetry,
}: {
  error: unknown;
  onRetry?: () => void;
}) {
  let message = 'Something went wrong.';
  if (error instanceof ApiError) {
    message =
      error.status === 0
        ? 'Could not reach the API. Is the backend running?'
        : `${error.message} (HTTP ${error.status})`;
  } else if (error instanceof Error) {
    message = error.message;
  }
  return (
    <div className="center-state error-state">
      <div className="es-icon">⚠️</div>
      <div className="es-title">Unable to load data</div>
      <div>{message}</div>
      {onRetry && (
        <button className="btn btn-secondary btn-sm" onClick={onRetry}>
          Retry
        </button>
      )}
    </div>
  );
}
