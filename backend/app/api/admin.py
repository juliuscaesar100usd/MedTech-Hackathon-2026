"""Admin router: uploads, catalog seeding, documents/batches, verification."""
from __future__ import annotations

import shutil
import tempfile
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ..catalog_loader import is_real_catalog, load_real_catalog
from ..config import settings
from ..enums import ParseStatus
from ..ingestion import enqueue_batch_processing, ingest_archive
from ..models import IngestionBatch, Partner, PriceDocument, PriceItem, Service
from ..normalization import load_catalog_from_file, seed_services
from ..schemas import (
    BatchOut,
    DashboardStats,
    PriceDocumentOut,
    PriceItemOut,
    VerifyRequest,
)
from ..services.stats_service import compute_dashboard
from ..validation import verify_item
from ..validation.verification import ItemNotFoundError
from ..auth.deps import require_admin
from .deps import Pagination, get_db, pagination

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


@router.post("/upload", response_model=BatchOut)
def upload_archive(file: UploadFile, db: Session = Depends(get_db)) -> IngestionBatch:
    """Upload a ZIP of clinic price lists; ingest then queue async processing."""
    name = file.filename or "upload.zip"
    if not name.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Принимаются только ZIP-архивы.")

    uploads_dir = Path(settings.data_dir) / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)
    safe_name = Path(name).name
    saved_path = uploads_dir / f"{uuid.uuid4().hex}_{safe_name}"
    with saved_path.open("wb") as fh:
        shutil.copyfileobj(file.file, fh)

    batch = ingest_archive(db, str(saved_path), archive_name=safe_name)
    enqueue_batch_processing(batch.batch_id)
    return batch


@router.post("/catalog")
def upload_catalog(file: UploadFile, db: Session = Depends(get_db)) -> dict:
    """Upload a service catalog; upsert into the Service table.

    The real organizer catalog (.xlsx, sheet "Справочник услуг" with
    service×specialty rows) is detected automatically and loaded with its
    specialties; a plain .xlsx/.json catalog falls back to the simple loader.
    """
    name = file.filename or "catalog"
    suffix = Path(name).suffix or ".json"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name

    try:
        if is_real_catalog(tmp_path):
            return load_real_catalog(db, tmp_path)
        items = load_catalog_from_file(tmp_path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        try:
            Path(tmp_path).unlink(missing_ok=True)
        except OSError:
            pass

    existing_names = {row[0] for row in db.query(Service.service_name).all()}
    incoming_names = {it["service_name"] for it in items}
    created = len(incoming_names - existing_names)
    updated = len(incoming_names & existing_names)

    seed_services(db, items)
    return {"created": created, "updated": updated}


@router.get("/documents", response_model=list[PriceDocumentOut])
def list_documents(
    status: ParseStatus | None = None,
    batch_id: str | None = None,
    page: Pagination = Depends(pagination),
    db: Session = Depends(get_db),
) -> list[PriceDocument]:
    """List ingested documents, newest first."""
    query = db.query(PriceDocument)
    if status is not None:
        query = query.filter(PriceDocument.parse_status == status)
    if batch_id:
        query = query.filter(PriceDocument.batch_id == batch_id)
    return (
        query.order_by(PriceDocument.parsed_at.desc().nullslast(), PriceDocument.doc_id)
        .offset(page.offset)
        .limit(page.limit)
        .all()
    )


@router.get("/batches", response_model=list[BatchOut])
def list_batches(
    page: Pagination = Depends(pagination),
    db: Session = Depends(get_db),
) -> list[IngestionBatch]:
    """List ingestion batches, newest first."""
    return (
        db.query(IngestionBatch)
        .order_by(IngestionBatch.created_at.desc())
        .offset(page.offset)
        .limit(page.limit)
        .all()
    )


@router.get("/verification")
def verification_queue(
    page: Pagination = Depends(pagination),
    db: Session = Depends(get_db),
) -> list[dict]:
    """Active items flagged for review, enriched with partner/service names."""
    rows = (
        db.query(PriceItem, Partner, Service)
        .outerjoin(Partner, PriceItem.partner_id == Partner.partner_id)
        .outerjoin(Service, PriceItem.service_id == Service.service_id)
        .filter(PriceItem.is_active.is_(True), PriceItem.needs_review.is_(True))
        .order_by(PriceItem.created_at.desc())
        .offset(page.offset)
        .limit(page.limit)
        .all()
    )

    out: list[dict] = []
    for item, partner, service in rows:
        base = PriceItemOut.model_validate(item).model_dump(mode="json")
        base["partner_name"] = partner.name if partner is not None else None
        base["service_name"] = service.service_name if service is not None else None
        base["anomaly_flags"] = list(item.anomaly_flags or [])
        out.append(base)
    return out


@router.post("/verify", response_model=PriceItemOut)
def verify(body: VerifyRequest, db: Session = Depends(get_db)) -> PriceItem:
    """Approve or reject an item (with optional service/price corrections)."""
    try:
        return verify_item(
            db,
            body.item_id,
            approve=body.approve,
            service_id=body.service_id,
            price_resident_kzt=body.price_resident_kzt,
            price_nonresident_kzt=body.price_nonresident_kzt,
            note=body.note,
            operator=body.operator or "operator",
        )
    except ItemNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/dashboard", response_model=DashboardStats)
def dashboard(db: Session = Depends(get_db)) -> DashboardStats:
    """Operator dashboard statistics."""
    return compute_dashboard(db)
