import json
from functools import wraps

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Prefetch, Q
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_POST
from django_htmx.http import reswap, trigger_client_event

from config.celery import worker_online
from course import vimeo
from course.models import (
    BUSY_UPLOAD_STATUSES,
    FINISHED_UPLOAD_STATUSES,
    Course,
    Lesson,
    LessonSubtitle,
    Section,
    VideoUpload,
)
from studio.forms import (
    LessonTitleForm,
    NewVideoLessonForm,
    SectionCreateForm,
    SectionTitleForm,
    SubtitleForm,
    VideoUploadForm,
)


def staff_required(view):
    """Panel yalnız personel (is_staff) ve süper kullanıcılara açık; diğer üyeler 403 alır."""

    @wraps(view)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not (request.user.is_staff or request.user.is_superuser):
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return wrapper


def _lesson(lesson_id):
    lessons = Lesson.objects.select_related("section__course").prefetch_related("video_uploads", "subtitles")
    return get_object_or_404(lessons, pk=lesson_id)


def _auto_id(lesson):
    # Sayfada birden çok dersin formu açık olabilir; alan kimlikleri derse göre ayrışır.
    return f"lesson-{lesson.pk}-%s"


def _toast(response, level, text):
    return trigger_client_event(response, "hy:toast", {"level": level, "text": text})


def _worker_online():
    # Geliştirmede işçi açık değilse yüklemeler "Sırada" bekler; panel bunu uyarı olarak gösterir.
    return worker_online()


@staff_required
def course_list(request):
    courses = Course.objects.with_video_stats().order_by("sort_order", "title")
    return render(request, "studio/course_list.html", dict(courses=courses))


def _course(course_id):
    return get_object_or_404(Course.objects.prefetch_related("preview_uploads"), pk=course_id)


def _with_lessons(sections):
    lessons = Lesson.objects.prefetch_related("video_uploads", "subtitles")
    return sections.prefetch_related(Prefetch("lessons", queryset=lessons))


def _section(section_id):
    return get_object_or_404(_with_lessons(Section.objects.select_related("course")), pk=section_id)


def _section_no(section):
    return section.course.sections.filter(sort_order__lt=section.sort_order).count() + 1


def _first_error(form):
    return next(error for errors in form.errors.values() for error in errors)


@staff_required
def course_detail(request, course_id):
    """İçerik düzenleyici: kategoriler (bölümler) ve videolar (dersler) sürükle-bırak ile düzenlenir."""
    course = _course(course_id)
    context = dict(
        course=course,
        sections=_with_lessons(course.sections.all()),
        section_form=SectionCreateForm(),
        title_sync_total=course.lessons_needing_vimeo_title_sync().count(),
        vimeo_configured=bool(settings.VIMEO_ACCESS_TOKEN),
        worker_online=_worker_online(),
    )
    return render(request, "studio/course_detail.html", context)


@staff_required
def section_detail(request, section_id):
    """Kategorinin video yükleme sayfası."""
    section = _section(section_id)
    context = dict(
        section=section,
        course=section.course,
        section_no=_section_no(section),
        vimeo_configured=bool(settings.VIMEO_ACCESS_TOKEN),
        worker_online=_worker_online(),
    )
    return render(request, "studio/section_detail.html", context)


@staff_required
@require_GET
def section_block(request, section_id):
    section = _section(section_id)
    context = dict(section=section, course=section.course, section_no=_section_no(section))
    return render(request, "studio/partials/_section.html", context)


def _video_lesson_response(request, lesson):
    """Yanıt yeni ders satırıdır. Bölüm sayfada henüz yoksa (ilk "Genel") istemci bölüm bloğunu ayrıca ister."""
    lesson = _lesson(lesson.pk)
    response = render(request, "studio/partials/_lesson.html", dict(lesson=lesson))
    response["X-Section-Id"] = str(lesson.section_id)
    response["X-Section-Block-Url"] = reverse("studio:section_block", args=[lesson.section_id])
    return response


@staff_required
@require_POST
def course_videos(request, course_id):
    """Kursa doğrudan bırakılan video "Genel" kategorisine eklenir."""
    course = get_object_or_404(Course, pk=course_id)
    form = NewVideoLessonForm(request.POST, request.FILES)
    if not form.is_valid():
        return HttpResponseBadRequest(_first_error(form))
    return _video_lesson_response(request, form.save(course.general_section(), request.user))


@staff_required
@require_POST
def section_videos(request, section_id):
    section = get_object_or_404(Section, pk=section_id)
    form = NewVideoLessonForm(request.POST, request.FILES)
    if not form.is_valid():
        return HttpResponseBadRequest(_first_error(form))
    return _video_lesson_response(request, form.save(section, request.user))


@staff_required
@require_POST
def course_structure(request, course_id):
    course = get_object_or_404(Course, pk=course_id)
    try:
        payload = json.loads(request.body)
        course.apply_structure(payload["sections"], reorder_sections=bool(payload.get("reorder_sections", True)))
    except (ValueError, KeyError, TypeError, AttributeError) as error:
        return HttpResponseBadRequest(str(error))
    return HttpResponse(status=204)


@staff_required
@require_POST
def section_create(request, course_id):
    course = get_object_or_404(Course, pk=course_id)
    form = SectionCreateForm(request.POST)
    if not form.is_valid():
        return render(request, "studio/partials/_section_create_form.html", dict(course=course, section_form=form))
    section = _section(form.save(course).pk)
    context = dict(
        course=course, section=section, section_no=_section_no(section), section_form=SectionCreateForm()
    )
    response = render(request, "studio/partials/_section_created.html", context)
    return _toast(response, "success", _("Kategori eklendi."))


@staff_required
def section_title(request, section_id):
    section = get_object_or_404(Section.objects.select_related("course"), pk=section_id)
    if request.method == "POST":
        form = SectionTitleForm(request.POST, instance=section, auto_id=f"section-{section.pk}-%s")
        if form.is_valid():
            form.save()
            return render(request, "studio/partials/_section_title.html", dict(section=section))
        return render(request, "studio/partials/_section_title_form.html", dict(section=section, form=form))
    if request.GET.get("edit"):
        form = SectionTitleForm(instance=section, auto_id=f"section-{section.pk}-%s")
        return render(request, "studio/partials/_section_title_form.html", dict(section=section, form=form))
    return render(request, "studio/partials/_section_title.html", dict(section=section))


@staff_required
@require_POST
def section_status(request, section_id):
    section = get_object_or_404(Section, pk=section_id)
    section.toggle_published()
    return render(request, "studio/partials/_section_status.html", dict(section=section))


@staff_required
@require_POST
def section_delete(request, section_id):
    section = get_object_or_404(Section, pk=section_id)
    if not section.can_delete:
        response = reswap(HttpResponse(), "none")
        return _toast(response, "warning", _("Kategoride video var; önce videoları taşı ya da sil."))
    section.delete()
    return _toast(HttpResponse(), "success", _("Kategori silindi."))


@staff_required
@require_POST
def lesson_status(request, lesson_id):
    lesson = get_object_or_404(Lesson, pk=lesson_id)
    lesson.toggle_published()
    return render(request, "studio/partials/_lesson_status.html", dict(lesson=lesson))


@staff_required
@require_POST
def lesson_preview(request, lesson_id):
    lesson = get_object_or_404(Lesson, pk=lesson_id)
    lesson.toggle_preview()
    return render(request, "studio/partials/_lesson_status.html", dict(lesson=lesson))


@staff_required
def lesson_delete(request, lesson_id):
    """GET onay panelini açar (Vimeo'dan da silinsin mi sorulur); POST dersi siler ve satırı kaldırır."""
    lesson = get_object_or_404(Lesson, pk=lesson_id)
    if request.method != "POST":
        return render(request, "studio/partials/_lesson_delete.html", dict(lesson=lesson))
    delete_from_vimeo = request.POST.get("vimeo") == "1"
    lesson.remove(delete_from_vimeo=delete_from_vimeo)
    text = _("Ders ve Vimeo videosu silindi.") if delete_from_vimeo else _("Ders silindi.")
    return _toast(HttpResponse(), "success", text)


# Taşıma başlatılınca klasör sayısı 5 saniyede bir, en fazla 2 dakika yenilenir.
FOLDER_POLL_LIMIT = 24


def _folder_context(course, tries=0):
    expected = len(course.vimeo_video_ids())
    folder_total, error = None, ""
    if course.vimeo_folder_uri:
        try:
            folder_total = vimeo.folder_video_total(course.vimeo_folder_uri)
        except vimeo.VimeoError as exc:
            error = str(exc)
    complete = folder_total is not None and folder_total >= expected
    return dict(
        course=course,
        expected=expected,
        folder_total=folder_total,
        error=error,
        moving=0 < tries <= FOLDER_POLL_LIMIT and not complete and not error,
        next_try=tries + 1,
        can_move=bool(expected) and not complete and not error,
    )


@staff_required
def course_folder(request, course_id):
    """Kursun Vimeo klasörü: içindeki video sayısı Vimeo'dan okunur; POST eksik videoları klasöre taşır."""
    course = get_object_or_404(Course, pk=course_id)
    if request.method != "POST":
        tries = int(request.GET.get("tries", 0)) if request.GET.get("tries", "").isdigit() else 0
        return render(request, "studio/partials/_course_folder.html", _folder_context(course, tries))
    try:
        scopes = vimeo.token_scopes()
    except vimeo.VimeoError as error:
        response = render(request, "studio/partials/_course_folder.html", _folder_context(course))
        return _toast(response, "error", _("Vimeo'ya ulaşılamadı: %(error)s") % {"error": error})
    if "interact" not in scopes:
        response = render(request, "studio/partials/_course_folder.html", _folder_context(course))
        text = _("Vimeo anahtarında 'interact' yetkisi yok; videolar klasöre taşınamaz. Bu yetkiyle yeni anahtar oluştur.")
        return _toast(response, "error", text)
    course.queue_move_to_vimeo_folder()
    response = render(request, "studio/partials/_course_folder.html", _folder_context(course, tries=1))
    return _toast(response, "success", _("Videolar Vimeo klasörüne taşınıyor."))


@staff_required
@require_POST
def course_sync_titles(request, course_id):
    course = get_object_or_404(Course, pk=course_id)
    queued = sum(lesson.queue_vimeo_title_sync() for lesson in course.lessons_needing_vimeo_title_sync())
    messages.success(request, _("%(count)s dersin başlığı Vimeo'da güncellenecek.") % {"count": queued})
    return redirect("studio:course_detail", course_id=course.pk)


@staff_required
def lesson_title(request, lesson_id):
    lesson = _lesson(lesson_id)
    if request.method == "POST":
        form = LessonTitleForm(request.POST, instance=lesson, auto_id=_auto_id(lesson))
        if form.is_valid():
            form.save()
            lesson.queue_vimeo_title_sync()
            return render(request, "studio/partials/_lesson_title.html", dict(lesson=lesson))
        return render(request, "studio/partials/_lesson_title_form.html", dict(lesson=lesson, form=form))
    if request.GET.get("edit"):
        form = LessonTitleForm(instance=lesson, auto_id=_auto_id(lesson))
        return render(request, "studio/partials/_lesson_title_form.html", dict(lesson=lesson, form=form))
    return render(request, "studio/partials/_lesson_title.html", dict(lesson=lesson))


@staff_required
def lesson_video(request, lesson_id):
    lesson = _lesson(lesson_id)
    is_post = request.method == "POST"
    form = VideoUploadForm(
        request.POST if is_post else None, request.FILES if is_post else None, lesson=lesson, auto_id=_auto_id(lesson)
    )
    if is_post and form.is_valid():
        form.save(request.user)
        response = render(request, "studio/partials/_video_queued.html", dict(lesson=_lesson(lesson_id)))
        return _toast(response, "success", _("Video sunucuya ulaştı; Vimeo'ya gönderiliyor."))
    return render(request, "studio/partials/_video_form.html", dict(lesson=lesson, form=form))


@staff_required
@require_GET
def lesson_video_status(request, lesson_id):
    return render(request, "studio/partials/_lesson_video.html", dict(lesson=_lesson(lesson_id)))


@staff_required
def course_preview(request, course_id):
    course = _course(course_id)
    is_post = request.method == "POST"
    form = VideoUploadForm(
        request.POST if is_post else None, request.FILES if is_post else None, course=course, auto_id="preview-%s"
    )
    if is_post and form.is_valid():
        form.save(request.user)
        response = render(request, "studio/partials/_preview_queued.html", dict(course=_course(course_id)))
        return _toast(response, "success", _("Tanıtım videosu sunucuya ulaştı; Vimeo'ya gönderiliyor."))
    return render(request, "studio/partials/_video_form.html", dict(form=form, course=course))


@staff_required
@require_GET
def course_preview_status(request, course_id):
    return render(request, "studio/partials/_preview_video.html", dict(course=_course(course_id)))


QUEUE_FILTERS = {"active": BUSY_UPLOAD_STATUSES, "finished": FINISHED_UPLOAD_STATUSES, "all": None}
QUEUE_LIMIT = 200


def _queue_filter(request):
    value = request.POST.get("filter") or request.GET.get("filter")
    return value if value in QUEUE_FILTERS else "all"


def _queue_context(queue_filter):
    uploads = VideoUpload.objects.for_queue()
    if QUEUE_FILTERS[queue_filter]:
        uploads = uploads.filter(status__in=QUEUE_FILTERS[queue_filter])
    uploads = list(uploads[:QUEUE_LIMIT])
    totals = VideoUpload.objects.aggregate(
        active=Count("pk", filter=Q(status__in=BUSY_UPLOAD_STATUSES)),
        finished=Count("pk", filter=Q(status__in=FINISHED_UPLOAD_STATUSES)),
        all=Count("pk"),
    )
    return dict(
        uploads=uploads, queue_filter=queue_filter, totals=totals, has_busy=any(upload.is_busy for upload in uploads)
    )


@staff_required
@require_GET
def queue(request):
    context = _queue_context(_queue_filter(request))
    if request.htmx:
        return render(request, "studio/partials/_queue.html", context)
    context["worker_online"] = _worker_online()
    return render(request, "studio/queue.html", context)


def _upload_response(request, upload, level, text):
    """Eylem kuyruk sayfasından geldiyse liste, ders ya da kurs sayfasından geldiyse ilgili video hücresi döner."""
    if request.POST.get("from") == "queue":
        response = render(request, "studio/partials/_queue.html", _queue_context(_queue_filter(request)))
    elif upload.is_preview:
        response = render(request, "studio/partials/_preview_video.html", dict(course=_course(upload.course_id)))
    else:
        response = render(request, "studio/partials/_lesson_video.html", dict(lesson=_lesson(upload.lesson_id)))
    return _toast(response, level, text)


def _upload(upload_id):
    return get_object_or_404(VideoUpload.objects.select_related("lesson", "course"), pk=upload_id)


@staff_required
@require_POST
def upload_retry(request, upload_id):
    upload = _upload(upload_id)
    if upload.retry():
        return _upload_response(request, upload, "success", _("Yükleme yeniden sıraya alındı."))
    return _upload_response(request, upload, "warning", _("Bu iş yeniden başlatılamıyor; liste güncellendi."))


@staff_required
@require_POST
def upload_cancel(request, upload_id):
    upload = _upload(upload_id)
    if upload.cancel():
        text = _("Yükleme iptal edildi; dosya yeniden başlatmak için saklanıyor.")
        return _upload_response(request, upload, "success", text)
    return _upload_response(request, upload, "warning", _("Bu iş artık iptal edilemiyor; liste güncellendi."))


@staff_required
@require_POST
def upload_discard(request, upload_id):
    upload = _upload(upload_id)
    removed = upload.discard()
    response = render(request, "studio/partials/_queue.html", _queue_context(_queue_filter(request)))
    if removed:
        return _toast(response, "success", _("İş kuyruktan kaldırıldı."))
    return _toast(response, "warning", _("Süren iş kaldırılamaz; önce iptal et."))


@staff_required
@require_POST
def queue_clear(request):
    cleared = sum(upload.discard() for upload in VideoUpload.objects.finished())
    response = render(request, "studio/partials/_queue.html", _queue_context(_queue_filter(request)))
    return _toast(response, "success", _("%(count)s biten iş temizlendi.") % {"count": cleared})


@staff_required
def lesson_subtitles(request, lesson_id):
    lesson = _lesson(lesson_id)
    is_post = request.method == "POST"
    form = SubtitleForm(
        request.POST if is_post else None, request.FILES if is_post else None, lesson=lesson, auto_id=_auto_id(lesson)
    )
    if is_post and form.is_valid():
        subtitle = form.save()
        response = render(request, "studio/partials/_subtitle_queued.html", dict(lesson=_lesson(lesson_id)))
        return _toast(response, "success", _("%(language)s altyazı kaydedildi.") % {"language": subtitle.get_language_display()})
    return render(request, "studio/partials/_subtitle_form.html", dict(lesson=lesson, form=form))


@staff_required
@require_GET
def lesson_subtitles_status(request, lesson_id):
    return render(request, "studio/partials/_lesson_subtitles.html", dict(lesson=_lesson(lesson_id)))


@staff_required
@require_POST
def subtitle_retry(request, subtitle_id):
    subtitle = get_object_or_404(LessonSubtitle.objects.select_related("lesson"), pk=subtitle_id)
    if subtitle.is_failed:
        subtitle.schedule()
    return render(request, "studio/partials/_lesson_subtitles.html", dict(lesson=_lesson(subtitle.lesson_id)))


@staff_required
@require_POST
def subtitle_delete(request, subtitle_id):
    subtitle = get_object_or_404(LessonSubtitle, pk=subtitle_id)
    lesson_id = subtitle.lesson_id
    subtitle.remove()
    return render(request, "studio/partials/_lesson_subtitles.html", dict(lesson=_lesson(lesson_id)))
