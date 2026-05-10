from flask import Blueprint, jsonify, request, render_template
from flask_login import login_required, current_user
from app import db
from app.models.product import Product, StockMovement

from app.models.customer import Customer, Payment
from app.models.user import User
from datetime import datetime
from app.models.order import Order, OrderItem, Return, ReturnItem

api_bp = Blueprint('api', __name__)

# ============ PRODUCTS ============
@api_bp.route('/product/barcode/<barcode>')
@login_required
def get_product(barcode):
    product = Product.query.filter_by(barcode=barcode.strip(), is_active=True).first()
    if product:
        return jsonify(product.to_dict())
    return jsonify({'error': 'Not found'}), 404

@api_bp.route('/products/search')
@login_required
def search_products():
    query = request.args.get('q', '').strip()
    customer_type = request.args.get('customer_type', 'retail')
    
    if query:
        products = Product.query.filter(
            Product.is_active == True,
            db.or_(
                Product.name.ilike(f'%{query}%'),
                Product.barcode.ilike(f'%{query}%'),
                Product.sku.ilike(f'%{query}%'),
                Product.category.ilike(f'%{query}%')
            )
        ).limit(50).all()
    else:
        products = Product.query.filter_by(is_active=True).limit(50).all()
    
    result = []
    for p in products:
        data = p.to_dict()
        data['price'] = p.wholesale_price if customer_type == 'wholesale' else 0
        result.append(data)
    
    return jsonify(result)

@api_bp.route('/products/all')
@login_required
def get_all_products():
       
    products = Product.query.order_by(Product.category, Product.name).all()
    return jsonify([{
        'id': p.id,
        'barcode': p.barcode,
        'name': p.name,
        'category': p.category or 'Uncategorized',
        'sku': p.sku or '',
        'cost_price': p.cost_price,
        'wholesale_price': p.wholesale_price,
        'stock_quantity': p.stock_quantity,
        'min_stock_level': p.min_stock_level,
        'is_active': p.is_active
    } for p in products])

@api_bp.route('/products/categories')
@login_required
def get_categories():
    """Get all product categories"""
    categories = db.session.query(Product.category).filter(
        Product.category.isnot(None),
        Product.is_active == True
    ).distinct().all()
    return jsonify([cat[0] for cat in categories if cat[0]])

@api_bp.route('/products/add', methods=['POST'])
@login_required
def add_product():
    if current_user.role not in ['owner', 'manager']:
        return jsonify({'error': 'Permission denied'}), 403
    
    data = request.json
    
    if Product.query.filter_by(barcode=data.get('barcode')).first():
        return jsonify({'error': 'Barcode exists'}), 400
    
    product = Product(
        barcode=data.get('barcode', ''),
        name=data['name'],
        description=data.get('description', ''),
        category=data.get('category', ''),
        sku=data.get('sku', ''),
        cost_price=float(data.get('cost_price', 0)),
        wholesale_price=float(data.get('wholesale_price', 0)),
        stock_quantity=int(data.get('stock_quantity', 0)),
        min_stock_level=int(data.get('min_stock_level', 5)),
        added_by=current_user.id
    )
    
    db.session.add(product)
    
    if product.stock_quantity > 0:
        movement = StockMovement(
            product=product, user_id=current_user.id,
            movement_type='stock_in', quantity=product.stock_quantity,
            previous_stock=0, new_stock=product.stock_quantity,
            reference='Initial stock'
        )
        db.session.add(movement)
    
    db.session.commit()
    return jsonify({'success': True, 'product': product.to_dict()})

@api_bp.route('/products/<int:product_id>/update', methods=['POST'])
@login_required
def update_product(product_id):
    if current_user.role not in ['owner', 'manager']:
        return jsonify({'error': 'Permission denied'}), 403
    
    product = Product.query.get_or_404(product_id)
    data = request.json
    
    product.name = data.get('name', product.name)
    product.barcode = data.get('barcode', product.barcode)
    product.category = data.get('category', product.category)
    product.sku = data.get('sku', product.sku)
    product.cost_price = float(data.get('cost_price', product.cost_price))
    product.wholesale_price = float(data.get('wholesale_price', product.wholesale_price))
    product.min_stock_level = int(data.get('min_stock_level', product.min_stock_level))
    
    db.session.commit()
    return jsonify({'success': True})

@api_bp.route('/products/<int:product_id>/stock', methods=['POST'])
@login_required
def update_stock(product_id):
    if current_user.role not in ['owner', 'manager']:
        return jsonify({'error': 'Permission denied'}), 403
    
    product = Product.query.get_or_404(product_id)
    data = request.json
    change_type = data.get('type', 'adjustment')
    quantity = int(data.get('quantity', 0))
    previous_stock = product.stock_quantity
    
    if change_type == 'stock_in':
        product.stock_quantity += quantity
    elif change_type == 'stock_out':
        if quantity > product.stock_quantity:
            return jsonify({'error': 'Insufficient stock'}), 400
        product.stock_quantity -= quantity
    elif change_type == 'set':
        product.stock_quantity = quantity
    
    movement = StockMovement(
        product_id=product.id, user_id=current_user.id,
        movement_type=change_type, quantity=quantity,
        previous_stock=previous_stock, new_stock=product.stock_quantity,
        reference=data.get('reference', ''), notes=data.get('notes', '')
    )
    db.session.add(movement)
    db.session.commit()
    
    return jsonify({'success': True, 'new_stock': product.stock_quantity})

@api_bp.route('/products/<int:product_id>/toggle-status', methods=['POST'])
@login_required
def toggle_product_status(product_id):
    if current_user.role not in ['owner', 'manager']:
        return jsonify({'error': 'Permission denied'}), 403
    
    product = Product.query.get_or_404(product_id)
    product.is_active = not product.is_active
    db.session.commit()
    return jsonify({'success': True, 'is_active': product.is_active})

# ============ ORDERS ============

@api_bp.route('/orders', methods=['POST'])
@login_required
def create_order():
    data = request.json
    
    try:
        customer_type = 'retail'
        order_type = 'retail'
        
        if data.get('customer_id'):
            customer = Customer.query.get(data['customer_id'])
            if customer and customer.customer_type == 'wholesale':
                customer_type = 'wholesale'
                order_type = 'wholesale'
        
        order = Order(
            user_id=current_user.id,
            order_type=order_type,
            payment_method=data.get('payment_method', 'cash'),
            customer_name=data.get('customer_name', ''),
            customer_phone=data.get('customer_phone', ''),
            customer_address=data.get('customer_address', ''),
            sale_type=data.get('sale_type', 'retail')
        )
        order.generate_order_number()
        
        if data.get('customer_id'):
            order.customer_id = data['customer_id']
        
        discount_amount = float(data.get('discount_amount', 0))
        
        for item_data in data.get('items', []):
            # Check for balance payment FIRST before product lookup
            if item_data.get('id') == 'balance_pay':
                price = float(item_data.get('price', 0))
                order_item = OrderItem(
                    product_id=0,
                    product_name='Balance Payment',
                    product_barcode='',
                    product_price=price,
                    quantity=1,
                    line_total=price,
                    discount_amount=0
                )
                order.items.append(order_item)
                continue
            
            product = Product.query.get(item_data['id'])
            if not product:
                continue
            
            qty = int(item_data.get('quantity', 1))
            if product.stock_quantity < qty:
                return jsonify({'error': f'Not enough stock for {product.name}'}), 400
            
            price = float(item_data.get('price', 0))
            if price == 0 and customer_type == 'wholesale':
                price = product.wholesale_price
            
            order_item = OrderItem(
                product_id=product.id,
                product_name=product.name,
                product_barcode=product.barcode,
                product_price=price,
                quantity=qty,
                line_total=price * qty,
                discount_amount=0
            )
            
            order.items.append(order_item)
            product.stock_quantity -= qty
            
            movement = StockMovement(
                product_id=product.id, user_id=current_user.id,
                movement_type='sale', quantity=-qty,
                previous_stock=product.stock_quantity + qty,
                new_stock=product.stock_quantity,
                reference=order.order_number
            )
            db.session.add(movement)
        
        order.subtotal = sum(item.product_price * item.quantity for item in order.items)
        order.discount_amount = discount_amount
        order.tax_amount = 0
        order.total = order.subtotal - order.discount_amount
        
        if data.get('payment_method') == 'cash':
            order.cash_received = float(data.get('cash_received', 0))
            order.change_given = order.cash_received - order.total
            order.payment_status = 'completed'
        elif data.get('payment_method') == 'card':
            order.payment_status = 'completed'
        elif data.get('payment_method') == 'credit' and order.customer_id:
            customer = Customer.query.get(order.customer_id)
            if customer:
                # Get balance payment from frontend
                balance_payment = float(data.get('balance_payment', 0))
                
                # Remove Balance Payment item from items for subtotal calculation
                real_items = [item for item in order.items if item.product_name != 'Balance Payment']
                order.subtotal = sum(item.product_price * item.quantity for item in real_items)
                order.total = order.subtotal - order.discount_amount
                order.credit_paid = balance_payment
                
                # Store balances
                order.previous_balance = customer.balance
                
                # Add purchase to balance
                customer.balance += order.total
                customer.total_purchases += order.total
                
                # Subtract credit payment if any
                if balance_payment > 0:
                    customer.balance -= balance_payment
                    customer.total_paid += balance_payment
                    payment = Payment(
                        customer_id=customer.id,
                        amount=balance_payment,
                        payment_method='cash',
                        received_by=current_user.id
                    )
                    db.session.add(payment)
                
                order.new_balance = customer.balance
                order.payment_status = 'pending'
        
        db.session.add(order)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'order': {
                'order_number': order.order_number,
                'previous_balance': order.previous_balance or 0,
                'new_balance': order.new_balance or 0,                
                'total': order.total,
                'subtotal': order.subtotal,
                'discount': order.discount_amount,
                'credit_paid': order.credit_paid or 0,
                'change': order.change_given,
                'cash_received': order.cash_received,
                'payment_method': order.payment_method,
                'payment_status': order.payment_status,
                'sale_type': order.sale_type,
                'created_at': order.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                'items': [{
                    'id': item.id,
                    'product_id': item.product_id,
                    'name': item.product_name,
                    'quantity': item.quantity,
                    'price': item.product_price,
                    'total': item.line_total
                } for item in order.items]
            }
        })
                
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500
    
@api_bp.route('/orders/today')
@login_required
def today_orders():
    today = datetime.now().date()
    orders = Order.query.filter(
        db.func.date(Order.created_at) == today
    ).order_by(Order.created_at.desc()).all()
    
    return jsonify({
        'orders': [{
            'order_number': o.order_number,
            'type': o.order_type,
            'total': o.total,
            'payment_method': o.payment_method,
            'status': o.payment_status,
            'time': o.created_at.strftime('%H:%M:%S'),
            'cashier': o.cashier_rel.username if o.cashier_rel else 'N/A',
            'customer': o.customer_rel.name if o.customer_rel else 'Walk-in',
            'items_count': len(o.items)
        } for o in orders]
    })

@api_bp.route('/orders/all')
@login_required
def get_all_orders():
    """Get all orders for bill history page"""
    
    date = request.args.get('date', '')
    sale_type = request.args.get('type', 'all')
    payment = request.args.get('payment', 'all')
    
    query = Order.query
    
    if date:
        # Use the date string directly to match the created_at date
        query = query.filter(db.func.date(Order.created_at) == date)
    
    if sale_type != 'all':
        query = query.filter(Order.order_type == sale_type)
    if payment != 'all':
        query = query.filter(Order.payment_method == payment)
    
    orders = query.order_by(Order.created_at.desc()).limit(100).all()
    
    return jsonify({
        'orders': [{
            'order_number': o.order_number,
            'created_at': o.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'customer_name': o.customer_name or 'Walk-in',
            'customer_phone': o.customer_phone or '',
            'sale_type': o.order_type or 'retail',
            'item_count': len(o.items),
            'total': o.total,
            'payment_method': o.payment_method,
            'payment_status': o.payment_status
        } for o in orders],
        'total_sales': sum(o.total for o in orders)
    })

@api_bp.route('/orders/<order_number>/details')
@login_required
def order_details(order_number):
    """Get full order details"""
    order = Order.query.filter_by(order_number=order_number).first()
    if not order:
        return jsonify({'error': 'Not found'}), 404
    
    return jsonify({
        'order_number': order.order_number,
        'created_at': order.created_at.strftime('%Y-%m-%d %H:%M:%S'),
        'sale_type': order.order_type or 'retail',
        'payment_method': order.payment_method,
        'payment_status': order.payment_status,
        'customer_name': order.customer_name or 'Walk-in',
        'customer_phone': order.customer_phone or '',
        'subtotal': order.subtotal,
        'discount': order.discount_amount,
        'credit_paid': order.credit_paid or 0,
        'previous_balance': order.previous_balance or 0,
        'new_balance': order.new_balance or 0,
        'total': order.total,
        'items': [{
            'id': item.id,
            'product_id': item.product_id,
            'name': item.product_name,
            'quantity': item.quantity,
            'price': item.product_price,
            'total': item.line_total
        } for item in order.items]
    })

@api_bp.route('/orders/<order_number>/bill')
@login_required
def get_bill(order_number):
    """Generate bill/receipt"""
    order = Order.query.filter_by(order_number=order_number).first()
    if not order:
        return jsonify({'error': 'Order not found'}), 404
    
    customer_name = order.customer_name or 'Walk-in Customer'
    
    return render_template('pos/bill.html', order=order, customer_name=customer_name)

# ============ CUSTOMERS ============
@api_bp.route('/customers/search')
@login_required
def search_customers():
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
        'address': c.address,
        'type': c.customer_type,
        'balance': c.balance,
    } for c in customers])

@api_bp.route('/customers/add', methods=['POST'])
@login_required
def add_customer():
    data = request.json
    
    # Validate required fields
    name = (data.get('name') or '').strip()
    phone = (data.get('phone') or '').strip()
    nic = (data.get('nic') or '').strip()
    
    errors = []
    if not name:
        errors.append('Name is required')
    if not phone:
        errors.append('Phone is required')
    if not nic:
        errors.append('NIC is required')
    
    if errors:
        return jsonify({'success': False, 'error': ', '.join(errors)}), 400
    
    # Check for duplicate phone
    existing_phone = Customer.query.filter_by(phone=phone).first()
    if existing_phone:
        return jsonify({'success': False, 'error': f'Phone number {phone} already exists! Customer: {existing_phone.name}'}), 400
    
    # Check for duplicate NIC
    existing_nic = Customer.query.filter_by(nic=nic).first()
    if existing_nic:
        return jsonify({'success': False, 'error': f'NIC {nic} already exists! Customer: {existing_nic.name}'}), 400
    
    try:
        customer = Customer(
            name=name,
            phone=phone,
            email=(data.get('email') or '').strip(),
            address=(data.get('address') or '').strip(),
            nic=nic,
            customer_type=data.get('customer_type', 'wholesale')
        )
        db.session.add(customer)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'customer': {
                'id': customer.id,
                'name': customer.name,
                'phone': customer.phone,
                'nic': customer.nic,
                'address': customer.address,
                'balance': customer.balance,
                'type': customer.customer_type
            }
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@api_bp.route('/customers/<int:customer_id>/details')
@login_required
def customer_details(customer_id):
    """Get customer full details with payment history"""
    customer = Customer.query.get_or_404(customer_id)
    
    orders = Order.query.filter_by(customer_id=customer_id)\
        .order_by(Order.created_at.desc()).limit(20).all()
    
    return jsonify({
        'id': customer.id,
        'name': customer.name,
        'phone': customer.phone,
        'email': customer.email,
        'address': customer.address,
        'nic': customer.nic,
        'customer_type': customer.customer_type,
        'balance': customer.balance,
        'total_purchases': customer.total_purchases,
        'total_paid': customer.total_paid,
        'payment_history': customer.get_payment_history(),
        'recent_orders': [{
            'order_number': o.order_number,
            'total': o.total,
            'payment_status': o.payment_status,
            'created_at': o.created_at.strftime('%Y-%m-%d %H:%M')
        } for o in orders]
    })

@api_bp.route('/customers/<int:customer_id>/payment', methods=['POST'])
@login_required
def record_payment(customer_id):
    customer = Customer.query.get_or_404(customer_id)
    data = request.json
    
    amount = float(data.get('amount', 0))
    if amount <= 0:
        return jsonify({'error': 'Invalid amount'}), 400
    
    payment = Payment(
        customer_id=customer.id,
        amount=amount,
        payment_method=data.get('payment_method', 'cash'),
        reference_number=data.get('reference', ''),
        notes=data.get('notes', ''),
        received_by=current_user.id
    )
    
    customer.balance -= amount
    customer.total_paid += amount
    
    db.session.add(payment)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'new_balance': customer.balance,
        'message': f'Payment of Rs.{amount:.2f} recorded'
    })

# ============ DASHBOARD ============
@api_bp.route('/dashboard/stats')
@login_required
def dashboard_stats():
    today = datetime.now().date()
    today_orders = Order.query.filter(
        db.func.date(Order.created_at) == today
    ).all()
    
    return jsonify({
        'today_sales': sum(o.total for o in today_orders),
        'retail_sales': sum(o.total for o in today_orders if o.order_type == 'retail'),
        'wholesale_sales': sum(o.total for o in today_orders if o.order_type == 'wholesale'),
        'transaction_count': len(today_orders),
        'products_count': Product.query.filter_by(is_active=True).count(),
        'low_stock': Product.query.filter(
            Product.stock_quantity <= Product.min_stock_level,
            Product.is_active == True
        ).count(),
        'total_credit': db.session.query(db.func.sum(Customer.balance)).scalar() or 0,
        'wholesale_customers': Customer.query.filter_by(customer_type='wholesale', is_active=True).count()
    })


# ============ DRAWER ============
@api_bp.route('/open-drawer')
@login_required
def open_drawer():
    print(f"🔓 Cash drawer opened by {current_user.username}")
    return jsonify({'success': True})


### a function removed

# ============ RETURNS ============
@api_bp.route('/orders/<order_number>/return', methods=['POST'])
@login_required
def return_order(order_number):
    """Process a return/refund/replacement"""
    from app.models.order import Return
    
    order = Order.query.filter_by(order_number=order_number).first()
    if not order:
        return jsonify({'error': 'Order not found'}), 404
    
    data = request.json
    return_type = data.get('return_type', 'refund')  # refund, replacement, credit_note
    
    # Create return record
    ret = Return(
        order_id=order.id,
        return_type=return_type,
        reason=data.get('reason', ''),
        refund_amount=float(data.get('refund_amount', 0)),
        refund_method=data.get('refund_method', 'cash'),
        processed_by=current_user.id,
        notes=data.get('notes', ''),
        status='completed'
    )
    ret.generate_return_number()
    
    # Handle replacement
    if return_type == 'replacement':
        ret.replacement_product_id = data.get('replacement_product_id')
        ret.replacement_quantity = data.get('replacement_quantity', 1)
        
        if ret.replacement_product_id:
            replacement_product = Product.query.get(ret.replacement_product_id)
            if replacement_product:
                replacement_product.stock_quantity -= ret.replacement_quantity
                repl_movement = StockMovement(
                    product_id=replacement_product.id,
                    user_id=current_user.id,
                    movement_type='stock_out',
                    quantity=-ret.replacement_quantity,
                    previous_stock=replacement_product.stock_quantity + ret.replacement_quantity,
                    new_stock=replacement_product.stock_quantity,
                    reference=f'REPLACE-{ret.return_number}',
                    notes=f'Replacement for order {order_number}'
                )
                db.session.add(repl_movement)
    
    # Handle refund
    if return_type in ['refund', 'credit_note'] and ret.refund_amount > 0:
        selected_items = data.get('items', [])
        
        discount_ratio = 1.0
        if order.subtotal > 0:
            discount_ratio = 1.0 - (order.discount_amount / order.subtotal)
        
        reason_type = data.get('reason_type', 'no_damage')

        for item_data in selected_items:
            price = float(item_data.get('price', 0))
            qty = int(item_data.get('quantity', 1))
            
            if reason_type != 'damaged':
                product = Product.query.get(item_data.get('product_id'))
                if product:
                    product.stock_quantity += qty
                    rtn_movement = StockMovement(
                        product_id=product.id,
                        user_id=current_user.id,
                        movement_type='return',
                        quantity=qty,
                        previous_stock=product.stock_quantity - qty,
                        new_stock=product.stock_quantity,
                        reference=f'RTN-{ret.return_number}'
                    )
                    db.session.add(rtn_movement)
        
        if order.customer_id and order.payment_method == 'credit':
            customer = Customer.query.get(order.customer_id)
            if customer:
                customer.balance -= ret.refund_amount
    
    order.is_returned = True
    order.return_date = datetime.now()
    
    db.session.add(ret)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'return_number': ret.return_number,
        'message': f'Return processed: {ret.return_number}'
    })
 
@api_bp.route('/returns/all')
@login_required
def get_all_returns():
    """Get all returns"""
    from app.models.order import Return
    
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
            'processed_by': r.processor.username if r.processor else 'N/A',
            'customer': r.order.customer_name if r.order else 'N/A'
        } for r in returns]
    })