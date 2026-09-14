import datetime

from pydantic import BaseModel, ConfigDict


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
