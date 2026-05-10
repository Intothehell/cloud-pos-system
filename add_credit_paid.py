from app import create_app, db
from sqlalchemy import inspect

app = create_app()
with app.app_context():
    inspector = inspect(db.engine)
    existing = [col['name'] for col in inspector.get_columns('orders')]
    
    if 'credit_paid' not in existing:
        db.session.execute(db.text("ALTER TABLE orders ADD COLUMN credit_paid FLOAT DEFAULT 0.0"))
        db.session.commit()
        print("Added credit_paid column")
    else:
        print("credit_paid already exists")