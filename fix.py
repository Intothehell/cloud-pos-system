# fix_pending.py
from app import create_app, db
from app.models.order import Order

app = create_app()
with app.app_context():
    orders = Order.query.filter_by(payment_status='pending').all()
    for o in orders:
        o.payment_status = 'completed'
    db.session.commit()
    print(f"Fixed {len(orders)} orders")