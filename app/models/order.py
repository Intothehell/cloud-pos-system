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
    total = db.Column(db.Float, default=0.0)
    
    # Payment
    payment_method = db.Column(db.String(20))  # cash, card, credit
    payment_status = db.Column(db.String(20), default='pending')
    
    # Cash
    cash_received = db.Column(db.Float)
    change_given = db.Column(db.Float)
    
    # Return flags
    is_returned = db.Column(db.Boolean, default=False)
    return_date = db.Column(db.DateTime)
    
    # Status
    status = db.Column(db.String(20), default='completed')
    notes = db.Column(db.Text)
    
    created_at = db.Column(db.DateTime, default=datetime.now)
    
    items = db.relationship('OrderItem', backref='order', lazy=True, cascade='all, delete-orphan')
    returns = db.relationship('Return', backref='order', lazy=True)
    
    def generate_order_number(self):
        date_str = datetime.now().strftime('%Y%m%d')
        prefix = 'WHO-' if self.order_type == 'wholesale' else 'RET-'
        count = Order.query.filter(Order.order_number.like(f'{prefix}{date_str}%')).count()
        self.order_number = f'{prefix}{date_str}-{count+1:04d}'
    
    def calculate_totals(self):
        self.subtotal = sum(item.line_total for item in self.items)
        self.discount_amount = sum(item.discount_amount for item in self.items)
        self.tax_amount = 0  # No tax
        self.total = self.subtotal - self.discount_amount

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

class Return(db.Model):
    __tablename__ = 'returns'
    
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'))
    return_number = db.Column(db.String(20), unique=True, index=True)
    
    # Return details
    return_type = db.Column(db.String(20))  # refund, replacement, credit_note
    reason = db.Column(db.Text)
    refund_amount = db.Column(db.Float, default=0.0)
    refund_method = db.Column(db.String(20))  # cash, card, credit_note
    
    # Replacement item
    replacement_product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=True)
    replacement_quantity = db.Column(db.Integer, default=0)
    
    # Status
    status = db.Column(db.String(20), default='completed')
    
    # Who processed it
    processed_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.now)
    
    # Relationships
    processor = db.relationship('User', foreign_keys=[processed_by])
    
    def generate_return_number(self):
        date_str = datetime.now().strftime('%Y%m%d')
        count = Return.query.filter(Return.return_number.like(f'RTN-{date_str}%')).count()
        self.return_number = f'RTN-{date_str}-{count+1:04d}'

class ReturnItem(db.Model):
    __tablename__ = 'return_items'
    
    id = db.Column(db.Integer, primary_key=True)
    return_id = db.Column(db.Integer, db.ForeignKey('returns.id'))
    product_name = db.Column(db.String(200))
    product_price = db.Column(db.Float)
    quantity = db.Column(db.Integer, default=1)
    is_damaged = db.Column(db.Boolean, default=False)