"""Destek talepleri: konu + mesaj zinciri. Üye talebini panelden (Destek) yazar ve yanıtlar; hesabı olmayan kişi formu
doldurur, yanıt e-postayla gelir ve e-postayı yanıtlayınca destek adresine (SUPPORT_EMAIL) döner.

Giriş yapmadan yazılan e-posta kayıtlı bir hesaba aitse talep o hesaba bağlanır; yanıt panel bağlantısıyla gider.
"""

from functools import partial

from django.conf import settings
from django.db import models, transaction
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from core.models import BaseModel

MESSAGE_MAX_LENGTH = 1000
STAFF_NAME = "Hakan Yalçınkaya"


class TicketStatus(models.TextChoices):
    OPEN = "open", _("Yanıt bekliyor")
    ANSWERED = "answered", _("Yanıtlandı")
    CLOSED = "closed", _("Kapandı")


class TicketQuerySet(models.QuerySet):
    def for_user(self, user):
        """Üyenin kendi talepleri; giriş yapmamışsa hiçbiri."""
        return self.filter(user=user) if user.is_authenticated else self.none()

    def awaiting(self):
        """Yanıt bekleyenler (stüdyo menüsündeki rozet)."""
        return self.filter(status=TicketStatus.OPEN)

    def unread(self):
        """Üyenin henüz görmediği yanıtı olanlar (site menüsündeki "yeni mesaj" rozeti)."""
        return self.filter(has_unread_reply=True)


class Ticket(BaseModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("üye"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="support_tickets",
    )
    name = models.CharField(_("ad soyad"), max_length=150)
    email = models.EmailField(_("e-posta"))
    subject = models.CharField(_("konu"), max_length=150)
    status = models.CharField(_("durum"), max_length=10, choices=TicketStatus.choices, default=TicketStatus.OPEN, db_index=True)
    has_unread_reply = models.BooleanField(_("okunmamış yanıt"), default=False)
    last_message_at = models.DateTimeField(_("son mesaj"), default=timezone.now, db_index=True)

    objects = TicketQuerySet.as_manager()

    class Meta:
        verbose_name = _("destek talebi")
        verbose_name_plural = _("destek talepleri")
        ordering = ("-last_message_at",)

    def __str__(self):
        return self.subject

    def get_absolute_url(self):
        return reverse("support:ticket_detail", args=[self.pk])

    def get_studio_url(self):
        return reverse("studio:support_detail", args=[self.pk])

    @property
    def is_guest(self):
        """Hesaba bağlı değil: yanıt e-postayla gider, e-posta yanıtı destek adresine döner."""
        return self.user_id is None

    @property
    def is_closed(self):
        return self.status == TicketStatus.CLOSED

    @property
    def status_badge(self):
        return {
            TicketStatus.OPEN: "text-bg-warning",
            TicketStatus.ANSWERED: "text-bg-success",
            TicketStatus.CLOSED: "text-bg-secondary",
        }[self.status]

    @classmethod
    @transaction.atomic
    def open(cls, *, subject, body, user=None, name="", email=""):
        """Yeni talep ve ilk mesajı; yöneticiye bildirim gider. Giriş yapmamış kişinin e-postası kayıtlı bir hesaba
        aitse talep o hesaba bağlanır."""
        from account.models import User

        if user is not None and user.is_authenticated:
            name, email = user.get_full_name() or user.email, user.email
        else:
            user = User.objects.with_email(email).first()
            email = user.email if user else email
        ticket = cls.objects.create(user=user, name=name, email=email, subject=subject)
        ticket._add_message(body, author=user, from_staff=False)
        return ticket

    @transaction.atomic
    def add_customer_message(self, body):
        """Üyenin panelden yanıtı; kapalı talep yeniden açılır, yöneticiye bildirim gider."""
        self.status = TicketStatus.OPEN
        return self._add_message(body, author=self.user, from_staff=False)

    @transaction.atomic
    def reply(self, author, body):
        """Yönetici yanıtı: talep "yanıtlandı" olur, üyeye "yeni mesaj" rozeti ve e-posta gider."""
        self.status = TicketStatus.ANSWERED
        self.has_unread_reply = True
        return self._add_message(body, author=author, from_staff=True)

    def set_closed(self, closed):
        self.status = TicketStatus.CLOSED if closed else TicketStatus.OPEN
        self.save(update_fields=["status", "updated_at"])

    def mark_read(self):
        """Üye talebi açınca yanıt okunmuş sayılır."""
        if self.has_unread_reply:
            self.has_unread_reply = False
            self.save(update_fields=["has_unread_reply", "updated_at"])

    def _add_message(self, body, *, author, from_staff):
        from support.tasks import notify_admin, send_reply

        message = TicketMessage.objects.create(ticket=self, author=author, from_staff=from_staff, body=body)
        self.last_message_at = message.created_at
        self.save(update_fields=["status", "has_unread_reply", "last_message_at", "updated_at"])
        task = send_reply if from_staff else notify_admin
        transaction.on_commit(partial(task.delay, str(message.pk)))
        return message


class TicketMessage(BaseModel):
    ticket = models.ForeignKey(Ticket, verbose_name=_("talep"), on_delete=models.CASCADE, related_name="messages")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name=_("yazan"), null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    from_staff = models.BooleanField(_("yönetici yanıtı"), default=False)
    body = models.TextField(_("mesaj"), max_length=MESSAGE_MAX_LENGTH)

    class Meta:
        verbose_name = _("destek mesajı")
        verbose_name_plural = _("destek mesajları")
        ordering = ("created_at",)

    def __str__(self):
        return f"{self.ticket} · {self.author_name}"

    @property
    def author_name(self):
        return STAFF_NAME if self.from_staff else self.ticket.name
