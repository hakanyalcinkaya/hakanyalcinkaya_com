from django import template

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
    ("courses", ("course_", "section_", "lesson_", "extra_content", "subtitle_")),
    ("catalog", ("catalog_",)),
    ("sales", ("order", "cart")),
    ("students", ("student", "enrollment")),
    ("reviews", ("review",)),
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
