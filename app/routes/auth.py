from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from app.models.user import User
from app import db

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('pos.dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            login_user(user)
            flash(f'Welcome, {user.username}!', 'success')
            return redirect(url_for('pos.dashboard'))
        else:
            flash('Invalid username or password', 'danger')
    
    return render_template('auth/login.html')

@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out successfully', 'info')
    return redirect(url_for('auth.login'))

@auth_bp.route('/users')
@login_required
def manage_users():
    if current_user.role != 'owner':
        flash('Access denied', 'danger')
        return redirect(url_for('pos.dashboard'))
    users = User.query.order_by(User.role, User.username).all()
    return render_template('auth/users.html', users=users)

@auth_bp.route('/users/add', methods=['POST'])
@login_required
def add_user():
    if current_user.role != 'owner':
        flash('Access denied', 'danger')
        return redirect(url_for('pos.dashboard'))
    
    username = request.form.get('username', '').strip()
    email = request.form.get('email', '').strip()
    password = request.form.get('password', '').strip()
    role = request.form.get('role', 'staff')
    
    if not username or not email or not password:
        flash('All fields required', 'danger')
        return redirect(url_for('auth.manage_users'))
    
    if User.query.filter_by(username=username).first():
        flash('Username already exists', 'danger')
        return redirect(url_for('auth.manage_users'))
    
    user = User(username=username, email=email, role=role)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    
    flash(f'User {username} created', 'success')
    return redirect(url_for('auth.manage_users'))

@auth_bp.route('/users/edit/<int:user_id>', methods=['POST'])
@login_required
def edit_user(user_id):
    if current_user.role != 'owner':
        flash('Access denied', 'danger')
        return redirect(url_for('pos.dashboard'))
    
    user = User.query.get_or_404(user_id)
    
    username = request.form.get('username', '').strip()
    email = request.form.get('email', '').strip()
    password = request.form.get('password', '').strip()
    role = request.form.get('role', 'staff')
    
    if not username or not email:
        flash('Username and email required', 'danger')
        return redirect(url_for('auth.manage_users'))
    
    existing = User.query.filter(User.username == username, User.id != user_id).first()
    if existing:
        flash('Username already taken', 'danger')
        return redirect(url_for('auth.manage_users'))
    
    user.username = username
    user.email = email
    user.role = role
    if password:
        user.set_password(password)
    
    db.session.commit()
    flash(f'User {username} updated', 'success')
    return redirect(url_for('auth.manage_users'))

@auth_bp.route('/users/toggle/<int:user_id>', methods=['POST'])
@login_required
def toggle_user(user_id):
    if current_user.role != 'owner':
        flash('Access denied', 'danger')
        return redirect(url_for('pos.dashboard'))
    
    user = User.query.get_or_404(user_id)
    
    if user.id == current_user.id:
        flash('Cannot deactivate yourself', 'danger')
        return redirect(url_for('auth.manage_users'))
    
    user.is_active = not user.is_active
    db.session.commit()
    flash(f'User {user.username} {"activated" if user.is_active else "deactivated"}', 'success')
    return redirect(url_for('auth.manage_users'))