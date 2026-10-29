"""Stüdyo kurs istatistikleri: kayıtlar, izleme oranı dağılımı, satın alanlar ve sepette bırakanlar.

İzleme oranı yayındaki derslere göredir (Enrollment.objects.with_progress). Gelir yalnız kursun doğrudan satıldığı
kalemlerden ve para birimine göre toplanır; paketle satışlarda kursa düşen pay bilinmediği için ayrı sayılır.
"""

from django.db.models import Avg, Count, Q, Sum
from django.utils.translation import gettext_lazy as _

from cart.models import CartItem
from learning.models import Enrollment, EnrollmentSource
from order.models import Order, OrderItem, OrderStatus

# (anahtar, etiket, en az %, en çok %)
PROGRESS_BUCKETS = (
    ("baslamadi", _("Başlamadı"), 0, 0),
    ("1-25", _("%1–25"), 1, 25),
    ("26-50", _("%26–50"), 26, 50),
    ("51-75", _("%51–75"), 51, 75),
    ("76-99", _("%76–99"), 76, 99),
    ("bitirdi", _("Bitirdi (%100)"), 100, 100),
)


def bucket_filter(key):
    """İzleme oranı aralığının Q filtresi; bilinmeyen anahtar için None."""
    for name, _label, low, high in PROGRESS_BUCKETS:
        if name == key:
            return Q(progress__gte=low, progress__lte=high)
    return None


def enrollments(course):
    return Enrollment.objects.filter(course=course).with_progress()


def buyer_orders(course):
    return Order.objects.paid().containing(course)


def left_in_cart(course):
    return CartItem.objects.left_for(course)


def unfinished_orders(course):
    """Ödeme adımına gelip tamamlamayan ve kursa sonradan da kaydolmayanlar."""
    return Order.objects.unfinished().containing(course).exclude(user__enrollments__course=course)


def summary(course):
    """Özet kartları ve izleme oranı dağılımı."""
    rows = enrollments(course)
    totals = rows.aggregate(
        total=Count("pk"),
        started=Count("pk", filter=Q(progress__gt=0) | Q(last_watched_at__isnull=False)),
        average=Avg("progress"),
        **{f"bucket{index}": Count("pk", filter=Q(progress__gte=low, progress__lte=high)) for index, (_key, _label, low, high) in enumerate(PROGRESS_BUCKETS)},
    )
    total = totals["total"]
    counts = [totals[f"bucket{index}"] for index in range(len(PROGRESS_BUCKETS))]
    buckets = [
        dict(key=key, label=label, count=count, percent=round(count * 100 / total) if total else 0)
        for (key, label, _low, _high), count in zip(PROGRESS_BUCKETS, counts)
    ]
    sources = dict(rows.order_by().values_list("source").annotate(n=Count("pk")))
    left = left_in_cart(course)
    return dict(
        enrollment_total=total,
        started_total=totals["started"],
        average_progress=round(totals["average"] or 0),
        finished_total=counts[-1],
        buckets=buckets,
        sources=[dict(label=label, count=sources.get(value, 0)) for value, label in EnrollmentSource.choices if sources.get(value)],
        buyer_total=buyer_orders(course).values("email").distinct().count(),
        bundle_sale_total=OrderItem.objects.filter(order__status=OrderStatus.PAID, bundle__courses=course).count(),
        revenue=list(
            OrderItem.objects.filter(order__status=OrderStatus.PAID, course=course)
            .order_by()
            .values("order__currency")
            .annotate(total=Sum("paid_price"), count=Count("pk"))
            .order_by("order__currency")
        ),
        cart_member_total=left.filter(cart__user__isnull=False).values("cart__user").distinct().count(),
        cart_guest_total=left.filter(cart__user__isnull=True).values("cart").distinct().count(),
        unfinished_total=unfinished_orders(course).values("email").distinct().count(),
    )


def revenue(orders):
    """Siparişlerin para birimine göre toplamı ve sayısı (filtrelenmiş listenin altında gösterilir)."""
    ids = orders.order_by().values("pk")
    return list(
        Order.objects.filter(pk__in=ids).order_by().values("currency").annotate(total=Sum("total"), count=Count("pk")).order_by("currency")
    )
