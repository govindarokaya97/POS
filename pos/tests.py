from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse


class HomeAndManagementNavigationTests(TestCase):
    def setUp(self):
        self.cashier = User.objects.create_user("cashier", password="pw-12345")
        self.manager = User.objects.create_user("manager", password="pw-12345", is_staff=True)
        self.admin = User.objects.create_superuser("admin", "admin@example.com", "pw-12345")

    def test_home_has_exactly_two_primary_destinations(self):
        self.client.force_login(self.cashier)
        response = self.client.get(reverse("pos_home"))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn(reverse("billing_products"), html)
        self.assertNotIn(reverse("management_home"), html)
        self.assertIn("POS &amp; Checkout", html)
        self.assertIn("Management", html)
        self.assertNotIn("Start Selling", html)

    def test_cashier_cannot_open_management_hub(self):
        self.client.force_login(self.cashier)
        self.assertEqual(self.client.get(reverse("management_home")).status_code, 403)

    def test_staff_can_open_management_hub_with_core_sections(self):
        self.client.force_login(self.manager)
        response = self.client.get(reverse("management_home"))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        for label in ("Inventory", "Billing &amp; Finance", "Reports", "Customers", "Expenses"):
            with self.subTest(section=label):
                self.assertIn(label, html)
        self.assertIn("Users &amp; Security", html)
        self.assertIn("User administration is restricted to superusers", html)
        self.assertNotIn(reverse("admin:index"), html)

    def test_superuser_sees_users_and_security_entry(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("management_home"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("Users &amp; Security", response.content.decode())

    def test_inventory_management_routes_are_staff_only(self):
        self.client.force_login(self.cashier)
        for route in ("view_product", "category"):
            with self.subTest(route=route):
                self.assertEqual(self.client.get(reverse(route)).status_code, 403)
        self.client.force_login(self.manager)
        for route in ("view_product", "category"):
            with self.subTest(route=route, role="staff"):
                self.assertEqual(self.client.get(reverse(route)).status_code, 200)

    def test_pos_remains_available_to_cashiers(self):
        self.client.force_login(self.cashier)
        self.assertEqual(self.client.get(reverse("billing_products")).status_code, 200)
