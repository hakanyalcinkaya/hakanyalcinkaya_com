"""Stüdyo istatistiklerinde dönem karşılaştırması: bugün ve dün, bu hafta ve geçen hafta (Pazartesi başlar), bu ay ve
geçen ay; yerel saatle.

Süren dönem (bugün, bu hafta, bu ay) önceki dönemin aynı anına kadarki kısmıyla kıyaslanır: bugün 14:00 ise dünün
14:00'üne kadarki sayıyla, bu hafta Perşembe 14:00 ise geçen haftanın Perşembe 14:00'üne kadarkiyle, ayın 6'sı 14:00 ise
geçen ayın 6'sı 14:00'üne kadarkiyle (geçen ay daha kısaysa ayın tamamıyla). Önceki dönemin tamamı ayrıca gösterilir.

Yalnız sonradan değişmeyen anlara bakılır (ödeme, kayıt, ilk açılış, tamamlanma), böylece geçmiş dönemler bugün
bakıldığında da aynı kalır. Satış ve kayıt tanımları genel istatistiklerle aynıdır (Order.sold; ders sayılarına yalnız
kursa kayıtlı öğrenciler girer). Her satır tek sorguyla, tüm dönemler için koşullu toplamla sayılır.
"""

from datetime import datetime, time, timedelta

from django.contrib.auth import get_user_model
from django.db.models import Count, Exists, OuterRef, Q, Sum
from django.db.models.functions import Lower
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from cart.models import Cart
from core.money import format_money
from course.models import Review
from learning.models import Enrollment, EnrollmentSource, LessonProgress
from newsletter.models import Subscriber
from order.models import Order
from studio.order_stats import _change
from studio.periods import MONTHS
from support.models import Ticket

# Pencereler: süren dönem, önceki dönemin tamamı, önceki dönemin aynı ana kadarki kısmı.
PARTS = ("current", "previous", "same")


def _day_label(day):
    return f"{day.day} {MONTHS[day.month - 1]}"


def _span_label(first, last):
    if first == last:
        return _day_label(first)
    if first.month == last.month:
        return f"{first.day}–{last.day} {MONTHS[last.month - 1]}"
    return f"{_day_label(first)} – {_day_label(last)}"


def periods(now=None):
    """Gün, hafta ve ay için süren ve önceki dönemin sınırları, etiketleri ve sipariş filtresi tarihleri."""
    now = now or timezone.now()
    zone = timezone.get_current_timezone()
    today = timezone.localdate(now)
    day_start = datetime.combine(today, time.min, tzinfo=zone)
    week_start = day_start - timedelta(days=today.weekday())
    month_start = day_start.replace(day=1)
    previous_month_start = (month_start - timedelta(days=1)).replace(day=1)
    rows = (
        ("day", _("Bugün"), _("Dün"), day_start, day_start - timedelta(days=1), _("bu saate kadar")),
        ("week", _("Bu hafta"), _("Geçen hafta"), week_start, week_start - timedelta(days=7), _("aynı ana kadar")),
        ("month", _("Bu ay"), _("Geçen ay"), month_start, previous_month_start, _("aynı ana kadar")),
    )
    result = []
    for key, label, previous_label, start, previous_start, same_label in rows:
        previous_last_day = (start - timedelta(days=1)).date()
        result.append(
            dict(
                key=key,
                label=label,
                previous_label=previous_label,
                same_label=same_label,
                current=(start, now),
                previous=(previous_start, start),
                same=(previous_start, min(previous_start + (now - start), start)),
                dates=_span_label(start.date(), today) if key != "month" else f"{MONTHS[start.month - 1]} {start.year}",
                previous_dates=(
                    _span_label(previous_start.date(), previous_last_day)
                    if key != "month"
                    else f"{MONTHS[previous_start.month - 1]} {previous_start.year}"
                ),
                first_day=start.date(),
                last_day=today,
                previous_first_day=previous_start.date(),
                previous_last_day=previous_last_day,
            )
        )
    return result


def _windows(field, spans):
    """{"day_current": Q(...), ...}: alanın her pencereye düşmesi."""
    return {
        f"{span['key']}_{part}": Q(**{f"{field}__gte": span[part][0], f"{field}__lt": span[part][1]}) for span in spans for part in PARTS
    }


def _totals(queryset, field, spans, value):
    """Tek sorguda her pencerenin sayısı ya da toplamı; value(Q) koşullu toplam ifadesini verir."""
    earliest = min(span["previous"][0] for span in spans)
    windows = _windows(field, spans)
    totals = queryset.filter(**{f"{field}__gte": earliest}).aggregate(**{name: value(condition) for name, condition in windows.items()})
    return {name: total or 0 for name, total in totals.items()}


def _count(condition):
    return Count("pk", filter=condition)


def _metrics():
    """(bölüm, anahtar, etiket, açıklama, queryset, tarih alanı, toplam ifadesi, biçim)."""
    enrolled = Enrollment.objects.filter(user=OuterRef("user"), course=OuterRef("lesson__section__course"))
    lessons = LessonProgress.objects.filter(Exists(enrolled))
    sold = Order.objects.sold()
    carts = Cart.objects.filter(pk__in=Cart.objects.countable().with_products().values("pk"))
    return (
        (_("Satış"), "sales", _("Satış"), _("ödenen sipariş, hediye hariç"), sold, "paid_at", _count, str),
        (_("Satış"), "revenue", _("Gelir"), _("TL ödenen tutar"), sold.filter(currency="TRY"), "paid_at", lambda q: Sum("total", filter=q), format_money),
        (_("Satış"), "buyers", _("Alıcı"), _("farklı e-posta"), sold, "paid_at", lambda q: Count(Lower("email"), distinct=True, filter=q), str),
        (_("Satış"), "gifts", _("Hediye"), _("satışa girmez"), Order.objects.gifted(), "paid_at", _count, str),
        (_("Öğrenciler"), "members", _("Yeni üye"), "", get_user_model().objects.all(), "date_joined", _count, str),
        (
            _("Öğrenciler"),
            "enrollments",
            _("Yeni kurs kaydı"),
            _("satın alma, paket, hediye ve elle; aktarım hariç"),
            Enrollment.objects.exclude(source=EnrollmentSource.IMPORTED),
            "created_at",
            _count,
            str,
        ),
        (_("Öğrenciler"), "learners", _("Ders açan öğrenci"), _("yeni bir dersi ilk kez açan"), lessons, "created_at", lambda q: Count("user", distinct=True, filter=q), str),
        (_("Öğrenciler"), "opened", _("Açılan ders"), _("ilk kez açılan"), lessons, "created_at", _count, str),
        (_("Öğrenciler"), "completed", _("Tamamlanan ders"), "", lessons, "completed_at", _count, str),
        (_("Öğrenciler"), "finished", _("Bitirilen kurs"), "", Enrollment.objects.all(), "completed_at", _count, str),
        (_("Sepet"), "carts", _("Yeni sepet"), _("içine ürün eklenen"), carts, "created_at", _count, str),
        (_("Sepet"), "checkout", _("Ödeme adımına geçen"), "", Cart.objects.countable(), "checkout_at", _count, str),
        (_("Topluluk"), "tickets", _("Destek talebi"), "", Ticket.objects.all(), "created_at", _count, str),
        (_("Topluluk"), "reviews", _("Yorum"), "", Review.objects.all(), "created_at", _count, str),
        (_("Topluluk"), "subscribers", _("Bülten aboneliği"), _("onaylanan"), Subscriber.objects.all(), "confirmed_at", _count, str),
    )


def comparison(now=None):
    """Dönem sütunları ve bölümlere ayrılmış satırlar: her satırda dönem başına süren değer (önceki dönemin aynı anına
    göre değişimle) ve önceki dönemin tamamı (aynı ana kadarki değeriyle)."""
    spans = periods(now)
    sections = []
    for section, key, label, note, queryset, field, value, display in _metrics():
        totals = _totals(queryset, field, spans, value)
        cells = []
        for span in spans:
            current, previous, same = (totals[f"{span['key']}_{part}"] for part in PARTS)
            cells.append(
                dict(
                    current=current,
                    current_label=display(current),
                    change=_change(current, same),
                    previous=previous,
                    previous_label=display(previous),
                    same_label=display(same),
                    span=span,
                )
            )
        row = dict(key=key, label=label, note=note, cells=cells)
        if sections and sections[-1]["label"] == section:
            sections[-1]["rows"].append(row)
        else:
            sections.append(dict(label=section, rows=[row]))
    return dict(periods=spans, sections=sections)
