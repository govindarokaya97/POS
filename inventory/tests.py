from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from .models import Category, Product


class DeleteRequiresPostTests(TestCase):
    def setUp(self):
        User.objects.create_user("owner", password="pw-12345")
        self.client.login(username="owner", password="pw-12345")
        self.category = Category.objects.create(name="General")
        self.product = Product.objects.create(
            category=self.category, name="Pen", price=1, stock=1
        )

    def test_get_does_not_delete(self):
        for name, obj in [("delete_product", self.product), ("delete_category", self.category)]:
            with self.subTest(name=name):
                response = self.client.get(reverse(name, args=[obj.id]))
                self.assertEqual(response.status_code, 405)
        self.assertTrue(Product.objects.filter(id=self.product.id).exists())
        self.assertTrue(Category.objects.filter(id=self.category.id).exists())

    def test_post_deletes_product(self):
        response = self.client.post(reverse("delete_product", args=[self.product.id]))
        self.assertRedirects(response, reverse("view_product"))
        self.assertFalse(Product.objects.filter(id=self.product.id).exists())

    def test_anonymous_cannot_delete(self):
        self.client.logout()
        response = self.client.post(reverse("delete_product", args=[self.product.id]))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Product.objects.filter(id=self.product.id).exists())

    def test_delete_forms_carry_csrf_tokens(self):
        client = Client(enforce_csrf_checks=True)
        client.login(username="owner", password="pw-12345")
        html = client.get(reverse("view_product")).content.decode()
        self.assertNotIn(f'href="/inventory/product/delete/{self.product.id}"', html)
        self.assertIn("csrfmiddlewaretoken", html)
        html = client.get(reverse("view_category")).content.decode()
        self.assertNotIn(f'href="/inventory/category/delete/{self.category.id}"', html)
        self.assertIn("csrfmiddlewaretoken", html)