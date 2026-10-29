from django.urls import reverse
from django.utils import timezone
from django.utils.functional import SimpleLazyObject

from core.models import SiteSettings
from newsletter.models import Subscriber

from page import content
from page.catalog import (
    NAV,
    NEWSLETTER_SESSION_KEY,
    SHOP_URL_NAMES,
)


def site(request):
    index_url = reverse("page:index")
    course_list_url = reverse("page:course_list")
    match = request.resolver_match
    url_name = match.url_name if match else ""
    user = request.user
    cards = content.catalog_cards(user)
    cart_count = len(content.cart_cards(request.session, user, cards))
    nav_items = []
    for item_id, label in NAV:
        if item_id == "egitimler":
            href = course_list_url
        else:
            href = f"{index_url}#{item_id}"
        nav_items.append({"id": item_id, "href": href, "label": label})
    return {
        "courses": cards,
        "nav_items": nav_items,
        "year": timezone.now().year,
        "login_url": reverse("page:login"),
        "join_url": reverse("page:signup"),
        "logout_url": reverse("page:logout"),
        "settings_url": reverse("page:account_settings"),
        "privacy_url": reverse("page:privacy"),
        "terms_url": reverse("page:terms"),
        "cookies_url": reverse("page:cookies"),
        "nav_member": user.is_authenticated,
        "account_user": user if user.is_authenticated else None,
        # Ziyaretçi sepeti her zaman görür; üye yalnız sepetinde kurs varken.
        "show_cart": not user.is_authenticated or cart_count > 0,
        # "Kursları Keşfet" yalnız ziyaretçiye ve mağaza sayfaları dışında.
        "show_explore": not user.is_authenticated and url_name not in SHOP_URL_NAMES,
        "cart_url": reverse("page:cart"),
        "cart_count": cart_count,
        "library_url": reverse("page:library"),
        # Stüdyo "Ayarlar"ı (ör. not alma açık mı); yalnız şablonda kullanılırsa okunur.
        "site_settings": SimpleLazyObject(SiteSettings.load),
        # Bülten kutusu: form yerine gösterilecek durum (abonesin / onay bekliyor / gönderildi); yoksa form.
        "newsletter_state": SimpleLazyObject(
            lambda: Subscriber.state_for(user, request.session.get(NEWSLETTER_SESSION_KEY, "")) or {}
        ),
    }
