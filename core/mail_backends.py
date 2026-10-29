"""E-posta altyapısı: EMAIL_REDIRECT_TO tanımlıysa her e-posta (Django'nun kendi gönderdikleri dahil) yalnız o adrese
gider. Asıl alıcılar konu satırına ve X-Original-To başlığına yazılır. Yayına çıkarken ayar kaldırılır."""

from django.conf import settings
from django.core.mail.backends import console, locmem, smtp


class RedirectMixin:
    def send_messages(self, email_messages):
        target = getattr(settings, "EMAIL_REDIRECT_TO", "")
        if target:
            for message in email_messages:
                original = ", ".join([*message.to, *message.cc, *message.bcc])
                message.subject = f"[Test → {original}] {message.subject}"
                message.extra_headers["X-Original-To"] = original
                message.to, message.cc, message.bcc = [target], [], []
        return super().send_messages(email_messages)


class RedirectSMTPBackend(RedirectMixin, smtp.EmailBackend):
    pass


class RedirectConsoleBackend(RedirectMixin, console.EmailBackend):
    pass


class RedirectLocmemBackend(RedirectMixin, locmem.EmailBackend):
    """Testler için: e-postalar bellekte (django.core.mail.outbox) tutulur."""
