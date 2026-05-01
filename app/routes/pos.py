<<<<<<< HEAD
=======
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
>>>>>>> 63a0515518e06011422f8f6330026106586034b5
from flask import Blueprint, render_template, redirect, url_for
from flask_login import login_required, current_user
from app.models.user import User
from app.models.product import Product
from app.models.order import Order
from app.models.product import Product
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

<<<<<<< HEAD
# ============ NEW ROUTES ============

@pos_bp.route('/sales-detail')
@login_required
def sales_detail():
    """Sales Summary detail page"""
    return render_template('pos/sales_detail.html')

@pos_bp.route('/transactions-detail')
@login_required
def transactions_detail():
    """All Transactions detail page"""
    return render_template('pos/transactions_detail.html')

# ============ API ROUTES ============

@pos_bp.route('/api/sales/summary')
@login_required
def api_sales_summary():
    """API for Sales Summary page"""
    today = datetime.now().date()
    
    orders = Order.query.filter(
        db.func.date(Order.created_at) == today
    ).all()
    
    total_sales = sum(o.total for o in orders)
    retail_sales = sum(o.total for o in orders if o.order_type == 'retail')
    wholesale_sales = sum(o.total for o in orders if o.order_type == 'wholesale')
    cash_sales = sum(o.total for o in orders if o.payment_method == 'cash')
    card_sales = sum(o.total for o in orders if o.payment_method == 'card')
    credit_sales = sum(o.total for o in orders if o.payment_method == 'credit')
    
    return {
        'total_sales': total_sales,
        'retail_sales': retail_sales,
        'wholesale_sales': wholesale_sales,
        'cash_sales': cash_sales,
        'card_sales': card_sales,
        'credit_sales': credit_sales,
        'transaction_count': len(orders)
    }

@pos_bp.route('/api/transactions/all')
@login_required
def api_all_transactions():
    """API for Transactions detail page"""
    today = datetime.now().date()
    
    orders = Order.query.filter(
        db.func.date(Order.created_at) == today
    ).order_by(Order.created_at.desc()).all()
    
    from flask import jsonify
    return jsonify({
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
            'items': [{
                'name': item.product_name,
                'quantity': item.quantity,
                'price': item.product_price,
                'total': item.line_total
            } for item in o.items],
            'time': o.created_at.strftime('%H:%M:%S'),
            'date': o.created_at.strftime('%Y-%m-%d'),
            'notes': o.notes or ''
        } for o in orders]
    })
=======
@pos_bp.route('/bills')
@login_required
def bills():
    if current_user.role not in ['owner', 'manager']:
        return "Access denied", 403
    today = datetime.now().strftime('%Y-%m-%d')
    return render_template('pos/bills.html', today=today)
>>>>>>> 63a0515518e06011422f8f6330026106586034b5
