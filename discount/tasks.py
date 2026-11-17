"""İndirim e-postaları (Celery): kişiye özel indirim kodunun gönderimi."""

import smtplib
from urllib.parse import urlencode

from celery import shared_task
from django.conf import settings
from django.urls import reverse
from django.utils import timezone

from mailing.emails import send_email, send_staff_email
from order.emails import absolute, recipient_context


@shared_task(autoretry_for=(smtplib.SMTPException, OSError), retry_backoff=True, max_retries=3)
def send_personal_discount(request_id):
    """Özel indirim kodu isteğine gönderilen (yeni ya da hâlâ geçerli) kod; kursları açan bağlantı kodu da uygular."""
    from discount.models import PersonalDiscountRequest
    from discount.pending import CODE_PARAM

    request = PersonalDiscountRequest.objects.select_related("discount", "user").filter(pk=request_id).first()
    if request is None or request.discount is None:
        return
    discount = request.discount
    context = recipient_context(request.user) if request.user else {"email": request.email, "greeting_name": "", "site_url": settings.SITE_URL.rstrip("/")}
    products = [course.title for course in discount.courses.order_by("sort_order", "title")] + [bundle.title for bundle in discount.bundles.order_by("sort_order", "title")]
    context.update(
        code=discount.code,
        discount_label=discount.label,
        valid_until=timezone.localtime(discount.valid_until) if discount.valid_until else None,
        audience=request.get_audience_display(),
        products=products,
        courses_url=absolute(f"{reverse('page:course_list')}?{CODE_PARAM}={discount.code}"),
        resent=request.result == "resent",
    )
    send_email("personal_discount", request.email, context, user=request.user)


@shared_task
def notify_staff_personal_discount(request_id):
    """Kişiye özel indirim kodu gönderildi: kimin (e-posta, beyan) hangi kodu aldığı tüm personele."""
    from discount.models import PersonalDiscountRequest

    request = PersonalDiscountRequest.objects.select_related("discount", "user").filter(pk=request_id).first()
    if request is None or request.discount is None or not request.is_sent:
        return
    discount = request.discount
    user = request.user
    context = {
        "email": request.email,
        "full_name": user.get_full_name().strip() if user else "",
        "is_member": user is not None,
        "audience": request.get_audience_display(),
        "code": discount.code,
        "discount_label": discount.label,
        "valid_until": timezone.localtime(discount.valid_until) if discount.valid_until else None,
        "resent": request.result == "resent",
        "requested_at": timezone.localtime(request.created_at),
        "studio_url": absolute(f"{reverse('studio:personal_discounts')}?{urlencode({'q': request.email})}"),
    }
    send_staff_email("admin_personal_discount", context)
