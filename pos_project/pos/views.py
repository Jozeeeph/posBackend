from decimal import Decimal
from django.forms import ValidationError
from django.shortcuts import render
import json
from django.http import JsonResponse, HttpResponseNotAllowed
from django.views.decorators.csrf import csrf_exempt
from .models import Product, Category, SubCategory, Variant
from django.forms.models import model_to_dict


# Create your views here.

#Product
@csrf_exempt
def createProduct(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)

            # Required fields
            designation = data["designation"]
            prix_ht = Decimal(data["prix_ht"])
            taxe = Decimal(data["taxe"])
            marge = Decimal(data["marge"])
            category_id = data["category"]

            # Optional fields
            stock = data.get("stock", 0)
            code = data.get("code")
            description = data.get("description")
            date_expiration = data.get("date_expiration")
            sub_category_id = data.get("sub_category")
            remise_max = Decimal(data.get("remise_max", 0))
            remise_valeur_max = Decimal(data.get("remise_valeur_max", 0))
            has_variants = data.get("has_variants", False)
            sellable = data.get("sellable", True)
            status = data.get("status", "in_stock")
            brand = data.get("brand")
            prix_ttc = Decimal(data.get("prix_ttc", prix_ht * (1 + taxe / 100)))
            variants = data.get("variants", [])

            # Foreign keys
            category = Category.objects.get(id=category_id)
            sub_category = SubCategory.objects.get(id=sub_category_id) if sub_category_id else None

            # Create product
            product = Product.objects.create(
                code=code,
                designation=designation,
                description=description,
                stock=stock,
                prix_ht=prix_ht,
                taxe=taxe,
                prix_ttc=prix_ttc,
                date_expiration=date_expiration,
                category=category,
                sub_category=sub_category,
                marge=marge,
                remise_max=remise_max,
                remise_valeur_max=remise_valeur_max,
                has_variants=has_variants,
                sellable=sellable,
                status=status,
                brand=brand,
            )

            # Create variants
            created_variants = []
            for v in variants:
                variant = Variant.objects.create(
                    product=product,
                    code=v.get("code"),
                    combination_name=v["combination_name"],
                    price=Decimal(v["price"]),
                    price_impact=Decimal(v["price_impact"]),
                    stock=v["stock"],
                    default_variant=v.get("default_variant", False),
                    attributes=v.get("attributes", {})
                )
                created_variants.append(model_to_dict(variant))

            return JsonResponse({
                "message": "Product with variants created successfully.",
                "product_id": product.id,
                "variants": created_variants
            }, status=201)

        except Category.DoesNotExist:
            return JsonResponse({"error": "Category not found."}, status=404)
        except SubCategory.DoesNotExist:
            return JsonResponse({"error": "SubCategory not found."}, status=404)
        except KeyError as e:
            return JsonResponse({"error": f"Missing field: {str(e)}"}, status=400)
        except ValidationError as e:
            return JsonResponse({"error": e.message_dict}, status=400)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)

    return HttpResponseNotAllowed(['POST'])

@csrf_exempt
def import_products(request):
    if request.method != "POST":
        return JsonResponse({"error": "Only POST method is allowed"}, status=405)
    
    try:
        data = json.loads(request.body)
        products_data = data.get('products', [])
        
        created_products = 0
        created_variants = 0
        errors = []
        
        for product_data in products_data:
            try:
                # Extract product info with defaults
                code = product_data.get('code', '').strip()
                designation = product_data.get('designation', '').strip()
                if not designation:
                    raise ValidationError("Product name is required")
                
                # Handle category - take first category if multiple
                category_name = (product_data.get('category_name', 'Default')
                               .split(',')[0]
                               .strip())
                category, _ = Category.objects.get_or_create(
                    name=category_name,
                    defaults={'image_path': product_data.get('image', '')}
                )
                
                # Handle subcategory - use category name + "Default" if not specified
                sub_category_name = "Default"
                if '>' in category_name:
                    main_cat, sub_cat = category_name.split('>', 1)
                    sub_category_name = sub_cat.split(',')[0].strip()
                
                sub_category, _ = SubCategory.objects.get_or_create(
                    name=sub_category_name,
                    category=category,
                    defaults={'parent': None}
                )
                
                # Convert prices safely
                def safe_decimal(value, default=0):
                    try:
                        return Decimal(str(value))
                    except:
                        return Decimal(default)
                
                prix_ht = safe_decimal(product_data.get('prixHT'))
                cost_price = safe_decimal(product_data.get('cost_price'))
                taxe = safe_decimal(product_data.get('taxe'))
                prix_ttc = safe_decimal(product_data.get('prixTTC', prix_ht * (1 + taxe / 100)))
                
                # Handle stock - sum variants if product has variants
                has_variants = product_data.get('has_variants', False)
                stock = safe_decimal(product_data.get('stock', 0))
                
                # Create product
                product = Product.objects.create(
                    code=code,
                    designation=designation,
                    description=product_data.get('description', ''),
                    stock=int(stock),
                    prix_ht=prix_ht,
                    taxe=taxe,
                    prix_ttc=prix_ttc,
                    category=category,
                    sub_category=sub_category,
                    marge=prix_ht - cost_price,
                    remise_max=safe_decimal(product_data.get('remise_max', 0)),
                    remise_valeur_max=safe_decimal(product_data.get('remise_valeur_max', 0)),
                    has_variants=has_variants,
                    sellable=product_data.get('sellable', True),
                    brand=product_data.get('brand', '')[:100],  # Ensure it fits in CharField
                    image=product_data.get('image', None),
                )
                created_products += 1
                
                # Handle variants
                variants_data = product_data.get('variants', [])
                if has_variants and variants_data:
                    for variant_data in variants_data:
                        Variant.objects.create(
                            product=product,
                            combination_name=variant_data.get('combination_name', ''),
                            price=prix_ht + safe_decimal(variant_data.get('price_impact', 0)),
                            price_impact=safe_decimal(variant_data.get('price_impact', 0)),
                            stock=variant_data.get('stock', 0),
                            default_variant=variant_data.get('default_variant', False),
                            attributes=variant_data.get('attributes', {})
                        )
                        created_variants += 1
                
            except Exception as e:
                errors.append({
                    'product': product_data.get('designation', 'Unknown product'),
                    'error': str(e),
                    'code': product_data.get('code', '')
                })
                continue
        
        return JsonResponse({
            'success': True,
            'created_products': created_products,
            'created_variants': created_variants,
            'errors': errors,
            'total_attempted': len(products_data)
        }, status=201)
        
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON data'}, status=400)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)


def getProducts(request):
    if request.method == "GET":
        products = list(Product.objects.filter(is_deleted=False).values())
        return JsonResponse(products, safe=False)
    return HttpResponseNotAllowed(['GET'])


@csrf_exempt
def updateProduct(request):
    if request.method == "PUT":
        data = json.loads(request.body)
        product_id = data.get("id")
        try:
            product = Product.objects.get(id=product_id)
            for key, value in data.items():
                setattr(product, key, value)
            product.save()
            return JsonResponse(model_to_dict(product))
        except Product.DoesNotExist:
            return JsonResponse({"error": "Product not found"}, status=404)
    return HttpResponseNotAllowed(['PUT'])


@csrf_exempt
def deleteProduct(request):
    if request.method == "DELETE":
        data = json.loads(request.body)
        product_id = data.get("id")
        try:
            product = Product.objects.get(id=product_id)
            product.is_deleted = True
            product.save()
            return JsonResponse({"message": "Product soft-deleted"})
        except Product.DoesNotExist:
            return JsonResponse({"error": "Product not found"}, status=404)
    return HttpResponseNotAllowed(['DELETE'])


#Category
@csrf_exempt
def createCategory(request):
    if request.method == "POST":
        data = json.loads(request.body)
        category = Category.objects.create(**data)
        return JsonResponse(model_to_dict(category), status=201)
    return HttpResponseNotAllowed(['POST'])


def getCategories(request):
    if request.method == "GET":
        categories = list(Category.objects.all().values())
        return JsonResponse(categories, safe=False)
    return HttpResponseNotAllowed(['GET'])


@csrf_exempt
def updateCategory(request):
    if request.method == "PUT":
        data = json.loads(request.body)
        try:
            category = Category.objects.get(id=data.get("id"))
            for key, value in data.items():
                setattr(category, key, value)
            category.save()
            return JsonResponse(model_to_dict(category))
        except Category.DoesNotExist:
            return JsonResponse({"error": "Category not found"}, status=404)
    return HttpResponseNotAllowed(['PUT'])


@csrf_exempt
def deleteCategory(request):
    if request.method == "DELETE":
        data = json.loads(request.body)
        try:
            category = Category.objects.get(id=data.get("id"))
            category.delete()
            return JsonResponse({"message": "Category deleted"})
        except Category.DoesNotExist:
            return JsonResponse({"error": "Category not found"}, status=404)
    return HttpResponseNotAllowed(['DELETE'])

#SubCategory
@csrf_exempt
def createSubCategory(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            name = data.get("name")
            parent_id = data.get("parent")
            category_id = data.get("category")

            if not name or not category_id:
                return JsonResponse({"error": "Name and category are required."}, status=400)

            category = Category.objects.get(id=category_id)
            parent = SubCategory.objects.get(id=parent_id) if parent_id else None

            subcategory = SubCategory(name=name, parent=parent, category=category)
            subcategory.save()
            return JsonResponse(subcategory.to_map(), status=201)

        except Category.DoesNotExist:
            return JsonResponse({"error": "Category not found."}, status=404)
        except SubCategory.DoesNotExist:
            return JsonResponse({"error": "Parent subcategory not found."}, status=404)
        except ValidationError as e:
            return JsonResponse({"error": e.message_dict}, status=400)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)

# Get All SubCategories
def getSubCategories(request):
    if request.method == "GET":
        subcategories = SubCategory.objects.all()
        data = [sc.to_map() for sc in subcategories]
        return JsonResponse(data, safe=False, status=200)

# Update SubCategory
@csrf_exempt
def updateSubCategory(request):
    if request.method == "PUT":
        try:
            data = json.loads(request.body)
            sc_id = data.get("id")
            name = data.get("name")
            parent_id = data.get("parent")
            category_id = data.get("category")

            subcategory = SubCategory.objects.get(id=sc_id)
            if name:
                subcategory.name = name
            if parent_id is not None:
                subcategory.parent = SubCategory.objects.get(id=parent_id) if parent_id else None
            if category_id:
                subcategory.category = Category.objects.get(id=category_id)

            subcategory.save()
            return JsonResponse(subcategory.to_map(), status=200)

        except SubCategory.DoesNotExist:
            return JsonResponse({"error": "SubCategory not found."}, status=404)
        except Category.DoesNotExist:
            return JsonResponse({"error": "Category not found."}, status=404)
        except ValidationError as e:
            return JsonResponse({"error": e.message_dict}, status=400)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)

# Delete SubCategory
@csrf_exempt
def deleteSubCategory(request):
    if request.method == "DELETE":
        try:
            data = json.loads(request.body)
            sc_id = data.get("id")
            subcategory = SubCategory.objects.get(id=sc_id)
            subcategory.delete()
            return JsonResponse({"message": "SubCategory deleted successfully."}, status=200)
        except SubCategory.DoesNotExist:
            return JsonResponse({"error": "SubCategory not found."}, status=404)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)

#Variant

@csrf_exempt
def createVariant(request):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    try:
        data = json.loads(request.body)

        # Required fields
        product_id = data["product"]
        combination_name = data["combination_name"]
        price = Decimal(data["price"])
        price_impact = Decimal(data["price_impact"])
        stock = int(data["stock"])
        attributes = data.get("attributes", {})

        # Optional fields
        code = data.get("code")
        default_variant = data.get("default_variant", False)

        # Foreign key validation
        product = Product.objects.get(id=product_id)

        variant = Variant.objects.create(
            product=product,
            code=code,
            combination_name=combination_name,
            price=price,
            price_impact=price_impact,
            stock=stock,
            default_variant=default_variant,
            attributes=attributes,
        )

        return JsonResponse(model_to_dict(variant), status=201)

    except Product.DoesNotExist:
        return JsonResponse({"error": "Product not found."}, status=404)
    except KeyError as e:
        return JsonResponse({"error": f"Missing field: {str(e)}"}, status=400)
    except ValueError:
        return JsonResponse({"error": "Invalid data type for a field."}, status=400)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

def getVariants(request):
    if request.method == "GET":
        variants = list(Variant.objects.all().values())
        return JsonResponse(variants, safe=False)
    return HttpResponseNotAllowed(['GET'])


@csrf_exempt
def updateVariant(request):
    if request.method == "PUT":
        data = json.loads(request.body)
        try:
            variant = Variant.objects.get(id=data.get("id"))
            for key, value in data.items():
                setattr(variant, key, value)
            variant.save()
            return JsonResponse(model_to_dict(variant))
        except Variant.DoesNotExist:
            return JsonResponse({"error": "Variant not found"}, status=404)
    return HttpResponseNotAllowed(['PUT'])


@csrf_exempt
def deleteVariant(request):
    if request.method == "DELETE":
        data = json.loads(request.body)
        try:
            variant = Variant.objects.get(id=data.get("id"))
            variant.delete()
            return JsonResponse({"message": "Variant deleted"})
        except Variant.DoesNotExist:
            return JsonResponse({"error": "Variant not found"}, status=404)
    return HttpResponseNotAllowed(['DELETE'])
