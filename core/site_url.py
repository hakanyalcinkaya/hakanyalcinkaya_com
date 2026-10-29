"""Sitenin asıl adresiyle (SITE_URL) mutlak bağlantı. Canonical, og:url ve schema isteğin Host'una ve sorgu
parametrelerine (utm, e-posta takibi, filtre) bağlı kalmaz."""

from django.conf import settings


def absolute_url(path):
    if path.startswith(("http://", "https://")):
        return path
    return f"{settings.SITE_URL.rstrip('/')}/{path.lstrip('/')}"
