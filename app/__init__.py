from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_bcrypt import Bcrypt
from flask_cors import CORS
from sqlalchemy import inspect, text

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
    from app.routes.supply import supply_bp
    app.register_blueprint(supply_bp, url_prefix='/supply')
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(pos_bp, url_prefix='/pos')
    app.register_blueprint(customer_bp, url_prefix='/customer')
    app.register_blueprint(api_bp, url_prefix='/api')
    app.register_blueprint(inventory_bp, url_prefix='/inventory')

    from flask import redirect, url_for

    @app.route('/')
    def home():
        return redirect(url_for('pos.index'))
    
    # Block reviewer role from modifying data
    from flask import request, flash, redirect, url_for, jsonify
    from flask_login import current_user
    
    READ_ONLY_METHODS = {'POST', 'PUT', 'PATCH', 'DELETE'}
    READ_ONLY_PATHS = {'/auth/logout', '/auth/login'}  # Always allowed
    
    @app.before_request
    def block_reviewer_writes():
        if current_user.is_authenticated and current_user.role == 'reviewer':
            if request.method in READ_ONLY_METHODS and request.path not in READ_ONLY_PATHS:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.path.startswith('/api/'):
                    return jsonify({'error': 'Reviewer accounts are read-only'}), 403
                flash('Reviewer accounts are read-only. No changes can be made.', 'warning')
                return redirect(request.referrer or url_for('pos.dashboard'))
    
    with app.app_context():
        from app.models.user import User
        from app.models.customer import Customer, Payment
        from app.models.product import Product, StockMovement
        from app.models.order import Order, OrderItem, Return
        from app.models.supplier import Supplier, SupplierPayment
        from app.models.supply import SupplyBill, SupplyBillItem, SupplyReturn, LedgerOffset
        
        db.create_all()
        _ensure_compat_columns()
    
    return app


def _ensure_compat_columns():
    inspector = inspect(db.engine)
    table_names = inspector.get_table_names()
    if 'suppliers' in table_names:
        existing = {col['name'] for col in inspector.get_columns('suppliers')}
        if 'linked_customer_id' not in existing:
            db.session.execute(text('ALTER TABLE suppliers ADD COLUMN linked_customer_id INTEGER'))
            db.session.commit()
    if 'supplier_payments' in table_names:
        existing = {col['name'] for col in inspector.get_columns('supplier_payments')}
        if 'supply_bill_id' not in existing:
            db.session.execute(text('ALTER TABLE supplier_payments ADD COLUMN supply_bill_id INTEGER'))
            db.session.commit()
    if 'supply_returns' in table_names:
        existing = {col['name'] for col in inspector.get_columns('supply_returns')}
        if 'payable_adjusted' not in existing:
            db.session.execute(text('ALTER TABLE supply_returns ADD COLUMN payable_adjusted FLOAT DEFAULT 0.0'))
            db.session.commit()
        if 'credit_amount' not in existing:
            db.session.execute(text('ALTER TABLE supply_returns ADD COLUMN credit_amount FLOAT DEFAULT 0.0'))
            db.session.commit()
