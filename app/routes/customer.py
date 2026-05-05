from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user
from app import db
from app.models.customer import Customer, Payment
from app.models.order import Order
from datetime import datetime
from app.models.order import Order, OrderItem

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
    name = request.form.get('name', '').strip()
    phone = request.form.get('phone', '').strip()
    nic = request.form.get('nic', '').strip()
    
    # Validate required fields
    if not name:
        flash('Customer name is required!', 'danger')
        return redirect(url_for('customer.list_customers'))
    if not phone:
        flash('Phone number is required!', 'danger')
        return redirect(url_for('customer.list_customers'))
    if not nic:
        flash('NIC number is required!', 'danger')
        return redirect(url_for('customer.list_customers'))
    
    # Check if phone already exists
    existing_phone = Customer.query.filter_by(phone=phone).first()
    if existing_phone:
        flash(f'Phone number {phone} already exists! Customer: {existing_phone.name}', 'danger')
        return redirect(url_for('customer.list_customers'))
    
    # Check if NIC already exists
    existing_nic = Customer.query.filter_by(nic=nic).first()
    if existing_nic:
        flash(f'NIC {nic} already exists! Customer: {existing_nic.name}', 'danger')
        return redirect(url_for('customer.list_customers'))
    
    customer = Customer(
        name=name,
        phone=phone,
        email=request.form.get('email', '').strip(),
        address=request.form.get('address', '').strip(),
        nic=nic,
        customer_type=request.form.get('customer_type', 'retail'),
    )
    db.session.add(customer)
    db.session.commit()
    flash(f'Customer {customer.name} added successfully!', 'success')
    return redirect(url_for('customer.list_customers'))

@customer_bp.route('/edit/<int:customer_id>', methods=['POST'])
@login_required
def edit_customer(customer_id):
    """Edit customer details"""
    if current_user.role not in ['owner', 'manager']:
        flash('You do not have permission to edit customers.', 'danger')
        return redirect(url_for('customer.list_customers'))
    
    customer = Customer.query.get_or_404(customer_id)
    
    name = request.form.get('name', '').strip()
    phone = request.form.get('phone', '').strip()
    nic = request.form.get('nic', '').strip()
    
    if not name or not phone or not nic:
        flash('Name, phone and NIC are required!', 'danger')
        return redirect(url_for('customer.list_customers'))
    
    # Check phone uniqueness (exclude current customer)
    dup_phone = Customer.query.filter(Customer.phone == phone, Customer.id != customer_id).first()
    if dup_phone:
        flash(f'Phone {phone} already used by {dup_phone.name}', 'danger')
        return redirect(url_for('customer.list_customers'))
    
    # Check NIC uniqueness
    dup_nic = Customer.query.filter(Customer.nic == nic, Customer.id != customer_id).first()
    if dup_nic:
        flash(f'NIC {nic} already used by {dup_nic.name}', 'danger')
        return redirect(url_for('customer.list_customers'))
    
    customer.name = name
    customer.phone = phone
    customer.nic = nic
    customer.email = request.form.get('email', '').strip()
    customer.address = request.form.get('address', '').strip()
    customer.customer_type = request.form.get('customer_type', 'retail')
    
    db.session.commit()
    flash(f'Customer {customer.name} updated!', 'success')
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
            Customer.phone.ilike(f'%{query}%'),
            Customer.nic.ilike(f'%{query}%')
        ),
        Customer.is_active == True
    ).limit(10).all()
    
    return jsonify([{
        'id': c.id,
        'name': c.name,
        'phone': c.phone,
        'nic': c.nic,
        'type': c.customer_type,
        'balance': c.balance,
    } for c in customers])

@customer_bp.route('/record-payment/<int:customer_id>', methods=['POST'])
@login_required
def record_payment(customer_id):
    """Record payment and settle pending orders (FIFO)"""
    customer = Customer.query.get_or_404(customer_id)
    amount = float(request.form.get('amount', 0))
    payment_method = request.form.get('payment_method', 'cash')
    reference = request.form.get('reference', '')
    
    # Validate amount
    if amount <= 0:
        flash('Payment amount must be greater than $0.00', 'danger')
        return redirect(url_for('customer.list_customers'))
    
    if amount > customer.balance:
        flash(f'Payment amount cannot exceed the outstanding balance of ${customer.balance:.2f}', 'danger')
        return redirect(url_for('customer.list_customers'))
    
    # Record the payment
    payment = Payment(
        customer_id=customer.id,
        amount=amount,
        payment_method=payment_method,
        reference_number=reference,
        received_by=current_user.id
    )
    
    customer.balance -= amount
    customer.total_paid += amount
    db.session.add(payment)
    
    # Settle pending orders (FIFO - oldest first)
    remaining = amount
    pending_orders = Order.query.filter_by(
        customer_id=customer.id,
        payment_status='pending'
    ).order_by(Order.created_at.asc()).all()
    
    for order in pending_orders:
        if remaining <= 0:
            break
        if remaining >= order.total:
            remaining -= order.total
            order.payment_status = 'completed'
        else:
            remaining = 0
    
    # Create a payment receipt bill (CPY prefix)
    date_str = datetime.now().strftime('%Y%m%d')
    count = Order.query.filter(Order.order_number.like(f'CPY-{date_str}%')).count()
    receipt_number = f'CPY-{date_str}-{count+1:04d}'
    
    receipt = Order(
        order_number=receipt_number,
        order_type='payment',
        sale_type='payment',
        user_id=current_user.id,
        customer_id=customer.id,
        customer_name=customer.name,
        customer_phone=customer.phone,
        customer_address=customer.address,
        subtotal=amount,
        total=amount,
        discount_amount=0,
        delivery_charge=0,
        payment_method=payment_method,
        payment_status='completed',
        status='completed',
        notes=reference if reference else ''
    )
    
    # Add a single item line for the payment
    receipt_item = OrderItem(
        product_name='Credit Payment Received',
        product_price=amount,
        quantity=1,
        line_total=amount,
        discount_amount=0
    )
    receipt.items.append(receipt_item)
    db.session.add(receipt)
    db.session.commit()
    
    flash(f'Payment of ${amount:.2f} recorded! New balance: ${customer.balance:.2f}', 'success')
    return redirect(url_for('pos.bills'))