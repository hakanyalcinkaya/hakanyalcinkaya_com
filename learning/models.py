from django.conf import settings
from django.db import models
from django.db.models import Case, Count, IntegerField, OuterRef, Subquery, Value, When
from django.db.models.functions import Cast, Coalesce, Round
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from core.models import BaseModel, Status
from course.models import SubtitleLanguage


class EnrollmentSource(models.TextChoices):
    PURCHASE = "purchase", _("Satın alma")
    BUNDLE = "bundle", _("Paket satın alma")
    MANUAL = "manual", _("Manuel")
    GIFT = "gift", _("Hediye")
    IMPORTED = "imported", _("Eski platformdan aktarıldı")


class EnrollmentQuerySet(models.QuerySet):
    def for_user(self, user):
        if not user.is_authenticated:
            return self.none()
        return self.filter(user=user)

    def in_progress(self):
        return self.filter(completed_at__isnull=True)

    def finished(self):
        return self.filter(completed_at__isnull=False)

    def has_access(self, user, course):
        """Kullanıcının kursa erişimi var mı (satın alma, paket, hediye, manuel ya da eski platformdan aktarım)."""
        return self.for_user(user).filter(course=course).exists()

    def with_progress(self):
        """completed_total, lesson_total ve progress (yayındaki derslere göre %0-100) ekler; filtrelenip sıralanabilir."""
        from course.models import Lesson

        published = dict(status=Status.PUBLISHED, section__status=Status.PUBLISHED)
        lessons = (
            Lesson.objects.filter(section__course=OuterRef("course"), **published)
            .order_by()
            .values("section__course")
            .annotate(n=Count("pk"))
            .values("n")
        )
        done = (
            LessonProgress.objects.filter(
                user=OuterRef("user"),
                lesson__section__course=OuterRef("course"),
                lesson__status=Status.PUBLISHED,
                lesson__section__status=Status.PUBLISHED,
                completed_at__isnull=False,
            )
            .order_by()
            .values("user")
            .annotate(n=Count("pk"))
            .values("n")
        )
        return self.annotate(
            lesson_total=Coalesce(Subquery(lessons, output_field=IntegerField()), 0),
            completed_total=Coalesce(Subquery(done, output_field=IntegerField()), 0),
        ).annotate(
            progress=Case(
                When(lesson_total=0, then=Value(0)),
                default=Cast(Round(Cast("completed_total", models.FloatField()) * 100.0 / Cast("lesson_total", models.FloatField())), IntegerField()),
                output_field=IntegerField(),
            )
        )


class Enrollment(BaseModel):
    """Kullanıcının bir kursa erişimi. Satın alma, paket, hediye ya da manuel olarak açılır."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="enrollments", verbose_name=_("kullanıcı"))
    course = models.ForeignKey("course.Course", on_delete=models.PROTECT, related_name="enrollments", verbose_name=_("kurs"))
    source = models.CharField(_("kaynak"), max_length=20, choices=EnrollmentSource, default=EnrollmentSource.PURCHASE)
    order = models.ForeignKey(
        "order.Order", on_delete=models.SET_NULL, null=True, blank=True, related_name="enrollments", verbose_name=_("sipariş")
    )
    bundle = models.ForeignKey(
        "course.Bundle", on_delete=models.SET_NULL, null=True, blank=True, related_name="enrollments", verbose_name=_("paket")
    )
    last_lesson = models.ForeignKey(
        "course.Lesson", on_delete=models.SET_NULL, null=True, blank=True, related_name="+", verbose_name=_("son izlenen ders")
    )
    last_watched_at = models.DateTimeField(_("son izleme"), null=True, blank=True)
    completed_at = models.DateTimeField(_("tamamlanma"), null=True, blank=True)

    objects = EnrollmentQuerySet.as_manager()

    class Meta:
        verbose_name = _("kurs kaydı")
        verbose_name_plural = _("kurs kayıtları")
        ordering = ("-last_watched_at", "-created_at")
        constraints = [models.UniqueConstraint(fields=("user", "course"), name="enrollment_unique_user_course")]

    def __str__(self):
        return f"{self.user} · {self.course}"

    @property
    def is_completed(self):
        return self.completed_at is not None

    def completed_lesson_count(self):
        return LessonProgress.objects.filter(
            user=self.user, lesson__in=self.course.published_lessons(), completed_at__isnull=False
        ).count()

    @property
    def progress_percent(self):
        total = self.course.published_lessons().count()
        return round(self.completed_lesson_count() / total * 100) if total else 0

    def continue_lesson(self):
        """Kaldığı ders; yoksa tamamlanmamış ilk ders, o da yoksa ilk ders."""
        if self.last_lesson_id:
            return self.last_lesson
        lessons = self.course.published_lessons().order_by("section__sort_order", "sort_order")
        done = LessonProgress.objects.filter(user=self.user, completed_at__isnull=False).values("lesson")
        return lessons.exclude(pk__in=done).first() or lessons.first()

    def record_visit(self, lesson):
        self.last_lesson = lesson
        self.last_watched_at = timezone.now()
        self.save(update_fields=["last_lesson", "last_watched_at", "updated_at"])


class LessonProgress(BaseModel):
    """Ders ilerlemesi. Oynatıcı izlenen saniyeyi düzenli aralıklarla yazar (TODO.md: her 5 sn)."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="lesson_progress", verbose_name=_("kullanıcı"))
    lesson = models.ForeignKey("course.Lesson", on_delete=models.CASCADE, related_name="progress", verbose_name=_("ders"))
    position_seconds = models.PositiveIntegerField(_("kaldığı saniye"), default=0)
    completed_at = models.DateTimeField(_("tamamlanma"), null=True, blank=True)

    class Meta:
        verbose_name = _("ders ilerlemesi")
        verbose_name_plural = _("ders ilerlemeleri")
        constraints = [models.UniqueConstraint(fields=("user", "lesson"), name="lesson_progress_unique_user_lesson")]

    def __str__(self):
        return f"{self.user} · {self.lesson}"

    @property
    def is_completed(self):
        return self.completed_at is not None

    def mark_complete(self):
        self.completed_at = self.completed_at or timezone.now()
        self.save(update_fields=["completed_at", "updated_at"])

    def mark_incomplete(self):
        self.completed_at = None
        self.save(update_fields=["completed_at", "updated_at"])

    @classmethod
    def set_completed(cls, user, lesson, done):
        """Dersi tamamlandı ya da tamamlanmadı olarak işaretler; kaydı döner."""
        progress = cls.objects.get_or_create(user=user, lesson=lesson)[0]
        if done:
            progress.mark_complete()
        else:
            progress.mark_incomplete()
        return progress

    @classmethod
    def completed_lesson_ids(cls, user, lessons):
        if not user.is_authenticated:
            return set()
        return set(
            cls.objects.filter(user=user, lesson__in=lessons, completed_at__isnull=False).values_list("lesson_id", flat=True)
        )

    def record_position(self, seconds):
        self.position_seconds = max(int(seconds), 0)
        self.save(update_fields=["position_seconds", "updated_at"])


class Note(BaseModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notes", verbose_name=_("kullanıcı"))
    course = models.ForeignKey("course.Course", on_delete=models.CASCADE, related_name="notes", verbose_name=_("kurs"))
    lesson = models.ForeignKey(
        "course.Lesson",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="notes",
        verbose_name=_("ders"),
        help_text=_("Boşsa not kursun geneline aittir."),
    )
    text = models.TextField(_("not"))

    class Meta:
        verbose_name = _("not")
        verbose_name_plural = _("notlar")
        ordering = ("-created_at",)

    def __str__(self):
        return self.text[:60]

    @property
    def scope_label(self):
        return _("Bu ders") if self.lesson_id else _("Kurs geneli")


class FavoriteQuerySet(models.QuerySet):
    def for_user(self, user):
        if not user.is_authenticated:
            return self.none()
        return self.filter(user=user)

    def for_library(self):
        """Kurslarım sayfası: kurs kurs, müfredat sırasıyla."""
        return self.select_related("lesson__section__course").order_by(
            "lesson__section__course__title", "lesson__section__sort_order", "lesson__sort_order", "id"
        )


class Favorite(BaseModel):
    """Öğrencinin favorilerine aldığı ders (video); Kurslarım sayfasında kurs bazında listelenir."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="favorites", verbose_name=_("kullanıcı"))
    lesson = models.ForeignKey("course.Lesson", on_delete=models.CASCADE, related_name="favorites", verbose_name=_("ders"))

    objects = FavoriteQuerySet.as_manager()

    class Meta:
        verbose_name = _("favori")
        verbose_name_plural = _("favoriler")
        ordering = ("-created_at",)
        constraints = [models.UniqueConstraint(fields=("user", "lesson"), name="favorite_unique_user_lesson")]

    def __str__(self):
        return f"{self.user} · {self.lesson}"

    @classmethod
    def is_favorite(cls, user, lesson):
        return user.is_authenticated and cls.objects.filter(user=user, lesson=lesson).exists()

    @classmethod
    def toggle(cls, user, lesson):
        """Favorideyse çıkarır, değilse ekler; yeni durumu (favoride mi) döner."""
        if cls.objects.filter(user=user, lesson=lesson).delete()[0]:
            return False
        cls.objects.get_or_create(user=user, lesson=lesson)
        return True


class PlaybackRate(models.TextChoices):
    SLOWEST = "0.5", "0.5×"
    SLOW = "0.75", "0.75×"
    NORMAL = "1", _("Normal (1×)")
    FAST = "1.25", "1.25×"
    FASTER = "1.5", "1.5×"
    FASTEST = "1.75", "1.75×"
    DOUBLE = "2", "2×"


class VideoQuality(models.TextChoices):
    AUTO = "auto", _("Otomatik (bağlantıya göre)")
    Q360 = "360", "360p"
    Q480 = "480", "480p"
    Q720 = "720", "720p"
    Q1080 = "1080", "1080p"
    HIGHEST = "highest", _("En yüksek")


class PlayerPreference(BaseModel):
    """Kullanıcının video oynatma tercihleri. Hesap ayarlarından seçilir; oynatıcıda hız, kalite ya da altyazı
    değiştirilince de kendiliğinden kaydedilir ve bir sonraki videoda uygulanır."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="player_preference", verbose_name=_("kullanıcı")
    )
    playback_rate = models.CharField(_("oynatma hızı"), max_length=5, choices=PlaybackRate, default=PlaybackRate.NORMAL)
    quality = models.CharField(_("video kalitesi"), max_length=10, choices=VideoQuality, default=VideoQuality.Q720)
    subtitles_enabled = models.BooleanField(_("altyazı açık"), default=False)
    subtitle_language = models.CharField(
        _("altyazı dili"), max_length=10, choices=SubtitleLanguage, default=SubtitleLanguage.TR
    )
    fullscreen_on_play = models.BooleanField(_("oynatınca tam ekran"), default=False)

    class Meta:
        verbose_name = _("oynatıcı tercihi")
        verbose_name_plural = _("oynatıcı tercihleri")

    def __str__(self):
        return str(self.user)

    @classmethod
    def for_user(cls, user):
        """Kayıtlı tercih ya da varsayılanlar (kaydedilmemiş)."""
        if not user.is_authenticated:
            return cls()
        return cls.objects.filter(user=user).first() or cls(user=user)

    def player_options(self):
        """Oynatıcıya (site.js) verilen tercihler."""
        return {
            "rate": float(self.playback_rate),
            "quality": self.quality if self.quality in (VideoQuality.AUTO, VideoQuality.HIGHEST) else int(self.quality),
            "subtitles": self.subtitles_enabled,
            "subtitleLanguage": self.subtitle_language,
            "fullscreen": self.fullscreen_on_play,
        }
