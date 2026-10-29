"""Stüdyo katalog yönetimi: kurs bilgileri ve istatistikleri; paket, indirim kodu, kategori, teknoloji ve eğitmen kayıtları.

Django admin'deki işlemler buradan yapılır. Sıralı kayıtlar listede sürükle-bırak ile sıralanır (studio.js
data-sortable-list); sıra her bırakmada tümüyle gönderilir.
"""

import json

from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, ProtectedError, Q
from django.http import Http404, HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from django.views.decorators.http import require_POST
from django_htmx.http import HttpResponseClientRedirect

from account.models import InstructorProfile
from course.models import Bundle, Category, Course, Technology
from discount.models import Discount
from studio import course_stats
from studio.forms import (
    BundleForm,
    CategoryForm,
    CourseForm,
    CourseHighlightFormSet,
    DiscountForm,
    InstructorForm,
    OrderFilterForm,
    TechnologyForm,
)
from studio.templatetags.studio_tags import ROWS_PARAM
from studio.views import superuser_required

STATS_PAGE_SIZE = 50


def _apply_order(queryset, ids):
    """Kayıtların sort_order'ını gönderilen sıraya göre yazar; listede olmayan kimlikler yok sayılır."""
    by_id = {str(item.pk): item for item in queryset.filter(pk__in=ids)}
    items = []
    for order, item_id in enumerate(ids):
        item = by_id.get(str(item_id))
        if item is not None:
            item.sort_order = order
            items.append(item)
    queryset.model.objects.bulk_update(items, ["sort_order"])


def _order_ids(request):
    try:
        ids = json.loads(request.body)["ids"]
    except (ValueError, KeyError, TypeError):
        return None
    return ids if isinstance(ids, list) else None


# Kurslar
@superuser_required
@require_POST
def course_sort(request):
    ids = _order_ids(request)
    if ids is None:
        return HttpResponseBadRequest()
    _apply_order(Course.objects.all(), ids)
    return HttpResponse(status=204)


def _course_form(request, course):
    form = CourseForm(request.POST or None, request.FILES or None, instance=course)
    highlights = CourseHighlightFormSet(request.POST or None, instance=course, prefix="highlights")
    if request.method == "POST" and form.is_valid() and highlights.is_valid():
        with transaction.atomic():
            course = form.save()
            highlights.instance = course
            highlights.save()
        messages.success(request, _("Kurs kaydedildi."))
        if course.queue_preview_title_sync():
            messages.info(request, _("Tanıtım videosunun başlığı video platformunda da güncellenecek."))
        return redirect("studio:course_edit", course.pk)
    return render(request, "studio/course_form.html", dict(form=form, highlights=highlights, course=course, is_new=course._state.adding))


@superuser_required
def course_create(request):
    return _course_form(request, Course())


@superuser_required
def course_edit(request, course_id):
    """Kurs bilgileri, fiyat, sınıflandırma, eğitmenler ve sayfadaki madde listeleri."""
    return _course_form(request, get_object_or_404(Course, pk=course_id))


STATS_TABS = {
    "students": gettext_lazy("Öğrenciler"),
    "buyers": gettext_lazy("Satın alanlar"),
    "in-cart": gettext_lazy("Sepette bırakanlar"),
}


def _page(request, rows):
    return Paginator(rows, STATS_PAGE_SIZE).get_page(request.GET.get("page"))


def _stats_list(request, course, tab):
    query = request.GET.get("q", "").strip()
    context = dict(tab=tab, query=query, list_url=reverse("studio:course_stats", args=[course.pk]))
    if tab == "buyers":
        orders = course_stats.buyer_orders(course)
        filters = OrderFilterForm(request.GET, orders=orders, with_status=False, with_course=False)
        rows = filters.filter(orders).select_related("user").prefetch_related("items__bundle__courses")
        page = _page(request, rows.order_by("-paid_at", "id"))
        for order in page:
            order.matched_items = [
                item for item in order.items.all()
                if item.course_id == course.pk or (item.bundle_id and course in item.bundle.courses.all())
            ]
        return dict(context, page=page, filters=filters, revenue=course_stats.revenue(rows))
    if tab == "in-cart":
        rows = course_stats.left_in_cart(course).select_related("cart__user", "bundle")
        if query:
            rows = rows.filter(cart__user__email__icontains=query)
        unfinished = course_stats.unfinished_orders(course).select_related("user").order_by("-created_at", "id")[:STATS_PAGE_SIZE]
        return dict(context, page=_page(request, rows.order_by("-created_at", "id")), unfinished=unfinished)
    bucket = request.GET.get("progress", "")
    rows = course_stats.enrollments(course).select_related("user", "last_lesson", "order")
    condition = course_stats.bucket_filter(bucket)
    if condition is not None:
        rows = rows.filter(condition)
    else:
        bucket = ""
    if query:
        rows = rows.filter(Q(user__email__icontains=query) | Q(user__first_name__icontains=query) | Q(user__last_name__icontains=query))
    page = _page(request, rows.order_by("-progress", "-last_watched_at", "id"))
    return dict(context, page=page, bucket=bucket, buckets=course_stats.PROGRESS_BUCKETS)


@superuser_required
def course_stats_view(request, course_id):
    """Kurs istatistikleri: kayıt ve izleme oranı özeti; sekmelerde öğrenciler, satın alanlar, sepette bırakanlar.
    Sekme, oran, filtre ve arama GET parametresinde; HTMX isteğinde yalnız liste, kaydırınca yalnız yeni satırlar döner."""
    course = get_object_or_404(Course, pk=course_id)
    tab = request.GET.get("tab", "students")
    if tab not in STATS_TABS:
        tab = "students"
    context = _stats_list(request, course, tab)
    context.update(course=course, tabs=list(STATS_TABS.items()))
    if request.htmx and request.GET.get(ROWS_PARAM):
        return render(request, f"studio/partials/stats/_{tab}_rows.html", context)
    if request.htmx and not request.htmx.boosted:
        return render(request, "studio/partials/_course_stats_list.html", context)
    context["stats"] = course_stats.summary(course)
    return render(request, "studio/course_stats.html", context)


# Katalog: aynı liste/form/silme akışı; satırlar türe özel partial ile çizilir.
CATALOG = {
    "bundles": dict(
        model=Bundle,
        form=BundleForm,
        title=gettext_lazy("Paketler"),
        singular=gettext_lazy("Paket"),
        description=gettext_lazy("Birden çok kurs, kendi indirimli fiyatıyla. Sıra sitedeki listeleme sırasıdır."),
        queryset=lambda: Bundle.objects.prefetch_related("courses").order_by("sort_order", "title"),
        sortable=True,
    ),
    "discounts": dict(
        model=Discount,
        form=DiscountForm,
        title=gettext_lazy("İndirim kodları"),
        singular=gettext_lazy("İndirim kodu"),
        description=gettext_lazy("Sepete tek kod olarak uygulanır. Kullanım sayısı ödenen siparişlerde artar."),
        queryset=lambda: Discount.objects.prefetch_related("courses", "bundles").order_by("-created_at", "id"),
        sortable=False,
    ),
    "categories": dict(
        model=Category,
        form=CategoryForm,
        title=gettext_lazy("Kategoriler"),
        singular=gettext_lazy("Kategori"),
        description=gettext_lazy("Üst kategoriler sitede filtre, alt kategoriler kurs başlığında etiket olarak görünür."),
        queryset=lambda: Category.objects.select_related("parent")
        .annotate(course_total=Count("courses", distinct=True), tagged_total=Count("tagged_courses", distinct=True))
        .order_by("sort_order", "name"),
        sortable=True,
    ),
    "technologies": dict(
        model=Technology,
        form=TechnologyForm,
        title=gettext_lazy("Teknolojiler"),
        singular=gettext_lazy("Teknoloji"),
        description=gettext_lazy("Kurslarda etiket olarak kullanılır."),
        queryset=lambda: Technology.objects.annotate(course_total=Count("courses")).order_by("sort_order", "name"),
        sortable=True,
    ),
    "instructors": dict(
        model=InstructorProfile,
        form=InstructorForm,
        title=gettext_lazy("Eğitmenler"),
        singular=gettext_lazy("Eğitmen"),
        description=gettext_lazy("Kurs sayfalarında görünen eğitmen profilleri; her profil bir üyeye bağlıdır."),
        queryset=lambda: InstructorProfile.objects.select_related("user")
        .annotate(course_total=Count("course_links"))
        .order_by("sort_order", "display_name"),
        sortable=True,
    ),
}


def _catalog(kind):
    if kind not in CATALOG:
        raise Http404
    return dict(CATALOG[kind], kind=kind)


@superuser_required
def catalog_list(request, kind):
    entry = _catalog(kind)
    return render(request, "studio/catalog_list.html", dict(entry=entry, items=entry["queryset"](), row_template=f"studio/partials/catalog/_{kind}.html"))


def _catalog_form(request, entry, instance):
    form = entry["form"](request.POST or None, request.FILES or None, instance=instance)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            item = form.save()
        messages.success(request, _("%(name)s kaydedildi.") % {"name": item})
        return redirect("studio:catalog_list", entry["kind"])
    return render(request, "studio/catalog_form.html", dict(entry=entry, form=form, item=instance, is_new=instance._state.adding))


@superuser_required
def catalog_create(request, kind):
    entry = _catalog(kind)
    return _catalog_form(request, entry, entry["model"]())


@superuser_required
def catalog_edit(request, kind, item_id):
    entry = _catalog(kind)
    return _catalog_form(request, entry, get_object_or_404(entry["model"], pk=item_id))


@superuser_required
@require_POST
def catalog_delete(request, kind, item_id):
    """Kursa, siparişe bağlı kayıtlar silinmez (PROTECT); yayından kaldırmak için durumu Arşiv yapılır."""
    entry = _catalog(kind)
    item = get_object_or_404(entry["model"], pk=item_id)
    try:
        item.delete()
    except ProtectedError:
        messages.error(request, _("%(name)s silinemez; bağlı kurs ya da sipariş var. Durumunu Arşiv yapabilirsin.") % {"name": item})
    else:
        messages.success(request, _("%(name)s silindi.") % {"name": item})
    url = reverse("studio:catalog_list", args=[kind])
    return HttpResponseClientRedirect(url) if request.htmx else redirect(url)


@superuser_required
@require_POST
def catalog_sort(request, kind):
    entry = _catalog(kind)
    ids = _order_ids(request)
    if not entry["sortable"] or ids is None:
        return HttpResponseBadRequest()
    _apply_order(entry["model"].objects.all(), ids)
    return HttpResponse(status=204)
