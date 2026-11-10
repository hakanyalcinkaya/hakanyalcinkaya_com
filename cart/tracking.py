"""Sepete ekleme kaydı (CartAddEvent.data): ziyaretçi bilgileri (core.visitor) ve eklenen ürün. Kayıt hiçbir zaman sepete
eklemeyi engellemez: bir hata loglanır ve geçilir."""

import logging

from cart.models import CartAddEvent
from core import visitor

logger = logging.getLogger(__name__)


def _product(cart, course, bundle):
    product = course or bundle
    return dict(
        kind="course" if course else "bundle",
        slug=getattr(product, "slug", ""),
        title=str(product.title)[:300],
        price=str(product.price),
        list_price=str(product.compare_price) if product.compare_price is not None else "",
        cart_id=str(cart.pk),
        cart_items=cart.items.count(),
        has_discount_code=bool(cart.discount_id),
    )


def record(request, cart, source, course=None, bundle=None):
    try:
        return CartAddEvent.objects.create(
            cart=cart,
            course=course,
            bundle=bundle,
            user=request.user if request.user.is_authenticated else None,
            source=source,
            data=dict(visitor.collect(request), product=_product(cart, course, bundle)),
        )
    except Exception:  # noqa: BLE001
        logger.exception("Sepete ekleme kaydı yazılamadı")
        return None
