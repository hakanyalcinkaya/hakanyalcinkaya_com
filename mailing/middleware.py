"""EMAIL_TRACKING_URL ayrı bir adresse (ör. geliştirmede Gmail'in ulaşabildiği geçici tünel) o adres yalnız e-posta
takibini (/e/) sunar; sitenin geri kalanı oradan açılmaz."""

from urllib.parse import urlparse

from django.conf import settings
from django.http import HttpResponseNotFound

TRACKING_PREFIX = "/e/"


class TrackingHostMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        tracking = urlparse(getattr(settings, "EMAIL_TRACKING_URL", "")).hostname or ""
        site = urlparse(settings.SITE_URL).hostname or ""
        self.host = tracking.lower() if tracking and tracking != site else ""

    def __call__(self, request):
        if self.host and request.get_host().split(":")[0].lower() == self.host and not request.path.startswith(TRACKING_PREFIX):
            return HttpResponseNotFound()
        return self.get_response(request)
