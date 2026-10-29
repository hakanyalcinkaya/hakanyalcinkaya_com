"""Shared Django settings. Environment-specific modules import this file."""

from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env(
    DEBUG=(bool, False),
)
env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("SECRET_KEY")
DEBUG = env("DEBUG")

ALLOWED_HOSTS = []


BASE_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "core.apps.AdminHoneypotConfig",
    "adminsortable2",
    "django_htmx",
    "crispy_forms",
    "crispy_bootstrap5",
]

MY_APPS = [
    "core",
    "account",
    "course",
    "learning",
    "discount",
    "cart",
    "order",
    "newsletter",
    "page",
    "studio",
]

INSTALLED_APPS = BASE_APPS + THIRD_PARTY_APPS + MY_APPS

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "core.middleware.CanonicalHostMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.template.context_processors.csrf",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "page.context_processors.site",
            ],
        },
    },
]

AUTH_USER_MODEL = "account.User"

# Bunny Stream (varsayılan platform): yönetim panelinden video/altyazı yükleme, başlık güncelleme, süre okuma ve sitede HLS oynatma.
# Kütüphane kimliği ve API anahtarı tanımlı değilse işler hata verir.
BUNNY_LIBRARY_ID = env("BUNNY_LIBRARY_ID", default="")
BUNNY_API_KEY = env("BUNNY_API_KEY", default="")
BUNNY_CDN_HOST = env("BUNNY_CDN_HOST", default="")
# CDN token koruması Bunny'de açıksa oynatma adresleri bu anahtarla kısa süreli imzalanır.
BUNNY_TOKEN_KEY = env("BUNNY_TOKEN_KEY", default="")
BUNNY_CDN_TOKEN_AUTH = env.bool("BUNNY_CDN_TOKEN_AUTH", default=False)

# Vimeo: Bunny'nin yerine stüdyodaki "Ayarlar"dan seçilebilen ikinci platform.
# Anahtarın yetkileri: public, private, create, edit, delete, upload, interact (klasör için).
VIMEO_ACCESS_TOKEN = env("VIMEO_ACCESS_TOKEN", default="")
# Yüklenen videolar Vimeo'da gizlenir, yalnız bu alan adlarında gömülebilir ve indirilemez.
VIMEO_EMBED_DOMAINS = env.list("VIMEO_EMBED_DOMAINS", default=["hakanyalcinkaya.dev", "hakanyalcinkaya.com"])

# Celery: uzun süren video işleri (yükleme, işleme takibi, altyazı) arka planda çalışır.
CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="redis://localhost:6379/0")
CELERY_TASK_IGNORE_RESULT = True
CELERY_TIMEZONE = "Europe/Istanbul"
# Yükleme görevleri dakikalar sürer; işçi aynı anda tek görev alsın ki sıradakiler başka işçiye gidebilsin.
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
LOGIN_URL = "page:login"
LOGIN_REDIRECT_URL = "page:library"
LOGOUT_REDIRECT_URL = "page:index"

CRISPY_ALLOWED_TEMPLATE_PACKS = "bootstrap5"
CRISPY_TEMPLATE_PACK = "bootstrap5"

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("DB_NAME"),
        "USER": env("DB_USER"),
        "PASSWORD": env("DB_PASSWORD"),
        "HOST": env("DB_HOST", default="localhost"),
        "PORT": env("DB_PORT", default="5432"),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

LANGUAGE_CODE = "tr"

TIME_ZONE = "Europe/Istanbul"

USE_I18N = True

USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static_files"]

MEDIA_URL = "media/"

# E-posta: SendGrid SMTP (kullanıcı adı her zaman "apikey", şifre API anahtarı). Anahtar yoksa e-postalar terminale yazılır.
SENDGRID_API_KEY = env("SENDGRID_API_KEY", default="")
# Tanımlıysa bütün e-postalar yalnız bu adrese gider (test; asıl alıcı konu satırında). Yayına çıkarken kaldırılır.
EMAIL_REDIRECT_TO = env("EMAIL_REDIRECT_TO", default="")
MAILERS = {
    "default": (
        {
            "BACKEND": "core.mail_backends.RedirectSMTPBackend",
            "OPTIONS": {
                "host": "smtp.sendgrid.net",
                "port": 587,
                "use_tls": True,
                "username": "apikey",
                "password": SENDGRID_API_KEY,
                "timeout": 20,
            },
        }
        if SENDGRID_API_KEY
        else {"BACKEND": "core.mail_backends.RedirectConsoleBackend"}
    ),
}
# E-postalardaki bağlantılar bu adresle kurulur (istek olmadan, ör. toplu gönderimde).
SITE_URL = env("SITE_URL", default="https://hakanyalcinkaya.com")
# Asıl alan adı; REDIRECT_HOSTS'tan gelen istekler buraya yönlendirilir (core.middleware). Boşsa yönlendirme yok.
CANONICAL_HOST = ""
REDIRECT_HOSTS = []
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="Hakan Yalçınkaya <no-reply@hakanyalcinkaya.com>")
SERVER_EMAIL = DEFAULT_FROM_EMAIL
