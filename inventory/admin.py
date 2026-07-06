from django.contrib import admin
from .models import Category, Product

# Register your models here.

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', )
    search_fields = ('name',)
    ordering = ('name',)

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'price', 'stock', 'is_available', 'created_at', 'updated_at')
    list_filter = ('category', 'is_available', 'created_at', 'updated_at')
    search_fields = ('name', 'description')
    ordering = ('name',)
    list_per_page = 20