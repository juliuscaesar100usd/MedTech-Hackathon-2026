import type { ReactNode } from 'react';
import { ApiError } from '../lib/api';

export function Spinner({ large = false }: { large?: boolean }) {
  return <span className={`spinner${large ? ' lg' : ''}`} aria-label="Загрузка" />;
}

export function Loading({ label = 'Загрузка…' }: { label?: string }) {
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
  icon?: ReactNode;
  title: string;
  children?: ReactNode;
}) {
  return (
    <div className="center-state empty-state">
      <div className="es-icon" aria-hidden="true">{icon}</div>
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
  let message = 'Что-то пошло не так.';
  if (error instanceof ApiError) {
    message =
      error.status === 0
        ? 'Не удалось подключиться к API. Запущен ли сервер?'
        : `${error.message} (HTTP ${error.status})`;
  } else if (error instanceof Error) {
    message = error.message;
  }
  return (
    <div className="center-state error-state" role="alert">
      <div className="es-icon" aria-hidden="true">⚠️</div>
      <div className="es-title">Не удалось загрузить данные</div>
      <div>{message}</div>
      {onRetry && (
        <button className="btn btn-secondary btn-sm" onClick={onRetry}>
          Повторить
        </button>
      )}
    </div>
  );
}
