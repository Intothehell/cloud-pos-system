from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_bcrypt import Bcrypt
from flask_cors import CORS
from sqlalchemy import text

db = SQLAlchemy()
login_manager = LoginManager()
bcrypt = Bcrypt()

def create_app():
    app = Flask(__name__)
    app.config.from_object('app.config.DevelopmentConfig')
    
    db.init_app(app)
    login_manager.init_app(app)
    bcrypt.init_app(app)
    CORS(app)
    
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please log in to access this page.'
    
    from app.routes.auth import auth_bp
    from app.routes.pos import pos_bp
    from app.routes.customer import customer_bp
    from app.routes.api import api_bp
    from app.routes.inventory import inventory_bp
    
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(pos_bp, url_prefix='/pos')
    app.register_blueprint(customer_bp, url_prefix='/customer')
    app.register_blueprint(api_bp, url_prefix='/api')
    app.register_blueprint(inventory_bp, url_prefix='/inventory')
    
    with app.app_context():
        from app.models.user import User
        from app.models.customer import Customer, Payment
        from app.models.product import Product, StockMovement
        from app.models.order import Order, OrderItem
        
        db.create_all()
        
        # Create users
        if not User.query.filter_by(username='owner').first():
            owner = User(username='owner', email='owner@warehouse.com', role='owner', is_active=True)
            owner.set_password('owner123')
            db.session.add(owner)
            
            staff = User(username='staff', email='staff@warehouse.com', role='staff', is_active=True)
            staff.set_password('staff123')
            db.session.add(staff)
            db.session.commit()
            print('Users created: owner/owner123, staff/staff123')
        
        # Add sample products
        if Product.query.count() == 0:
            products = [
                Product(barcode='1001', name='3-Seater Sofa', category='Sofas', cost_price=400, wholesale_price=650, retail_price=899, stock_quantity=10, sku='SOFA-001'),
                Product(barcode='1002', name='L-Shape Sofa', category='Sofas', cost_price=600, wholesale_price=950, retail_price=1299, stock_quantity=5, sku='SOFA-002'),
                Product(barcode='1003', name='Dining Table', category='Tables', cost_price=250, wholesale_price=400, retail_price=599, stock_quantity=8, sku='TBL-001'),
                Product(barcode='1004', name='Coffee Table', category='Tables', cost_price=80, wholesale_price=150, retail_price=249, stock_quantity=0, sku='TBL-002'),
                Product(barcode='1005', name='Queen Bed', category='Beds', cost_price=350, wholesale_price=550, retail_price=799, stock_quantity=6, sku='BED-001'),
                Product(barcode='1006', name='Office Chair', category='Chairs', cost_price=60, wholesale_price=100, retail_price=199, stock_quantity=20, sku='CHR-001'),
                Product(barcode='1007', name='TV Cabinet', category='Cabinets', cost_price=180, wholesale_price=300, retail_price=449, stock_quantity=2, sku='CAB-001'),
                Product(barcode='1008', name='Wardrobe', category='Cabinets', cost_price=300, wholesale_price=500, retail_price=749, stock_quantity=3, sku='CAB-002'),
            ]
            for p in products:
                db.session.add(p)
            db.session.commit()
            print('Sample products added')
    
    return app