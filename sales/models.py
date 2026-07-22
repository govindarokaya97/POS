from django.db import models
from django.contrib.auth.models import User
from inventory.models import Product


class Sale(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    sold_by = models.ForeignKey(User, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField()
    total_price = models.DecimalField(max_digits=10, decimal_places=2)
    sold_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.product.name} ({self.quantity})"
