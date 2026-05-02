from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user
from app import db
from app.models.customer import Customer, Payment

customer_bp = Blueprint('customer', __name__)

@customer_bp.route('/list')
@login_required
def list_customers():
    """List all customers"""
    customers = Customer.query.filter_by(is_active=True).order_by(Customer.customer_type, Customer.name).all()
    return render_template('customer/list.html', customers=customers)

@customer_bp.route('/add', methods=['POST'])
@login_required
def add_customer():
    """Add new customer"""
    phone = request.form.get('phone')
    
    # Check if phone already exists
    existing = Customer.query.filter_by(phone=phone).first()
    if existing:
        flash(f'Phone number {phone} already exists! Customer: {existing.name}', 'danger')
        return redirect(url_for('customer.list_customers'))
    
    customer = Customer(
        name=request.form.get('name'),
        phone=phone,
        email=request.form.get('email'),
        address=request.form.get('address'),
        nic=request.form.get('nic'),
        customer_type=request.form.get('customer_type', 'retail'),
        credit_limit=float(request.form.get('credit_limit', 5000))
    )
    db.session.add(customer)
    db.session.commit()
    flash(f'Customer {customer.name} added successfully!', 'success')
    return redirect(url_for('customer.list_customers'))

@customer_bp.route('/delete/<int:customer_id>', methods=['POST'])
@login_required
def delete_customer(customer_id):
    """Delete customer (soft delete - set is_active to False)"""
    if current_user.role not in ['owner', 'manager']:
        flash('You do not have permission to delete customers.', 'danger')
        return redirect(url_for('customer.list_customers'))
    
    customer = Customer.query.get_or_404(customer_id)
    
    # Check if customer has pending balance
    if customer.balance > 0:
        flash(f'Cannot delete {customer.name}. They have an outstanding balance of ${customer.balance:.2f}. Please settle the balance first.', 'danger')
        return redirect(url_for('customer.list_customers'))
    
    customer_name = customer.name
    customer.is_active = False
    db.session.commit()
    
    flash(f'Customer {customer_name} has been deleted successfully.', 'success')
    return redirect(url_for('customer.list_customers'))

@customer_bp.route('/api/search')
@login_required
def search_customers_api():
    """API: Search customers"""
    query = request.args.get('q', '')
    customers = Customer.query.filter(
        db.or_(
            Customer.name.ilike(f'%{query}%'),
            Customer.phone.ilike(f'%{query}%')
        ),
        Customer.is_active == True
    ).limit(10).all()
    
    return jsonify([{
        'id': c.id,
        'name': c.name,
        'phone': c.phone,
        'type': c.customer_type,
        'balance': c.balance,
        'credit_limit': c.credit_limit
    } for c in customers])

@customer_bp.route('/record-payment/<int:customer_id>', methods=['POST'])
@login_required
def record_payment(customer_id):
    """Record payment"""
    customer = Customer.query.get_or_404(customer_id)
    amount = float(request.form.get('amount'))
    
    payment = Payment(
        customer_id=customer.id,
        amount=amount,
        payment_method=request.form.get('payment_method'),
        reference_number=request.form.get('reference', ''),
        received_by=current_user.id
    )
    
    customer.balance -= amount
    db.session.add(payment)
    db.session.commit()
    
    flash(f'Payment of ${amount:.2f} recorded! New balance: ${customer.balance:.2f}', 'success')
    return redirect(url_for('customer.list_customers'))