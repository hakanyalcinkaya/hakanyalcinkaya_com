"""Destek e-postaları (Celery): yönetici yanıtı müşteriye, müşteri mesajı yöneticiye."""

import smtplib

from celery import shared_task
from django.conf import settings

from mailing.emails import send_email
from order.emails import absolute, recipient_context


def _message(message_id):
    from support.models import TicketMessage

    return TicketMessage.objects.select_related("ticket__user").filter(pk=message_id).first()


@shared_task(autoretry_for=(smtplib.SMTPException, OSError), retry_backoff=True, max_retries=3)
def send_reply(message_id):
    """Yönetici yanıtı. Hesaba bağlı talepte no-reply'dan panel bağlantısı gider (yanıt panelden yazılır); hesabı
    olmayana yanıtın kendisi destek adresinden gider, e-postayı yanıtlayınca oraya döner."""
    message = _message(message_id)
    if message is None:
        return
    ticket = message.ticket
    context = {"subject": ticket.subject, "reply_text": message.body}
    if ticket.user is not None:
        context.update(recipient_context(ticket.user), ticket_url=absolute(ticket.get_absolute_url()))
        send_email("support_reply", ticket.user.email, context, user=ticket.user)
        return
    first = ticket.name.split()[0] if ticket.name.strip() else ""
    earlier = ticket.messages.exclude(pk=message.pk).filter(from_staff=False).order_by("-created_at").first()
    context.update(
        greeting_name=first,
        full_name=ticket.name,
        email=ticket.email,
        site_url=settings.SITE_URL.rstrip("/"),
        original_text=earlier.body if earlier else "",
    )
    send_email(
        "support_reply_guest",
        ticket.email,
        context,
        from_email=settings.SUPPORT_FROM_EMAIL,
        reply_to=[settings.SUPPORT_EMAIL],
    )


@shared_task(autoretry_for=(smtplib.SMTPException, OSError), retry_backoff=True, max_retries=3)
def notify_admin(message_id):
    """Yeni talep ya da üyenin yeni mesajı: yöneticiye özet ve stüdyo bağlantısı."""
    message = _message(message_id)
    if message is None:
        return
    ticket = message.ticket
    context = {
        "subject": ticket.subject,
        "sender_name": ticket.name,
        "sender_email": ticket.email,
        "is_member": ticket.user_id is not None,
        "is_new": ticket.messages.count() == 1,
        "message_text": message.body,
        "studio_url": absolute(ticket.get_studio_url()),
    }
    send_email("admin_support_message", settings.SUPPORT_EMAIL, context)
