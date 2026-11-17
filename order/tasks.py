"""Sipariş e-postaları (Celery)."""

import smtplib

from celery import shared_task
from django.conf import settings

from django.urls import reverse

from mailing.emails import send_email, send_staff_email
from order.emails import absolute, order_items_context, order_notice_context, purchase_confirmation_context, recipient_context

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


@shared_task
def notify_staff_new_order(order_id):
    """Ödemesi onaylanan (hediye olmayan) sipariş: alıcı, ürünler ve tutar tüm personele; stüdyodaki sipariş bağlantısıyla."""
    from order.models import Order

    order = Order.objects.paid().select_related("user").filter(pk=order_id).first()
    if order is None or order.is_gift:
        return
    context = {
        **(recipient_context(order.user) if order.user else {"email": order.email, "full_name": ""}),
        **order_items_context([order]),
        "purchased_at": order.paid_at,
        "admin_url": absolute(reverse("studio:order_detail", args=[order.pk])),
    }
    send_staff_email("admin_new_order", context)
