"""Bülten e-postaları (Celery)."""

import smtplib

from celery import shared_task

from core.emails import send_email
from newsletter.models import Subscriber, SubscriberStatus


@shared_task(autoretry_for=(smtplib.SMTPException, OSError), retry_backoff=True, max_retries=3)
def send_confirmation(subscriber_id):
    """Onay bekleyen aboneye onay bağlantılı e-posta (çift onay). Bu arada onaylanmış ya da çıkmışsa gönderilmez."""
    subscriber = Subscriber.objects.filter(pk=subscriber_id, status=SubscriberStatus.PENDING).first()
    if subscriber is None:
        return
    send_email("newsletter_confirm", subscriber.email, subscriber.email_context())
