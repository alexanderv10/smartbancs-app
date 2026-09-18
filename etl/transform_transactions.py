import csv
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
RAW_FILE = BASE_DIR / "data" / "raw_transactions.csv"
CLEAN_FILE = BASE_DIR / "data" / "clean_transactions.csv"


def normalize_amount(value: str | None) -> str:
    if value is None or value.strip() == "":
        return "0.00"
    cleaned = value.strip().replace("$", "").replace(",", "")
    try:
        return f"{Decimal(cleaned):.2f}"
    except InvalidOperation:
        return "0.00"


def normalize_currency(value: str | None) -> str:
    return (value or "USD").strip().upper() or "USD"


def normalize_date(value: str) -> str:
    candidates = ["%Y-%m-%d", "%d/%m/%Y", "%m-%d-%Y"]
    for fmt in candidates:
        try:
            return datetime.strptime(value.strip(), fmt).date().isoformat()
        except ValueError:
            continue
    raise ValueError(f"Unsupported date format: {value}")


def transform() -> None:
    with RAW_FILE.open(newline="", encoding="utf-8") as raw, CLEAN_FILE.open("w", newline="", encoding="utf-8") as clean:
        reader = csv.DictReader(raw)
        fieldnames = ["transaction_id", "account_id", "amount", "currency", "date"]
        writer = csv.DictWriter(clean, fieldnames=fieldnames)
        writer.writeheader()
        for row in reader:
            writer.writerow(
                {
                    "transaction_id": row["transaction_id"].strip(),
                    "account_id": row["account_id"].strip(),
                    "amount": normalize_amount(row.get("amount")),
                    "currency": normalize_currency(row.get("currency")),
                    "date": normalize_date(row["date"]),
                }
            )


if __name__ == "__main__":
    transform()
    print(f"Clean file generated at {CLEAN_FILE}")
