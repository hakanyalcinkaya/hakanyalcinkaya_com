from .settings_base import *  # noqa: F403

MEDIA_ROOT = BASE_DIR / "media_files"

INSTALLED_APPS = [
    *INSTALLED_APPS,
    "debug_toolbar",
    "django_browser_reload",
    "django_extensions",
]

MIDDLEWARE = [
    "debug_toolbar.middleware.DebugToolbarMiddleware",
    *MIDDLEWARE,
    "django_browser_reload.middleware.BrowserReloadMiddleware",
]

INTERNAL_IPS = ["127.0.0.1", "::1"]

# Videolar yalnız izinli alan adlarında oynar; yerelde /etc/hosts ile 127.0.0.1'e yönlenen alt alan adı kullanılır.
# .dev alan adları tarayıcıda HTTPS'e zorlandığı için yerel adres .com altında.
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]", "local.hakanyalcinkaya.com"]
VIMEO_EMBED_DOMAINS = [*VIMEO_EMBED_DOMAINS, "local.hakanyalcinkaya.com"]  # noqa: F405
SITE_URL = env("SITE_URL", default="http://local.hakanyalcinkaya.com:8001")  # noqa: F405

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "config.storage.DevStaticFilesStorage"},
}
