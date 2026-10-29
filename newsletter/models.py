import uuid
from datetime import timedelta
from functools import partial

from django.conf import settings
from django.db import IntegrityError, models, transaction
from django.db.models.functions import Lower
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from core.models import BaseModel


# Abone olurken gösterilen metin; onayın kanıtı olarak abone kaydında saklanır (İYS / KVKK).
CONSENT_TEXT = (
    "Yeni yazılım kursları, faydalı kaynaklar ve geliştirici içerikleri e-posta kutuna gelsin. "
    "İstediğin zaman abonelikten çıkabilirsin."
)
# Aynı adrese bu süre içinde ikinci onay e-postası gönderilmez (formu art arda göndermeye karşı).
RESEND_AFTER = timedelta(minutes=1)


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

    @classmethod
    def subscribe(cls, email, name="", source="", consent_text=CONSENT_TEXT):
        """Abonelik isteği: kayıt "onay bekliyor" olur ve onay e-postası sıraya alınır.

        Onaylı adres değişmez ve e-posta gitmez; kullanıcıya her durumda aynı sayfa gösterildiği için adresin listede
        olup olmadığı dışarıdan anlaşılmaz. Abonelikten çıkmış adres yeniden onaya düşer. Döner: (abone, e-posta gönderildi mi).
        """
        subscriber = cls.objects.by_email(email)
        if subscriber is None:
            try:
                with transaction.atomic():
                    subscriber = cls.objects.create(email=email, name=name, source=source, consent_text=consent_text)
            except IntegrityError:
                # Aynı adres eş zamanlı kaydedildi; var olan kayıtla devam edilir.
                subscriber = cls.objects.by_email(email)
            else:
                subscriber.queue_confirmation()
                return subscriber, True
        if subscriber.status == SubscriberStatus.CONFIRMED:
            return subscriber, False
        if subscriber.status == SubscriberStatus.PENDING and subscriber.updated_at > timezone.now() - RESEND_AFTER:
            return subscriber, False
        subscriber.status = SubscriberStatus.PENDING
        subscriber.unsubscribed_at = None
        subscriber.name = name or subscriber.name
        subscriber.source = source or subscriber.source
        subscriber.consent_text = consent_text
        subscriber.save()
        subscriber.queue_confirmation()
        return subscriber, True

    @classmethod
    def state_for(cls, user, session_email=""):
        """Bülten kutusunda form yerine gösterilecek durum.

        Giriş yapmış kullanıcının kendi adresinin durumu gösterilir ("subscribed" / "pending"). Giriş yapmamış
        ziyaretçide yalnız bu tarayıcıdan az önce abone olunduysa "sent" döner; adresin onaylı olup olmadığı
        söylenmez (başkasının adresi yazılmış olabilir). Diğer herkes formu görür (None).
        """
        if user.is_authenticated:
            subscriber = cls.objects.by_email(user.email)
            if subscriber is not None and subscriber.status == SubscriberStatus.CONFIRMED:
                return {"status": "subscribed", "email": subscriber.email, "unsubscribe_path": subscriber.unsubscribe_path()}
            if subscriber is not None and subscriber.status == SubscriberStatus.PENDING:
                return {"status": "pending", "email": subscriber.email}
            return None
        if session_email:
            return {"status": "sent", "email": session_email}
        return None

    def queue_confirmation(self):
        from newsletter.tasks import send_confirmation

        transaction.on_commit(partial(send_confirmation.delay, str(self.pk)))

    @property
    def is_confirmed(self):
        return self.status == SubscriberStatus.CONFIRMED

    def _absolute(self, name):
        return settings.SITE_URL.rstrip("/") + reverse(name, kwargs={"token": self.confirm_token})

    def confirm_url(self):
        return self._absolute("page:newsletter_activate")

    def unsubscribe_path(self):
        return reverse("page:newsletter_unsubscribe_link", kwargs={"token": self.confirm_token})

    def unsubscribe_url(self):
        return settings.SITE_URL.rstrip("/") + self.unsubscribe_path()

    def email_context(self):
        """Bülten e-postalarının değişkenleri (bkz. mailing.emails: newsletter_confirm, newsletter)."""
        return {
            "name": self.name,
            "email": self.email,
            "confirm_url": self.confirm_url(),
            "unsubscribe_url": self.unsubscribe_url(),
            "site_url": settings.SITE_URL.rstrip("/"),
        }

    def confirm(self):
        self.status = SubscriberStatus.CONFIRMED
        self.confirmed_at = timezone.now()
        self.unsubscribed_at = None
        self.save(update_fields=["status", "confirmed_at", "unsubscribed_at", "updated_at"])

    def unsubscribe(self):
        self.status = SubscriberStatus.UNSUBSCRIBED
        self.unsubscribed_at = timezone.now()
        self.save(update_fields=["status", "unsubscribed_at", "updated_at"])
