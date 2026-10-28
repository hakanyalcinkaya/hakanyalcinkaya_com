"""Vimeo işleri (Celery). Görevler kimlikle çağrılır ve beklenen durumda değilse sessizce çıkar; iki kez çalışması zarar vermez."""

import logging

from celery import shared_task

from course import vimeo
from course.models import Course, Lesson, LessonSubtitle, SubtitleStatus, UploadCanceled, VideoUpload, VideoUploadStatus

logger = logging.getLogger(__name__)

PROCESSING_CHECK_SECONDS = 20
# Vimeo'nun işlemesi uzun videolarda dakikalar sürer; yaklaşık 2 saat beklenir.
PROCESSING_MAX_CHECKS = 360


def _delete_quietly(vimeo_id):
    try:
        vimeo.delete_video(vimeo_id)
    except vimeo.VimeoError as error:
        logger.warning("Yarım kalan Vimeo videosu silinemedi (%s): %s", vimeo_id, error)


@shared_task
def upload_video(upload_id):
    upload = VideoUpload.objects.select_related("lesson__section__course", "course").filter(pk=upload_id).first()
    # İptal edilmiş ya da başka bir işçinin aldığı iş atlanır.
    if upload is None or not upload.mark_uploading():
        return
    name = upload.vimeo_name
    video = None
    try:
        video = vimeo.create_video(name, upload.size)
        upload.mark_created(video.id, name)
        vimeo.upload_file(video.upload_link, upload.file.path, on_progress=upload.set_progress)
        vimeo.allow_domains(video.id)
    except UploadCanceled:
        if video:
            _delete_quietly(video.id)
        return
    except (vimeo.VimeoError, OSError, ValueError) as error:
        # Vimeo'da yarım kalan kayıt silinir; yeniden başlatınca yenisi açılır.
        if video:
            _delete_quietly(video.id)
        upload.mark_failed(str(error))
        return
    if not upload.mark_sent():
        return
    # Klasör düzeni yardımcıdır; başarısız olursa video yine kullanılabilir.
    try:
        vimeo.add_to_folder(upload.target_course.ensure_vimeo_folder(), video.id)
    except vimeo.VimeoError as error:
        logger.warning("Video Vimeo klasörüne eklenemedi (%s): %s", video.id, error)
    check_video_processing.apply_async((upload_id,), countdown=PROCESSING_CHECK_SECONDS)


@shared_task(bind=True, max_retries=PROCESSING_MAX_CHECKS, default_retry_delay=PROCESSING_CHECK_SECONDS)
def check_video_processing(self, upload_id):
    upload = (
        VideoUpload.objects.select_related("lesson", "course")
        .filter(pk=upload_id, status=VideoUploadStatus.PROCESSING)
        .first()
    )
    if upload is None:
        return
    try:
        status = vimeo.video_status(upload.vimeo_id)
    except vimeo.VimeoError as error:
        # Geçici ağ hatası işlemeyi bozmaz; bir sonraki kontrolde yeniden sorulur.
        logger.warning("Vimeo durumu okunamadı (%s): %s", upload.vimeo_id, error)
        status = None
    if status:
        upload.set_vimeo_state(status.state)
    if status and status.is_ready:
        upload.mark_ready(status)
        return
    if status and status.is_failed:
        if upload.mark_failed("Vimeo videoyu işleyemedi; dosyayı kontrol edip yeniden başlat."):
            _delete_quietly(upload.vimeo_id)
        return
    if self.request.retries >= self.max_retries:
        upload.mark_failed("Vimeo'daki işleme 2 saatte tamamlanmadı.")
        return
    raise self.retry()


@shared_task
def move_course_videos_to_folder(course_id):
    """Kursun videolarını Vimeo klasörüne ekler (zaten oradaysa değişmez). Yükleme sırasında atlanan videoları toplar."""
    course = Course.objects.filter(pk=course_id).first()
    if course is None:
        return
    try:
        folder_uri = course.ensure_vimeo_folder()
    except vimeo.VimeoError as error:
        logger.warning("Vimeo klasörü açılamadı (%s): %s", course.title, error)
        return
    for vimeo_id in course.vimeo_video_ids():
        try:
            vimeo.add_to_folder(folder_uri, vimeo_id)
        except vimeo.VimeoError as error:
            logger.warning("Video Vimeo klasörüne eklenemedi (%s): %s", vimeo_id, error)
            # Yetki eksikse diğerleri de eklenemez.
            if "403" in str(error):
                return


@shared_task
def sync_vimeo_title(lesson_id):
    lesson = Lesson.objects.filter(pk=lesson_id).first()
    if lesson is None or not lesson.needs_vimeo_title_sync:
        return
    title = lesson.title
    try:
        vimeo.rename_video(lesson.vimeo_id, title)
    except vimeo.VimeoError as error:
        logger.warning("Vimeo başlığı güncellenemedi (%s): %s", lesson.vimeo_id, error)
        return
    Lesson.objects.filter(pk=lesson.pk).update(vimeo_title=title)


@shared_task
def sync_preview_title(course_id):
    course = Course.objects.filter(pk=course_id).first()
    if course is None or not course.needs_preview_title_sync:
        return
    title = course.title
    try:
        vimeo.rename_video(course.preview_vimeo_id, title)
    except vimeo.VimeoError as error:
        logger.warning("Tanıtım videosunun Vimeo başlığı güncellenemedi (%s): %s", course.preview_vimeo_id, error)
        return
    Course.objects.filter(pk=course.pk).update(preview_vimeo_title=title)


@shared_task
def upload_subtitle(subtitle_id):
    subtitle = (
        LessonSubtitle.objects.select_related("lesson").filter(pk=subtitle_id, status=SubtitleStatus.QUEUED).first()
    )
    if subtitle is None:
        return
    lesson = subtitle.lesson
    if not lesson.vimeo_id or lesson.has_busy_upload:
        subtitle.mark_waiting()
        return
    try:
        # Aynı dilin önceki dosyası bu videodaysa önce kaldırılır.
        if subtitle.vimeo_uri:
            vimeo.delete_text_track(subtitle.vimeo_uri)
        uri = vimeo.upload_text_track(
            lesson.vimeo_id, subtitle.language, subtitle.get_language_display(), subtitle.file.path
        )
    except (vimeo.VimeoError, OSError) as error:
        subtitle.mark_failed(str(error))
        return
    subtitle.mark_ready(uri)


@shared_task
def delete_vimeo_video(vimeo_id):
    """İptal edilen yüklemenin Vimeo'daki videosu (derse henüz bağlanmamış)."""
    _delete_quietly(vimeo_id)


@shared_task
def delete_text_track(uri):
    try:
        vimeo.delete_text_track(uri)
    except vimeo.VimeoError as error:
        logger.warning("Vimeo altyazısı silinemedi (%s): %s", uri, error)
