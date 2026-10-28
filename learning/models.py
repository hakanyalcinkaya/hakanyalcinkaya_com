from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from core.models import BaseModel


class EnrollmentSource(models.TextChoices):
    PURCHASE = "purchase", _("Satın alma")
    BUNDLE = "bundle", _("Paket satın alma")
    MANUAL = "manual", _("Manuel")
    GIFT = "gift", _("Hediye")


class EnrollmentQuerySet(models.QuerySet):
    def for_user(self, user):
        if not user.is_authenticated:
            return self.none()
        return self.filter(user=user)

    def in_progress(self):
        return self.filter(completed_at__isnull=True)

    def finished(self):
        return self.filter(completed_at__isnull=False)


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
