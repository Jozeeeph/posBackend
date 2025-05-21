from django.urls import path,include
from . import views

urlpatterns = [
    #Product
    path('product/add', views.createProduct),
    path('product/get', views.getProducts),
    path('product/update', views.updateProduct),
    path('product/delete', views.deleteProduct),
    path('product/import', views.import_products),
    
    #Category
    path('category/add', views.createCategory),
    path('category/get', views.getCategories),
    path('category/update', views.updateCategory),
    path('category/delete', views.deleteCategory),
    
    #SubCategory
    path('subcategory/add', views.createSubCategory),
    path('subcategory/get', views.getSubCategories),
    path('subcategory/update', views.updateSubCategory),
    path('subcategory/delete', views.deleteSubCategory),
    
    #Variant
    path('variant/add', views.createVariant),
    path('variant/get', views.getVariants),
    path('variant/update', views.updateVariant),
    path('variant/delete', views.deleteVariant),
]
