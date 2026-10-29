"""Bülten e-postaları (Celery)."""

import smtplib

from celery import shared_task

from mailing.emails import send_email
from newsletter.models import Subscriber, SubscriberStatus


@shared_task(autoretry_for=(smtplib.SMTPException, OSError), retry_backoff=True, max_retries=3)
def send_confirmation(subscriber_id):
    """Onay bekleyen aboneye onay bağlantılı e-posta (çift onay). Bu arada onaylanmış ya da çıkmışsa gönderilmez."""
    subscriber = Subscriber.objects.filter(pk=subscriber_id, status=SubscriberStatus.PENDING).first()
    if subscriber is None:
        return
    send_email("newsletter_confirm", subscriber.email, subscriber.email_context())


@shared_task
def send_issue(issue_id):
    """Bülten sayısını kitlesindeki onaylı abonelere gönderir (Issue.start_sending sonrası). Her alıcı mailing.EmailLog'a yazılır."""
    from mailing.emails import send_batch
    from newsletter.models import Issue, IssueStatus

    issue = Issue.objects.select_related("batch").filter(pk=issue_id, status=IssueStatus.SENDING).first()
    if issue is None:
        return
    # Yarıda kalıp yeniden çalışırsa daha önce gönderilenlere ikinci kez gitmesin.
    already = {email.lower() for email in issue.batch.logs.values_list("to_email", flat=True)}
    recipients = [
        (subscriber.email, issue.email_context(subscriber))
        for subscriber in issue.recipients().order_by("created_at", "id")
        if subscriber.email.lower() not in already
    ]
    send_batch("newsletter", recipients, subject=issue.headline, batch=issue.batch)
    issue.mark_sent()
