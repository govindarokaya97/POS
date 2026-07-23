import logging
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from .models import Category, Product

logger = logging.getLogger(__name__)


def _parse_product_fields(post):
    """Validates and converts the raw POST data for a product form.

    Returns (cleaned_dict, errors_list). Never raises -- callers just
    check whether errors_list is empty.
    """
    errors = []
    cleaned = {}

    name = (post.get("name") or "").strip()
    if not name:
        errors.append("Name is required.")
    cleaned["name"] = name

    cleaned["description"] = post.get("description", "")

    try:
        price = Decimal(post.get("price", ""))
        if price < 0:
            errors.append("Price cannot be negative.")
    except (InvalidOperation, TypeError):
        errors.append("Price must be a valid number.")
        price = None
    cleaned["price"] = price

    try:
        stock = int(post.get("stock", ""))
        if stock < 0:
            errors.append("Stock cannot be negative.")
    except (TypeError, ValueError):
        errors.append("Stock must be a whole number.")
        stock = None
    cleaned["stock"] = stock

    return cleaned, errors


# Create your views here.



@login_required
def categories(request):
    return render(request, "inventory/categories.html")



@login_required
def add_categories(request):
    if request.method == "POST":
        name = request.POST.get("name")
        description = request.POST.get("description")

        Category.objects.create(name=name, description=description)
        messages.success(request, "Category Added Successfully")
        return redirect("category")

    return render(request, "inventory/add_categories.html")



@login_required
def update_categories(request, id):
    category = get_object_or_404(Category, id=id)

    if request.method == "POST":
        category.name = request.POST.get("name", category.name)
        category.description = request.POST.get("description", category.description)
        category.save()
        messages.success(request, "Category Updated Successfully")
        return redirect("view_category")

    context = {"category": category}
    return render(request, "inventory/update_categories.html", context)



@login_required
def delete_category(request, id):
    category = get_object_or_404(Category, id=id)
    category.delete()
    messages.success(request, "Deleted successfully")
    return redirect('view_category')



@login_required
def view_categories(request):
    categories = Category.objects.all()
    context={"categories": categories}

    return render(request, "inventory/view_categories.html", context)




@login_required
def products(request):
    return render(request, "inventory/products.html")



@login_required
def add_product(request):
    categories = Category.objects.all()

    if request.method == "POST":
        category_id = request.POST.get("category")
        image = request.FILES.get("image")

        cleaned, errors = _parse_product_fields(request.POST)

        category = None
        if not category_id:
            errors.append("Please choose a category.")
        else:
            try:
                category = Category.objects.get(id=category_id)
            except Category.DoesNotExist:
                errors.append("That category no longer exists. Please choose another.")

        if errors:
            for err in errors:
                messages.error(request, err)
            return render(
                request,
                "inventory/add_product.html",
                {"categories": categories, "form_data": request.POST},
            )

        try:
            Product.objects.create(
                name=cleaned["name"],
                description=cleaned["description"],
                price=cleaned["price"],
                stock=cleaned["stock"],
                image=image,
                category=category,
            )
        except Exception:
            logger.exception("Unexpected error creating product (category_id=%s)", category_id)
            messages.error(request, "Something went wrong saving the product. Please try again.")
            return render(
                request,
                "inventory/add_product.html",
                {"categories": categories, "form_data": request.POST},
            )

        messages.success(request, "Product Added Successfully")
        return redirect("view_product")

    context = {
        "categories": categories,
    }
    return render(request, "inventory/add_product.html", context)




@login_required
def view_product(request):
    products = Product.objects.all()

    context={
        "products": products,
    }
   
    return render(request, "inventory/view_product.html",context)




@login_required
def update_product(request, id):
    product = get_object_or_404(Product, id=id)
    categories = Category.objects.all()

    if request.method == "POST":
        category_id = request.POST.get("category")
        image = request.FILES.get("image")

        cleaned, errors = _parse_product_fields(request.POST)

        category = None
        if not category_id:
            errors.append("Please choose a category.")
        else:
            try:
                category = Category.objects.get(id=category_id)
            except Category.DoesNotExist:
                errors.append("That category no longer exists. Please choose another.")

        if errors:
            for err in errors:
                messages.error(request, err)
            return render(
                request,
                "inventory/update_product.html",
                {"categories": categories, "product": product},
            )

        try:
            product.name = cleaned["name"]
            product.description = cleaned["description"]
            product.price = cleaned["price"]
            product.stock = cleaned["stock"]
            product.category = category
            if image:
                product.image = image
            product.save()
        except Exception:
            logger.exception("Unexpected error updating product %s", id)
            messages.error(request, "Something went wrong saving the product. Please try again.")
            return render(
                request,
                "inventory/update_product.html",
                {"categories": categories, "product": product},
            )

        messages.success(request, "Product Updated Successfully")
        return redirect("view_product")

    context = {
        "categories": categories,
        "product": product,
    }

    return render(request, "inventory/update_product.html", context)





@login_required
def delete_product(request, id):
    product=get_object_or_404(Product, id=id)
    product.delete()
    messages.success(request, "Product daleted successfully")
    return redirect('view_product')

