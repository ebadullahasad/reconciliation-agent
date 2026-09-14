from sqlalchemy.orm import Session

from app.models import Invoice, ReconciliationResult, Transaction

DATE_TOLERANCE_DAYS = 1


def _exact_candidates(
    invoice: Invoice, transactions: list[Transaction], excluded_ids: set[int]
) -> list[Transaction]:
    return [
        t
        for t in transactions
        if t.id not in excluded_ids
        and t.amount == invoice.amount
        and abs((t.date - invoice.invoice_date).days) <= DATE_TOLERANCE_DAYS
    ]


def _closest_candidate(invoice: Invoice, transactions: list[Transaction]) -> Transaction | None:
    if not transactions:
        return None
    return min(
        transactions,
        key=lambda t: (abs(t.amount - invoice.amount), abs((t.date - invoice.invoice_date).days)),
    )


def run_matcher(db: Session) -> list[ReconciliationResult]:
    """Rule-based matching, no LLM. For each invoice: exact amount match within
    +/-1 day -> "matched"; otherwise -> "needs_review", paired with the closest
    transaction candidate for the explainer node to reason about later."""

    invoices = db.query(Invoice).order_by(Invoice.invoice_date).all()
    transactions = db.query(Transaction).all()
    claimed_transaction_ids: set[int] = set()

    results: list[ReconciliationResult] = []
    for invoice in invoices:
        candidates = _exact_candidates(invoice, transactions, claimed_transaction_ids)

        if candidates:
            best = min(candidates, key=lambda t: abs((t.date - invoice.invoice_date).days))
            status = "matched"
            transaction_id = best.id
            claimed_transaction_ids.add(best.id)
        else:
            closest = _closest_candidate(invoice, transactions)
            status = "needs_review"
            transaction_id = closest.id if closest else None

        result = db.query(ReconciliationResult).filter_by(invoice_id=invoice.id).one_or_none()
        if result is None:
            result = ReconciliationResult(invoice_id=invoice.id)
            db.add(result)

        result.status = status
        result.transaction_id = transaction_id
        if status == "matched":
            # Clear any stale explainer output from a previous run.
            result.possible_reasons = None
            result.confidence = None
            result.review_status = "approved"
        else:
            result.review_status = "pending"

        results.append(result)

    db.commit()
    for r in results:
        db.refresh(r)
    return results
