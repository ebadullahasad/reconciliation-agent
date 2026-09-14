import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Invoice, Transaction
from app.schemas import UploadResponse
from app.services.csv_parser import parse_invoices_csv, parse_statement_csv

router = APIRouter(prefix="/upload", tags=["upload"])

UPLOADS_ROOT = Path(__file__).resolve().parent.parent.parent / "uploads"


def _save_upload(file: UploadFile, subdir: str) -> Path:
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are supported")

    dest_dir = UPLOADS_ROOT / subdir
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / f"{uuid.uuid4().hex}_{file.filename}"

    with dest_path.open("wb") as out:
        out.write(file.file.read())

    return dest_path


@router.post("/statement", response_model=UploadResponse)
def upload_statement(file: UploadFile, db: Session = Depends(get_db)):
    dest_path = _save_upload(file, "statements")

    try:
        rows, errors = parse_statement_csv(str(dest_path))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    for row in rows:
        db.add(Transaction(**row))
    db.commit()

    return UploadResponse(
        filename=file.filename,
        rows_parsed=len(rows) + len(errors),
        rows_inserted=len(rows),
        rows_skipped=0,
        errors=errors,
    )


@router.post("/invoices", response_model=UploadResponse)
def upload_invoices(file: UploadFile, db: Session = Depends(get_db)):
    dest_path = _save_upload(file, "invoices")

    try:
        rows, errors = parse_invoices_csv(str(dest_path))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    rows_parsed = len(rows) + len(errors)
    existing_numbers = {r[0] for r in db.query(Invoice.invoice_number).all()}

    inserted = 0
    skipped = 0
    for row in rows:
        if row["invoice_number"] in existing_numbers:
            skipped += 1
            errors.append(f"invoice {row['invoice_number']}: already exists, skipped")
            continue
        db.add(Invoice(**row))
        existing_numbers.add(row["invoice_number"])
        inserted += 1
    db.commit()

    return UploadResponse(
        filename=file.filename,
        rows_parsed=rows_parsed,
        rows_inserted=inserted,
        rows_skipped=skipped,
        errors=errors,
    )
