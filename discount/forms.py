from django import forms
from django.utils.translation import gettext_lazy as _

from discount.models import Discount, DiscountKind


class DiscountTargetsMixin:
    """Tutar indirimi ve sabit fiyat bir kurs ya da pakete bağlı olmalı (ilişkiler model clean'inde görünmez)."""

    def clean(self):
        cleaned = super().clean()
        kind = cleaned.get("kind")
        has_targets = bool(cleaned.get("courses")) or bool(cleaned.get("bundles"))
        if kind in (DiscountKind.AMOUNT, DiscountKind.FIXED_PRICE) and not has_targets:
            raise forms.ValidationError(_("Tutar indirimi ve sabit fiyat için en az bir kurs ya da paket seçmelisin."))
        return cleaned


class DiscountAdminForm(DiscountTargetsMixin, forms.ModelForm):
    class Meta:
        model = Discount
        fields = "__all__"
