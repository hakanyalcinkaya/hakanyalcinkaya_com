"""Stüdyo istatistiklerinde ay seçimi (?month=YYYY-AA): yerel saatle ayın başı, sonu, etiketi ve komşu aylar."""

from datetime import datetime, timedelta

from django.utils import timezone
from django.utils.translation import gettext_lazy as _

MONTHS = (
    _("Ocak"), _("Şubat"), _("Mart"), _("Nisan"), _("Mayıs"), _("Haziran"),
    _("Temmuz"), _("Ağustos"), _("Eylül"), _("Ekim"), _("Kasım"), _("Aralık"),
)


def month_bounds(year, month):
    zone = timezone.get_current_timezone()
    return datetime(year, month, 1, tzinfo=zone), datetime(year + month // 12, month % 12 + 1, 1, tzinfo=zone)


def month_label(year, month):
    return f"{MONTHS[month - 1]} {year}"


def month_period(value=""):
    """?month=YYYY-AA değerinden ayın başı ve sonu (yerel saat); geçersiz ya da boşsa bu ay."""
    today = timezone.localdate()
    try:
        year, month = (int(part) for part in value.split("-"))
        datetime(year, month, 1)
    except (TypeError, ValueError):
        year, month = today.year, today.month
    start, end = month_bounds(year, month)
    previous = (start - timedelta(days=1)).strftime("%Y-%m")
    following = end.strftime("%Y-%m") if end.date() <= today else None
    return dict(
        start=start,
        end=end,
        year=year,
        month=month,
        key=start.strftime("%Y-%m"),
        label=month_label(year, month),
        previous=previous,
        following=following,
        last_day=(end - timedelta(days=1)).date(),
    )
