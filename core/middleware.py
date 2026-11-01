"""Ortak middleware'ler.

Tek asıl alan adı: CANONICAL_HOST tanımlıysa REDIRECT_HOSTS'taki adreslerden (ör. www.) gelen istekler kalıcı olarak
asıl adrese yönlendirilir; yol ve parametreler korunur. Asıl yönlendirme Nginx'te de yapılabilir, bu yedektir."""

from urllib.parse import urlencode, urlparse

from django.conf import settings
from django.contrib.auth import REDIRECT_FIELD_NAME
from django.http import HttpResponsePermanentRedirect
from django.shortcuts import resolve_url
from django_htmx.http import HttpResponseClientRedirect


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


class HtmxLoginRedirectMiddleware:
    """Oturumu düşmüş kullanıcının HTMX isteği (ör. ders tamamla, favori, yorum) login_required'dan düz 302 alır; htmx bu
    yönlendirmeyi izleyip giriş sayfasını düğmenin yerine basardı. Bunun yerine tarayıcı giriş sayfasına gider, girişten
    sonra isteğin yapıldığı sayfaya (HX-Current-URL) döner."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if not getattr(request, "htmx", False) or response.status_code != 302:
            return response
        login_path = resolve_url(settings.LOGIN_URL)
        if urlparse(response.get("Location", "")).path != login_path:
            return response
        current = urlparse(request.htmx.current_url or "")
        back = current.path + (f"?{current.query}" if current.query else "") if current.path else "/"
        return HttpResponseClientRedirect(f"{login_path}?{urlencode({REDIRECT_FIELD_NAME: back})}")
