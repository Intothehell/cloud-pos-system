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
    
    # Block reviewer role from modifying data
    from flask import request, flash, redirect, url_for
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
        
        db.create_all()
    
    return app