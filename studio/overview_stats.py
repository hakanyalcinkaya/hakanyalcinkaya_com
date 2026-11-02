"""Stüdyo genel istatistikleri: sitenin geneli, tüm kursların öğrenci/izleme/satış/sepet sayıları tek tabloda, en çok
izlenen ve en çok bırakılan dersler, son 12 ayın satış, kayıt ve ders açılışları.

Kurs satırları kurs istatistikleriyle (course_stats) aynı tanımları kullanır: izleme oranı yayındaki derslere göre,
gelir kursun tek başına satıldığı kalemlerden (paketle satış ayrı), sepette bırakan kursa kayıtlı olmayan üye ya da
misafir sepetidir. Ders sayılarına yalnız kursa kayıtlı öğrenciler girer (personelin denemeleri girmez).

Satış ödenmiş ve hediye olmayan siparişlerdir (Order.sold). Hediyeler, iptal ve iade edilenler satışa girmez; ödeme
yolu tablosunda ve kurs satırlarında ayrı gösterilir.
"""

from collections import Counter, defaultdict
from datetime import timedelta

from django.db.models import Avg, Count, Exists, OuterRef, Q, Sum
from django.db.models.functions import Lower, TruncMonth
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from cart.models import CartItem, CartStatus
from core.models import Status
from course.models import Course, Lesson
from learning.models import Enrollment, EnrollmentSource, LessonProgress
from order.models import GIFT, PAYMENT_METHODS, Order, OrderItem, OrderStatus
from studio import cart_stats, course_stats, order_stats, periods

# Bu kadar gün içinde ders açan öğrenci "aktif" sayılır.
ACTIVE_DAYS = 30
TOP_LESSONS = 10
# Son 12 ayda yeni kayıtların kaynağa göre sütunları: (anahtar, etiket, kayıt kaynakları).
ENROLLMENT_GROUPS = (
    ("purchase", _("Satın alma"), (EnrollmentSource.PURCHASE, EnrollmentSource.BUNDLE)),
    ("gift", _("Hediye"), (EnrollmentSource.GIFT,)),
    ("manual", _("Elle"), (EnrollmentSource.MANUAL,)),
    ("imported", _("Aktarım"), (EnrollmentSource.IMPORTED,)),
)


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


def _by_group(counts):
    """{kayıt kaynağı: sayı} → ENROLLMENT_GROUPS sırasıyla [{key, label, count}]."""
    return [dict(key=key, label=label, count=sum(counts.get(source, 0) for source in sources)) for key, label, sources in ENROLLMENT_GROUPS]


def summary():
    """Özet kartları: öğrenciler (son ACTIVE_DAYS günün yeni kayıtları kaynağa göre), aktif öğrenciler ve izleme, tüm
    zamanların satışı, bu ay, şu an sepette bekleyenler."""
    since = _active_since()
    totals = Enrollment.objects.with_progress().aggregate(**_enrollment_totals())
    sold = Order.objects.sold()
    period = periods.month_period()
    return dict(
        period=period,
        enrollments=totals,
        average_progress=round(totals["average"] or 0),
        student_total=Enrollment.objects.values("user").distinct().count(),
        new_enrollments=[
            group
            for group in _by_group(dict(Enrollment.objects.filter(created_at__gte=since).order_by().values_list("source").annotate(n=Count("pk"))))
            if group["count"]
        ],
        active_students=Enrollment.objects.filter(last_watched_at__gte=since).values("user").distinct().count(),
        order_total=sold.count(),
        revenue=order_stats.by_currency(sold),
        buyer_total=sold.annotate(buyer=Lower("email")).values("buyer").distinct().count(),
        gift_total=Order.objects.gifted().count(),
        cancelled_total=Order.objects.filter(status__in=(OrderStatus.CANCELLED, OrderStatus.REFUNDED)).count(),
        month=order_stats.summary(period),
        waiting=cart_stats.waiting(),
        active_days=ACTIVE_DAYS,
    )


def providers():
    """Tüm zamanların siparişleri ödeme yoluna göre: ödenen sipariş, alıcı, gelir (para birimine göre); iptal ve iade
    edilenler ayrı sütunda, satışa girmez. Hediye kendi satırında, tutarı 0."""
    rows = {}

    def entry(key):
        return rows.setdefault(
            key,
            dict(key=key, label=PAYMENT_METHODS.get(key, key) or _("Belirtilmemiş"), is_gift=key == GIFT, count=0, buyers=0, amounts=[], cancelled=0, refunded=0),
        )

    paid = Order.objects.paid().order_by()
    for row in paid.values("payment_provider", "currency").annotate(total=Sum("total"), count=Count("pk")):
        current = entry(row["payment_provider"])
        current["count"] += row["count"]
        current["amounts"].append(dict(currency=row["currency"], total=row["total"]))
    for row in paid.annotate(buyer=Lower("email")).values("payment_provider").annotate(n=Count("buyer", distinct=True)):
        entry(row["payment_provider"])["buyers"] = row["n"]
    closed = Order.objects.filter(status__in=(OrderStatus.CANCELLED, OrderStatus.REFUNDED)).order_by()
    for row in closed.values("payment_provider", "status").annotate(n=Count("pk")):
        entry(row["payment_provider"])["cancelled" if row["status"] == OrderStatus.CANCELLED else "refunded"] += row["n"]
    order = list(PAYMENT_METHODS)
    for current in rows.values():
        current["amounts"].sort(key=lambda row: row["currency"] != "TRY")
    return sorted(rows.values(), key=lambda row: (order.index(row["key"]) if row["key"] in order else len(order), row["key"]))


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
    satın alan (doğrudan ya da paketle), tek başına satış ve geliri (ödeme yoluna göre adetleriyle), paketle satış,
    hediye kaydı (hediye sipariş, hediye edilen sepet ya da öğrenciye hediye olarak açılan erişim), sepette bırakan."""
    progress = {
        row["course"]: row
        for row in Enrollment.objects.with_progress().order_by().values("course").annotate(**_enrollment_totals())
    }
    paid_items = OrderItem.objects.sold().order_by()
    direct = paid_items.filter(course__isnull=False)
    revenue = defaultdict(list)
    for row in direct.values("course", "order__currency").annotate(total=Sum("paid_price"), count=Count("pk")):
        revenue[row["course"]].append(row)
    methods = defaultdict(list)
    for row in direct.values("course", "order__payment_provider").annotate(n=Count("pk")).order_by("-n"):
        key = row["order__payment_provider"]
        methods[row["course"]].append(dict(label=PAYMENT_METHODS.get(key, key) or _("Belirtilmemiş"), count=row["n"]))
    gifts = dict(Enrollment.objects.filter(source=EnrollmentSource.GIFT).order_by().values_list("course").annotate(n=Count("pk")))
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
        course.sale_methods = methods[course.pk]
        course.gift_total = gifts.get(course.pk, 0)
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
    """Son 12 ayın satış adedi ve geliri (order_stats.trend), kaynağa göre yeni kurs kaydı (ENROLLMENT_GROUPS sırasıyla
    row["enrollments"]) ve ilk kez açılan ders sayısı."""
    rows = order_stats.trend(periods.month_period())
    year, month = (int(part) for part in rows[0]["key"].split("-"))
    start = periods.month_bounds(year, month)[0]
    zone = timezone.get_current_timezone()

    def by_month(queryset, *fields):
        """{(ay, *alanlar): sayı}; ay "YYYY-AA"."""
        counts = queryset.filter(created_at__gte=start).annotate(month=TruncMonth("created_at", tzinfo=zone)).order_by().values("month", *fields).annotate(n=Count("pk"))
        result = {}
        for row in counts:
            month = timezone.localtime(row["month"], zone) if timezone.is_aware(row["month"]) else row["month"]
            result[(month.strftime("%Y-%m"), *(row[field] for field in fields))] = row["n"]
        return result

    enrolled = Enrollment.objects.filter(user=OuterRef("user"), course=OuterRef("lesson__section__course"))
    enrollments = by_month(Enrollment.objects.all(), "source")
    opened = by_month(LessonProgress.objects.filter(Exists(enrolled)))
    for row in rows:
        row["enrollments"] = _by_group({source: count for (month, source), count in enrollments.items() if month == row["key"]})
        row["opened"] = opened.get((row["key"],), 0)
    return rows
