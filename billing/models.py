
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


    subtotal = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )


    discount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )


    tax = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )


    paid_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )


    due_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )


    PAYMENT_STATUS = (

        ("paid", "Paid"),

        ("partial", "Partial"),

        ("due", "Due"),

    )


    payment_status = models.CharField(
        max_length=20,
        choices=PAYMENT_STATUS,
        default="due"
    )


    total = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )


    payment_method = models.CharField(
        max_length=20,
        choices=PAYMENT_METHODS,
        default="cash"
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
    



class Expense(models.Model):

    EXPENSE_TYPES = (

        ("rent", "Rent"),

        ("salary", "Salary"),

        ("electricity", "Electricity"),

        ("supplier", "Supplier"),

        ("other", "Other"),

    )


    title = models.CharField(
        max_length=100
    )


    expense_type = models.CharField(
        max_length=20,
        choices=EXPENSE_TYPES,
        default="other"
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