"""Tek asıl alan adı: CANONICAL_HOST tanımlıysa REDIRECT_HOSTS'taki adreslerden (ör. www.) gelen istekler kalıcı olarak
asıl adrese yönlendirilir; yol ve parametreler korunur. Asıl yönlendirme Nginx'te de yapılabilir, bu yedektir."""

from django.conf import settings
from django.http import HttpResponsePermanentRedirect


class CanonicalHostMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.canonical = getattr(settings, "CANONICAL_HOST", "")
        self.redirect_hosts = {host.lower() for host in getattr(settings, "REDIRECT_HOSTS", [])}

    def __call__(self, request):
        if self.canonical:
            host = request.get_host().split(":")[0].lower()
            if host in self.redirect_hosts:
                scheme = "https" if request.is_secure() else request.scheme
                return HttpResponsePermanentRedirect(f"{scheme}://{self.canonical}{request.get_full_path()}")
        return self.get_response(request)
