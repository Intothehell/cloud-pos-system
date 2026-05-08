from app import create_app, db
from app.models.order import Order

app = create_app()
with app.app_context():
    orders = Order.query.filter(Order.order_type == 'payment').all()
    for o in orders:
        print(o.order_number, o.total, o.created_at)