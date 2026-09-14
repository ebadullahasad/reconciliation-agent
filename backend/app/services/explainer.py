import json
from typing import TypedDict

from langgraph.graph import END, StateGraph
from sqlalchemy.orm import Session

from app.models import Invoice, ReconciliationResult, Transaction
from app.services.llm_client import LLMError, complete_json

SYSTEM_PROMPT = (
    "You are a payments reconciliation assistant. You will be given an invoice "
    "and, if one exists, the closest candidate bank transaction. Explain the "
    "mismatch using ONLY the numeric and text fields provided below — never "
    "invent amounts, dates, customers, or reasons not supported by this data. "
    'Respond with strict JSON only: {"possible_reasons": [string, ...], '
    '"confidence": "high"|"medium"|"low"}.'
)


class ExplainerState(TypedDict):
    invoice_number: str
    invoice_amount: float
    invoice_date: str
    customer_name: str | None
    transaction_amount: float | None
    transaction_date: str | None
    transaction_description: str | None
    transaction_reference: str | None
    possible_reasons: list[str]
    confidence: str


def _build_user_prompt(state: ExplainerState) -> str:
    lines = [
        f"Invoice number: {state['invoice_number']}",
        f"Invoice amount: {state['invoice_amount']}",
        f"Invoice date: {state['invoice_date']}",
        f"Customer name: {state['customer_name'] or 'unknown'}",
    ]
    if state["transaction_amount"] is not None:
        lines += [
            f"Candidate transaction amount: {state['transaction_amount']}",
            f"Candidate transaction date: {state['transaction_date']}",
            f"Candidate transaction description: {state['transaction_description']}",
            f"Candidate transaction reference: {state['transaction_reference'] or 'none'}",
        ]
    else:
        lines.append("No candidate transaction exists anywhere in the bank statement.")
    return "\n".join(lines)


def _explain_node(state: ExplainerState) -> ExplainerState:
    try:
        raw = complete_json(SYSTEM_PROMPT, _build_user_prompt(state))
        reasons = raw.get("possible_reasons")
        confidence = raw.get("confidence")
        if not isinstance(reasons, list) or not all(isinstance(r, str) for r in reasons):
            raise LLMError(f"Malformed possible_reasons: {reasons!r}")
        if confidence not in ("high", "medium", "low"):
            confidence = "low"
        state["possible_reasons"] = reasons[:5]
        state["confidence"] = confidence
    except Exception as exc:
        state["possible_reasons"] = [f"Explanation unavailable: {exc}"]
        state["confidence"] = "low"
    return state


_graph = StateGraph(ExplainerState)
_graph.add_node("explain", _explain_node)
_graph.set_entry_point("explain")
_graph.add_edge("explain", END)
_compiled_graph = _graph.compile()


def explain_mismatch(invoice: Invoice, transaction: Transaction | None) -> dict:
    initial: ExplainerState = {
        "invoice_number": invoice.invoice_number,
        "invoice_amount": invoice.amount,
        "invoice_date": invoice.invoice_date.isoformat(),
        "customer_name": invoice.customer_name,
        "transaction_amount": transaction.amount if transaction else None,
        "transaction_date": transaction.date.isoformat() if transaction else None,
        "transaction_description": transaction.description if transaction else None,
        "transaction_reference": transaction.reference if transaction else None,
        "possible_reasons": [],
        "confidence": "low",
    }
    result = _compiled_graph.invoke(initial)
    return {"possible_reasons": result["possible_reasons"], "confidence": result["confidence"]}


def run_explainer(db: Session) -> int:
    """Explain every needs_review result that doesn't already have one. Safe to
    call repeatedly — already-explained rows are skipped."""

    pending = (
        db.query(ReconciliationResult)
        .filter(ReconciliationResult.status == "needs_review")
        .filter(ReconciliationResult.possible_reasons.is_(None))
        .all()
    )

    for result in pending:
        output = explain_mismatch(result.invoice, result.transaction)
        result.possible_reasons = json.dumps(output["possible_reasons"])
        result.confidence = output["confidence"]

    db.commit()
    return len(pending)
