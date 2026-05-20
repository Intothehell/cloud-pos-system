from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from app.models.user import User
from app.models.product import Product
from app.models.supplier import Supplier, SupplierPayment
from app import db
from datetime import datetime

supply_bp = Blueprint('supply', __name__)

@supply_bp.route('/')
@login_required
def index():
    return redirect(url_for('supply.dashboard'))

@supply_bp.route('/dashboard')
@login_required
def dashboard():
    return render_template('supply/dashboard.html')

@supply_bp.route('/terminal')
@login_required
def terminal():
    return render_template('supply/terminal.html')

@supply_bp.route('/inventory')
@login_required
def inventory():
    return render_template('supply/inventory.html')

@supply_bp.route('/bills')
@login_required
def bills():
    return render_template('supply/bills.html')

@supply_bp.route('/returns')
@login_required
def returns():
    return render_template('supply/returns.html')

# ============ SUPPLIERS ============
@supply_bp.route('/suppliers')
@login_required
def suppliers():
    suppliers = Supplier.query.filter_by(is_active=True).order_by(Supplier.name).all()
    return render_template('supply/suppliers.html', suppliers=suppliers)

@supply_bp.route('/suppliers/add', methods=['POST'])
@login_required
def add_supplier():
    name = request.form.get('name', '').strip()
    phone = request.form.get('phone', '').strip()
    nic = request.form.get('nic', '').strip()
    
    if not name or not phone or not nic:
        flash('Name, phone and NIC are required!', 'danger')
        return redirect(url_for('supply.suppliers'))
    
    if Supplier.query.filter_by(phone=phone).first():
        flash(f'Phone {phone} already exists!', 'danger')
        return redirect(url_for('supply.suppliers'))
    
    if Supplier.query.filter_by(nic=nic).first():
        flash(f'NIC {nic} already exists!', 'danger')
        return redirect(url_for('supply.suppliers'))
    
    supplier = Supplier(
        name=name,
        phone=phone,
        email=request.form.get('email', '').strip(),
        address=request.form.get('address', '').strip(),
        nic=nic,
    )
    db.session.add(supplier)
    db.session.commit()
    flash(f'Supplier {supplier.name} added!', 'success')
    return redirect(url_for('supply.suppliers'))

@supply_bp.route('/suppliers/edit/<int:supplier_id>', methods=['POST'])
@login_required
def edit_supplier(supplier_id):
    if current_user.role not in ['owner', 'manager']:
        flash('Permission denied', 'danger')
        return redirect(url_for('supply.suppliers'))
    
    supplier = Supplier.query.get_or_404(supplier_id)
    
    name = request.form.get('name', '').strip()
    phone = request.form.get('phone', '').strip()
    nic = request.form.get('nic', '').strip()
    
    if not name or not phone or not nic:
        flash('All fields required', 'danger')
        return redirect(url_for('supply.suppliers'))
    
    dup_phone = Supplier.query.filter(Supplier.phone == phone, Supplier.id != supplier_id).first()
    if dup_phone:
        flash(f'Phone already used by {dup_phone.name}', 'danger')
        return redirect(url_for('supply.suppliers'))
    
    dup_nic = Supplier.query.filter(Supplier.nic == nic, Supplier.id != supplier_id).first()
    if dup_nic:
        flash(f'NIC already used by {dup_nic.name}', 'danger')
        return redirect(url_for('supply.suppliers'))
    
    supplier.name = name
    supplier.phone = phone
    supplier.nic = nic
    supplier.email = request.form.get('email', '').strip()
    supplier.address = request.form.get('address', '').strip()
    supplier.balance = float(request.form.get('balance', supplier.balance))
    
    db.session.commit()
    flash(f'Supplier {supplier.name} updated!', 'success')
    return redirect(url_for('supply.suppliers'))

@supply_bp.route('/suppliers/delete/<int:supplier_id>', methods=['POST'])
@login_required
def delete_supplier(supplier_id):
    if current_user.role not in ['owner', 'manager']:
        flash('Permission denied', 'danger')
        return redirect(url_for('supply.suppliers'))
    
    supplier = Supplier.query.get_or_404(supplier_id)
    
    if supplier.balance > 0 and current_user.role != 'owner':
        flash(f'Cannot delete. Outstanding payable of Rs.{supplier.balance:.2f}', 'danger')
        return redirect(url_for('supply.suppliers'))
    
    supplier_name = supplier.name
    supplier.phone = f"{supplier.phone}_deleted_{supplier.id}"
    supplier.nic = f"{supplier.nic}_deleted_{supplier.id}"
    supplier.is_active = False
    db.session.commit()
    
    flash(f'Supplier {supplier_name} deleted.', 'success')
    return redirect(url_for('supply.suppliers'))

@supply_bp.route('/suppliers/record-payment/<int:supplier_id>', methods=['POST'])
@login_required
def record_payment(supplier_id):
    supplier = Supplier.query.get_or_404(supplier_id)
    amount = float(request.form.get('amount', 0))
    payment_method = request.form.get('payment_method', 'cash')
    reference = request.form.get('reference', '')
    
    if amount <= 0:
        flash('Amount must be greater than 0', 'danger')
        return redirect(url_for('supply.suppliers'))
    
    if amount > supplier.balance:
        flash(f'Amount cannot exceed payable of Rs.{supplier.balance:.2f}', 'danger')
        return redirect(url_for('supply.suppliers'))
    
    payment = SupplierPayment(
        supplier_id=supplier.id,
        amount=amount,
        payment_method=payment_method,
        reference_number=reference,
        received_by=current_user.id
    )
    
    supplier.balance -= amount
    supplier.total_paid += amount
    
    db.session.add(payment)
    db.session.commit()
    
    flash(f'Payment of Rs.{amount:.2f} recorded. New payable: Rs.{supplier.balance:.2f}', 'success')
    return redirect(url_for('supply.suppliers'))