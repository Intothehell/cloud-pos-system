from flask import Blueprint, render_template, redirect, url_for
from flask_login import login_required, current_user
from app.models.user import User
from app.models.product import Product
from app.models.order import Order
from app.models.customer import Customer
from app import db
from datetime import datetime

pos_bp = Blueprint('pos', __name__)

@pos_bp.route('/')
def index():
    """Home page"""
    if current_user.is_authenticated:
        return redirect(url_for('pos.dashboard'))
    return redirect(url_for('auth.login'))

@pos_bp.route('/dashboard')
@login_required
def dashboard():
    """Main dashboard"""
    users_count = User.query.count()
    products_count = Product.query.filter_by(is_active=True).count()
    
    today = datetime.now().date()
    today_orders = Order.query.filter(
        db.func.date(Order.created_at) == today
    ).all()
    
    stats = {
        'today_sales': sum(o.total for o in today_orders),
        'transaction_count': len(today_orders),
        'products_count': products_count,
        'users_count': users_count
    }
    
    return render_template('pos/dashboard.html', stats=stats)

@pos_bp.route('/terminal')
@login_required
def terminal():
    """POS Terminal"""
    return render_template('pos/terminal.html')

@pos_bp.route('/bills')
@login_required
def bills():
    """Bill History"""
    if current_user.role not in ['owner', 'manager']:
        return "Access denied", 403
    
    today = datetime.now().strftime('%Y-%m-%d')
    return render_template('pos/bills.html', today=today)