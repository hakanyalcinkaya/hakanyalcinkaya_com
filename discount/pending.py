"""Bağlantıyla gelen indirim kodu (?code=KOD): oturumda bekler, sepet açılınca ya da açık sepete hemen uygulanır.

Kod geçerliyse (discount.Discount.validate_for) oturuma yazılır; açık sepet varsa kod ona uygulanır ve oturumdan düşer,
yoksa ilk sepet açıldığında (cart.request_cart.current_cart) uygulanır. Kurs sayfası bekleyen ya da sepetteki kodla
indirimli fiyatı gösterir (active_discount).
"""

from django.core.exceptions import ValidationError

from discount.models import Discount

PENDING_CODE_SESSION_KEY = "pending_discount_code"
CODE_PARAM = "code"


def _valid(code, user):
    discount = Discount.objects.by_code(code) if code else None
    if discount is None:
        raise ValidationError("Bu indirim kodu geçerli değil.")
    discount.validate_for(user)
    return discount


def capture(request, cart):
    """Bağlantıdaki kodu oturuma yazar; açık sepet (cart) varsa hemen uygular. Uygulanan ya da bekleyen indirim kodu
    döner; geçersizse ValidationError (eski bekleyen kod oturumda kalır)."""
    discount = _valid(request.GET.get(CODE_PARAM, ""), request.user)
    request.session[PENDING_CODE_SESSION_KEY] = discount.code
    if cart is not None:
        apply_pending(request, cart)
    return discount


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
