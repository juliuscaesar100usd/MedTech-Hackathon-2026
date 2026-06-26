"""Safe ZIP archive handling for ingestion.

Guards against the classic archive attacks while extracting clinic price-list
ZIPs:

  * **Path traversal** — entries with absolute paths or ``..`` components are
    skipped (we never write outside the per-batch originals directory).
  * **Zip bombs** — each entry is capped at ``MAX_FILE_BYTES`` (declared *and*
    actually-read size) so a single crafted member cannot exhaust the disk.

It also provides the helpers the rest of the pipeline relies on:
  * :func:`safe_filename` — a filesystem-safe, collision-resistant name,
  * :func:`sha256_bytes` / :func:`sha256_file` — content hashing for dedup,
  * :func:`is_supported_name` / :func:`supported_format` — the document filter
    (we only keep pdf / docx / xlsx / xls).
"""
from __future__ import annotations

import hashlib
import os
import re
import zipfile
from dataclasses import dataclass

from ..enums import FileFormat

# Cap per-entry size (declared and read) to defuse zip bombs. 200 MB is far
# beyond any real price list yet keeps a single archive bounded.
MAX_FILE_BYTES = 200 * 1024 * 1024

# Extensions we treat as ingestible documents.
SUPPORTED_EXTS: dict[str, FileFormat] = {
    ".pdf": FileFormat.pdf,
    ".docx": FileFormat.docx,
    ".xlsx": FileFormat.xlsx,
    ".xls": FileFormat.xls,
}

_UNSAFE_CHARS = re.compile(r"[^\w.\-]+", re.UNICODE)


@dataclass
class ArchiveEntry:
    """One safely-extracted archive member ready to persist."""

    original_name: str   # name as it appeared inside the ZIP (basename)
    safe_name: str       # filesystem-safe name for storage
    data: bytes          # raw bytes of the file


def is_supported_name(name: str) -> bool:
    """True when ``name``'s extension is one we ingest."""
    return os.path.splitext(name)[1].lower() in SUPPORTED_EXTS


def supported_format(name: str) -> FileFormat | None:
    """Map a filename extension to its :class:`FileFormat`, or None."""
    return SUPPORTED_EXTS.get(os.path.splitext(name)[1].lower())


def safe_filename(name: str) -> str:
    """Return a filesystem-safe basename (no path components, sane charset).

    Cyrillic is preserved (``\\w`` is Unicode-aware) so Russian/Kazakh clinic
    names survive; only path separators and exotic punctuation are folded to
    underscores. Empty results fall back to ``file``.
    """
    base = os.path.basename(name.replace("\\", "/").strip())
    if not base or base in {".", ".."}:
        return "file"
    stem, ext = os.path.splitext(base)
    stem = _UNSAFE_CHARS.sub("_", stem).strip("._") or "file"
    ext = _UNSAFE_CHARS.sub("", ext)
    # Keep names bounded so they never blow past filesystem limits.
    return (stem[:180] + ext)[:200]


def _is_traversal(name: str) -> bool:
    """True if a ZIP entry name would escape the extraction root."""
    norm = name.replace("\\", "/")
    if norm.startswith("/") or (len(norm) > 1 and norm[1] == ":"):
        return True  # absolute (posix or windows drive)
    return any(part == ".." for part in norm.split("/"))


def sha256_bytes(data: bytes) -> str:
    """Hex SHA-256 of a byte string."""
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str) -> str:
    """Hex SHA-256 of a file, read in chunks."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def iter_supported_entries(zip_path: str):
    """Yield :class:`ArchiveEntry` for every safe, supported member of a ZIP.

    Directories, traversal attempts, oversized members and unsupported file
    types are silently skipped — the caller only sees ingestible documents.
    """
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            name = info.filename
            # Skip directories (trailing slash or explicit dir flag).
            if name.endswith("/") or getattr(info, "is_dir", lambda: False)():
                continue
            if _is_traversal(name):
                continue
            if not is_supported_name(name):
                continue
            # Declared-size bomb guard before we read anything.
            if info.file_size > MAX_FILE_BYTES:
                continue

            with zf.open(info, "r") as fh:
                data = fh.read(MAX_FILE_BYTES + 1)
            if len(data) > MAX_FILE_BYTES:
                # Actual content exceeded the cap -> treat as a bomb, skip.
                continue
            if not data:
                continue

            yield ArchiveEntry(
                original_name=os.path.basename(name.replace("\\", "/")),
                safe_name=safe_filename(name),
                data=data,
            )


def count_supported_entries(zip_path: str) -> int:
    """Count ingestible members without extracting their bytes."""
    n = 0
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            name = info.filename
            if name.endswith("/"):
                continue
            if _is_traversal(name) or not is_supported_name(name):
                continue
            if info.file_size > MAX_FILE_BYTES:
                continue
            n += 1
    return n
