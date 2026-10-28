from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class StudioConfig(AppConfig):
    """Personel için içerik yönetim paneli (video, altyazı, Vimeo başlıkları). Kendi modeli yok."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "studio"
    verbose_name = _("Stüdyo")
