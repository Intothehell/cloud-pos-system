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
