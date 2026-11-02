"""Sipariş e-postaları (Celery)."""

import smtplib

from celery import shared_task
from django.conf import settings

from mailing.emails import send_email
from order.emails import order_notice_context, purchase_confirmation_context

# Stüdyoda durum değişince alıcıya giden bilgilendirme (Order.set_status, notify).
NOTICE_EMAILS = {"refunded": "refund_processed", "cancelled": "order_cancelled"}


@shared_task(autoretry_for=(smtplib.SMTPException, OSError), retry_backoff=True, max_retries=3)
def send_purchase_confirmation(order_id):
    """Ödemesi onaylanan sipariş: alıcıya satın alma onayı (Order.mark_paid sonrası). Yanıtlanınca destek adresine döner.
    Siparişler hesaba bağlıdır (misafirin hesabı "Kartla öde"de açılır); hesapsız eski kayıt olursa gönderilmez."""
    from order.models import Order

    order = Order.objects.paid().select_related("user").filter(pk=order_id).first()
    if order is None or order.user is None:
        return
    send_email(
        "purchase_confirmation", order.email, purchase_confirmation_context(order), user=order.user, reply_to=[settings.SUPPORT_EMAIL]
    )


@shared_task(autoretry_for=(smtplib.SMTPException, OSError), retry_backoff=True, max_retries=3)
def send_order_notice(order_id, access_revoked=False):
    """İade ya da iptal edilen sipariş: alıcıya bilgilendirme. Gönderilene kadar durum yine değiştiyse gönderilmez."""
    from order.models import Order

    order = Order.objects.select_related("user").filter(pk=order_id, status__in=NOTICE_EMAILS).first()
    if order is None or order.user is None:
        return
    send_email(
        NOTICE_EMAILS[order.status],
        order.email,
        order_notice_context(order, access_revoked),
        user=order.user,
        reply_to=[settings.SUPPORT_EMAIL],
    )
