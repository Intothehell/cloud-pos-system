"""
Create or update supply-module database objects without deleting POS data.

Run from the project root with the same Python environment you use for Flask:

    python setup_supply_tables_safe.py

The script is intentionally additive:
- creates missing SQLAlchemy tables with db.create_all()
- adds only missing compatibility columns
- never drops tables, deletes rows, or rewrites existing values
"""

from sqlalchemy import inspect, text

from app import create_app, db


REQUIRED_TABLES = [
    'supply_bills',
    'supply_bill_items',
    'supply_returns',
    'ledger_offsets',
]

REQUIRED_COLUMNS = {
    'suppliers': {
        'linked_customer_id': 'INTEGER',
    },
    'supplier_payments': {
        'supply_bill_id': 'INTEGER',
    },
    'supply_returns': {
        'payable_adjusted': 'FLOAT DEFAULT 0.0',
        'credit_amount': 'FLOAT DEFAULT 0.0',
    },
}


def add_column_if_missing(table_name, column_name, sql_type):
    inspector = inspect(db.engine)
    if table_name not in inspector.get_table_names():
        print(f'SKIP: table {table_name} does not exist yet')
        return

    existing = {column['name'] for column in inspector.get_columns(table_name)}
    if column_name in existing:
        print(f'OK: {table_name}.{column_name} already exists')
        return

    db.session.execute(text(f'ALTER TABLE {table_name} ADD COLUMN {column_name} {sql_type}'))
    db.session.commit()
    print(f'ADDED: {table_name}.{column_name}')


def main():
    app = create_app()
    with app.app_context():
        print(f'Database: {db.engine.url}')
        db.create_all()
        inspector = inspect(db.engine)

        for table_name in REQUIRED_TABLES:
            if table_name in inspector.get_table_names():
                print(f'OK: table {table_name}')
            else:
                print(f'MISSING: table {table_name}')

        for table_name, columns in REQUIRED_COLUMNS.items():
            for column_name, sql_type in columns.items():
                add_column_if_missing(table_name, column_name, sql_type)

        print('Supply database setup finished safely.')


if __name__ == '__main__':
    main()
