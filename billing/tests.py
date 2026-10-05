import re
from decimal import Decimal
from unittest import mock

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from inventory.models import Category, Product

from .models import Invoice, InvoiceItem


class CartAndCheckoutTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("cashier", password="pw-12345")
        self.client.login(username="cashier", password="pw-12345")

        category = Category.objects.create(name="General")
        self.pen = Product.objects.create(
            category=category, name="Pen", price=Decimal("10.50"), stock=5
        )
        self.book = Product.objects.create(
            category=category, name="Book", price=Decimal("100.00"), stock=2
        )

    # -- helpers ---------------------------------------------------------
    def add(self, product, times=1):
        for _ in range(times):
            self.client.post(reverse("add_to_cart", args=[product.id]))

    def pay(self, **overrides):
        data = {
            "customer": "",
            "payment_method": "cash",
            "discount": "0",
            "tax": "0",
            "paid_amount": "9999",
        }
        data.update(overrides)
        return self.client.post(reverse("checkout"), data)

    # -- cart ------------------------------------------------------------
    def test_cart_session_is_json_serialisable_and_totals_are_numeric(self):
        # Regression: Decimal in the session used to raise TypeError.
        self.add(self.pen, 3)
        response = self.client.get(reverse("cart"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["subtotal"], Decimal("31.50"))

    def test_barcode_and_button_add_to_cart_use_same_format(self):
        # Regression: scan stored price as str, button stored Decimal, and
        # str * int repeated the string instead of multiplying.
        self.client.post(reverse("scan_barcode"), {"barcode": self.pen.barcode})
        self.add(self.pen)
        response = self.client.get(reverse("cart"))
        self.assertEqual(response.context["subtotal"], Decimal("21.00"))

    def test_cannot_add_more_than_stock(self):
        self.add(self.book, 5)
        cart = self.client.session["cart"]
        self.assertEqual(cart[str(self.book.id)]["quantity"], 2)

    def test_cart_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse("cart"))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(reverse("login")))

    def test_unknown_or_empty_barcode_does_not_404(self):
        response = self.client.post(reverse("scan_barcode"), {"barcode": "nope"})
        self.assertEqual(response.status_code, 302)
        response = self.client.post(reverse("scan_barcode"), {"barcode": "  "})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.session.get("cart", {}), {})

    # -- checkout: happy path -------------------------------------------
    def test_checkout_creates_invoice_and_reduces_stock(self):
        self.add(self.pen, 2)
        self.add(self.book)
        response = self.pay(discount="1", tax="10")

        invoice = Invoice.objects.get()
        self.assertRedirects(response, reverse("invoice", args=[invoice.id]))
        # subtotal 121.00, discount 1, tax 12.10 -> 132.10
        self.assertEqual(invoice.subtotal, Decimal("121.00"))
        self.assertEqual(invoice.tax, Decimal("12.10"))
        self.assertEqual(invoice.total, Decimal("132.10"))
        self.assertEqual(invoice.payment_status, "paid")
        self.assertEqual(invoice.due_amount, Decimal("0"))
        self.assertEqual(invoice.invoice_number, f"INV-{invoice.pk:05d}")
        self.assertEqual(InvoiceItem.objects.filter(invoice=invoice).count(), 2)

        self.pen.refresh_from_db()
        self.book.refresh_from_db()
        self.assertEqual(self.pen.stock, 3)
        self.assertEqual(self.book.stock, 1)
        self.assertEqual(self.client.session["cart"], {})

    def test_overpayment_is_capped_and_partial_payment_tracked(self):
        self.add(self.book)
        self.pay(paid_amount="500")
        self.assertEqual(Invoice.objects.get().paid_amount, Decimal("100.00"))

        self.add(self.pen)
        self.pay(paid_amount="4")
        partial = Invoice.objects.latest("id")
        self.assertEqual(partial.payment_status, "partial")
        self.assertEqual(partial.due_amount, Decimal("6.50"))

        self.add(self.pen)
        self.pay(paid_amount="0")
        self.assertEqual(Invoice.objects.latest("id").payment_status, "due")

    def test_invoice_numbers_stay_unique_after_a_delete(self):
        # Regression: count()+1 reused numbers after a deletion -> crash.
        self.add(self.pen)
        self.pay()
        self.add(self.pen)
        self.pay()
        Invoice.objects.order_by("id").first().delete()
        self.add(self.pen)
        self.pay()  # would raise IntegrityError with the old numbering
        numbers = list(Invoice.objects.values_list("invoice_number", flat=True))
        self.assertEqual(len(numbers), len(set(numbers)))

    # -- checkout: atomicity ---------------------------------------------
    def test_failure_on_second_item_rolls_back_first_items_stock(self):
        # Regression: stock of earlier items stayed deducted when a later
        # item failed, and the invoice delete did not restore it.
        self.add(self.pen, 2)
        self.add(self.book, 2)
        self.book.stock = 1  # someone else sold one meanwhile
        self.book.save()

        self.pay()

        self.assertEqual(Invoice.objects.count(), 0)
        self.pen.refresh_from_db()
        self.assertEqual(self.pen.stock, 5)  # untouched
        self.assertTrue(self.client.session["cart"])  # cart kept for retry

    def test_unexpected_error_mid_checkout_rolls_everything_back(self):
        self.add(self.pen, 2)
        with mock.patch(
            "billing.views.InvoiceItem.objects.bulk_create",
            side_effect=RuntimeError("db went away"),
        ):
            response = self.pay()

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Invoice.objects.count(), 0)
        self.pen.refresh_from_db()
        self.assertEqual(self.pen.stock, 5)

    def test_price_comes_from_database_not_stale_cart(self):
        self.add(self.pen)
        self.pen.price = Decimal("20.00")
        self.pen.save()
        self.pay()
        self.assertEqual(Invoice.objects.get().subtotal, Decimal("20.00"))

    # -- checkout: input validation --------------------------------------
    def test_bad_input_is_rejected_without_crashing_or_writing(self):
        bad_cases = [
            {"discount": "abc"},
            {"discount": "-5"},
            {"discount": "NaN"},
            {"discount": "Infinity"},
            {"discount": "9999"},  # more than subtotal
            {"tax": "150"},
            {"paid_amount": "-1"},
            {"payment_method": "bitcoin"},
            {"customer": "abc"},
            {"customer": "99999"},
        ]
        for overrides in bad_cases:
            with self.subTest(overrides=overrides):
                self.add(self.pen)
                response = self.pay(**overrides)
                self.assertEqual(response.status_code, 302)
                self.assertEqual(Invoice.objects.count(), 0)
                self.pen.refresh_from_db()
                self.assertEqual(self.pen.stock, 5)
                self.client.post(reverse("clear_cart"))

    def test_empty_cart_redirects_to_cart(self):
        response = self.client.get(reverse("checkout"))
        self.assertRedirects(response, reverse("cart"))


class StateChangesRequirePostAndCsrfTests(TestCase):
    """Cart changes and scans must be POST-only and CSRF-protected."""

    def setUp(self):
        self.user = User.objects.create_user("cashier", password="pw-12345")
        self.client.login(username="cashier", password="pw-12345")
        category = Category.objects.create(name="General")
        self.pen = Product.objects.create(
            category=category, name="Pen", price=Decimal("10.00"), stock=5
        )
        self.client.post(reverse("add_to_cart", args=[self.pen.id]))

    def cart_qty(self):
        cart = self.client.session.get("cart", {})
        return cart.get(str(self.pen.id), {}).get("quantity", 0)

    def test_get_is_rejected_and_changes_nothing(self):
        before = self.cart_qty()
        urls = [
            reverse("add_to_cart", args=[self.pen.id]),
            reverse("increase_quantity", args=[self.pen.id]),
            reverse("decrease_quantity", args=[self.pen.id]),
            reverse("remove_from_cart", args=[self.pen.id]),
            reverse("clear_cart"),
            reverse("scan_barcode"),
        ]
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 405)
                self.assertEqual(self.cart_qty(), before)

    def test_anonymous_post_is_redirected_to_login(self):
        self.client.logout()
        response = self.client.post(reverse("clear_cart"))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(reverse("login")))

    def test_pages_render_forms_with_working_csrf_tokens(self):
        # enforce_csrf_checks=True turns Django's CSRF protection back on
        # (the normal test client disables it), so this fails if any
        # template form is missing its {% csrf_token %}.
        client = Client(enforce_csrf_checks=True)
        client.login(username="cashier", password="pw-12345")

        def token_from(response):
            html = response.content.decode()
            match = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', html)
            self.assertIsNotNone(match, "page has no CSRF-protected form")
            return match.group(1)

        # No token -> 403
        response = client.post(reverse("increase_quantity", args=[self.pen.id]))
        self.assertEqual(response.status_code, 403)

        # Token taken from the rendered cart page -> works
        client.post(reverse("scan_barcode"), {"barcode": self.pen.barcode},
                    HTTP_X_CSRFTOKEN=token_from(client.get(reverse("billing_products"))))
        page = client.get(reverse("cart"))
        html = page.content.decode()
        self.assertNotIn("href=\"/billing/remove/", html)
        self.assertNotIn("href=\"/billing/clear/", html)
        response = client.post(
            reverse("increase_quantity", args=[self.pen.id]),
            {"csrfmiddlewaretoken": token_from(page)},
        )
        self.assertEqual(response.status_code, 302)

    def test_every_post_form_on_every_page_has_its_own_csrf_token(self):
        # Checks each <form method="post"> individually, so one form with a
        # token cannot hide another form without one.
        self.client.post(reverse("add_to_cart", args=[self.pen.id]))
        pages = ["cart", "billing_products", "checkout", "view_product",
                 "view_category", "dashboard"]
        for name in pages:
            with self.subTest(page=name):
                html = self.client.get(reverse(name)).content.decode()
                forms = re.findall(r"<form\b[^>]*>.*?</form>", html, re.S | re.I)
                post_forms = [f for f in forms if re.search(r'method="post"', f, re.I)]
                self.assertTrue(post_forms, "expected at least one POST form")
                for form in post_forms:
                    self.assertIn("csrfmiddlewaretoken", form, form[:120])

    def test_product_list_has_no_get_links_that_change_data(self):
        html = self.client.get(reverse("billing_products")).content.decode()
        self.assertNotIn(f'href="/billing/add/{self.pen.id}/"', html)
        self.assertIn('name="barcode"', html)