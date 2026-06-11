def seed_supply_inputs():
    from app import db
    from app.models.product import Product
    from app.models.supplier import Supplier

    supplier = Supplier(name='Northline Imports', phone='0771234567', nic='SUP1001')
    product = Product(
        barcode='P-100',
        sku='CHAIR-01',
        name='Dining Chair',
        category='Furniture',
        cost_price=1000,
        wholesale_price=1500,
        stock_quantity=5,
        min_stock_level=2,
        is_active=True,
    )
    db.session.add_all([supplier, product])
    db.session.commit()
    return supplier, product


def test_create_supply_bill_updates_stock_and_supplier_balance(app, manager_client):
    from app.models.product import Product, StockMovement
    from app.models.supplier import SupplierPayment
    from app.models.supply import SupplyBill

    with app.app_context():
        supplier, product = seed_supply_inputs()
        supplier_id = supplier.id
        product_id = product.id

    response = manager_client.post('/supply/api/bills', json={
        'supplier_id': supplier_id,
        'supplier_invoice': 'INV-44',
        'discount_amount': 100,
        'paid_amount': 500,
        'payment_method': 'cash',
        'items': [{
            'product_id': product_id,
            'quantity': 3,
            'unit_cost': 1200,
            'wholesale_price': 1800,
        }],
    })

    assert response.status_code == 200
    data = response.get_json()
    assert data['success'] is True
    assert data['bill']['payment_status'] == 'partial'

    with app.app_context():
        product = Product.query.get(product_id)
        bill = SupplyBill.query.filter_by(bill_number=data['bill']['bill_number']).first()
        movement = StockMovement.query.filter_by(reference=bill.bill_number).first()
        payment = SupplierPayment.query.filter_by(supply_bill_id=bill.id).first()

        assert product.stock_quantity == 8
        assert product.cost_price == 1200
        assert product.wholesale_price == 1800
        assert bill.total == 3500
        assert bill.balance_amount == 3000
        assert bill.supplier.balance == 3000
        assert movement.movement_type == 'supply_in'
        assert payment.amount == 500


def test_create_supply_bill_rejects_invalid_supplier(manager_client):
    response = manager_client.post('/supply/api/bills', json={
        'supplier_id': 999,
        'items': [{'product_id': 1, 'quantity': 1, 'unit_cost': 10}],
    })

    assert response.status_code == 404
    assert response.get_json()['error'] == 'Supplier not found'


def test_staff_cannot_create_supply_bill(app, staff_client):
    with app.app_context():
        supplier, product = seed_supply_inputs()
        supplier_id = supplier.id
        product_id = product.id

    response = staff_client.post('/supply/api/bills', json={
        'supplier_id': supplier_id,
        'items': [{'product_id': product_id, 'quantity': 1, 'unit_cost': 10}],
    })

    assert response.status_code == 403


def test_supply_product_search_supports_split_keywords(app, manager_client):
    with app.app_context():
        seed_supply_inputs()

    response = manager_client.get('/supply/api/products/search?q=Dining Furniture')

    assert response.status_code == 200
    names = [item['name'] for item in response.get_json()]
    assert 'Dining Chair' in names

    assert manager_client.get('/supply/api/products/search?q=P-100').get_json()[0]['barcode'] == 'P-100'
    assert manager_client.get('/supply/api/products/search?q=CHAIR-01').get_json()[0]['sku'] == 'CHAIR-01'
    assert manager_client.get('/supply/api/products/search?q=Furniture').get_json()[0]['category'] == 'Furniture'


def test_supplier_details_suggests_customer_match_by_nic(app, manager_client):
    from app import db
    from app.models.customer import Customer
    from app.models.supplier import Supplier

    with app.app_context():
        customer = Customer(name='Nisith Herath', phone='0711111111', nic='200601603087', balance=3350)
        supplier = Supplier(name='Nisith Ranvidu', phone='0772222222', nic='200601603087', balance=500)
        db.session.add_all([customer, supplier])
        db.session.commit()
        supplier_id = supplier.id

    response = manager_client.get(f'/supply/api/suppliers/{supplier_id}/details')

    assert response.status_code == 200
    data = response.get_json()
    assert data['linked_customer'] is None
    assert data['customer_matches'][0]['match_type'] == 'nic'
    assert data['customer_matches'][0]['balance'] == 3350


def test_link_customer_and_offset_balances(app, manager_client):
    from app import db
    from app.models.customer import Customer, Payment
    from app.models.supplier import Supplier, SupplierPayment
    from app.models.supply import LedgerOffset

    with app.app_context():
        customer = Customer(name='Same Person', phone='0710000000', nic='NIC-LINK', balance=1000)
        supplier = Supplier(name='Same Person Supplies', phone='0770000000', nic='NIC-LINK', balance=600)
        db.session.add_all([customer, supplier])
        db.session.commit()
        customer_id = customer.id
        supplier_id = supplier.id

    link_response = manager_client.post(
        f'/supply/api/suppliers/{supplier_id}/link-customer',
        json={'customer_id': customer_id},
    )
    assert link_response.status_code == 200

    offset_response = manager_client.post(
        f'/supply/api/suppliers/{supplier_id}/offset',
        json={'amount': 600, 'reference': 'manual approval'},
    )

    assert offset_response.status_code == 200
    data = offset_response.get_json()
    assert data['offset']['amount'] == 600
    assert data['linked_customer']['balance'] == 400
    assert data['supplier']['balance'] == 0

    with app.app_context():
        assert LedgerOffset.query.count() == 1
        assert Payment.query.filter_by(payment_method='offset').count() == 1
        assert SupplierPayment.query.filter_by(payment_method='offset').count() == 1


def test_supplier_payment_settles_open_supply_bills_fifo(app, manager_client):
    from app.models.supply import SupplyBill

    with app.app_context():
        supplier, product = seed_supply_inputs()
        supplier_id = supplier.id
        product_id = product.id

    for reference in ['FIFO-1', 'FIFO-2']:
        response = manager_client.post('/supply/api/bills', json={
            'supplier_id': supplier_id,
            'supplier_invoice': reference,
            'paid_amount': 0,
            'payment_method': 'credit',
            'items': [{'product_id': product_id, 'quantity': 1, 'unit_cost': 100}],
        })
        assert response.status_code == 200

    payment_response = manager_client.post(f'/supply/api/suppliers/{supplier_id}/payment', json={
        'amount': 150,
        'payment_method': 'cash',
        'reference': 'PAY-FIFO',
    })

    assert payment_response.status_code == 200
    with app.app_context():
        bills = SupplyBill.query.filter_by(supplier_id=supplier_id).order_by(SupplyBill.created_at.asc()).all()
        assert bills[0].balance_amount == 0
        assert bills[0].payment_status == 'completed'
        assert bills[1].balance_amount == 50
        assert bills[1].payment_status == 'partial'


def test_supply_return_against_paid_note_records_supplier_credit(app, manager_client):
    from app.models.product import Product, StockMovement
    from app.models.supply import SupplyBill, SupplyReturn

    with app.app_context():
        supplier, product = seed_supply_inputs()
        supplier_id = supplier.id
        product_id = product.id

    bill_response = manager_client.post('/supply/api/bills', json={
        'supplier_id': supplier_id,
        'supplier_invoice': 'PAID-RETURN',
        'paid_amount': 200,
        'payment_method': 'cash',
        'items': [{'product_id': product_id, 'quantity': 2, 'unit_cost': 100}],
    })
    assert bill_response.status_code == 200
    bill_id = bill_response.get_json()['bill']['id']

    return_response = manager_client.post('/supply/api/returns', json={
        'supply_bill_id': bill_id,
        'product_id': product_id,
        'quantity': 1,
        'reason': 'Damaged on receipt',
    })

    assert return_response.status_code == 200
    data = return_response.get_json()
    assert data['return']['payable_adjusted'] == 0
    assert data['return']['credit_amount'] == 100

    with app.app_context():
        product = Product.query.get(product_id)
        bill = SupplyBill.query.get(bill_id)
        ret = SupplyReturn.query.first()
        movement = StockMovement.query.filter_by(reference=ret.return_number).first()

        assert product.stock_quantity == 6
        assert bill.total == 200
        assert bill.balance_amount == 0
        assert ret.credit_amount == 100
        assert movement.movement_type == 'supply_return'


def test_supply_dashboard_flags_suppliers_without_recent_payment(app, manager_client):
    from datetime import datetime, timedelta

    from app import db
    from app.models.supply import SupplyBill

    with app.app_context():
        supplier, product = seed_supply_inputs()
        supplier_id = supplier.id
        product_id = product.id

    bill_response = manager_client.post('/supply/api/bills', json={
        'supplier_id': supplier_id,
        'supplier_invoice': 'OLD-PAYABLE',
        'paid_amount': 0,
        'payment_method': 'credit',
        'items': [{'product_id': product_id, 'quantity': 1, 'unit_cost': 100}],
    })
    assert bill_response.status_code == 200

    with app.app_context():
        bill = SupplyBill.query.filter_by(supplier_id=supplier_id).first()
        bill.created_at = datetime.now() - timedelta(days=6)
        db.session.commit()

    stats_response = manager_client.get('/supply/api/dashboard/stats')
    list_response = manager_client.get('/supply/api/dashboard/overdue-suppliers')

    assert stats_response.status_code == 200
    assert stats_response.get_json()['overdue_suppliers'] == 1
    assert list_response.status_code == 200
    suppliers = list_response.get_json()['suppliers']
    assert suppliers[0]['name'] == 'Northline Imports'
    assert suppliers[0]['oldest_note'] == bill_response.get_json()['bill']['bill_number']
