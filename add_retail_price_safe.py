# save as add_retail_price_safe.py
from app import create_app, db
from sqlalchemy import inspect, text

app = create_app()
with app.app_context():
    inspector = inspect(db.engine)
    existing = [col['name'] for col in inspector.get_columns('products')]
    
    if 'retail_price' not in existing:
        db.session.execute(text("ALTER TABLE products ADD COLUMN retail_price FLOAT DEFAULT 0.0"))
        print("Added retail_price to products")
    else:
        print("retail_price already exists")
    
    db.session.commit()
    print("Done!")