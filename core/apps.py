import logging
import os
import sys
from pathlib import Path

from django.apps import AppConfig
from django.conf import settings
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)


class CoreConfig(AppConfig):
    # Bu dosyada iki AppConfig var; INSTALLED_APPS'teki "core" bunu kullansın (yoksa Django düz AppConfig seçer).
    default = True
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"
    verbose_name = _("Çekirdek")

    def ready(self):
        # Geliştirmede kullanılan ikonlar kendiliğinden üretilir: runserver açılınca (kod değişip yeniden başlayınca da) ve
        # şablon/JS/CSS değişince (sunucu yeniden başlamaz; autoreload'ın file_changed sinyali). Sunucuda deploy üretir.
        if settings.DEBUG and _serving():
            from django.utils.autoreload import file_changed

            _build_icons()
            file_changed.connect(_icons_on_change, dispatch_uid="core.build_icons")


def _serving():
    """runserver'ın asıl (yeniden yükleyicinin başlattığı) süreci; diğer manage.py komutlarında ikon üretilmez."""
    return len(sys.argv) > 1 and sys.argv[1] == "runserver" and (os.environ.get("RUN_MAIN") == "true" or "--noreload" in sys.argv)


def _build_icons():
    from core import icons

    try:
        built, count = icons.build()
    except Exception as error:  # noqa: BLE001 — ikon üretilemese de sunucu açılsın
        logger.warning("İkonlar üretilemedi: %s", error)
        return
    if built:
        logger.warning("İkonlar yeniden üretildi (%s ikon).", count)


def _icons_on_change(sender, file_path, **kwargs):
    from core import icons

    path = Path(file_path)
    if path.suffix in icons.SCAN_SUFFIXES and icons.OUTPUT_DIR not in path.parents:
        _build_icons()


class AdminHoneypotConfig(AppConfig):
    """admin_honeypot paketi anahtar tipini belirtmiyor; migration'ındaki AutoField'a sabitlenir.

    Django 6 varsayılanı BigAutoField olduğu için aksi hâlde paketin klasörüne yeni migration istenir.
    """

    name = "admin_honeypot"
    default_auto_field = "django.db.models.AutoField"
