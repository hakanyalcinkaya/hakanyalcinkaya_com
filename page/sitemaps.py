"""sitemap.xml: dizine girmesi istenen herkese açık sayfalar. noindex sayfalar (sepet, hesap, ders vb.) buraya girmez."""

from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from course.models import Course


class StaticSitemap(Sitemap):
    priorities = {"page:index": 1.0, "page:course_list": 0.9}

    def items(self):
        return ["page:index", "page:course_list", "page:privacy", "page:terms", "page:cookies"]

    def location(self, item):
        return reverse(item)

    def priority(self, item):
        return self.priorities.get(item, 0.3)


class CourseSitemap(Sitemap):
    """Yayındaki kurslar; taslaklar yalnız personele görünür, sitemap'e girmez."""

    priority = 0.8

    def items(self):
        return Course.objects.published().order_by("sort_order", "pk")

    def lastmod(self, course):
        return course.updated_at


sitemaps = {"static": StaticSitemap, "courses": CourseSitemap}
