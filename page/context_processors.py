from django.conf import settings
from django.urls import reverse
from django.utils import timezone
from django.utils.functional import SimpleLazyObject

from core.models import SiteSettings
from core.version import app_version
from core.site_url import absolute_url
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
    cart_count = len(content.cart_cards(request, cards))
    nav_items = []
    for item_id, label in NAV:
        # Giriş yapan üyeye tanıtım bölümleri (Öğrenci Yorumları, Hakkımda) gösterilmez; yalnız Kurslar.
        if user.is_authenticated and item_id != "egitimler":
            continue
        if item_id == "egitimler":
            href = course_list_url
        else:
            href = f"{index_url}#{item_id}"
        nav_items.append({"id": item_id, "href": href, "label": label})
    return {
        # Sorgu parametresiz asıl adres: filtre, utm ve e-posta takibi parametreli adresler aynı sayfaya bağlanır.
        "canonical_url": absolute_url(request.path),
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
        # Google Analytics: tanımlıysa çerez izni bandı gösterilir, etiket yalnız izinle yüklenir (site.js). Yöneticinin
        # (staff) ziyaretleri ölçülmez: ona bant da etiket de hiç gelmez.
        "google_analytics_id": "" if user.is_staff else settings.GOOGLE_ANALYTICS_ID,
        "nav_member": user.is_authenticated,
        "account_user": user if user.is_authenticated else None,
        # Sepet simgesi herkese, her zaman (boşken de) üst menüde görünür.
        "show_cart": True,
        # "Kursları Keşfet" yalnız ziyaretçiye ve mağaza sayfaları dışında.
        "show_explore": not user.is_authenticated and url_name not in SHOP_URL_NAMES,
        "cart_url": reverse("page:cart"),
        "cart_count": cart_count,
        "library_url": reverse("page:library"),
        # Stüdyo "Ayarlar"ı (ör. not alma açık mı); yalnız şablonda kullanılırsa okunur.
        "site_settings": SimpleLazyObject(SiteSettings.load),
        # Superuser'a menüde sürüm (v + commit sayısı): yerel ile sunucunun aynı commit'te olup olmadığı görülür.
        "app_version": SimpleLazyObject(app_version) if user.is_superuser else None,
        # Bülten kutusu: form yerine gösterilecek durum (abonesin / onay bekliyor / gönderildi); yoksa form.
        "newsletter_state": SimpleLazyObject(
            lambda: Subscriber.state_for(user, request.session.get(NEWSLETTER_SESSION_KEY, "")) or {}
        ),
    }
