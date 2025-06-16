from django.db import models
from django.core.validators import MinValueValidator
from django.core.exceptions import ValidationError
from django.utils import timezone


class Category(models.Model):
    name = models.CharField(max_length=100)
    image_path = models.CharField(max_length=255, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Category"
        verbose_name_plural = "Categories"
        ordering = ['name']

    def __str__(self):
        return self.name


class SubCategory(models.Model):
    name = models.CharField(max_length=100)
    parent = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='children'
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.CASCADE,
        related_name='subcategories'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "SubCategory"
        verbose_name_plural = "SubCategories"
        ordering = ['name']
        constraints = [
            models.UniqueConstraint(
                fields=['name', 'category'],
                name='unique_subcategory_per_category'
            )
        ]

    def __str__(self):
        parent_info = f" (child of {self.parent.name})" if self.parent else ""
        return f"{self.name}{parent_info} [{self.category.name}]"

    def clean(self):
        if self.parent and self.parent.id == self.id:
            raise ValidationError("A subcategory cannot be its own parent")
        if self.parent and self.parent.category != self.category:
            raise ValidationError("Parent subcategory must belong to the same category")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def to_map(self):
        return {
            'id_sub_category': self.id,
            'sub_category_name': self.name,
            'parent_id': self.parent_id,
            'category_id': self.category_id,
        }

    @classmethod
    def from_map(cls, data):
        return cls(
            id=data.get('id_sub_category'),
            name=data.get('sub_category_name', 'Unnamed Subcategory'),
            parent_id=data.get('parent_id'),
            category_id=data.get('category_id'),
        )


class Product(models.Model):
    STATUS_CHOICES = [
        ('in_stock', 'En stock'),
        ('out_of_stock', 'En rupture'),
        ('pre_order', 'Pré-commande'),
    ]

    code = models.CharField(max_length=50, unique=True, null=True, blank=True)
    designation = models.CharField(max_length=255)
    description = models.TextField(null=True, blank=True)
    stock = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    prix_ht = models.DecimalField(max_digits=10, decimal_places=2)
    taxe = models.DecimalField(max_digits=5, decimal_places=2)
    prix_ttc = models.DecimalField(max_digits=10, decimal_places=2, blank=True)
    date_expiration = models.DateField(null=True, blank=True)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True)
    category_name = models.CharField(max_length=100, null=True, blank=True)
    sub_category = models.ForeignKey(SubCategory, on_delete=models.SET_NULL, null=True, blank=True)
    sub_category_name = models.CharField(max_length=100, null=True, blank=True)
    is_deleted = models.BooleanField(default=False)
    marge = models.DecimalField(null=True, max_digits=5, decimal_places=2)
    remise_max = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    remise_valeur_max = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    has_variants = models.BooleanField(default=False)
    sellable = models.BooleanField(default=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='in_stock')
    image = models.ImageField(upload_to='products/', null=True, blank=True)
    brand = models.CharField(max_length=100, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Product"
        verbose_name_plural = "Products"


    def __str__(self):
        return f"{self.designation} ({self.code})"

    @property
    def total_stock(self):
        if self.has_variants:
            return sum(variant.stock for variant in self.variants.all())
        return self.stock

    def save(self, *args, **kwargs):
    # Auto-set prix_ttc if not given
        if not self.prix_ttc:
            self.prix_ttc = self.prix_ht * (1 + self.taxe / 100)

    # Set category_name from foreign key
        if self.category:
            self.category_name = self.category.name
        else:
            self.category_name = None

    # Set sub_category_name from foreign key
        if self.sub_category:
            self.sub_category_name = self.sub_category.name
        else:
            self.sub_category_name = None

        super().save(*args, **kwargs)


        

class Variant(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='variants')
    code = models.CharField(max_length=50, null=True, blank=True)
    combination_name = models.CharField(max_length=255)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    price_impact = models.DecimalField(max_digits=10, decimal_places=2)
    stock = models.IntegerField(validators=[MinValueValidator(0)])
    default_variant = models.BooleanField(default=False)
    attributes = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-default_variant', 'combination_name']
        unique_together = ('product', 'combination_name')

    def __str__(self):
        return f"{self.combination_name} - {self.product.designation}"

    @property
    def final_price(self):
        return self.price + self.price_impact

    def save(self, *args, **kwargs):
        if not isinstance(self.attributes, dict):
            self.attributes = {}
        super().save(*args, **kwargs)

        
        
class Stock(models.Model):
    product_id = models.IntegerField(unique=True)
    product_name = models.CharField(max_length=255)
    quantity = models.IntegerField()
    last_updated = models.DateTimeField(default=timezone.now)
    
    def __str__(self):
        return f"{self.product_name} (ID: {self.product_id}) - {self.quantity} unités"
    

class Warehouse(models.Model):
    name = models.CharField(max_length=255)
    percentage = models.FloatField(default=0.0)  # Add this line

    def __str__(self):
        return self.name

class StockItem(models.Model):
    warehouse = models.ForeignKey(Warehouse, on_delete=models.CASCADE, related_name='stock')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='stock_items')
    variant = models.ForeignKey(Variant, on_delete=models.CASCADE, related_name='stock_items', null=True, blank=True)
    quantity = models.PositiveIntegerField(default=0)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.product.has_variants:
            total_quantity = sum(item.quantity for item in self.product.stock_items.all())
            self.product.stock = total_quantity
            self.product.save()