from datetime import timedelta

from django import template
from django.utils import timezone
from django.utils.timesince import timesince
from django.utils.translation import gettext as _

from core.duration import clock, hours_minutes
from core.money import format_try

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
