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