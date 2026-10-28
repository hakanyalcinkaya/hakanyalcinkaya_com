from datetime import timedelta
from decimal import Decimal
from functools import partial
from pathlib import Path

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models, transaction
from django.db.models import Count, F, FloatField, IntegerField, Q, Sum
from django.db.models.functions import Cast, Ceil, Coalesce
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from core.duration import ceil_minutes, clock, hours_minutes, video_file_seconds
from core.models import BaseModel, BaseSortOrder, BaseStatus, Status, StatusQuerySet
from core.text import slugify_tr

GENERAL_SECTION_SLUG = "genel"
PRICE_FIELD = {"max_digits": 10, "decimal_places": 2, "validators": [MinValueValidator(Decimal("0"))]}


def vimeo_src(vimeo_id, vimeo_hash=""):
    """Video.js Vimeo kaynağı. Gizli (unlisted) videolar Vimeo'nun verdiği anahtarla açılır: vimeo.com/<id>?h=<anahtar>."""
    if not vimeo_id:
        return ""
    return f"https://vimeo.com/{vimeo_id}?h={vimeo_hash}" if vimeo_hash else f"https://vimeo.com/{vimeo_id}"


def lesson_minutes_expression(prefix="", filter=None):
    """Her dersin süresi dakikaya yukarı yuvarlanıp toplanır (1 dk 27 sn → 2 dk)."""
    seconds = F(f"{prefix}duration_seconds")
    rounded = Ceil(Cast(seconds, FloatField()) / 60.0)
    return Coalesce(Cast(Sum(rounded, filter=filter), IntegerField()), 0)


class SlugFromTitleMixin:
    slug_source = "title"

    def slug_siblings(self):
        """Slug'ın benzersiz olması gereken kayıtlar (ör. aynı bölümdeki dersler); None ise kontrol edilmez."""
        return None

    def unique_slug(self, base):
        max_length = self._meta.get_field("slug").max_length
        base = base[: max_length - 4] or "icerik"
        siblings = self.slug_siblings()
        if siblings is None:
            return base
        siblings = siblings.exclude(pk=self.pk)
        slug, number = base, 2
        while siblings.filter(slug=slug).exists():
            slug, number = f"{base}-{number}", number + 1
        return slug

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = self.unique_slug(slugify_tr(getattr(self, self.slug_source)))
        super().save(*args, **kwargs)


class Category(SlugFromTitleMixin, BaseModel, BaseStatus, BaseSortOrder):
    """Kurs kategorisi. Üst kategori filtre için (Front-End), alt kategoriler kurs başlığında etiket (React 18.x)."""

    slug_source = "name"

    name = models.CharField(_("ad"), max_length=80)
    slug = models.SlugField(_("slug"), max_length=100, unique=True, blank=True)
    parent = models.ForeignKey(
        "self", on_delete=models.PROTECT, null=True, blank=True, related_name="children", verbose_name=_("üst kategori")
    )

    class Meta:
        verbose_name = _("kategori")
        verbose_name_plural = _("kategoriler")
        ordering = ("sort_order", "name")

    def __str__(self):
        return f"{self.parent} › {self.name}" if self.parent_id else self.name


class Technology(SlugFromTitleMixin, BaseModel, BaseSortOrder):
    slug_source = "name"

    name = models.CharField(_("ad"), max_length=60, unique=True)
    slug = models.SlugField(_("slug"), max_length=80, unique=True, blank=True)

    class Meta:
        verbose_name = _("teknoloji")
        verbose_name_plural = _("teknolojiler")
        ordering = ("sort_order", "name")

    def __str__(self):
        return self.name


class Level(models.TextChoices):
    BEGINNER = "beginner", _("Başlangıç")
    INTERMEDIATE = "intermediate", _("Orta")
    ADVANCED = "advanced", _("İleri")
    ALL = "all", _("Tüm seviyeler")


LEVEL_CARD_TEXT = {
    Level.BEGINNER: _("Sıfırdan başlar"),
    Level.INTERMEDIATE: _("Temel bilgi gerekir"),
    Level.ADVANCED: _("Deneyim gerektirir"),
    Level.ALL: _("Her seviyeye uygun"),
}


class PricedMixin:
    """Fiyatlar TL ve KDV dahil. Liste fiyatı satış fiyatından yüksekse üstü çizili gösterilir."""

    @property
    def has_list_discount(self):
        return self.compare_price is not None and self.compare_price > self.price

    @property
    def discount_percent(self):
        if not self.has_list_discount:
            return 0
        return int(round((1 - self.price / self.compare_price) * 100))


class CourseQuerySet(StatusQuerySet):
    def with_stats(self):
        published_lessons = Q(sections__status=Status.PUBLISHED, sections__lessons__status=Status.PUBLISHED)
        return self.annotate(
            lesson_total=Count("sections__lessons", filter=published_lessons, distinct=True),
            preview_total=Count(
                "sections__lessons", filter=published_lessons & Q(sections__lessons__is_preview=True), distinct=True
            ),
        )

    def for_listing(self):
        return self.published().select_related("category").prefetch_related("subcategories", "technologies")

    def with_video_stats(self):
        """Yönetim paneli için: video dersi, videosu yüklenmiş ders ve süren yükleme sayıları (taslaklar dahil)."""
        video_lessons = Q(sections__lessons__kind="video")
        return self.annotate(
            video_lesson_total=Count("sections__lessons", filter=video_lessons, distinct=True),
            video_ready_total=Count(
                "sections__lessons", filter=video_lessons & ~Q(sections__lessons__vimeo_id=""), distinct=True
            ),
            busy_upload_total=Count(
                "sections__lessons__video_uploads",
                filter=Q(sections__lessons__video_uploads__status__in=BUSY_UPLOAD_STATUSES),
                distinct=True,
            ),
        )


class Course(SlugFromTitleMixin, PricedMixin, BaseModel, BaseStatus, BaseSortOrder):
    title = models.CharField(_("başlık"), max_length=200)
    short_title = models.CharField(_("kısa başlık"), max_length=80, help_text=_("Örn. Front-End ve React 18.x"))
    slug = models.SlugField(_("slug"), max_length=200, unique=True, blank=True)
    subtitle = models.CharField(_("alt başlık"), max_length=300, blank=True)
    description = models.TextField(_("kısa açıklama"), blank=True, help_text=_("Kurs kartlarında görünür."))
    image = models.ImageField(_("kapak görseli"), upload_to="courses/", blank=True)
    preview_vimeo_id = models.CharField(
        _("tanıtım videosu (Vimeo kimliği)"), max_length=40, blank=True, help_text=_("Varsa kurs görseline tıklanınca oynar.")
    )
    preview_vimeo_hash = models.CharField(
        _("tanıtım videosu gizli anahtarı"),
        max_length=40,
        blank=True,
        help_text=_("Gizli videolarda Vimeo bağlantısındaki h= değeri (ör. 9a60ec7769)."),
    )
    preview_vimeo_title = models.CharField(
        _("tanıtım videosunun Vimeo'daki başlığı"),
        max_length=200,
        blank=True,
        help_text=_("Kurs başlığından farklıysa Vimeo'ya yeniden gönderilir."),
    )
    vimeo_folder_uri = models.CharField(
        _("Vimeo klasörü"), max_length=200, blank=True, help_text=_("İlk video yüklemesinde kurs adıyla açılır.")
    )
    category = models.ForeignKey(
        Category, on_delete=models.PROTECT, related_name="courses", verbose_name=_("kategori")
    )
    subcategories = models.ManyToManyField(
        Category, blank=True, related_name="tagged_courses", verbose_name=_("alt kategoriler")
    )
    technologies = models.ManyToManyField(Technology, blank=True, related_name="courses", verbose_name=_("teknolojiler"))
    instructors = models.ManyToManyField(
        "account.InstructorProfile",
        through="CourseInstructor",
        blank=True,
        related_name="courses",
        verbose_name=_("eğitmenler"),
    )
    level = models.CharField(_("seviye"), max_length=20, choices=Level, default=Level.BEGINNER)
    price = models.DecimalField(_("fiyat (₺, KDV dahil)"), **PRICE_FIELD)
    list_price = models.DecimalField(
        _("liste fiyatı (₺)"), null=True, blank=True, help_text=_("Fiyattan yüksekse üstü çizili gösterilir."), **PRICE_FIELD
    )
    access_note = models.TextField(_("erişim notu"), blank=True)

    objects = CourseQuerySet.as_manager()

    class Meta:
        verbose_name = _("kurs")
        verbose_name_plural = _("kurslar")
        ordering = ("sort_order", "title")

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("page:course_detail", kwargs={"slug": self.slug})

    def get_buy_url(self):
        return reverse("page:buy", kwargs={"slug": self.slug})

    def get_cart_url(self):
        return reverse("page:add_to_cart", kwargs={"slug": self.slug})

    @property
    def compare_price(self):
        return self.list_price

    @property
    def preview_video(self):
        return vimeo_src(self.preview_vimeo_id, self.preview_vimeo_hash)

    @property
    def has_preview_video(self):
        return bool(self.preview_vimeo_id)

    @property
    def latest_preview_upload(self):
        uploads = self.preview_uploads.all()
        return uploads[0] if uploads else None

    @property
    def has_busy_preview_upload(self):
        return self.preview_uploads.filter(status__in=BUSY_UPLOAD_STATUSES).exists()

    @property
    def needs_preview_title_sync(self):
        return bool(self.preview_vimeo_id) and self.preview_vimeo_title != self.title

    def queue_preview_title_sync(self):
        """Kurs başlığı tanıtım videosunun Vimeo başlığından farklıysa kayıt tamamlanınca Vimeo'da günceller."""
        if not self.needs_preview_title_sync:
            return False
        from course.tasks import sync_preview_title

        transaction.on_commit(partial(sync_preview_title.delay, str(self.pk)))
        return True

    def attach_preview_video(self, vimeo_id, vimeo_hash, vimeo_title):
        self.preview_vimeo_id = vimeo_id
        self.preview_vimeo_hash = vimeo_hash
        self.preview_vimeo_title = vimeo_title
        self.save(update_fields=["preview_vimeo_id", "preview_vimeo_hash", "preview_vimeo_title", "updated_at"])

    @property
    def level_card_text(self):
        return LEVEL_CARD_TEXT[self.level]

    def published_lessons(self):
        return Lesson.objects.published().filter(section__course=self, section__status=Status.PUBLISHED)

    @property
    def total_minutes(self):
        return self.published_lessons().aggregate(total=lesson_minutes_expression())["total"]

    @property
    def duration_display(self):
        return hours_minutes(self.total_minutes)

    @property
    def vimeo_folder_url(self):
        """Klasörün Vimeo'daki sayfası; API adresi /users/<kullanıcı>/projects/<klasör> biçimindedir."""
        parts = self.vimeo_folder_uri.strip("/").split("/")
        if len(parts) != 4:
            return ""
        return f"https://vimeo.com/user/{parts[1]}/folder/{parts[3]}"

    def ensure_vimeo_folder(self):
        """Kursun Vimeo klasörünü döner, yoksa açar. Aynı anda çalışan yüklemeler tek klasör açsın diye satır kilitlenir."""
        from course import vimeo

        with transaction.atomic():
            course = Course.objects.select_for_update().get(pk=self.pk)
            if not course.vimeo_folder_uri:
                course.vimeo_folder_uri = vimeo.create_folder(course.title)
                course.save(update_fields=["vimeo_folder_uri", "updated_at"])
        self.vimeo_folder_uri = course.vimeo_folder_uri
        return self.vimeo_folder_uri

    def general_section(self):
        """Kursa doğrudan bırakılan videoların bölümü; yoksa en başa taslak olarak açılır."""
        section = self.sections.filter(slug=GENERAL_SECTION_SLUG).first()
        if section is None:
            self.sections.update(sort_order=F("sort_order") + 1)
            section = Section.objects.create(course=self, title=_("Genel"), slug=GENERAL_SECTION_SLUG, sort_order=0)
        return section

    def next_section_order(self):
        return (self.sections.aggregate(last=models.Max("sort_order"))["last"] or 0) + 1

    @transaction.atomic
    def apply_structure(self, sections, reorder_sections=True):
        """Stüdyodaki sürükle-bırak düzenini kaydeder.

        `sections`: [{"id": bölüm, "lessons": [ders, ...]}, ...] sayfadaki sırayla. Ders başka bölüme taşındıysa
        bölümü değişir. Listede olmayan bölüm ve dersler değişmez; yabancı kimlik gelirse ValueError.
        """
        own_sections = {str(pk): pk for pk in self.sections.values_list("pk", flat=True)}
        lessons = {str(lesson.pk): lesson for lesson in Lesson.objects.filter(section__course=self)}
        seen = set()
        for section_index, item in enumerate(sections):
            section_id = str(item.get("id"))
            if section_id not in own_sections:
                raise ValueError(f"Bölüm bu kursa ait değil: {section_id}")
            if reorder_sections:
                Section.objects.filter(pk=section_id).update(sort_order=section_index)
            for lesson_index, lesson_id in enumerate(item.get("lessons", [])):
                lesson = lessons.get(str(lesson_id))
                if lesson is None or lesson.pk in seen:
                    raise ValueError(f"Ders bu kursa ait değil ya da iki kez geçiyor: {lesson_id}")
                seen.add(lesson.pk)
                lesson.move_to(own_sections[section_id], lesson_index)

    def vimeo_video_ids(self):
        """Kursa bağlı tüm Vimeo videoları: tanıtım videosu ve ders videoları."""
        lesson_ids = Lesson.objects.filter(section__course=self).exclude(vimeo_id="").values_list("vimeo_id", flat=True)
        ids = [self.preview_vimeo_id, *lesson_ids] if self.preview_vimeo_id else list(lesson_ids)
        return list(dict.fromkeys(ids))

    def queue_move_to_vimeo_folder(self):
        from course.tasks import move_course_videos_to_folder

        transaction.on_commit(partial(move_course_videos_to_folder.delay, str(self.pk)))

    def lessons_needing_vimeo_title_sync(self):
        return Lesson.objects.filter(section__course=self).exclude(vimeo_id="").exclude(vimeo_title=F("title"))

    def sync_durations(self):
        """Vimeo kimliği olan derslerin süresini API'den günceller; güncellenen ders sayısını döner."""
        updated = 0
        for lesson in self.published_lessons().exclude(vimeo_id=""):
            lesson.sync_duration()
            updated += 1
        return updated


class CourseInstructor(BaseModel, BaseSortOrder):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="course_instructors")
    instructor = models.ForeignKey(
        "account.InstructorProfile", on_delete=models.PROTECT, related_name="course_links", verbose_name=_("eğitmen")
    )

    class Meta:
        verbose_name = _("kurs eğitmeni")
        verbose_name_plural = _("kurs eğitmenleri")
        ordering = ("sort_order",)
        constraints = [models.UniqueConstraint(fields=("course", "instructor"), name="course_instructor_unique")]

    def __str__(self):
        return f"{self.course} · {self.instructor}"


class HighlightKind(models.TextChoices):
    LEARN = "learn", _("Neler öğreneceksin")
    ABOUT = "about", _("Kurs hakkında")
    FEATURE = "feature", _("Özellik")
    TOPIC = "topic", _("İşlenen konu")
    OUTCOME = "outcome", _("Kazanım")
    AUDIENCE = "audience", _("Kimler için")


class CourseHighlight(BaseModel, BaseSortOrder):
    """Kurs sayfasındaki madde listeleri: öğrenecekler, özellikler, konular, kazanımlar, hedef kitle."""

    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="highlights")
    kind = models.CharField(_("tür"), max_length=20, choices=HighlightKind)
    title = models.CharField(_("başlık"), max_length=160, blank=True)
    text = models.TextField(_("metin"))

    class Meta:
        verbose_name = _("kurs maddesi")
        verbose_name_plural = _("kurs maddeleri")
        ordering = ("sort_order",)

    def __str__(self):
        return self.title or self.text[:60]


class SectionQuerySet(StatusQuerySet):
    def with_minutes(self):
        published = Q(lessons__status=Status.PUBLISHED)
        return self.annotate(
            minutes=lesson_minutes_expression("lessons__", filter=published),
            lesson_total=Count("lessons", filter=published, distinct=True),
        )


class Section(SlugFromTitleMixin, BaseModel, BaseStatus, BaseSortOrder):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="sections", verbose_name=_("kurs"))
    title = models.CharField(_("başlık"), max_length=200)
    slug = models.SlugField(_("slug"), max_length=200, blank=True)

    objects = SectionQuerySet.as_manager()

    class Meta:
        verbose_name = _("bölüm")
        verbose_name_plural = _("bölümler")
        ordering = ("sort_order",)
        constraints = [models.UniqueConstraint(fields=("course", "slug"), name="section_slug_unique_per_course")]

    def __str__(self):
        return f"{self.course.short_title} · {self.title}"

    def slug_siblings(self):
        return Section.objects.filter(course_id=self.course_id)

    def next_lesson_order(self):
        return (self.lessons.aggregate(last=models.Max("sort_order"))["last"] or 0) + 1

    @property
    def can_delete(self):
        # Videoları olan bölüm silinmez; önce dersler başka bölüme taşınır ya da silinir.
        return not self.lessons.exists()

    @property
    def total_minutes(self):
        return self.lessons.published().aggregate(total=lesson_minutes_expression())["total"]

    @property
    def duration_display(self):
        return hours_minutes(self.total_minutes)


class LessonKind(models.TextChoices):
    VIDEO = "video", _("Video")
    FORM = "form", _("Form")
    TEXT = "text", _("Metin")


LESSON_ICONS = {LessonKind.VIDEO: "bi-play-circle", LessonKind.FORM: "bi-ui-checks", LessonKind.TEXT: "bi-file-text"}


class Lesson(SlugFromTitleMixin, BaseModel, BaseStatus, BaseSortOrder):
    section = models.ForeignKey(Section, on_delete=models.CASCADE, related_name="lessons", verbose_name=_("bölüm"))
    title = models.CharField(_("başlık"), max_length=250)
    slug = models.SlugField(_("slug"), max_length=250, blank=True)
    kind = models.CharField(_("tür"), max_length=10, choices=LessonKind, default=LessonKind.VIDEO)
    is_preview = models.BooleanField(_("ücretsiz önizleme"), default=False)
    # Video yönetim panelinden (studio) Celery ile Vimeo'ya yüklenir; kimlik elle de girilebilir.
    vimeo_id = models.CharField(_("Vimeo video kimliği"), max_length=40, blank=True)
    vimeo_hash = models.CharField(
        _("Vimeo gizli anahtarı"), max_length=40, blank=True, help_text=_("Gizli videolarda Vimeo bağlantısındaki h= değeri.")
    )
    duration_seconds = models.PositiveIntegerField(
        _("süre (saniye)"), null=True, blank=True, help_text=_("Vimeo API ile hesaplanır; anahtar yoksa elle girilebilir.")
    )
    vimeo_title = models.CharField(
        _("Vimeo'daki başlık"), max_length=250, blank=True, help_text=_("Ders başlığından farklıysa Vimeo'ya yeniden gönderilir.")
    )
    external_url = models.URLField(_("dış bağlantı"), blank=True, help_text=_("Form dersleri için."))
    body = models.TextField(_("metin içeriği"), blank=True)

    class Meta:
        verbose_name = _("ders")
        verbose_name_plural = _("dersler")
        ordering = ("sort_order",)
        constraints = [models.UniqueConstraint(fields=("section", "slug"), name="lesson_slug_unique_per_section")]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse(
            "page:lesson",
            kwargs={"course_slug": self.section.course.slug, "section_slug": self.section.slug, "lesson_slug": self.slug},
        )

    @property
    def icon(self):
        return LESSON_ICONS[self.kind]

    @property
    def video_src(self):
        return vimeo_src(self.vimeo_id, self.vimeo_hash)

    @property
    def duration_minutes(self):
        return ceil_minutes(self.duration_seconds)

    @property
    def duration_display(self):
        return clock(self.duration_seconds) if self.duration_seconds else ""

    def sync_duration(self):
        from course.vimeo import fetch_duration

        self.duration_seconds = fetch_duration(self.vimeo_id)
        self.save(update_fields=["duration_seconds", "updated_at"])
        return self.duration_seconds

    @property
    def is_video(self):
        return self.kind == LessonKind.VIDEO

    @property
    def latest_upload(self):
        # video_uploads önceden yüklendiyse (prefetch) ek sorgu yapılmaz; sıralama en yeni önce.
        uploads = self.video_uploads.all()
        return uploads[0] if uploads else None

    @property
    def has_busy_upload(self):
        return self.video_uploads.filter(status__in=BUSY_UPLOAD_STATUSES).exists()

    @property
    def has_busy_subtitles(self):
        return any(subtitle.is_busy for subtitle in self.subtitles.all())

    @property
    def needs_vimeo_title_sync(self):
        return bool(self.vimeo_id) and self.vimeo_title != self.title

    def queue_vimeo_title_sync(self):
        """Başlık Vimeo'dakinden farklıysa kayıt tamamlanınca Vimeo'da güncellenmek üzere sıraya alır."""
        if not self.needs_vimeo_title_sync:
            return False
        from course.tasks import sync_vimeo_title

        transaction.on_commit(partial(sync_vimeo_title.delay, str(self.pk)))
        return True

    def slug_siblings(self):
        return Lesson.objects.filter(section_id=self.section_id)

    def move_to(self, section_id, sort_order):
        """Dersi bölüme ve sıraya yerleştirir; hedef bölümde aynı slug varsa ders yeni slug alır."""
        fields = {"sort_order": sort_order}
        if self.section_id != section_id:
            self.section_id = section_id
            fields["section_id"] = section_id
            fields["slug"] = self.slug = self.unique_slug(self.slug)
        if self.sort_order != sort_order or len(fields) > 1:
            self.sort_order = sort_order
            Lesson.objects.filter(pk=self.pk).update(updated_at=timezone.now(), **fields)

    def toggle_preview(self):
        self.is_preview = not self.is_preview
        self.save(update_fields=["is_preview", "updated_at"])

    def remove(self, delete_from_vimeo=False):
        """Dersi siler. Süren yüklemeler iptal edilir, sunucudaki dosyalar silinir.

        `delete_from_vimeo` ise dersin Vimeo videosu da (kayıt tamamlanınca) silinir; değilse Vimeo'da kalır.
        """
        from course.tasks import delete_vimeo_video

        for upload in self.video_uploads.all():
            upload.cancel()
            upload.discard_file()
        for subtitle in self.subtitles.all():
            subtitle.file.delete(save=False)
        if delete_from_vimeo and self.vimeo_id:
            transaction.on_commit(partial(delete_vimeo_video.delay, self.vimeo_id))
        self.delete()

    def attach_video(self, vimeo_id, vimeo_hash, duration_seconds, vimeo_title):
        self.vimeo_id = vimeo_id
        self.vimeo_hash = vimeo_hash
        self.duration_seconds = duration_seconds or None
        self.vimeo_title = vimeo_title
        self.save(update_fields=["vimeo_id", "vimeo_hash", "duration_seconds", "vimeo_title", "updated_at"])
        # Altyazılar videoya bağlıdır; yeni video gelince hepsi yeniden gönderilir.
        for subtitle in self.subtitles.all():
            subtitle.vimeo_uri = ""
            subtitle.schedule()


class VideoUploadStatus(models.TextChoices):
    QUEUED = "queued", _("Sırada")
    UPLOADING = "uploading", _("Vimeo'ya gönderiliyor")
    PROCESSING = "processing", _("Vimeo'da işleniyor")
    READY = "ready", _("Hazır")
    FAILED = "failed", _("Hata")
    CANCELED = "canceled", _("İptal edildi")


BUSY_UPLOAD_STATUSES = (VideoUploadStatus.QUEUED, VideoUploadStatus.UPLOADING, VideoUploadStatus.PROCESSING)
FINISHED_UPLOAD_STATUSES = (VideoUploadStatus.READY, VideoUploadStatus.FAILED, VideoUploadStatus.CANCELED)
# Dosya Vimeo'ya ulaştıktan sonra Vimeo'nun kendi video durumu; bekleme Vimeo tarafında olduğunda panelde açıklanır.
VIMEO_STATE_LABELS = {
    "uploading": _("Vimeo dosyayı sıraya aldı"),
    "transcode_starting": _("Vimeo işlemeye başlıyor"),
    "transcoding": _("Vimeo işliyor"),
}
# İşçi kapalıyken ya da görev kaybolduğunda yükleme "Sırada" takılı kalır; bu süreden sonra yeniden sıraya alınabilir.
STALE_QUEUE_MINUTES = 10
VIDEO_EXTENSIONS = (".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi")


class UploadCanceled(Exception):
    """Yükleme sürerken panelden iptal edildi; işçi elindeki işi bırakır."""


class VideoUploadQuerySet(models.QuerySet):
    def busy(self):
        return self.filter(status__in=BUSY_UPLOAD_STATUSES)

    def finished(self):
        return self.filter(status__in=FINISHED_UPLOAD_STATUSES)

    def for_queue(self):
        """Kuyruk sayfası: sürenler önce, sonra en yeniler."""
        return self.select_related("lesson__section__course", "course", "created_by").order_by(
            models.Case(models.When(status__in=BUSY_UPLOAD_STATUSES, then=0), default=1), "-created_at", "id"
        )


class VideoUpload(BaseModel):
    """Videonun Vimeo'ya yüklenme işi; hedef ya bir ders ya da bir kursun tanıtım videosudur.

    Dosya önce sunucuya gelir; Vimeo işlemeyi bitirince silinir, o zamana kadar hata olursa yeniden gönderilebilir.
    """

    lesson = models.ForeignKey(
        Lesson, on_delete=models.CASCADE, null=True, blank=True, related_name="video_uploads", verbose_name=_("ders")
    )
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="preview_uploads",
        verbose_name=_("kurs (tanıtım videosu)"),
    )
    file = models.FileField(
        _("dosya"), upload_to="video_uploads/%Y/%m/", blank=True, help_text=_("Vimeo videoyu işleyince silinir.")
    )
    original_name = models.CharField(_("dosya adı"), max_length=255)
    size = models.PositiveBigIntegerField(_("boyut (bayt)"), default=0)
    duration_seconds = models.PositiveIntegerField(
        _("süre (saniye)"), null=True, blank=True, help_text=_("Yüklenen dosyadan okunur; Vimeo işleyince onun süresi esas alınır.")
    )
    status = models.CharField(
        _("durum"), max_length=20, choices=VideoUploadStatus, default=VideoUploadStatus.QUEUED, db_index=True
    )
    progress = models.PositiveSmallIntegerField(_("ilerleme (%)"), default=0)
    vimeo_id = models.CharField(_("Vimeo video kimliği"), max_length=40, blank=True)
    vimeo_title = models.CharField(_("Vimeo'ya gönderilen başlık"), max_length=250, blank=True)
    vimeo_state = models.CharField(_("Vimeo durumu"), max_length=30, blank=True)
    error = models.TextField(_("hata"), blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("yükleyen"),
    )
    sent_at = models.DateTimeField(_("Vimeo'ya ulaştı"), null=True, blank=True)
    finished_at = models.DateTimeField(_("bitiş"), null=True, blank=True)

    objects = VideoUploadQuerySet.as_manager()

    class Meta:
        verbose_name = _("video yüklemesi")
        verbose_name_plural = _("video yüklemeleri")
        ordering = ("-created_at",)
        constraints = [
            models.CheckConstraint(
                condition=Q(lesson__isnull=False, course__isnull=True) | Q(lesson__isnull=True, course__isnull=False),
                name="video_upload_single_target",
            )
        ]

    def __str__(self):
        return f"{self.target_label} · {self.get_status_display()}"

    @property
    def is_preview(self):
        return self.course_id is not None

    @property
    def target_label(self):
        return f"{self.course} · {_('tanıtım videosu')}" if self.is_preview else str(self.lesson)

    @property
    def target_course(self):
        return self.course if self.is_preview else self.lesson.section.course

    @property
    def vimeo_name(self):
        """Vimeo'daki ad oynatıcıda görünür: dersin ya da kursun Türkçe başlığı."""
        return self.course.title if self.is_preview else self.lesson.title

    @property
    def is_busy(self):
        return self.status in BUSY_UPLOAD_STATUSES

    @property
    def is_uploading(self):
        return self.status == VideoUploadStatus.UPLOADING

    @property
    def is_failed(self):
        return self.status == VideoUploadStatus.FAILED

    @property
    def is_canceled(self):
        return self.status == VideoUploadStatus.CANCELED

    @property
    def is_processing(self):
        return self.status == VideoUploadStatus.PROCESSING

    @property
    def is_stale(self):
        return self.status == VideoUploadStatus.QUEUED and self.updated_at < timezone.now() - timedelta(
            minutes=STALE_QUEUE_MINUTES
        )

    @property
    def duration_display(self):
        return clock(self.duration_seconds) if self.duration_seconds else ""

    @property
    def vimeo_state_label(self):
        return VIMEO_STATE_LABELS.get(self.vimeo_state, "")

    @property
    def can_cancel(self):
        return self.is_busy

    @property
    def can_retry(self):
        return bool(self.file) and (self.is_failed or self.is_canceled or self.is_stale)

    @property
    def can_discard(self):
        return not self.is_busy

    def has_other_busy_upload(self):
        siblings = VideoUpload.objects.filter(course=self.course) if self.is_preview else self.lesson.video_uploads
        return siblings.busy().exclude(pk=self.pk).exists()

    def _move(self, from_statuses, **changes):
        """Kaydı yalnız beklenen durumdaysa değiştirir. Panelden iptal ile işçi aynı anda yazarsa önce gelen kazanır."""
        changes["updated_at"] = timezone.now()
        moved = VideoUpload.objects.filter(pk=self.pk, status__in=from_statuses).update(**changes)
        if moved:
            for name, value in changes.items():
                setattr(self, name, value)
        return bool(moved)

    def read_duration(self):
        """Süreyi dosyadan okur; videosu olmayan derse hemen yazılır (video değiştiriliyorsa Vimeo hazır olunca)."""
        self.duration_seconds = video_file_seconds(self.file.path)
        self.save(update_fields=["duration_seconds", "updated_at"])
        if self.duration_seconds and self.lesson_id and not self.lesson.vimeo_id:
            self.lesson.duration_seconds = self.duration_seconds
            self.lesson.save(update_fields=["duration_seconds", "updated_at"])

    def queue(self):
        from course.tasks import upload_video

        transaction.on_commit(partial(upload_video.delay, str(self.pk)))

    # Panel eylemleri

    def retry(self):
        """Hatalı, iptal edilmiş ya da takılı yüklemeyi aynı dosyayla baştan sıraya alır; Vimeo'da yeni kayıt açılır."""
        if not self.can_retry or self.has_other_busy_upload():
            return False
        statuses = (VideoUploadStatus.FAILED, VideoUploadStatus.CANCELED, VideoUploadStatus.QUEUED)
        moved = self._move(
            statuses,
            status=VideoUploadStatus.QUEUED,
            progress=0,
            vimeo_id="",
            vimeo_state="",
            error="",
            sent_at=None,
            finished_at=None,
        )
        if moved:
            self.queue()
        return moved

    def cancel(self):
        """Süren yüklemeyi durdurur. Vimeo'da açılmış (henüz derse bağlanmamış) video silinir; dosya yeniden başlatmak için kalır."""
        if not self._move(BUSY_UPLOAD_STATUSES, status=VideoUploadStatus.CANCELED, finished_at=timezone.now()):
            return False
        # İşçi bu arada Vimeo kaydı açmış olabilir; güncel kimlik okunur.
        self.refresh_from_db(fields=["vimeo_id"])
        if self.vimeo_id:
            from course.tasks import delete_vimeo_video

            transaction.on_commit(partial(delete_vimeo_video.delay, self.vimeo_id))
        return True

    def discard(self):
        """Biten işi kuyruktan kaldırır; yerel dosya da silinir. Derse bağlanmış video etkilenmez."""
        if not self.can_discard:
            return False
        self.discard_file()
        self.delete()
        return True

    # İşçi geçişleri (Celery)

    def mark_uploading(self):
        return self._move((VideoUploadStatus.QUEUED,), status=VideoUploadStatus.UPLOADING, progress=0)

    def mark_created(self, vimeo_id, vimeo_title):
        if not self._move((VideoUploadStatus.UPLOADING,), vimeo_id=vimeo_id, vimeo_title=vimeo_title):
            raise UploadCanceled

    def set_progress(self, sent, total):
        """Her parçadan sonra çağrılır; yükleme iptal edildiyse UploadCanceled ile gönderimi durdurur."""
        percent = min(100, sent * 100 // total) if total else 100
        if not self._move((VideoUploadStatus.UPLOADING,), progress=percent):
            raise UploadCanceled

    def mark_sent(self):
        """Dosya Vimeo'ya ulaştı, işlemesi beklenir. Yerel kopya, işleme başarısız olursa yeniden gönderilmek üzere kalır."""
        return self._move(
            (VideoUploadStatus.UPLOADING,), status=VideoUploadStatus.PROCESSING, progress=100, sent_at=timezone.now()
        )

    def set_vimeo_state(self, state):
        if state and state != self.vimeo_state:
            self._move((VideoUploadStatus.PROCESSING,), vimeo_state=state)

    def mark_ready(self, vimeo_status):
        moved = self._move(
            (VideoUploadStatus.PROCESSING,),
            status=VideoUploadStatus.READY,
            vimeo_state=vimeo_status.state,
            finished_at=timezone.now(),
        )
        if not moved:
            return False
        self.discard_file()
        VideoUpload.objects.filter(pk=self.pk).update(file="")
        if self.is_preview:
            self.course.attach_preview_video(self.vimeo_id, vimeo_status.hash, self.vimeo_title)
        else:
            duration = vimeo_status.duration or self.duration_seconds
            self.lesson.attach_video(self.vimeo_id, vimeo_status.hash, duration, self.vimeo_title)
        return True

    def mark_failed(self, error):
        return self._move(BUSY_UPLOAD_STATUSES, status=VideoUploadStatus.FAILED, error=error, finished_at=timezone.now())

    def discard_file(self):
        if self.file:
            self.file.delete(save=False)


class SubtitleLanguage(models.TextChoices):
    # Oynatıcıdaki altyazı menüsünde dilin kendi adıyla görünür.
    TR = "tr", "Türkçe"
    EN = "en", "English"
    DE = "de", "Deutsch"
    FR = "fr", "Français"
    ES = "es", "Español"
    AR = "ar", "العربية"
    RU = "ru", "Русский"


class SubtitleStatus(models.TextChoices):
    WAITING = "waiting", _("Video bekleniyor")
    QUEUED = "queued", _("Gönderiliyor")
    READY = "ready", _("Vimeo'da")
    FAILED = "failed", _("Hata")


SUBTITLE_EXTENSIONS = (".srt", ".vtt")


class LessonSubtitle(BaseModel):
    """Dersin altyazı dosyası. Dosya saklanır; video değişince yeni videoya yeniden gönderilir."""

    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name="subtitles", verbose_name=_("ders"))
    language = models.CharField(_("dil"), max_length=10, choices=SubtitleLanguage)
    file = models.FileField(_("dosya"), upload_to="subtitles/%Y/%m/")
    status = models.CharField(
        _("durum"), max_length=20, choices=SubtitleStatus, default=SubtitleStatus.QUEUED, db_index=True
    )
    vimeo_uri = models.CharField(_("Vimeo altyazı adresi"), max_length=200, blank=True)
    error = models.TextField(_("hata"), blank=True)

    class Meta:
        verbose_name = _("altyazı")
        verbose_name_plural = _("altyazılar")
        ordering = ("language",)
        constraints = [models.UniqueConstraint(fields=("lesson", "language"), name="lesson_subtitle_unique_language")]

    def __str__(self):
        return f"{self.lesson} · {self.get_language_display()}"

    @property
    def is_busy(self):
        return self.status == SubtitleStatus.QUEUED

    @property
    def is_failed(self):
        return self.status == SubtitleStatus.FAILED

    @property
    def file_name(self):
        return Path(self.file.name).name

    def schedule(self):
        """Videosu hazırsa Vimeo'ya gönderilmek üzere sıraya alır, değilse video hazır olunca gönderilir."""
        from course.tasks import upload_subtitle

        ready = self.lesson.vimeo_id and not self.lesson.has_busy_upload
        self.status = SubtitleStatus.QUEUED if ready else SubtitleStatus.WAITING
        self.error = ""
        self.save(update_fields=["status", "error", "vimeo_uri", "updated_at"])
        if ready:
            transaction.on_commit(partial(upload_subtitle.delay, str(self.pk)))

    def remove(self):
        """Kaydı ve dosyasını siler; Vimeo'daki altyazı kayıt tamamlanınca kaldırılır."""
        from course.tasks import delete_text_track

        if self.vimeo_uri:
            transaction.on_commit(partial(delete_text_track.delay, self.vimeo_uri))
        self.file.delete(save=False)
        self.delete()

    def mark_waiting(self):
        self.status = SubtitleStatus.WAITING
        self.save(update_fields=["status", "updated_at"])

    def mark_ready(self, vimeo_uri):
        self.status = SubtitleStatus.READY
        self.vimeo_uri = vimeo_uri
        self.save(update_fields=["status", "vimeo_uri", "updated_at"])

    def mark_failed(self, error):
        self.status = SubtitleStatus.FAILED
        self.error = error
        self.save(update_fields=["status", "error", "updated_at"])


class ReviewSource(models.TextChoices):
    IMPORTED = "imported", _("Dışarıdan aktarıldı")
    USER = "user", _("Kullanıcı yorumu")


class Review(BaseModel, BaseStatus, BaseSortOrder):
    """Kurs yorumu. Dışarıdan aktarılanlarda kullanıcı boş, ad elle girilir."""

    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="reviews", verbose_name=_("kurs"))
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviews",
        verbose_name=_("kullanıcı"),
    )
    author_name = models.CharField(_("yazan"), max_length=120, blank=True)
    text = models.TextField(_("yorum"))
    rating = models.PositiveSmallIntegerField(
        _("puan"), null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    source = models.CharField(_("kaynak"), max_length=20, choices=ReviewSource, default=ReviewSource.IMPORTED)

    class Meta:
        verbose_name = _("yorum")
        verbose_name_plural = _("yorumlar")
        ordering = ("sort_order", "-created_at")
        constraints = [
            models.UniqueConstraint(
                fields=("course", "user"), condition=Q(user__isnull=False), name="review_one_per_user_course"
            ),
        ]

    def __str__(self):
        return f"{self.display_name} · {self.course.short_title}"

    @property
    def display_name(self):
        if self.user_id and not self.author_name:
            return self.user.display_name
        return self.author_name

    @property
    def initial(self):
        return self.display_name[:1].upper()


class BundleQuerySet(StatusQuerySet):
    def for_listing(self):
        return self.published().prefetch_related("courses")


class Bundle(SlugFromTitleMixin, PricedMixin, BaseModel, BaseStatus, BaseSortOrder):
    """Birden fazla kurs, kendi indirimli fiyatıyla. Liste fiyatı içindeki kursların fiyatları toplamıdır."""

    title = models.CharField(_("başlık"), max_length=200)
    short_title = models.CharField(_("kısa başlık"), max_length=80)
    slug = models.SlugField(_("slug"), max_length=200, unique=True, blank=True)
    description = models.TextField(_("açıklama"), blank=True)
    image = models.ImageField(_("kapak görseli"), upload_to="bundles/", blank=True)
    price = models.DecimalField(_("paket fiyatı (₺, KDV dahil)"), **PRICE_FIELD)
    courses = models.ManyToManyField(Course, through="BundleCourse", related_name="bundles", verbose_name=_("kurslar"))

    objects = BundleQuerySet.as_manager()

    class Meta:
        verbose_name = _("paket")
        verbose_name_plural = _("paketler")
        ordering = ("sort_order", "title")

    def __str__(self):
        return self.title

    @property
    def compare_price(self):
        return self.courses.aggregate(total=Sum("price"))["total"]


class BundleCourse(BaseModel, BaseSortOrder):
    bundle = models.ForeignKey(Bundle, on_delete=models.CASCADE, related_name="bundle_courses")
    course = models.ForeignKey(Course, on_delete=models.PROTECT, related_name="bundle_links", verbose_name=_("kurs"))

    class Meta:
        verbose_name = _("paketteki kurs")
        verbose_name_plural = _("paketteki kurslar")
        ordering = ("sort_order",)
        constraints = [models.UniqueConstraint(fields=("bundle", "course"), name="bundle_course_unique")]

    def __str__(self):
        return f"{self.bundle} · {self.course}"
