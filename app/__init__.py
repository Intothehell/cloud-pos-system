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
    
    # Import blueprints
    from app.routes.auth import auth_bp
    from app.routes.pos import pos_bp
    from app.routes.customer import customer_bp
    from app.routes.api import api_bp
    from app.routes.inventory import inventory_bp
    
    # Register blueprints
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(pos_bp, url_prefix='/pos')
    app.register_blueprint(customer_bp, url_prefix='/customer')
    app.register_blueprint(api_bp, url_prefix='/api')
    app.register_blueprint(inventory_bp, url_prefix='/inventory')
    
    # Create tables and seed data
    with app.app_context():
        from app.models.user import User
        from app.models.customer import Customer, Payment
        from app.models.product import Product, StockMovement
        from app.models.order import Order, OrderItem
        
        # Create all tables
        db.create_all()
        
        # Add NIC column if upgrading from old database
        try:
            db.session.execute(text('ALTER TABLE customers ADD COLUMN nic VARCHAR(20)'))
            db.session.commit()
        except:
            pass  # Column already exists
        
        try:
            db.session.execute(text('ALTER TABLE customers ADD COLUMN total_paid FLOAT DEFAULT 0.0'))
            db.session.commit()
        except:
            pass
        
        try:
            db.session.execute(text('ALTER TABLE orders ADD COLUMN order_type VARCHAR(20) DEFAULT "retail"'))
            db.session.commit()
        except:
            pass
        
        # Create default users if not exist
        if not User.query.filter_by(username='owner').first():
            owner = User(
                username='owner',
                email='owner@warehouse.com',
                role='owner',
                is_active=True
            )
            owner.set_password('owner123')
            db.session.add(owner)
            
            staff = User(
                username='staff',
                email='staff@warehouse.com',
                role='staff',
                is_active=True
            )
            staff.set_password('staff123')
            db.session.add(staff)
            
            db.session.commit()
            print('=' * 50)
            print('✓ Users Created:')
            print('  Owner: owner / owner123 (Full Access)')
            print('  Staff: staff / staff123 (POS Only)')
            print('=' * 50)
        
        # Add sample products if empty
        if Product.query.count() == 0:
            products = [
                Product(barcode='1001', name='3-Seater Sofa', category='Sofas', 
                       cost_price=400, wholesale_price=650, retail_price=899, 
                       stock_quantity=10, sku='SOFA-001'),
                Product(barcode='1002', name='L-Shape Sofa', category='Sofas', 
                       cost_price=600, wholesale_price=950, retail_price=1299, 
                       stock_quantity=5, sku='SOFA-002'),
                Product(barcode='1003', name='Dining Table 6-Seater', category='Tables', 
                       cost_price=250, wholesale_price=400, retail_price=599, 
                       stock_quantity=8, sku='TBL-001'),
                Product(barcode='1004', name='Coffee Table', category='Tables', 
                       cost_price=80, wholesale_price=150, retail_price=249, 
                       stock_quantity=15, sku='TBL-002'),
                Product(barcode='1005', name='Queen Bed Frame', category='Beds', 
                       cost_price=350, wholesale_price=550, retail_price=799, 
                       stock_quantity=6, sku='BED-001'),
                Product(barcode='1006', name='King Bed Frame', category='Beds', 
                       cost_price=450, wholesale_price=700, retail_price=999, 
                       stock_quantity=4, sku='BED-002'),
                Product(barcode='1007', name='Office Chair', category='Chairs', 
                       cost_price=60, wholesale_price=100, retail_price=199, 
                       stock_quantity=20, sku='CHR-001'),
                Product(barcode='1008', name='Dining Chair Set of 4', category='Chairs', 
                       cost_price=120, wholesale_price=200, retail_price=349, 
                       stock_quantity=12, sku='CHR-002'),
                Product(barcode='1009', name='TV Cabinet', category='Cabinets', 
                       cost_price=180, wholesale_price=300, retail_price=449, 
                       stock_quantity=7, sku='CAB-001'),
                Product(barcode='1010', name='Wardrobe 3-Door', category='Cabinets', 
                       cost_price=300, wholesale_price=500, retail_price=749, 
                       stock_quantity=3, sku='CAB-002'),
            ]
            for p in products:
                db.session.add(p)
            db.session.commit()
            print('✓ 10 Sample Products Added')
            print('=' * 50)
        
        # Add sample wholesale customer
        if Customer.query.count() == 0:
            customer = Customer(
                name='ABC Furniture Store',
                phone='0771234567',
                email='abc@furniture.com',
                address='123 Main Street, Colombo',
                nic='987654321V',
                customer_type='wholesale',
                credit_limit=50000,
                balance=0.0
            )
            db.session.add(customer)
            db.session.commit()
            print('✓ Sample Wholesale Customer Added')
            print('=' * 50)
    
    return app