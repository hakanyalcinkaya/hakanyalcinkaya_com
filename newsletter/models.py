import re
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

    def status_counts(self):
        """Durum başına abone sayısı ve toplam: {"all": .., "confirmed": .., ...}."""
        counts = {value: models.Count("pk", filter=models.Q(status=value)) for value in SubscriberStatus.values}
        return self.aggregate(all=models.Count("pk"), **counts)

    def with_unsubscribe_email(self):
        """Abonelikten çıkılan e-posta (en son; bağlantıyla çıkıldıysa): unsubscribe_log_id, unsubscribe_log_subject."""
        from mailing.models import EmailEvent, EmailEventKind

        events = EmailEvent.objects.filter(
            kind=EmailEventKind.UNSUBSCRIBED, log__to_email__iexact=models.OuterRef("email")
        ).order_by("-created_at")
        return self.annotate(
            unsubscribe_log_id=models.Subquery(events.values("log_id")[:1]),
            unsubscribe_log_subject=models.Subquery(events.values("log__subject")[:1]),
        )


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


# Bülten metinlerinde (başlık, giriş, içerik) kullanılabilen alanlar: {{ ad }} yazılır, her aboneye kendi değeri konur.
# {{ ad|dostum }}: değer boşsa | sonrasındaki metin yazılır. Tanımsız alan olduğu gibi kalır.
PERSONALIZATION_FIELDS = {
    "ad": _("Abonenin adı (ilk kelime)"),
    "ad_soyad": _("Abonenin yazdığı tam ad"),
    "eposta": _("Abonenin e-posta adresi"),
    "site": _("Sitenin adresi"),
}
PLACEHOLDER_RE = re.compile(r"\{\{\s*(\w+)\s*(?:\|\s*([^}]*?)\s*)?\}\}")


def personalize(text, values):
    """{{ alan }} ve {{ alan|yedek }} yer tutucularını values'taki değerlerle doldurur."""

    def replace(match):
        name, fallback = match.group(1), match.group(2)
        if name not in values:
            return match.group(0)
        return values[name] or (fallback or "")

    return PLACEHOLDER_RE.sub(replace, text or "")


class AudienceKind(models.TextChoices):
    ALL = "all", _("Tüm aboneler")
    BUYERS = "buyers", _("Yalnız satın alanlar")
    NON_BUYERS = "non_buyers", _("Yalnız satın almayanlar")
    SUBSCRIBERS = "subscribers", _("Sadece aboneler")


class IssueStatus(models.TextChoices):
    DRAFT = "draft", _("Taslak")
    SENDING = "sending", _("Gönderiliyor")
    SENT = "sent", _("Gönderildi")


class Issue(BaseModel):
    """Bülten sayısı: Stüdyo'da yazılır, onaylı abonelere toplu gönderilir (mailing.EmailBatch). Gönderildikten sonra
    değiştirilmez; alıcılar ve oranlar toplu gönderim kaydındadır."""

    headline = models.CharField(_("başlık"), max_length=200, help_text=_("E-postanın konusu da budur."))
    intro = models.TextField(_("giriş"), blank=True)
    content = models.TextField(_("içerik"), blank=True, help_text=_("Markdown."))
    cta_label = models.CharField(_("düğme yazısı"), max_length=60, blank=True)
    cta_url = models.URLField(_("düğme bağlantısı"), blank=True)
    audience = models.CharField(_("kitle"), max_length=12, choices=AudienceKind, default=AudienceKind.ALL)
    courses = models.ManyToManyField(
        "course.Course", blank=True, related_name="+", verbose_name=_("eğitimler"), help_text=_("Boşsa bütün eğitimler.")
    )
    categories = models.ManyToManyField("course.Category", blank=True, related_name="+", verbose_name=_("kategoriler"))
    min_progress = models.PositiveSmallIntegerField(_("en az bitirme (%)"), null=True, blank=True)
    max_progress = models.PositiveSmallIntegerField(_("en çok bitirme (%)"), null=True, blank=True)
    status = models.CharField(_("durum"), max_length=10, choices=IssueStatus, default=IssueStatus.DRAFT, db_index=True)
    batch = models.OneToOneField(
        "mailing.EmailBatch",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="issue",
        verbose_name=_("toplu gönderim"),
    )
    sent_at = models.DateTimeField(_("gönderim"), null=True, blank=True)

    class Meta:
        verbose_name = _("bülten sayısı")
        verbose_name_plural = _("bülten sayıları")
        ordering = ("-created_at",)

    def __str__(self):
        return self.headline

    def get_absolute_url(self):
        return reverse("studio:newsletter_edit", kwargs={"issue_id": self.pk})

    @property
    def is_draft(self):
        return self.status == IssueStatus.DRAFT

    def recipients(self):
        """Gideceği onaylı aboneler (kitle, eğitim/kategori ve bitirme oranına göre; bkz. newsletter.audience)."""
        from newsletter import audience

        return audience.subscribers(
            self.audience, self.courses.all(), self.categories.all(), self.min_progress, self.max_progress
        )

    @staticmethod
    def personalization_values(subscriber):
        name = (subscriber.name or "").strip()
        return {
            "ad": name.split()[0] if name else "",
            "ad_soyad": name,
            "eposta": subscriber.email,
            "site": settings.SITE_URL.rstrip("/"),
        }

    def email_context(self, subscriber):
        """Bir abone için "newsletter" e-postasının değişkenleri (bkz. mailing.emails); metinlerdeki {{ ad }} gibi alanlar
        aboneye göre doldurulur (PERSONALIZATION_FIELDS)."""
        from core.markup import render_markdown

        values = self.personalization_values(subscriber)
        content = personalize(self.content, values)
        return {
            **subscriber.email_context(),
            "headline": personalize(self.headline, values),
            "intro": personalize(self.intro, values),
            "content_html": render_markdown(content),
            "content_text": content,
            "cta_label": self.cta_label,
            "cta_url": self.cta_url,
        }

    def start_sending(self):
        """Taslağı "gönderiliyor"a alır ve toplu gönderim kaydını açar; zaten başlamışsa False (çift tıklamaya karşı)."""
        from mailing.models import EmailBatch

        with transaction.atomic():
            issue = Issue.objects.select_for_update().get(pk=self.pk)
            if issue.status != IssueStatus.DRAFT:
                return False
            batch = EmailBatch.objects.create(
                template="newsletter", subject=self.headline, planned=self.recipients().count()
            )
            Issue.objects.filter(pk=self.pk).update(status=IssueStatus.SENDING, batch=batch, updated_at=timezone.now())
        self.refresh_from_db()
        return True

    def mark_sent(self):
        self.status = IssueStatus.SENT
        self.sent_at = timezone.now()
        self.save(update_fields=["status", "sent_at", "updated_at"])
