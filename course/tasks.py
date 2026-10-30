"""Video platformu işleri (Celery; Bunny Stream / Vimeo). Görevler kimlikle çağrılır ve beklenen durumda değilse sessizce
çıkar; iki kez çalışması zarar vermez. Her iş, videonun kaydında yazan platformla yapılır (bkz. `course.video_service`)."""

import logging

from celery import shared_task

from core.models import SiteSettings, VideoPlatform
from course import video_service
from course.models import Course, Lesson, LessonSubtitle, SubtitleStatus, UploadCanceled, VideoUpload, VideoUploadStatus
from course.video_service import VideoServiceError

logger = logging.getLogger(__name__)

PROCESSING_CHECK_SECONDS = 15
# Platform birkaç dakikada işler; uzun videolar için yaklaşık 2 saat beklenir.
PROCESSING_MAX_CHECKS = 480


def _delete_quietly(service, video_id):
    try:
        service.delete_video(video_id)
    except VideoServiceError as error:
        logger.warning("%s videosu silinemedi (%s): %s", service.LABEL, video_id, error)


@shared_task
def upload_video(upload_id):
    upload = VideoUpload.objects.select_related("lesson__section__course", "course").filter(pk=upload_id).first()
    # İptal edilmiş ya da başka bir işçinin aldığı iş atlanır.
    if upload is None or not upload.mark_uploading():
        return
    service = upload.video_service
    name = upload.video_name
    video = None
    try:
        # Video kursun klasöründe açılır; platformun panelinde kurs kurs görünür.
        folder = upload.target_course.ensure_video_folder(upload.platform)
        video = service.create_video(name, folder, upload.size)
        upload.mark_created(video.id, name)
        service.upload_file(video, upload.file.path, name, on_progress=upload.set_progress)
        service.finish_upload(video, folder)
    except UploadCanceled:
        if video:
            _delete_quietly(service, video.id)
        return
    except (VideoServiceError, OSError, ValueError) as error:
        # Platformda yarım kalan kayıt silinir; yeniden başlatınca yenisi açılır.
        if video:
            _delete_quietly(service, video.id)
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
    service = upload.video_service
    try:
        status = service.video_status(upload.video_id)
    except VideoServiceError as error:
        # Geçici ağ hatası işlemeyi bozmaz; bir sonraki kontrolde yeniden sorulur.
        logger.warning("%s durumu okunamadı (%s): %s", service.LABEL, upload.video_id, error)
        status = None
    if status:
        upload.set_service_state(status)
    if status and status.is_ready:
        upload.mark_ready(status)
        return
    if status and status.is_failed:
        if upload.mark_failed(f"Video işlenemedi ({service.LABEL}); dosyayı kontrol edip yeniden başlat."):
            _delete_quietly(service, upload.video_id)
        return
    if self.request.retries >= self.max_retries:
        upload.mark_failed(f"İşleme 2 saatte tamamlanmadı ({service.LABEL}).")
        return
    raise self.retry()


@shared_task
def sync_video_title(lesson_id):
    lesson = Lesson.objects.filter(pk=lesson_id).first()
    # Sıradayken ayar kapatılmışsa başlık platformda değişmez.
    if lesson is None or not lesson.needs_video_title_sync or not SiteSettings.title_sync_enabled():
        return
    title = lesson.title
    try:
        lesson.video_service.rename_video(lesson.video_id, title)
    except VideoServiceError as error:
        logger.warning("Video başlığı güncellenemedi (%s): %s", lesson.video_id, error)
        return
    Lesson.objects.filter(pk=lesson.pk).update(video_title=title)


@shared_task
def sync_preview_title(course_id):
    course = Course.objects.filter(pk=course_id).first()
    if course is None or not course.needs_preview_title_sync or not SiteSettings.title_sync_enabled():
        return
    title = course.title
    try:
        video_service.get(course.preview_video_platform).rename_video(course.preview_video_id, title)
    except VideoServiceError as error:
        logger.warning("Tanıtım videosunun başlığı güncellenemedi (%s): %s", course.preview_video_id, error)
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
        # Platformda aynı dilin altyazısı yenisiyle değişir.
        language = lesson.video_service.upload_caption(
            lesson.video_id, subtitle.language, subtitle.get_language_display(), subtitle.file.path
        )
    except (VideoServiceError, OSError) as error:
        subtitle.mark_failed(str(error))
        return
    subtitle.mark_ready(language)


@shared_task
def delete_remote_video(video_id, platform=VideoPlatform.BUNNY):
    """Silinen dersin, iptal edilen yüklemenin ya da yerine yenisi konan videonun platformdaki kopyası."""
    _delete_quietly(video_service.get(platform), video_id)


@shared_task
def delete_remote_caption(video_id, language, platform=VideoPlatform.BUNNY):
    try:
        video_service.get(platform).delete_caption(video_id, language)
    except VideoServiceError as error:
        logger.warning("Altyazı silinemedi (%s, %s): %s", video_id, language, error)
