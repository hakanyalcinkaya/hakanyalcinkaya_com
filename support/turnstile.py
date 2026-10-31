"""Cloudflare Turnstile: giriş yapmamış kullanıcının destek formunda bot doğrulaması. Anahtar tanımlı değilse kapalıdır."""

import logging

import requests
from django.conf import settings

VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
TOKEN_FIELD = "cf-turnstile-response"

logger = logging.getLogger(__name__)


def is_enabled():
    return bool(settings.TURNSTILE_SITE_KEY and settings.TURNSTILE_SECRET_KEY)


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
