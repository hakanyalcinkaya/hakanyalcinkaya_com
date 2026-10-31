"""İstek sınırı: anahtar başına belirli sürede en çok N istek (ör. bülten aboneliği IP ve e-posta başına).

Sayaçlar "ratelimit" önbelleğinde (Redis) tutulur; uWSGI işçileri ortak sayar. Redis'e ulaşılamazsa istek engellenmez
(sınır bir koruma; site çalışmaya devam etmeli), yalnız uyarı yazılır.
"""

import hashlib
import logging

from django.core.cache import caches

logger = logging.getLogger(__name__)


def key(scope, value):
    """Önbellek anahtarı; e-posta gibi kişisel değer açık yazılmaz."""
    return f"{scope}:{hashlib.sha256(str(value).strip().lower().encode()).hexdigest()[:32]}"


def allow(scope, value, limit, seconds):
    """İsteği sayar; süre içinde sınırı aşmadıysa True."""
    cache = caches["ratelimit"]
    name = key(scope, value)
    try:
        # add yalnız anahtar yoksa yazar (süre ilk istekten başlar); incr sayacı atomik artırır.
        cache.add(name, 0, timeout=seconds)
        return cache.incr(name) <= limit
    except Exception as error:  # noqa: BLE001 — önbellek yoksa sınırlama atlanır
        logger.warning("İstek sınırı uygulanamadı (%s): %s", scope, error)
        return True
