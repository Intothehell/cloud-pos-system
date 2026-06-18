import sqlite3
from pathlib import Path


DB_PATH = Path(__file__).resolve().parent / "instance" / "pos.db"


def column_exists(cursor, table, column):
    cursor.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cursor.fetchall())


def add_column_if_missing(cursor, table, column, sql_type):
    if column_exists(cursor, table, column):
        print(f"{table}.{column} already exists")
        return False
    cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {sql_type}")
    print(f"Added {table}.{column}")
    return True


def main():
    if not DB_PATH.exists():
        raise SystemExit(f"Database not found: {DB_PATH}")

    conn = sqlite3.connect(DB_PATH)
    try:
        cursor = conn.cursor()
        changed = False
        changed |= add_column_if_missing(cursor, "returns", "previous_balance", "FLOAT")
        changed |= add_column_if_missing(cursor, "returns", "new_balance", "FLOAT")
        if changed:
            conn.commit()
            print("Return balance columns added safely.")
        else:
            print("No changes needed.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
