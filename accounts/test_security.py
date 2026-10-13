"""Regression tests for the access-control and data-integrity fixes."""
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from billing.models import Expense, ExpenseCategory, Invoice, InvoiceItem
from inventory.models import Category, Product


class SecurityFixesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.cashier = User.objects.create_user("cashier", password="pw12345!")
        cls.owner = User.objects.create_user("owner", password="pw12345!", is_staff=True)
        cls.admin = User.objects.create_superuser("admin", "a@x.com", "pw12345!")
        cls.cat = Category.objects.create(name="Food")
        cls.product = Product.objects.create(category=cls.cat, name="Rice", price=Decimal("100"), stock=10)

    # -- search --------------------------------------------------------
    def test_search_requires_login(self):
        r = self.client.get(reverse("global_search"), {"q": "rice"})
        self.assertEqual(r.status_code, 401)
        self.assertNotIn("Rice", r.content.decode())

    def test_search_works_when_logged_in(self):
        self.client.login(username="cashier", password="pw12345!")
        r = self.client.get(reverse("global_search"), {"q": "rice"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["products"][0]["name"], "Rice")

    # -- registration --------------------------------------------------
    def test_register_is_not_public(self):
        data = {"username": "evil", "email": "e@x.com", "password1": "Str0ngPass!9", "password2": "Str0ngPass!9"}
        self.client.post(reverse("register"), data)
        self.assertFalse(User.objects.filter(username="evil").exists())

    def test_cashier_cannot_register_users(self):
        self.client.login(username="cashier", password="pw12345!")
        data = {"username": "evil2", "email": "e@x.com", "password1": "Str0ngPass!9", "password2": "Str0ngPass!9"}
        self.client.post(reverse("register"), data)
        self.assertFalse(User.objects.filter(username="evil2").exists())

    def test_superuser_can_register_users(self):
        self.client.login(username="admin", password="pw12345!")
        data = {"username": "newcashier", "email": "n@x.com", "password1": "Str0ngPass!9", "password2": "Str0ngPass!9"}
        self.client.post(reverse("register"), data)
        u = User.objects.get(username="newcashier")
        self.assertFalse(u.is_staff)

    # -- staff-only pages ---------------------------------------------
    def test_cashier_gets_403_on_expenses_and_reports(self):
        self.client.login(username="cashier", password="pw12345!")
        for name in ["expense_list", "expense_category_list", "sales_report", "expense_export_csv", "export_sales_csv"]:
            self.assertEqual(self.client.get(reverse(name)).status_code, 403, name)

    def test_staff_can_open_expenses_and_reports(self):
        self.client.login(username="owner", password="pw12345!")
        for name in ["expense_list", "sales_report"]:
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)

    # -- deletes -------------------------------------------------------
    def test_expense_delete_rejects_get_and_works_with_post(self):
        c = ExpenseCategory.objects.create(name="Rent")
        e = Expense.objects.create(title="June rent", category=c, amount=Decimal("500"))
        self.client.login(username="owner", password="pw12345!")
        self.assertEqual(self.client.get(reverse("expense_delete", args=[e.id])).status_code, 405)
        self.assertTrue(Expense.objects.filter(id=e.id).exists())
        self.client.post(reverse("expense_delete", args=[e.id]))
        self.assertFalse(Expense.objects.filter(id=e.id).exists())

    def test_cashier_cannot_post_delete_expense(self):
        c = ExpenseCategory.objects.create(name="Rent")
        e = Expense.objects.create(title="June rent", category=c, amount=Decimal("500"))
        self.client.login(username="cashier", password="pw12345!")
        self.assertEqual(self.client.post(reverse("expense_delete", args=[e.id])).status_code, 403)
        self.assertTrue(Expense.objects.filter(id=e.id).exists())

    # -- history protection -------------------------------------------
    def _sell(self):
        inv = Invoice.objects.create(created_by=self.cashier, invoice_number="INV-T1",
                                     subtotal=Decimal("100"), total=Decimal("100"))
        InvoiceItem.objects.create(invoice=inv, product=self.product, quantity=1,
                                   price=Decimal("100"), total=Decimal("100"))
        return inv

    def test_product_with_sales_is_hidden_not_deleted(self):
        inv = self._sell()
        self.client.login(username="owner", password="pw12345!")
        r = self.client.post(reverse("delete_product", args=[self.product.id]))
        self.assertEqual(r.status_code, 302)
        self.product.refresh_from_db()
        self.assertFalse(self.product.is_available)
        self.assertEqual(inv.items.count(), 1)

    def test_product_without_sales_is_deleted(self):
        self.client.login(username="owner", password="pw12345!")
        self.client.post(reverse("delete_product", args=[self.product.id]))
        self.assertFalse(Product.objects.filter(id=self.product.id).exists())

    def test_category_with_products_cannot_be_deleted(self):
        self.client.login(username="owner", password="pw12345!")
        r = self.client.post(reverse("delete_category", args=[self.cat.id]))
        self.assertEqual(r.status_code, 302)
        self.assertTrue(Category.objects.filter(id=self.cat.id).exists())
        self.assertTrue(Product.objects.filter(id=self.product.id).exists())

    def test_cashier_cannot_delete_inventory(self):
        self.client.login(username="cashier", password="pw12345!")
        response = self.client.post(reverse("delete_product", args=[self.product.id]))
        self.assertEqual(response.status_code, 403)
        self.assertTrue(Product.objects.filter(id=self.product.id).exists())

    def test_empty_category_can_be_deleted(self):
        empty = Category.objects.create(name="Empty")
        self.client.login(username="owner", password="pw12345!")
        self.client.post(reverse("delete_category", args=[empty.id]))
        self.assertFalse(Category.objects.filter(id=empty.id).exists())