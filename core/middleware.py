"""Ortak middleware'ler.

Tek asıl alan adı: CANONICAL_HOST tanımlıysa REDIRECT_HOSTS'taki adreslerden (ör. www.) gelen istekler kalıcı olarak
asıl adrese yönlendirilir; yol ve parametreler korunur. Asıl yönlendirme Nginx'te de yapılabilir, bu yedektir.

İstek sınırı: aynı IP'den dakikada REQUEST_LIMIT["LIMIT"] istekten fazlası 429 alır (RequestLimitMiddleware)."""

import ipaddress
import logging
import re
import time
from urllib.parse import urlencode, urlparse

from django.conf import settings
from django.contrib.auth import REDIRECT_FIELD_NAME
from django.http import HttpResponse, HttpResponsePermanentRedirect
from django.shortcuts import resolve_url
from django.template.loader import render_to_string
from django_htmx.http import HttpResponseClientRedirect

from core import ratelimit

logger = logging.getLogger(__name__)


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


def _networks(values):
    return [ipaddress.ip_network(value.strip(), strict=False) for value in values if value.strip()]


def _address(value):
    try:
        return ipaddress.ip_address(value.strip())
    except ValueError:
        return None


class RequestLimitMiddleware:
    """Aynı IP'den pencere (WINDOW_SECONDS) içinde LIMIT'ten fazla istek 429 alır; LIMIT 0 ise kapalı.

    - Sayaçlar core.ratelimit ile Redis'te; uWSGI işçileri ortak sayar. Redis'e ulaşılamazsa istek geçer ve sınır
      PAUSE_SECONDS boyunca denenmez (her istek bağlantı zaman aşımını beklemesin).
    - IP, Nginx'in verdiği REMOTE_ADDR'dir. İstek TRUSTED_PROXIES'ten (ör. ileride Cloudflare) geliyorsa istemci
      CF-Connecting-IP'den, yoksa X-Forwarded-For'da sağdan ilk güvenilmeyen adresten okunur; başlıklar başka
      kaynaktan gelirse dikkate alınmaz (sahte IP ile sınır aşılamasın). IPv6 /64 ağı tek adres sayılır.
    - EXEMPT_PATHS sayılmaz (e-posta takip pikseli, ödeme dönüşleri, ders izleme konumu).
    - Yöneticiler (is_staff) sınırı aşsa da engellenmez; stüdyo durum ekranları birkaç saniyede bir yenilenir.
    """

    PAUSE_SECONDS = 30

    def __init__(self, get_response):
        self.get_response = get_response
        conf = getattr(settings, "REQUEST_LIMIT", {})
        self.limit = conf.get("LIMIT", 60)
        self.window = conf.get("WINDOW_SECONDS", 60)
        self.exempt = [re.compile(pattern) for pattern in conf.get("EXEMPT_PATHS", [])]
        self.trusted = _networks(conf.get("TRUSTED_PROXIES", []))
        self.paused_until = 0

    def __call__(self, request):
        if self.is_limited(request):
            return self.too_many_requests()
        return self.get_response(request)

    def is_limited(self, request):
        if not self.limit or time.monotonic() < self.paused_until:
            return False
        if any(pattern.search(request.path_info) for pattern in self.exempt):
            return False
        ip = self.client_ip(request)
        if not ip:
            return False
        count = ratelimit.hit("request-ip", ip, self.window)
        if count is None:
            self.paused_until = time.monotonic() + self.PAUSE_SECONDS
            return False
        if count <= self.limit or request.user.is_staff:
            return False
        if count == self.limit + 1:
            logger.warning("İstek sınırı aşıldı: %s, %s sn'de %s istek (%s)", ip, self.window, self.limit, request.path)
        return True

    def is_trusted(self, address):
        return address is not None and any(address in network for network in self.trusted)

    def client_ip(self, request):
        """Sayacın anahtarı: istemci adresi; IPv6'da adresin /64 ağı."""
        remote = _address(request.META.get("REMOTE_ADDR", ""))
        address = remote
        if self.is_trusted(remote):
            cloudflare = _address(request.META.get("HTTP_CF_CONNECTING_IP", ""))
            forwarded = [_address(part) for part in request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")]
            # Proxy'ler adresi sona ekler; sağdan ilk güvenilmeyen adres istemcidir.
            untrusted = [item for item in reversed(forwarded) if item is not None and not self.is_trusted(item)]
            address = cloudflare or (untrusted[0] if untrusted else remote)
        if address is None:
            return ""
        if address.version == 6:
            if address.ipv4_mapped:
                return str(address.ipv4_mapped)
            return str(ipaddress.ip_network(f"{address}/64", strict=False))
        return str(address)

    def too_many_requests(self):
        response = HttpResponse(render_to_string("429.html"), status=429)
        response["Retry-After"] = str(self.window)
        return response
