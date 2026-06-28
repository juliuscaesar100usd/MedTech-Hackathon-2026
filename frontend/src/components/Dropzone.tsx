import { useRef, useState, type DragEvent } from 'react';
import { FileZip } from '@phosphor-icons/react';

export function Dropzone({
  accept,
  file,
  disabled = false,
  title,
  subtitle,
  onFile,
}: {
  accept: string;
  file: File | null;
  disabled?: boolean;
  title: string;
  subtitle: string;
  onFile: (file: File) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  function handleDrop(e: DragEvent) {
    e.preventDefault();
    setDragging(false);
    if (disabled) return;
    const f = e.dataTransfer.files?.[0];
    if (f) onFile(f);
  }

  return (
    <div
      className={`dropzone${dragging ? ' dragging' : ''}`}
      onClick={() => !disabled && inputRef.current?.click()}
      onDragOver={(e) => {
        e.preventDefault();
        if (!disabled) setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={handleDrop}
      onKeyDown={(e) => {
        if (disabled) return;
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          inputRef.current?.click();
        }
      }}
      role="button"
      tabIndex={0}
      aria-disabled={disabled}
    >
      <div className="dz-icon" aria-hidden="true"><FileZip size={30} weight="duotone" /></div>
      <div className="dz-title">{title}</div>
      <div className="dz-sub">{subtitle}</div>
      {file && <div className="dz-file">Выбран: {file.name}</div>}
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        style={{ display: 'none' }}
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) onFile(f);
          e.target.value = ''; // allow re-selecting the same file
        }}
      />
    </div>
  );
}
