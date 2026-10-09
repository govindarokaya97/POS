
from django.db import models
from django.contrib.auth.models import User
from inventory.models import Product



class Customer(models.Model):

    name = models.CharField(
        max_length=100
    )

    phone = models.CharField(
        max_length=20,
        blank=True
    )

    email = models.EmailField(
        blank=True
    )

    address = models.TextField(
        blank=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )


    def __str__(self):
        return self.name



class Invoice(models.Model):

    PAYMENT_METHODS = (

        ("cash","Cash"),

        ("card","Card"),

        ("esewa","eSewa"),

        ("khalti","Khalti"),

    )


    invoice_number = models.CharField(
        max_length=50,
        unique=True
    )


    customer = models.ForeignKey(
        Customer,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )


    created_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE
    )


    PAYMENT_STATUS = (

        ("paid", "Paid"),

        ("partial", "Partial"),

        ("due", "Due"),

    )

    subtotal = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
    )

    discount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
    )

    tax = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
    )

    vat = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
    )

    total = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
    )

    paid_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
    )

    due_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
    )

    return_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0
    )

    payment_status = models.CharField(
        max_length=20,
        default="due",
    )

    payment_method = models.CharField(
        max_length=20,
        default="cash",
    )



    created_at=models.DateTimeField(
        auto_now_add=True
    )



    def __str__(self):
        return self.invoice_number





class InvoiceItem(models.Model):

    invoice=models.ForeignKey(
        Invoice,
        related_name="items",
        on_delete=models.CASCADE
    )


    product=models.ForeignKey(
        Product,
        on_delete=models.CASCADE
    )


    quantity=models.PositiveIntegerField()


    price=models.DecimalField(
        max_digits=10,
        decimal_places=2
    )


    total=models.DecimalField(
        max_digits=10,
        decimal_places=2
    )



    def __str__(self):
        return self.product.name
    


class ExpenseCategory(models.Model):

    GROUP_CHOICES = [

        ("cinema", "Cinema Hall"),

        ("canteen", "Canteen"),

        ("general", "General"),

    ]


    name = models.CharField(
        max_length=100
    )


    group = models.CharField(
        max_length=20,
        choices=GROUP_CHOICES,
        default="general"
    )


    created_at = models.DateTimeField(
        auto_now_add=True
    )


    class Meta:

        ordering = [
            "group",
            "name"
        ]


    def __str__(self):

        return self.name





class Expense(models.Model):


    title = models.CharField(
        max_length=100
    )

    category = models.ForeignKey(
        ExpenseCategory,
        on_delete=models.PROTECT,
        related_name="expenses"
    )



    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )


    description = models.TextField(
        blank=True
    )


    created_at = models.DateTimeField(
        auto_now_add=True
    )


    def __str__(self):

        return self.title

    

class ShopSetting(models.Model):

    shop_name = models.CharField(
        max_length=100,
        default="MY SHOP"
    )


    address = models.TextField(
        blank=True
    )


    phone = models.CharField(
        max_length=20,
        blank=True
    )


    email = models.EmailField(
        blank=True
    )


    vat_number = models.CharField(
        max_length=50,
        blank=True
    )


    logo = models.ImageField(
        upload_to="shop/",
        blank=True,
        null=True
    )


    footer_message = models.CharField(
        max_length=200,
        default="Thank You! Visit Again"
    )


    updated_at = models.DateTimeField(
        auto_now=True
    )


    def __str__(self):

        return self.shop_name

