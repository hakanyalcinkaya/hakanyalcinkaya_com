"""Podia'daki eski satışların aktarımı: her fatura ödenmiş bir sipariş ve kurs kaydı olur.

Fatura numarası siparişin ödeme referansıdır; aynı fatura ikinci kez aktarılmaz, yani aktarım tekrar çalıştırılabilir
(ör. geçiş tamamlanana kadar Podia'da yapılan yeni satışlar için). Kullanıcı e-postayla bulunur ya da şifresiz açılır;
şifresini "Şifremi unuttum" ya da davet e-postasıyla belirler. Var olan kullanıcının adı değiştirilmez.
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Count, Exists, OuterRef, Q, Subquery

from account.models import PASSWORD_SET, User
from core.models import Status
from course.models import Course
from learning.models import Enrollment, EnrollmentSource
from order.models import Order, OrderItem, OrderStatus

PROVIDER = "podia"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S %z"
REQUIRED_COLUMNS = ("Invoice #", "Date", "Name", "Email", "Status", "Items", "Subtotal", "Discount", "Total", "Currency", "Coupon")


class PodiaImportError(Exception):
    pass


@dataclass
class ImportReport:
    orders_created: int = 0
    orders_skipped: int = 0
    users_created: int = 0
    users_existing: int = 0
    enrollments_created: int = 0
    enrollments_existing: int = 0
    unmatched_items: dict = field(default_factory=dict)
    skipped_status: int = 0
    errors: list = field(default_factory=list)


def course_rules(pairs, courses=None):
    """["React 18.x=react", ...] → [(ürün adında geçen metin, kurs)]. Kurs slug'ı yoksa hata."""
    courses = courses if courses is not None else Course.objects.all()
    rules = []
    for pair in pairs:
        text, _sep, slug = pair.partition("=")
        if not text.strip() or not slug.strip():
            raise PodiaImportError(f"Eşleşme '{pair}' biçiminde olmalı: 'ürün adında geçen metin=kurs-slug'.")
        course = courses.filter(slug=slug.strip()).first()
        if course is None:
            raise PodiaImportError(f"'{slug.strip()}' slug'lı kurs yok; önce kursu aç.")
        rules.append((text.strip(), course))
    return rules


def match_course(item, rules):
    """Ürün adı tam olarak bir kurala uymalı; hiçbirine ya da birden fazlasına uyarsa None."""
    matches = {course.pk: course for text, course in rules if text.casefold() in item.casefold()}
    return next(iter(matches.values())) if len(matches) == 1 else None


def _money(value):
    try:
        return Decimal(str(value or "0")).quantize(Decimal("0.01"))
    except InvalidOperation as error:
        raise PodiaImportError(f"Tutar okunamadı: {value!r}") from error


def _coupon(value):
    """"KENDINIGELISTIRMEYEDEVAM (€15 off)" → "KENDINIGELISTIRMEYEDEVAM"."""
    return (value or "").split(" (")[0].strip()[:40]


def _names(full_name):
    parts = (full_name or "").split()
    if len(parts) < 2:
        return " ".join(parts), ""
    return " ".join(parts[:-1]), parts[-1]


def _user(email, full_name, report):
    user = User.objects.with_email(email).first()
    if user is not None:
        report.users_existing += 1
        return user
    first_name, last_name = _names(full_name)
    user = User.objects.create_user(email=email, password=None, first_name=first_name[:150], last_name=last_name[:150])
    report.users_created += 1
    return user


def import_rows(rows, rules, dry_run=False):
    """rows: başlık satırındaki sütun adlarıyla sözlükler. Deneme modunda hiçbir şey kaydedilmez, rapor yine üretilir."""
    report = ImportReport()
    with transaction.atomic():
        for row in rows:
            invoice = str(row.get("Invoice #") or "").strip()
            email = str(row.get("Email") or "").strip().lower()
            if not invoice or not email:
                report.errors.append(f"Fatura no ya da e-posta boş: {invoice or '?'}")
                continue
            if str(row.get("Status") or "").strip() != "Completed":
                report.skipped_status += 1
                continue
            if Order.objects.filter(payment_provider=PROVIDER, payment_reference=invoice).exists():
                report.orders_skipped += 1
                continue
            item = str(row.get("Items") or "").strip()
            course = match_course(item, rules)
            if course is None:
                report.unmatched_items[item] = report.unmatched_items.get(item, 0) + 1
                continue
            try:
                paid_at = datetime.strptime(str(row["Date"]).strip(), DATE_FORMAT)
            except ValueError:
                report.errors.append(f"Tarih okunamadı ({invoice}): {row.get('Date')!r}")
                continue
            user = _user(email, str(row.get("Name") or ""), report)
            subtotal, total = _money(row.get("Subtotal")), _money(row.get("Total"))
            order = Order.objects.create(
                user=user,
                email=email,
                status=OrderStatus.PAID,
                subtotal=subtotal,
                discount_total=_money(row.get("Discount")),
                total=total,
                discount_code=_coupon(row.get("Coupon")),
                payment_provider=PROVIDER,
                payment_reference=invoice,
                paid_at=paid_at,
                currency=str(row.get("Currency") or "EUR").strip()[:3].upper(),
            )
            OrderItem.objects.create(order=order, course=course, title=item[:200], unit_price=subtotal, paid_price=total)
            report.orders_created += 1
            _enrollment, created = Enrollment.objects.get_or_create(
                user=user, course=course, defaults={"source": EnrollmentSource.IMPORTED, "order": order}
            )
            if created:
                report.enrollments_created += 1
            else:
                report.enrollments_existing += 1
        if dry_run:
            transaction.set_rollback(True)
    return report


def invite_candidates(resend=False):
    """Podia'dan aktarılan siparişi olan etkin kullanıcılar; resend değilse "Hesabın taşındı" e-postası daha önce
    gönderilmiş olanlar (mailing.EmailLog) çıkarılır."""
    from mailing.models import EmailLog, EmailStatus

    users = User.objects.filter(is_active=True, orders__payment_provider=PROVIDER).distinct().order_by("date_joined", "pk")
    if not resend:
        invited = EmailLog.objects.filter(template="account_migrated", status=EmailStatus.SENT, user__isnull=False)
        users = users.exclude(pk__in=invited.values("user"))
    return users


def with_invite(users):
    """Kullanıcılara Podia aktarımı ve "Hesabın taşındı" e-postasının durumu: podia_imported, invite_sent_at (son başarılı
    gönderim), invite_opened_at ve invite_clicked_at (gönderilen davetlerde ilk açılma / tıklama) ve has_watched (ders
    izlemeye başladı)."""
    from mailing.models import EmailLog, EmailStatus

    invites = EmailLog.objects.filter(template="account_migrated", status=EmailStatus.SENT, user=OuterRef("pk"))
    return users.annotate(
        podia_imported=Exists(Order.objects.filter(user=OuterRef("pk"), payment_provider=PROVIDER)),
        invite_sent_at=Subquery(invites.order_by("-sent_at").values("sent_at")[:1]),
        invite_opened_at=Subquery(invites.exclude(first_opened_at=None).order_by("first_opened_at").values("first_opened_at")[:1]),
        invite_clicked_at=Subquery(invites.exclude(first_clicked_at=None).order_by("first_clicked_at").values("first_clicked_at")[:1]),
        has_watched=Exists(Enrollment.objects.filter(user=OuterRef("pk"), last_watched_at__isnull=False)),
    )


def invite_report():
    """Podia'dan aktarılan etkin üyelerde davetin ilerleyişi: aktarılan, davet gönderilen, açan, tıklayan, şifresini
    belirleyen ve ders izlemeye başlayan sayıları (stüdyo öğrenciler sayfası)."""
    users = with_invite(User.objects.filter(is_active=True)).filter(podia_imported=True)
    report = users.aggregate(
        imported=Count("pk"),
        sent=Count("pk", filter=Q(invite_sent_at__isnull=False)),
        opened=Count("pk", filter=Q(invite_opened_at__isnull=False)),
        clicked=Count("pk", filter=Q(invite_clicked_at__isnull=False)),
        password_set=Count("pk", filter=PASSWORD_SET),
        watched=Count("pk", filter=Q(has_watched=True)),
    )
    # Oranlar (%): davet gönderilen aktarılanlara, sonrakiler davet gönderilenlere göre.
    report["sent_rate"] = round(report["sent"] * 100 / report["imported"]) if report["imported"] else 0
    for name in ("opened", "clicked", "password_set", "watched"):
        report[f"{name}_rate"] = round(report[name] * 100 / report["sent"]) if report["sent"] else 0
    return report


def unpublished_imported_courses():
    """Podia siparişlerindeki kurslardan henüz yayında olmayanlar (davet öncesi uyarı)."""
    return (
        Course.objects.filter(order_items__order__payment_provider=PROVIDER)
        .exclude(status=Status.PUBLISHED)
        .distinct()
        .order_by("title")
    )
