from datetime import timedelta

from django import template
from django.utils import timezone
from django.utils.timesince import timesince
from django.utils.translation import gettext as _

from core.duration import clock, hours_minutes
from core.money import format_try
from core.site_url import absolute_url

register = template.Library()


@register.filter
def money(amount):
    return format_try(amount)


@register.filter
def lesson_clock(seconds):
    return clock(seconds)


@register.filter
def total_minutes(minutes):
    return hours_minutes(minutes)


@register.filter
def ago(value):
    """Göreli zaman, tek birimle: "az önce", "3 saat önce", "1 gün önce", "2 ay önce"."""
    if not value:
        return ""
    if timezone.now() - value < timedelta(minutes=1):
        return _("az önce")
    return _("%(delta)s önce") % {"delta": timesince(value, depth=1)}


@register.filter
def absolute(path):
    """Statik ya da site içi yolu SITE_URL ile mutlak adrese çevirir (og:image, canonical)."""
    return absolute_url(path)


@register.filter
def share_image(image):
    """Paylaşım görseli (og:image): sayfadaki WebP kapağın aynı adlı JPEG'i; bazı platformlar WebP önizleme göstermez."""
    return image.removesuffix(".webp") + ".jpg" if image.endswith(".webp") else image
