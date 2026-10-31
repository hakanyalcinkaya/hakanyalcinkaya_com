"""Stüdyo sipariş istatistikleri: ayın satışları (ödeme tarihine göre), önceki ayla kıyas, yeni/tekrar alıcı, ödeme
yolu, ürün ve indirim kodu kırılımı, ödeme bekleyenler ve son 12 ayın seyri.

Tutarlar para birimine göre ayrı toplanır (sitede TL, eski platformdan aktarılanlar kendi para birimiyle); farklı para
birimleri birbirine eklenmez. Alıcı e-postayla tanınır.
"""

from collections import defaultdict
from decimal import Decimal

from django.db.models import Count, F, Q, Sum
from django.db.models.functions import Lower, TruncMonth
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from course.models import Bundle, Course
from order.models import PAYMENT_METHODS, Order, OrderItem, OrderStatus
from studio.periods import month_bounds, month_label

TREND_MONTHS = 12


def _by_currency(orders):
    """[{currency, total, count, average, discount}], TL önce."""
    rows = orders.order_by().values("currency").annotate(total=Sum("total"), count=Count("pk"), discount=Sum("discount_total"))
    result = [dict(row, average=(row["total"] / row["count"]).quantize(Decimal("0.01")) if row["count"] else 0) for row in rows]
    return sorted(result, key=lambda row: (row["currency"] != "TRY", row["currency"]))


def _change(current, previous):
    """Önceki aya göre % değişim ({value, label}: "+%12", "−%5"); önceki 0 ise None."""
    if not previous:
        return None
    value = round((current - previous) * 100 / previous)
    sign = "+" if value > 0 else "−" if value < 0 else ""
    return dict(value=value, label=f"{sign}%{abs(value)}")


def paid_in(start, end):
    return Order.objects.paid().filter(paid_at__gte=start, paid_at__lt=end)


def summary(period):
    """Ayın özet kartları: satış, gelir (para birimine göre, önceki ayla kıyas), alıcılar, indirim, bekleyen/başarısız."""
    start, end = period["start"], period["end"]
    orders = paid_in(start, end)
    year, month = (period["year"] - 1, 12) if period["month"] == 1 else (period["year"], period["month"] - 1)
    previous_orders = paid_in(*month_bounds(year, month))
    revenue = _by_currency(orders)
    previous_revenue = {row["currency"]: row for row in _by_currency(previous_orders)}
    for row in revenue:
        row["change"] = _change(row["total"], (previous_revenue.get(row["currency"]) or {}).get("total"))
    count, previous_count = orders.count(), previous_orders.count()

    emails = set(orders.annotate(buyer=Lower("email")).values_list("buyer", flat=True))
    returning = set(
        Order.objects.paid().filter(paid_at__lt=start).annotate(buyer=Lower("email")).filter(buyer__in=emails).values_list("buyer", flat=True)
    )
    created = Order.objects.filter(created_at__gte=start, created_at__lt=end)
    pending = Order.objects.filter(status=OrderStatus.PENDING)
    return dict(
        count=count,
        count_change=_change(count, previous_count),
        previous_count=previous_count,
        revenue=revenue,
        buyers=len(emails),
        new_buyers=len(emails - returning),
        returning_buyers=len(returning),
        with_code=orders.exclude(discount_code="").count(),
        items=OrderItem.objects.filter(order__in=orders).count(),
        pending=_by_currency(pending),
        pending_count=pending.count(),
        created_unpaid=created.filter(status=OrderStatus.PENDING).count(),
        failed=created.filter(status=OrderStatus.FAILED).count(),
    )


def providers(start, end):
    """Ayın satışları ödeme yoluna göre."""
    rows = defaultdict(list)
    for row in paid_in(start, end).order_by().values("payment_provider", "currency").annotate(total=Sum("total"), count=Count("pk")):
        rows[row["payment_provider"]].append(row)
    result = [
        dict(label=PAYMENT_METHODS.get(key, key) or _("Belirtilmemiş"), count=sum(row["count"] for row in values), amounts=sorted(values, key=lambda row: row["currency"] != "TRY"))
        for key, values in rows.items()
    ]
    return sorted(result, key=lambda row: -row["count"])


def products(start, end):
    """Ayda satılan kurs ve paketler: adet, ödenen tutar (para birimine göre), indirimli satış."""
    rows = (
        OrderItem.objects.filter(order__status=OrderStatus.PAID, order__paid_at__gte=start, order__paid_at__lt=end)
        .order_by()
        .values("course_id", "bundle_id", "title", "order__currency")
        .annotate(count=Count("pk"), total=Sum("paid_price"), discounted=Count("pk", filter=Q(paid_price__lt=F("unit_price"))))
    )
    grouped = {}
    for row in rows:
        key = ("bundle", row["bundle_id"]) if row["bundle_id"] else ("course", row["course_id"])
        entry = grouped.setdefault(key, dict(title=row["title"], count=0, discounted=0, amounts=[], course_id=row["course_id"], is_bundle=bool(row["bundle_id"])))
        entry["count"] += row["count"]
        entry["discounted"] += row["discounted"]
        entry["amounts"].append(dict(currency=row["order__currency"], total=row["total"]))
    titles = dict(Course.objects.filter(pk__in=[pk for kind, pk in grouped if kind == "course"]).values_list("pk", "title"))
    titles.update(Bundle.objects.filter(pk__in=[pk for kind, pk in grouped if kind == "bundle"]).values_list("pk", "title"))
    for (kind, pk), entry in grouped.items():
        entry["title"] = titles.get(pk, entry["title"])
        entry["amounts"].sort(key=lambda row: row["currency"] != "TRY")
    return sorted(grouped.values(), key=lambda row: (-row["count"], row["title"]))


def codes(start, end):
    """Ayın satışlarında kullanılan indirim kodları: kullanım ve düşülen tutar."""
    return list(
        paid_in(start, end)
        .exclude(discount_code="")
        .order_by()
        .values("discount_code", "discount_id", "currency")
        .annotate(count=Count("pk"), discount=Sum("discount_total"), total=Sum("total"))
        .order_by("-count", "discount_code")
    )


def trend(period):
    """Seçili ay dahil son 12 ayın satış adedi ve geliri; çubuklar en yüksek aya göre ölçeklenir."""
    year, month = period["year"], period["month"]
    keys = []
    for _index in range(TREND_MONTHS):
        keys.append((year, month))
        year, month = (year - 1, 12) if month == 1 else (year, month - 1)
    keys.reverse()
    start, end = month_bounds(*keys[0])[0], period["end"]
    zone = timezone.get_current_timezone()
    rows = (
        paid_in(start, end)
        .annotate(month=TruncMonth("paid_at", tzinfo=zone))
        .order_by()
        .values("month", "currency")
        .annotate(count=Count("pk"), total=Sum("total"))
    )
    data = defaultdict(lambda: dict(count=0, amounts=[]))
    for row in rows:
        local = timezone.localtime(row["month"], zone) if timezone.is_aware(row["month"]) else row["month"]
        entry = data[(local.year, local.month)]
        entry["count"] += row["count"]
        entry["amounts"].append(dict(currency=row["currency"], total=row["total"]))
    peak = max((entry["count"] for entry in data.values()), default=0)
    return [
        dict(
            key=f"{key[0]}-{key[1]:02d}",
            label=month_label(*key),
            count=data[key]["count"],
            amounts=sorted(data[key]["amounts"], key=lambda row: row["currency"] != "TRY"),
            percent=round(data[key]["count"] * 100 / peak) if peak else 0,
            is_current=key == (period["year"], period["month"]),
        )
        for key in keys
    ]
