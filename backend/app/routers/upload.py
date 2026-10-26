import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Invoice, Transaction
from app.schemas import (
    FinalizeUploadRequest,
    PresignedUploadRequest,
    PresignedUploadResponse,
    UploadResponse,
)
from app.services.content_validation import ContentValidationError, validate_content
from app.services.csv_parser import parse_invoices_csv, parse_statement_csv
from app.services.pdf_parser import PDFParseError, parse_invoice_pdf
from app.services.s3_client import build_object_key, delete_object, download_object_bytes, generate_upload_post

router = APIRouter(prefix="/upload", tags=["upload"])

UPLOAD_CATEGORY_RULES = {
    "invoice": {
        "prefix": "invoices",
        "allowed_suffixes": {".csv", ".pdf"},
        "allowed_content_types": {"text/csv", "application/csv", "application/pdf"},
    },
    "statement": {
        "prefix": "statements",
        "allowed_suffixes": {".csv"},
        "allowed_content_types": {"text/csv", "application/csv"},
    },
}


def _original_filename(object_key: str) -> str:
    # object_key shape: "<prefix>/<uuid4-hex, 32 chars>_<original filename>"
    stored_name = object_key.split("/", 1)[1]
    return stored_name[33:]


@router.post("/request-url", response_model=PresignedUploadResponse)
def request_upload_url(payload: PresignedUploadRequest):

    rules = UPLOAD_CATEGORY_RULES[payload.category]

    if payload.content_type not in rules["allowed_content_types"]:
        raise HTTPException(
            status_code=400,
            detail=f"unsupported content type '{payload.content_type}' for category '{payload.category}'",
        )

    suffix = Path(payload.filename).suffix.lower()
    if suffix not in rules["allowed_suffixes"]:
        raise HTTPException(
            status_code=400,
            detail=f"unsupported file extension '{suffix}' for category '{payload.category}'",
        )

    object_key = build_object_key(rules["prefix"], payload.filename)
    presigned = generate_upload_post(object_key, payload.content_type)

    return PresignedUploadResponse(
        object_key=object_key,
        upload_url=presigned["url"],
        upload_fields=presigned["fields"],
    )


@router.post("/finalize", response_model=UploadResponse)
def finalize_upload(payload: FinalizeUploadRequest, db: Session = Depends(get_db)):
    """Step 2: called once the client's direct-to-S3 upload has finished.
    Downloads the file back from the bucket, validates its actual content
    (not just the extension it was uploaded under), then parses and inserts
    it exactly like the old direct-upload endpoints used to - just sourced
    from S3 instead of local disk. An invalid file is deleted from the
    bucket immediately rather than left sitting there."""

    rules = UPLOAD_CATEGORY_RULES[payload.category]
    suffix = Path(payload.object_key).suffix.lower()
    if suffix not in rules["allowed_suffixes"]:
        raise HTTPException(
            status_code=400,
            detail=f"unsupported file extension '{suffix}' for category '{payload.category}'",
        )

    try:
        content = download_object_bytes(payload.object_key)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"could not read '{payload.object_key}' from the bucket: {exc}")

    try:
        validate_content(suffix, content)
    except ContentValidationError as exc:
        delete_object(payload.object_key)
        raise HTTPException(status_code=400, detail=str(exc))

    filename = _original_filename(payload.object_key)

    with tempfile.NamedTemporaryFile(suffix=suffix) as tmp:
        tmp.write(content)
        tmp.flush()

        if payload.category == "statement":
            try:
                rows, errors = parse_statement_csv(tmp.name)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc))

            for row in rows:
                db.add(Transaction(**row))
            db.commit()

            return UploadResponse(
                filename=filename,
                rows_parsed=len(rows) + len(errors),
                rows_inserted=len(rows),
                rows_skipped=0,
                errors=errors,
            )

        # category == "invoice"
        if suffix == ".pdf":
            try:
                row = parse_invoice_pdf(tmp.name)
            except PDFParseError as exc:
                raise HTTPException(status_code=400, detail=str(exc))
            rows, errors = [row], []
            source = "pdf"
        else:
            try:
                rows, errors = parse_invoices_csv(tmp.name)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc))
            source = "csv"

        rows_parsed = len(rows) + len(errors)
        existing_numbers = {r[0] for r in db.query(Invoice.invoice_number).all()}

        inserted = 0
        skipped = 0
        for row in rows:
            if row["invoice_number"] in existing_numbers:
                skipped += 1
                errors.append(f"invoice {row['invoice_number']}: already exists, skipped")
                continue
            db.add(Invoice(**row, source=source))
            existing_numbers.add(row["invoice_number"])
            inserted += 1
        db.commit()

        return UploadResponse(
            filename=filename,
            rows_parsed=rows_parsed,
            rows_inserted=inserted,
            rows_skipped=skipped,
            errors=errors,
        )
