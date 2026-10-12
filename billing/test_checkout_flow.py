"""End-to-end cashier flow: add to cart -> checkout page -> invoice.

Also guards against decorators landing on internal helpers, which breaks
them with "'dict' object has no attribute 'user'".
"""
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from billing import views
from billing.models import Invoice
from inventory.models import Category, Product


class HelpersAreNotViewsTests(TestCase):
    def test_helpers_carry_no_view_decorators(self):
        for fn in (views._get_cart, views._save_cart, views._add_product,
                   views._create_invoice, views._cart_lines, views._checkout_context):
            self.assertFalse(hasattr(fn, "__wrapped__"), fn.__name__)


class CashierCheckoutFlowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.cashier = User.objects.create_user("cashier", password="pw12345!")
        cat = Category.objects.create(name="Food")
        cls.rice = Product.objects.create(category=cat, name="Rice", price=Decimal("100.00"), stock=5, barcode="111")
        cls.oil = Product.objects.create(category=cat, name="Oil", price=Decimal("50.00"), stock=5, barcode="222")

    def setUp(self):
        self.client.login(username="cashier", password="pw12345!")

    def test_cashier_can_add_to_cart(self):
        r = self.client.post(reverse("add_to_cart", args=[self.rice.id]))
        self.assertRedirects(r, reverse("cart"))
        self.assertIn(str(self.rice.id), self.client.session["cart"])

    def test_cashier_can_scan_barcode(self):
        r = self.client.get(reverse("scan_barcode"), {"barcode": "222"})
        self.assertTrue(r.json()["success"])
        self.assertIn(str(self.oil.id), self.client.session["cart"])

    def test_checkout_page_renders_with_totals(self):
        self.client.post(reverse("add_to_cart", args=[self.rice.id]))
        self.client.post(reverse("add_to_cart", args=[self.oil.id]))
        r = self.client.get(reverse("checkout"))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context["subtotal"], Decimal("150.00"))
        self.assertEqual(r.context["vat"], Decimal("19.50"))
        self.assertEqual(r.context["total"], Decimal("169.50"))
        self.assertContains(r, "Rice")

    def test_checkout_creates_invoice_and_reduces_stock(self):
        self.client.post(reverse("add_to_cart", args=[self.rice.id]))
        r = self.client.post(reverse("checkout"), {
            "payment_method": "cash", "paid_amount": "113", "discount": "0", "vat": "13",
        })
        self.assertEqual(r.status_code, 302)
        inv = Invoice.objects.get()
        self.assertEqual(inv.created_by, self.cashier)
        self.assertEqual(inv.total, Decimal("113.00"))
        self.assertEqual(inv.due_amount, Decimal("0.00"))
        self.rice.refresh_from_db()
        self.assertEqual(self.rice.stock, 4)
        self.assertEqual(self.client.session["cart"], {})

    def test_validation_error_reshows_checkout_with_totals(self):
        self.client.post(reverse("add_to_cart", args=[self.rice.id]))
        r = self.client.post(reverse("checkout"), {
            "payment_method": "cash", "paid_amount": "10", "discount": "9999", "vat": "13",
        })
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context["total"], Decimal("113.00"))
        self.assertEqual(Invoice.objects.count(), 0)
        self.rice.refresh_from_db()
        self.assertEqual(self.rice.stock, 5)


class VatAndTotalsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.cashier = User.objects.create_user("cashier", password="pw12345!")
        cat = Category.objects.create(name="Food")
        cls.rice = Product.objects.create(category=cat, name="Rice", price=Decimal("100.00"), stock=50)
        cls.coin = Product.objects.create(category=cat, name="Candy", price=Decimal("0.50"), stock=50)

    def setUp(self):
        self.client.login(username="cashier", password="pw12345!")

    def _checkout(self, product, **fields):
        self.client.post(reverse("add_to_cart", args=[product.id]))
        data = {"payment_method": "cash", "paid_amount": "0", "discount": "0", "vat": "13"}
        data.update(fields)
        return self.client.post(reverse("checkout"), data)

    def test_vat_percent_is_taken_from_the_form(self):
        self._checkout(self.rice, vat="0")
        self.assertEqual(Invoice.objects.get().total, Decimal("100.00"))

    def test_decimal_vat_percent(self):
        self._checkout(self.rice, vat="15.5")
        inv = Invoice.objects.get()
        self.assertEqual(inv.vat, Decimal("15.50"))
        self.assertEqual(inv.total, Decimal("115.50"))

    def test_vat_applies_after_discount(self):
        self._checkout(self.rice, vat="13", discount="20")
        inv = Invoice.objects.get()
        self.assertEqual(inv.vat, Decimal("10.40"))
        self.assertEqual(inv.total, Decimal("90.40"))

    def test_vat_rounds_half_up(self):
        # 0.50 * 13% = 0.065 -> 0.07 (banker's rounding would give 0.06)
        self._checkout(self.coin, vat="13")
        inv = Invoice.objects.get()
        self.assertEqual(inv.vat, Decimal("0.07"))
        self.assertEqual(inv.total, Decimal("0.57"))

    def test_vat_over_100_or_negative_is_rejected(self):
        for bad in ("101", "-1", "abc"):
            r = self._checkout(self.rice, vat=bad)
            self.assertEqual(r.status_code, 200, bad)
        self.assertEqual(Invoice.objects.count(), 0)

    def test_blank_vat_uses_default(self):
        self._checkout(self.rice, vat="")
        self.assertEqual(Invoice.objects.get().total, Decimal("113.00"))

    def test_esewa_and_khalti_are_accepted(self):
        for method in ("esewa", "khalti"):
            Invoice.objects.all().delete()
            self._checkout(self.rice, payment_method=method)
            self.assertEqual(Invoice.objects.get().payment_method, method)

    def test_page_has_vat_input_and_no_dead_tax_field(self):
        self.client.post(reverse("add_to_cart", args=[self.rice.id]))
        html = self.client.get(reverse("checkout")).content.decode()
        self.assertIn('name="vat"', html)
        self.assertNotIn('name="tax"', html)
        self.assertIn('data-subtotal-cents="10000"', html)
        self.assertIn('value="esewa"', html)

    def test_entered_values_survive_a_validation_error(self):
        r = self._checkout(self.rice, vat="7.5", discount="9999", paid_amount="42")
        self.assertEqual(r.status_code, 200)
        html = r.content.decode()
        self.assertIn('value="7.5"', html)
        self.assertIn('value="9999"', html)
        self.assertIn('value="42"', html)