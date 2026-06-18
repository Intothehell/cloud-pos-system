from flask import Blueprint, jsonify, request, render_template
from flask_login import login_required, current_user
from app import db
from app.models.product import Product, StockMovement

from app.models.customer import Customer, Payment
from app.models.user import User
from app.models.supplier import Supplier
from datetime import datetime
from app.models.order import Order, OrderItem, Return, ReturnItem
from datetime import datetime, timedelta
from sqlalchemy import text

api_bp = Blueprint('api', __name__)


def return_item_order_item_id_enabled():
    try:
        rows = db.session.execute(text("PRAGMA table_info(return_items)")).fetchall()
        return any(row[1] == 'order_item_id' for row in rows)
    except Exception:
        return False


def return_item_order_item_ids(return_item_ids):
    if not return_item_ids or not return_item_order_item_id_enabled():
        return {}
    ids = ','.join(str(int(item_id)) for item_id in return_item_ids)
    rows = db.session.execute(text(f"SELECT id, order_item_id FROM return_items WHERE id IN ({ids})")).fetchall()
    return {row[0]: row[1] for row in rows}


def return_balance_columns_enabled():
    try:
        rows = db.session.execute(text("PRAGMA table_info(returns)")).fetchall()
        columns = {row[1] for row in rows}
        return {'previous_balance', 'new_balance'}.issubset(columns)
    except Exception:
        return False


def set_return_balance_snapshot(return_id, previous_balance, new_balance):
    if not return_balance_columns_enabled():
        return False
    db.session.execute(
        text(
            "UPDATE returns "
            "SET previous_balance = :previous_balance, new_balance = :new_balance "
            "WHERE id = :return_id"
        ),
        {
            'return_id': return_id,
            'previous_balance': previous_balance,
            'new_balance': new_balance
        }
    )
    return True


def get_return_balance_snapshot(return_id):
    if not return_balance_columns_enabled():
        return None
    row = db.session.execute(
        text("SELECT previous_balance, new_balance FROM returns WHERE id = :return_id"),
        {'return_id': return_id}
    ).fetchone()
    if not row:
        return None
    return {
        'previous_balance': row[0],
        'new_balance': row[1],
        'has_balance_snapshot': row[0] is not None and row[1] is not None
    }

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
        terms = [term for term in query.lower().split() if term]
        products = Product.query.filter(Product.is_active == True).all()
        if terms:
            def matches(product):
                haystack = ' '.join([
                    product.name or '',
                    product.barcode or '',
                    product.sku or '',
                    product.category or ''
                ]).lower()
                return all(term in haystack for term in terms)

            products = [product for product in products if matches(product)]

        exact = []
        partial = []
        query_lower = query.lower()
        for product in products:
            barcode = (product.barcode or '').lower()
            sku = (product.sku or '').lower()
            if barcode == query_lower or sku == query_lower:
                exact.append(product)
            else:
                partial.append(product)
        products = (exact + partial)[:50]
    else:
        products = Product.query.filter_by(is_active=True).limit(50).all()
    
    result = []
    for p in products:
        data = p.to_dict()
        data['price'] = p.wholesale_price if customer_type == 'wholesale' else 0
        data['cost_price'] = p.cost_price or 0
        data['retail_price'] = p.retail_price or 0
        data['min_stock_level'] = p.min_stock_level or 0
        data['is_active'] = p.is_active
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
        'retail_price': p.retail_price,
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
    
    cost_price = float(data.get('cost_price', 0) or 0)
    wholesale_price = float(data.get('wholesale_price', 0) or 0)
    retail_price = data.get('retail_price')
    if retail_price in (None, ''):
        retail_price = wholesale_price if wholesale_price > 0 else cost_price

    product = Product(
        barcode=data.get('barcode', ''),
        name=data['name'],
        description=data.get('description', ''),
        category=data.get('category', ''),
        sku=data.get('sku', ''),
        cost_price=cost_price,
        retail_price=float(retail_price or 0),
        wholesale_price=wholesale_price,
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
    if 'retail_price' in data and data.get('retail_price') not in (None, ''):
        product.retail_price = float(data.get('retail_price', product.retail_price))
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
                order.balance_payment_method = data.get('balance_payment_method', 'cash')
                
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
                        payment_method=data.get('balance_payment_method', 'cash'),
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
                'credit_paid_method': data.get('balance_payment_method', 'cash') if order.credit_paid > 0 else None,
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
    """Get all sales and return documents for bill history page"""
    
    date = request.args.get('date', '')
    sale_type = request.args.get('type', 'all')
    payment = request.args.get('payment', 'all')
    search = request.args.get('q', '').strip().lower()
    
    query = Order.query
    return_query = Return.query.join(Order, Return.order_id == Order.id)
    
    if date:
        # Use the date string directly to match the created_at date
        query = query.filter(db.func.date(Order.created_at) == date)
        return_query = return_query.filter(db.func.date(Return.created_at) == date)

    include_orders = sale_type != 'return'
    include_returns = sale_type in ('all', 'return')
    if sale_type not in ('all', 'return'):
        query = query.filter(Order.order_type == sale_type)
    
    if payment != 'all':
        query = query.filter(
            db.or_(
                Order.payment_method == payment,
                Order.balance_payment_method == payment
            )
        )
        return_query = return_query.filter(Order.payment_method == payment)
    
    orders = query.order_by(Order.created_at.desc()).all() if include_orders else []
    returns = return_query.order_by(Return.created_at.desc()).all() if include_returns else []

    def order_item_names(order):
        return ' '.join([item.product_name for item in order.items])

    def return_item_names(ret):
        return ' '.join([item.product_name for item in ReturnItem.query.filter_by(return_id=ret.id).all()])

    rows = []
    for o in orders:
        item_names = order_item_names(o)
        row = {
            'row_kind': 'order',
            'invoice_number': o.order_number,
            'order_number': o.order_number,
            'created_at': o.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'customer_name': o.customer_name or 'Walk-in',
            'customer_phone': o.customer_phone or '',
            'sale_type': o.order_type or 'retail',
            'item_count': len(o.items),
            'total': o.total,
            'payment_method': o.payment_method,
            'type': o.payment_method,
            'payment_status': o.payment_status,
            'status': o.payment_status,
            'balance_payment_method': o.balance_payment_method or '',
            'item_names': item_names,
            'search_text': ' '.join([
                o.order_number or '',
                o.customer_name or '',
                o.customer_phone or '',
                item_names,
            ]).lower(),
        }
        rows.append(row)

    for ret in returns:
        original_order = ret.order
        item_names = return_item_names(ret)
        original_payment = original_order.payment_method if original_order else ret.refund_method
        row = {
            'row_kind': 'return',
            'invoice_number': ret.return_number,
            'order_number': ret.return_number,
            'return_number': ret.return_number,
            'original_order_number': original_order.order_number if original_order else '',
            'created_at': ret.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'customer_name': original_order.customer_name if original_order else 'Walk-in',
            'customer_phone': original_order.customer_phone if original_order else '',
            'sale_type': 'return',
            'item_count': len(ret.order.items) if original_order else 0,
            'total': ret.refund_amount or 0,
            'payment_method': original_payment or '',
            'type': original_payment or '',
            'payment_status': 'returned',
            'status': 'returned',
            'balance_payment_method': '',
            'item_names': item_names,
            'search_text': ' '.join([
                ret.return_number or '',
                original_order.order_number if original_order else '',
                original_order.customer_name if original_order else '',
                original_order.customer_phone if original_order else '',
                item_names,
            ]).lower(),
        }
        rows.append(row)

    if search:
        rows = [row for row in rows if search in row['search_text']]

    rows.sort(key=lambda row: row['created_at'], reverse=True)
    for row in rows:
        row.pop('search_text', None)
    
    return jsonify({
        'orders': rows,
        'total_sales': sum(row['total'] or 0 for row in rows)
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
            'order_item_id': item.id,
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
        .filter(db.or_(Order.order_type.is_(None), Order.order_type != 'payment'))\
        .filter(~Order.order_number.like('CPY-%'))\
        .order_by(Order.created_at.desc()).limit(20).all()
    
    # Get returns for this customer
    order_ids = [o.id for o in orders]
    returns = Return.query.filter(Return.order_id.in_(order_ids))\
        .order_by(Return.created_at.desc()).all() if order_ids else []
    
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
        'linked_supplier': (lambda supplier: {
            'id': supplier.id,
            'name': supplier.name,
            'phone': supplier.phone,
            'nic': supplier.nic,
            'balance': supplier.balance or 0,
            'total_purchases': supplier.total_purchases or 0,
            'total_paid': supplier.total_paid or 0,
            'net_position': (customer.balance or 0) - (supplier.balance or 0),
            'can_offset': (customer.balance or 0) > 0 and (supplier.balance or 0) > 0,
            'max_offset': min(customer.balance or 0, supplier.balance or 0)
        } if supplier else None)(Supplier.query.filter_by(linked_customer_id=customer.id, is_active=True).first()),
        'recent_orders': [{
            'order_number': o.order_number,
            'total': o.total,
            'payment_status': o.payment_status,
            'created_at': o.created_at.strftime('%Y-%m-%d %H:%M')
        } for o in orders],
        'recent_returns': [{
            'return_number': r.return_number,
            'refund_amount': r.refund_amount,
            'refund_method': r.refund_method,
            'created_at': r.created_at.strftime('%Y-%m-%d %H:%M')
        } for r in returns]
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
    
    today_returns = Return.query.filter(
        db.func.date(Return.created_at) == today
    ).all()
    
    # Cash sales from POS (excluding payment receipts CPY-)
    cash_sales = sum(o.total for o in today_orders if o.payment_method == 'cash' and o.order_type != 'payment')
    card_sales = sum(o.total for o in today_orders if o.payment_method == 'card' and o.order_type != 'payment')
    
    # All balance payments today (from POS terminal + customer page)
    today_payments = Payment.query.filter(
        db.func.date(Payment.created_at) == today
    ).all()
    
    cash_payments = sum(p.amount for p in today_payments if p.payment_method == 'cash')
    card_payments = sum(p.amount for p in today_payments if p.payment_method in ('card', 'bank_transfer'))
    cheque_payments = sum(p.amount for p in today_payments if p.payment_method == 'check')
    
    # Refunds today by method
    cash_refunds = sum(r.refund_amount for r in today_returns if r.refund_method == 'cash')
    card_refunds = sum(r.refund_amount for r in today_returns if r.refund_method == 'card')
    
    # Retail and Wholesale sales
    retail_sales = sum(o.total for o in today_orders if o.order_type == 'retail')
    wholesale_sales = sum(o.total for o in today_orders if o.order_type == 'wholesale')
    
    # Subtract returns from sales by original order type
    for r in today_returns:
        if r.order and r.order.order_type == 'retail':
            retail_sales -= r.refund_amount
        elif r.order and r.order.order_type == 'wholesale':
            wholesale_sales -= r.refund_amount
    
    # Top 3 selling items today (by quantity sold)
    top_items = db.session.query(
        OrderItem.product_name,
        db.func.sum(OrderItem.quantity).label('total_qty')
    ).join(Order, OrderItem.order_id == Order.id)\
     .filter(db.func.date(Order.created_at) == today)\
     .filter(Order.order_type != 'payment')\
     .group_by(OrderItem.product_name)\
     .order_by(db.func.sum(OrderItem.quantity).desc())\
     .limit(3).all()
    
    top_items_list = [{'name': item.product_name, 'qty': int(item.total_qty)} for item in top_items]
    
    cash_in_hand = cash_sales + cash_payments - cash_refunds
    to_bank = card_sales + card_payments - card_refunds
    by_cheque = cheque_payments
    
    # Overdue customers: balance > 0, no payment in 4 days, 
    # AND (has pending credit order 4+ days old OR has never ordered)
    four_days_ago = datetime.now() - timedelta(days=4)
    overdue_customers = Customer.query.filter(
        Customer.is_active == True,
        Customer.customer_type == 'wholesale',
        Customer.balance > 0,
        ~Customer.payments.any(db.and_(Payment.created_at >= four_days_ago))
    ).filter(
        db.or_(
            Customer.orders.any(db.and_(
                Order.payment_method == 'credit',
                Order.payment_status == 'pending',
                Order.created_at < four_days_ago
            )),
            ~Customer.orders.any()
        )
    ).count()

    return jsonify({
        'today_sales': retail_sales + wholesale_sales,
        'retail_sales': retail_sales,
        'wholesale_sales': wholesale_sales,
        'transaction_count': len(today_orders),
        'cash_in_hand': cash_in_hand,
        'to_bank': to_bank,
        'by_cheque': by_cheque,
        'products_count': Product.query.filter_by(is_active=True).count(),
        'low_stock': Product.query.filter(
            Product.stock_quantity <= Product.min_stock_level,
            Product.is_active == True
        ).count(),
        'total_credit': db.session.query(db.func.sum(Customer.balance)).filter(Customer.is_active == True).scalar() or 0,
        'wholesale_customers': Customer.query.filter_by(customer_type='wholesale', is_active=True).count(),
        'overdue_customers': overdue_customers,
        'top_items': top_items_list
    })

@api_bp.route('/dashboard/overdue-customers')
@login_required
def overdue_customers_list():
    """Get list of overdue customers for the reminder modal"""
    from datetime import timedelta
    four_days_ago = datetime.now() - timedelta(days=4)
    
    customers = Customer.query.filter(
        Customer.is_active == True,
        Customer.customer_type == 'wholesale',
        Customer.balance > 0,
        ~Customer.payments.any(db.and_(Payment.created_at >= four_days_ago))
    ).filter(
        db.or_(
            Customer.orders.any(db.and_(
                Order.payment_method == 'credit',
                Order.payment_status == 'pending',
                Order.created_at < four_days_ago
            )),
            ~Customer.orders.any()
        )
    ).order_by(Customer.balance.desc()).all()
    
    return jsonify({
        'customers': [{
            'id': c.id,
            'name': c.name,
            'phone': c.phone,
            'balance': c.balance,
            'last_payment': c.payments[-1].created_at.strftime('%Y-%m-%d') if c.payments else 'Never'
        } for c in customers]
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
    reason_type = data.get('reason_type', 'no_damage')
    
    selected_items = data.get('items', [])
    prepared_items = []
    has_order_item_id_column = return_item_order_item_id_enabled()

    if not selected_items:
        return jsonify({'error': 'Select at least one item'}), 400

    for item_data in selected_items:
        return_qty = int(item_data.get('quantity', 1))
        if return_qty <= 0:
            return jsonify({'error': 'Return quantity must be greater than 0'}), 400

        order_item_id = item_data.get('order_item_id')
        original_item = None
        if order_item_id:
            original_item = OrderItem.query.filter_by(
                id=order_item_id,
                order_id=order.id
            ).first()

        if not original_item:
            product_id = item_data.get('product_id')
            original_item = OrderItem.query.filter_by(
                order_id=order.id,
                product_id=product_id
            ).first()

        if not original_item:
            return jsonify({'error': 'Returned item was not found in this order'}), 400

        if order_item_id and has_order_item_id_column:
            already_returned = db.session.execute(
                text(
                    "SELECT COALESCE(SUM(ri.quantity), 0) "
                    "FROM return_items ri JOIN returns r ON ri.return_id = r.id "
                    "WHERE r.order_id = :order_id "
                    "AND (ri.order_item_id = :order_item_id "
                    "OR (ri.order_item_id IS NULL AND ri.product_name = :product_name))"
                ),
                {
                    'order_id': order.id,
                    'order_item_id': original_item.id,
                    'product_name': original_item.product_name
                }
            ).scalar() or 0
        else:
            already_returned = db.session.query(db.func.sum(ReturnItem.quantity))\
                .join(Return, ReturnItem.return_id == Return.id)\
                .filter(Return.order_id == order.id)\
                .filter(ReturnItem.product_name == original_item.product_name)\
                .scalar() or 0
        max_returnable = original_item.quantity - already_returned
        if return_qty > max_returnable:
            return jsonify({
                'error': f'Cannot return {return_qty} x {original_item.product_name}. Only {max_returnable} remaining (original: {original_item.quantity}, already returned: {int(already_returned)})'
            }), 400

        prepared_items.append({
            'order_item': original_item,
            'quantity': return_qty,
            'price': float(item_data.get('price', original_item.product_price or 0))
        })

    # Create return record after validation passes.
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
    
    db.session.add(ret)
    db.session.flush()  # Get ret.id without full commit

    for item_data in prepared_items:
        original_item = item_data['order_item']
        return_item = ReturnItem(
            return_id=ret.id,
            product_name=original_item.product_name,
            product_price=item_data['price'],
            quantity=item_data['quantity'],
            is_damaged=(reason_type == 'damaged')
        )
        db.session.add(return_item)
        db.session.flush()
        if has_order_item_id_column:
            db.session.execute(
                text("UPDATE return_items SET order_item_id = :order_item_id WHERE id = :id"),
                {'order_item_id': original_item.id, 'id': return_item.id}
            )
    
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
    return_previous_balance = None
    return_new_balance = None
    has_return_balance_snapshot = False
    if return_type in ['refund', 'credit_note'] and ret.refund_amount > 0:
        for item_data in prepared_items:
            qty = item_data['quantity']
            if reason_type != 'damaged':
                product = Product.query.get(item_data['order_item'].product_id)
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
                return_previous_balance = customer.balance
                customer.balance -= ret.refund_amount
                return_new_balance = customer.balance
                has_return_balance_snapshot = set_return_balance_snapshot(
                    ret.id,
                    return_previous_balance,
                    return_new_balance
                )
    
    order.is_returned = True
    order.return_date = datetime.now()
    
    db.session.commit()
    
    # Build return bill data from saved items
    saved_items = ReturnItem.query.filter_by(return_id=ret.id).all()
    saved_order_item_ids = return_item_order_item_ids([ri.id for ri in saved_items])
    returned_items = [{
        'order_item_id': saved_order_item_ids.get(ri.id),
        'name': ri.product_name,
        'price': ri.product_price,
        'quantity': ri.quantity,
        'total': ri.product_price * ri.quantity,
        'is_damaged': ri.is_damaged
    } for ri in saved_items]
    
    return jsonify({
        'success': True,
        'return_number': ret.return_number,
        'message': f'Return processed: {ret.return_number}',
        'return_details': {
            'return_number': ret.return_number,
            'return_type': ret.return_type,
            'reason': ret.reason,
            'refund_amount': ret.refund_amount,
            'refund_method': ret.refund_method,
            'order_number': order.order_number,
            'customer_name': order.customer_name or 'Walk-in Customer',
            'customer_phone': order.customer_phone or '',
            'created_at': ret.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'is_credit_return': bool(order.customer_id and order.payment_method == 'credit'),
            'previous_balance': return_previous_balance,
            'new_balance': return_new_balance,
            'has_balance_snapshot': has_return_balance_snapshot or (return_previous_balance is not None and return_new_balance is not None),
            'items': returned_items
        }
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
            'customer': r.order.customer_name if r.order else 'N/A',
            'item_names': ' '.join([item.product_name for item in ReturnItem.query.filter_by(return_id=r.id).all()])
        } for r in returns]
    })

@api_bp.route('/returns/<return_number>/details')
@login_required
def return_details(return_number):

    """Get return details for bill/receipt"""
    ret = Return.query.filter_by(return_number=return_number).first()
    if not ret:
        return jsonify({'error': 'Return not found'}), 404
    
    order = ret.order
    items = ReturnItem.query.filter_by(return_id=ret.id).all()
    item_order_ids = return_item_order_item_ids([ri.id for ri in items])
    balance_snapshot = get_return_balance_snapshot(ret.id) or {}
    is_credit_return = bool(order and order.customer_id and order.payment_method == 'credit')
    
    return jsonify({
        'return_number': ret.return_number,
        'return_type': ret.return_type,
        'reason': ret.reason,
        'refund_amount': ret.refund_amount,
        'refund_method': ret.refund_method,
        'order_number': order.order_number if order else 'N/A',
        'customer_name': order.customer_name if order else 'Walk-in Customer',
        'customer_phone': order.customer_phone if order else '',
        'created_at': ret.created_at.strftime('%Y-%m-%d %H:%M:%S'),
        'is_credit_return': is_credit_return,
        'previous_balance': balance_snapshot.get('previous_balance'),
        'new_balance': balance_snapshot.get('new_balance'),
        'has_balance_snapshot': bool(balance_snapshot.get('has_balance_snapshot')),
        'items': [{
            'order_item_id': item_order_ids.get(ri.id),
            'name': ri.product_name,
            'price': ri.product_price,
            'quantity': ri.quantity,
            'total': ri.product_price * ri.quantity,
            'is_damaged': ri.is_damaged
        } for ri in items]
    })

@api_bp.route('/returns/damaged-items')
@login_required
def damaged_items():
    """Get damaged returned items grouped by product"""
    from sqlalchemy import func
    
    items = db.session.query(
        ReturnItem.product_name,
        func.sum(ReturnItem.quantity).label('total_qty'),
        Product.barcode,
        Product.category,
        Product.cost_price,
        Product.id.label('product_id')
    ).outerjoin(Product, ReturnItem.product_name == Product.name)\
     .filter(ReturnItem.is_damaged == True)\
     .filter(ReturnItem.quantity > 0)\
     .group_by(ReturnItem.product_name)\
     .order_by(ReturnItem.product_name).all()
    
    return jsonify({
        'items': [{
            'product_name': item.product_name,
            'quantity': int(item.total_qty),
            'barcode': item.barcode or '',
            'category': item.category or 'Unknown',
            'cost_price': item.cost_price or 0,
            'product_id': item.product_id
        } for item in items]
    })

@api_bp.route('/returns/damaged-items/adjust', methods=['POST'])
@login_required
def adjust_damaged_item():
    """Adjust quantity of damaged items by product name"""
    if current_user.role not in ['owner', 'manager']:
        return jsonify({'error': 'Permission denied'}), 403
    
    data = request.json
    product_name = data.get('product_name')
    qty = int(data.get('quantity', 0))
    adj_type = data.get('type', 'remove')
    
    if not product_name or qty < 1:
        return jsonify({'error': 'Invalid data'}), 400
    
    # Get all damaged items for this product, oldest first
    items = db.session.query(ReturnItem)\
        .join(Return, ReturnItem.return_id == Return.id)\
        .filter(ReturnItem.product_name == product_name)\
        .filter(ReturnItem.is_damaged == True)\
        .filter(ReturnItem.quantity > 0)\
        .order_by(Return.created_at.asc()).all()
    
    total_available = sum(i.quantity for i in items)
    
    if adj_type == 'remove':
        if qty > total_available:
            return jsonify({'error': f'Only {total_available} available'}), 400
        
        remaining = qty
        for item in items:
            if remaining <= 0:
                break
            if item.quantity >= remaining:
                item.quantity -= remaining
                remaining = 0
            else:
                remaining -= item.quantity
                item.quantity = 0
    
    elif adj_type == 'add':
        # Add to the most recent return item
        if items:
            items[-1].quantity += qty
        else:
            return jsonify({'error': 'No existing damaged item found for this product'}), 400
    
    elif adj_type == 'set':
        # Set exact quantity on the most recent item
        if items:
            diff = qty - total_available
            items[-1].quantity += diff
        elif qty > 0:
            return jsonify({'error': 'No existing damaged item found'}), 400
    
    db.session.commit()
    
    # Return updated total
    updated_total = sum(i.quantity for i in items)
    return jsonify({'success': True, 'new_quantity': updated_total})
