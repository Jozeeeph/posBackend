from decimal import Decimal
from django.forms import ValidationError
from django.shortcuts import render
import json
from django.http import HttpResponseBadRequest, JsonResponse, HttpResponseNotAllowed
from django.views.decorators.csrf import csrf_exempt
from .models import Product, Category, StockItem, SubCategory, Variant, Warehouse
from django.forms.models import model_to_dict
from django.utils.text import slugify
from django.middleware.csrf import get_token
# Create your views here.
from django.db import transaction
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from decimal import Decimal
import json
from .models import Product, Variant, Category, SubCategory

from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse, HttpResponseNotAllowed
from django.forms.models import model_to_dict
import json
from decimal import Decimal
from django.core.exceptions import ValidationError

from datetime import datetime
from django.utils.text import slugify

def get_csrf_token(request):
    return JsonResponse({'csrfToken': get_token(request)})

#Product
@csrf_exempt
def createProduct(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)

            # Vérification des champs requis
            required_fields = ['designation', 'prix_ht', 'taxe', 'marge', 'category_name']
            for field in required_fields:
                if field not in data:
                    return JsonResponse({"error": f"Missing required field: {field}"}, status=400)

            designation = data["designation"]
            prix_ht = Decimal(str(data["prix_ht"]))
            taxe = Decimal(str(data["taxe"]))
            marge = Decimal(str(data["marge"]))
            category_name = data["category_name"]

            stock = int(data.get("stock", 0))
            code = data.get("code")
            description = data.get("description", "")
            date_expiration_str = data.get("date_expiration")
            date_expiration = None
            if date_expiration_str:
                date_expiration = datetime.strptime(date_expiration_str, "%Y-%m-%d").date()
            
            sub_category_name = data.get("sub_category_name")
            remise_max = Decimal(str(data.get("remise_max", 0)))
            remise_valeur_max = Decimal(str(data.get("remise_valeur_max", 0)))
            has_variants = bool(data.get("has_variants", False))
            sellable = bool(data.get("sellable", True))
            status = data.get("status", "in_stock")
            brand = data.get("brand", "")
            image_path = data.get("image_path", "")
            variants = data.get("variants", [])
        
            category, _ = Category.objects.get_or_create(
                name=category_name,
                defaults={'image_path': image_path or f"categories/{slugify(category_name)}.jpg"}
            )

            sub_category = None
            if sub_category_name:
                sub_category, _ = SubCategory.objects.get_or_create(
                    name=sub_category_name,
                    category=category
                )

            product = Product(
                code=code,
                designation=designation,
                description=description,
                stock=stock,
                prix_ht=prix_ht,
                taxe=taxe,
                prix_ttc=prix_ht * (1 + taxe / 100),
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
                is_deleted=0
            )
            
            product.full_clean()
            product.save()  # First save to get the primary key
            
            # Now update the ID-based fields
            product.category_id_backend = category.id
            product.category_name = category.name
            if sub_category:
                product.sub_category_id_backend = sub_category.id
                product.sub_category_name = sub_category.name
            product.save()  # Second save with updated fields

            created_variants = []
            if has_variants:
                for variant_data in variants:
                    variant = Variant(
                        product=product,
                        code=variant_data.get("code"),
                        combination_name=variant_data["combination_name"],
                        price=Decimal(str(variant_data["price"])),
                        price_impact=Decimal(str(variant_data["price_impact"])),
                        stock=int(variant_data["stock"]),
                        default_variant=bool(variant_data.get("default_variant", False)),
                        attributes=variant_data.get("attributes", {})
                    )
                    variant.full_clean()
                    variant.save()
                    created_variants.append(model_to_dict(variant))
                
                # Update product with variant information
                default_variant = product.variants.filter(default_variant=True).first()
                if default_variant:
                    product.prix_ttc = default_variant.final_price
                    product.prix_ht = default_variant.price
                    product.taxe = ((product.prix_ttc / product.prix_ht) - 1) * 100 if product.prix_ht else 0
                product.code = None
                product.stock = 0
                product.save()

            product_dict = model_to_dict(product)
            if hasattr(product, 'image') and product.image:
                product_dict['image'] = product.image.url
            else:
                product_dict['image'] = None

            return JsonResponse({
                "success": True,
                "product": product_dict,
                "variants": created_variants
            }, status=201)

        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON data"}, status=400)
        except KeyError as e:
            return JsonResponse({"error": f"Missing required field: {str(e)}"}, status=400)
        except ValidationError as e:
            return JsonResponse({"error": "Validation error", "details": str(e)}, status=400)
        except Exception as e:
            return JsonResponse({"error": "Server error", "details": str(e)}, status=500)

    return HttpResponseNotAllowed(['POST'])





@csrf_exempt
def import_products(request):
    if request.method != "POST":
        return JsonResponse({"error": "Only POST method is allowed"}, status=405)

    try:
        # 1. Parse input data
        try:
            data = json.loads(request.body)
            rows_data = data.get('rows', [])
        except json.JSONDecodeError as e:
            return JsonResponse({'error': f'Invalid JSON data: {str(e)}'}, status=400)
        
        if not rows_data:
            return JsonResponse({"error": "No data provided"}, status=400)

        # 2. Group rows by product reference
        products_dict = {}
        for row in rows_data:
            ref = row.get('REFERENCE')
            if not ref:
                continue
                
            if ref not in products_dict:
                products_dict[ref] = {
                    'main_data': row,
                    'variants': []
                }
            
            # Add as variant if it's a variant row
            if row.get('SIMPLEPRODUCT') in ['FALSE', False] and row.get('VARIANTNAME'):
                products_dict[ref]['variants'].append(row)

        # 3. Initialize counters
        results = {
            'created_products': 0,
            'created_variants': 0,
            'errors': [],
            'total_attempted': len(products_dict)
        }

        # 4. Process in transaction
        with transaction.atomic():
            for index, (ref, product_data) in enumerate(products_dict.items(), start=1):
                try:
                    main_data = product_data['main_data']
                    
                    # Validate required fields
                    if not main_data.get('PRODUCTNAME'):
                        raise ValidationError("Product name is required")
                    
                    # Process category
                    category_name = main_data.get('CATEGORY', 'Default').strip()
                    category, _ = Category.objects.get_or_create(
                        name=category_name,
                        defaults={'image_path': ''}
                    )

                    # Convert numeric values
                    def to_decimal(value, default=Decimal('0')):
                        if value in [None, '']:
                            return default
                        if isinstance(value, str):
                            value = value.replace(',', '.')
                        try:
                            return Decimal(str(value))
                        except:
                            return default

                    # Create product
                    product = Product(
                        code=ref,
                        designation=main_data['PRODUCTNAME'].strip(),
                        description=main_data.get('DESCRIPTION', '').strip() or None,
                        stock=int(to_decimal(main_data.get('QUANTITY', 0))),
                        prix_ht=to_decimal(main_data.get('SELLPRICETAXEXCLUDE')),
                        taxe=to_decimal(main_data.get('VAT')),
                        prix_ttc=to_decimal(main_data.get('SELLPRICETAXINCLUDE')),
                        category=category,
                        brand=main_data.get('BRAND', '').strip()[:100] or None,
                        has_variants=main_data.get('SIMPLEPRODUCT') in ['FALSE', False],
                        sellable=main_data.get('SELLABLE') in ['TRUE', True],
                        status='in_stock',
                        image_path=main_data.get('IMAGE', '')
                    )
                    
                    product.full_clean()
                    product.save()
                    results['created_products'] += 1

                    # Handle variants
                    if product.has_variants and product_data['variants']:
                        for variant_data in product_data['variants']:
                            variant = Variant(
                                product=product,
                                combination_name=variant_data['VARIANTNAME'].strip(),
                                price=to_decimal(variant_data.get('SELLPRICETAXINCLUDE')),
                                price_impact=to_decimal(variant_data.get('IMPACTPRICE')),
                                stock=int(to_decimal(variant_data.get('QUANTITYVARIANT', 0))),
                                default_variant=variant_data.get('DEFAULTVARIANT') in ['TRUE', True],
                                image_path=variant_data.get('VARIANTIMAGE', '')
                            )
                            variant.full_clean()
                            variant.save()
                            results['created_variants'] += 1

                except Exception as e:
                    results['errors'].append({
                        'line': index,
                        'product': main_data.get('PRODUCTNAME', 'Unknown'),
                        'error': str(e)
                    })
                    continue

        return JsonResponse({'success': True, **results}, status=201)

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f"Server error: {str(e)}"
        }, status=500)
    

def getProducts(request):
    if request.method == "GET":
        try:
            products = Product.objects.filter(is_deleted=False) \
                .select_related('category') \
                .prefetch_related('variants') \
                .order_by('-created_at')

            product_list = []
            for product in products:
                data = {
                    'id': product.id,
                    'code': product.code,
                    'designation': product.designation,
                    'description': product.description,
                    'stock': product.stock,
                    'prix_ht': float(product.prix_ht),
                    'taxe': float(product.taxe),
                    'prix_ttc': float(product.prix_ttc),
                    'category_name': product.category.name if product.category else None,
                    'brand': product.brand,
                    'has_variants': product.has_variants,
                    'image_url': product.image.url if product.image else None,
                    'variants': []
                }
                if product.has_variants:
                    data['variants'] = [{
                        'id': v.id,
                        'combination_name': v.combination_name,
                        'price': float(v.price),
                        'price_impact': float(v.price_impact),
                        'stock': v.stock,
                        'default_variant': v.default_variant
                    } for v in product.variants.all()]
                product_list.append(data)

            return JsonResponse({'products': product_list})
        except Exception as e:
            return JsonResponse({'error': str(e), 'products': []}, status=500)

    return HttpResponseNotAllowed(['GET'])



@csrf_exempt
def updateProduct(request, id):
    if request.method == 'PUT':
        try:
            data = json.loads(request.body)
            product = Product.objects.get(pk=id)
            product.stock = data.get('stock', product.stock)
            product.save()
            return JsonResponse({'message': 'Stock mis à jour'})
        except Product.DoesNotExist:
            return JsonResponse({'error': 'Produit non trouvé'}, status=404)

@csrf_exempt
def deleteAllProducts(request):
    if request.method == "DELETE":
        deleted_count, _ = Product.objects.all().delete()
        return JsonResponse(
            {"message": f"Successfully deleted {deleted_count} products"},
            status=200
        )
    return HttpResponseNotAllowed(['DELETE'])

@csrf_exempt
def deleteProduct(request,id):
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
def deleteAllCategories(request):
    if request.method == "DELETE":
        deleted_count, _ = Category.objects.all().delete()
        return JsonResponse(
            {"message": f"Successfully deleted {deleted_count} categories"},
            status=200
        )
    return HttpResponseNotAllowed(['DELETE'])

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
        
@csrf_exempt
def deleteAllSubCategories(request):
    if request.method == "DELETE":
        deleted_count, _ = SubCategory.objects.all().delete()
        return JsonResponse(
            {"message": f"Successfully deleted {deleted_count} sub categories"},
            status=200
        )
    return HttpResponseNotAllowed(['DELETE'])

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
def deleteAllVariants(request):
    if request.method == "DELETE":
        deleted_count, _ = Variant.objects.all().delete()
        return JsonResponse(
            {"message": f"Successfully deleted {deleted_count} variants"},
            status=200
        )
    return HttpResponseNotAllowed(['DELETE'])


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


#Stock :
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from .models import Stock
import json

@csrf_exempt
@login_required
@require_http_methods(["GET"])
def stock_list(request):
    """Get list of all stocks"""
    stocks = Stock.objects.all().values('product_id', 'product_name', 'quantity', 'last_updated')
    return JsonResponse(list(stocks), safe=False)

@csrf_exempt
@login_required
@require_http_methods(["GET", "PUT"])
def stock_detail(request, product_id):
    """Get or update specific stock"""
    try:
        stock = Stock.objects.get(product_id=product_id)
    except Stock.DoesNotExist:
        return JsonResponse({'error': 'Stock not found'}, status=404)

    if request.method == 'GET':
        data = {
            'product_id': stock.product_id,
            'product_name': stock.product_name,
            'quantity': stock.quantity,
            'last_updated': stock.last_updated
        }
        return JsonResponse(data)

    elif request.method == 'PUT':
        try:
            data = json.loads(request.body)
            stock.quantity = data.get('quantity', stock.quantity)
            stock.save()
            return JsonResponse({'status': 'success'})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)

@csrf_exempt
@login_required
@require_http_methods(["POST"])
def stock_create(request):
    """Create new stock"""
    try:
        data = json.loads(request.body)
        stock = Stock.objects.create(
            product_id=data['product_id'],
            product_name=data['product_name'],
            quantity=data['quantity']
        )
        return JsonResponse({
            'product_id': stock.product_id,
            'status': 'created'
        }, status=201)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

@csrf_exempt
def create_warehouse(request):
    if request.method != "POST":
        return HttpResponseNotAllowed(['POST'])

    try:
        payload = json.loads(request.body)
        name = payload.get("name")

        if not name:
            return HttpResponseBadRequest("Name is required")

        warehouse = Warehouse.objects.create(name=name)
        return JsonResponse({
            "id": warehouse.id,
            "name": warehouse.name,
        }, status=201)

    except Exception as e:
        return HttpResponseBadRequest(str(e))

@csrf_exempt
def warehouse_list(request):
    if request.method == "GET":
        warehouses = Warehouse.objects.all()
        data = []
        for wh in warehouses:
            stock_data = [
                {
                    "product_id": item.product.id,
                    "product_name": item.product.designation,
                    "quantity": item.quantity
                }
                for item in wh.stock.all()
            ]
            data.append({
                "id": wh.id,
                "name": wh.name,
                "stock": stock_data,
                "percentage": wh.percentage if hasattr(wh, 'percentage') else 0
            })
        return JsonResponse(data, safe=False)

    elif request.method == "POST":
        try:
            payload = json.loads(request.body)
            name = payload.get("name")
            if not name:
                return HttpResponseBadRequest("Name is required")
            warehouse = Warehouse.objects.create(name=name)
            return JsonResponse({"id": warehouse.id, "name": warehouse.name})
        except json.JSONDecodeError:
            return HttpResponseBadRequest("Invalid JSON")
        except Exception as e:
            return HttpResponseBadRequest(str(e))
    elif request.method == "PATCH":
        try:
            payload = json.loads(request.body)
            warehouse_id = payload.get("id")
            percentage = payload.get("percentage")

            if not warehouse_id or percentage is None:
                return HttpResponseBadRequest("Missing 'id' or 'percentage'")

            warehouse = Warehouse.objects.get(id=warehouse_id)
            warehouse.percentage = percentage
            warehouse.save()

            return JsonResponse({"id": warehouse.id, "name": warehouse.name, "percentage": warehouse.percentage})

        except Warehouse.DoesNotExist:
            return HttpResponseBadRequest("Warehouse not found")
        except json.JSONDecodeError:
            return HttpResponseBadRequest("Invalid JSON")
        except Exception as e:
            return HttpResponseBadRequest(str(e))

    return HttpResponseNotAllowed(['GET', 'POST', 'PATCH'])

    return HttpResponseNotAllowed(['GET', 'POST'])

@csrf_exempt
def warehouse_detail(request, warehouse_id):
    try:
        warehouse = Warehouse.objects.get(id=warehouse_id)
    except Warehouse.DoesNotExist:
        return HttpResponseBadRequest("Warehouse not found")

    if request.method == "PATCH":
        try:
            payload = json.loads(request.body)
            percentage = payload.get("percentage")
            if percentage is None:
                return HttpResponseBadRequest("Missing 'percentage'")
            warehouse.percentage = percentage
            warehouse.save()
            return JsonResponse({"id": warehouse.id, "name": warehouse.name, "percentage": warehouse.percentage})
        except json.JSONDecodeError:
            return HttpResponseBadRequest("Invalid JSON")

    return HttpResponseNotAllowed(['PATCH'])


@csrf_exempt
def add_stock_to_warehouse(request, warehouse_id):
    if request.method != "POST":
        return HttpResponseNotAllowed(['POST'])

    try:
        warehouse = Warehouse.objects.get(id=warehouse_id)
    except Warehouse.DoesNotExist:
        return JsonResponse({"error": "Warehouse not found"}, status=404)

    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        return HttpResponseBadRequest("Invalid JSON")

    product_id = payload.get("product_id")
    quantity = payload.get("quantity")

    if not product_id or quantity is None:
        return HttpResponseBadRequest("Fields 'product_id' and 'quantity' are required")

    try:
        product = Product.objects.get(id=product_id)
    except Product.DoesNotExist:
        return JsonResponse({"error": "Product not found"}, status=404)

    stock_item, created = StockItem.objects.get_or_create(warehouse=warehouse, product=product)
    stock_item.quantity = quantity
    stock_item.save()

    return JsonResponse({
        "warehouse": warehouse.name,
        "product": product.designation,  # updated from product.name to match your JSON
        "quantity": stock_item.quantity,
        "updated": not created
    })
    
@csrf_exempt
def update_stock_item(request, product_id):
    if request.method == 'PATCH':
        try:
            payload = json.loads(request.body)
            print("Payload received:", payload)  # 👈 Add this for debugging

            warehouse_id = payload.get("warehouse_id")
            quantity = payload.get("quantity")

            if warehouse_id is None or quantity is None:
                return JsonResponse({"error": "Missing warehouse_id or quantity"}, status=400)

            stock_item = StockItem.objects.get(product_id=product_id, warehouse_id=warehouse_id)
            stock_item.quantity = quantity
            stock_item.save()
            return JsonResponse({"success": True, "new_quantity": stock_item.quantity})

        except StockItem.DoesNotExist:
            return JsonResponse({"error": "Stock item not found"}, status=404)
        except Exception as e:
            import traceback
            traceback.print_exc()
            return JsonResponse({"error": str(e)}, status=400)

    return HttpResponseNotAllowed(['PATCH'])

@csrf_exempt
def distribute_product_to_warehouses(product, total_quantity):
    warehouses = Warehouse.objects.all()
    for warehouse in warehouses:
        quantity = int(total_quantity * (warehouse.percentage / 100))
        StockItem.objects.update_or_create(
            warehouse=warehouse,
            product=product,
            defaults={'quantity': quantity}
        )

@csrf_exempt
def distribute_stock_to_all_warehouses(request):
    if request.method != "POST":
        return HttpResponseNotAllowed(['POST'])

    warehouses = Warehouse.objects.all()
    products = Product.objects.all()

    result = []

    for warehouse in warehouses:
        entry = {
            "warehouse": warehouse.name,
            "distributed_stock": []
        }
        for product in products:
            if product.stock is None:
                continue

            stock_quantity = round(product.stock * (warehouse.percentage / 100))

            stock_item, created = StockItem.objects.get_or_create(
                warehouse=warehouse, product=product
            )
            stock_item.quantity = stock_quantity
            stock_item.save()

            entry["distributed_stock"].append({
                "product_id": product.id,
                "product_name": product.designation,
                "assigned_quantity": stock_quantity,
                "updated": not created
            })

        result.append(entry)

    return JsonResponse(result, safe=False)