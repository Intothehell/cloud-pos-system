# save as add_columns.py
from app import create_app, db

app = create_app()
with app.app_context():
    db.session.execute(db.text("ALTER TABLE orders ADD COLUMN previous_balance FLOAT DEFAULT 0.0"))
    db.session.execute(db.text("ALTER TABLE orders ADD COLUMN new_balance FLOAT DEFAULT 0.0"))
    db.session.commit()
    print("Columns added!")