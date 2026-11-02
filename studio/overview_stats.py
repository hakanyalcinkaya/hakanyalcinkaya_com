"""Stüdyo genel istatistikleri: sitenin geneli, tüm kursların öğrenci/izleme/satış/sepet sayıları tek tabloda, en çok
izlenen ve en çok bırakılan dersler, son 12 ayın satış, kayıt ve ders açılışları.

Kurs satırları kurs istatistikleriyle (course_stats) aynı tanımları kullanır: izleme oranı yayındaki derslere göre,
gelir kursun tek başına satıldığı kalemlerden (paketle satış ayrı), sepette bırakan kursa kayıtlı olmayan üye ya da
misafir sepetidir. Ders sayılarına yalnız kursa kayıtlı öğrenciler girer (personelin denemeleri girmez).
"""

from collections import Counter, defaultdict
from datetime import timedelta

from django.db.models import Avg, Count, Exists, OuterRef, Q, Sum
from django.db.models.functions import Lower, TruncMonth
from django.utils import timezone

from cart.models import CartItem, CartStatus
from core.models import Status
from course.models import Course, Lesson
from learning.models import Enrollment, LessonProgress
from order.models import Order, OrderItem, OrderStatus
from studio import cart_stats, course_stats, order_stats, periods

# Bu kadar gün içinde ders açan öğrenci "aktif" sayılır.
ACTIVE_DAYS = 30
TOP_LESSONS = 10


def _percent(part, whole):
    return round(part * 100 / whole) if whole else 0


def _active_since():
    return timezone.now() - timedelta(days=ACTIVE_DAYS)


def _enrollment_totals():
    """with_progress satırlarının sayıları (aggregate ya da values().annotate() için)."""
    return dict(
        total=Count("pk"),
        started=Count("pk", filter=Q(progress__gt=0) | Q(last_watched_at__isnull=False)),
        average=Avg("progress"),
        finished=Count("pk", filter=Q(progress__gte=100)),
        active=Count("pk", filter=Q(last_watched_at__gte=_active_since())),
    )


def summary():
    """Özet kartları: öğrenciler, aktif öğrenciler ve izleme, tüm zamanların satışı, bu ay, şu an sepette bekleyenler."""
    since = _active_since()
    totals = Enrollment.objects.with_progress().aggregate(**_enrollment_totals())
    paid = Order.objects.paid()
    period = periods.month_period()
    return dict(
        period=period,
        enrollments=totals,
        average_progress=round(totals["average"] or 0),
        student_total=Enrollment.objects.values("user").distinct().count(),
        new_enrollments=Enrollment.objects.filter(created_at__gte=since).count(),
        active_students=Enrollment.objects.filter(last_watched_at__gte=since).values("user").distinct().count(),
        order_total=paid.count(),
        revenue=order_stats.by_currency(paid),
        buyer_total=paid.annotate(buyer=Lower("email")).values("buyer").distinct().count(),
        month=order_stats.summary(period),
        waiting=cart_stats.waiting(),
        active_days=ACTIVE_DAYS,
    )


def _cart_counts():
    """Kurs başına sepette bırakan (course_stats.summary ile aynı): açık ya da boşaltılmış sepette kursu doğrudan ya da
    paketle içeren, kursa kayıtlı olmayan üyeler ve misafir sepetleri."""
    items = CartItem.objects.filter(cart__status__in=(CartStatus.ACTIVE, CartStatus.EMPTIED)).order_by()
    pairs = set(items.filter(course__isnull=False).values_list("course", "cart", "cart__user"))
    pairs |= set(items.filter(bundle__isnull=False).values_list("bundle__courses", "cart", "cart__user"))
    users = {user for _course, _cart, user in pairs if user}
    enrolled = set(Enrollment.objects.filter(user__in=users).values_list("user", "course"))
    owners = defaultdict(set)
    for course, cart, user in pairs:
        if course is None or (user, course) in enrolled:
            continue
        owners[course].add(("user", user) if user else ("cart", cart))
    return {course: len(keys) for course, keys in owners.items()}


def courses():
    """Tüm kurslar kurs sırasıyla: kayıt, izlemeye başlayan, ortalama izleme, bitiren, son ACTIVE_DAYS günde ders açan,
    satın alan (doğrudan ya da paketle), tek başına satış ve geliri, paketle satış, sepette bırakan."""
    progress = {
        row["course"]: row
        for row in Enrollment.objects.with_progress().order_by().values("course").annotate(**_enrollment_totals())
    }
    paid_items = OrderItem.objects.filter(order__status=OrderStatus.PAID).order_by()
    revenue = defaultdict(list)
    for row in paid_items.filter(course__isnull=False).values("course", "order__currency").annotate(total=Sum("paid_price"), count=Count("pk")):
        revenue[row["course"]].append(row)
    bundle_sales = dict(paid_items.filter(bundle__isnull=False).values_list("bundle__courses").annotate(n=Count("pk")))
    buyers = defaultdict(set)
    for course, email in paid_items.filter(course__isnull=False).values_list("course", "order__email"):
        buyers[course].add(email)
    for course, email in paid_items.filter(bundle__isnull=False).values_list("bundle__courses", "order__email"):
        buyers[course].add(email)
    in_cart = _cart_counts()

    rows = list(Course.objects.order_by("sort_order", "title"))
    for course in rows:
        stats = progress.get(course.pk) or dict(total=0, started=0, average=None, finished=0, active=0)
        course.enrollment_total = stats["total"]
        course.started_total = stats["started"]
        course.average_progress = round(stats["average"] or 0)
        course.finished_total = stats["finished"]
        course.active_total = stats["active"]
        course.finished_percent = _percent(stats["finished"], stats["total"])
        course.buyer_total = len(buyers[course.pk])
        course.revenue = sorted(revenue[course.pk], key=lambda row: row["order__currency"] != "TRY")
        course.sale_total = sum(row["count"] for row in course.revenue)
        course.bundle_sale_total = bundle_sales.get(course.pk, 0)
        course.cart_total = in_cart.get(course.pk, 0)
    return rows


def _published_lessons():
    return Lesson.objects.filter(status=Status.PUBLISHED, section__status=Status.PUBLISHED)


def top_watched(enrollment_totals):
    """En çok kayıtlı öğrencinin oynattığı ya da tamamladığı yayındaki dersler; oran kursa kayıtlı olanlara göre."""
    enrolled = Enrollment.objects.filter(user=OuterRef("user"), course=OuterRef("lesson__section__course"))
    completed = Q(completed_at__isnull=False)
    rows = list(
        LessonProgress.objects.filter(Exists(enrolled), Q(position_seconds__gt=0) | completed, lesson__in=_published_lessons())
        .order_by()
        .values("lesson")
        .annotate(viewers=Count("pk"), completed=Count("pk", filter=completed))
        .order_by("-viewers", "lesson")[:TOP_LESSONS]
    )
    lessons = _published_lessons().select_related("section__course").in_bulk([row["lesson"] for row in rows])
    result = []
    for row in rows:
        lesson = lessons[row["lesson"]]
        total = enrollment_totals.get(lesson.section.course_id, 0)
        result.append(dict(lesson=lesson, viewers=row["viewers"], completed=row["completed"], percent=_percent(row["viewers"], total)))
    return result


def top_left():
    """En çok öğrencinin bıraktığı dersler (course_stats.left_filter: son açtığı ders, LEFT_AFTER_DAYS gündür ders
    açmadı, kursu bitirmedi)."""
    counts = Counter(Enrollment.objects.with_progress().filter(course_stats.left_filter()).values_list("last_lesson", flat=True))
    top = counts.most_common(TOP_LESSONS)
    lessons = Lesson.objects.select_related("section__course").in_bulk([pk for pk, _count in top])
    return [dict(lesson=lessons[pk], count=count) for pk, count in top if pk in lessons]


def trend():
    """Son 12 ayın satış adedi ve geliri (order_stats.trend), yeni kurs kaydı ve ilk kez açılan ders sayısı."""
    rows = order_stats.trend(periods.month_period())
    year, month = (int(part) for part in rows[0]["key"].split("-"))
    start = periods.month_bounds(year, month)[0]
    zone = timezone.get_current_timezone()

    def by_month(queryset):
        counts = queryset.filter(created_at__gte=start).annotate(month=TruncMonth("created_at", tzinfo=zone)).order_by().values("month").annotate(n=Count("pk"))
        return {(timezone.localtime(row["month"], zone) if timezone.is_aware(row["month"]) else row["month"]).strftime("%Y-%m"): row["n"] for row in counts}

    enrolled = Enrollment.objects.filter(user=OuterRef("user"), course=OuterRef("lesson__section__course"))
    enrollments = by_month(Enrollment.objects.all())
    opened = by_month(LessonProgress.objects.filter(Exists(enrolled)))
    for row in rows:
        row["enrollments"] = enrollments.get(row["key"], 0)
        row["opened"] = opened.get(row["key"], 0)
    return rows
