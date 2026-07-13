from pathlib import Path
import sqlite3


DB_PATH = Path(__file__).resolve().parents[1] / "apps" / "backend" / "invoice_ocr.db"


def infer_ledger_name(description: str | None) -> str | None:
    if not description:
        return None

    value = description.strip()
    lower = value.lower()

    prefixes = [
        "cheque to ",
        "check to ",
        "payment to ",
        "paid to ",
        "upi ",
    ]
    for prefix in prefixes:
        if lower.startswith(prefix):
            return value[len(prefix):].strip() or value

    suffixes = [
        " settlement received",
        " payment issued, cheque not yet presented",
        " recorded in books, not yet credited",
        " received",
    ]
    for suffix in suffixes:
        if lower.endswith(suffix):
            return value[: -len(suffix)].strip(" -,:") or value

    if lower.startswith("cash deposit - "):
        return value[len("cash deposit - "):].strip() or value

    return value


def main() -> None:
    with sqlite3.connect(DB_PATH) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(ledger_entries)")}
        if "ledger_name" not in columns:
            conn.execute("ALTER TABLE ledger_entries ADD COLUMN ledger_name TEXT")

        rows = conn.execute(
            "SELECT id, description, ledger_name FROM ledger_entries"
        ).fetchall()

        updates = []
        for entry_id, description, ledger_name in rows:
            if ledger_name and ledger_name.strip():
                continue
            inferred = infer_ledger_name(description)
            updates.append((inferred, entry_id))

        conn.executemany(
            "UPDATE ledger_entries SET ledger_name = ? WHERE id = ?",
            updates,
        )
        conn.commit()

    print(f"Backfilled {len(updates)} ledger names in {DB_PATH}")


if __name__ == "__main__":
    main()
