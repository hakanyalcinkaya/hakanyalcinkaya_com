"""Günlük rapor (send_daily_report komutu, her gece Türkiye saatiyle 00:00): biten günün (yerel saat) satışları,
siparişleri, giden e-postaları, üyeler ve girişler, izlenen kurslar, sepetler, destek, yorum ve bülten; en üstte
dikkat isteyen durumlar.

Satış ve kayıt tanımları stüdyo istatistikleriyle aynıdır (Order.sold; ders sayılarına yalnız kursa kayıtlı öğrenciler
girer). Giriş `last_login`'dir: yalnız şifreyle giriş yapılan anı sayar, açık oturumla gelenler "ders açan" sayısındadır.
Ders ilerlemesi ve son izleme kaydın son güncellemesidir; rapor gün biter bitmez alındığı için o günü gösterir, ama
geçmiş günlerle kıyaslanamaz. Kıyas (dün, geçen hafta aynı gün) yalnız sonradan değişmeyen sayılar için yapılır.
"""

from collections import defaultdict
from datetime import datetime, time, timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Count, Exists, OuterRef, Q, Sum
from django.urls import reverse
from django.utils import timezone

from cart.models import Cart, CartItem, CartItemRemoval, CartRemovalReason
from core.money import format_money
from course.models import Course, Lesson, Review, VideoUpload, VideoUploadStatus
from learning.models import Enrollment, EnrollmentSource, LessonProgress
from mailing.models import EmailBatch, EmailLog
from newsletter.models import Subscriber, SubscriberStatus
from order.models import PAYMENT_METHODS, Order, OrderItem, OrderStatus
from studio import cart_stats, order_stats
from studio.overview_stats import ENROLLMENT_GROUPS
from support.models import Ticket

# Bu kadar günden uzun süredir ödeme bekleyen sipariş (ör. havale) uyarıya düşer.
PENDING_ALERT_DAYS = 2
TOP_LESSONS = 5
WEEKDAYS = ("Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar")
MONTHS = ("Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık")


def report_day():
    """Raporlanacak gün: yerel saatle dün (komut gece yarısından hemen sonra çalışır)."""
    return timezone.localdate() - timedelta(days=1)


def day_bounds(day):
    start = timezone.make_aware(datetime.combine(day, time.min))
    return start, start + timedelta(days=1)


def day_label(day):
    return f"{day.day} {MONTHS[day.month - 1]} {day.year}, {WEEKDAYS[day.weekday()]}"


def _url(name, query=""):
    return f"{settings.SITE_URL.rstrip('/')}{reverse(name)}{query}"


def _within(field, start, end):
    return Q(**{f"{field}__gte": start, f"{field}__lt": end})


def _revenue(orders):
    return [dict(row, label=format_money(row["total"], row["currency"])) for row in order_stats.by_currency(orders)]


def _compare(count_for, day, label=str):
    """Gün, bir önceki gün ve geçen haftanın aynı günü için sayı; label sayıyı yazıya çevirir (ör. tutar)."""
    value, yesterday, last_week = (count_for(*day_bounds(day - timedelta(days=back))) for back in (0, 1, 7))
    return dict(value=value, label=label(value), note=f"dün {label(yesterday)} · geçen hafta {label(last_week)}")


def _headline(day):
    def sales(start, end):
        return order_stats.sold_in(start, end).count()

    def revenue(start, end):
        return order_stats.sold_in(start, end).filter(currency="TRY").aggregate(total=Sum("total"))["total"] or 0

    def members(start, end):
        return get_user_model().objects.filter(_within("date_joined", start, end)).count()

    def enrollments(start, end):
        return Enrollment.objects.filter(_within("created_at", start, end)).count()

    def carts(start, end):
        return Cart.objects.countable().with_products().filter(_within("created_at", start, end)).count()

    return dict(
        sales=_compare(sales, day),
        revenue=_compare(revenue, day, label=format_money),
        members=_compare(members, day),
        enrollments=_compare(enrollments, day),
        carts=_compare(carts, day),
    )


def _orders(start, end):
    sold = order_stats.sold_in(start, end)
    created = Order.objects.filter(_within("created_at", start, end))
    created_counts = dict(created.order_by().values_list("status").annotate(n=Count("pk")))
    methods = []
    for key, label in PAYMENT_METHODS.items():
        paid = order_stats.paid_in(start, end).filter(payment_provider=key)
        count = paid.count()
        if count:
            methods.append(dict(label=label, count=count, is_gift=key == "gift", revenue=_revenue(paid)))
    # İptal ve iade anı ayrıca tutulmaz; durum değişikliği siparişin son güncellemesidir.
    changed = Order.objects.filter(_within("updated_at", start, end))
    pending = Order.objects.filter(status=OrderStatus.PENDING)
    codes = sold.exclude(discount_code="").order_by().values("discount_code").annotate(count=Count("pk")).order_by("-count", "discount_code")
    buyers = sold.values("email").distinct().count()
    items = OrderItem.objects.filter(order__in=sold).count()
    return dict(
        sold=sold.count(),
        sold_note=f"{buyers} alıcı · {items} ürün",
        revenue=_revenue(sold),
        methods=methods,
        gifts=Order.objects.gifted().filter(_within("paid_at", start, end)).count(),
        created=created.count(),
        created_statuses=[dict(label=str(label), count=created_counts[value]) for value, label in OrderStatus.choices if created_counts.get(value)],
        failed=created_counts.get(OrderStatus.FAILED, 0),
        closed=f"{changed.filter(status=OrderStatus.CANCELLED).count()} / {changed.filter(status=OrderStatus.REFUNDED).count()}",
        pending=pending.count(),
        pending_revenue=_revenue(pending),
        codes=list(codes),
    )


def _emails(start, end):
    from mailing.emails import EMAILS

    logs = EmailLog.objects.filter(_within("created_at", start, end))
    rows = []
    for row in logs.stats_by_template():
        email = EMAILS.get(row["template"], {})
        rows.append(dict(row, label=email.get("label", row["template"]), description=email.get("description", "")))
    batches = EmailBatch.objects.filter(pk__in=logs.values("batch")).with_stats()
    return dict(totals=logs.stats(), templates=rows, batches=list(batches))


def _imported_users():
    return Enrollment.objects.filter(user=OuterRef("pk"), source=EnrollmentSource.IMPORTED)


def _users(start, end):
    users = get_user_model().objects
    logins = users.filter(_within("last_login", start, end))
    sources = dict(Enrollment.objects.filter(_within("created_at", start, end)).order_by().values_list("source").annotate(n=Count("pk")))
    groups = [dict(key=key, label=str(label), count=sum(sources.get(source, 0) for source in group)) for key, label, group in ENROLLMENT_GROUPS]
    return dict(
        members=users.filter(_within("date_joined", start, end)).count(),
        logins=logins.count(),
        imported_logins=f"{logins.filter(Exists(_imported_users())).count()} Podia'dan aktarılan hesap",
        learners=Enrollment.objects.filter(_within("last_watched_at", start, end)).values("user").distinct().count(),
        enrollments=sum(group["count"] for group in groups),
        enrollment_groups=[group for group in groups if group["count"]],
    )


def _courses(start, end):
    """Kurs başına günün izlemesi: ders açan öğrenci, açılan ve tamamlanan ders, yeni kayıt, kursu bitiren."""
    enrolled = Enrollment.objects.filter(user=OuterRef("user"), course=OuterRef("lesson__section__course"))
    progress = LessonProgress.objects.filter(Exists(enrolled), _within("updated_at", start, end))
    rows = defaultdict(lambda: dict(learners=0, opened=0, completed=0, enrollments=0, finished=0))
    for row in progress.order_by().values("lesson__section__course").annotate(
        learners=Count("user", distinct=True), opened=Count("pk"), completed=Count("pk", filter=_within("completed_at", start, end))
    ):
        rows[row["lesson__section__course"]].update(learners=row["learners"], opened=row["opened"], completed=row["completed"])
    for field, key in (("created_at", "enrollments"), ("completed_at", "finished")):
        for course_id, count in Enrollment.objects.filter(_within(field, start, end)).order_by().values_list("course").annotate(n=Count("pk")):
            rows[course_id][key] = count
    courses = Course.objects.in_bulk(list(rows))
    result = [dict(counts, course=courses[pk]) for pk, counts in rows.items() if pk in courses]
    result.sort(key=lambda row: (-row["learners"], -row["opened"], row["course"].title))

    top = list(
        progress.order_by().values("lesson").annotate(viewers=Count("user", distinct=True)).order_by("-viewers", "lesson")[:TOP_LESSONS]
    )
    lessons = Lesson.objects.select_related("section__course").in_bulk([row["lesson"] for row in top])
    return dict(rows=result, top_lessons=[dict(lesson=lessons[row["lesson"]], viewers=row["viewers"]) for row in top])


def _carts(start, end):
    created = Cart.objects.countable().with_products().filter(_within("created_at", start, end))
    totals = created.aggregate(total=Count("pk"), members=Count("pk", filter=Q(user__isnull=False)))
    waiting = cart_stats.waiting()
    added = CartItem.objects.filter(_within("created_at", start, end), cart__in=Cart.objects.countable()).count()
    added += CartItemRemoval.objects.countable().filter(_within("added_at", start, end)).count()
    removed = CartItemRemoval.objects.countable().filter(_within("created_at", start, end), reason=CartRemovalReason.REMOVED).count()
    return dict(
        waiting=waiting["total"],
        waiting_note=f"{waiting['guests']} misafir · {waiting['members']} üye · {waiting['item_total']} ürün · {format_money(waiting['amount'])}",
        steps=f"{waiting['cart_step']} / {waiting['checkout_step']}",
        idle=waiting["idle"],
        idle_label=f"{waiting['idle_days']} günden uzun süredir değişmeyen",
        created=totals["total"],
        created_note=f"{totals['total'] - totals['members']} misafir · {totals['members']} üye",
        items=f"{added} / {removed}",
        checkout=Cart.objects.countable().filter(_within("checkout_at", start, end)).count(),
        converted=Cart.objects.filter(_within("converted_at", start, end)).count(),
    )


def _community(start, end):
    subscribers = Subscriber.objects
    changes = [subscribers.filter(_within(field, start, end)).count() for field in ("created_at", "confirmed_at", "unsubscribed_at")]
    return dict(
        tickets=Ticket.objects.filter(_within("created_at", start, end)).count(),
        tickets_note=f"yanıt bekleyen {Ticket.objects.awaiting().count()}",
        reviews=Review.objects.filter(_within("created_at", start, end)).count(),
        reviews_note=f"onay bekleyen {Review.objects.awaiting().count()}",
        subscribers=" / ".join(str(count) for count in changes),
        subscribers_note=(
            f"{subscribers.confirmed().count()} onaylı abone · {subscribers.filter(status=SubscriberStatus.PENDING).count()} onay bekliyor"
        ),
    )


def _alerts(start, end, emails):
    """Dikkat isteyen durumlar; yoksa boş liste."""
    from config.celery import worker_online

    alerts = []
    if emails["totals"]["failed"]:
        alerts.append(dict(text=f"{emails['totals']['failed']} e-posta gönderilemedi.", url=_url("studio:email_log")))
    uploads = VideoUpload.objects.filter(_within("updated_at", start, end), status=VideoUploadStatus.FAILED).count()
    if uploads:
        alerts.append(dict(text=f"{uploads} video yüklemesi hata verdi.", url=_url("studio:queue")))
    if not worker_online():
        alerts.append(dict(text="Celery işçisi çalışmıyor: video yükleme ve bülten gönderimi durur.", url=_url("studio:queue")))
    stale = Order.objects.filter(status=OrderStatus.PENDING, created_at__lt=timezone.now() - timedelta(days=PENDING_ALERT_DAYS)).count()
    if stale:
        alerts.append(dict(text=f"{stale} sipariş {PENDING_ALERT_DAYS} günden uzun süredir ödeme bekliyor.", url=_url("studio:orders", "?status=pending")))
    return alerts


def build(day=None):
    """E-postanın bağlamı: verilmezse dünün raporu."""
    day = day or report_day()
    start, end = day_bounds(day)
    emails = _emails(start, end)
    return dict(
        day=day,
        day_label=day_label(day),
        alerts=_alerts(start, end, emails),
        headline=_headline(day),
        orders=_orders(start, end),
        emails=emails,
        users=_users(start, end),
        courses=_courses(start, end),
        carts=_carts(start, end),
        community=_community(start, end),
        pending_alert_days=PENDING_ALERT_DAYS,
        links=dict(
            stats=_url("studio:stats"),
            orders=_url("studio:orders", f"?date_from={day:%Y-%m-%d}&date_to={day:%Y-%m-%d}"),
            carts=_url("studio:carts"),
            emails=_url("studio:email_log"),
            support=_url("studio:support_list"),
            reviews=_url("studio:reviews"),
            subscribers=_url("studio:subscribers"),
        ),
    )
