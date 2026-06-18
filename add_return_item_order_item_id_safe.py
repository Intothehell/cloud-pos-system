import sqlite3
from pathlib import Path


DB_PATH = Path(__file__).resolve().parent / "instance" / "pos.db"


def column_exists(cursor, table, column):
    cursor.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cursor.fetchall())


def main():
    if not DB_PATH.exists():
        raise SystemExit(f"Database not found: {DB_PATH}")

    conn = sqlite3.connect(DB_PATH)
    try:
        cursor = conn.cursor()
        if column_exists(cursor, "return_items", "order_item_id"):
            print("return_items.order_item_id already exists")
            return

        cursor.execute("ALTER TABLE return_items ADD COLUMN order_item_id INTEGER")
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS ix_return_items_order_item_id "
            "ON return_items(order_item_id)"
        )
        conn.commit()
        print("Added return_items.order_item_id")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
