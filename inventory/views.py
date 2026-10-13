import logging
from decimal import Decimal, InvalidOperation
from django.shortcuts import get_object_or_404, redirect, render
from django.db.models import ProtectedError, Sum, Q
from django.http import JsonResponse

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from core.permissions import staff_required
from django.views.decorators.http import require_POST

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

from billing.models import Customer

def global_search(request):

    # JSON endpoint called from JavaScript, so answer 401 instead of
    # redirecting to the HTML login page.
    if not request.user.is_authenticated:
        return JsonResponse({"error": "login required"}, status=401)

    query = request.GET.get("q", "").strip()


    if not query:

        return JsonResponse({
            "products": [],
            "customers": []
        })



    products = Product.objects.filter(

        Q(name__icontains=query)
        |
        Q(barcode__icontains=query)

    )[:5]



    customers = Customer.objects.filter(

        Q(name__icontains=query)
        |
        Q(phone__icontains=query)

    )[:5]



    return JsonResponse({

        "products":[

            {
                "id": product.id,
                "name": product.name,
                "barcode": product.barcode,
                "stock": product.stock,
            }

            for product in products

        ],


        "customers":[

            {
                "id": customer.id,
                "name": customer.name,
                "phone": customer.phone,
            }

            for customer in customers

        ]

    })




@staff_required
def add_categories(request):
    if request.method == "POST":
        name = request.POST.get("name")
        description = request.POST.get("description")

        Category.objects.create(name=name, description=description)
        messages.success(request, "Category Added Successfully")
        return redirect("category")

    return render(request, "inventory/add_categories.html")



@staff_required
def update_categories(request, id):
    category = get_object_or_404(Category, id=id)

    if request.method == "POST":
        category.name = request.POST.get("name", category.name)
        category.description = request.POST.get("description", category.description)
        category.save()
        messages.success(request, "Category Updated Successfully")
        return redirect("category")

    context = {"category": category}
    return render(request, "inventory/update_categories.html", context)



@staff_required
@require_POST
def delete_category(request, id):
    category = get_object_or_404(Category, id=id)

    try:
        category.delete()
    except ProtectedError:
        messages.error(
            request,
            "This category still has products. Move or remove them first.",
        )
        return redirect('category')

    messages.success(request, "Deleted successfully")
    return redirect('category')


@staff_required
def category_list(request):
    categories = Category.objects.all().order_by("name")

    return render(
        request,
        "inventory/categories.html",
        {
            "categories": categories,
        },
    )



@staff_required
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
                errors.append(
                    "That category no longer exists."
                )


        if errors:

            for err in errors:
                messages.error(request, err)

            return render(
                request,
                "inventory/add_product.html",
                {
                    "categories": categories,
                    "form_data": request.POST,
                    "selected_category": request.POST.get("category","")
                },
            )


        Product.objects.create(
            name=cleaned["name"],
            description=cleaned["description"],
            price=cleaned["price"],
            stock=cleaned["stock"],
            image=image,
            category=category,
            barcode=request.POST.get("barcode") or None,
        )


        messages.success(
            request,
            "Product Added Successfully"
        )

        return redirect("view_product")


    return render(
        request,
        "inventory/add_product.html",
        {
            "categories": categories,
            "form_data": request.POST,
            "selected_category": request.POST.get("category"),
        }
    )



@staff_required
def product_list(request):
    products = Product.objects.all().order_by("-id")

    total_products = products.count()

    in_stock = products.filter(
        stock__gt=0
    ).count()

    out_of_stock = products.filter(
        stock__lte=0
    ).count()

    total_stock = products.aggregate(
        total=Sum("stock")
    )["total"] or 0

    context = {
        "products": products,
        "total_products": total_products,
        "in_stock": in_stock,
        "out_of_stock": out_of_stock,
        "total_stock": total_stock,
    }

    return render(
        request,
        "inventory/products.html",
        context,
    )



@staff_required
def product_detail(request, id):
    product = get_object_or_404(Product, id=id)

    return render(
        request,
        "inventory/product_detail.html",
        {
            "product": product,
        },
    )


    

@staff_required
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





@staff_required
@require_POST
def delete_product(request, id):
    product = get_object_or_404(Product, id=id)

    try:
        product.delete()
    except ProtectedError:
        # The product appears on past invoices/sales. Deleting it would
        # break that history, so retire it instead.
        product.is_available = False
        product.save(update_fields=["is_available"])
        messages.info(
            request,
            "Product has sales history, so it was hidden instead of deleted.",
        )
        return redirect('view_product')

    messages.success(request, "Product deleted successfully")
    return redirect('view_product')