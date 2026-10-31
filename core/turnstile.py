"""Cloudflare Turnstile: herkese açık formlarda bot doğrulaması (giriş, kayıt, şifremi unuttum, misafir destek formu).
Anahtar tanımlı değilse kapalıdır; form doğrulamasız çalışır.

Forma TurnstileMixin eklenir (form sınıfından önce) ve düzeninde gönder düğmesinden önce `*self.turnstile_fields()`
yer alır; view `remote_ip=client_ip(request)` verir, şablon `_base/turnstile_script.html`'i form.uses_turnstile ise yükler.
"""

import logging

import requests
from crispy_forms.layout import HTML
from django import forms
from django.conf import settings
from ipware import get_client_ip

VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
TOKEN_FIELD = "cf-turnstile-response"
ERROR = "Robot olmadığını doğrulayamadık; kutucuğu işaretleyip tekrar dene."

logger = logging.getLogger(__name__)


def is_enabled():
    return bool(settings.TURNSTILE_SITE_KEY and settings.TURNSTILE_SECRET_KEY)


def client_ip(request):
    return get_client_ip(request)[0] or ""


def verify(token, remote_ip=""):
    """Tarayıcının gönderdiği doğrulama belirtecini Cloudflare'e sorar; kapalıysa her zaman True."""
    if not is_enabled():
        return True
    if not token:
        return False
    data = {"secret": settings.TURNSTILE_SECRET_KEY, "response": token}
    if remote_ip:
        data["remoteip"] = remote_ip
    try:
        response = requests.post(VERIFY_URL, data=data, timeout=10)
        return bool(response.json().get("success"))
    except (requests.RequestException, ValueError) as error:
        logger.warning("Turnstile doğrulanamadı: %s", error)
        return False


class TurnstileMixin:
    """Doğrulama formun kendi kontrollerinden önce yapılır (ör. girişte şifre denenmeden önce)."""

    def __init__(self, *args, remote_ip="", **kwargs):
        self.remote_ip = remote_ip
        super().__init__(*args, **kwargs)

    def turnstile_fields(self):
        """Düzende gönder düğmesinden önce yer alacak kutucuk; doğrulama kapalıysa boş."""
        if not self.uses_turnstile:
            return []
        return [HTML(f'<div class="cf-turnstile mb-3" data-sitekey="{settings.TURNSTILE_SITE_KEY}" data-theme="auto" data-language="tr"></div>')]

    @property
    def uses_turnstile(self):
        return is_enabled()

    def clean(self):
        if self.is_bound and not verify(self.data.get(TOKEN_FIELD, ""), self.remote_ip):
            raise forms.ValidationError(ERROR)
        return super().clean()
