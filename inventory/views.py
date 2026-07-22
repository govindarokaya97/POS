from django.shortcuts import render, redirect, get_object_or_404
from .models import Category, Product
from django.contrib import messages
from django.contrib.auth.decorators import login_required


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

    if request.method=="POST":
        name=request.POST.get('name')
        description=request.POST.get('description')
        price=request.POST.get('price')
        stock=request.POST.get('stock')

        category_id=request.POST.get('category')

        image=request.FILES.get('image')

        category=Category.objects.get(id=category_id)

        Product.objects.create(
            name=name,
            description=description,
            price=price,
            stock=stock,
            image=image,
            category=category,
        )

        messages.success(request,"Product Added Successfully")
        return redirect("view_product")
        
    context = {
        "categories":categories,
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

    if request.method=="POST":
        product.name=request.POST.get('name')
        product.description=request.POST.get('description')
        product.price=request.POST.get('price')
        product.stock=request.POST.get('stock')
        
        image=request.FILES.get('image')
        category_id=request.POST.get('category')

        product.category=Category.objects.get(id=category_id)
        if image:
            product.image=image
        
        product.save()

        messages.success(request,"Product Updated Successfully")
        return redirect('view_product')


    context={
        "categories":categories,
        "product":product,
    }

    return render(request, "inventory/update_product.html", context)





@login_required
def delete_product(request, id):
    product=get_object_or_404(Product, id=id)
    product.delete()
    messages.success(request, "Product daleted successfully")
    return redirect('view_product')

