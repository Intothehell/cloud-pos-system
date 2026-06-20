def test_supply_bill_recalculates_partial_payment(app):
    from app.models.supply import SupplyBill, SupplyBillItem

    with app.app_context():
        bill = SupplyBill(discount_amount=10, paid_amount=40)
        bill.items = [
            SupplyBillItem(quantity=2, unit_cost=25, line_total=50),
            SupplyBillItem(quantity=1, unit_cost=20, line_total=20),
        ]

        bill.recalculate_totals()

        assert bill.subtotal == 70
        assert bill.total == 60
        assert bill.paid_amount == 40
        assert bill.balance_amount == 20
        assert bill.payment_status == 'partial'
