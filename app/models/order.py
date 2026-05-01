from app import db
from datetime import datetime

class Order(db.Model):
    __tablename__ = 'orders'
    
    id = db.Column(db.Integer, primary_key=True)
    order_number = db.Column(db.String(20), unique=True, index=True)
    order_type = db.Column(db.String(20), default='retail')  # retail, wholesale
    sale_type = db.Column(db.String(20), default='retail')
    
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=True)
    
    # Customer info (for walk-in customers)
    customer_name = db.Column(db.String(100))
    customer_phone = db.Column(db.String(20))
    customer_address = db.Column(db.Text)
    
    # Financials
    subtotal = db.Column(db.Float, default=0.0)
    tax_amount = db.Column(db.Float, default=0.0)
    discount_amount = db.Column(db.Float, default=0.0)
    delivery_charge = db.Column(db.Float, default=0.0)
    total = db.Column(db.Float, default=0.0)
    
    # Payment
    payment_method = db.Column(db.String(20))  # cash, card, credit
    payment_status = db.Column(db.String(20), default='pending')
    
    # Cash
    cash_received = db.Column(db.Float)
    change_given = db.Column(db.Float)
    
    # Status
    status = db.Column(db.String(20), default='completed')
    notes = db.Column(db.Text)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    items = db.relationship('OrderItem', backref='order', lazy=True, cascade='all, delete-orphan')
    
    def generate_order_number(self):
        date_str = datetime.now().strftime('%Y%m%d')
        prefix = 'WHO-' if self.order_type == 'wholesale' else 'RET-'
        count = Order.query.filter(Order.order_number.like(f'{prefix}{date_str}%')).count()
        self.order_number = f'{prefix}{date_str}-{count+1:04d}'
    
    def calculate_totals(self):
        self.subtotal = sum(item.line_total for item in self.items)
        self.discount_amount = sum(item.discount_amount for item in self.items)
        self.tax_amount = 0  # No tax
        self.total = self.subtotal - self.discount_amount + (self.delivery_charge or 0)

class OrderItem(db.Model):
    __tablename__ = 'order_items'
    
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'))
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'))
    
    product_name = db.Column(db.String(200))
    product_barcode = db.Column(db.String(50))
    product_price = db.Column(db.Float)
    
    quantity = db.Column(db.Integer, default=1)
    discount_percent = db.Column(db.Float, default=0)
    line_total = db.Column(db.Float)
    discount_amount = db.Column(db.Float, default=0)