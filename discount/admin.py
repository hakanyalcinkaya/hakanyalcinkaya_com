from django import forms
from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from discount.models import Discount, DiscountKind


class DiscountAdminForm(forms.ModelForm):
    class Meta:
        model = Discount
        fields = "__all__"

    def clean(self):
        cleaned = super().clean()
        kind = cleaned.get("kind")
        has_targets = bool(cleaned.get("courses")) or bool(cleaned.get("bundles"))
        if kind in (DiscountKind.AMOUNT, DiscountKind.FIXED_PRICE) and not has_targets:
            raise forms.ValidationError(_("Tutar indirimi ve sabit fiyat için en az bir kurs ya da paket seçmelisin."))
        return cleaned


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
