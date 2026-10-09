from django.contrib import admin
from .models import Customer,Invoice,InvoiceItem, Expense,ExpenseCategory, ShopSetting



@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):

    list_display = (
        "name",
        "phone",
        "email",
        "created_at",
    )


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):

    list_display = (
        "invoice_number",
        "created_at",
        "customer",
        "total",
        "paid_amount",
        "due_amount",
        "payment_status",
    )

    list_filter = (
        "payment_status",
        "payment_method",
        "created_at",
    )

    search_fields = (
        "invoice_number",
        "customer__name",
        "customer__phone",
    )

    ordering = (
        "-created_at",
    )



@admin.register(InvoiceItem)
class InvoiceItemAdmin(admin.ModelAdmin):

    list_display = (
        "invoice",
        "product",
        "quantity",
        "price",
        "total",
    )




@admin.register(ExpenseCategory)
class ExpenseCategoryAdmin(admin.ModelAdmin):

    list_display = (
        "name",
        "group",
        "created_at",
    )

    list_filter = (
        "group",
    )

    search_fields = (
        "name",
    )



@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):

    list_display = (
        "title",
        "category",
        "amount",
        "created_at",
    )


    list_filter = (
        "category__group",
        "category",
        "created_at",
    )


    search_fields = (
        "title",
        "category__name",
        "description",
    )


    ordering = (
        "-created_at",
    )

    
@admin.register(ShopSetting)
class ShopSettingAdmin(admin.ModelAdmin):

    list_display = (
        "shop_name",
        "phone",
        "vat_number",
    )


    