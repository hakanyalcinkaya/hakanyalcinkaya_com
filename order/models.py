import secrets

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from core.models import BaseModel

MONEY = {"max_digits": 10, "decimal_places": 2, "validators": [MinValueValidator(0)]}


class OrderStatus(models.TextChoices):
    PENDING = "pending", _("Ödeme bekleniyor")
    PAID = "paid", _("Ödendi")
    FAILED = "failed", _("Başarısız")
    REFUNDED = "refunded", _("İade edildi")
    CANCELLED = "cancelled", _("İptal")


class OrderQuerySet(models.QuerySet):
    def paid(self):
        return self.filter(status=OrderStatus.PAID)

    def for_user(self, user):
        return self.filter(user=user) if user.is_authenticated else self.none()

    def containing(self, course):
        """Kursu doğrudan ya da içindeki bir paketle içeren siparişler."""
        return self.filter(Q(items__course=course) | Q(items__bundle__courses=course)).distinct()

    def unfinished(self):
        """Ödeme adımına gelip tamamlanmayanlar (bekleyen ya da başarısız)."""
        return self.filter(status__in=(OrderStatus.PENDING, OrderStatus.FAILED))


def new_order_number():
    return f"HY-{timezone.localdate():%y%m%d}-{secrets.token_hex(3).upper()}"


class Order(BaseModel):
    """Ödeme anındaki mali kayıt. Tutarlar ve ürün adları kopyalanır; sonradan fiyat değişse de sipariş aynı kalır."""

    number = models.CharField(_("sipariş no"), max_length=20, unique=True, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="orders", verbose_name=_("kullanıcı")
    )
    email = models.EmailField(_("e-posta"))
    cart = models.ForeignKey(
        "cart.Cart", on_delete=models.SET_NULL, null=True, blank=True, related_name="orders", verbose_name=_("sepet")
    )
    status = models.CharField(_("durum"), max_length=20, choices=OrderStatus, default=OrderStatus.PENDING, db_index=True)
    subtotal = models.DecimalField(_("ara toplam (₺)"), **MONEY)
    discount_total = models.DecimalField(_("indirim (₺)"), default=0, **MONEY)
    total = models.DecimalField(_("toplam (₺, KDV dahil)"), **MONEY)
    discount = models.ForeignKey(
        "discount.Discount", on_delete=models.SET_NULL, null=True, blank=True, related_name="orders", verbose_name=_("indirim kodu")
    )
    discount_code = models.CharField(_("kullanılan kod"), max_length=40, blank=True)
    payment_provider = models.CharField(_("ödeme sağlayıcı"), max_length=30, blank=True)
    payment_reference = models.CharField(_("ödeme referansı"), max_length=120, blank=True)
    paid_at = models.DateTimeField(_("ödeme tarihi"), null=True, blank=True)
    # Sitedeki satışlar TL; eski platformdan (Podia) aktarılan siparişler kendi para birimiyle saklanır.
    currency = models.CharField(_("para birimi"), max_length=3, default="TRY")

    objects = OrderQuerySet.as_manager()

    class Meta:
        verbose_name = _("sipariş")
        verbose_name_plural = _("siparişler")
        ordering = ("-created_at",)
        constraints = [
            # Aynı ödeme (ör. Podia faturası) iki kez kaydedilmez.
            models.UniqueConstraint(
                fields=("payment_provider", "payment_reference"),
                condition=~Q(payment_reference=""),
                name="order_unique_payment_reference",
            ),
        ]

    def __str__(self):
        return self.number

    def save(self, *args, **kwargs):
        if not self.number:
            self.number = new_order_number()
            while Order.objects.filter(number=self.number).exists():
                self.number = new_order_number()
        super().save(*args, **kwargs)

    @property
    def is_paid(self):
        return self.status == OrderStatus.PAID

    @classmethod
    def create_from_cart(cls, cart, email, user=None):
        """Sepetin o anki fiyatlarıyla bekleyen bir sipariş oluşturur."""
        from cart.pricing import price_cart

        summary = price_cart(cart, user)
        with transaction.atomic():
            order = cls.objects.create(
                user=user if user and user.is_authenticated else None,
                email=email,
                cart=cart,
                subtotal=summary.subtotal,
                discount_total=summary.discount_total,
                total=summary.total,
                discount=cart.discount,
                discount_code=cart.discount.code if cart.discount_id else "",
            )
            OrderItem.objects.bulk_create(
                [
                    OrderItem(
                        order=order,
                        course=line.item.course,
                        bundle=line.item.bundle,
                        title=line.product.title,
                        unit_price=line.base_price,
                        paid_price=line.final_price,
                    )
                    for line in summary.lines
                ]
            )
        return order

    def mark_paid(self, provider="", reference=""):
        """Ödemeyi onaylar: kurs kayıtlarını açar, kod kullanımını sayar, sepeti kapatır."""
        from learning.models import Enrollment, EnrollmentSource

        if self.is_paid:
            return
        with transaction.atomic():
            self.status = OrderStatus.PAID
            self.paid_at = timezone.now()
            self.payment_provider = provider or self.payment_provider
            self.payment_reference = reference or self.payment_reference
            self.save(update_fields=["status", "paid_at", "payment_provider", "payment_reference", "updated_at"])
            if self.user_id:
                for item in self.items.select_related("course", "bundle"):
                    if item.bundle_id:
                        for course in item.bundle.courses.all():
                            Enrollment.objects.get_or_create(
                                user=self.user,
                                course=course,
                                defaults={"source": EnrollmentSource.BUNDLE, "order": self, "bundle": item.bundle},
                            )
                    else:
                        Enrollment.objects.get_or_create(
                            user=self.user, course=item.course, defaults={"source": EnrollmentSource.PURCHASE, "order": self}
                        )
            if self.discount_id:
                self.discount.register_use()
            if self.cart_id:
                self.cart.mark_converted()

    def mark_failed(self, reference=""):
        self.status = OrderStatus.FAILED
        self.payment_reference = reference or self.payment_reference
        self.save(update_fields=["status", "payment_reference", "updated_at"])


class OrderItem(BaseModel):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items", verbose_name=_("sipariş"))
    course = models.ForeignKey(
        "course.Course", on_delete=models.PROTECT, null=True, blank=True, related_name="order_items", verbose_name=_("kurs")
    )
    bundle = models.ForeignKey(
        "course.Bundle", on_delete=models.PROTECT, null=True, blank=True, related_name="order_items", verbose_name=_("paket")
    )
    title = models.CharField(_("ürün adı"), max_length=200)
    unit_price = models.DecimalField(_("fiyat (₺)"), **MONEY)
    paid_price = models.DecimalField(_("ödenen (₺)"), **MONEY)

    class Meta:
        verbose_name = _("sipariş kalemi")
        verbose_name_plural = _("sipariş kalemleri")
        ordering = ("created_at",)
        constraints = [
            models.CheckConstraint(
                condition=Q(course__isnull=False, bundle__isnull=True) | Q(course__isnull=True, bundle__isnull=False),
                name="order_item_course_xor_bundle",
            ),
            models.UniqueConstraint(fields=("order", "course"), condition=Q(course__isnull=False), name="order_item_unique_course"),
            models.UniqueConstraint(fields=("order", "bundle"), condition=Q(bundle__isnull=False), name="order_item_unique_bundle"),
        ]

    def __str__(self):
        return self.title
