"""Stüdyo izometrik panosu: genel istatistiklerin (overview_stats, period_stats) sayılarını kule, şehir ve çubuk
yüksekliklerine çevirir. Tanımlar genel istatistiklerle aynıdır; burada yalnız ölçekleme ve seçim yapılır.

Yükseklikler 0–1 arası oranlardır (şablonda CSS --t). Farklı birimlerdeki kuleler karekökle ölçeklenir ki küçük
sayılar da görünsün; aynı birimdeki çubuklar (aylar, kurslar) doğrusal, en yükseğe göre ölçeklenir.
"""

from math import sqrt

from django.utils.translation import gettext_lazy as _

from core.money import format_money

# En alçak kule bile görünsün diye taban oran; sıfır değer zemine yakın ince bir levhadır.
FLOOR = 0.12
ZERO = 0.02
# Nabız kartlarında dönem karşılaştırmasından gösterilen satırlar.
PULSE_KEYS = ("sales", "revenue", "members", "enrollments", "opened", "completed")
PULSE_ICONS = dict(
    sales="bag-check",
    revenue="cash-stack",
    members="person-plus",
    enrollments="journal-plus",
    opened="play-circle",
    completed="check2-circle",
)
CITY_COURSES = 12
CITY_COLUMNS = 4
CITY_COLORS = ("#6366F1", "#3B82F6", "#F97316", "#EC4899", "#14B8A6", "#A855F7")


def _linear(value, peak):
    return round(FLOOR + (1 - FLOOR) * value / peak, 3) if value and peak else ZERO


def _try_total(revenue):
    return next((row["total"] for row in revenue if row["currency"] == "TRY"), 0)


def towers(stats):
    """Ana kuleler: öğrenci, aktif öğrenci, satış, TL gelir, bekleyen sepet. Gelir varsa gelir kulesi en yüksektir."""
    rows = [
        dict(key="students", label=_("Öğrenci"), icon="mortarboard", value=stats["student_total"], note=_("%(count)s kurs kaydı") % dict(count=stats["enrollments"]["total"])),
        dict(key="active", label=_("Aktif öğrenci"), icon="play-circle", value=stats["active_students"], note=_("son %(days)s günde ders açan") % dict(days=stats["active_days"])),
        dict(key="sales", label=_("Satış"), icon="bag-check", value=stats["order_total"], note=_("%(count)s alıcı") % dict(count=stats["buyer_total"])),
        dict(key="carts", label=_("Sepette"), icon="cart3", value=stats["waiting"]["total"], note=format_money(stats["waiting"]["amount"])),
    ]
    peak = sqrt(max((row["value"] for row in rows), default=0))
    for row in rows:
        row["height"] = round(FLOOR + (0.82 - FLOOR) * sqrt(row["value"]) / peak, 3) if row["value"] else ZERO
    revenue = _try_total(stats["revenue"])
    rows.insert(
        2,
        dict(key="revenue", label=_("Gelir"), icon="cash-stack", value=None, label_value=format_money(revenue), note=_("tüm zamanlar, TL"), height=1 if revenue else ZERO),
    )
    return rows


def pulse(comparison):
    """Dönem karşılaştırmasından seçili satırlar; hücrelerde bugün, bu hafta, bu ay ve önceki döneme göre değişim."""
    rows = {row["key"]: row for section in comparison["sections"] for row in section["rows"]}
    return [dict(rows[key], icon=PULSE_ICONS[key]) for key in PULSE_KEYS if key in rows]


def trend(rows):
    """Son 12 ay: satış adedi ve yeni kurs kaydı çubukları, ikisi de kendi en yükseğine göre."""
    for row in rows:
        row["enrollment_total"] = sum(group["count"] for group in row["enrollments"])
    sales_peak = max((row["count"] for row in rows), default=0)
    enrollment_peak = max((row["enrollment_total"] for row in rows), default=0)
    for row in rows:
        row["sales_height"] = _linear(row["count"], sales_peak)
        row["enrollment_height"] = _linear(row["enrollment_total"], enrollment_peak)
    return rows


def city(courses):
    """Kurs şehri: en çok kaydı olan CITY_COURSES kurs CITY_COLUMNS sütunlu ızgarada; bina yüksekliği kayda, parlayan
    kat bitirme oranına göre."""
    rows = sorted((course for course in courses if course.enrollment_total), key=lambda course: -course.enrollment_total)[:CITY_COURSES]
    peak = rows[0].enrollment_total if rows else 0
    for index, course in enumerate(rows):
        course.city_height = _linear(course.enrollment_total, peak)
        course.city_x, course.city_y = index % CITY_COLUMNS, index // CITY_COLUMNS
        course.city_color = CITY_COLORS[index % len(CITY_COLORS)]
    return dict(courses=rows, columns=min(len(rows), CITY_COLUMNS), rows=-(-len(rows) // CITY_COLUMNS))
