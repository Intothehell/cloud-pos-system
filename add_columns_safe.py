# save as add_columns_safe.py
from app import create_app, db
from sqlalchemy import inspect

app = create_app()
with app.app_context():
    inspector = inspect(db.engine)
    existing = [col['name'] for col in inspector.get_columns('orders')]
    
    if 'previous_balance' not in existing:
        db.session.execute(db.text("ALTER TABLE orders ADD COLUMN previous_balance FLOAT DEFAULT 0.0"))
        print("Added previous_balance")
    else:
        print("previous_balance already exists")
    
    if 'new_balance' not in existing:
        db.session.execute(db.text("ALTER TABLE orders ADD COLUMN new_balance FLOAT DEFAULT 0.0"))
        print("Added new_balance")
    else:
        print("new_balance already exists")
    
    if 'credit_paid' not in existing:
        db.session.execute(db.text("ALTER TABLE orders ADD COLUMN credit_paid FLOAT DEFAULT 0.0"))
        print("Added credit_paid")
    else:
        print("credit_paid already exists")
    
    if 'balance_payment_method' not in existing:
        db.session.execute(db.text("ALTER TABLE orders ADD COLUMN balance_payment_method VARCHAR(20)"))
        print("Added balance_payment_method")
    else:
        print("balance_payment_method already exists")
    
    db.session.commit()
    print("Done!")