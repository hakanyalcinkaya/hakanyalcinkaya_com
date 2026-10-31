"""Stüdyo sepet istatistikleri: ayın sepet hunisi (sepet → ödeme adımı → sipariş → ödeme), ürün bazında eklenen ve
çıkarılanlar, şu an sepette bekleyenler.

Huni, ay içinde açılan sepetleri izler (kohort). Üye sepetine katılan misafir sepetleri sayılmaz; ürünleri üyenin
sepetinde sayılır. Çıkarılan ürünler ve ödeme adımına geçiş, kaydı tutulmaya başladığı tarihten itibaren bilinir.
"""

from collections import defaultdict
from datetime import timedelta

from django.db.models import Count, Exists, OuterRef, Q, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from cart.models import Cart, CartItem, CartItemRemoval, CartRemovalReason, CartStatus
from course.models import Bundle, Course
from order.models import Order, OrderStatus

# Sepet bu kadar gün değişmezse "uzun süredir bekliyor" sayılır.
IDLE_DAYS = 7


def _percent(part, whole):
    return round(part * 100 / whole) if whole else 0


def funnel(start, end):
    """Ayda açılıp içine ürün eklenen sepetlerin hangi adıma kadar gittiği."""
    cohort = Cart.objects.countable().with_products().filter(created_at__gte=start, created_at__lt=end)
    carts = Cart.objects.filter(pk__in=cohort.values("pk")).annotate(
        has_order=Exists(Order.objects.filter(cart=OuterRef("pk"))),
    )
    totals = carts.aggregate(
        total=Count("pk"),
        members=Count("pk", filter=Q(user__isnull=False)),
        checkout=Count("pk", filter=Q(checkout_at__isnull=False) | Q(has_order=True) | Q(status=CartStatus.CONVERTED)),
        ordered=Count("pk", filter=Q(has_order=True)),
        paid=Count("pk", filter=Q(status=CartStatus.CONVERTED)),
        gifted=Count("pk", filter=Q(status=CartStatus.GIFTED)),
        emptied=Count("pk", filter=Q(status=CartStatus.EMPTIED)),
        open=Count("pk", filter=Q(status=CartStatus.ACTIVE)),
    )
    total = totals["total"]
    labels = (
        ("total", _("Sepete ürün ekledi")),
        ("checkout", _("Ödeme adımına geçti")),
        ("ordered", _("Sipariş oluştu")),
        ("paid", _("Ödendi")),
    )
    steps, previous = [], total
    for key, label in labels:
        count = totals[key]
        steps.append(dict(key=key, label=label, count=count, percent=_percent(count, total), lost=max(previous - count, 0)))
        previous = count
    return dict(totals, steps=steps, guests=total - totals["members"])


def _product_key(course_id, bundle_id):
    return ("bundle", bundle_id) if bundle_id else ("course", course_id)


def products(start, end):
    """Ürün bazında: ayda eklenen, ziyaretçinin çıkardığı, paket/sahiplik nedeniyle düşen, sepetten satın alınan ve
    şu an açık sepetlerde bekleyen adetler. Eklenen = ayda eklenip hâlâ sepette duran + ayda eklenip sonradan çıkan."""
    rows = defaultdict(lambda: dict(added=0, removed=0, dropped=0, purchased=0, waiting=0))
    items = CartItem.objects.filter(cart__in=Cart.objects.countable()).order_by()
    removals = CartItemRemoval.objects.countable().order_by()

    def collect(queryset, field):
        for row in queryset.values("course_id", "bundle_id").annotate(n=Count("pk")):
            rows[_product_key(row["course_id"], row["bundle_id"])][field] += row["n"]

    collect(items.filter(created_at__gte=start, created_at__lt=end), "added")
    collect(removals.filter(added_at__gte=start, added_at__lt=end), "added")
    in_month = removals.filter(created_at__gte=start, created_at__lt=end)
    collect(in_month.filter(reason=CartRemovalReason.REMOVED), "removed")
    collect(in_month.exclude(reason=CartRemovalReason.REMOVED), "dropped")
    collect(items.filter(cart__status=CartStatus.CONVERTED, cart__converted_at__gte=start, cart__converted_at__lt=end), "purchased")
    collect(items.filter(cart__status=CartStatus.ACTIVE), "waiting")

    courses = Course.objects.in_bulk([pk for kind, pk in rows if kind == "course"])
    bundles = Bundle.objects.in_bulk([pk for kind, pk in rows if kind == "bundle"])
    result = []
    for (kind, pk), counts in rows.items():
        product = (bundles if kind == "bundle" else courses).get(pk)
        if product is None:
            continue
        result.append(dict(counts, product=product, is_bundle=kind == "bundle", removed_percent=_percent(counts["removed"], counts["added"])))
    result.sort(key=lambda row: (-row["added"], -row["waiting"], row["product"].title))
    return result


def waiting():
    """Şu an açık ve içinde ürün olan sepetler: hangi adımda bekledikleri, kaçının uzun süredir değişmediği."""
    carts = Cart.objects.active().filter(pk__in=Cart.objects.active().filter(items__isnull=False).values("pk")).annotate(
        has_pending_order=Exists(Order.objects.filter(cart=OuterRef("pk"), status=OrderStatus.PENDING)),
    )
    totals = carts.aggregate(
        total=Count("pk"),
        members=Count("pk", filter=Q(user__isnull=False)),
        cart_step=Count("pk", filter=Q(checkout_at__isnull=True)),
        checkout_step=Count("pk", filter=Q(checkout_at__isnull=False)),
        pending_order=Count("pk", filter=Q(has_pending_order=True)),
        idle=Count("pk", filter=Q(updated_at__lt=timezone.now() - timedelta(days=IDLE_DAYS))),
    )
    value = CartItem.objects.filter(cart__status=CartStatus.ACTIVE).aggregate(
        items=Count("pk"), amount=Sum(Coalesce("course__price", "bundle__price"))
    )
    return dict(totals, guests=totals["total"] - totals["members"], item_total=value["items"], amount=value["amount"] or 0, idle_days=IDLE_DAYS)
