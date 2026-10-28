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