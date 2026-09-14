import datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Transaction(Base):
    """A single row from an uploaded bank statement."""

    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[datetime.date] = mapped_column(Date)
    description: Mapped[str] = mapped_column(String, default="")
    amount: Mapped[float] = mapped_column(Float)
    reference: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow
    )

    reconciliation_results: Mapped[list["ReconciliationResult"]] = relationship(
        back_populates="transaction"
    )


class Invoice(Base):
    """A single invoice, uploaded via CSV (Phase 1) or parsed from a PDF (Phase 2)."""

    __tablename__ = "invoices"

    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_number: Mapped[str] = mapped_column(String, unique=True, index=True)
    invoice_date: Mapped[datetime.date] = mapped_column(Date)
    amount: Mapped[float] = mapped_column(Float)
    customer_name: Mapped[str | None] = mapped_column(String, nullable=True)
    source: Mapped[str] = mapped_column(String, default="csv")  # "csv" | "pdf"
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow
    )

    reconciliation_result: Mapped["ReconciliationResult | None"] = relationship(
        back_populates="invoice", uselist=False
    )


class ReconciliationResult(Base):
    """Outcome of matching one invoice against the transaction pool, plus the
    human-approval state for anything the matcher couldn't confirm on its own."""

    __tablename__ = "reconciliation_results"
    __table_args__ = (UniqueConstraint("invoice_id", name="uq_reconciliation_invoice"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"))
    transaction_id: Mapped[int | None] = mapped_column(
        ForeignKey("transactions.id"), nullable=True
    )

    status: Mapped[str] = mapped_column(String)  # "matched" | "needs_review"

    # Populated by the explainer node, only for "needs_review" rows.
    possible_reasons: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list
    confidence: Mapped[str | None] = mapped_column(String, nullable=True)  # high|medium|low

    # Human-in-the-loop approval, set from the dashboard.
    review_status: Mapped[str] = mapped_column(String, default="pending")  # pending|approved|rejected

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow
    )

    invoice: Mapped["Invoice"] = relationship(back_populates="reconciliation_result")
    transaction: Mapped["Transaction | None"] = relationship(
        back_populates="reconciliation_results"
    )
