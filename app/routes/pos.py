from flask import Blueprint, render_template
from flask_login import login_required
from app.models.user import User

pos_bp = Blueprint('pos', __name__)

@pos_bp.route('/dashboard')
@login_required
def dashboard():
    users_count = User.query.count()
    return render_template('pos/dashboard.html', users_count=users_count)

@pos_bp.route('/terminal')
@login_required
def terminal():
    """POS Terminal"""
    return render_template('pos/terminal.html')
from flask import Blueprint, render_template, redirect, url_for
from flask_login import login_required, current_user
from app.models.user import User
from app.models.product import Product
from app.models.order import Order
from app import db
from datetime import datetime

pos_bp = Blueprint('pos', __name__)

@pos_bp.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('pos.dashboard'))
    return redirect(url_for('auth.login'))

@pos_bp.route('/dashboard')
@login_required
def dashboard():
    users_count = User.query.count()
    return render_template('pos/dashboard.html', users_count=users_count)

@pos_bp.route('/terminal')
@login_required
def terminal():
    return render_template('pos/terminal.html')

@pos_bp.route('/bills')
@login_required
def bills():
    if current_user.role not in ['owner', 'manager']:
        return "Access denied", 403
    today = datetime.now().strftime('%Y-%m-%d')
    return render_template('pos/bills.html', today=today)