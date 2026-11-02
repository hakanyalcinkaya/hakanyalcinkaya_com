"""Stüdyo kurs istatistikleri: kayıtlar, izleme oranı dağılımı, ders bazında izleme, satın alanlar ve sepette bırakanlar.

İzleme oranı yayındaki derslere göredir (Enrollment.objects.with_progress). Gelir yalnız kursun doğrudan satıldığı
kalemlerden ve para birimine göre toplanır; paketle satışlarda kursa düşen pay bilinmediği için ayrı sayılır. Hediye
siparişler satış sayılmaz (kayıt kaynağında "Hediye" olarak görünür); iptal ve iade edilenler de sayılmaz.
"""

from collections import Counter
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db.models import Avg, Count, Q, Sum
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from cart.models import CartItem
from course.models import Lesson
from learning.models import Enrollment, EnrollmentSource
from order.models import Order, OrderItem

# Son açtığı ders bu olup bu kadar gündür hiç ders açmayan, kursu bitirmemiş öğrenci o derste "bıraktı" sayılır.
LEFT_AFTER_DAYS = 14

# (anahtar, etiket, en az %, en çok %)
PROGRESS_BUCKETS = (
    ("not-started", _("Başlamadı"), 0, 0),
    ("1-25", _("%1–25"), 1, 25),
    ("26-50", _("%26–50"), 26, 50),
    ("51-75", _("%51–75"), 51, 75),
    ("76-99", _("%76–99"), 76, 99),
    ("completed", _("Bitirdi (%100)"), 100, 100),
)


def bucket_filter(key):
    """İzleme oranı aralığının Q filtresi; bilinmeyen anahtar için None."""
    for name, _label, low, high in PROGRESS_BUCKETS:
        if name == key:
            return Q(progress__gte=low, progress__lte=high)
    return None


def enrollments(course):
    return Enrollment.objects.filter(course=course).with_progress()


def left_filter(lesson=None):
    """Bıraktı (with_progress satırlarında): son açtığı ders (verilirse bu ders), LEFT_AFTER_DAYS gündür ders açmadı,
    kursu bitirmedi."""
    condition = Q(last_lesson__isnull=False, last_watched_at__lt=timezone.now() - timedelta(days=LEFT_AFTER_DAYS), progress__lt=100)
    if lesson is not None:
        condition &= Q(last_lesson=lesson)
    return condition


def course_lesson(course, lesson_id):
    """GET'ten gelen ders kimliği bu kursun dersiyse ders, değilse None."""
    if not lesson_id:
        return None
    try:
        return Lesson.objects.filter(section__course=course, pk=lesson_id).first()
    except ValidationError:
        return None


def lessons(course):
    """Yayındaki dersler kurs sırasıyla; her derste izleyen, bitiren, ortalama kaldığı yer ve o derste bırakan sayısı.
    Yalnız kursa kayıtlı öğrenciler sayılır (personelin denemeleri sayılmaz). Kaldığı yer oynatıcının son yazdığı saniyedir."""
    students = Enrollment.objects.filter(course=course).values("user")
    mine = Q(progress__user__in=students)
    rows = list(
        course.published_lessons()
        .select_related("section")
        .order_by("section__sort_order", "sort_order", "id")
        .annotate(
            viewer_total=Count("progress", filter=mine & (Q(progress__position_seconds__gt=0) | Q(progress__completed_at__isnull=False))),
            completed_total=Count("progress", filter=mine & Q(progress__completed_at__isnull=False)),
            average_position=Avg("progress__position_seconds", filter=mine & Q(progress__position_seconds__gt=0)),
        )
    )
    left = Counter(enrollments(course).filter(left_filter()).values_list("last_lesson", flat=True))
    total = Enrollment.objects.filter(course=course).count()
    for number, lesson in enumerate(rows, 1):
        lesson.number = number
        lesson.left_total = left[lesson.pk]
        lesson.viewer_percent = round(lesson.viewer_total * 100 / total) if total else 0
        lesson.average_percent = (
            min(round(lesson.average_position * 100 / lesson.duration_seconds), 100)
            if lesson.average_position and lesson.duration_seconds
            else None
        )
    return rows


def buyer_orders(course):
    return Order.objects.sold().containing(course)


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
        bundle_sale_total=OrderItem.objects.sold().filter(bundle__courses=course).count(),
        revenue=list(
            OrderItem.objects.sold().filter(course=course)
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
