def test_supply_pages_render(manager_client):
    for path in [
        '/supply/dashboard',
        '/supply/receive',
        '/supply/bills',
        '/supply/suppliers',
        '/supply/inventory',
        '/supply/returns',
    ]:
        response = manager_client.get(path)
        assert response.status_code == 200


def test_supply_payments_redirects_to_suppliers(manager_client):
    response = manager_client.get('/supply/payments')
    assert response.status_code == 302
    assert '/supply/suppliers' in response.headers['Location']


def test_sales_pages_still_render(manager_client):
    for path in ['/pos/terminal', '/pos/bills', '/inventory/manage']:
        response = manager_client.get(path)
        assert response.status_code == 200
