from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from discount.forms import DiscountAdminForm
from discount.models import Discount


@admin.register(Discount)
class DiscountAdmin(admin.ModelAdmin):
    form = DiscountAdminForm
    list_display = ("code", "kind", "label", "status", "used_count", "max_uses", "valid_until")
    list_filter = ("status", "kind", "valid_until", "courses", "bundles")
    search_fields = ("code", "note")
    autocomplete_fields = ("courses", "bundles")
    readonly_fields = ("used_count",)
    fieldsets = (
        (None, {"fields": ("code", "kind", "value", "note")}),
        (
            _("Kapsam"),
            {"fields": ("courses", "bundles"), "description": _("Yüzde indirimde boş bırakılırsa tüm kurs ve paketlerde geçerlidir.")},
        ),
        (_("Geçerlilik"), {"fields": ("valid_from", "valid_until", "max_uses", "max_uses_per_user", "used_count")}),
        (_("Yayın"), {"fields": ("status", "published_at")}),
    )

    @admin.display(description=_("değer"))
    def label(self, obj):
        return obj.label
