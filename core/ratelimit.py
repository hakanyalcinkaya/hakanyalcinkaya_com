"""İstek sınırı: anahtar başına belirli sürede en çok N istek (ör. bülten aboneliği IP ve e-posta başına).

Sayaçlar "ratelimit" önbelleğinde (Redis) tutulur; uWSGI işçileri ortak sayar. Redis'e ulaşılamazsa istek engellenmez
(sınır bir koruma; site çalışmaya devam etmeli), yalnız uyarı yazılır.
"""

import hashlib
import logging

from django.core.cache import caches

logger = logging.getLogger(__name__)

# Ziyaretçinin yazdığı adrese giden her e-posta türü (şifre sıfırlama, özel indirim kodu, bülten onayı): adres başına
# günde en çok 5; başkasının kutusuna e-posta yağdırılmasın.
EMAIL_DAILY_LIMIT = (5, 24 * 60 * 60)


def key(scope, value):
    """Önbellek anahtarı; e-posta gibi kişisel değer açık yazılmaz."""
    return f"{scope}:{hashlib.sha256(str(value).strip().lower().encode()).hexdigest()[:32]}"


def hit(scope, value, seconds):
    """İsteği sayar ve süre içindeki istek sayısını döner; önbelleğe ulaşılamazsa None."""
    cache = caches["ratelimit"]
    name = key(scope, value)
    try:
        # add yalnız anahtar yoksa yazar (süre ilk istekten başlar); incr sayacı atomik artırır.
        cache.add(name, 0, timeout=seconds)
        return cache.incr(name)
    except Exception as error:  # noqa: BLE001 — önbellek yoksa sınırlama atlanır
        logger.warning("İstek sınırı uygulanamadı (%s): %s", scope, error)
        return None


def allow(scope, value, limit, seconds):
    """İsteği sayar; süre içinde sınırı aşmadıysa True."""
    count = hit(scope, value, seconds)
    return count is None or count <= limit


def allow_email(scope, email):
    """Bu adrese bu türden e-posta isteğini sayar; günlük sınırı (EMAIL_DAILY_LIMIT) aşmadıysa True."""
    return allow(scope, email, *EMAIL_DAILY_LIMIT)
