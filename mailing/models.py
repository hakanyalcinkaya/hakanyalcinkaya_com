import uuid

from django.conf import settings
from django.db import models
from django.db.models import Count, F, Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from core.models import BaseModel


class EmailStatus(models.TextChoices):
    QUEUED = "queued", _("Gönderiliyor")
    SENT = "sent", _("Gönderildi")
    FAILED = "failed", _("Hata")


class EmailEventKind(models.TextChoices):
    SENT = "sent", _("Gönderildi")
    FAILED = "failed", _("Hata")
    OPENED = "opened", _("Açıldı")
    CLICKED = "clicked", _("Tıklandı")
    UNSUBSCRIBED = "unsubscribed", _("Abonelikten çıktı")


class EmailLogQuerySet(models.QuerySet):
    def single(self):
        """Tekil e-postalar (toplu gönderimin parçası olmayanlar)."""
        return self.filter(batch__isnull=True)

    def for_token(self, value):
        """Takip anahtarıyla eşleşen kayıt; anahtar geçersizse boş."""
        try:
            return self.filter(token=uuid.UUID(str(value)))
        except ValueError:
            return self.none()

    @staticmethod
    def _counts():
        return dict(
            total=Count("pk"),
            sent=Count("pk", filter=Q(status=EmailStatus.SENT)),
            failed=Count("pk", filter=Q(status=EmailStatus.FAILED)),
            opened=Count("pk", filter=Q(first_opened_at__isnull=False)),
            clicked=Count("pk", filter=Q(first_clicked_at__isnull=False)),
        )

    @staticmethod
    def _with_rates(row):
        """Açılma ve tıklama oranı (%), gönderilen e-postalara göre; her e-posta bir kez sayılır."""
        sent = row["sent"]
        row["open_rate"] = round(row["opened"] * 100 / sent) if sent else 0
        row["click_rate"] = round(row["clicked"] * 100 / sent) if sent else 0
        return row

    def stats_by_template(self):
        """Şablon başına gönderim, hata, açılan ve tıklanan e-posta sayıları ve oranları."""
        rows = self.values("template").annotate(**self._counts()).order_by("-total", "template")
        return [self._with_rates(dict(row)) for row in rows]

    def stats(self):
        """Tüm e-postaların toplamları ve oranları."""
        return self._with_rates(self.aggregate(**self._counts()))


class EmailBatchQuerySet(models.QuerySet):
    def with_stats(self):
        """Alıcı, gönderilen, hata, açılan ve tıklanan e-posta sayıları (her alıcı bir kez sayılır)."""
        return self.annotate(
            # Olaylar da birleştirildiği için satırlar çoğalır; her kayıt bir kez sayılsın diye distinct.
            recipients=Count("logs", distinct=True),
            sent=Count("logs", distinct=True, filter=Q(logs__status=EmailStatus.SENT)),
            failed=Count("logs", distinct=True, filter=Q(logs__status=EmailStatus.FAILED)),
            opened=Count("logs", distinct=True, filter=Q(logs__first_opened_at__isnull=False)),
            clicked=Count("logs", distinct=True, filter=Q(logs__first_clicked_at__isnull=False)),
            unsubscribed=Count("logs", distinct=True, filter=Q(logs__events__kind=EmailEventKind.UNSUBSCRIBED)),
        )


class EmailBatch(BaseModel):
    """Toplu gönderim (ör. bir bülten sayısı): aynı e-posta birçok alıcıya; her alıcının kaydı ayrı EmailLog."""

    template = models.CharField(_("şablon"), max_length=60, db_index=True)
    subject = models.CharField(_("konu"), max_length=300)
    planned = models.PositiveIntegerField(_("planlanan alıcı"), default=0)
    finished_at = models.DateTimeField(_("bitiş"), null=True, blank=True)

    objects = EmailBatchQuerySet.as_manager()

    class Meta:
        verbose_name = _("toplu gönderim")
        verbose_name_plural = _("toplu gönderimler")
        ordering = ("-created_at",)

    def __str__(self):
        return self.subject

    def rate(self, count):
        sent = getattr(self, "sent", 0)
        return round(count * 100 / sent) if sent else 0

    @property
    def open_rate(self):
        return self.rate(getattr(self, "opened", 0))

    @property
    def click_rate(self):
        return self.rate(getattr(self, "clicked", 0))

    def finish(self, subject=""):
        """Gönderimi bitirir; konu verilmediyse ilk alıcının konusu (kişiselleştirilmemiş varsayılır) yazılır."""
        first = self.logs.order_by("created_at").first()
        if not subject and first:
            self.subject = first.subject
        self.finished_at = timezone.now()
        self.save(update_fields=["subject", "finished_at", "updated_at"])


class EmailLog(BaseModel):
    """Sistemden giden bir e-posta: içeriği (gizli bağlantılar maskelenmiş), durumu ve açılma/tıklama sayıları.

    `token` takip adreslerinde (açılma görseli, tıklama yönlendirmesi) kullanılır; e-postayı tahmin edilemez biçimde tanır.
    """

    token = models.UUIDField(_("takip anahtarı"), default=uuid.uuid4, unique=True, editable=False)
    batch = models.ForeignKey(
        EmailBatch,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="logs",
        verbose_name=_("toplu gönderim"),
        help_text=_("Boşsa tekil e-posta (şifre, satın alma vb.)."),
    )
    template = models.CharField(_("şablon"), max_length=60, db_index=True)
    to_email = models.EmailField(_("alıcı"))
    delivered_to = models.EmailField(_("gönderildiği adres"), help_text=_("Test yönlendirmesi açıksa alıcıdan farklıdır."))
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="email_logs",
        verbose_name=_("kullanıcı"),
    )
    subject = models.CharField(_("konu"), max_length=300)
    text_body = models.TextField(_("düz metin"))
    html_body = models.TextField(_("HTML"))
    status = models.CharField(_("durum"), max_length=10, choices=EmailStatus, default=EmailStatus.QUEUED, db_index=True)
    error = models.TextField(_("hata"), blank=True)
    sent_at = models.DateTimeField(_("gönderim"), null=True, blank=True)
    open_count = models.PositiveIntegerField(_("açılma"), default=0)
    first_opened_at = models.DateTimeField(_("ilk açılma"), null=True, blank=True)
    click_count = models.PositiveIntegerField(_("tıklama"), default=0)
    first_clicked_at = models.DateTimeField(_("ilk tıklama"), null=True, blank=True)

    objects = EmailLogQuerySet.as_manager()

    class Meta:
        verbose_name = _("e-posta kaydı")
        verbose_name_plural = _("e-posta kayıtları")
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.template} → {self.to_email}"

    def _record(self, kind, url="", user_agent=""):
        EmailEvent.objects.create(log=self, kind=kind, url=url[:500], user_agent=user_agent[:300])

    def mark_sent(self):
        self.status = EmailStatus.SENT
        self.sent_at = timezone.now()
        self.save(update_fields=["status", "sent_at", "updated_at"])
        self._record(EmailEventKind.SENT)

    def mark_failed(self, error):
        self.status = EmailStatus.FAILED
        self.error = str(error)[:2000]
        self.save(update_fields=["status", "error", "updated_at"])
        self._record(EmailEventKind.FAILED)

    def record_open(self, user_agent=""):
        now = timezone.now()
        EmailLog.objects.filter(pk=self.pk).update(open_count=F("open_count") + 1, updated_at=now)
        EmailLog.objects.filter(pk=self.pk, first_opened_at__isnull=True).update(first_opened_at=now)
        self._record(EmailEventKind.OPENED, user_agent=user_agent)

    def record_click(self, url, user_agent=""):
        now = timezone.now()
        EmailLog.objects.filter(pk=self.pk).update(click_count=F("click_count") + 1, updated_at=now)
        EmailLog.objects.filter(pk=self.pk, first_clicked_at__isnull=True).update(first_clicked_at=now)
        # Bağlantıya tıklayan e-postayı açmıştır (görseller kapalı olsa bile).
        EmailLog.objects.filter(pk=self.pk, first_opened_at__isnull=True).update(first_opened_at=now)
        self._record(EmailEventKind.CLICKED, url=url, user_agent=user_agent)

    def record_unsubscribe(self):
        self._record(EmailEventKind.UNSUBSCRIBED)


class EmailEvent(BaseModel):
    log = models.ForeignKey(EmailLog, on_delete=models.CASCADE, related_name="events", verbose_name=_("e-posta"))
    kind = models.CharField(_("olay"), max_length=20, choices=EmailEventKind, db_index=True)
    url = models.URLField(_("bağlantı"), max_length=500, blank=True)
    user_agent = models.CharField(_("tarayıcı"), max_length=300, blank=True)

    class Meta:
        verbose_name = _("e-posta olayı")
        verbose_name_plural = _("e-posta olayları")
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.log} · {self.get_kind_display()}"
