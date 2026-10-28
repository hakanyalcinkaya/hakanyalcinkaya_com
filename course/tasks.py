"""Bunny Stream işleri (Celery). Görevler kimlikle çağrılır ve beklenen durumda değilse sessizce çıkar; iki kez çalışması zarar vermez."""

import logging

from celery import shared_task

from course import bunny
from course.models import Course, Lesson, LessonSubtitle, SubtitleStatus, UploadCanceled, VideoUpload, VideoUploadStatus

logger = logging.getLogger(__name__)

PROCESSING_CHECK_SECONDS = 15
# Bunny birkaç dakikada işler; uzun videolar için yaklaşık 2 saat beklenir.
PROCESSING_MAX_CHECKS = 480


def _delete_quietly(video_id):
    try:
        bunny.delete_video(video_id)
    except bunny.VideoServiceError as error:
        logger.warning("Bunny videosu silinemedi (%s): %s", video_id, error)


@shared_task
def upload_video(upload_id):
    upload = VideoUpload.objects.select_related("lesson__section__course", "course").filter(pk=upload_id).first()
    # İptal edilmiş ya da başka bir işçinin aldığı iş atlanır.
    if upload is None or not upload.mark_uploading():
        return
    name = upload.video_name
    video_id = None
    try:
        # Video kursun koleksiyonunda açılır; Bunny panelinde kurs kurs görünür.
        video_id = bunny.create_video(name, upload.target_course.ensure_video_collection())
        upload.mark_created(video_id, name)
        bunny.upload_file(video_id, upload.file.path, name, on_progress=upload.set_progress)
    except UploadCanceled:
        if video_id:
            _delete_quietly(video_id)
        return
    except (bunny.VideoServiceError, OSError, ValueError) as error:
        # Bunny'de yarım kalan kayıt silinir; yeniden başlatınca yenisi açılır.
        if video_id:
            _delete_quietly(video_id)
        upload.mark_failed(str(error))
        return
    if upload.mark_sent():
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
        status = bunny.video_status(upload.video_id)
    except bunny.VideoServiceError as error:
        # Geçici ağ hatası işlemeyi bozmaz; bir sonraki kontrolde yeniden sorulur.
        logger.warning("Bunny durumu okunamadı (%s): %s", upload.video_id, error)
        status = None
    if status:
        upload.set_service_state(status)
    if status and status.is_ready:
        upload.mark_ready(status)
        return
    if status and status.is_failed:
        if upload.mark_failed("Bunny videoyu işleyemedi; dosyayı kontrol edip yeniden başlat."):
            _delete_quietly(upload.video_id)
        return
    if self.request.retries >= self.max_retries:
        upload.mark_failed("Bunny'deki işleme 2 saatte tamamlanmadı.")
        return
    raise self.retry()


@shared_task
def sync_video_title(lesson_id):
    lesson = Lesson.objects.filter(pk=lesson_id).first()
    if lesson is None or not lesson.needs_video_title_sync:
        return
    title = lesson.title
    try:
        bunny.rename_video(lesson.video_id, title)
    except bunny.VideoServiceError as error:
        logger.warning("Bunny başlığı güncellenemedi (%s): %s", lesson.video_id, error)
        return
    Lesson.objects.filter(pk=lesson.pk).update(video_title=title)


@shared_task
def sync_preview_title(course_id):
    course = Course.objects.filter(pk=course_id).first()
    if course is None or not course.needs_preview_title_sync:
        return
    title = course.title
    try:
        bunny.rename_video(course.preview_video_id, title)
    except bunny.VideoServiceError as error:
        logger.warning("Tanıtım videosunun Bunny başlığı güncellenemedi (%s): %s", course.preview_video_id, error)
        return
    Course.objects.filter(pk=course.pk).update(preview_video_title=title)


@shared_task
def upload_subtitle(subtitle_id):
    subtitle = (
        LessonSubtitle.objects.select_related("lesson").filter(pk=subtitle_id, status=SubtitleStatus.QUEUED).first()
    )
    if subtitle is None:
        return
    lesson = subtitle.lesson
    if not lesson.video_id or lesson.has_busy_upload:
        subtitle.mark_waiting()
        return
    try:
        # Bunny'de aynı dilin altyazısı yenisiyle değişir.
        language = bunny.upload_caption(
            lesson.video_id, subtitle.language, subtitle.get_language_display(), subtitle.file.path
        )
    except (bunny.VideoServiceError, OSError) as error:
        subtitle.mark_failed(str(error))
        return
    subtitle.mark_ready(language)


@shared_task
def delete_remote_video(video_id):
    """Silinen dersin ya da iptal edilen yüklemenin Bunny'deki videosu."""
    _delete_quietly(video_id)


@shared_task
def delete_remote_caption(video_id, language):
    try:
        bunny.delete_caption(video_id, language)
    except bunny.VideoServiceError as error:
        logger.warning("Bunny altyazısı silinemedi (%s, %s): %s", video_id, language, error)
