from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_bcrypt import Bcrypt
from flask_cors import CORS

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
    
    from app.routes.auth import auth_bp
    from app.routes.pos import pos_bp
    from app.routes.customer import customer_bp
    
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(pos_bp, url_prefix='/pos')
    app.register_blueprint(customer_bp, url_prefix='/customer')
    
    with app.app_context():
        from app.models.user import User
        from app.models.customer import Customer, Payment
        
        db.create_all()
        
        if not User.query.filter_by(username='admin').first():
            admin = User(username='admin', email='admin@store.com', role='admin', is_active=True)
            admin.set_password('admin123')
            db.session.add(admin)
            db.session.commit()
            print('Admin user created: admin/admin123')
    
    return app