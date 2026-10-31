from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from cart.models import Cart, CartItem, CartItemRemoval


class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0
    autocomplete_fields = ("course", "bundle")


class CartItemRemovalInline(admin.TabularInline):
    model = CartItemRemoval
    extra = 0
    can_delete = False
    fields = ("course", "bundle", "reason", "added_at", "created_at")
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ("__str__", "status", "item_count", "discount", "updated_at")
    list_filter = ("status", ("user", admin.EmptyFieldListFilter), ("discount", admin.EmptyFieldListFilter), "updated_at")
    search_fields = ("user__email", "session_key")
    list_select_related = ("user", "discount")
    autocomplete_fields = ("user", "discount")
    readonly_fields = ("checkout_at", "emptied_at", "converted_at", "gifted_at", "created_at", "updated_at")
    inlines = (CartItemInline, CartItemRemovalInline)

    @admin.display(description=_("ürün"))
    def item_count(self, obj):
        return obj.items.count()


@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    list_display = ("__str__", "cart", "created_at")
    list_filter = ("cart__status", ("bundle", admin.EmptyFieldListFilter), "course", "bundle")
    search_fields = ("course__title", "bundle__title", "cart__user__email")
    list_select_related = ("cart__user", "course", "bundle")
    autocomplete_fields = ("course", "bundle")
    raw_id_fields = ("cart",)

