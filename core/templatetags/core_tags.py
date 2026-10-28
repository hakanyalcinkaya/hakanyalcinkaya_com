from django import template

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
