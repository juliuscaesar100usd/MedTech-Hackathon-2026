import { useState } from 'react';
import { Link } from 'react-router-dom';
import { api, ApiError } from '../../lib/api';
import type { BatchOut, CatalogUploadResult } from '../../lib/api';
import { Card } from '../../components/Card';
import { Dropzone } from '../../components/Dropzone';
import { Spinner } from '../../components/States';
import { StatusBadge } from '../../components/Badge';
import { useToast } from '../../components/Toast';
import { formatInt, formatDateTime } from '../../lib/format';

function errMessage(err: unknown): string {
  if (err instanceof ApiError)
    return err.status === 0 ? 'Не удалось подключиться к API.' : `${err.message} (HTTP ${err.status})`;
  if (err instanceof Error) return err.message;
  return 'Загрузка не выполнена.';
}

export function UploadPage() {
  return (
    <div className="card-grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(340px, 1fr))' }}>
      <ArchiveUpload />
      <CatalogUpload />
    </div>
  );
}

function ArchiveUpload() {
  const toast = useToast();
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<BatchOut | null>(null);

  async function submit() {
    if (!file) return;
    setBusy(true);
    setResult(null);
    try {
      const batch = await api.uploadArchive(file);
      setResult(batch);
      toast.success('Архив загружен — обработка начата.');
      setFile(null);
    } catch (err) {
      toast.error(errMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <h3>Загрузить архив прайс-листов</h3>
      <p className="muted">
        Загрузите <b>.zip</b>-архив прайс-листов клиник (PDF, сканы, Excel, Word). Файлы будут
        разобраны и нормализованы в фоновом режиме.
      </p>

      <Dropzone
        accept=".zip,application/zip"
        file={file}
        disabled={busy}
        title="Перетащите .zip-архив сюда"
        subtitle="или нажмите для выбора файла"
        onFile={setFile}
      />

      <div className="btn-row" style={{ marginTop: 16 }}>
        <button className="btn btn-primary" disabled={!file || busy} onClick={submit}>
          {busy ? <Spinner /> : null}
          {busy ? 'Загрузка…' : 'Загрузить архив'}
        </button>
        {file && !busy && (
          <button className="btn btn-ghost" onClick={() => setFile(null)}>
            Очистить
          </button>
        )}
      </div>

      {result && (
        <div className="card pad-sm" style={{ marginTop: 16, background: 'var(--c-surface-2)' }}>
          <div className="row between">
            <h4 style={{ margin: 0 }}>Пакет #{result.batch_id}</h4>
            <StatusBadge status={result.status} />
          </div>
          <div className="divider" />
          <div className="rc-meta" style={{ gap: '6px 18px' }}>
            <span>
              <b>{result.archive_name || file?.name || 'archive.zip'}</b>
            </span>
            <span>Всего файлов: {formatInt(result.total_files)}</span>
            <span>Обработано: {formatInt(result.processed_files)}</span>
            <span>Ошибок: {formatInt(result.error_files)}</span>
            <span className="faint">Создан: {formatDateTime(result.created_at)}</span>
          </div>
          <div style={{ marginTop: 12 }}>
            <Link to="/admin/documents" className="btn btn-secondary btn-sm">
              Просмотр документов →
            </Link>
          </div>
        </div>
      )}
    </Card>
  );
}

function CatalogUpload() {
  const toast = useToast();
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<CatalogUploadResult | null>(null);

  async function submit() {
    if (!file) return;
    setBusy(true);
    setResult(null);
    try {
      const res = await api.uploadCatalog(file);
      setResult(res);
      toast.success(`Каталог импортирован: создано ${res.created}, обновлено ${res.updated}.`);
      setFile(null);
    } catch (err) {
      toast.error(errMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <h3>Импортировать каталог услуг</h3>
      <p className="muted">
        Загрузите <b>.xlsx</b> или <b>.json</b>-каталог эталонных услуг (названия, синонимы,
        категории, коды МКБ), используемый для нормализации.
      </p>

      <Dropzone
        accept=".xlsx,.json,application/json"
        file={file}
        disabled={busy}
        title="Перетащите файл каталога сюда"
        subtitle=".xlsx или .json — нажмите для выбора"
        onFile={setFile}
      />

      <div className="btn-row" style={{ marginTop: 16 }}>
        <button className="btn btn-primary" disabled={!file || busy} onClick={submit}>
          {busy ? <Spinner /> : null}
          {busy ? 'Импорт…' : 'Импортировать каталог'}
        </button>
        {file && !busy && (
          <button className="btn btn-ghost" onClick={() => setFile(null)}>
            Очистить
          </button>
        )}
      </div>

      {result && (
        <div className="card pad-sm" style={{ marginTop: 16, background: 'var(--c-surface-2)' }}>
          <h4 style={{ marginTop: 0 }}>Каталог импортирован</h4>
          <div className="rc-meta" style={{ gap: '6px 18px' }}>
            <span>
              Создано: <b>{formatInt(result.created)}</b>
            </span>
            <span>
              Обновлено: <b>{formatInt(result.updated)}</b>
            </span>
          </div>
          <div style={{ marginTop: 12 }}>
            <Link to="/services" className="btn btn-secondary btn-sm">
              Просмотр услуг →
            </Link>
          </div>
        </div>
      )}
    </Card>
  );
}
