import datetime
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

SAFE_FILENAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}")


class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    date: datetime.date
    description: str
    amount: float
    reference: str | None = None


class InvoiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    invoice_number: str
    invoice_date: datetime.date
    amount: float
    customer_name: str | None = None
    source: str


class UploadResponse(BaseModel):
    filename: str
    rows_parsed: int
    rows_inserted: int
    rows_skipped: int
    errors: list[str] = []


class ReconciliationResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: str
    review_status: str
    confidence: str | None = None
    possible_reasons: str | None = None
    invoice: InvoiceOut
    transaction: TransactionOut | None = None


class MatchRunResponse(BaseModel):
    invoices_processed: int
    matched: int
    needs_review: int
    explained: int


class PresignedUploadRequest(BaseModel):
    category: Literal["invoice", "statement"]
    filename: str
    content_type: str

    @field_validator("filename")
    @classmethod
    def filename_must_be_safe(cls, value: str) -> str:
        if not SAFE_FILENAME_RE.fullmatch(value):
            raise ValueError(
                "filename may only contain letters, digits, '_', '-' and '.', "
                "must start with a letter or digit, and be at most 100 characters "
                "(no spaces, slashes or special characters)"
            )
        return value


class PresignedUploadResponse(BaseModel):
    object_key: str
    upload_url: str
    upload_fields: dict[str, str]


class FinalizeUploadRequest(BaseModel):
    object_key: str
    category: Literal["invoice", "statement"]
