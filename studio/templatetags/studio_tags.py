from django import template
from django.urls import reverse

from course.models import VideoUpload

register = template.Library()


@register.simple_tag
def busy_upload_total():
    """Stüdyo menüsündeki kuyruk rozeti: süren video yüklemeleri."""
    return VideoUpload.objects.busy().count()


@register.simple_tag
def pending_review_total():
    """Stüdyo menüsündeki "Yorumlar" rozeti: onay bekleyen yorumlar."""
    from course.models import Review

    return Review.objects.awaiting().count()


@register.simple_tag
def awaiting_support_total():
    """Stüdyo menüsündeki "Destek" rozeti: yanıt bekleyen talepler."""
    from support.models import Ticket

    return Ticket.objects.awaiting().count()


@register.simple_tag
def video_accept():
    """Dosya seçicinin kabul ettiği video uzantıları (sunucudaki doğrulamayla aynı liste)."""
    from course.models import VIDEO_EXTENSIONS

    return ",".join(VIDEO_EXTENSIONS)


@register.simple_tag(takes_context=True)
def title_sync_enabled(context):
    """Ayarlarda başlık güncelleme açık mı; her ders satırında sorulduğu için istek başına bir kez okunur."""
    from core.models import SiteSettings

    request = context.get("request")
    if request is None:
        return SiteSettings.title_sync_enabled()
    if not hasattr(request, "_title_sync_enabled"):
        request._title_sync_enabled = SiteSettings.title_sync_enabled()
    return request._title_sync_enabled


@register.simple_tag
def video_platform_label():
    """Yeni yüklemelerin gideceği platformun adı (stüdyo "Ayarlar"ından)."""
    from course import video_service

    return video_service.current().LABEL


# Kaydırınca yüklenen listeler: sayfanın sonundaki gözcü satır görünür olunca sonraki sayfanın satırları istenir.
ROWS_PARAM = "part"


@register.simple_tag(takes_context=True)
def next_rows_url(context, page):
    """Geçerli filtrelerle sonraki sayfanın yalnız satırlarını isteyen adres (?...&page=N&part=satir)."""
    request = context["request"]
    params = request.GET.copy()
    params["page"] = page.next_page_number()
    params[ROWS_PARAM] = "rows"
    return f"{request.path}?{params.urlencode()}"


NAV_SECTIONS = (
    ("stats", ("stats",)),
    ("courses", ("course_", "section_", "lesson_", "extra_content", "subtitle_")),
    ("catalog", ("catalog_", "personal_")),
    ("sales", ("order", "cart")),
    ("students", ("student", "enrollment", "watch_log")),
    ("reviews", ("review",)),
    ("support", ("support",)),
    ("mail", ("email", "newsletter", "subscriber")),
    ("queue", ("queue", "upload_")),
    ("settings", ("settings",)),
)


@register.simple_tag(takes_context=True)
def studio_section(context):
    """Menüde vurgulanacak bölüm (geçerli adresin adına göre)."""
    match = getattr(context.get("request"), "resolver_match", None)
    name = match.url_name if match else ""
    return next((section for section, prefixes in NAV_SECTIONS if name.startswith(prefixes)), "")


# Mobil stüdyo menüsü: gruplar ve bağlantılar (ad, simge, url adı ve argümanı, rozet anahtarı). Masaüstü menüsüyle aynı
# sayfalar; masaüstünde açılır menüde olanlar burada başlıklı grup olarak alt alta durur.
MOBILE_NAV = (
    ("Genel", (
        ("Kurslar", "bi-collection-play", "course_list", None, ""),
        ("İstatistikler", "bi-graph-up", "stats", None, ""),
        ("Yorumlar", "bi-chat-square-quote", "reviews", None, "reviews"),
        ("Destek", "bi-life-preserver", "support_list", None, "support"),
        ("Kuyruk", "bi-list-task", "queue", None, "queue"),
        ("Ayarlar", "bi-gear", "settings", None, ""),
    )),
    ("Satışlar", (
        ("Siparişler", "bi-receipt", "orders", None, ""),
        ("Sepetler", "bi-cart", "carts", None, ""),
    )),
    ("Öğrenciler", (
        ("Üyeler", "bi-people", "students", None, ""),
        ("İzleme kayıtları", "bi-play-circle", "watch_log", None, ""),
    )),
    ("Katalog", (
        ("Paketler", "bi-stack", "catalog_list", "bundles", ""),
        ("İndirim kodları", "bi-ticket-perforated", "catalog_list", "discounts", ""),
        ("Özel indirim kodları", "bi-person-badge", "personal_discounts", None, ""),
        ("Kategoriler", "bi-diagram-3", "catalog_list", "categories", ""),
        ("Teknolojiler", "bi-cpu", "catalog_list", "technologies", ""),
        ("Eğitmenler", "bi-person-video3", "catalog_list", "instructors", ""),
    )),
    ("E-posta", (
        ("Gönderim günlüğü", "bi-journal-text", "email_log", None, ""),
        ("Şablonlar", "bi-envelope", "emails", None, ""),
        ("Bültenler", "bi-megaphone", "newsletters", None, ""),
        ("Aboneler", "bi-people", "subscribers", None, ""),
    )),
)


@register.simple_tag(takes_context=True)
def studio_mobile_nav(context, **badges):
    """Mobil menünün grupları: her bağlantıda label, icon, url, badge ve active. Geçerli adresle en uzun başlangıcı eşleşen
    bağlantı etkin sayılır (ör. /studio/emails/log/ "Gönderim günlüğü", alt sayfalar da kendi bölümünde)."""
    path = getattr(context.get("request"), "path", "")
    groups = []
    for title, links in MOBILE_NAV:
        items = []
        for label, icon, name, arg, badge in links:
            url = reverse(f"studio:{name}", args=[arg] if arg else None)
            items.append(dict(label=label, icon=icon, url=url, badge=badges.get(badge, 0) if badge else 0, active=False))
        groups.append(dict(title=title, items=items))
    matches = [item for group in groups for item in group["items"] if path.startswith(item["url"])]
    if matches:
        current = max(matches, key=lambda item: len(item["url"]))
        current["active"] = True
    return groups
