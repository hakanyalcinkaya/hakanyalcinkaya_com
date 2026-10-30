import os

from django.conf import settings
from django.contrib.staticfiles import finders
from django.contrib.staticfiles.storage import StaticFilesStorage

from core.version import app_version

VERSIONED_EXTENSIONS = (".css", ".js")
# Bootstrap (ve ikonları) sürümüyle birlikte değişir; her deploy'da yeniden indirilmesine gerek yok.
UNVERSIONED_PREFIXES = ("css/bootstrap",)


class VersionedStaticFilesStorage(StaticFilesStorage):
    """CSS ve JS adreslerine sitenin sürümü eklenir (?v=v82); her deploy'da tarayıcı yenisini indirir, Nginx'in 1 günlük
    önbelleği eski dosyayı göstermez. Geliştirmede sürüm commit'le değiştiği için kaydedilmemiş düzenlemeler de görünsün
    diye dosyanın değişme zamanı kullanılır."""

    def url(self, name):
        url = super().url(name)
        version = self._version(name)
        return f"{url}?v={version}" if version else url

    def _version(self, name):
        if not name.endswith(VERSIONED_EXTENSIONS) or name.startswith(UNVERSIONED_PREFIXES):
            return ""
        if settings.DEBUG:
            path = finders.find(name)
            return str(int(os.path.getmtime(path))) if path else ""
        return app_version()["label"]
