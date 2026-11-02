"""E-posta altyapısı: EMAIL_REDIRECT_TO tanımlıysa her e-posta (Django'nun kendi gönderdikleri dahil) yalnız o adrese
gider. Asıl alıcılar konu satırına ve X-Original-To başlığına yazılır. Yayına çıkarken ayar kaldırılır.

EMAIL_HOSTNAME tanımlıysa Message-ID alan adı ve SMTP EHLO adı sunucunun hostname'i yerine bu ad olur; sunucu adı
FQDN değilse (ör. `ubuntu2025srv`) bazı filtreler puan düşürür.

SendGrid'in açılma ve tıklama takibi her e-postada X-SMTPAPI başlığıyla kapatılır (hesap ayarı ne olursa olsun): takip
sitenin kendisinde (mailing.tracking, EmailLog); SendGrid'in sarması şifre bağlantılarını ct.sendgrid.net üzerinden
geçirir ve kendi sunucusunda saklar."""

import json
from email.utils import make_msgid

from django.conf import settings
from django.core.mail.backends import console, locmem, smtp

SENDGRID_NO_TRACKING = json.dumps(
    {"filters": {"clicktrack": {"settings": {"enable": 0}}, "opentrack": {"settings": {"enable": 0}}}}
)


class RedirectMixin:
    def send_messages(self, email_messages):
        target = getattr(settings, "EMAIL_REDIRECT_TO", "")
        hostname = getattr(settings, "EMAIL_HOSTNAME", "")
        for message in email_messages:
            message.extra_headers.setdefault("X-SMTPAPI", SENDGRID_NO_TRACKING)
            if hostname:
                # Django, extra_headers'da Message-ID varsa kendi üretmez (alan adı sunucu hostname'i olurdu).
                message.extra_headers.setdefault("Message-ID", make_msgid(domain=hostname))
            if target:
                original = ", ".join([*message.to, *message.cc, *message.bcc])
                message.subject = f"[Test → {original}] {message.subject}"
                message.extra_headers["X-Original-To"] = original
                message.to, message.cc, message.bcc = [target], [], []
        return super().send_messages(email_messages)


class RedirectSMTPBackend(RedirectMixin, smtp.EmailBackend):
    @property
    def connection_class(self):
        """SMTP bağlantısını EMAIL_HOSTNAME ile EHLO yapacak şekilde sarar; Django local_hostname için ayar vermez."""
        base = super().connection_class
        hostname = getattr(settings, "EMAIL_HOSTNAME", "")
        if not hostname:
            return base

        def connect(host, port, **params):
            return base(host, port, **{**params, "local_hostname": hostname})

        return connect


class RedirectConsoleBackend(RedirectMixin, console.EmailBackend):
    pass


class RedirectLocmemBackend(RedirectMixin, locmem.EmailBackend):
    """Testler için: e-postalar bellekte (django.core.mail.outbox) tutulur."""
