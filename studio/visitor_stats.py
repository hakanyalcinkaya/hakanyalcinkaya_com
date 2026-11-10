"""Stüdyo ziyaretçi istatistikleri (izometrik pano): son DAYS gündeki sepete eklemeler (CartAddEvent), kayıtlar ve girişler
(AccountEvent) ülke, cihaz, işletim sistemi, tarayıcı, dil, geliş kaynağı ve saate göre; ders izlemeleri (LessonView) ve
üye sayfa ziyaretleri (PageView) cihaz ve ülkeye göre.

Bilgiler kayıtların data alanından okunur (core.visitor). Bir sepete ekleme, aynı sepetten o kurs için ödenmiş ve hediye
olmayan bir sipariş kalemi varsa "satışa döndü" sayılır; misafir sepeti üyeninkine katılınca kayıt üyenin sepetine
geçtiği için girişten sonra alınanlar da sayılır. Personelin kayıtları sayılmaz.
"""

from datetime import timedelta

from django.db.models import Count, Exists, OuterRef, Q, Sum
from django.db.models.fields.json import KT
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from account.models import AccountEvent, AccountEventKind, PageView
from cart.models import CartAddEvent
from learning.models import LessonView
from order.models import OrderItem

# Personel dışı: anahtar yoksa da (eski ya da eksik kayıt) sayılır; exclude(is_staff=True) eksik anahtarı da dışlardı.
NOT_STAFF = Q(data__member__is_staff=False) | Q(data__member__is_staff__isnull=True)
DAY_CHOICES = (7, 30, 90, 365)
DEFAULT_DAYS = 30
TOP = 8
WEEKDAYS = (_("Pzt"), _("Sal"), _("Çar"), _("Per"), _("Cum"), _("Cmt"), _("Paz"))
DEVICE_LABELS = dict(desktop=_("Masaüstü"), mobile=_("Mobil"), tablet=_("Tablet"), bot=_("Bot"), other=_("Diğer"))
DEVICE_ICONS = dict(desktop="laptop", mobile="phone", tablet="tablet", bot="robot", other="question-circle")
# Gruplar: (anahtar, başlık, simge, JSON yolu).
GROUPS = (
    ("device", _("Cihaz"), "phone", "data__agent__type"),
    ("os", _("İşletim sistemi"), "windows", "data__agent__os__family"),
    ("browser", _("Tarayıcı"), "browser-chrome", "data__agent__browser__family"),
    ("language", _("Dil"), "translate", "data__language__base"),
    ("source", _("İlk geliş kaynağı"), "signpost-split", "data__visit__first__referrer_host"),
    ("campaign", _("UTM kaynağı"), "megaphone", "data__visit__first__utm__source"),
)


def days_param(value):
    try:
        days = int(value)
    except (TypeError, ValueError):
        return DEFAULT_DAYS
    return days if days in DAY_CHOICES else DEFAULT_DAYS


def flag(code):
    """"TR" → 🇹🇷; geçersizse boş."""
    code = (code or "").upper()
    if len(code) != 2 or not code.isalpha():
        return ""
    return "".join(chr(0x1F1E6 + ord(letter) - ord("A")) for letter in code)


def _percent(part, whole):
    return round(part * 100 / whole) if whole else 0


def _cart_events(since):
    sold = OrderItem.objects.sold().filter(order__cart=OuterRef("cart"), course=OuterRef("course"))
    return (
        CartAddEvent.objects.filter(created_at__gte=since)
        .filter(NOT_STAFF)
        .annotate(purchased=Exists(sold))
        .order_by()
    )


def _account_events(since):
    return AccountEvent.objects.filter(created_at__gte=since).filter(NOT_STAFF).order_by()


def _rows(queryset, path, with_sales=False):
    """[{key, count, sold, percent}] en çoktan aza; boş değer "" anahtarıyla."""
    values = dict(count=Count("pk"))
    if with_sales:
        values["sold"] = Count("pk", filter=Q(purchased=True))
    rows = list(queryset.annotate(key=KT(path)).values("key").annotate(**values).order_by("-count", "key"))
    for row in rows:
        row["key"] = row["key"] or ""
    return rows


def _label(group, key):
    if not key:
        return _("Bilinmiyor") if group != "source" else _("Doğrudan / bilinmiyor")
    if group == "device":
        return DEVICE_LABELS.get(key, key)
    if group == "language":
        return key.upper()
    return key


def _group(key, label, icon, path, carts, accounts):
    cart_rows = _rows(carts, path, with_sales=True)
    account_rows = {row["key"]: row["count"] for row in _rows(accounts.filter(kind=AccountEventKind.SIGNUP), path)}
    peak = max((row["count"] for row in cart_rows), default=0)
    rows = []
    for row in cart_rows[:TOP]:
        rows.append(
            dict(
                key=row["key"],
                label=_label(key, row["key"]),
                icon=DEVICE_ICONS.get(row["key"], "") if key == "device" else "",
                count=row["count"],
                sold=row["sold"],
                sold_percent=_percent(row["sold"], row["count"]),
                signups=account_rows.get(row["key"], 0),
                width=_percent(row["count"], peak),
            )
        )
    return dict(key=key, label=label, icon=icon, rows=rows, more=max(len(cart_rows) - TOP, 0))


def _countries(carts, accounts):
    """İlk TOP ülke (sepete eklemeye göre); kule yüksekliği en çoğa göre."""
    cart_rows = _rows(carts, "data__geo__country_code", with_sales=True)
    signups = {row["key"]: row["count"] for row in _rows(accounts.filter(kind=AccountEventKind.SIGNUP), "data__geo__country_code")}
    names = dict(carts.exclude(data__geo__country="").annotate(code=KT("data__geo__country_code"), name=KT("data__geo__country")).values_list("code", "name"))
    rows = cart_rows[:TOP]
    peak = rows[0]["count"] if rows else 0
    result = []
    for index, row in enumerate(rows):
        result.append(
            dict(
                code=row["key"],
                name=names.get(row["key"]) or row["key"] or _("Bilinmiyor"),
                flag=flag(row["key"]),
                count=row["count"],
                sold=row["sold"],
                sold_percent=_percent(row["sold"], row["count"]),
                signups=signups.get(row["key"], 0),
                height=round(0.12 + 0.88 * row["count"] / peak, 3) if peak else 0.02,
                x=index,
            )
        )
    return result


def _heatmap(carts):
    """Haftanın günü × saat (yerel saat) sepete ekleme sayısı; [{label, cells: [{hour, count, height}]}]."""
    counts = {
        (row["weekday"], row["hour"]): row["n"]
        for row in carts.annotate(weekday=KT("data__time__weekday"), hour=KT("data__time__hour")).values("weekday", "hour").annotate(n=Count("pk"))
        if row["weekday"] and row["hour"] is not None
    }
    counts = {(int(day), int(hour)): n for (day, hour), n in counts.items()}
    peak = max(counts.values(), default=0)
    return dict(
        peak=peak,
        days=[
            dict(
                label=WEEKDAYS[day - 1],
                y=day - 1,
                cells=[
                    dict(hour=hour, count=counts.get((day, hour), 0), height=round(0.08 + 0.92 * counts[(day, hour)] / peak, 3) if counts.get((day, hour)) else 0.02)
                    for hour in range(24)
                ],
            )
            for day in range(1, 8)
        ],
    )


def _split(queryset, group, path):
    """Kısa kırılım (cihaz ya da ülke): [{label, flag, count, width}] ilk TOP."""
    rows = _rows(queryset, path)[:TOP]
    peak = max((row["count"] for row in rows), default=0)
    return [
        dict(
            label=_label(group, row["key"]),
            flag=flag(row["key"]) if group == "country" else "",
            count=row["count"],
            width=_percent(row["count"], peak),
        )
        for row in rows
    ]


def watching(since):
    """Ders izleme: izleme günü, farklı üye, izlenen saat, tamamlanan; en çok izlenen dersler, cihaz ve ülke."""
    views = LessonView.objects.filter(day__gte=timezone.localdate(since)).filter(NOT_STAFF).order_by()
    totals = views.aggregate(
        count=Count("pk"),
        members=Count("user", distinct=True),
        seconds=Sum("watched_seconds"),
        opens=Sum("opens"),
        completed=Count("pk", filter=Q(completed_at__isnull=False)),
    )
    top = list(
        views.filter(lesson__isnull=False)
        .values("lesson", "lesson__title", "lesson__section__course__title")
        .annotate(members=Count("user", distinct=True), seconds=Sum("watched_seconds"))
        .order_by("-members", "-seconds", "lesson")[:5]
    )
    return dict(
        count=totals["count"],
        members=totals["members"],
        opens=totals["opens"] or 0,
        hours=round((totals["seconds"] or 0) / 3600, 1),
        completed=totals["completed"],
        top=[dict(row, minutes=round((row["seconds"] or 0) / 60)) for row in top],
        devices=_split(views, "device", "data__agent__type"),
        countries=_split(views, "country", "data__geo__country_code"),
    )


def pages(since):
    """Üye sayfa ziyaretleri: ziyaret, farklı üye; en çok açılan görünümler, cihaz ve ülke."""
    visits = PageView.objects.filter(created_at__gte=since).order_by()
    totals = visits.aggregate(count=Count("pk"), members=Count("user", distinct=True))
    top = list(visits.values("view_name").annotate(count=Count("pk"), members=Count("user", distinct=True)).order_by("-count", "view_name")[:TOP])
    peak = top[0]["count"] if top else 0
    return dict(
        count=totals["count"],
        members=totals["members"],
        per_member=round(totals["count"] / totals["members"], 1) if totals["members"] else 0,
        top=[dict(row, width=_percent(row["count"], peak)) for row in top],
        devices=_split(visits, "device", "data__agent__type"),
        countries=_split(visits, "country", "data__geo__country_code"),
    )


def overview(days=DEFAULT_DAYS):
    since = timezone.now() - timedelta(days=days)
    carts = _cart_events(since)
    accounts = _account_events(since)
    totals = carts.aggregate(count=Count("pk"), sold=Count("pk", filter=Q(purchased=True)))
    account_totals = accounts.aggregate(
        signups=Count("pk", filter=Q(kind=AccountEventKind.SIGNUP)),
        logins=Count("pk", filter=Q(kind=AccountEventKind.LOGIN)),
        members=Count("user", distinct=True, filter=Q(kind=AccountEventKind.LOGIN)),
    )
    return dict(
        days=days,
        day_choices=DAY_CHOICES,
        adds=totals["count"],
        sold=totals["sold"],
        sold_percent=_percent(totals["sold"], totals["count"]),
        guests=carts.filter(user__isnull=True).count(),
        **account_totals,
        countries=_countries(carts, accounts),
        groups=[_group(key, label, icon, path, carts, accounts) for key, label, icon, path in GROUPS],
        heatmap=_heatmap(carts),
        watching=watching(since),
        pages=pages(since),
    )
