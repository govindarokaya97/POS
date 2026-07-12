from django.shortcuts import render, redirect, get_object_or_404
from .models import Category, Product
from django.contrib import messages

# Create your views here.


def categories(request):
    return render(request, "inventory/categories.html")


def add_categories(request):
    if request.method == "POST":
        name = request.POST.get("name")
        description = request.POST.get("description")

        Category.objects.create(name=name, description=description)
        messages.success(request, "Category Added Successfully")
        return redirect("category")

    return render(request, "inventory/add_categories.html")


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



def view_categories(request):
    categories = Category.objects.all()
    context={"categories": categories}

    return render(request, "inventory/view_categories.html", context)

def products(request):
    return render(request, "inventory/products.html")

def add_products(request):
    categories = Category.objects.all()

    if request.method=="POST":
        name=reqest.POST.get('name')
        description=request.POST.get('description')
        price=request.POST.get('price')
        stock=request.POST.get('stock')

        category_id=request.POST.get('category')

        image=request.POST.get('image')

        category=Category.objects.get(id=category_id)

        product.objects.create(
            name=name,
            description=description,
            price=price,
            stock=stock,
            image=image,
            category=category,
        )

        messages.success(request,"Product Added Successfully")
        return redirect("view-products")
        
    context = {
        "categories":categories,
    }
    return render(request, "inventory/add_products.html", context)

def view_product(request):
    products = Product.objects.all()

    context={
        "products": products,
    }
   
    return render(request, "inventory/view_product.html",context)
