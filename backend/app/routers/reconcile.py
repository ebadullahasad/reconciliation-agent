from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ReconciliationResult
from app.schemas import MatchRunResponse, ReconciliationResultOut
from app.services.explainer import run_explainer
from app.services.matcher import run_matcher

router = APIRouter(prefix="/reconcile", tags=["reconcile"])


@router.post("/run", response_model=MatchRunResponse)
def run_reconciliation(db: Session = Depends(get_db)):
    results = run_matcher(db)
    matched = sum(1 for r in results if r.status == "matched")
    explained = run_explainer(db)
    return MatchRunResponse(
        invoices_processed=len(results),
        matched=matched,
        needs_review=len(results) - matched,
        explained=explained,
    )


@router.get("/results", response_model=list[ReconciliationResultOut])
def list_results(db: Session = Depends(get_db)):
    return db.query(ReconciliationResult).all()
