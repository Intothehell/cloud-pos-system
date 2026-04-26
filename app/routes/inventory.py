from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user
from functools import wraps
from app import db
from app.models.product import Product, StockMovement

inventory_bp = Blueprint('inventory', __name__)

def owner_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if current_user.role not in ['owner', 'manager']:
            return jsonify({'error': 'Permission denied'}), 403
        return f(*args, **kwargs)
    return decorated_function

@inventory_bp.route('/manage')
@login_required
def manage():
    return render_template('inventory/manage.html')