"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.sitemaps.views import sitemap
from django.urls import include, path
from django.views.decorators.cache import cache_page

from page.sitemaps import sitemaps
from page.views import robots_txt

urlpatterns = [
    # Gerçek yönetim paneli tahmin edilmesi zor bir adreste; /admin/ giriş denemelerini kaydeden sahte sayfa.
    path("verona/", admin.site.urls),
    path("admin/", include("admin_honeypot.urls")),
]

if settings.DEBUG:
    urlpatterns += [
        path("__debug__/", include("debug_toolbar.urls")),
        path("__reload__/", include("django_browser_reload.urls")),
    ]

urlpatterns += [
    path("robots.txt", robots_txt, name="robots_txt"),
    # Kurs yayınlanınca/kaldırılınca en geç 1 saatte yansır.
    path("sitemap.xml", cache_page(60 * 60)(sitemap), {"sitemaps": sitemaps}, name="sitemap"),
    path("studio/", include("studio.urls")),
    # E-posta açılma/tıklama takibi
    path("e/", include("mailing.urls")),
    path("", include("page.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
