from app import db
from datetime import datetime


class SupplyBill(db.Model):
    __tablename__ = 'supply_bills'

    id = db.Column(db.Integer, primary_key=True)
    bill_number = db.Column(db.String(24), unique=True, index=True, nullable=False)
    supplier_invoice = db.Column(db.String(80), index=True)
    supplier_id = db.Column(db.Integer, db.ForeignKey('suppliers.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    bill_date = db.Column(db.DateTime, default=datetime.now)
    subtotal = db.Column(db.Float, default=0.0)
    discount_amount = db.Column(db.Float, default=0.0)
    total = db.Column(db.Float, default=0.0)
    paid_amount = db.Column(db.Float, default=0.0)
    balance_amount = db.Column(db.Float, default=0.0)
    payment_method = db.Column(db.String(20), default='credit')
    payment_status = db.Column(db.String(20), default='pending')
    notes = db.Column(db.Text)

    is_cancelled = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    supplier = db.relationship('Supplier', backref='supply_bills')
    creator = db.relationship('User', backref='supply_bills')
    items = db.relationship('SupplyBillItem', backref='bill', lazy=True, cascade='all, delete-orphan')
    returns = db.relationship('SupplyReturn', backref='bill', lazy=True)
    payments = db.relationship('SupplierPayment', backref='supply_bill', lazy=True)

    def generate_bill_number(self):
        date_str = datetime.now().strftime('%Y%m%d')
        count = SupplyBill.query.filter(SupplyBill.bill_number.like(f'SUP-{date_str}%')).count()
        self.bill_number = f'SUP-{date_str}-{count + 1:04d}'

    def recalculate_totals(self):
        self.subtotal = sum(item.line_total for item in self.items)
        self.total = max(self.subtotal - (self.discount_amount or 0), 0)
        self.paid_amount = min(self.paid_amount or 0, self.total)
        self.balance_amount = max(self.total - self.paid_amount, 0)
        if self.balance_amount == 0:
            self.payment_status = 'completed'
        elif self.paid_amount > 0:
            self.payment_status = 'partial'
        else:
            self.payment_status = 'pending'

    def to_dict(self, include_items=False):
        data = {
            'id': self.id,
            'bill_number': self.bill_number,
            'supplier_invoice': self.supplier_invoice or '',
            'supplier_id': self.supplier_id,
            'supplier_name': self.supplier.name if self.supplier else 'N/A',
            'bill_date': self.bill_date.strftime('%Y-%m-%d') if self.bill_date else '',
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'subtotal': self.subtotal or 0,
            'discount_amount': self.discount_amount or 0,
            'total': self.total or 0,
            'paid_amount': self.paid_amount or 0,
            'balance_amount': self.balance_amount or 0,
            'payment_method': self.payment_method or 'credit',
            'payment_status': self.payment_status or 'pending',
            'notes': self.notes or '',
            'item_count': len(self.items),
            'is_cancelled': self.is_cancelled,
            'created_by': self.creator.username if self.creator else 'N/A',
        }
        if include_items:
            data['items'] = [item.to_dict() for item in self.items]
            data['returns'] = [ret.to_dict() for ret in self.returns]
        return data


class SupplyBillItem(db.Model):
    __tablename__ = 'supply_bill_items'

    id = db.Column(db.Integer, primary_key=True)
    supply_bill_id = db.Column(db.Integer, db.ForeignKey('supply_bills.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)

    product_name = db.Column(db.String(200), nullable=False)
    product_barcode = db.Column(db.String(50))
    quantity = db.Column(db.Integer, default=1)
    unit_cost = db.Column(db.Float, default=0.0)
    line_total = db.Column(db.Float, default=0.0)
    previous_stock = db.Column(db.Integer, default=0)
    new_stock = db.Column(db.Integer, default=0)

    product = db.relationship('Product')

    def to_dict(self):
        return {
            'id': self.id,
            'product_id': self.product_id,
            'product_name': self.product_name,
            'product_barcode': self.product_barcode or '',
            'quantity': self.quantity or 0,
            'unit_cost': self.unit_cost or 0,
            'line_total': self.line_total or 0,
            'previous_stock': self.previous_stock or 0,
            'new_stock': self.new_stock or 0,
        }


class SupplyReturn(db.Model):
    __tablename__ = 'supply_returns'

    id = db.Column(db.Integer, primary_key=True)
    return_number = db.Column(db.String(24), unique=True, index=True, nullable=False)
    supply_bill_id = db.Column(db.Integer, db.ForeignKey('supply_bills.id'), nullable=False)
    supplier_id = db.Column(db.Integer, db.ForeignKey('suppliers.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    quantity = db.Column(db.Integer, default=1)
    unit_cost = db.Column(db.Float, default=0.0)
    total = db.Column(db.Float, default=0.0)
    payable_adjusted = db.Column(db.Float, default=0.0)
    credit_amount = db.Column(db.Float, default=0.0)
    previous_stock = db.Column(db.Integer, default=0)
    new_stock = db.Column(db.Integer, default=0)
    reason = db.Column(db.Text)
    status = db.Column(db.String(20), default='completed')
    created_at = db.Column(db.DateTime, default=datetime.now)

    supplier = db.relationship('Supplier', backref='supply_returns')
    product = db.relationship('Product')
    creator = db.relationship('User')

    def generate_return_number(self):
        date_str = datetime.now().strftime('%Y%m%d')
        count = SupplyReturn.query.filter(SupplyReturn.return_number.like(f'SRT-{date_str}%')).count()
        self.return_number = f'SRT-{date_str}-{count + 1:04d}'

    def to_dict(self):
        return {
            'id': self.id,
            'return_number': self.return_number,
            'bill_number': self.bill.bill_number if self.bill else '',
            'supplier_name': self.supplier.name if self.supplier else 'N/A',
            'product_name': self.product.name if self.product else 'N/A',
            'quantity': self.quantity or 0,
            'unit_cost': self.unit_cost or 0,
            'total': self.total or 0,
            'payable_adjusted': self.payable_adjusted or 0,
            'credit_amount': self.credit_amount or 0,
            'reason': self.reason or '',
            'status': self.status,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S'),
        }


class LedgerOffset(db.Model):
    __tablename__ = 'ledger_offsets'

    id = db.Column(db.Integer, primary_key=True)
    offset_number = db.Column(db.String(24), unique=True, index=True, nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=False)
    supplier_id = db.Column(db.Integer, db.ForeignKey('suppliers.id'), nullable=False)
    customer_payment_id = db.Column(db.Integer, db.ForeignKey('payments.id'), nullable=True)
    supplier_payment_id = db.Column(db.Integer, db.ForeignKey('supplier_payments.id'), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    amount = db.Column(db.Float, nullable=False)
    customer_balance_before = db.Column(db.Float, default=0.0)
    customer_balance_after = db.Column(db.Float, default=0.0)
    supplier_balance_before = db.Column(db.Float, default=0.0)
    supplier_balance_after = db.Column(db.Float, default=0.0)
    reference = db.Column(db.String(80))
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.now)

    customer = db.relationship('Customer', backref='ledger_offsets')
    supplier = db.relationship('Supplier', backref='ledger_offsets')
    customer_payment = db.relationship('Payment')
    supplier_payment = db.relationship('SupplierPayment')
    creator = db.relationship('User')

    def generate_offset_number(self):
        date_str = datetime.now().strftime('%Y%m%d')
        count = LedgerOffset.query.filter(LedgerOffset.offset_number.like(f'OFF-{date_str}%')).count()
        self.offset_number = f'OFF-{date_str}-{count + 1:04d}'

    def to_dict(self):
        return {
            'id': self.id,
            'offset_number': self.offset_number,
            'customer_id': self.customer_id,
            'customer_name': self.customer.name if self.customer else 'N/A',
            'supplier_id': self.supplier_id,
            'supplier_name': self.supplier.name if self.supplier else 'N/A',
            'amount': self.amount or 0,
            'customer_balance_before': self.customer_balance_before or 0,
            'customer_balance_after': self.customer_balance_after or 0,
            'supplier_balance_before': self.supplier_balance_before or 0,
            'supplier_balance_after': self.supplier_balance_after or 0,
            'reference': self.reference or '',
            'notes': self.notes or '',
            'created_by': self.creator.username if self.creator else 'N/A',
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S'),
        }
