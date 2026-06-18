from datetime import datetime, timedelta
from functools import wraps

from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import db
from app.models.customer import Customer, Payment
from app.models.order import Order
from app.models.product import Product, StockMovement
from app.models.supplier import Supplier, SupplierPayment
from app.models.supply import LedgerOffset, SupplyBill, SupplyBillItem, SupplyReturn

supply_bp = Blueprint('supply', __name__)

WRITE_ROLES = {'owner', 'manager'}


def supply_write_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if current_user.role not in WRITE_ROLES:
            if request.path.startswith('/supply/api/'):
                return jsonify({'error': 'Permission denied'}), 403
            flash('Permission denied. Supply changes require owner or manager access.', 'danger')
            return redirect(request.referrer or url_for('supply.dashboard'))
        return view(*args, **kwargs)
    return wrapped


def parse_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def parse_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def serialize_supplier(supplier):
    return {
        'id': supplier.id,
        'name': supplier.name,
        'phone': supplier.phone,
        'email': supplier.email or '',
        'address': supplier.address or '',
        'nic': supplier.nic,
        'balance': supplier.balance or 0,
        'total_purchases': supplier.total_purchases or 0,
        'total_paid': supplier.total_paid or 0,
    }


def serialize_customer(customer, match_type='linked'):
    return {
        'id': customer.id,
        'name': customer.name,
        'phone': customer.phone,
        'nic': customer.nic,
        'email': customer.email or '',
        'balance': customer.balance or 0,
        'total_purchases': customer.total_purchases or 0,
        'total_paid': customer.total_paid or 0,
        'match_type': match_type,
    }


def find_customer_matches(supplier):
    seen = set()
    matches = []

    def add_customers(customers, match_type):
        for customer in customers:
            if customer.id not in seen:
                seen.add(customer.id)
                matches.append(serialize_customer(customer, match_type))

    if supplier.nic:
        add_customers(Customer.query.filter(
            Customer.is_active == True,
            Customer.nic == supplier.nic
        ).limit(5).all(), 'nic')

    if supplier.phone:
        add_customers(Customer.query.filter(
            Customer.is_active == True,
            Customer.phone == supplier.phone
        ).limit(5).all(), 'phone')

    if supplier.name:
        add_customers(Customer.query.filter(
            Customer.is_active == True,
            Customer.name.ilike(f'%{supplier.name}%')
        ).limit(5).all(), 'name')

    return matches


def flash_customer_match_hint(supplier):
    matches = find_customer_matches(supplier)
    if not matches:
        return
    strong = [match for match in matches if match['match_type'] in {'nic', 'phone'}]
    if strong:
        flash(f'Possible same-person customer found for {supplier.name}. Open supplier details to confirm and link.', 'warning')
    else:
        flash(f'Name-similar customer found for {supplier.name}. Confirm identity before linking.', 'warning')


def settle_customer_orders(customer, amount):
    remaining = amount
    pending_orders = Order.query.filter_by(
        customer_id=customer.id,
        payment_status='pending'
    ).order_by(Order.created_at.asc()).all()
    for order in pending_orders:
        if remaining <= 0:
            break
        if remaining >= (order.total or 0):
            remaining -= order.total or 0
            order.payment_status = 'completed'
        else:
            remaining = 0


def settle_supplier_bills(supplier, amount):
    remaining = amount
    open_bills = SupplyBill.query.filter(
        SupplyBill.supplier_id == supplier.id,
        SupplyBill.is_cancelled == False,
        SupplyBill.balance_amount > 0
    ).order_by(SupplyBill.created_at.asc()).all()
    for open_bill in open_bills:
        if remaining <= 0:
            break
        applied = min(remaining, open_bill.balance_amount or 0)
        open_bill.paid_amount = (open_bill.paid_amount or 0) + applied
        open_bill.balance_amount = max((open_bill.balance_amount or 0) - applied, 0)
        if open_bill.balance_amount == 0:
            open_bill.payment_status = 'completed'
        elif open_bill.paid_amount > 0:
            open_bill.payment_status = 'partial'
        remaining -= applied


def apply_supplier_credit_to_open_bills(supplier, amount, preferred_bill=None):
    remaining = amount
    bills = []
    if preferred_bill and (preferred_bill.balance_amount or 0) > 0:
        bills.append(preferred_bill)

    other_bills = SupplyBill.query.filter(
        SupplyBill.supplier_id == supplier.id,
        SupplyBill.is_cancelled == False,
        SupplyBill.balance_amount > 0
    ).order_by(SupplyBill.created_at.asc()).all()
    for bill in other_bills:
        if not preferred_bill or bill.id != preferred_bill.id:
            bills.append(bill)

    for bill in bills:
        if remaining <= 0:
            break
        applied = min(remaining, bill.balance_amount or 0)
        bill.balance_amount = max((bill.balance_amount or 0) - applied, 0)
        if bill.balance_amount == 0:
            bill.payment_status = 'completed'
        elif (bill.paid_amount or 0) > 0:
            bill.payment_status = 'partial'
        else:
            bill.payment_status = 'pending'
        remaining -= applied


@supply_bp.route('/')
@login_required
def index():
    return redirect(url_for('supply.dashboard'))


@supply_bp.route('/dashboard')
@login_required
def dashboard():
    today = datetime.now().date()
    today_bills = SupplyBill.query.filter(
        db.func.date(SupplyBill.created_at) == today,
        SupplyBill.is_cancelled == False
    ).all()
    recent_bills = SupplyBill.query.filter_by(is_cancelled=False).order_by(SupplyBill.created_at.desc()).limit(8).all()
    top_suppliers = Supplier.query.filter_by(is_active=True).order_by(Supplier.balance.desc()).limit(6).all()
    low_stock = Product.query.filter(
        Product.is_active == True,
        Product.stock_quantity <= Product.min_stock_level
    ).order_by(Product.stock_quantity.asc()).limit(8).all()

    stats = {
        'today_total': sum(b.total or 0 for b in today_bills),
        'today_count': len(today_bills),
        'total_payable': db.session.query(db.func.sum(Supplier.balance)).filter(Supplier.is_active == True).scalar() or 0,
        'partial_count': SupplyBill.query.filter(
            SupplyBill.payment_status == 'partial',
            SupplyBill.is_cancelled == False
        ).count(),
        'low_stock_count': Product.query.filter(
            Product.is_active == True,
            Product.stock_quantity <= Product.min_stock_level
        ).count(),
    }
    return render_template(
        'supply/dashboard.html',
        stats=stats,
        recent_bills=recent_bills,
        top_suppliers=top_suppliers,
        low_stock=low_stock,
    )


def supplier_last_payment_date(supplier):
    payment = SupplierPayment.query.filter_by(supplier_id=supplier.id).order_by(SupplierPayment.created_at.desc()).first()
    return payment.created_at if payment else None


def overdue_supplier_query():
    five_days_ago = datetime.now() - timedelta(days=5)
    return Supplier.query.filter(
        Supplier.is_active == True,
        Supplier.balance > 0,
        ~Supplier.payments.any(SupplierPayment.created_at >= five_days_ago),
        Supplier.supply_bills.any(db.and_(
            SupplyBill.is_cancelled == False,
            SupplyBill.balance_amount > 0,
            SupplyBill.created_at < five_days_ago,
        )),
    )


@supply_bp.route('/api/dashboard/stats')
@login_required
def api_dashboard_stats():
    return jsonify({
        'overdue_suppliers': overdue_supplier_query().count(),
        'total_payable': db.session.query(db.func.sum(Supplier.balance)).filter(Supplier.is_active == True).scalar() or 0,
    })


@supply_bp.route('/api/dashboard/overdue-suppliers')
@login_required
def api_overdue_suppliers():
    suppliers = overdue_supplier_query().order_by(Supplier.balance.desc()).all()
    data = []
    for supplier in suppliers:
        oldest_bill = SupplyBill.query.filter(
            SupplyBill.supplier_id == supplier.id,
            SupplyBill.is_cancelled == False,
            SupplyBill.balance_amount > 0,
        ).order_by(SupplyBill.created_at.asc()).first()
        last_payment = supplier_last_payment_date(supplier)
        data.append({
            'id': supplier.id,
            'name': supplier.name,
            'phone': supplier.phone,
            'balance': supplier.balance or 0,
            'last_payment': last_payment.strftime('%Y-%m-%d') if last_payment else 'Never',
            'oldest_note': oldest_bill.bill_number if oldest_bill else '',
            'oldest_note_date': oldest_bill.created_at.strftime('%Y-%m-%d') if oldest_bill else '',
        })
    return jsonify({'suppliers': data})


@supply_bp.route('/receive')
@login_required
def receive():
    return render_template('supply/receive.html', can_write=current_user.role in WRITE_ROLES)


@supply_bp.route('/terminal')
@login_required
def terminal():
    return redirect(url_for('supply.receive'))


@supply_bp.route('/bills')
@login_required
def bills():
    return render_template('supply/bills.html')


@supply_bp.route('/bills/<bill_number>')
@login_required
def bill_detail(bill_number):
    bill = SupplyBill.query.filter_by(bill_number=bill_number).first_or_404()
    return render_template('supply/bill_detail.html', bill=bill, can_write=current_user.role in WRITE_ROLES)


@supply_bp.route('/suppliers')
@login_required
def suppliers():
    supplier_list = Supplier.query.filter_by(is_active=True).order_by(Supplier.name).all()
    return render_template('supply/suppliers.html', suppliers=supplier_list, can_write=current_user.role in WRITE_ROLES)


@supply_bp.route('/payments')
@login_required
def payments():
    return redirect(url_for('supply.suppliers'))


@supply_bp.route('/inventory')
@login_required
def inventory():
    return render_template('supply/inventory.html', can_write=current_user.role in WRITE_ROLES)


@supply_bp.route('/returns')
@login_required
def returns():
    return_list = SupplyReturn.query.order_by(SupplyReturn.created_at.desc()).limit(100).all()
    bills_with_items = SupplyBill.query.filter_by(is_cancelled=False).order_by(SupplyBill.created_at.desc()).limit(50).all()
    returned_by_item = {}
    for bill in bills_with_items:
        for item in bill.items:
            returned_by_item[(bill.id, item.product_id)] = db.session.query(db.func.sum(SupplyReturn.quantity)).filter_by(
                supply_bill_id=bill.id,
                product_id=item.product_id,
            ).scalar() or 0
    return render_template(
        'supply/returns.html',
        returns=return_list,
        bills=bills_with_items,
        returned_by_item=returned_by_item,
        can_write=current_user.role in WRITE_ROLES,
    )


@supply_bp.route('/suppliers/add', methods=['POST'])
@login_required
@supply_write_required
def add_supplier():
    name = request.form.get('name', '').strip()
    phone = request.form.get('phone', '').strip()
    nic = request.form.get('nic', '').strip()

    if not name or not phone or not nic:
        flash('Name, phone and NIC are required.', 'danger')
        return redirect(url_for('supply.suppliers'))
    if Supplier.query.filter_by(phone=phone).first():
        flash(f'Phone {phone} already exists.', 'danger')
        return redirect(url_for('supply.suppliers'))
    if Supplier.query.filter_by(nic=nic).first():
        flash(f'NIC {nic} already exists.', 'danger')
        return redirect(url_for('supply.suppliers'))

    supplier = Supplier(
        name=name,
        phone=phone,
        email=request.form.get('email', '').strip(),
        address=request.form.get('address', '').strip(),
        nic=nic,
        notes=request.form.get('notes', '').strip(),
    )
    db.session.add(supplier)
    db.session.commit()
    flash(f'Supplier {supplier.name} added.', 'success')
    flash_customer_match_hint(supplier)
    return redirect(url_for('supply.suppliers'))


@supply_bp.route('/suppliers/edit/<int:supplier_id>', methods=['POST'])
@login_required
@supply_write_required
def edit_supplier(supplier_id):
    supplier = Supplier.query.get_or_404(supplier_id)
    name = request.form.get('name', '').strip()
    phone = request.form.get('phone', '').strip()
    nic = request.form.get('nic', '').strip()

    if not name or not phone or not nic:
        flash('Name, phone and NIC are required.', 'danger')
        return redirect(url_for('supply.suppliers'))
    dup_phone = Supplier.query.filter(Supplier.phone == phone, Supplier.id != supplier_id).first()
    if dup_phone:
        flash(f'Phone already used by {dup_phone.name}.', 'danger')
        return redirect(url_for('supply.suppliers'))
    dup_nic = Supplier.query.filter(Supplier.nic == nic, Supplier.id != supplier_id).first()
    if dup_nic:
        flash(f'NIC already used by {dup_nic.name}.', 'danger')
        return redirect(url_for('supply.suppliers'))

    supplier.name = name
    supplier.phone = phone
    supplier.nic = nic
    supplier.email = request.form.get('email', '').strip()
    supplier.address = request.form.get('address', '').strip()
    supplier.notes = request.form.get('notes', '').strip()
    db.session.commit()
    flash(f'Supplier {supplier.name} updated.', 'success')
    flash_customer_match_hint(supplier)
    return redirect(url_for('supply.suppliers'))


@supply_bp.route('/suppliers/delete/<int:supplier_id>', methods=['POST'])
@login_required
@supply_write_required
def delete_supplier(supplier_id):
    supplier = Supplier.query.get_or_404(supplier_id)
    if (supplier.balance or 0) > 0 and current_user.role != 'owner':
        flash(f'Cannot delete. Outstanding payable is Rs.{supplier.balance:.2f}.', 'danger')
        return redirect(url_for('supply.suppliers'))

    supplier_name = supplier.name
    supplier.phone = f'{supplier.phone}_deleted_{supplier.id}'
    supplier.nic = f'{supplier.nic}_deleted_{supplier.id}'
    supplier.is_active = False
    db.session.commit()
    flash(f'Supplier {supplier_name} deleted.', 'success')
    return redirect(url_for('supply.suppliers'))


@supply_bp.route('/suppliers/record-payment/<int:supplier_id>', methods=['POST'])
@login_required
@supply_write_required
def record_payment_form(supplier_id):
    response, status = create_supplier_payment(supplier_id)
    payload = response.get_json(silent=True) or {}
    if status >= 400:
        flash(payload.get('error', 'Payment failed.'), 'danger')
    else:
        flash(payload.get('message', 'Payment recorded.'), 'success')
    return redirect(request.referrer or url_for('supply.suppliers'))


@supply_bp.route('/api/products/search')
@login_required
def api_search_products():
    query = request.args.get('q', '').strip()
    product_query = Product.query.filter(Product.is_active == True)
    if query:
        for keyword in [part for part in query.split() if part]:
            like = f'%{keyword}%'
            product_query = product_query.filter(db.or_(
                Product.name.ilike(like),
                Product.barcode.ilike(like),
                Product.sku.ilike(like),
                Product.category.ilike(like),
            ))
    products = product_query.order_by(Product.category, Product.name).limit(50).all()
    return jsonify([{
        'id': p.id,
        'barcode': p.barcode or '',
        'name': p.name,
        'category': p.category or 'Uncategorized',
        'sku': p.sku or '',
        'cost_price': p.cost_price or 0,
        'retail_price': p.retail_price or 0,
        'wholesale_price': p.wholesale_price or 0,
        'stock_quantity': p.stock_quantity or 0,
        'min_stock_level': p.min_stock_level or 0,
    } for p in products])


@supply_bp.route('/api/suppliers/search')
@login_required
def api_search_suppliers():
    query = request.args.get('q', '').strip()
    supplier_query = Supplier.query.filter(Supplier.is_active == True)
    if query:
        supplier_query = supplier_query.filter(db.or_(
            Supplier.name.ilike(f'%{query}%'),
            Supplier.phone.ilike(f'%{query}%'),
            Supplier.nic.ilike(f'%{query}%'),
        ))
    suppliers = supplier_query.order_by(Supplier.name).limit(10).all()
    return jsonify([serialize_supplier(s) for s in suppliers])


@supply_bp.route('/api/suppliers/<int:supplier_id>/details')
@login_required
def api_supplier_details(supplier_id):
    supplier = Supplier.query.get_or_404(supplier_id)
    data = serialize_supplier(supplier)
    data['linked_customer'] = serialize_customer(supplier.linked_customer) if supplier.linked_customer else None
    data['customer_matches'] = find_customer_matches(supplier)
    data['net_position'] = {
        'customer_credit_due': supplier.linked_customer.balance if supplier.linked_customer else 0,
        'supplier_payable': supplier.balance or 0,
        'offset_available': min(
            supplier.linked_customer.balance if supplier.linked_customer else 0,
            supplier.balance or 0
        ),
    }
    data['payment_history'] = [{
        'date': p.created_at.strftime('%Y-%m-%d %H:%M'),
        'amount': p.amount,
        'method': p.payment_method,
        'reference': p.reference_number or '',
        'bill_number': p.supply_bill.bill_number if p.supply_bill else '',
    } for p in sorted(supplier.payments, key=lambda payment: payment.created_at or datetime.min, reverse=True)]
    data['recent_bills'] = [
        bill.to_dict() for bill in SupplyBill.query.filter_by(
            supplier_id=supplier.id,
            is_cancelled=False
        ).order_by(SupplyBill.created_at.desc()).limit(60).all()
    ]
    data['recent_returns'] = [
        ret.to_dict() for ret in SupplyReturn.query.filter_by(
            supplier_id=supplier.id
        ).order_by(SupplyReturn.created_at.desc()).limit(60).all()
    ]
    data['offset_history'] = [
        offset.to_dict() for offset in LedgerOffset.query.filter_by(
            supplier_id=supplier.id
        ).order_by(LedgerOffset.created_at.desc()).limit(10).all()
    ]
    return jsonify(data)


@supply_bp.route('/api/suppliers/<int:supplier_id>/link-customer', methods=['POST'])
@login_required
@supply_write_required
def api_link_customer(supplier_id):
    data = request.get_json(silent=True) or {}
    supplier = Supplier.query.filter_by(id=supplier_id, is_active=True).first()
    if not supplier:
        return jsonify({'error': 'Supplier not found'}), 404

    customer_id = parse_int(data.get('customer_id'))
    customer = Customer.query.filter_by(id=customer_id, is_active=True).first()
    if not customer:
        return jsonify({'error': 'Customer not found'}), 404

    supplier.linked_customer_id = customer.id
    db.session.commit()
    return jsonify({
        'success': True,
        'supplier': serialize_supplier(supplier),
        'linked_customer': serialize_customer(customer),
    })


@supply_bp.route('/api/suppliers/<int:supplier_id>/offset', methods=['POST'])
@login_required
@supply_write_required
def api_offset_balances(supplier_id):
    data = request.get_json(silent=True) or {}
    supplier = Supplier.query.filter_by(id=supplier_id, is_active=True).first()
    if not supplier:
        return jsonify({'error': 'Supplier not found'}), 404
    if not supplier.linked_customer:
        return jsonify({'error': 'Link a customer before offsetting balances'}), 400

    customer = supplier.linked_customer
    amount = parse_float(data.get('amount'))
    max_offset = min(customer.balance or 0, supplier.balance or 0)
    if amount <= 0:
        return jsonify({'error': 'Offset amount must be greater than 0'}), 400
    if amount > max_offset:
        return jsonify({'error': f'Offset cannot exceed Rs.{max_offset:.2f}'}), 400

    customer_before = customer.balance or 0
    supplier_before = supplier.balance or 0

    offset = LedgerOffset(
        customer_id=customer.id,
        supplier_id=supplier.id,
        user_id=current_user.id,
        amount=amount,
        customer_balance_before=customer_before,
        supplier_balance_before=supplier_before,
        reference=(data.get('reference') or '').strip(),
        notes=(data.get('notes') or '').strip(),
    )
    offset.generate_offset_number()

    customer.balance = max(customer_before - amount, 0)
    customer.total_paid = (customer.total_paid or 0) + amount
    supplier.balance = max(supplier_before - amount, 0)
    supplier.total_paid = (supplier.total_paid or 0) + amount

    offset.customer_balance_after = customer.balance
    offset.supplier_balance_after = supplier.balance

    customer_payment = Payment(
        customer_id=customer.id,
        amount=amount,
        payment_method='offset',
        reference_number=offset.offset_number,
        notes=f'Offset against supplier payable: {supplier.name}',
        received_by=current_user.id,
    )
    supplier_payment = SupplierPayment(
        supplier_id=supplier.id,
        amount=amount,
        payment_method='offset',
        reference_number=offset.offset_number,
        notes=f'Offset against customer credit due: {customer.name}',
        received_by=current_user.id,
    )

    settle_customer_orders(customer, amount)
    settle_supplier_bills(supplier, amount)

    db.session.add(customer_payment)
    db.session.add(supplier_payment)
    db.session.add(offset)
    db.session.flush()
    offset.customer_payment_id = customer_payment.id
    offset.supplier_payment_id = supplier_payment.id
    db.session.commit()

    return jsonify({
        'success': True,
        'offset': offset.to_dict(),
        'supplier': serialize_supplier(supplier),
        'linked_customer': serialize_customer(customer),
    })


@supply_bp.route('/api/bills', methods=['GET'])
@login_required
def api_bills():
    date = request.args.get('date', '').strip()
    status = request.args.get('status', 'all')
    query = request.args.get('q', '').strip().lower()

    bill_query = SupplyBill.query.filter_by(is_cancelled=False)
    if date:
        bill_query = bill_query.filter(db.func.date(SupplyBill.created_at) == date)
    if status != 'all':
        bill_query = bill_query.filter(SupplyBill.payment_status == status)

    bills = bill_query.order_by(SupplyBill.created_at.desc()).limit(250).all()
    if query:
        bills = [
            b for b in bills
            if query in (b.bill_number or '').lower()
            or query in (b.supplier_invoice or '').lower()
            or query in (b.supplier.name if b.supplier else '').lower()
            or any(query in item.product_name.lower() for item in b.items)
        ]

    return jsonify({
        'bills': [bill.to_dict() for bill in bills],
        'total_purchases': sum(b.total or 0 for b in bills),
        'total_balance': sum(b.balance_amount or 0 for b in bills),
    })


@supply_bp.route('/api/bills/<bill_number>')
@login_required
def api_bill_details(bill_number):
    bill = SupplyBill.query.filter(
        SupplyBill.is_cancelled == False,
        db.or_(
            SupplyBill.bill_number == bill_number,
            SupplyBill.supplier_invoice == bill_number,
        )
    ).first_or_404()
    return jsonify(bill.to_dict(include_items=True))


@supply_bp.route('/api/bills', methods=['POST'])
@login_required
@supply_write_required
def api_create_bill():
    data = request.get_json(silent=True) or {}
    supplier = Supplier.query.filter_by(id=data.get('supplier_id'), is_active=True).first()
    if not supplier:
        return jsonify({'error': 'Supplier not found'}), 404

    items_data = data.get('items') or []
    if not items_data:
        return jsonify({'error': 'Add at least one product line'}), 400

    try:
        bill = SupplyBill(
            supplier_id=supplier.id,
            user_id=current_user.id,
            supplier_invoice=(data.get('supplier_invoice') or '').strip(),
            payment_method=data.get('payment_method') or 'credit',
            discount_amount=max(parse_float(data.get('discount_amount')), 0),
            paid_amount=max(parse_float(data.get('paid_amount')), 0),
            notes=(data.get('notes') or '').strip(),
        )
        bill.generate_bill_number()

        bill_date = (data.get('bill_date') or '').strip()
        if bill_date:
            bill.bill_date = datetime.strptime(bill_date, '%Y-%m-%d')

        db.session.add(bill)

        seen_products = set()
        for item_data in items_data:
            product_id = parse_int(item_data.get('product_id') or item_data.get('id'))
            if product_id in seen_products:
                db.session.rollback()
                return jsonify({'error': 'Each product can appear only once per supply bill'}), 400
            product = Product.query.filter_by(id=product_id, is_active=True).first()
            if not product:
                db.session.rollback()
                return jsonify({'error': 'One or more products were not found'}), 400

            quantity = parse_int(item_data.get('quantity'))
            unit_cost = parse_float(item_data.get('unit_cost'))
            if quantity <= 0:
                db.session.rollback()
                return jsonify({'error': f'Quantity must be greater than 0 for {product.name}'}), 400
            if unit_cost < 0:
                db.session.rollback()
                return jsonify({'error': f'Unit cost cannot be negative for {product.name}'}), 400

            previous_stock = product.stock_quantity or 0
            product.stock_quantity = previous_stock + quantity
            product.cost_price = unit_cost

            wholesale_price = item_data.get('wholesale_price')
            if wholesale_price not in (None, ''):
                product.wholesale_price = parse_float(wholesale_price, product.wholesale_price or 0)
            retail_price = item_data.get('retail_price')
            if retail_price not in (None, ''):
                product.retail_price = parse_float(retail_price, product.retail_price or 0)

            line_total = quantity * unit_cost
            bill.items.append(SupplyBillItem(
                product_id=product.id,
                product_name=product.name,
                product_barcode=product.barcode,
                quantity=quantity,
                unit_cost=unit_cost,
                line_total=line_total,
                previous_stock=previous_stock,
                new_stock=product.stock_quantity,
            ))
            db.session.add(StockMovement(
                product_id=product.id,
                user_id=current_user.id,
                movement_type='supply_in',
                quantity=quantity,
                previous_stock=previous_stock,
                new_stock=product.stock_quantity,
                reference=bill.bill_number,
                notes=f'Supplier: {supplier.name}',
            ))
            seen_products.add(product_id)

        bill.recalculate_totals()
        if bill.paid_amount > bill.total:
            db.session.rollback()
            return jsonify({'error': 'Paid amount cannot exceed bill total'}), 400

        supplier.total_purchases = (supplier.total_purchases or 0) + bill.total
        supplier.balance = (supplier.balance or 0) + bill.balance_amount
        db.session.flush()
        if bill.paid_amount > 0:
            supplier.total_paid = (supplier.total_paid or 0) + bill.paid_amount
            db.session.add(SupplierPayment(
                supplier_id=supplier.id,
                supply_bill_id=bill.id,
                amount=bill.paid_amount,
                payment_method=bill.payment_method,
                reference_number=bill.bill_number,
                notes='Paid during supply receiving',
                received_by=current_user.id,
            ))

        db.session.commit()

        return jsonify({'success': True, 'bill': bill.to_dict(include_items=True)})
    except ValueError:
        db.session.rollback()
        return jsonify({'error': 'Invalid bill date'}), 400
    except Exception as exc:
        db.session.rollback()
        return jsonify({'error': str(exc)}), 500


@supply_bp.route('/api/suppliers/<int:supplier_id>/payment', methods=['POST'])
@login_required
@supply_write_required
def api_supplier_payment(supplier_id):
    return create_supplier_payment(supplier_id)


def create_supplier_payment(supplier_id):
    data = request.get_json(silent=True) if request.is_json else request.form
    supplier = Supplier.query.filter_by(id=supplier_id, is_active=True).first()
    if not supplier:
        return jsonify({'error': 'Supplier not found'}), 404

    amount = parse_float(data.get('amount'))
    payment_method = data.get('payment_method') or 'cash'
    reference = (data.get('reference') or '').strip()
    notes = (data.get('notes') or '').strip()
    supply_bill_id = parse_int(data.get('supply_bill_id'), None)

    if amount <= 0:
        return jsonify({'error': 'Payment amount must be greater than 0'}), 400
    if amount > (supplier.balance or 0):
        return jsonify({'error': f'Amount cannot exceed payable of Rs.{supplier.balance:.2f}'}), 400

    bill = None
    if supply_bill_id:
        bill = SupplyBill.query.filter_by(id=supply_bill_id, supplier_id=supplier.id, is_cancelled=False).first()
        if not bill:
            return jsonify({'error': 'Supply bill not found for this supplier'}), 404
        if amount > (bill.balance_amount or 0):
            return jsonify({'error': f'Amount cannot exceed bill balance of Rs.{bill.balance_amount:.2f}'}), 400

    payment = SupplierPayment(
        supplier_id=supplier.id,
        supply_bill_id=bill.id if bill else None,
        amount=amount,
        payment_method=payment_method,
        reference_number=reference or (bill.bill_number if bill else ''),
        notes=notes,
        received_by=current_user.id,
    )
    supplier.balance = max((supplier.balance or 0) - amount, 0)
    supplier.total_paid = (supplier.total_paid or 0) + amount

    if bill:
        bill.paid_amount = (bill.paid_amount or 0) + amount
        bill.balance_amount = max((bill.balance_amount or 0) - amount, 0)
        if bill.balance_amount == 0:
            bill.payment_status = 'completed'
        elif bill.paid_amount > 0:
            bill.payment_status = 'partial'
    else:
        settle_supplier_bills(supplier, amount)

    db.session.add(payment)
    db.session.commit()
    return jsonify({
        'success': True,
        'message': f'Payment of Rs.{amount:.2f} recorded. New payable: Rs.{supplier.balance:.2f}',
        'supplier': serialize_supplier(supplier),
    }), 200


@supply_bp.route('/api/returns', methods=['POST'])
@login_required
@supply_write_required
def api_create_return():
    data = request.get_json(silent=True) or {}
    bill = SupplyBill.query.filter_by(id=data.get('supply_bill_id'), is_cancelled=False).first()
    if not bill:
        return jsonify({'error': 'Supply bill not found'}), 404

    product = Product.query.get(data.get('product_id'))
    if not product:
        return jsonify({'error': 'Product not found'}), 404

    quantity = parse_int(data.get('quantity'))
    if quantity <= 0:
        return jsonify({'error': 'Return quantity must be greater than 0'}), 400

    bill_item = SupplyBillItem.query.filter_by(supply_bill_id=bill.id, product_id=product.id).first()
    if not bill_item:
        return jsonify({'error': 'Product was not received on this supply bill'}), 400

    already_returned = db.session.query(db.func.sum(SupplyReturn.quantity)).filter_by(
        supply_bill_id=bill.id,
        product_id=product.id,
    ).scalar() or 0
    remaining = (bill_item.quantity or 0) - already_returned
    if quantity > remaining:
        return jsonify({'error': f'Cannot return more than remaining received quantity ({remaining})'}), 400
    if quantity > (product.stock_quantity or 0):
        return jsonify({'error': f'Current stock is only {product.stock_quantity}'}), 400

    previous_stock = product.stock_quantity or 0
    product.stock_quantity = previous_stock - quantity
    total = quantity * (bill_item.unit_cost or 0)
    supplier = bill.supplier
    supplier_balance_before = supplier.balance or 0
    payable_adjusted = min(total, supplier_balance_before)
    credit_amount = max(total - payable_adjusted, 0)

    ret = SupplyReturn(
        supply_bill_id=bill.id,
        supplier_id=bill.supplier_id,
        product_id=product.id,
        user_id=current_user.id,
        quantity=quantity,
        unit_cost=bill_item.unit_cost or 0,
        total=total,
        payable_adjusted=payable_adjusted,
        credit_amount=credit_amount,
        previous_stock=previous_stock,
        new_stock=product.stock_quantity,
        reason=(data.get('reason') or '').strip(),
    )
    ret.generate_return_number()

    supplier.total_purchases = max((supplier.total_purchases or 0) - total, 0)
    supplier.balance = max(supplier_balance_before - payable_adjusted, 0)
    apply_supplier_credit_to_open_bills(supplier, payable_adjusted, bill)

    db.session.add(ret)
    db.session.add(StockMovement(
        product_id=product.id,
        user_id=current_user.id,
        movement_type='supply_return',
        quantity=-quantity,
        previous_stock=previous_stock,
        new_stock=product.stock_quantity,
        reference=ret.return_number,
        notes=f'Return to supplier: {supplier.name}',
    ))
    db.session.commit()
    return jsonify({'success': True, 'return': ret.to_dict(), 'bill': bill.to_dict()})
