import secrets
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.db.models.functions import Lower
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from core.models import BaseModel, BaseStatus, BaseVisitorEvent, Status, StatusQuerySet, VisitorEventQuerySet

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
        return self._discounted(base_price)

    def _discounted(self, base_price):
        if self.kind == DiscountKind.PERCENT:
            price = base_price * (Decimal("100") - self.value) / Decimal("100")
        elif self.kind == DiscountKind.AMOUNT:
            price = base_price - self.value
        else:
            price = min(self.value, base_price)
        return max(price, Decimal("0")).quantize(CENT, rounding=ROUND_HALF_UP)

    def course_prices(self, courses):
        """Kodun düşürdüğü kurs fiyatları {kurs id: indirimli fiyat} (applies_to ile aynı kural, iki sorguyla); fiyatı
        değişmeyen kurslar yer almaz."""
        targets = set(self.courses.values_list("pk", flat=True))
        if not targets and (self.kind != DiscountKind.PERCENT or self.bundles.exists()):
            return {}
        prices = {}
        for course in courses:
            if targets and course.pk not in targets:
                continue
            price = self._discounted(course.price)
            if price < course.price:
                prices[course.pk] = price
        return prices

    @property
    def is_expired(self):
        return bool(self.valid_until and timezone.now() > self.valid_until)

    @property
    def is_used_up(self):
        return self.max_uses is not None and self.used_count >= self.max_uses

    @property
    def is_usable(self):
        """Yayında, süresi dolmamış ve kullanım sınırı dolmamış (kişiye özel kurallar hariç)."""
        return self.status == Status.PUBLISHED and not self.is_expired and not self.is_used_up

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

    def release_use(self):
        Discount.objects.filter(pk=self.pk, used_count__gt=0).update(used_count=models.F("used_count") - 1)


# Kişiye özel indirim kodu (bağlantıyla gelen ya da girilen kod geçersizse istenebilir): öğrenci / çalışan beyanına göre
# kuraldaki indirimle tek kullanımlık, süreli kod üretilip e-postayla gönderilir.
PERSONAL_CODE_PREFIX = "SPC"
PERSONAL_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


class PersonalAudience(models.TextChoices):
    STUDENT = "student", _("Öğrenci")
    EMPLOYEE = "employee", _("Çalışan")


class PersonalDiscountRule(BaseModel, BaseStatus):
    """Kitle (öğrenci ya da çalışan) başına bir kural: üretilecek kodun indirimi, geçerli olduğu kurslar/paketler, kaç gün
    geçerli olduğu ve süresi dolan ya da kullanılan koddan sonra aynı e-postaya yeni kod verilip verilmeyeceği. Yalnız
    yayındaki kurallar istek formunda seçilebilir."""

    audience = models.CharField(_("kitle"), max_length=20, choices=PersonalAudience, unique=True)
    kind = models.CharField(_("tür"), max_length=20, choices=DiscountKind, default=DiscountKind.PERCENT)
    value = models.DecimalField(_("değer"), max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0"))])
    courses = models.ManyToManyField("course.Course", blank=True, related_name="personal_discount_rules", verbose_name=_("kurslar"))
    bundles = models.ManyToManyField("course.Bundle", blank=True, related_name="personal_discount_rules", verbose_name=_("paketler"))
    valid_days = models.PositiveSmallIntegerField(_("geçerlilik (gün)"), default=3, validators=[MinValueValidator(1)])
    allow_repeat = models.BooleanField(
        _("süre dolunca yeni kod verilir"),
        default=False,
        help_text=_("Kapalıysa aynı e-posta, kodunun süresi dolduktan ya da kodu kullandıktan sonra yeni kod alamaz."),
    )
    note = models.CharField(_("iç not"), max_length=200, blank=True)

    class Meta:
        verbose_name = _("özel indirim kuralı")
        verbose_name_plural = _("özel indirim kuralları")
        ordering = ("audience",)

    def __str__(self):
        return f"{self.get_audience_display()} · {self.label}"

    def clean(self):
        super().clean()
        if self.kind == DiscountKind.PERCENT and not Decimal("0") < (self.value or 0) <= Decimal("100"):
            raise ValidationError({"value": _("Yüzde indirim 0 ile 100 arasında olmalı.")})

    @property
    def label(self):
        return Discount(kind=self.kind, value=self.value).label

    @staticmethod
    def new_code():
        while True:
            code = PERSONAL_CODE_PREFIX + "".join(secrets.choice(PERSONAL_CODE_ALPHABET) for _index in range(6))
            if not Discount.objects.filter(code__iexact=code).exists():
                return code

    def issue(self, email):
        """Kurala göre tek kullanımlık, valid_days gün geçerli yeni kod (yayında)."""
        now = timezone.now()
        with transaction.atomic():
            discount = Discount.objects.create(
                code=self.new_code(),
                kind=self.kind,
                value=self.value,
                valid_from=now,
                valid_until=now + timedelta(days=self.valid_days),
                max_uses=1,
                max_uses_per_user=1,
                status=Status.PUBLISHED,
                note=f"Özel kod · {self.get_audience_display()} · {email}"[:200],
            )
            discount.courses.set(self.courses.all())
            discount.bundles.set(self.bundles.all())
        return discount


class PersonalRequestResult(models.TextChoices):
    SENT = "sent", _("Yeni kod gönderildi")
    RESENT = "resent", _("Geçerli kod yeniden gönderildi")
    REFUSED_EXPIRED = "refused-expired", _("Verilmedi: süre doldu")
    REFUSED_USED = "refused-used", _("Verilmedi: kod kullanıldı")


class PersonalDiscountRequestQuerySet(VisitorEventQuerySet):
    def for_email(self, email):
        return self.filter(email__iexact=email.strip())


class PersonalDiscountRequest(BaseVisitorEvent):
    """Kişiye özel indirim kodu isteği (e-posta + öğrenci/çalışan beyanı) ve sonucu; gönderilen kod discount alanında.
    Ziyaretçi bilgileri data alanında (core.visitor)."""

    email = models.EmailField(_("e-posta"), db_index=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="personal_discount_requests", verbose_name=_("üye"))
    audience = models.CharField(_("kitle"), max_length=20, choices=PersonalAudience)
    rule = models.ForeignKey(PersonalDiscountRule, on_delete=models.SET_NULL, null=True, blank=True, related_name="requests", verbose_name=_("kural"))
    discount = models.ForeignKey(Discount, on_delete=models.SET_NULL, null=True, blank=True, related_name="personal_requests", verbose_name=_("indirim kodu"))
    result = models.CharField(_("sonuç"), max_length=20, choices=PersonalRequestResult)

    objects = PersonalDiscountRequestQuerySet.as_manager()

    class Meta(BaseVisitorEvent.Meta):
        verbose_name = _("özel indirim kodu isteği")
        verbose_name_plural = _("özel indirim kodu istekleri")

    def __str__(self):
        return f"{self.email} · {self.get_audience_display()} · {self.get_result_display()}"

    @property
    def is_sent(self):
        return self.result in (PersonalRequestResult.SENT, PersonalRequestResult.RESENT)

    @property
    def refusal_message(self):
        if self.result == PersonalRequestResult.REFUSED_USED:
            return "Üzgünüz, sana özel indirim kodunu daha önce kullandığın için yeni indirim kodu tanımlanamadı."
        if self.result == PersonalRequestResult.REFUSED_EXPIRED:
            days = self.rule.valid_days if self.rule else ""
            return f"Üzgünüz, indirim kodu tekrar tanımlanamadı çünkü {days} günlük süre doldu."
        return ""

    @classmethod
    def handle(cls, rule, email, audience, user=None, data=None):
        """İsteği kurala göre sonuçlandırır ve kaydeder. Bu e-postaya daha önce verilen kod hâlâ kullanılabiliyorsa o kod
        yeniden gönderilir; süresi dolmuş ya da kullanılmışsa kural izin veriyorsa yeni kod üretilir, vermiyorsa istek
        reddedilir. Gönderim (Celery) kayıt veritabanına yazılınca başlar."""
        from discount.tasks import send_personal_discount

        email = email.strip()
        last = cls.objects.for_email(email).filter(discount__isnull=False).select_related("discount").order_by("-created_at").first()
        previous = last.discount if last else None
        if previous is not None and previous.is_usable:
            result, discount = PersonalRequestResult.RESENT, previous
        elif previous is not None and not rule.allow_repeat:
            result = PersonalRequestResult.REFUSED_USED if previous.is_used_up else PersonalRequestResult.REFUSED_EXPIRED
            discount = None
        else:
            result, discount = PersonalRequestResult.SENT, rule.issue(email)
        request = cls.objects.create(email=email, user=user, audience=audience, rule=rule, discount=discount, result=result, data=data or {})
        if request.is_sent:
            transaction.on_commit(lambda: send_personal_discount.delay(str(request.pk)))
        return request
