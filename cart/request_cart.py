"""Ziyaretçinin sepeti (cart.Cart): üyede kullanıcıya, misafirde oturuma bağlı.

Misafir sepetinin kimliği oturumda tutulur; girişte oturum anahtarı değişse de veri kalır, misafir sepeti üyenin sepetine
katılır (sahip olunan kurslar taşınmaz).
"""

from cart.models import Cart

GUEST_CART_SESSION_KEY = "guest_cart_id"


def current_cart(request, create=False):
    """Açık sepet; yoksa None (create=True ise açılır)."""
    if request.user.is_authenticated:
        cart = Cart.objects.active().filter(user=request.user).first()
        if cart is None and create:
            cart = Cart.objects.create(user=request.user)
        return cart
    cart_id = request.session.get(GUEST_CART_SESSION_KEY)
    cart = Cart.objects.active().filter(pk=cart_id, user__isnull=True).first() if cart_id else None
    if cart is None and create:
        if not request.session.session_key:
            request.session.save()
        cart = Cart.objects.create(session_key=request.session.session_key)
        request.session[GUEST_CART_SESSION_KEY] = str(cart.pk)
    return cart


def merge_guest_cart(sender, request, user, **kwargs):
    """user_logged_in: misafir sepetini üyenin açık sepetine katar."""
    if request is None or not hasattr(request, "session"):
        return
    cart_id = request.session.pop(GUEST_CART_SESSION_KEY, None)
    guest = Cart.objects.active().filter(pk=cart_id, user__isnull=True).first() if cart_id else None
    if guest is None:
        return
    if not guest.items.exists():
        guest.empty()
        return
    target = Cart.objects.active().filter(user=user).first() or Cart.objects.create(user=user)
    guest.merge_into(target)
