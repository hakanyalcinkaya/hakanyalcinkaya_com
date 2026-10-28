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
