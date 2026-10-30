import os

from django.contrib.staticfiles import finders
from django.contrib.staticfiles.storage import StaticFilesStorage
from django.core.exceptions import ImproperlyConfigured


class VersionedStaticFilesStorage(StaticFilesStorage):
    """Statik adreslere dosyanın değişme zamanını ekler; tarayıcı eski JS/CSS'i önbellekten kullanmaz (Nginx 1 gün
    önbelleğe aldırır). Sunucuda collectstatic'in kopyası (yalnız değişince yenilenir), geliştirmede kaynak dosya esas
    alınır."""

    def url(self, name):
        url = super().url(name)
        path = self._file_path(name)
        if path:
            url = f"{url}?v={int(os.path.getmtime(path))}"
        return url

    def _file_path(self, name):
        try:
            path = self.path(name)
        except ImproperlyConfigured:
            # Geliştirmede STATIC_ROOT yok.
            path = None
        if path and os.path.exists(path):
            return path
        return finders.find(name)
