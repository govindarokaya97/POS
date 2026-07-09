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

