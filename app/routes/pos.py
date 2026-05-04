from flask import Blueprint, render_template, redirect, url_for, jsonify
from flask_login import login_required, current_user
from app.models.user import User
from app.models.product import Product
from app.models.order import Order, Return
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
    today = datetime.now().strftime('%Y-%m-%d')
    return render_template('pos/bills.html', today=today)

@pos_bp.route('/returns')
@login_required
def returns():
    return render_template('pos/returns.html')

# ============ API ROUTES ============

@pos_bp.route('/api/sales/summary')
@login_required
def api_sales_summary():
    today = datetime.now().date()
    orders = Order.query.filter(
        db.func.date(Order.created_at) == today
    ).all()
    
    return jsonify({
        'total_sales': sum(o.total for o in orders),
        'retail_sales': sum(o.total for o in orders if o.order_type == 'retail'),
        'wholesale_sales': sum(o.total for o in orders if o.order_type == 'wholesale'),
        'cash_sales': sum(o.total for o in orders if o.payment_method == 'cash'),
        'card_sales': sum(o.total for o in orders if o.payment_method == 'card'),
        'credit_sales': sum(o.total for o in orders if o.payment_method == 'credit'),
        'transaction_count': len(orders)
    })

@pos_bp.route('/api/transactions/all')
@login_required
def api_all_transactions():
    today = datetime.now().date()
    orders = Order.query.filter(
        db.func.date(Order.created_at) == today
    ).order_by(Order.created_at.desc()).all()
    
    return jsonify({
        'orders': [{
            'id': o.id,
            'order_number': o.order_number,
            'type': o.order_type,
            'subtotal': o.subtotal,
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

# ============ RETURNS API ============
@pos_bp.route('/api/returns/all')
@login_required
def api_all_returns():
    """Get all returns history"""
    returns = Return.query.order_by(Return.created_at.desc()).limit(50).all()
    
    return jsonify({
        'returns': [{
            'return_number': r.return_number,
            'order_number': r.order.order_number if r.order else 'N/A',
            'type': r.return_type,
            'reason': r.reason,
            'refund_amount': r.refund_amount,
            'refund_method': r.refund_method,
            'status': r.status,
            'created_at': r.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'customer': r.order.customer_name if r.order else 'N/A'
        } for r in returns]
    })