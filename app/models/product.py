from app import db
from datetime import datetime

class Product(db.Model):
    __tablename__ = 'products'
    
    id = db.Column(db.Integer, primary_key=True)
    barcode = db.Column(db.String(50), unique=True, index=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    category = db.Column(db.String(100))
    sku = db.Column(db.String(50), unique=True)
    
    # Pricing
    cost_price = db.Column(db.Float, default=0.0)  # What warehouse paid
    retail_price = db.Column(db.Float, default=0.0)  # Regular selling price
    wholesale_price = db.Column(db.Float, default=0.0)  # Price for credit/bulk customers
    
    # Inventory
    stock_quantity = db.Column(db.Integer, default=0)
    min_stock_level = db.Column(db.Integer, default=5)
    
    # Status
    is_active = db.Column(db.Boolean, default=True)
    
    # Meta
    added_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    
    # Relationships
    stock_movements = db.relationship('StockMovement', backref='product', lazy=True)
    
    def to_dict(self):
        return {
            'id': self.id,
            'barcode': self.barcode,
            'name': self.name,
            'category': self.category,
            'retail_price': self.retail_price,
            'wholesale_price': self.wholesale_price,
            'stock_quantity': self.stock_quantity,
            'sku': self.sku
        }

class StockMovement(db.Model):
    """Track all stock movements"""
    __tablename__ = 'stock_movements'
    
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    
    movement_type = db.Column(db.String(20))  # stock_in, stock_out, sale, return, adjustment
    quantity = db.Column(db.Integer)
    previous_stock = db.Column(db.Integer)
    new_stock = db.Column(db.Integer)
    
    reference = db.Column(db.String(100))
    notes = db.Column(db.Text)
    
    created_at = db.Column(db.DateTime, default=datetime.now)
