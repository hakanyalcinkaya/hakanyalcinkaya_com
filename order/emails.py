"""E-posta değişkenleri: alıcı bilgileri ve siparişlerden ürün/tutar listesi (bkz. core.emails)."""

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from core.money import format_money


def absolute(path):
    return settings.SITE_URL.rstrip("/") + path


def recipient_context(user):
    first, last = user.first_name.strip(), user.last_name.strip()
    return {
        "first_name": first,
        "last_name": last,
        "full_name": " ".join(part for part in (first, last) if part),
        "greeting_name": first,
        "email": user.email,
        "site_url": settings.SITE_URL.rstrip("/"),
        "library_url": absolute(reverse("page:library")),
        "login_url": absolute(reverse("page:login")),
    }


def order_items_context(orders):
    """Siparişlerin kalemleri ve ilk ürün için kısayollar."""
    orders = list(orders)
    items = []
    for order in orders:
        for item in order.items.select_related("course", "bundle"):
            product = item.course or item.bundle
            items.append(
                {
                    "title": item.title,
                    "url": absolute(product.get_absolute_url()) if product and item.course_id else "",
                    "price": format_money(item.unit_price, order.currency),
                    "paid_price": format_money(item.paid_price, order.currency),
                    "discount": format_money(item.unit_price - item.paid_price, order.currency)
                    if item.unit_price > item.paid_price
                    else "",
                    "purchased_at": order.paid_at,
                }
            )
    first = orders[0] if orders else None
    total = sum((order.total for order in orders), 0)
    return {
        "items": items,
        "product_title": items[0]["title"] if items else "",
        "product_price": items[0]["price"] if items else "",
        "paid_price": items[0]["paid_price"] if items else "",
        "order_number": first.number if first else "",
        "order_total": format_money(total, first.currency) if first else "",
        "currency": first.currency if first else "",
        "coupon": first.discount_code if first else "",
        "purchased_at": first.paid_at if first else None,
    }


def password_url(user):
    """Tek kullanımlık şifre belirleme/sıfırlama bağlantısı (Django'nun şifre sıfırlama belirteci)."""
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    return absolute(reverse("page:password_reset_confirm", kwargs={"uidb64": uid, "token": token}))


def account_migrated_context(user):
    """Podia'dan taşınan müşteri: aktarılan tüm siparişleri ve şifre belirleme bağlantısı."""
    from order.podia import PROVIDER

    orders = user.orders.filter(payment_provider=PROVIDER).order_by("paid_at")
    return {**recipient_context(user), **order_items_context(orders), "set_password_url": password_url(user)}


def purchase_confirmation_context(order):
    return {**recipient_context(order.user), **order_items_context([order])}


def password_reset_context(user, reset_url=None):
    return {**recipient_context(user), "reset_url": reset_url or password_url(user)}


def preview_context(key, user):
    """Stüdyo önizlemesi: seçilen kullanıcının gerçek verisi (ad, e-posta; taşınma, son sipariş, şifre bağlantısı).

    Kullanıcıya ait olmayan değişkenler (ör. kurs bitirme tarihi) örnek veriden gelir.
    """
    from core.emails import sample_context
    from order.models import Order

    context = {**sample_context(key), **recipient_context(user)}
    if key == "account_migrated":
        context.update(account_migrated_context(user))
    elif key in ("purchase_confirmation", "admin_new_order"):
        order = Order.objects.paid().filter(user=user).order_by("-paid_at").first()
        if order is not None:
            context.update(order_items_context([order]))
    elif key == "password_reset":
        context.update(password_reset_context(user))
    return context
