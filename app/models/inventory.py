from flask import Blueprint, render_template
from flask_login import login_required, current_user
from functools import wraps

inventory_bp = Blueprint('inventory', __name__)

def owner_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if current_user.role not in ['owner', 'manager']:
            return "Access denied", 403
        return f(*args, **kwargs)
    return decorated

@inventory_bp.route('/manage')
@login_required
@owner_required
def manage():
    return render_template('inventory/manage.html')