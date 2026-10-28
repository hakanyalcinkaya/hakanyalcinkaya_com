from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from core.models import BaseModel, BaseStatus, Status, StatusQuerySet

CENT = Decimal("0.01")


class DiscountKind(models.TextChoices):
    PERCENT = "percent", _("Yüzde indirim")
    AMOUNT = "amount", _("Tutar indirimi (₺)")
    FIXED_PRICE = "fixed_price", _("Sabit fiyat (₺)")


class DiscountQuerySet(StatusQuerySet):
    def by_code(self, code):
        return self.filter(code__iexact=(code or "").strip()).first()


class Discount(BaseModel, BaseStatus):
    """Sepete tek kod olarak uygulanan indirim.

    Yüzde: ürün seçilmezse tüm kurs ve paketlerde geçerli. Tutar ve sabit fiyat: seçilen her kurs/pakete ayrı ayrı uygulanır
    (sabit fiyat ₺499 ise A ve B kursu ₺499'dan, toplam ₺998). İndirimli fiyat 0'ın altına inmez.
    """

    code = models.CharField(_("kod"), max_length=40)
    kind = models.CharField(_("tür"), max_length=20, choices=DiscountKind, default=DiscountKind.PERCENT)
    value = models.DecimalField(_("değer"), max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0"))])
    courses = models.ManyToManyField("course.Course", blank=True, related_name="discounts", verbose_name=_("kurslar"))
    bundles = models.ManyToManyField("course.Bundle", blank=True, related_name="discounts", verbose_name=_("paketler"))
    valid_from = models.DateTimeField(_("başlangıç"), null=True, blank=True)
    valid_until = models.DateTimeField(_("bitiş"), null=True, blank=True)
    max_uses = models.PositiveIntegerField(_("toplam kullanım sınırı"), null=True, blank=True)
    max_uses_per_user = models.PositiveIntegerField(_("kişi başı kullanım sınırı"), null=True, blank=True)
    used_count = models.PositiveIntegerField(_("kullanım sayısı"), default=0, editable=False)
    note = models.CharField(_("iç not"), max_length=200, blank=True)

    objects = DiscountQuerySet.as_manager()

    class Meta:
        verbose_name = _("indirim kodu")
        verbose_name_plural = _("indirim kodları")
        ordering = ("-created_at",)
        constraints = [models.UniqueConstraint(Lower("code"), name="discount_code_ci_unique")]

    def __str__(self):
        return self.code

    def save(self, *args, **kwargs):
        self.code = self.code.strip().upper()
        super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        if self.kind == DiscountKind.PERCENT and not Decimal("0") < (self.value or 0) <= Decimal("100"):
            raise ValidationError({"value": _("Yüzde indirim 0 ile 100 arasında olmalı.")})
        if self.valid_from and self.valid_until and self.valid_from >= self.valid_until:
            raise ValidationError({"valid_until": _("Bitiş, başlangıçtan sonra olmalı.")})

    @property
    def label(self):
        if self.kind == DiscountKind.PERCENT:
            return f"%{self.value.normalize():f}"
        from core.money import format_try

        return format_try(self.value)

    @property
    def needs_targets(self):
        return self.kind != DiscountKind.PERCENT

    def has_targets(self):
        return self.courses.exists() or self.bundles.exists()

    def applies_to(self, product):
        """product: Course ya da Bundle."""
        targets = self.courses if product._meta.model_name == "course" else self.bundles
        if not self.has_targets():
            return self.kind == DiscountKind.PERCENT
        return targets.filter(pk=product.pk).exists()

    def price_for(self, product, base_price):
        if not self.applies_to(product):
            return base_price
        if self.kind == DiscountKind.PERCENT:
            price = base_price * (Decimal("100") - self.value) / Decimal("100")
        elif self.kind == DiscountKind.AMOUNT:
            price = base_price - self.value
        else:
            price = min(self.value, base_price)
        return max(price, Decimal("0")).quantize(CENT, rounding=ROUND_HALF_UP)

    def uses_by(self, user):
        if not user or not user.is_authenticated:
            return 0
        return self.orders.filter(user=user, status="paid").count()

    def validate_for(self, user=None, now=None):
        """Kullanılabilir değilse kullanıcıya gösterilecek mesajla ValidationError fırlatır."""
        now = now or timezone.now()
        if self.status != Status.PUBLISHED:
            raise ValidationError(_("Bu indirim kodu geçerli değil."))
        if self.valid_from and now < self.valid_from:
            raise ValidationError(_("Bu indirim kodu henüz başlamadı."))
        if self.valid_until and now > self.valid_until:
            raise ValidationError(_("Bu indirim kodunun süresi doldu."))
        if self.max_uses is not None and self.used_count >= self.max_uses:
            raise ValidationError(_("Bu indirim kodunun kullanım sınırı doldu."))
        if self.max_uses_per_user is not None and self.uses_by(user) >= self.max_uses_per_user:
            raise ValidationError(_("Bu indirim kodunu daha önce kullandın."))

    def register_use(self):
        Discount.objects.filter(pk=self.pk).update(used_count=models.F("used_count") + 1)
