"""Giden e-postalardaki açılma görseli ve tıklama yönlendirmeleri; saklanan kopyalarda gizli bağlantıların maskelenmesi."""

import html
import re

from django.conf import settings
from django.core import signing
from django.urls import reverse

# Bağlantısı tek kullanımlık anahtar taşıyan değişkenler: saklanan kopyada maskelenir, tıklama takibine sokulmaz.
SENSITIVE_VARIABLES = ("reset_url", "set_password_url", "confirm_url", "unsubscribe_url")
MASK = "[gizli bağlantı]"
CLICK_SALT = "mailing.click"

HREF_RE = re.compile(r'href="(https?://[^"]+)"')


def _site(path):
    return settings.SITE_URL.rstrip("/") + path


def sensitive_values(context):
    return [str(context[name]) for name in SENSITIVE_VARIABLES if context.get(name)]


def mask(content, secrets):
    """Gizli bağlantıları (düz ve HTML'de kaçışlı hâlleriyle) MASK ile değiştirir."""
    for secret in secrets:
        content = content.replace(secret, MASK).replace(html.escape(secret), MASK)
    return content


def open_pixel_url(token):
    return _site(reverse("mailing:open", kwargs={"token": token}))


def click_url(token, url):
    return _site(reverse("mailing:click", kwargs={"token": token})) + "?u=" + signing.dumps(url, salt=CLICK_SALT, compress=True)


def unsign_click(value):
    """İmzalı hedef adres; imza bozuksa None (açık yönlendirmeye izin verilmez)."""
    try:
        return signing.loads(value, salt=CLICK_SALT)
    except signing.BadSignature:
        return None


def add_tracking(content, token, skip=()):
    """HTML'deki http(s) bağlantılarını tıklama yönlendirmesine çevirir (skip'tekiler hariç), sona açılma görseli ekler."""
    skip = set(skip)

    def rewrite(match):
        url = html.unescape(match.group(1))
        if url in skip:
            return match.group(0)
        return f'href="{html.escape(click_url(token, url))}"'

    content = HREF_RE.sub(rewrite, content)
    pixel = f'<img src="{open_pixel_url(token)}" width="1" height="1" alt="" style="display:block;border:0;width:1px;height:1px;">'
    if "</body>" in content:
        return content.replace("</body>", f"{pixel}</body>", 1)
    return content + pixel
