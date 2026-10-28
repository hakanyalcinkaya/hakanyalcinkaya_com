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


@register.filter
def bunny_play_url(video_id):
    """Videonun Bunny'deki oynatma sayfası (stüdyoda "önizle" bağlantısı)."""
    from course import bunny

    return bunny.dashboard_url(video_id) if video_id else ""
