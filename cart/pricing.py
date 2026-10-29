"""Sepet fiyat hesabı: kurs, paket, indirim kodu ve kullanıcının sahip olduğu kurslar birlikte değerlendirilir.

Sıra: ürün fiyatı → indirim kodu → (paketlerde) kullanıcının zaten sahip olduğu kurslar için ödediği tutar düşülür.
Hediye ya da manuel verilen kursta düşülecek tutar 0'dır. Hiçbir fiyat 0'ın altına inmez.
"""

from dataclasses import dataclass, field
from decimal import Decimal

ZERO = Decimal("0")


@dataclass
class CartLine:
    item: object
    product: object
    base_price: Decimal
    compare_price: Decimal
    final_price: Decimal
    owned_credit: Decimal = ZERO
    owned_courses: list = field(default_factory=list)

    @property
    def is_discounted(self):
        return self.final_price < self.compare_price


@dataclass
class CartSummary:
    lines: list
    discount: object = None

    @property
    def subtotal(self):
        return sum((line.base_price for line in self.lines), ZERO)

    @property
    def total(self):
        return sum((line.final_price for line in self.lines), ZERO)

    @property
    def discount_total(self):
        return self.subtotal - self.total

    @property
    def count(self):
        return len(self.lines)


def paid_amount_for(user, course):
    """Kullanıcının bu kurs için ödediği tutar (son ödenmiş sipariş kalemi); satın almadıysa 0."""
    from order.models import OrderItem, OrderStatus

    item = (
        OrderItem.objects.filter(order__user=user, order__status=OrderStatus.PAID, course=course)
        .order_by("-order__paid_at")
        .first()
    )
    return item.paid_price if item else ZERO


def price_cart(cart, user=None):
    return price_items(cart.items.select_related("course", "bundle"), user or cart.user, cart.discount)


def price_items(items, user=None, discount=None):
    """Sepet ürünleri (kayıtlı ya da kaydedilmemiş CartItem) için fiyat; yönetici siparişi sepet olmadan da hesaplanır."""
    owned = set(user.enrollments.values_list("course_id", flat=True)) if user and user.is_authenticated else set()
    lines = []
    for item in items:
        product = item.product
        base = product.price
        compare = max(product.compare_price or base, base)
        final = discount.price_for(product, base) if discount else base
        credit = ZERO
        owned_courses = []
        if item.bundle_id and owned:
            owned_courses = [course for course in product.courses.all() if course.pk in owned]
            credit = sum((paid_amount_for(user, course) for course in owned_courses), ZERO)
            final = max(final - credit, ZERO)
        lines.append(CartLine(item, product, base, compare, final, credit, owned_courses))
    return CartSummary(lines, discount)
