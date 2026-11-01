"""Sipariş e-postaları (Celery)."""

import smtplib

from celery import shared_task
from django.conf import settings

from mailing.emails import send_email
from order.emails import purchase_confirmation_context


@shared_task(autoretry_for=(smtplib.SMTPException, OSError), retry_backoff=True, max_retries=3)
def send_purchase_confirmation(order_id):
    """Ödemesi onaylanan sipariş: alıcıya satın alma onayı (Order.mark_paid sonrası). Yanıtlanınca destek adresine döner.
    Hesabı olmayan alıcının siparişi gönderilmez: hesabı açılınca (misafir siparişi akışı) gönderilmeli."""
    from order.models import Order

    order = Order.objects.paid().select_related("user").filter(pk=order_id).first()
    if order is None or order.user is None:
        return
    send_email(
        "purchase_confirmation", order.email, purchase_confirmation_context(order), user=order.user, reply_to=[settings.SUPPORT_EMAIL]
    )
