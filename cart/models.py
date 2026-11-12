from django.conf import settings
from django.contrib.postgres.indexes import GinIndex
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import OuterRef, Q, Subquery
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from core.models import BaseModel, BaseVisitorEvent


class CartStatus(models.TextChoices):
    ACTIVE = "active", _("Aktif")
    EMPTIED = "emptied", _("Boşaltıldı")
    CONVERTED = "converted", _("Siparişe dönüştü")
    GIFTED = "gifted", _("Hediye edildi")
    MERGED = "merged", _("Üye sepetine katıldı")


class CartRemovalReason(models.TextChoices):
    REMOVED = "removed", _("Ziyaretçi çıkardı")
    BUNDLE = "bundle", _("Paket eklenince çıktı")
    OWNED = "owned", _("Kursa sahip olunca düştü")


class CartQuerySet(models.QuerySet):
    def active(self):
        return self.filter(status=CartStatus.ACTIVE)

    def for_request(self, request):
        """Giriş yapmışsa kullanıcının, değilse oturumun aktif sepeti."""
        if request.user.is_authenticated:
            return self.active().filter(user=request.user).first()
        key = request.session.session_key
        return self.active().filter(user__isnull=True, session_key=key).first() if key else None

    def countable(self):
        """İstatistikte sayılan sepetler: üye sepetine katılan misafir sepetleri hariç (ürünleri üye sepetinde sayılır).
        Eskiden katılan sepet "siparişe dönüştü" olarak, dönüşme tarihi boş kalırdı."""
        return self.exclude(status=CartStatus.MERGED).exclude(status=CartStatus.CONVERTED, converted_at__isnull=True)

    def clearable(self):
        """Stüdyoda temizlenebilen (silinebilen) sepetler: satışa dönüşmemiş (açık ya da boşaltılmış) ve siparişi olmayan.
        Silinen sepet ürünleri ve çıkarılan ürün kayıtlarıyla birlikte istatistiklerden de çıkar."""
        return self.filter(status__in=(CartStatus.ACTIVE, CartStatus.EMPTIED), orders__isnull=True)

    def with_products(self):
        """İçine en az bir ürün eklenmiş sepetler (sonradan çıkarılmış olsa da)."""
        return self.filter(Q(items__isnull=False) | Q(removals__isnull=False)).distinct()

    def with_visitor(self):
        """visitor: sepete son eklemenin ziyaretçi bilgileri (CartAddEvent.data), yoksa None."""
        latest = CartAddEvent.objects.filter(cart=OuterRef("pk")).order_by("-created_at").values("data")[:1]
        return self.annotate(visitor=Subquery(latest, output_field=models.JSONField()))


class Cart(BaseModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True, related_name="carts", verbose_name=_("kullanıcı")
    )
    session_key = models.CharField(_("oturum anahtarı"), max_length=40, blank=True, db_index=True)
    status = models.CharField(_("durum"), max_length=20, choices=CartStatus, default=CartStatus.ACTIVE, db_index=True)
    discount = models.ForeignKey(
        "discount.Discount", on_delete=models.SET_NULL, null=True, blank=True, related_name="carts", verbose_name=_("indirim kodu")
    )
    emptied_at = models.DateTimeField(_("boşaltılma"), null=True, blank=True)
    converted_at = models.DateTimeField(_("siparişe dönüşme"), null=True, blank=True)
    checkout_at = models.DateTimeField(_("ödeme adımına geçiş"), null=True, blank=True)
    gifted_at = models.DateTimeField(_("hediye edilme"), null=True, blank=True)

    objects = CartQuerySet.as_manager()

    class Meta:
        verbose_name = _("sepet")
        verbose_name_plural = _("sepetler")
        ordering = ("-updated_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("user",), condition=Q(status="active", user__isnull=False), name="cart_one_active_per_user"
            ),
        ]

    def __str__(self):
        owner = self.user or self.session_key[:8] or "-"
        return f"{owner} · {self.get_status_display()}"

    @property
    def is_active(self):
        return self.status == CartStatus.ACTIVE

    @property
    def is_merged(self):
        return self.status == CartStatus.MERGED or (self.status == CartStatus.CONVERTED and self.converted_at is None)

    def _check_active(self):
        if not self.is_active:
            raise ValidationError(_("Bu sepet artık değiştirilemez."))

    def owned_course_ids(self):
        if not self.user_id:
            return set()
        return set(self.user.enrollments.values_list("course_id", flat=True))

    def add_course(self, course):
        self._check_active()
        if course.pk in self.owned_course_ids():
            raise ValidationError(_("Bu kursa zaten sahipsin."))
        if self.items.filter(bundle__courses=course).exists():
            raise ValidationError(_("Bu kurs sepetindeki bir paketin içinde."))
        item, _created = self.items.get_or_create(course=course)
        return item

    def add_bundle(self, bundle):
        """Paketi ekler; paketin içindeki tek kurslar sepetten çıkar ve listesi döner (bildirim için)."""
        self._check_active()
        with transaction.atomic():
            contained = list(self.items.filter(course__in=bundle.courses.all()).select_related("course"))
            removed = [item.course for item in contained]
            for item in contained:
                self.remove_item(item, reason=CartRemovalReason.BUNDLE)
            self.items.get_or_create(bundle=bundle)
        return removed

    def remove_item(self, item, reason=CartRemovalReason.REMOVED):
        """Ürünü sepetten çıkarır; istatistik için ne zaman eklenip neden çıktığı kaydedilir."""
        self._check_active()
        with transaction.atomic():
            self.removals.create(course_id=item.course_id, bundle_id=item.bundle_id, reason=reason, added_at=item.created_at)
            item.delete()

    def reach_checkout(self):
        """Ödeme adımına ilk geçiş (sepet → ödeme hunisi); sonraki ziyaretler değiştirmez."""
        if self.checkout_at is None and self.is_active:
            self.checkout_at = timezone.now()
            self.save(update_fields=["checkout_at", "updated_at"])

    def apply_discount(self, discount, user=None):
        self._check_active()
        discount.validate_for(user or self.user)
        self.discount = discount
        self.save(update_fields=["discount", "updated_at"])

    def remove_discount(self):
        self.discount = None
        self.save(update_fields=["discount", "updated_at"])

    def empty(self):
        """Sepeti boşaltır: silinmez, 'boşaltıldı' olarak kalır; bir sonraki eklemede yeni sepet açılır.

        TODO: Boşaltılan sepetlerin sahiplerine ileride indirim bildirimi gönderilebilir (TODO.md).
        """
        self._check_active()
        self.status = CartStatus.EMPTIED
        self.emptied_at = timezone.now()
        self.save(update_fields=["status", "emptied_at", "updated_at"])

    def mark_converted(self):
        self.status = CartStatus.CONVERTED
        self.converted_at = timezone.now()
        self.save(update_fields=["status", "converted_at", "updated_at"])

    def gift(self):
        """Yönetici sepetteki kursları üyeye hediye eder (paketlerin kursları dahil); sahip olunanlar atlanır, sepet
        "hediye edildi" olarak kapanır. Açılan kurs kayıtlarının listesi döner."""
        from learning.models import Enrollment, EnrollmentSource

        self._check_active()
        if not self.user_id:
            raise ValidationError(_("Misafir sepeti hediye edilemez; önce üye olması gerekir."))
        created = []
        with transaction.atomic():
            for item in self.items.select_related("course", "bundle").prefetch_related("bundle__courses"):
                courses = item.bundle.courses.all() if item.bundle_id else [item.course]
                for course in courses:
                    enrollment, is_new = Enrollment.objects.get_or_create(
                        user=self.user, course=course, defaults={"source": EnrollmentSource.GIFT, "bundle": item.bundle}
                    )
                    if is_new:
                        created.append(enrollment)
            self.status = CartStatus.GIFTED
            self.gifted_at = timezone.now()
            self.save(update_fields=["status", "gifted_at", "updated_at"])
        return created

    def merge_into(self, target):
        """Misafir sepetini giriş yapan kullanıcının sepetine taşır; sahip olunan kurslar taşınmaz. Bu sepet kapanır."""
        with transaction.atomic():
            for item in self.items.select_related("course", "bundle"):
                try:
                    if item.bundle_id:
                        target.add_bundle(item.bundle)
                    else:
                        target.add_course(item.course)
                except ValidationError:
                    continue
            if self.discount_id and not target.discount_id:
                target.discount = self.discount
                target.save(update_fields=["discount", "updated_at"])
            if self.checkout_at and not target.checkout_at:
                target.checkout_at = self.checkout_at
                target.save(update_fields=["checkout_at", "updated_at"])
            # Sepete ekleme kayıtları satın alma izlensin diye üyenin sepetine geçer.
            self.add_events.update(cart=target, user=target.user)
            self.status = CartStatus.MERGED
            self.save(update_fields=["status", "updated_at"])
        return target


class CartItemQuerySet(models.QuerySet):
    def with_visitor(self):
        """visitor: ürünün bu sepete son eklenmesinin ziyaretçi bilgileri (CartAddEvent.data), yoksa None."""
        latest = (
            CartAddEvent.objects.filter(cart=OuterRef("cart"))
            .filter(Q(course=OuterRef("course")) | Q(bundle=OuterRef("bundle")))
            .order_by("-created_at")
            .values("data")[:1]
        )
        return self.annotate(visitor=Subquery(latest, output_field=models.JSONField()))

    def for_course(self, course):
        """Kursu doğrudan ya da içindeki bir paketle içeren ürünler."""
        return self.filter(Q(course=course) | Q(bundle__courses=course)).distinct()

    def left_for(self, course):
        """Sepete eklenip satın alınmamış: sepet açık ya da boşaltılmış, sahibi kursa kayıtlı değil (misafirler dahil)."""
        return (
            self.for_course(course)
            .filter(cart__status__in=(CartStatus.ACTIVE, CartStatus.EMPTIED))
            .exclude(cart__user__enrollments__course=course)
        )


class CartItem(BaseModel):
    """Sepetteki ürün: bir kurs ya da bir paket (ikisinden yalnız biri)."""

    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items", verbose_name=_("sepet"))
    course = models.ForeignKey(
        "course.Course", on_delete=models.CASCADE, null=True, blank=True, related_name="cart_items", verbose_name=_("kurs")
    )
    bundle = models.ForeignKey(
        "course.Bundle", on_delete=models.CASCADE, null=True, blank=True, related_name="cart_items", verbose_name=_("paket")
    )

    objects = CartItemQuerySet.as_manager()

    class Meta:
        verbose_name = _("sepet ürünü")
        verbose_name_plural = _("sepet ürünleri")
        ordering = ("created_at",)
        constraints = [
            models.CheckConstraint(
                condition=Q(course__isnull=False, bundle__isnull=True) | Q(course__isnull=True, bundle__isnull=False),
                name="cart_item_course_xor_bundle",
            ),
            models.UniqueConstraint(fields=("cart", "course"), condition=Q(course__isnull=False), name="cart_item_unique_course"),
            models.UniqueConstraint(fields=("cart", "bundle"), condition=Q(bundle__isnull=False), name="cart_item_unique_bundle"),
        ]

    def __str__(self):
        return str(self.product)

    @property
    def product(self):
        return self.bundle if self.bundle_id else self.course


class CartItemRemovalQuerySet(models.QuerySet):
    def countable(self):
        return self.filter(cart__in=Cart.objects.countable())


class CartItemRemoval(BaseModel):
    """Sepetten çıkan ürün (istatistik için): ne zaman eklendiği ve neden çıktığı. created_at çıkma zamanıdır."""

    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="removals", verbose_name=_("sepet"))
    course = models.ForeignKey(
        "course.Course", on_delete=models.CASCADE, null=True, blank=True, related_name="cart_removals", verbose_name=_("kurs")
    )
    bundle = models.ForeignKey(
        "course.Bundle", on_delete=models.CASCADE, null=True, blank=True, related_name="cart_removals", verbose_name=_("paket")
    )
    reason = models.CharField(_("neden"), max_length=20, choices=CartRemovalReason, default=CartRemovalReason.REMOVED)
    added_at = models.DateTimeField(_("sepete eklenme"))

    objects = CartItemRemovalQuerySet.as_manager()

    class Meta:
        verbose_name = _("sepetten çıkan ürün")
        verbose_name_plural = _("sepetten çıkan ürünler")
        ordering = ("-created_at",)

    def __str__(self):
        return str(self.product)

    @property
    def product(self):
        return self.bundle if self.bundle_id else self.course


class CartAddSource(models.TextChoices):
    ADD = "add", _("Sepete ekle")
    BUY = "buy", _("Hemen satın al")


class CartAddEvent(BaseVisitorEvent):
    """Sepete her ekleme (istatistik için, silinmez): ekleyenin ağ, konum, cihaz, dil, tarayıcı ve geliş bilgileri ile
    ürün data alanında (cart.tracking). Sepet, ürün ya da üye silinse de kayıt kalır; misafir sepeti üyeninkine katılınca
    kayıt üyenin sepetine geçer. IP, core.visitor.IP_RETENTION_DAYS gün sonra maskelenir."""

    cart = models.ForeignKey(Cart, on_delete=models.SET_NULL, null=True, blank=True, related_name="add_events", verbose_name=_("sepet"))
    course = models.ForeignKey(
        "course.Course", on_delete=models.SET_NULL, null=True, blank=True, related_name="cart_add_events", verbose_name=_("kurs")
    )
    bundle = models.ForeignKey(
        "course.Bundle", on_delete=models.SET_NULL, null=True, blank=True, related_name="cart_add_events", verbose_name=_("paket")
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="cart_add_events", verbose_name=_("kullanıcı")
    )
    source = models.CharField(_("kaynak"), max_length=10, choices=CartAddSource, default=CartAddSource.ADD)

    class Meta(BaseVisitorEvent.Meta):
        verbose_name = _("sepete ekleme")
        verbose_name_plural = _("sepete eklemeler")
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("created_at",), name="cart_add_event_created"),
            GinIndex(fields=("data",), name="cart_add_event_data"),
        ]

    def __str__(self):
        return f"{self.course or self.bundle or '-'} · {timezone.localtime(self.created_at):%Y-%m-%d %H:%M}"
