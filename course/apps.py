from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class CourseConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "course"
    verbose_name = _("Kurslar")
