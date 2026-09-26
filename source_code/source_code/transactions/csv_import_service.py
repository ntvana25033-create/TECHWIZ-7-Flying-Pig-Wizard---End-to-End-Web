from __future__ import annotations

import csv
import io
from datetime import datetime
from decimal import Decimal, InvalidOperation

from .ai_service import classifier
from .models import Category, TransactionImportRow

MAX_IMPORT_ROWS = 2000
REQUIRED_HEADERS = {"type", "amount", "description", "date"}
OPTIONAL_HEADERS = {"category"}
CSV_HEADERS = ["type", "category", "amount", "description", "date"]

TYPE_ALIASES = {
    "income": "income",
    "expense": "expense",
}


DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y")


def normalize_type(value):
    key = " ".join((value or "").strip().lower().split())
    return TYPE_ALIASES.get(key, "")


def parse_amount(value):
    raw = (value or "").strip()
    if not raw:
        return None

    cleaned = (
        raw.replace("VND", "")
        .replace("vnd", "")
        .replace("₫", "")
        .replace(" ", "")
    )

    if "," in cleaned and "." not in cleaned:
        parts = cleaned.split(",")
        if len(parts) > 2 or (len(parts) == 2 and len(parts[-1]) == 3):
            cleaned = "".join(parts)
        else:
            cleaned = cleaned.replace(",", ".")
    elif "." in cleaned and "," not in cleaned:
        parts = cleaned.split(".")
        if len(parts) > 2 or (len(parts) == 2 and len(parts[-1]) == 3):
            cleaned = "".join(parts)
    elif "," in cleaned and "." in cleaned:
        cleaned = cleaned.replace(",", "")

    try:
        amount = Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return None

    if amount <= 0 or amount >= Decimal("100000000"):
        return None
    return amount.quantize(Decimal("0.01"))


def parse_date(value):
    raw = (value or "").strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def decode_csv(uploaded_file):
    raw = uploaded_file.read()
    if not raw:
        raise ValueError("The CSV file is empty.")

    for encoding in ("utf-8-sig", "utf-8"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("The CSV file must use UTF-8 encoding.")


def read_csv_rows(uploaded_file):
    text = decode_csv(uploaded_file)
    stream = io.StringIO(text, newline="")
    reader = csv.DictReader(stream)
    if not reader.fieldnames:
        raise ValueError("Could not find a header row in the CSV file.")

    normalized_headers = [str(name or "").strip().lower() for name in reader.fieldnames]
    reader.fieldnames = normalized_headers
    missing = REQUIRED_HEADERS - set(normalized_headers)
    if missing:
        raise ValueError(
            "CSV is missing required columns: " + ", ".join(sorted(missing)) + "."
        )

    unsupported = set(normalized_headers) - REQUIRED_HEADERS - OPTIONAL_HEADERS
    if unsupported:
        raise ValueError(
            "CSV contains unsupported columns: " + ", ".join(sorted(unsupported)) + "."
        )

    rows = []
    for row_number, source_row in enumerate(reader, start=2):
        if not any((value or "").strip() for value in source_row.values()):
            continue
        rows.append((row_number, {key: (value or "").strip() for key, value in source_row.items()}))
        if len(rows) > MAX_IMPORT_ROWS:
            raise ValueError(f"You can import at most {MAX_IMPORT_ROWS} transactions per batch.")

    if not rows:
        raise ValueError("The CSV file does not contain any data rows.")
    return rows


def category_lookup():
    lookup = {}
    for category in Category.objects.all():
        key = (category.type, " ".join(category.name.strip().lower().split()))
        lookup[key] = category
    return lookup


def build_import_row(batch, row_number, source_row, categories=None):
    categories = categories or category_lookup()
    errors = []
    notes = []

    transaction_type = normalize_type(source_row.get("type"))
    if not transaction_type:
        errors.append("Type must be income or expense.")

    amount = parse_amount(source_row.get("amount"))
    if amount is None:
        errors.append("Amount is invalid or must be greater than 0.")

    transaction_date = parse_date(source_row.get("date"))
    if transaction_date is None:
        errors.append("Date is invalid. Use YYYY-MM-DD or DD/MM/YYYY.")

    description = (source_row.get("description") or "").strip()
    category_text = " ".join((source_row.get("category") or "").strip().lower().split())
    selected_category = None

    if transaction_type and category_text:
        selected_category = categories.get((transaction_type, category_text))
        if not selected_category:
            notes.append("The CSV category does not match the system; AI will try to suggest another category.")

    prediction = None
    if transaction_type and description:
        prediction = classifier.predict(description, transaction_type)

    predicted_category = None
    confidence = None
    if prediction:
        predicted_category = Category.objects.filter(
            pk=prediction["category_id"], type=transaction_type
        ).first()
        confidence = prediction["confidence"]

    if selected_category is None and predicted_category is not None:
        selected_category = predicted_category
        notes.append("Category was filled by AI; review it before confirming.")

    if selected_category is None:
        errors.append("No category could be determined. Select a category in the staging table.")

    return TransactionImportRow(
        batch=batch,
        row_number=row_number,
        type=transaction_type,
        category=selected_category,
        amount=amount,
        description=description,
        date=transaction_date,
        ai_suggested_category=predicted_category,
        ai_prediction_confidence=confidence,
        validation_errors=errors,
        review_note=" ".join(notes),
        source_row=source_row,
    )


def validate_edited_row(*, transaction_type, category, amount_text, description, date_text):
    errors = []
    normalized_type = normalize_type(transaction_type)
    if not normalized_type:
        errors.append("Type is invalid.")

    amount = parse_amount(amount_text)
    if amount is None:
        errors.append("Amount is invalid or must be greater than 0.")

    transaction_date = parse_date(date_text)
    if transaction_date is None:
        errors.append("Date is invalid.")

    description = (description or "").strip()

    if category is None:
        errors.append("You must select a category.")
    elif normalized_type and category.type != normalized_type:
        errors.append("The category does not belong to the selected transaction type.")

    prediction = None
    if normalized_type and description:
        prediction = classifier.predict(description, normalized_type)

    return {
        "type": normalized_type,
        "category": category,
        "amount": amount,
        "description": description,
        "date": transaction_date,
        "prediction": prediction,
        "errors": errors,
    }
