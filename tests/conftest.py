import os

import pytest


@pytest.fixture()
def app(tmp_path, monkeypatch):
    db_path = tmp_path / 'test-pos.db'
    monkeypatch.setenv('DATABASE_URL', f'sqlite:///{db_path}')

    from app import create_app, db
    from app.models.customer import Customer, Payment
    from app.models.order import Order, OrderItem, Return, ReturnItem
    from app.models.product import Product, StockMovement
    from app.models.supplier import Supplier, SupplierPayment
    from app.models.supply import LedgerOffset, SupplyBill, SupplyBillItem, SupplyReturn
    from app.models.user import User

    flask_app = create_app()
    flask_app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)

    with flask_app.app_context():
        db.drop_all()
        db.create_all()
        yield flask_app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


def create_user(username='manager', role='manager'):
    from app import db
    from app.models.user import User

    user = User(username=username, email=f'{username}@example.com', role=role, is_active=True)
    user.set_password('password')
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture()
def manager_client(app, client):
    with app.app_context():
        create_user('manager', 'manager')
    client.post('/auth/login', data={'username': 'manager', 'password': 'password'})
    return client


@pytest.fixture()
def staff_client(app, client):
    with app.app_context():
        create_user('staff', 'staff')
    client.post('/auth/login', data={'username': 'staff', 'password': 'password'})
    return client
