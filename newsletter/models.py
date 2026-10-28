import uuid

from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from core.models import BaseModel


class SubscriberStatus(models.TextChoices):
    PENDING = "pending", _("Onay bekliyor")
    CONFIRMED = "confirmed", _("Onaylı")
    UNSUBSCRIBED = "unsubscribed", _("Abonelikten çıktı")


class SubscriberQuerySet(models.QuerySet):
    def confirmed(self):
        return self.filter(status=SubscriberStatus.CONFIRMED)

    def by_email(self, email):
        return self.filter(email__iexact=(email or "").strip()).first()


class Subscriber(BaseModel):
    """Bülten abonesi. Ticari e-posta için onay metni saklanır (İYS kaydı TODO.md)."""

    email = models.EmailField(_("e-posta"))
    name = models.CharField(_("ad"), max_length=120, blank=True)
    status = models.CharField(_("durum"), max_length=20, choices=SubscriberStatus, default=SubscriberStatus.PENDING, db_index=True)
    confirm_token = models.UUIDField(_("onay anahtarı"), default=uuid.uuid4, unique=True, editable=False)
    confirmed_at = models.DateTimeField(_("onay tarihi"), null=True, blank=True)
    unsubscribed_at = models.DateTimeField(_("çıkış tarihi"), null=True, blank=True)
    source = models.CharField(_("kaynak sayfa"), max_length=200, blank=True)
    consent_text = models.TextField(_("onay metni"), blank=True)

    objects = SubscriberQuerySet.as_manager()

    class Meta:
        verbose_name = _("bülten abonesi")
        verbose_name_plural = _("bülten aboneleri")
        ordering = ("-created_at",)
        constraints = [models.UniqueConstraint(Lower("email"), name="subscriber_email_ci_unique")]

    def __str__(self):
        return self.email

    def save(self, *args, **kwargs):
        self.email = self.email.strip().lower()
        super().save(*args, **kwargs)

    def confirm(self):
        self.status = SubscriberStatus.CONFIRMED
        self.confirmed_at = timezone.now()
        self.unsubscribed_at = None
        self.save(update_fields=["status", "confirmed_at", "unsubscribed_at", "updated_at"])

    def unsubscribe(self):
        self.status = SubscriberStatus.UNSUBSCRIBED
        self.unsubscribed_at = timezone.now()
        self.save(update_fields=["status", "unsubscribed_at", "updated_at"])
