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
    return err.status === 0 ? 'Could not reach the API.' : `${err.message} (HTTP ${err.status})`;
  if (err instanceof Error) return err.message;
  return 'Upload failed.';
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
      toast.success('Archive uploaded — processing started.');
      setFile(null);
    } catch (err) {
      toast.error(errMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <h3>Upload price-list archive</h3>
      <p className="muted">
        Upload a <b>.zip</b> of clinic price lists (PDF, scans, Excel, Word). It is parsed and
        normalized in the background.
      </p>

      <Dropzone
        accept=".zip,application/zip"
        file={file}
        disabled={busy}
        title="Drop a .zip archive here"
        subtitle="or click to browse"
        onFile={setFile}
      />

      <div className="btn-row" style={{ marginTop: 16 }}>
        <button className="btn btn-primary" disabled={!file || busy} onClick={submit}>
          {busy ? <Spinner /> : null}
          {busy ? 'Uploading…' : 'Upload archive'}
        </button>
        {file && !busy && (
          <button className="btn btn-ghost" onClick={() => setFile(null)}>
            Clear
          </button>
        )}
      </div>

      {result && (
        <div className="card pad-sm" style={{ marginTop: 16, background: 'var(--c-surface-2)' }}>
          <div className="row between">
            <h4 style={{ margin: 0 }}>Batch #{result.batch_id}</h4>
            <StatusBadge status={result.status} />
          </div>
          <div className="divider" />
          <div className="rc-meta" style={{ gap: '6px 18px' }}>
            <span>
              <b>{result.archive_name || file?.name || 'archive.zip'}</b>
            </span>
            <span>Total files: {formatInt(result.total_files)}</span>
            <span>Processed: {formatInt(result.processed_files)}</span>
            <span>Errors: {formatInt(result.error_files)}</span>
            <span className="faint">Created: {formatDateTime(result.created_at)}</span>
          </div>
          <div style={{ marginTop: 12 }}>
            <Link to="/admin/documents" className="btn btn-secondary btn-sm">
              View documents →
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
      toast.success(`Catalog imported: ${res.created} created, ${res.updated} updated.`);
      setFile(null);
    } catch (err) {
      toast.error(errMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <h3>Import service catalog</h3>
      <p className="muted">
        Upload an <b>.xlsx</b> or <b>.json</b> catalog of canonical services (names, synonyms,
        categories, ICD codes) used for normalization.
      </p>

      <Dropzone
        accept=".xlsx,.json,application/json"
        file={file}
        disabled={busy}
        title="Drop a catalog file here"
        subtitle=".xlsx or .json — click to browse"
        onFile={setFile}
      />

      <div className="btn-row" style={{ marginTop: 16 }}>
        <button className="btn btn-primary" disabled={!file || busy} onClick={submit}>
          {busy ? <Spinner /> : null}
          {busy ? 'Importing…' : 'Import catalog'}
        </button>
        {file && !busy && (
          <button className="btn btn-ghost" onClick={() => setFile(null)}>
            Clear
          </button>
        )}
      </div>

      {result && (
        <div className="card pad-sm" style={{ marginTop: 16, background: 'var(--c-surface-2)' }}>
          <h4 style={{ marginTop: 0 }}>Catalog imported</h4>
          <div className="rc-meta" style={{ gap: '6px 18px' }}>
            <span>
              Created: <b>{formatInt(result.created)}</b>
            </span>
            <span>
              Updated: <b>{formatInt(result.updated)}</b>
            </span>
          </div>
          <div style={{ marginTop: 12 }}>
            <Link to="/services" className="btn btn-secondary btn-sm">
              View services →
            </Link>
          </div>
        </div>
      )}
    </Card>
  );
}
