"""Bağlantıyla gelen indirim kodu (?coupon=KOD): oturumda bekler, sepet açılınca ya da açık sepete hemen uygulanır.

Kod geçerliyse (discount.Discount.validate_for) oturuma yazılır; açık sepet varsa kod ona uygulanır ve oturumdan düşer,
yoksa ilk sepet açıldığında (cart.request_cart.current_cart) uygulanır. Sitedeki fiyatlar bekleyen ya da sepetteki
kodla indirimli gösterilir (active_discount, page.content.coupon_prices).
"""

from urllib.parse import urlsplit, urlunsplit

from django.core.exceptions import ValidationError
from django.http import QueryDict

from discount.models import Discount

PENDING_CODE_SESSION_KEY = "pending_discount_code"
CODE_PARAM = "coupon"


def _valid(code, user):
    discount = Discount.objects.by_code(code) if code else None
    if discount is None:
        raise ValidationError("Bu indirim kodu geçerli değil.")
    discount.validate_for(user)
    return discount


def capture(request, cart):
    """Bağlantıdaki kodu oturuma yazar; açık sepet (cart) varsa hemen uygular. (indirim kodu, yeni mi) döner: kod zaten
    bekliyor ya da sepete uygulanmışsa (adres parametresi kaldığı için sayfa yenilenince) yeni sayılmaz. Geçersizse
    ValidationError (eski bekleyen kod oturumda kalır)."""
    discount = _valid(request.GET.get(CODE_PARAM, ""), request.user)
    is_new = request.session.get(PENDING_CODE_SESSION_KEY) != discount.code and (cart is None or cart.discount_id != discount.pk)
    if cart is not None and cart.discount_id == discount.pk:
        return discount, is_new
    request.session[PENDING_CODE_SESSION_KEY] = discount.code
    if cart is not None:
        apply_pending(request, cart)
    return discount, is_new


def apply_pending(request, cart):
    """Bekleyen kodu sepete uygular ve oturumdan düşürür; artık geçerli değilse sessizce düşer."""
    code = request.session.pop(PENDING_CODE_SESSION_KEY, None)
    if not code or not cart.is_active:
        return None
    try:
        discount = _valid(code, request.user)
        cart.apply_discount(discount, request.user)
    except ValidationError:
        return None
    return discount


def active_discount(request, cart):
    """Sayfalarda fiyatı düşecek kod: oturumda bekleyen kod, yoksa sepete uygulanmış kod; geçerli değilse None."""
    code = request.session.get(PENDING_CODE_SESSION_KEY)
    if code:
        try:
            return _valid(code, request.user)
        except ValidationError:
            request.session.pop(PENDING_CODE_SESSION_KEY, None)
    if cart is not None and cart.discount_id:
        try:
            cart.discount.validate_for(request.user)
        except ValidationError:
            return None
        return cart.discount
    return None


def remove(request, cart):
    """Ziyaretçinin indirim kodunu kaldırır: oturumda bekleyen kod düşer, açık sepetteki kod çıkar."""
    request.session.pop(PENDING_CODE_SESSION_KEY, None)
    if cart is not None and cart.is_active and cart.discount_id:
        cart.remove_discount()


def without_code(url):
    """Adresten kod parametresi (?coupon=) çıkarılmış hâli: kod kaldırılınca sayfaya dönerken yeniden uygulanmasın."""
    parts = urlsplit(url)
    params = QueryDict(parts.query, mutable=True)
    params.pop(CODE_PARAM, None)
    return urlunsplit(parts._replace(query=params.urlencode()))
