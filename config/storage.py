import os

from django.contrib.staticfiles import finders
from django.contrib.staticfiles.storage import StaticFilesStorage


class DevStaticFilesStorage(StaticFilesStorage):
    """Geliştirmede statik adreslere dosyanın değişme zamanını ekler; tarayıcı eski JS/CSS'i önbellekten kullanmaz."""

    def url(self, name):
        url = super().url(name)
        path = finders.find(name)
        if path:
            url = f"{url}?v={int(os.path.getmtime(path))}"
        return url
