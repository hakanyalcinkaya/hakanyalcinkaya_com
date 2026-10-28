import uuid

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class BaseUUID(models.Model):
    """Birincil anahtar UUID4; sıralı tam sayı dışarıya kayıt sayısı sızdırmaz."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class BaseCreatedAtUpdatedAt(models.Model):
    created_at = models.DateTimeField(_("oluşturulma"), auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(_("güncellenme"), auto_now=True)

    class Meta:
        abstract = True


class BaseModel(BaseUUID, BaseCreatedAtUpdatedAt):
    """Projedeki modellerin ortak temeli: UUID anahtar ve zaman damgaları."""

    class Meta:
        abstract = True


class Status(models.TextChoices):
    DRAFT = "draft", _("Taslak")
    PUBLISHED = "published", _("Yayında")
    ARCHIVED = "archived", _("Arşiv")


class StatusQuerySet(models.QuerySet):
    def published(self):
        return self.filter(status=Status.PUBLISHED)


class BaseStatus(models.Model):
    status = models.CharField(_("durum"), max_length=20, choices=Status, default=Status.DRAFT, db_index=True)
    published_at = models.DateTimeField(_("yayın tarihi"), null=True, blank=True)

    objects = StatusQuerySet.as_manager()

    class Meta:
        abstract = True

    @property
    def is_published(self):
        return self.status == Status.PUBLISHED

    def publish(self, save=True):
        self.status = Status.PUBLISHED
        if self.published_at is None:
            self.published_at = timezone.now()
        if save:
            self.save(update_fields=["status", "published_at"])

    def archive(self, save=True):
        self.status = Status.ARCHIVED
        if save:
            self.save(update_fields=["status"])

    def make_draft(self, save=True):
        self.status = Status.DRAFT
        if save:
            self.save(update_fields=["status"])

    def toggle_published(self):
        """Yayındaysa taslağa, değilse yayına alır."""
        if self.is_published:
            self.make_draft()
        else:
            self.publish()

    def save(self, *args, **kwargs):
        # Admin'den doğrudan "Yayında" seçilse de yayın tarihi dolsun.
        if self.status == Status.PUBLISHED and self.published_at is None:
            self.published_at = timezone.now()
        super().save(*args, **kwargs)


class BaseSortOrder(models.Model):
    sort_order = models.PositiveIntegerField(_("sıra"), default=0, db_index=True)

    class Meta:
        abstract = True
        ordering = ("sort_order",)
