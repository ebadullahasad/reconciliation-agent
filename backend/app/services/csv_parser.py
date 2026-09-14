import re

import pandas as pd

# Phase 1 assumes a single, already-consistent bank export format: one
# "amount" column (signed), not separate debit/credit columns. Multi-bank
# column mapping is explicitly deferred to Phase 2.
STATEMENT_COLUMN_ALIASES = {
    "date": ["date", "transaction_date", "posted_date", "value_date"],
    "description": ["description", "narrative", "details", "memo"],
    "amount": ["amount", "value"],
    "reference": ["reference", "ref", "transaction_ref", "cheque_no"],
}

INVOICE_COLUMN_ALIASES = {
    "invoice_number": ["invoice_number", "invoice_no", "invoice_id", "number"],
    "invoice_date": ["invoice_date", "date", "issue_date"],
    "amount": ["amount", "total", "total_amount", "value"],
    "customer_name": ["customer_name", "customer", "client", "client_name"],
}

REQUIRED_STATEMENT_FIELDS = ["date", "description", "amount"]
REQUIRED_INVOICE_FIELDS = ["invoice_number", "invoice_date", "amount"]


def _normalize_column(name: str) -> str:
    name = name.strip().lower()
    return re.sub(r"[\s\-]+", "_", name)


def _resolve_columns(columns: list[str], aliases: dict[str, list[str]]) -> dict[str, str]:
    """Map our canonical field name -> actual column name in the dataframe."""
    resolved: dict[str, str] = {}
    for field, candidates in aliases.items():
        for candidate in candidates:
            if candidate in columns:
                resolved[field] = candidate
                break
    return resolved


def _load(file_path: str, aliases: dict[str, list[str]], required: list[str]) -> tuple[pd.DataFrame, dict[str, str]]:
    df = pd.read_csv(file_path)
    df.columns = [_normalize_column(c) for c in df.columns]

    field_map = _resolve_columns(list(df.columns), aliases)
    missing = [f for f in required if f not in field_map]
    if missing:
        raise ValueError(
            f"CSV is missing required column(s): {missing}. Found columns: {list(df.columns)}"
        )
    return df, field_map


def parse_statement_csv(file_path: str) -> tuple[list[dict], list[str]]:
    """Returns (rows, errors). Each row: {date, description, amount, reference}."""
    df, field_map = _load(file_path, STATEMENT_COLUMN_ALIASES, REQUIRED_STATEMENT_FIELDS)

    rows: list[dict] = []
    errors: list[str] = []
    for i, raw in df.iterrows():
        try:
            date = pd.to_datetime(raw[field_map["date"]]).date()
            amount = float(raw[field_map["amount"]])
            rows.append(
                {
                    "date": date,
                    "description": str(raw[field_map["description"]]).strip(),
                    "amount": amount,
                    "reference": (
                        str(raw[field_map["reference"]]).strip()
                        if "reference" in field_map and pd.notna(raw[field_map["reference"]])
                        else None
                    ),
                }
            )
        except Exception as exc:
            errors.append(f"row {i + 2}: {exc}")

    return rows, errors


def parse_invoices_csv(file_path: str) -> tuple[list[dict], list[str]]:
    """Returns (rows, errors). Each row: {invoice_number, invoice_date, amount, customer_name}."""
    df, field_map = _load(file_path, INVOICE_COLUMN_ALIASES, REQUIRED_INVOICE_FIELDS)

    rows: list[dict] = []
    errors: list[str] = []
    for i, raw in df.iterrows():
        try:
            invoice_date = pd.to_datetime(raw[field_map["invoice_date"]]).date()
            amount = float(raw[field_map["amount"]])
            rows.append(
                {
                    "invoice_number": str(raw[field_map["invoice_number"]]).strip(),
                    "invoice_date": invoice_date,
                    "amount": amount,
                    "customer_name": (
                        str(raw[field_map["customer_name"]]).strip()
                        if "customer_name" in field_map
                        and pd.notna(raw[field_map["customer_name"]])
                        else None
                    ),
                }
            )
        except Exception as exc:
            errors.append(f"row {i + 2}: {exc}")

    return rows, errors
