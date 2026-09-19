import csv
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
RAW_FILE = BASE_DIR / "data" / "raw_transactions.csv"
CLEAN_FILE = BASE_DIR / "data" / "clean_transactions.csv"


# Limpia montos con simbolos, comas o valores vacios y los deja con dos decimales.
def normalize_amount(value: str | None) -> str:
    # Convierte montos sucios como "$100.50" o "1,200.75" a un decimal estandar.
    if value is None or value.strip() == "":
        return "0.00"
    cleaned = value.strip().replace("$", "").replace(",", "")
    try:
        return f"{Decimal(cleaned):.2f}"
    except InvalidOperation:
        return "0.00"


# Normaliza la moneda a mayusculas y usa USD si viene vacia.
def normalize_currency(value: str | None) -> str:
    return (value or "USD").strip().upper() or "USD"


# Convierte diferentes formatos de fecha al formato estandar YYYY-MM-DD.
def normalize_date(value: str) -> str:
    # Acepta varios formatos de entrada y entrega YYYY-MM-DD.
    candidates = ["%Y-%m-%d", "%d/%m/%Y", "%m-%d-%Y"]
    for fmt in candidates:
        try:
            return datetime.strptime(value.strip(), fmt).date().isoformat()
        except ValueError:
            continue
    raise ValueError(f"Unsupported date format: {value}")


# Lee el CSV crudo, normaliza sus columnas y genera el archivo limpio.
def transform() -> None:
    # El reto pide demostrar transformacion: entrada cruda -> salida lista para analisis/IA.
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
