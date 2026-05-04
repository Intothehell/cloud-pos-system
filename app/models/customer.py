from app import db
from datetime import datetime

class Customer(db.Model):
    __tablename__ = 'customers'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), unique=True, nullable=False)
    email = db.Column(db.String(120))
    address = db.Column(db.Text)
    nic = db.Column(db.String(20), unique=True, nullable=False)  # National ID Card - mandatory & unique
    customer_type = db.Column(db.String(20), default='retail')
    
    # Credit management
    balance = db.Column(db.Float, default=0.0)
    credit_limit = db.Column(db.Float, default=5000.0)
    total_purchases = db.Column(db.Float, default=0.0)
    total_paid = db.Column(db.Float, default=0.0)
    
    is_active = db.Column(db.Boolean, default=True)
    notes = db.Column(db.Text)
    
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    
    orders = db.relationship('Order', backref='customer_rel', lazy=True)
    payments = db.relationship('Payment', backref='customer_rel', lazy=True)
    
    def get_payment_history(self):
        return [{
            'date': p.created_at.strftime('%Y-%m-%d %H:%M'),
            'amount': p.amount,
            'method': p.payment_method,
            'reference': p.reference_number
        } for p in self.payments]

class Payment(db.Model):
    __tablename__ = 'payments'
    
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'))
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=True)
    amount = db.Column(db.Float, nullable=False)
    payment_method = db.Column(db.String(20))
    reference_number = db.Column(db.String(50))
    notes = db.Column(db.Text)
    received_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.now)