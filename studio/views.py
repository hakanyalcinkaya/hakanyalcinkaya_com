import json
import smtplib
from functools import partial, wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, IntegerField, OuterRef, Prefetch, Q, Subquery
from django.db.models.functions import Coalesce
from django.conf import settings
from django.http import Http404, HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from django.views.decorators.http import require_GET, require_POST
from django_htmx.http import HttpResponseClientRedirect, reswap, trigger_client_event

from config.celery import worker_online
from core.models import SiteSettings, Status, VideoPlatform
from course import video_service
from course.models import (
    BUSY_UPLOAD_STATUSES,
    FINISHED_UPLOAD_STATUSES,
    Course,
    Lesson,
    LessonSubtitle,
    Review,
    Section,
    VideoUpload,
)
from core.markup import render_markdown
from learning.models import Enrollment
from studio.templatetags.studio_tags import ROWS_PARAM
from studio.forms import (
    ExtraContentBulkForm,
    ExtraContentForm,
    ExtraContentUploadForm,
    IssueForm,
    LessonBulkForm,
    LessonTitleForm,
    NewVideoLessonForm,
    ReviewImportForm,
    SectionCreateForm,
    SectionTitleForm,
    SiteSettingsForm,
    SubtitleForm,
    VideoUploadForm,
)


def superuser_required(view):
    """Stüdyodaki her işlem yalnız süper kullanıcıya açık; diğer üyeler (personel dahil) 403 alır."""

    @wraps(view)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not request.user.is_superuser:
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


def _platform_label():
    return video_service.current().LABEL


def _video_platform():
    """Yeni yüklemelerin gideceği platform; ayarları eksikse panel uyarır."""
    platform = video_service.current_name()
    service = video_service.get(platform)
    return dict(value=platform, label=service.LABEL, missing=video_service.missing_settings(service.REQUIRED_SETTINGS))


@superuser_required
def course_list(request):
    enrollments = Enrollment.objects.filter(course=OuterRef("pk")).order_by().values("course").annotate(n=Count("pk")).values("n")
    courses = (
        Course.objects.with_video_stats()
        .annotate(enrollment_total=Coalesce(Subquery(enrollments, output_field=IntegerField()), 0))
        .order_by("sort_order", "title")
    )
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


@superuser_required
def course_detail(request, course_id):
    """İçerik düzenleyici: kategoriler (bölümler) ve videolar (dersler) sürükle-bırak ile düzenlenir."""
    course = _course(course_id)
    context = dict(
        course=course,
        sections=_with_lessons(course.sections.all()),
        section_form=SectionCreateForm(),
        title_sync_total=course.lessons_needing_video_title_sync().count() if SiteSettings.title_sync_enabled() else 0,
        video_platform=_video_platform(),
        worker_online=_worker_online(),
    )
    return render(request, "studio/course_detail.html", context)


@superuser_required
def section_detail(request, section_id):
    """Kategorinin video yükleme sayfası."""
    section = _section(section_id)
    context = dict(
        section=section,
        course=section.course,
        section_no=_section_no(section),
        video_platform=_video_platform(),
        worker_online=_worker_online(),
    )
    return render(request, "studio/section_detail.html", context)


@superuser_required
@require_GET
def section_block(request, section_id):
    section = _section(section_id)
    # Yalnız kurs düzenleyicisinden istenir; satırlarda toplu seçim kutusu olur.
    context = dict(section=section, course=section.course, section_no=_section_no(section), bulk=True)
    return render(request, "studio/partials/_section.html", context)


def _video_lesson_response(request, lesson, bulk):
    """Yanıt yeni ders satırıdır. Bölüm sayfada henüz yoksa (ilk "Genel") istemci bölüm bloğunu ayrıca ister.

    `bulk`: satır kurs düzenleyicisine eklenecekse toplu seçim kutusu olur.
    """
    lesson = _lesson(lesson.pk)
    response = render(request, "studio/partials/_lesson.html", dict(lesson=lesson, bulk=bulk))
    response["X-Section-Id"] = str(lesson.section_id)
    response["X-Lesson-Id"] = str(lesson.pk)
    response["X-Section-Block-Url"] = reverse("studio:section_block", args=[lesson.section_id])
    return response


@superuser_required
@require_POST
def course_videos(request, course_id):
    """Kursa doğrudan bırakılan video eşleşen videosuz derse yüklenir; eşleşme yoksa "Genel" kategorisine eklenir."""
    course = get_object_or_404(Course, pk=course_id)
    form = NewVideoLessonForm(request.POST, request.FILES)
    if not form.is_valid():
        return HttpResponseBadRequest(_first_error(form))
    # Eşleşme "Genel" açılmadan aranır; yeni kategori bölüm sırasını kaydırmasın.
    matched = form.matching_lesson(course, form.cleaned_data["file"].name)
    section = matched.section if matched else course.general_section()
    return _video_lesson_response(request, form.save(section, request.user, lesson=matched), bulk=True)


@superuser_required
@require_POST
def section_videos(request, section_id):
    section = get_object_or_404(Section, pk=section_id)
    form = NewVideoLessonForm(request.POST, request.FILES)
    if not form.is_valid():
        return HttpResponseBadRequest(_first_error(form))
    return _video_lesson_response(request, form.save(section, request.user), bulk=request.GET.get("bulk") == "1")


@superuser_required
@require_POST
def course_structure(request, course_id):
    course = get_object_or_404(Course, pk=course_id)
    try:
        payload = json.loads(request.body)
        course.apply_structure(payload["sections"], reorder_sections=bool(payload.get("reorder_sections", True)))
    except (ValueError, KeyError, TypeError, AttributeError) as error:
        return HttpResponseBadRequest(str(error))
    return HttpResponse(status=204)


@superuser_required
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


@superuser_required
@require_POST
def section_content_lesson(request, section_id):
    """Bölümün sonuna içerik dersi ekler ve düzenleyicisini açar (form bağlantısı, okuma gibi videosuz dersler)."""
    section = get_object_or_404(Section, pk=section_id)
    lesson = section.add_content_lesson(_("Yeni içerik"))
    response = _video_lesson_response(request, lesson, bulk=request.GET.get("bulk") == "1")
    return _toast(response, "success", _("İçerik dersi eklendi; başlığını ve içeriğini düzenle."))


@superuser_required
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


@superuser_required
@require_POST
def section_status(request, section_id):
    section = get_object_or_404(Section, pk=section_id)
    section.toggle_published()
    return render(request, "studio/partials/_section_status.html", dict(section=section))


@superuser_required
@require_POST
def section_delete(request, section_id):
    section = get_object_or_404(Section, pk=section_id)
    if not section.can_delete:
        response = reswap(HttpResponse(), "none")
        return _toast(response, "warning", _("Kategoride video var; önce videoları taşı ya da sil."))
    section.delete()
    return _toast(HttpResponse(), "success", _("Kategori silindi."))


@superuser_required
@require_POST
def lesson_status(request, lesson_id):
    lesson = get_object_or_404(Lesson, pk=lesson_id)
    lesson.toggle_published()
    return render(request, "studio/partials/_lesson_status.html", dict(lesson=lesson))


@superuser_required
@require_POST
def lesson_kind(request, lesson_id):
    """Ders türü (video / metin / form); satır yeniden çizilir (videolu ve içerik dersinin düğmeleri farklı)."""
    lesson = _lesson(lesson_id)
    try:
        lesson.set_kind(request.POST.get("kind", ""))
    except ValueError:
        return HttpResponseBadRequest()
    response = render(request, "studio/partials/_lesson.html", dict(lesson=_lesson(lesson.pk), bulk=request.GET.get("bulk") == "1"))
    return _toast(response, "success", _("Ders türü: %(kind)s.") % {"kind": lesson.get_kind_display()})


@superuser_required
@require_POST
def lesson_preview(request, lesson_id):
    lesson = get_object_or_404(Lesson, pk=lesson_id)
    lesson.toggle_preview()
    return render(request, "studio/partials/_lesson_status.html", dict(lesson=lesson))


@superuser_required
@require_POST
def lesson_bulk(request, course_id):
    """Düzenleyicide seçilen videolara toplu işlem; kategori listesi yeniden çizilir, seçim temizlenir."""
    course = get_object_or_404(Course, pk=course_id)
    form = LessonBulkForm(request.POST, course=course)
    if not form.is_valid():
        return _toast(reswap(HttpResponse(), "none"), "warning", _first_error(form))
    count = form.save()
    response = render(
        request, "studio/partials/_course_sections.html", dict(course=course, sections=_with_lessons(course.sections.all()))
    )
    return _toast(response, "success", form.message(count))


@superuser_required
def lesson_delete(request, lesson_id):
    """GET onay panelini açar (platformdan da silinsin mi sorulur); POST dersi siler ve satırı kaldırır."""
    lesson = get_object_or_404(Lesson, pk=lesson_id)
    if request.method != "POST":
        return render(request, "studio/partials/_lesson_delete.html", dict(lesson=lesson))
    delete_remote = request.POST.get("remote") == "1"
    lesson.remove(delete_remote=delete_remote)
    text = (
        _("Ders silindi; videosu %(platform)s platformundan da silinecek.") % {"platform": lesson.video_service.LABEL}
        if delete_remote
        else _("Ders silindi.")
    )
    return _toast(HttpResponse(), "success", text)


@superuser_required
@require_POST
def course_sync_titles(request, course_id):
    course = get_object_or_404(Course, pk=course_id)
    if not SiteSettings.title_sync_enabled():
        messages.warning(request, _("Video başlığını platformda güncelleme ayarı kapalı; Ayarlar'dan açabilirsin."))
        return redirect("studio:course_detail", course_id=course.pk)
    queued = sum(lesson.queue_video_title_sync() for lesson in course.lessons_needing_video_title_sync())
    messages.success(request, _("%(count)s dersin başlığı video platformunda güncellenecek.") % {"count": queued})
    return redirect("studio:course_detail", course_id=course.pk)


@superuser_required
def lesson_title(request, lesson_id):
    lesson = _lesson(lesson_id)
    if request.method == "POST":
        form = LessonTitleForm(request.POST, instance=lesson, auto_id=_auto_id(lesson))
        if form.is_valid():
            form.save()
            lesson.queue_video_title_sync()
            return render(request, "studio/partials/_lesson_title.html", dict(lesson=lesson))
        return render(request, "studio/partials/_lesson_title_form.html", dict(lesson=lesson, form=form))
    if request.GET.get("edit"):
        form = LessonTitleForm(instance=lesson, auto_id=_auto_id(lesson))
        return render(request, "studio/partials/_lesson_title_form.html", dict(lesson=lesson, form=form))
    return render(request, "studio/partials/_lesson_title.html", dict(lesson=lesson))


@superuser_required
def lesson_video(request, lesson_id):
    lesson = _lesson(lesson_id)
    is_post = request.method == "POST"
    form = VideoUploadForm(
        request.POST if is_post else None, request.FILES if is_post else None, lesson=lesson, auto_id=_auto_id(lesson)
    )
    if is_post and form.is_valid():
        form.save(request.user)
        response = render(request, "studio/partials/_video_queued.html", dict(lesson=_lesson(lesson_id)))
        return _toast(response, "success", _("Video sunucuya ulaştı; %(platform)s platformuna gönderiliyor.") % {"platform": _platform_label()})
    return render(request, "studio/partials/_video_form.html", dict(lesson=lesson, form=form))


@superuser_required
@require_GET
def lesson_video_status(request, lesson_id):
    return render(request, "studio/partials/_lesson_video.html", dict(lesson=_lesson(lesson_id)))


@superuser_required
def course_preview(request, course_id):
    course = _course(course_id)
    is_post = request.method == "POST"
    form = VideoUploadForm(
        request.POST if is_post else None, request.FILES if is_post else None, course=course, auto_id="preview-%s"
    )
    if is_post and form.is_valid():
        form.save(request.user)
        response = render(request, "studio/partials/_preview_queued.html", dict(course=_course(course_id)))
        return _toast(response, "success", _("Tanıtım videosu sunucuya ulaştı; %(platform)s platformuna gönderiliyor.") % {"platform": _platform_label()})
    return render(request, "studio/partials/_video_form.html", dict(form=form, course=course))


@superuser_required
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


@superuser_required
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


@superuser_required
@require_POST
def upload_retry(request, upload_id):
    upload = _upload(upload_id)
    if upload.retry():
        return _upload_response(request, upload, "success", _("Yükleme yeniden sıraya alındı."))
    return _upload_response(request, upload, "warning", _("Bu iş yeniden başlatılamıyor; liste güncellendi."))


@superuser_required
@require_POST
def upload_cancel(request, upload_id):
    upload = _upload(upload_id)
    if upload.cancel():
        text = _("Yükleme iptal edildi; dosya yeniden başlatmak için saklanıyor.")
        return _upload_response(request, upload, "success", text)
    return _upload_response(request, upload, "warning", _("Bu iş artık iptal edilemiyor; liste güncellendi."))


@superuser_required
@require_POST
def upload_discard(request, upload_id):
    upload = _upload(upload_id)
    removed = upload.discard()
    response = render(request, "studio/partials/_queue.html", _queue_context(_queue_filter(request)))
    if removed:
        return _toast(response, "success", _("İş kuyruktan kaldırıldı."))
    return _toast(response, "warning", _("Süren iş kaldırılamaz; önce iptal et."))


@superuser_required
@require_POST
def queue_clear(request):
    cleared = sum(upload.discard() for upload in VideoUpload.objects.finished())
    response = render(request, "studio/partials/_queue.html", _queue_context(_queue_filter(request)))
    return _toast(response, "success", _("%(count)s biten iş temizlendi.") % {"count": cleared})


@superuser_required
def _extras_panel(request, lesson, subtitle_form=None, content_form=None):
    """Dersin "Ek içerik" paneli: solda altyazı (SRT/VTT), sağda Markdown/TXT/HTML içerik; ikisine de dosya bırakılır.

    Satırdaki altyazı ve ek içerik rozetleri de (OOB) yenilenir.
    """
    context = dict(
        lesson=lesson,
        subtitle_form=subtitle_form or SubtitleForm(lesson=lesson, auto_id=_auto_id(lesson)),
        content_form=content_form or ExtraContentUploadForm(lesson=lesson, auto_id=f"lesson-{lesson.pk}-content-%s"),
    )
    return render(request, "studio/partials/_lesson_extras_panel.html", context)


@superuser_required
def lesson_subtitles(request, lesson_id):
    """GET paneli açar; POST altyazıyı kaydeder ve paneli yeniler."""
    lesson = _lesson(lesson_id)
    if request.method != "POST":
        return _extras_panel(request, lesson)
    form = SubtitleForm(request.POST, request.FILES, lesson=lesson, auto_id=_auto_id(lesson))
    if not form.is_valid():
        return _extras_panel(request, lesson, subtitle_form=form)
    subtitle = form.save()
    response = _extras_panel(request, _lesson(lesson_id))
    return _toast(response, "success", _("%(language)s altyazı kaydedildi.") % {"language": subtitle.get_language_display()})


@superuser_required
@require_POST
def lesson_extra_content(request, lesson_id):
    """Ek içerik dosyası (Markdown/TXT/HTML) yükler; varsa eskisinin yerine geçer."""
    lesson = _lesson(lesson_id)
    form = ExtraContentUploadForm(request.POST, request.FILES, lesson=lesson, auto_id=f"lesson-{lesson.pk}-content-%s")
    if not form.is_valid():
        return _extras_panel(request, lesson, content_form=form)
    form.save()
    return _toast(_extras_panel(request, lesson), "success", _("Ek içerik kaydedildi."))


@superuser_required
def lesson_extra_content_edit(request, lesson_id):
    """Ek içerik düzenleyicisi (pencerede). Kaydedince pencere kapanır, satırdaki rozet yenilenir."""
    lesson = _lesson(lesson_id)
    form = ExtraContentForm(request.POST or None, instance=lesson, auto_id=f"lesson-{lesson.pk}-editor-%s")
    if request.method == "POST" and form.is_valid():
        form.save()
        response = render(request, "studio/partials/_lesson_extra_saved.html", dict(lesson=lesson))
        response = trigger_client_event(response, "hy:dialog-close", {})
        text = _("Ek içerik kaydedildi.") if lesson.has_extra_content else _("Ek içerik kaldırıldı.")
        return _toast(response, "success", text)
    return render(request, "studio/partials/_extra_content_editor.html", dict(lesson=lesson, form=form))


@superuser_required
@require_POST
def course_extra_contents(request, course_id):
    """Toplu ek içerik: tek dosya alır, dosya adından dersi bulup kaydeder. Tarayıcı dosyaları sırayla gönderir ve
    sonucu listeye yazar; eşleşen dersin satırındaki rozet de yenilenir."""
    course = get_object_or_404(Course, pk=course_id)
    form = ExtraContentBulkForm(request.POST, request.FILES, course=course)
    if not form.is_valid():
        return JsonResponse(dict(status="error", message=str(_first_error(form))))
    lesson = form.save()
    badge = render_to_string("studio/partials/_lesson_extra.html", dict(lesson=lesson), request=request)
    status = "skipped" if form.skipped else "saved"
    message = _("Atlandı; derste ek içerik zaten var.") if form.skipped else _("Kaydedildi.")
    return JsonResponse(dict(status=status, message=str(message), lesson=lesson.title, lesson_id=str(lesson.pk), badge=badge))


@superuser_required
@require_POST
def extra_content_preview(request):
    """Düzenleyicideki metnin sayfada görüneceği hâli (kaydetmeden)."""
    return render(
        request, "studio/partials/_extra_content_preview.html", dict(html=render_markdown(request.POST.get("extra_content", "")))
    )


@superuser_required
@require_POST
def lesson_extra_content_delete(request, lesson_id):
    lesson = _lesson(lesson_id)
    lesson.set_extra_content("")
    response = render(request, "studio/partials/_lesson_extra.html", dict(lesson=lesson))
    return _toast(response, "success", _("Ek içerik kaldırıldı."))


@superuser_required
@require_GET
def lesson_subtitles_status(request, lesson_id):
    return render(request, "studio/partials/_lesson_subtitles.html", dict(lesson=_lesson(lesson_id)))


@superuser_required
@require_POST
def subtitle_retry(request, subtitle_id):
    subtitle = get_object_or_404(LessonSubtitle.objects.select_related("lesson"), pk=subtitle_id)
    if subtitle.is_failed:
        subtitle.schedule()
    return render(request, "studio/partials/_lesson_subtitles.html", dict(lesson=_lesson(subtitle.lesson_id)))


@superuser_required
@require_POST
def subtitle_delete(request, subtitle_id):
    subtitle = get_object_or_404(LessonSubtitle, pk=subtitle_id)
    lesson_id = subtitle.lesson_id
    subtitle.remove()
    return render(request, "studio/partials/_lesson_subtitles.html", dict(lesson=_lesson(lesson_id)))


@superuser_required
def site_settings(request):
    """Site ayarları: yeni videoların yükleneceği platform. Her platformun eksik ayarı ve video sayısı gösterilir."""
    site = SiteSettings.load()
    form = SiteSettingsForm(request.POST or None, instance=site)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, _("Ayarlar kaydedildi. Yeni yüklemeler %(platform)s platformuna gidecek.") % {
            "platform": site.get_video_platform_display()
        })
        return redirect("studio:settings")
    lesson_totals = dict(
        Lesson.objects.exclude(video_id="").values_list("video_platform").annotate(total=Count("pk")).order_by()
    )
    platforms = [
        dict(item, lesson_total=lesson_totals.get(item["value"], 0), selected=item["value"] == site.video_platform)
        for item in video_service.choices()
    ]
    return render(request, "studio/settings.html", dict(form=form, platforms=platforms))


@superuser_required
@require_POST
def settings_check(request, platform):
    """Platform bağlantısını dener (anahtar geçerli mi, yetkiler yeterli mi); sonucu satırına yazar."""
    if platform not in VideoPlatform.values:
        return HttpResponseBadRequest()
    service = video_service.get(platform)
    try:
        result, ok = service.check(), True
    except video_service.VideoServiceError as error:
        result, ok = str(error), False
    return render(request, "studio/partials/_settings_check.html", dict(result=result, ok=ok))


# Yorumlar: kullanıcı yorumları onaya düşer; eski yorumlar buradan elle eklenir.
REVIEW_FILTERS = {
    "bekleyen": (gettext_lazy("Onay bekleyen"), lambda reviews: reviews.awaiting()),
    "yayinda": (gettext_lazy("Yayında"), lambda reviews: reviews.visible()),
    "gizli": (gettext_lazy("Gizli"), lambda reviews: reviews.filter(status=Status.ARCHIVED)),
    "tumu": (gettext_lazy("Tümü"), lambda reviews: reviews),
}
REVIEW_ACTIONS = {
    "approve": (Review.approve, gettext_lazy("Yorum onaylandı; sitede görünüyor.")),
    "hide": (Review.hide, gettext_lazy("Yorum gizlendi.")),
    "featured": (Review.toggle_featured, ""),
    "home": (Review.toggle_home, ""),
}


def _review_filter(request):
    key = request.GET.get("durum", "bekleyen")
    return key if key in REVIEW_FILTERS else "bekleyen"


@superuser_required
def reviews(request):
    """Yorumlar: filtre (durum, kurs) GET parametresinde; HTMX isteğinde yalnız liste döner."""
    key = _review_filter(request)
    base = Review.objects.select_related("course", "user")
    course_id = request.GET.get("kurs", "")
    if course_id:
        base = base.filter(course_id=course_id) if Course.objects.filter(pk=course_id).exists() else base.none()
    items = REVIEW_FILTERS[key][1](base).order_by("-written_at", "id")
    filters = [
        dict(key=name, label=label, count=apply(base).count(), checked=name == key)
        for name, (label, apply) in REVIEW_FILTERS.items()
    ]
    context = dict(reviews=items, filters=filters, review_filter=key, course_id=course_id, courses=Course.objects.order_by("title"))
    if request.htmx and not request.htmx.boosted:
        return render(request, "studio/partials/_review_list.html", context)
    context["import_form"] = ReviewImportForm()
    return render(request, "studio/reviews.html", context)


@superuser_required
@require_POST
def review_action(request, review_id, action):
    """Onayla, gizle, kursta öne çıkar, ana sayfada göster; satır yeniden çizilir."""
    if action not in REVIEW_ACTIONS:
        return HttpResponseBadRequest()
    review = get_object_or_404(Review.objects.select_related("course", "user"), pk=review_id)
    method, message = REVIEW_ACTIONS[action]
    method(review)
    response = render(request, "studio/partials/_review_row.html", dict(review=review))
    return _toast(response, "success", str(message)) if message else response


@superuser_required
@require_POST
def review_delete(request, review_id):
    get_object_or_404(Review, pk=review_id).delete()
    return _toast(HttpResponse(), "success", _("Yorum silindi."))


@superuser_required
def review_create(request):
    """Eski yorum ekler (ad elle yazılır)."""
    form = ReviewImportForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        review = form.save()
        messages.success(request, _("Yorum eklendi.") if not review.is_visible else _("Yorum eklendi ve yayınlandı."))
        return redirect(f"{reverse('studio:reviews')}?durum={'yayinda' if review.is_visible else 'bekleyen'}")
    return render(request, "studio/reviews.html", dict(import_form=form, filters=[], reviews=[], import_open=True))


@superuser_required
def review_edit(request, review_id):
    """Eski (aktarılan) yorumu düzenler; kullanıcı yorumlarının metni yalnız kullanıcı tarafından değiştirilir."""
    review = get_object_or_404(Review.objects.select_related("course", "user"), pk=review_id, user__isnull=True)
    form = ReviewImportForm(request.POST or None, instance=review, prefix=f"edit-{review.pk}")
    if request.method == "POST" and form.is_valid():
        return render(request, "studio/partials/_review_row.html", dict(review=form.save()))
    return render(request, "studio/partials/_review_edit.html", dict(review=review, form=form))


# E-postalar: şablonların önizlemesi (gönderim yok; test yalnız yönlendirme adresine)
def _email_preview_context(request, key):
    """Örnek veri ya da ?kullanici=e-posta ile seçilen kullanıcının gerçek verisi."""
    from account.models import User
    from mailing.emails import sample_context
    from order.emails import preview_context

    lookup = request.GET.get("kullanici", "").strip() or request.POST.get("kullanici", "").strip()
    if not lookup:
        return sample_context(key), None, ""
    user = User.objects.with_email(lookup).first()
    if user is None:
        return sample_context(key), None, _("Bu e-postayla kullanıcı yok; örnek veri gösteriliyor.")
    return preview_context(key, user), user, ""


@superuser_required
def emails(request):
    from mailing.emails import EMAILS

    groups = {}
    for key, email in EMAILS.items():
        groups.setdefault(email["group"], []).append(dict(email, key=key))
    return render(request, "studio/emails.html", dict(groups=groups, redirect_to=settings.EMAIL_REDIRECT_TO))


# Bültenler: Stüdyo'da yazılır, önizlenir, yönlendirme adresine test edilir, onaylı abonelere toplu gönderilir (Celery).
def _preview_subscriber(user):
    """Önizleme ve test gönderimi giriş yapan yöneticinin adıyla: abone kaydı varsa o, yoksa kaydedilmemiş bir örnek."""
    from newsletter.models import Subscriber

    return Subscriber.objects.by_email(user.email) or Subscriber(email=user.email, name=user.first_name)


@superuser_required
def newsletters(request):
    from newsletter.models import Issue, Subscriber

    issues = Issue.objects.select_related("batch").order_by("-created_at", "id")
    return render(request, "studio/newsletters.html", dict(issues=issues, confirmed_total=Subscriber.objects.confirmed().count()))


@superuser_required
def newsletter_create(request):
    from newsletter.models import PERSONALIZATION_FIELDS

    form = IssueForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        issue = form.save()
        messages.success(request, _("Taslak kaydedildi."))
        return redirect(issue)
    from newsletter.models import Subscriber

    return render(
        request,
        "studio/newsletter_edit.html",
        dict(
            form=form,
            issue=None,
            confirmed_total=Subscriber.objects.confirmed().count(),
            recipient_total=Subscriber.objects.confirmed().count(),
            personalization_fields=list(PERSONALIZATION_FIELDS.items()),
        ),
    )


@superuser_required
def newsletter_edit(request, issue_id):
    """Taslak düzenlenir ve önizlenir; gönderilmiş sayı yalnız görüntülenir (alıcılar toplu gönderim sayfasında)."""
    from mailing.emails import render_email
    from newsletter.models import PERSONALIZATION_FIELDS, Issue, Subscriber

    issue = get_object_or_404(Issue.objects.select_related("batch"), pk=issue_id)
    form = IssueForm(request.POST or None, instance=issue) if issue.is_draft else None
    if form is not None and request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, _("Taslak kaydedildi."))
        return redirect(issue)
    subject, text, html = render_email("newsletter", issue.email_context(_preview_subscriber(request.user)))
    return render(
        request,
        "studio/newsletter_edit.html",
        dict(
            form=form,
            issue=issue,
            subject=subject,
            html=html,
            text=text,
            confirmed_total=Subscriber.objects.confirmed().count(),
            recipient_total=issue.recipients().count(),
            personalization_fields=list(PERSONALIZATION_FIELDS.items()),
            redirect_to=settings.EMAIL_REDIRECT_TO,
            test_to=settings.EMAIL_TEST_TO,
            worker_online=_worker_online(),
        ),
    )


@superuser_required
@require_GET
def newsletter_audience(request):
    """Formdaki kitle seçimine göre kaç onaylı aboneye gideceği (kaydetmeden, HTMX ile her değişiklikte)."""
    from newsletter import audience

    form = IssueForm(request.GET)
    form.is_valid()
    kwargs = form.audience_kwargs()
    count = audience.subscribers(**kwargs).count() if kwargs else None
    errors = [error for name in form.AUDIENCE_FIELDS for error in form.errors.get(name, [])]
    return render(request, "studio/partials/_newsletter_audience_count.html", dict(count=count, errors=errors))


@superuser_required
@require_POST
def newsletter_send_test(request, issue_id):
    """Kayıtlı taslağı giriş yapanın adıyla yalnız test adresine (EMAIL_TEST_TO) gönderir."""
    from mailing.emails import send_email
    from newsletter.models import Issue

    issue = get_object_or_404(Issue, pk=issue_id)
    if not settings.EMAIL_TEST_TO:
        return _toast(HttpResponse(), "warning", _("Test adresi (EMAIL_TEST_TO) yok; test gönderimi kapalı."))
    try:
        send_email("newsletter", settings.EMAIL_TEST_TO, issue.email_context(_preview_subscriber(request.user)))
    except (smtplib.SMTPException, OSError) as error:
        return _toast(HttpResponse(), "error", _("Gönderilemedi: %(error)s") % {"error": error})
    return _toast(HttpResponse(), "success", _("Test e-postası %(to)s adresine gönderildi.") % {"to": settings.EMAIL_TEST_TO})


@superuser_required
@require_POST
def newsletter_send(request, issue_id):
    """Kitledeki onaylı abonelere toplu gönderimi başlatır (bir kez); gönderim Celery işçisinde yapılır."""
    from newsletter.models import Issue
    from newsletter.tasks import send_issue

    issue = get_object_or_404(Issue, pk=issue_id)
    if not _worker_online():
        messages.error(request, _("Celery işçisi çalışmıyor; gönderim başlatılmadı."))
    elif not issue.recipients().exists():
        messages.warning(request, _("Seçilen kitlede onaylı abone yok; gönderim başlatılmadı."))
    elif issue.start_sending():
        transaction.on_commit(partial(send_issue.delay, issue.pk))
        messages.success(request, _("Gönderim başladı."))
    else:
        messages.info(request, _("Bu bülten zaten gönderildi ya da gönderiliyor."))
    return HttpResponseClientRedirect(issue.get_absolute_url()) if request.htmx else redirect(issue)


@superuser_required
@require_POST
def newsletter_delete(request, issue_id):
    """Yalnız taslak silinir."""
    from newsletter.models import Issue

    issue = get_object_or_404(Issue, pk=issue_id, status="draft")
    issue.delete()
    messages.success(request, _("Taslak silindi."))
    return HttpResponseClientRedirect(reverse("studio:newsletters")) if request.htmx else redirect("studio:newsletters")


SUBSCRIBER_PAGE_SIZE = 50


@superuser_required
def subscribers(request):
    """Bülten aboneleri: durum filtresi ve adres/ad araması GET parametresinde; HTMX isteğinde yalnız liste döner.
    Çıkanlarda hangi e-postadaki bağlantıyla çıktığı gösterilir."""
    from newsletter.models import Subscriber, SubscriberStatus

    status = request.GET.get("durum", "")
    if status not in SubscriberStatus.values:
        status = ""
    query = request.GET.get("q", "").strip()
    base = Subscriber.objects.all()
    if query:
        base = base.filter(Q(email__icontains=query) | Q(name__icontains=query))
    counts = base.status_counts()
    items = base.filter(status=status) if status else base
    page = Paginator(items.with_unsubscribe_email().order_by("-created_at", "id"), SUBSCRIBER_PAGE_SIZE).get_page(request.GET.get("sayfa"))
    filters = [dict(key="", label=_("Tümü"), count=counts["all"])] + [
        dict(key=value, label=label, count=counts[value]) for value, label in SubscriberStatus.choices
    ]
    context = dict(page=page, status=status, query=query, filters=filters)
    if request.htmx and request.GET.get(ROWS_PARAM):
        return render(request, "studio/partials/_subscriber_rows.html", context)
    if request.htmx and not request.htmx.boosted:
        return render(request, "studio/partials/_subscriber_list.html", context)
    return render(request, "studio/subscribers.html", context)


EMAIL_LOG_PAGE_SIZE = 50


def _email_labels():
    from mailing.emails import EMAILS

    return {key: email["label"] for key, email in EMAILS.items()}


def _email_log_list(request, logs, list_url, labels):
    """Gönderim listesi bağlamı: şablon, durum ve adres/konu filtresi GET parametresinde, sayfalı."""
    from mailing.models import EmailStatus

    template = request.GET.get("sablon", "")
    status = request.GET.get("durum", "")
    query = request.GET.get("q", "").strip()
    if template:
        logs = logs.filter(template=template)
    if status in EmailStatus.values:
        logs = logs.filter(status=status)
    if query:
        logs = logs.filter(Q(to_email__icontains=query) | Q(subject__icontains=query))
    page = Paginator(logs.select_related("user").order_by("-created_at", "id"), EMAIL_LOG_PAGE_SIZE).get_page(request.GET.get("sayfa"))
    for log in page:
        log.label = labels.get(log.template, log.template)
    return dict(
        page=page,
        list_url=list_url,
        template=template,
        status=status,
        query=query,
        statuses=EmailStatus.choices,
        templates=list(labels.items()),
    )


@superuser_required
def email_log(request):
    """Gönderim günlüğü, iki sekme: tekil e-postalar (şifre, satın alma vb.; tek alıcı) ve toplu gönderimler (bülten;
    çok alıcı). Tekil listede filtre (şablon, durum, adres) GET parametresinde; HTMX isteğinde yalnız liste döner."""
    from mailing.models import EmailBatch, EmailLog

    labels = _email_labels()
    if request.GET.get("tur") == "toplu":
        batches = Paginator(EmailBatch.objects.with_stats().order_by("-created_at", "id"), EMAIL_LOG_PAGE_SIZE).get_page(request.GET.get("sayfa"))
        for batch in batches:
            batch.label = labels.get(batch.template, batch.template)
        return render(
            request,
            "studio/email_log.html",
            dict(tab="toplu", batches=batches, single_total=EmailLog.objects.single().count(), batch_total=batches.paginator.count),
        )
    single = EmailLog.objects.single()
    context = _email_log_list(request, single, reverse("studio:email_log"), labels)
    if request.htmx and request.GET.get(ROWS_PARAM):
        return render(request, "studio/partials/_email_log_rows.html", context)
    if request.htmx and not request.htmx.boosted:
        return render(request, "studio/partials/_email_log_list.html", context)
    stats = single.stats_by_template()
    for row in stats:
        row["label"] = labels.get(row["template"], row["template"])
    context.update(tab="tekil", stats=stats, totals=single.stats(), single_total=single.count(), batch_total=EmailBatch.objects.count())
    return render(request, "studio/email_log.html", context)


@superuser_required
def email_batch_detail(request, batch_id):
    """Toplu gönderim: kaç alıcıya gittiği, açılma/tıklama/çıkış oranları ve alıcı listesi (filtreli, sayfalı)."""
    from mailing.models import EmailBatch

    batch = get_object_or_404(EmailBatch.objects.with_stats(), pk=batch_id)
    labels = _email_labels()
    context = _email_log_list(request, batch.logs.all(), reverse("studio:email_batch_detail", args=[batch.pk]), labels)
    context["in_batch"] = True
    if request.htmx and request.GET.get(ROWS_PARAM):
        return render(request, "studio/partials/_email_log_rows.html", context)
    if request.htmx and not request.htmx.boosted:
        return render(request, "studio/partials/_email_log_list.html", context)
    context.update(batch=batch, label=labels.get(batch.template, batch.template))
    return render(request, "studio/email_batch_detail.html", context)


@superuser_required
def email_log_detail(request, log_id):
    """Bir e-postanın saklanan içeriği (gizli bağlantılar maskeli) ve olayları (gönderim, açılma, tıklama, çıkış)."""
    from mailing.models import EmailLog

    log = get_object_or_404(EmailLog.objects.select_related("user", "batch"), pk=log_id)
    batch_size = log.batch.logs.count() if log.batch else 0
    return render(
        request,
        "studio/email_log_detail.html",
        dict(log=log, label=_email_labels().get(log.template, log.template), events=log.events.all(), batch_size=batch_size),
    )


@superuser_required
def email_preview(request, key):
    from mailing.emails import EMAILS, render_email, template_names

    if key not in EMAILS:
        raise Http404
    context, user, warning = _email_preview_context(request, key)
    subject, text, html = render_email(key, context)
    return render(
        request,
        "studio/email_preview.html",
        dict(
            key=key,
            email=EMAILS[key],
            # Şablonda sözlük.items "items" değişkeniyle çakışır; liste olarak verilir.
            variables=list(EMAILS[key]["variables"].items()),
            subject=subject,
            text=text,
            html=html,
            files=template_names(key).values(),
            selected_user=user,
            lookup=request.GET.get("kullanici", ""),
            warning=warning,
            redirect_to=settings.EMAIL_REDIRECT_TO,
            test_to=settings.EMAIL_TEST_TO,
        ),
    )


@superuser_required
@require_POST
def email_send_test(request, key):
    """Önizlenen e-postayı yalnız test adresine (EMAIL_TEST_TO) gönderir; adres yoksa göndermez."""
    from mailing.emails import EMAILS, send_email

    if key not in EMAILS:
        raise Http404
    if not settings.EMAIL_TEST_TO:
        return _toast(HttpResponse(), "warning", _("Test adresi (EMAIL_TEST_TO) yok; test gönderimi kapalı."))
    context, _user, _warning = _email_preview_context(request, key)
    try:
        send_email(key, settings.EMAIL_TEST_TO, context)
    except (smtplib.SMTPException, OSError) as error:
        return _toast(HttpResponse(), "error", _("Gönderilemedi: %(error)s") % {"error": error})
    return _toast(HttpResponse(), "success", _("Test e-postası %(to)s adresine gönderildi.") % {"to": settings.EMAIL_TEST_TO})
