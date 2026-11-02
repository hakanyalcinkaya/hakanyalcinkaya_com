import secrets
from functools import partial

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.db.models import Q
from django.urls import reverse
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


# Ödeme yolu (payment_provider). Son kullanıcı yalnız kartla öder; havale/EFT ve elle kayıtları yönetici açar.
PAYMENT_METHODS = {
    "card": _("Kredi / banka kartı"),
    "bank_transfer": _("Havale / EFT"),
    "manual": _("Elle (yönetici)"),
    "podia": _("Podia (eski platform)"),
}
ADMIN_PAYMENT_METHODS = ("bank_transfer", "card", "manual")

# Stüdyoda elle yapılabilen durum değişiklikleri; "ödendi"ye geçiş mark_paid ile olur.
STATUS_TRANSITIONS = {
    OrderStatus.PENDING: (OrderStatus.PAID, OrderStatus.FAILED, OrderStatus.CANCELLED),
    OrderStatus.FAILED: (OrderStatus.PAID, OrderStatus.PENDING, OrderStatus.CANCELLED),
    OrderStatus.PAID: (OrderStatus.REFUNDED, OrderStatus.CANCELLED),
    OrderStatus.REFUNDED: (OrderStatus.PAID,),
    OrderStatus.CANCELLED: (OrderStatus.PAID, OrderStatus.PENDING),
}
# Alıcıya bilgilendirme e-postası gönderilebilen geçişler (e-posta anahtarı: order.tasks.NOTICE_EMAILS).
NOTICE_STATUSES = (OrderStatus.REFUNDED, OrderStatus.CANCELLED)


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

    def visible_to(self, user, numbers=()):
        """Teşekkür sayfası: siparişin sahibi ya da siparişi bu tarayıcıda veren (oturumdaki sipariş numaraları)."""
        condition = Q(number__in=list(numbers))
        if user.is_authenticated:
            condition |= Q(user=user)
        return self.filter(condition)


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

    def get_thanks_url(self):
        return reverse("page:thanks", kwargs={"number": self.number})

    @property
    def is_paid(self):
        return self.status == OrderStatus.PAID

    @property
    def next_statuses(self):
        return STATUS_TRANSITIONS.get(self.status, ())

    @property
    def payment_method_label(self):
        return PAYMENT_METHODS.get(self.payment_provider, self.payment_provider)

    @classmethod
    def create_from_cart(cls, cart, email, user=None, provider=""):
        """Sepetin o anki fiyatlarıyla bekleyen bir sipariş oluşturur."""
        from cart.pricing import price_cart

        return cls._create(price_cart(cart, user), email, user, cart=cart, discount=cart.discount, provider=provider)

    @classmethod
    def create_for_items(cls, items, email, user, discount=None, provider="", cart=None):
        """Yöneticinin açtığı sipariş (ör. havale/EFT): ürünler (kaydedilmemiş CartItem) bugünkü fiyatlarıyla."""
        from cart.pricing import price_items

        return cls._create(price_items(items, user, discount), email, user, cart=cart, discount=discount, provider=provider)

    @classmethod
    def _create(cls, summary, email, user, cart=None, discount=None, provider=""):
        with transaction.atomic():
            order = cls.objects.create(
                user=user if user and user.is_authenticated else None,
                email=email,
                cart=cart,
                subtotal=summary.subtotal,
                discount_total=summary.discount_total,
                total=summary.total,
                discount=discount,
                discount_code=discount.code if discount else "",
                payment_provider=provider,
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
        """Ödemeyi onaylar: kurs kayıtlarını açar, kod kullanımını sayar, sepeti kapatır; işlem kaydedilince alıcıya satın
        alma onayı e-postası gider (iyzico, stüdyoda havale onayı, admin; Podia aktarımı bunu kullanmaz)."""
        from learning.models import Enrollment, EnrollmentSource
        from order.tasks import send_purchase_confirmation

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
            transaction.on_commit(partial(send_purchase_confirmation.delay, str(self.pk)))

    def set_status(self, status, revoke_access=True, notify=False):
        """Yöneticinin durum değişikliği; geçersiz geçişte ValueError. "Ödendi"ye mark_paid ile geçer. Ödenmiş sipariş iade
        ya da iptal edilince kod kullanımı geri alınır ve revoke_access ise bu siparişin açtığı kurs erişimleri kaldırılır
        (ders ilerlemesi kalır). notify: iade/iptalde alıcıya bilgilendirme e-postası (hesaba bağlı siparişte). Kaldırılan
        erişim sayısını döner."""
        from learning.models import Enrollment
        from order.tasks import send_order_notice

        if status not in self.next_statuses:
            raise ValueError(f"{self.status} -> {status}")
        if status == OrderStatus.PAID:
            self.mark_paid(provider=self.payment_provider or "manual")
            return 0
        notify = notify and status in NOTICE_STATUSES and bool(self.user_id)
        revoked = 0
        with transaction.atomic():
            was_paid = self.is_paid
            self.status = status
            self.save(update_fields=["status", "updated_at"])
            if was_paid:
                if revoke_access:
                    revoked = Enrollment.objects.filter(order=self).delete()[1].get("learning.Enrollment", 0)
                if self.discount_id:
                    self.discount.release_use()
            if notify:
                transaction.on_commit(partial(send_order_notice.delay, str(self.pk), access_revoked=bool(revoked)))
        return revoked

    def mark_failed(self, reference=""):
        self.status = OrderStatus.FAILED
        self.payment_reference = reference or self.payment_reference
        self.save(update_fields=["status", "payment_reference", "updated_at"])

    def other_orders(self):
        """Aynı alıcının diğer siparişleri: üyeye bağlıysa üyenin, değilse aynı e-postanın."""
        rows = Order.objects.filter(user_id=self.user_id) if self.user_id else Order.objects.filter(email__iexact=self.email)
        return rows.exclude(pk=self.pk).order_by("-created_at", "id")

    @property
    def can_resend_confirmation(self):
        return self.is_paid and bool(self.user_id)


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
