from django import template

from course.models import VideoUpload

register = template.Library()


@register.simple_tag
def busy_upload_total():
    """Stüdyo menüsündeki kuyruk rozeti: süren video yüklemeleri."""
    return VideoUpload.objects.busy().count()


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
