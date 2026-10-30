import re
import unicodedata
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
from core.markup import render_markdown
from core.models import BaseModel, BaseSortOrder, BaseStatus, SiteSettings, Status, StatusQuerySet, VideoPlatform
from course import video_service
from core.text import slugify_tr

GENERAL_SECTION_SLUG = "genel"
# Taslak aktarımında karşılığı olmayan derslerin bölümü (course.outline_import).
LEFTOVER_SECTION_SLUG = "eslesmeyen-dersler"
# Ders dosyalarının baştaki sıra numarası (ör. "018-014" ya da "007-022-003").
LESSON_FILE_NUMBER = re.compile(r"^\d+(?:-\d+)*")
PRICE_FIELD = {"max_digits": 10, "decimal_places": 2, "validators": [MinValueValidator(Decimal("0"))]}


def retire_replaced_video(platform, video_id):
    """Yerine yenisi konan videoyu platformdan siler (kayıt tamamlanınca, Celery'de). Video başka bir derste ya da kurs
    tanıtımında hâlâ kullanılıyorsa silinmez."""
    from course.tasks import delete_remote_video

    if not video_id:
        return
    in_use = Lesson.objects.filter(video_platform=platform, video_id=video_id).exists() or Course.objects.filter(
        preview_video_platform=platform, preview_video_id=video_id
    ).exists()
    if not in_use:
        transaction.on_commit(partial(delete_remote_video.delay, video_id, platform))


def attached_video_ids(platform):
    """Derslere ve kurs tanıtımlarına bağlı videoların platformdaki kimlikleri."""
    lessons = Lesson.objects.filter(video_platform=platform).exclude(video_id="").values_list("video_id", flat=True)
    previews = (
        Course.objects.filter(preview_video_platform=platform)
        .exclude(preview_video_id="")
        .values_list("preview_video_id", flat=True)
    )
    return set(lessons) | set(previews)


def video_ids_in_use(platform):
    """Platformda silinmemesi gereken videolar: bağlı olanlar ve süren yüklemelerin henüz bağlanmamış videoları."""
    uploads = VideoUpload.objects.busy().filter(platform=platform).exclude(video_id="").values_list("video_id", flat=True)
    return attached_video_ids(platform) | set(uploads)


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
                "sections__lessons", filter=video_lessons & ~Q(sections__lessons__video_id=""), distinct=True
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
    # Videolar ayarlarda seçili platformda (Bunny Stream / Vimeo) tutulur; stüdyodan yüklenince alanlar kendiliğinden dolar.
    preview_video_platform = models.CharField(
        _("tanıtım videosunun platformu"), max_length=20, choices=VideoPlatform, default=VideoPlatform.BUNNY
    )
    preview_video_id = models.CharField(
        _("tanıtım videosu (platformdaki kimliği)"),
        max_length=40,
        blank=True,
        help_text=_("Varsa kurs görseline tıklanınca oynar."),
    )
    preview_video_key = models.CharField(
        _("tanıtım videosunun gizli anahtarı"), max_length=40, blank=True, help_text=_("Vimeo'da gizli bağlantının h= değeri.")
    )
    preview_video_title = models.CharField(
        _("tanıtım videosunun platformdaki başlığı"),
        max_length=200,
        blank=True,
        help_text=_("Kurs başlığından farklıysa platforma yeniden gönderilir."),
    )
    video_collection_id = models.CharField(
        _("Bunny koleksiyonu"), max_length=40, blank=True, help_text=_("İlk Bunny yüklemesinde kurs adıyla açılır.")
    )
    vimeo_folder_uri = models.CharField(
        _("Vimeo klasörü"), max_length=200, blank=True, help_text=_("İlk Vimeo yüklemesinde kurs adıyla açılır.")
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
    def preview_player(self):
        """Tanıtım videosunun oynatıcı verisi: platform, adres (HLS; Vimeo vermezse gizli bağlantı) ve kapak görseli."""
        if not self.preview_video_id:
            return None
        return video_service.get(self.preview_video_platform).playback(self.preview_video_id, self.preview_video_key)

    @property
    def preview_video_dashboard_url(self):
        if not self.preview_video_id:
            return ""
        return video_service.get(self.preview_video_platform).dashboard_url(self.preview_video_id)

    @property
    def has_preview_video(self):
        return bool(self.preview_video_id)

    @property
    def preview_video_platform_short(self):
        return VideoPlatform(self.preview_video_platform).short_label

    @property
    def latest_preview_upload(self):
        uploads = self.preview_uploads.all()
        return uploads[0] if uploads else None

    @property
    def has_busy_preview_upload(self):
        return self.preview_uploads.filter(status__in=BUSY_UPLOAD_STATUSES).exists()

    @property
    def needs_preview_title_sync(self):
        return bool(self.preview_video_id) and self.preview_video_title != self.title

    def queue_preview_title_sync(self):
        """Kurs başlığı tanıtım videosunun platformdaki başlığından farklıysa kayıt tamamlanınca platformda günceller.

        Ayarlarda başlık güncelleme kapalıysa hiçbir şey yapmaz.
        """
        if not self.needs_preview_title_sync or not SiteSettings.title_sync_enabled():
            return False
        from course.tasks import sync_preview_title

        transaction.on_commit(partial(sync_preview_title.delay, str(self.pk)))
        return True

    def attach_preview_video(self, platform, video_id, video_key, video_title):
        replaced = (self.preview_video_platform, self.preview_video_id)
        self.preview_video_platform = platform
        self.preview_video_id = video_id
        self.preview_video_key = video_key
        self.preview_video_title = video_title
        self.save(
            update_fields=[
                "preview_video_platform",
                "preview_video_id",
                "preview_video_key",
                "preview_video_title",
                "updated_at",
            ]
        )
        # Video işlenirken kurs başlığı değişmiş olabilir; güncel başlık platforma da yazılır.
        self.refresh_from_db(fields=["title"])
        self.queue_preview_title_sync()
        # Eski tanıtım videosu platformdan silinir (yenisi hazır).
        if replaced != (platform, video_id):
            retire_replaced_video(*replaced)

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

    def ensure_video_folder(self, platform):
        """Kursun platformdaki klasörünü (Bunny koleksiyonu / Vimeo klasörü) döner, yoksa açar.

        Aynı anda çalışan yüklemeler tek klasör açsın diye satır kilitlenir.
        """
        service = video_service.get(platform)
        field = service.FOLDER_FIELD
        with transaction.atomic():
            course = Course.objects.select_for_update().get(pk=self.pk)
            if not getattr(course, field):
                setattr(course, field, service.create_folder(course.title))
                course.save(update_fields=[field, "updated_at"])
        setattr(self, field, getattr(course, field))
        return getattr(self, field)

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

    def match_lesson_for_file(self, file_name, lessons=None):
        """Dosyanın (ör. ders notu .md) ait olduğu dersi bulur; (ders, None) ya da (None, sebep) döner.

        Önce dersin videosunun dosya adıyla birebir karşılaştırılır (ek bilgi ve altyazı dosyaları video dosyasıyla aynı
        adla oluşturulur), sonra ders başlığı ya da slug'ıyla (videolar dosya adıyla açıldığı için). Bulunamazsa baştaki
        sıra numarası (ör. "018-014") yalnız tek bir dersle uyuşuyorsa kullanılır.
        """
        if lessons is None:
            lessons = list(Lesson.objects.filter(section__course=self))

        def key(text):
            return unicodedata.normalize("NFC", text).strip().casefold()

        stem = key(Path(file_name).stem)
        by_video = [lesson for lesson in lessons if stem in {key(name) for name in lesson.video_file_stems}]
        if len(by_video) == 1:
            return by_video[0], None
        if len(by_video) > 1:
            return None, _("Birden fazla dersin videosu bu dosya adında.")
        exact = [lesson for lesson in lessons if key(lesson.title) == stem or lesson.slug == slugify_tr(stem)]
        if len(exact) == 1:
            return exact[0], None
        if len(exact) > 1:
            return None, _("Birden fazla ders aynı ada sahip.")
        number = LESSON_FILE_NUMBER.match(stem)
        if number:
            numbered = [
                lesson
                for lesson in lessons
                if (match := LESSON_FILE_NUMBER.match(key(lesson.title))) and match.group(0) == number.group(0)
            ]
            if len(numbered) == 1:
                return numbered[0], None
            if len(numbered) > 1:
                return None, _("Bu numarayla birden fazla ders var; dosya adını ders adıyla aynı yap.")
            # Numara ders başlığında yoksa sıraya bakılır: "001-002" = 1. bölümün 2. dersi.
            positioned = self.lesson_at(number.group(0))
            if positioned is not None:
                return positioned, None
        return None, _("Bu adda ders bulunamadı.")

    def lesson_at(self, number):
        """Sıra numarasıyla ders: "001-002" = 1. bölümün (sıraya göre) 2. dersi; yoksa None. "Genel" ve "Eşleşmeyen dersler"
        sayılmaz (kursa bırakılan video "Genel"i en başa açar, sıra kaymasın)."""
        parts = number.split("-")
        if len(parts) != 2 or min(int(part) for part in parts) < 1:
            return None
        section_no, lesson_no = (int(part) for part in parts)
        sections = self.sections.exclude(slug__in=(GENERAL_SECTION_SLUG, LEFTOVER_SECTION_SLUG)).order_by("sort_order", "created_at")
        sections = list(sections[section_no - 1 : section_no])
        if not sections:
            return None
        lessons = list(sections[0].lessons.order_by("sort_order", "created_at")[lesson_no - 1 : lesson_no])
        return lessons[0] if lessons else None

    def lessons_needing_video_title_sync(self):
        return Lesson.objects.filter(section__course=self).exclude(video_id="").exclude(video_title=F("title"))

    def sync_durations(self):
        """Videosu olan derslerin süresini kendi platformundan günceller; güncellenen ders sayısını döner."""
        updated = 0
        for lesson in self.published_lessons().exclude(video_id=""):
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

    def add_content_lesson(self, title):
        """Video yerine Markdown içerikli ders (ör. form bağlantısı, okuma); taslak olarak bölümün sonuna eklenir."""
        return self.lessons.create(title=title, kind=LessonKind.TEXT, sort_order=self.next_lesson_order())

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
    # Video yönetim panelinden (studio) Celery ile ayarlarda seçili platforma yüklenir; kimlik elle de girilebilir.
    video_platform = models.CharField(
        _("video platformu"), max_length=20, choices=VideoPlatform, default=VideoPlatform.BUNNY
    )
    video_id = models.CharField(_("video kimliği (platformda)"), max_length=40, blank=True)
    video_key = models.CharField(
        _("videonun gizli anahtarı"), max_length=40, blank=True, help_text=_("Vimeo'da gizli bağlantının h= değeri.")
    )
    duration_seconds = models.PositiveIntegerField(
        _("süre (saniye)"), null=True, blank=True, help_text=_("Dosyadan ya da platformdan okunur; elle de girilebilir.")
    )
    video_title = models.CharField(
        _("platformdaki başlık"),
        max_length=250,
        blank=True,
        help_text=_("Ders başlığından farklıysa platforma yeniden gönderilir."),
    )
    # Stüdyoda ders başlığının üstüne gelince gösterilir; yükleme işi kuyruktan temizlense de kalır.
    video_file_name = models.CharField(_("yüklenen dosya adı"), max_length=255, blank=True)
    # Videonun altında "Ek bilgiler" olarak görünür. Kaynak Markdown'dır (HTML de yazılabilir); kaydedilince temizlenmiş
    # HTML'i üretilir, sayfa onu gösterir.
    extra_content = models.TextField(
        _("ek içerik (Markdown)"), blank=True, help_text=_("Videonun altında “Ek bilgiler” olarak görünür.")
    )
    extra_content_html = models.TextField(_("ek içerik (HTML)"), blank=True, editable=False)
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
    def video_service(self):
        return video_service.get(self.video_platform)

    @property
    def player(self):
        """Oynatıcı verisi: platform, adres (HLS; Vimeo vermezse gizli bağlantı) ve kapak görseli."""
        return self.video_service.playback(self.video_id, self.video_key) if self.video_id else None

    @property
    def video_dashboard_url(self):
        return self.video_service.dashboard_url(self.video_id) if self.video_id else ""

    @property
    def duration_minutes(self):
        return ceil_minutes(self.duration_seconds)

    @property
    def duration_display(self):
        return clock(self.duration_seconds) if self.duration_seconds else ""

    def sync_duration(self):
        self.duration_seconds = self.video_service.fetch_duration(self.video_id)
        self.save(update_fields=["duration_seconds", "updated_at"])
        return self.duration_seconds

    @property
    def is_video(self):
        return self.kind == LessonKind.VIDEO

    @property
    def video_platform_short(self):
        return VideoPlatform(self.video_platform).short_label

    @property
    def latest_upload(self):
        # video_uploads önceden yüklendiyse (prefetch) ek sorgu yapılmaz; sıralama en yeni önce.
        uploads = self.video_uploads.all()
        return uploads[0] if uploads else None

    @property
    def video_file_stems(self):
        """Videonun dosya adı (uzantısız); ek bilgi ve altyazı dosyaları bu adla oluşturulur. Dosya adı tutulmadan önce
        yüklenen derslerde platformdaki video başlığı dosya adından geldiği için o da denenir (ders adına çevrilmediyse)."""
        name = Path(self.video_file_name)
        # Ek bilgi / altyazı dosyasından öğrenilen ad uzantısız kaydedilir; yalnız video uzantısı atılır ("react-18.x" kalsın).
        stems = [name.stem if name.suffix.lower() in VIDEO_EXTENSIONS else name.name] if self.video_file_name else []
        if self.video_title and self.video_title != self.title:
            stems.append(self.video_title)
        return stems

    def learn_video_file_name(self, file_name):
        """Ek bilgi ve altyazı dosyaları videoyla aynı adla oluşturulur: dosya adı bilinmeyen videolu derse eşleşen dosyanın
        adı (uzantısız) yazılır, sonraki yüklemeler doğrudan adla eşleşir. Ad yazıldıysa True döner."""
        if not self.video_id or self.video_file_name:
            return False
        self.video_file_name = Path(file_name).stem[:255]
        self.save(update_fields=["video_file_name", "updated_at"])
        return True

    @property
    def video_file_label(self):
        """Videonun yüklendiği dosyanın adı; eski derslerde kuyrukta duran son yüklemeden okunur."""
        if self.video_file_name:
            return self.video_file_name
        upload = self.latest_upload
        return upload.original_name if upload else ""

    @property
    def has_busy_upload(self):
        return self.video_uploads.filter(status__in=BUSY_UPLOAD_STATUSES).exists()

    @property
    def has_busy_subtitles(self):
        return any(subtitle.is_busy for subtitle in self.subtitles.all())

    @property
    def needs_video_title_sync(self):
        return bool(self.video_id) and self.video_title != self.title

    def queue_video_title_sync(self):
        """Başlık platformdakinden farklıysa kayıt tamamlanınca platformda güncellenmek üzere sıraya alır.

        Ayarlarda başlık güncelleme kapalıysa hiçbir şey yapmaz.
        """
        if not self.needs_video_title_sync or not SiteSettings.title_sync_enabled():
            return False
        from course.tasks import sync_video_title

        transaction.on_commit(partial(sync_video_title.delay, str(self.pk)))
        return True

    def slug_siblings(self):
        return Lesson.objects.filter(section_id=self.section_id)

    @property
    def has_extra_content(self):
        return bool(self.extra_content_html)

    @property
    def extra_content_words(self):
        return len(self.extra_content.split())

    def set_extra_content(self, text):
        """Ek içeriği değiştirir (boşsa kaldırır); HTML'i yeniden üretilir."""
        self.extra_content = text.replace("\r\n", "\n").strip()
        self.save(update_fields=["extra_content", "updated_at"])

    def save(self, *args, **kwargs):
        # Admin'den düzenlenen kaynakla HTML her zaman uyumlu kalır.
        update_fields = kwargs.get("update_fields")
        if update_fields is None or "extra_content" in update_fields:
            self.extra_content_html = render_markdown(self.extra_content)
            if update_fields is not None:
                kwargs["update_fields"] = {*update_fields, "extra_content_html"}
        super().save(*args, **kwargs)

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
        self.set_preview(not self.is_preview)

    @property
    def kind_choices(self):
        return LessonKind.choices

    def set_kind(self, kind):
        """Ders türünü değiştirir (ör. video → metin). Varsa videosu silinmez; video türüne dönünce yine oynar."""
        if kind not in LessonKind.values:
            raise ValueError(kind)
        self.kind = kind
        self.save(update_fields=["kind", "updated_at"])

    def set_preview(self, value):
        self.is_preview = value
        self.save(update_fields=["is_preview", "updated_at"])

    def remove(self, delete_remote=False):
        """Dersi siler. Süren yüklemeler iptal edilir, sunucudaki dosyalar silinir.

        `delete_remote` ise dersin platformdaki videosu da (kayıt tamamlanınca) silinir; değilse platformda kalır.
        """
        from course.tasks import delete_remote_video

        for upload in self.video_uploads.all():
            upload.cancel()
            upload.discard_file()
        for subtitle in self.subtitles.all():
            subtitle.file.delete(save=False)
        if delete_remote and self.video_id:
            transaction.on_commit(partial(delete_remote_video.delay, self.video_id, self.video_platform))
        self.delete()

    def attach_video(self, platform, video_id, video_key, duration_seconds, video_title, file_name=""):
        replaced = (self.video_platform, self.video_id)
        self.video_platform = platform
        self.video_id = video_id
        self.video_key = video_key
        self.duration_seconds = duration_seconds or None
        self.video_title = video_title
        self.video_file_name = file_name
        self.save(
            update_fields=[
                "video_platform",
                "video_id",
                "video_key",
                "duration_seconds",
                "video_title",
                "video_file_name",
                "updated_at",
            ]
        )
        # Video işlenirken ders adı değişmiş olabilir (o sırada senkron kuyruğa alınamaz); güncel ad platforma da yazılır.
        self.refresh_from_db(fields=["title"])
        self.queue_video_title_sync()
        # Altyazılar videoya bağlıdır; yeni video gelince hepsi yeniden gönderilir.
        for subtitle in self.subtitles.all():
            subtitle.remote_language = ""
            subtitle.schedule()
        # Eski video (altyazılarıyla birlikte) platformdan silinir; yenisi hazır olduğu için ders hiç videosuz kalmaz.
        if replaced != (platform, video_id):
            retire_replaced_video(*replaced)


class VideoUploadStatus(models.TextChoices):
    QUEUED = "queued", _("Sırada")
    UPLOADING = "uploading", _("Platforma gönderiliyor")
    PROCESSING = "processing", _("Platformda işleniyor")
    READY = "ready", _("Hazır")
    FAILED = "failed", _("Hata")
    CANCELED = "canceled", _("İptal edildi")


BUSY_UPLOAD_STATUSES = (VideoUploadStatus.QUEUED, VideoUploadStatus.UPLOADING, VideoUploadStatus.PROCESSING)
FINISHED_UPLOAD_STATUSES = (VideoUploadStatus.READY, VideoUploadStatus.FAILED, VideoUploadStatus.CANCELED)
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
    """Videonun platforma (Bunny Stream / Vimeo) yüklenme işi; hedef ya bir ders ya da bir kursun tanıtım videosudur.

    Platform iş açılırken ayarlardan alınır ve yeniden denemede değişmez. Dosya önce sunucuya gelir; platform
    işlemeyi bitirince silinir, o zamana kadar hata olursa yeniden gönderilebilir.
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
    platform = models.CharField(_("platform"), max_length=20, choices=VideoPlatform, default=VideoPlatform.BUNNY)
    # Ders dosya adları uzun olabilir (ör. "..._without_silence.mp4"); varsayılan 100 karakter yetmez.
    file = models.FileField(
        _("dosya"),
        upload_to="video_uploads/%Y/%m/",
        max_length=255,
        blank=True,
        help_text=_("Platform videoyu işleyince silinir."),
    )
    original_name = models.CharField(_("dosya adı"), max_length=255)
    size = models.PositiveBigIntegerField(_("boyut (bayt)"), default=0)
    duration_seconds = models.PositiveIntegerField(
        _("süre (saniye)"), null=True, blank=True, help_text=_("Yüklenen dosyadan okunur; platform işleyince onun süresi esas alınır.")
    )
    status = models.CharField(
        _("durum"), max_length=20, choices=VideoUploadStatus, default=VideoUploadStatus.QUEUED, db_index=True
    )
    progress = models.PositiveSmallIntegerField(_("ilerleme (%)"), default=0)
    video_id = models.CharField(_("video kimliği (platformda)"), max_length=40, blank=True)
    video_title = models.CharField(_("platforma gönderilen başlık"), max_length=250, blank=True)
    service_state = models.CharField(_("platformdaki durum"), max_length=30, blank=True)
    encode_progress = models.PositiveSmallIntegerField(_("platformdaki işleme ilerlemesi (%)"), default=0)
    error = models.TextField(_("hata"), blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("yükleyen"),
    )
    sent_at = models.DateTimeField(_("platforma ulaştı"), null=True, blank=True)
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
    def video_service(self):
        return video_service.get(self.platform)

    @property
    def video_dashboard_url(self):
        return self.video_service.dashboard_url(self.video_id) if self.video_id else ""

    @property
    def video_name(self):
        """Platformdaki video adı: dersin ya da kursun Türkçe başlığı."""
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
    def service_state_label(self):
        label = self.video_service.STATE_LABELS.get(self.service_state, "")
        if label and self.encode_progress:
            return f"{label} · %{self.encode_progress}"
        return label

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
        """Süreyi dosyadan okur; videosu olmayan derse hemen yazılır (video değiştiriliyorsa platform hazır olunca)."""
        self.duration_seconds = video_file_seconds(self.file.path)
        self.save(update_fields=["duration_seconds", "updated_at"])
        if self.duration_seconds and self.lesson_id and not self.lesson.video_id:
            self.lesson.duration_seconds = self.duration_seconds
            self.lesson.save(update_fields=["duration_seconds", "updated_at"])

    def queue(self):
        from course.tasks import upload_video

        transaction.on_commit(partial(upload_video.delay, str(self.pk)))

    # Panel eylemleri

    def retry(self):
        """Hatalı, iptal edilmiş ya da takılı yüklemeyi aynı dosyayla baştan sıraya alır; platformda yeni kayıt açılır."""
        if not self.can_retry or self.has_other_busy_upload():
            return False
        statuses = (VideoUploadStatus.FAILED, VideoUploadStatus.CANCELED, VideoUploadStatus.QUEUED)
        moved = self._move(
            statuses,
            status=VideoUploadStatus.QUEUED,
            progress=0,
            video_id="",
            service_state="",
            encode_progress=0,
            error="",
            sent_at=None,
            finished_at=None,
        )
        if moved:
            self.queue()
        return moved

    def cancel(self):
        """Süren yüklemeyi durdurur. Platformda açılmış (henüz derse bağlanmamış) video silinir; dosya yeniden başlatmak için kalır."""
        if not self._move(BUSY_UPLOAD_STATUSES, status=VideoUploadStatus.CANCELED, finished_at=timezone.now()):
            return False
        # İşçi bu arada platformda kayıt açmış olabilir; güncel kimlik okunur.
        self.refresh_from_db(fields=["video_id"])
        if self.video_id:
            from course.tasks import delete_remote_video

            transaction.on_commit(partial(delete_remote_video.delay, self.video_id, self.platform))
        return True

    def discard(self):
        """Biten işi kuyruktan kaldırır; yerel dosya da silinir. Derse bağlanmış video etkilenmez."""
        if not self.can_discard:
            return False
        self.keep_file_name()
        self.discard_file()
        self.delete()
        return True

    def keep_file_name(self):
        """Bu işin videosu derste duruyorsa dosya adı derse yazılır; iş silinince ad kaybolmasın (alan öncesi dersler)."""
        if self.lesson_id and self.video_id:
            Lesson.objects.filter(pk=self.lesson_id, video_id=self.video_id, video_file_name="").update(
                video_file_name=self.original_name
            )

    # İşçi geçişleri (Celery)

    def mark_uploading(self):
        return self._move((VideoUploadStatus.QUEUED,), status=VideoUploadStatus.UPLOADING, progress=0)

    def mark_created(self, video_id, video_title):
        if not self._move((VideoUploadStatus.UPLOADING,), video_id=video_id, video_title=video_title):
            raise UploadCanceled

    def set_progress(self, sent, total):
        """Her parçadan sonra çağrılır; yükleme iptal edildiyse UploadCanceled ile gönderimi durdurur."""
        percent = min(100, sent * 100 // total) if total else 100
        if not self._move((VideoUploadStatus.UPLOADING,), progress=percent):
            raise UploadCanceled

    def mark_sent(self):
        """Dosya platforma ulaştı, işlemesi beklenir. Yerel kopya, işleme başarısız olursa yeniden gönderilmek üzere kalır."""
        return self._move(
            (VideoUploadStatus.UPLOADING,), status=VideoUploadStatus.PROCESSING, progress=100, sent_at=timezone.now()
        )

    def set_service_state(self, status):
        if (status.state, status.progress) != (self.service_state, self.encode_progress):
            self._move((VideoUploadStatus.PROCESSING,), service_state=status.state, encode_progress=status.progress)

    def mark_ready(self, status):
        moved = self._move(
            (VideoUploadStatus.PROCESSING,),
            status=VideoUploadStatus.READY,
            service_state=status.state,
            encode_progress=100,
            finished_at=timezone.now(),
        )
        if not moved:
            return False
        self.discard_file()
        VideoUpload.objects.filter(pk=self.pk).update(file="")
        if self.is_preview:
            self.course.attach_preview_video(self.platform, self.video_id, status.key, self.video_title)
        else:
            duration = status.duration or self.duration_seconds
            self.lesson.attach_video(
                self.platform, self.video_id, status.key, duration, self.video_title, self.original_name
            )
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
    READY = "ready", _("Gönderildi")
    FAILED = "failed", _("Hata")


SUBTITLE_EXTENSIONS = (".srt", ".vtt")


class LessonSubtitle(BaseModel):
    """Dersin altyazı dosyası. Dosya saklanır; video değişince yeni videoya yeniden gönderilir."""

    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name="subtitles", verbose_name=_("ders"))
    language = models.CharField(_("dil"), max_length=10, choices=SubtitleLanguage)
    file = models.FileField(_("dosya"), upload_to="subtitles/%Y/%m/", max_length=255)
    status = models.CharField(
        _("durum"), max_length=20, choices=SubtitleStatus, default=SubtitleStatus.QUEUED, db_index=True
    )
    # Platformda altyazı videonun ve dil kodunun altında durur; gönderilmişse dil kodu tutulur.
    remote_language = models.CharField(_("platformdaki altyazı dili"), max_length=10, blank=True)
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

    @classmethod
    def attach(cls, lesson, language, file):
        """Dersin bu dildeki altyazısı olur; aynı dilde altyazı varsa dosyası değiştirilir, platformdakinin yerine geçer."""
        subtitle = cls.objects.filter(lesson=lesson, language=language).first()
        if subtitle is None:
            subtitle = cls(lesson=lesson, language=language)
        elif subtitle.file:
            subtitle.file.delete(save=False)
        subtitle.file = file
        subtitle.save()
        subtitle.schedule()
        return subtitle

    def schedule(self):
        """Videosu hazırsa platforma gönderilmek üzere sıraya alır, değilse video hazır olunca gönderilir."""
        from course.tasks import upload_subtitle

        ready = self.lesson.video_id and not self.lesson.has_busy_upload
        self.status = SubtitleStatus.QUEUED if ready else SubtitleStatus.WAITING
        self.error = ""
        self.save(update_fields=["status", "error", "remote_language", "updated_at"])
        if ready:
            transaction.on_commit(partial(upload_subtitle.delay, str(self.pk)))

    def remove(self):
        """Kaydı ve dosyasını siler; platformdaki altyazı kayıt tamamlanınca kaldırılır."""
        from course.tasks import delete_remote_caption

        lesson = self.lesson
        if self.remote_language and lesson.video_id:
            transaction.on_commit(
                partial(delete_remote_caption.delay, lesson.video_id, self.remote_language, lesson.video_platform)
            )
        self.file.delete(save=False)
        self.delete()

    def mark_waiting(self):
        self.status = SubtitleStatus.WAITING
        self.save(update_fields=["status", "updated_at"])

    def mark_ready(self, language):
        self.status = SubtitleStatus.READY
        self.remote_language = language
        self.save(update_fields=["status", "remote_language", "updated_at"])

    def mark_failed(self, error):
        self.status = SubtitleStatus.FAILED
        self.error = error
        self.save(update_fields=["status", "error", "updated_at"])


class ReviewSource(models.TextChoices):
    IMPORTED = "imported", _("Dışarıdan aktarıldı")
    USER = "user", _("Kullanıcı yorumu")


REVIEW_RATINGS = [(value, "★" * value) for value in range(1, 6)]
# Stüdyoda yorum durumu: yayında = onaylı sürüm sitede görünür, taslak = henüz onaylanmadı, arşiv = gizlendi.
REVIEW_STATUS_LABELS = {Status.DRAFT: _("Onay bekliyor"), Status.PUBLISHED: _("Yayında"), Status.ARCHIVED: _("Gizli")}


def rating_summary(average, count):
    """Ortalama (bir ondalık), sayı ve dolu yıldız sayısı."""
    average = round(average, 1) if average else None
    return dict(average=average, count=count, stars=round(average) if average else 0)


class ReviewQuerySet(StatusQuerySet):
    def visible(self):
        """Sitede görünen: onaylanmış ve gizlenmemiş. Sitede onaylı sürüm (approved_*) gösterilir."""
        return self.filter(status=Status.PUBLISHED, approved_at__isnull=False)

    def with_text(self):
        return self.visible().exclude(approved_text="")

    def for_home(self):
        return self.with_text().filter(show_on_home=True).select_related("user", "course")

    def featured_for(self, course):
        return self.with_text().filter(course=course, featured=True).select_related("user", "course")

    def all_for(self, course=None):
        reviews = self.with_text().select_related("user", "course")
        return reviews.filter(course=course) if course is not None else reviews

    def course_counts(self):
        """Sitede yorumu olan kurslar ve yorum sayıları ("Tüm yorumlar" penceresindeki kurs filtresi)."""
        return (
            self.with_text()
            .values("course__slug", "course__short_title")
            .annotate(count=Count("pk"))
            .order_by("course__short_title")
        )

    def awaiting(self):
        """Stüdyoda onay bekleyen: yeni ya da onaydan sonra değiştirilmiş yorumlar."""
        return self.filter(needs_review=True).exclude(status=Status.ARCHIVED)

    def rating_summary(self):
        """Onaylı puanların ortalaması ve sayısı."""
        rated = self.visible().filter(approved_rating__isnull=False)
        data = rated.aggregate(average=models.Avg("approved_rating"), count=Count("pk"))
        return rating_summary(data["average"], data["count"])

    def ordered(self):
        return self.order_by("sort_order", "-approved_written_at", "id")


class Review(BaseModel, BaseStatus, BaseSortOrder):
    """Kurs değerlendirmesi: puan (1-5) ve isteğe bağlı yorum.

    Kursu alan kullanıcı yazar; her değişiklik yeniden onaya gider. Sitede yalnız onaylı sürüm (approved_*) görünür,
    yani onaylı yorum değiştirildiğinde yeni hali onaylanana kadar eskisi kalır. Eski (dışarıdan aktarılan) yorumlarda
    kullanıcı boştur, ad elle yazılır ve stüdyodan eklenince doğrudan onaylanabilir.
    """

    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="reviews", verbose_name=_("kurs"))
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviews",
        verbose_name=_("kullanıcı"),
    )
    author_name = models.CharField(_("yazan"), max_length=120, blank=True, help_text=_("Eski yorumlarda elle yazılır."))
    rating = models.PositiveSmallIntegerField(
        _("puan"), null=True, blank=True, choices=REVIEW_RATINGS, validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    text = models.TextField(_("yorum"), blank=True)
    written_at = models.DateTimeField(_("yorum tarihi"), default=timezone.now)
    source = models.CharField(_("kaynak"), max_length=20, choices=ReviewSource, default=ReviewSource.IMPORTED)
    # Sitede görünen (onaylanmış) sürüm
    approved_rating = models.PositiveSmallIntegerField(_("onaylı puan"), null=True, blank=True)
    approved_text = models.TextField(_("onaylı yorum"), blank=True)
    approved_written_at = models.DateTimeField(_("onaylı yorumun tarihi"), null=True, blank=True)
    approved_at = models.DateTimeField(_("onay tarihi"), null=True, blank=True)
    needs_review = models.BooleanField(_("onay bekliyor"), default=True, db_index=True)
    featured = models.BooleanField(_("kurs sayfasında öne çıkar"), default=False)
    show_on_home = models.BooleanField(_("ana sayfada göster"), default=False)

    objects = ReviewQuerySet.as_manager()

    class Meta:
        verbose_name = _("yorum")
        verbose_name_plural = _("yorumlar")
        ordering = ("sort_order", "-written_at")
        constraints = [
            models.UniqueConstraint(
                fields=("course", "user"), condition=Q(user__isnull=False), name="review_one_per_user_course"
            ),
        ]

    def __str__(self):
        return f"{self.display_name} · {self.course.short_title}"

    @property
    def display_name(self):
        """Elle yazılan ad; yoksa "Ad S." ya da ad bilgisi yoksa e-postanın ilk üç harfi (ilki büyük)."""
        if self.author_name:
            return self.author_name
        if not self.user_id:
            return ""
        first, last = self.user.first_name.strip(), self.user.last_name.strip()
        if first:
            return f"{first} {last[0].upper()}." if last else first
        return self.user.email[:3].capitalize()

    @property
    def initial(self):
        return self.display_name[:1].upper()

    @property
    def status_label(self):
        return REVIEW_STATUS_LABELS[self.status]

    @property
    def is_visible(self):
        return self.status == Status.PUBLISHED and self.approved_at is not None

    @property
    def has_pending_changes(self):
        """Onaylı sürümü sitede görünürken değiştirildi; yeni hali onay bekliyor."""
        return self.is_visible and self.needs_review

    def submit(self, rating, text):
        """Kullanıcı puanı ya da yorumu yazdı/değiştirdi: yeniden onaya gider. Onaylı sürüm sitede kalır."""
        self.rating = rating
        self.text = text.strip()
        self.written_at = timezone.now()
        self.needs_review = True
        self.source = ReviewSource.USER
        self.save()

    def approve(self):
        """Son hali onaylanır ve sitede görünür."""
        self.approved_rating = self.rating
        self.approved_text = self.text
        self.approved_written_at = self.written_at
        self.approved_at = timezone.now()
        self.needs_review = False
        self.status = Status.PUBLISHED
        self.save()

    def hide(self):
        """Yorum sitede gösterilmez (onaylı sürüm de)."""
        self.status = Status.ARCHIVED
        self.needs_review = False
        self.save(update_fields=["status", "needs_review", "updated_at"])

    def set_featured(self, value):
        self.featured = value
        self.save(update_fields=["featured", "updated_at"])

    def toggle_featured(self):
        self.set_featured(not self.featured)

    def set_home(self, value):
        self.show_on_home = value
        self.save(update_fields=["show_on_home", "updated_at"])

    def toggle_home(self):
        self.set_home(not self.show_on_home)

    def card(self):
        """Sitedeki yorum kartının verisi (onaylı sürüm)."""
        return dict(
            name=self.display_name,
            initial=self.initial,
            text=self.approved_text,
            rating=self.approved_rating,
            date=self.approved_written_at,
            course=self.course.short_title,
        )


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
