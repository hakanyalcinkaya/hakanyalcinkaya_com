from .settings_base import *  # noqa: F403

STATIC_ROOT = BASE_DIR.parent / "static_cdn" / "static_files"
MEDIA_ROOT = BASE_DIR.parent / "static_cdn" / "media_files"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "config.storage.VersionedStaticFilesStorage"},
}

# Alan adı: asıl adres hakanyalcinkaya.com; www kalıcı olarak ona yönlendirilir (Nginx'te de yapılmalı).
# link.hakanyalcinkaya.com gibi alt alan adları ayrı platformlardır: burada izinli değiller, çerezler yalnız bu adrese
# aittir (SESSION_COOKIE_DOMAIN bilerek boş) ve HSTS alt alan adlarını kapsamaz.
CANONICAL_HOST = env("CANONICAL_HOST", default="hakanyalcinkaya.com")  # noqa: F405
REDIRECT_HOSTS = [f"www.{CANONICAL_HOST}"]
ALLOWED_HOSTS = [CANONICAL_HOST, *REDIRECT_HOSTS]
CSRF_TRUSTED_ORIGINS = [f"https://{CANONICAL_HOST}"]
SITE_URL = env("SITE_URL", default=f"https://{CANONICAL_HOST}")  # noqa: F405

# HTTPS: Nginx arkasında; Nginx X-Forwarded-Proto başlığını göndermeli.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
# HSTS önce kısa süreyle (1 saat); sorunsuz çalıştığı görülünce 1 yıla (31536000) çıkarılır.
SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=3600)  # noqa: F405
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False
SECURE_CONTENT_TYPE_NOSNIFF = True
# Alt alan adları ayrı platformlar olduğu için HSTS onları kapsamaz ve preload listesine girilmez (bilerek).
SILENCED_SYSTEM_CHECKS = ["security.W005", "security.W021"]

# Canlı sitenin Google Analytics mülkü (yalnız ziyaretçi izniyle yüklenir).
GOOGLE_ANALYTICS_ID = env("GOOGLE_ANALYTICS_ID", default="G-QSLPC9JZR6")  # noqa: F405
