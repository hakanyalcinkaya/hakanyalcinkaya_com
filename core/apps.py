from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"
    verbose_name = _("Çekirdek")


class AdminHoneypotConfig(AppConfig):
    """admin_honeypot paketi anahtar tipini belirtmiyor; migration'ındaki AutoField'a sabitlenir.

    Django 6 varsayılanı BigAutoField olduğu için aksi hâlde paketin klasörüne yeni migration istenir.
    """

    name = "admin_honeypot"
    default_auto_field = "django.db.models.AutoField"
