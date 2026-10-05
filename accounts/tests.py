from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse


class LogoutTests(TestCase):
    def setUp(self):
        User.objects.create_user("owner", password="pw-12345")
        self.client.login(username="owner", password="pw-12345")

    def test_get_does_not_log_out(self):
        self.assertEqual(self.client.get(reverse("logout")).status_code, 405)
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 200)

    def test_post_logs_out(self):
        response = self.client.post(reverse("logout"))
        self.assertRedirects(response, reverse("login"))
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 302)

    def test_sidebar_logout_is_a_post_form(self):
        html = self.client.get(reverse("dashboard")).content.decode()
        self.assertNotIn('href="/user/logout"', html)
        self.assertIn('action="/user/logout"', html)