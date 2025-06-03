from django.urls import path,include
from . import views
from .views import get_csrf_token

urlpatterns = [
    path('get-csrf-token/', get_csrf_token, name='get-csrf-token'),
    #Product
    path('product/add', views.createProduct),
    path('product/get', views.getProducts),
    path('product/update/<int:id>', views.updateProduct),
    path('product/delete', views.deleteAllProducts),
    path('product/import', views.import_products),
    
    #Category
    path('category/add', views.createCategory),
    path('category/get', views.getCategories),
    path('category/update/<int:id>', views.updateCategory),
    path('category/delete', views.deleteAllCategories),
    
    #SubCategory
    path('subcategory/add', views.createSubCategory),
    path('subcategory/get', views.getSubCategories),
    path('subcategory/update/<int:id>', views.updateSubCategory),
    path('subcategory/delete', views.deleteAllSubCategories),
    
    #Variant
    path('variant/add', views.createVariant),
    path('variant/get', views.getVariants),
    path('variant/update/<int:id>', views.updateVariant),
    path('variant/delete', views.deleteAllVariants),
    
    #Stock
    path('stocks/', views.stock_list, name='stock-list'),
    path('stocks/<int:product_id>/', views.stock_detail, name='stock-detail'),
    path('stocks/create/', views.stock_create, name='stock-create'),
    
    # Warehouse
    path('warehouse/create', views.create_warehouse, name='create_warehouse'),
    path('warehouse/', views.warehouse_list, name='warehouse-list'),
    path('warehouse/<int:warehouse_id>/', views.warehouse_detail, name='warehouse-detail'),
    path('warehouse/<int:warehouse_id>/add-stock/', views.add_stock_to_warehouse, name='add-stock'),
    path('stockitem/<int:product_id>/', views.update_stock_item, name='update-stock-item'),
    
    
]
