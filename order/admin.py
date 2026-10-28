from django.contrib import admin, messages
from django.utils.translation import gettext_lazy as _

from core.money import format_try
from order.models import Order, OrderItem


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    can_delete = False
    fields = ("title", "course", "bundle", "unit_price", "paid_price")
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("number", "email", "status", "total_display", "discount_code", "paid_at", "created_at")
    list_filter = ("status", "payment_provider", ("discount", admin.EmptyFieldListFilter), "paid_at", "created_at")
    search_fields = ("number", "email", "user__email", "payment_reference")
    list_select_related = ("user",)
    inlines = (OrderItemInline,)
    actions = ("mark_paid",)
    # Mali kayıt: tutarlar ve kalemler elle değiştirilmez.
    readonly_fields = (
        "number",
        "user",
        "email",
        "cart",
        "subtotal",
        "discount_total",
        "total",
        "discount",
        "discount_code",
        "paid_at",
        "created_at",
        "updated_at",
    )
    fieldsets = (
        (None, {"fields": ("number", "user", "email", "cart", "status")}),
        (_("Tutarlar (₺, KDV dahil)"), {"fields": ("subtotal", "discount", "discount_code", "discount_total", "total")}),
        (_("Ödeme"), {"fields": ("payment_provider", "payment_reference", "paid_at")}),
        (_("Kayıt"), {"fields": ("created_at", "updated_at")}),
    )

    @admin.display(description=_("toplam"), ordering="total")
    def total_display(self, obj):
        return format_try(obj.total)

    @admin.action(description=_("Seçili siparişleri ödendi olarak işaretle (kurs kayıtlarını açar)"))
    def mark_paid(self, request, queryset):
        count = 0
        for order in queryset.exclude(status="paid"):
            order.mark_paid(provider=order.payment_provider or "manual")
            count += 1
        self.message_user(request, _("%(count)s sipariş ödendi olarak işaretlendi.") % {"count": count}, messages.SUCCESS)


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    """Sipariş kalemleri mali kayıttır; yalnız görüntülenir."""

    list_display = ("title", "order", "unit_price", "paid_price", "created_at")
    list_filter = ("order__status", ("bundle", admin.EmptyFieldListFilter), "course", "bundle")
    search_fields = ("title", "order__number", "order__email")
    list_select_related = ("order",)
    readonly_fields = ("order", "course", "bundle", "title", "unit_price", "paid_price", "created_at", "updated_at")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

