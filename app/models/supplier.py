from app import db
from datetime import datetime

class Supplier(db.Model):
    __tablename__ = 'suppliers'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), unique=True, nullable=False)
    email = db.Column(db.String(120))
    address = db.Column(db.Text)
    nic = db.Column(db.String(20), unique=True, nullable=False)
    
    # Credit management (money YOU owe THEM)
    balance = db.Column(db.Float, default=0.0)  # Positive = you owe them
    total_purchases = db.Column(db.Float, default=0.0)  # Total bought from them
    total_paid = db.Column(db.Float, default=0.0)  # Total paid to them
    
    # Link to customer if same person
    linked_customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=True)
    linked_customer = db.relationship('Customer', foreign_keys=[linked_customer_id])
    
    is_active = db.Column(db.Boolean, default=True)
    notes = db.Column(db.Text)
    
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    
    payments = db.relationship('SupplierPayment', backref='supplier_rel', lazy=True)
    
    def get_payment_history(self):
        return [{
            'date': p.created_at.strftime('%Y-%m-%d %H:%M'),
            'amount': p.amount,
            'method': p.payment_method,
            'reference': p.reference_number or ''
        } for p in self.payments]


class SupplierPayment(db.Model):
    __tablename__ = 'supplier_payments'
    
    id = db.Column(db.Integer, primary_key=True)
    supplier_id = db.Column(db.Integer, db.ForeignKey('suppliers.id'))
    supply_bill_id = db.Column(db.Integer, db.ForeignKey('supply_bills.id'), nullable=True)
    amount = db.Column(db.Float, nullable=False)
    payment_method = db.Column(db.String(20))  # cash, bank_transfer, check
    reference_number = db.Column(db.String(50))
    notes = db.Column(db.Text)
    received_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.now)
