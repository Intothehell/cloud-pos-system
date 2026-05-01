from flask import Blueprint, render_template, jsonify
from flask_login import login_required, current_user
from app.models.user import User
from app.models.order import Order
from app import db
from datetime import datetime

pos_bp = Blueprint('pos', __name__)

@pos_bp.route('/')
def index():
    if current_user.is_authenticated:
        return render_template('pos/dashboard.html')
    from flask import redirect, url_for
    return redirect(url_for('auth.login'))

@pos_bp.route('/dashboard')
@login_required
def dashboard():
    return render_template('pos/dashboard.html')

@pos_bp.route('/terminal')
@login_required
def terminal():
    return render_template('pos/terminal.html')

# ADD THESE NEW ROUTES:
@pos_bp.route('/sales-detail')
@login_required
def sales_detail():
    """Sales detail page with all today's transactions"""
    return render_template('pos/sales_detail.html')

@pos_bp.route('/api/sales/detail')
@login_required
def api_sales_detail():
    """API for sales detail page"""
    today = datetime.now().date()
    
    # Get today's orders
    orders = Order.query.filter(
        db.func.date(Order.created_at) == today
    ).order_by(Order.created_at.desc()).all()
    
    # Calculate totals
    total_sales = sum(o.total for o in orders)
    retail_sales = sum(o.total for o in orders if o.order_type == 'retail')
    wholesale_sales = sum(o.total for o in orders if o.order_type == 'wholesale')
    cash_sales = sum(o.total for o in orders if o.payment_method == 'cash')
    card_sales = sum(o.total for o in orders if o.payment_method == 'card')
    credit_sales = sum(o.total for o in orders if o.payment_method == 'credit')
    
    return jsonify({
        'summary': {
            'total_sales': total_sales,
            'retail_sales': retail_sales,
            'wholesale_sales': wholesale_sales,
            'cash_sales': cash_sales,
            'card_sales': card_sales,
            'credit_sales': credit_sales,
            'transaction_count': len(orders)
        },
        'orders': [{
            'id': o.id,
            'order_number': o.order_number,
            'type': o.order_type,
            'subtotal': o.subtotal,
            'tax': o.tax_amount,
            'discount': o.discount_amount,
            'total': o.total,
            'payment_method': o.payment_method,
            'payment_status': o.payment_status,
            'cashier': o.cashier_rel.username if o.cashier_rel else 'N/A',
            'customer': o.customer_rel.name if o.customer_rel else 'Walk-in',
            'items_count': len(o.items),
            'time': o.created_at.strftime('%H:%M:%S'),
            'date': o.created_at.strftime('%Y-%m-%d'),
            'notes': o.notes or ''
        } for o in orders]
    })