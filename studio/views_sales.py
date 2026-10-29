"""Stüdyo satış ve öğrenci yönetimi: siparişler, sepetler, üyeler ve kurs erişimleri, abone işlemleri.

Listeler filtreyi GET parametresinde tutar; HTMX isteğinde liste, kaydırınca (parca=satir) yalnız yeni satırlar döner.
"""

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, Prefetch, Q
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from django.views.decorators.http import require_POST
from django_htmx.http import HttpResponseClientRedirect

from account.models import User
from cart.models import Cart, CartItem, CartStatus
from course.models import Course
from learning.models import Enrollment
from newsletter.models import Subscriber
from order.models import Order, OrderItem, OrderStatus
from studio import course_stats
from studio.forms import EnrollmentGrantForm, ManualOrderForm, MemberAccessForm, OrderFilterForm
from studio.templatetags.studio_tags import ROWS_PARAM
from studio.views import _toast, superuser_required

PAGE_SIZE = 50


def _page(request, rows):
    return Paginator(rows, PAGE_SIZE).get_page(request.GET.get("page"))


def _list_response(request, name, context):
    """Tam sayfa, HTMX'te liste ya da kaydırınca yalnız satırlar (templates/studio/partials/_<ad>_rows.html)."""
    if request.htmx and request.GET.get(ROWS_PARAM):
        return render(request, f"studio/partials/_{name}_rows.html", context)
    if request.htmx and not request.htmx.boosted:
        return render(request, f"studio/partials/_{name}_list.html", context)
    return render(request, f"studio/{name}.html", context)


# Siparişler
@superuser_required
def orders(request):
    """Siparişler: durum, kurs, paket, ödeme yolu, para birimi, kod, tarih aralığı ve arama filtreleri."""
    base = Order.objects.all()
    filters = OrderFilterForm(request.GET, orders=base)
    rows = filters.filter(base)
    page = _page(request, rows.select_related("user").prefetch_related("items").order_by("-created_at", "id"))
    return _list_response(request, "orders", dict(page=page, filters=filters, revenue=course_stats.revenue(rows.paid())))


@superuser_required
def order_create(request):
    """Yöneticinin açtığı sipariş (havale/EFT vb.); ?cart=<id> ile üyenin sepetinden doldurulur. Ödeme alındıysa
    hemen "ödendi" yapılır, değilse sipariş bekler ve sipariş sayfasından onaylanır."""
    initial = None
    cart_id = request.GET.get("cart")
    if cart_id and request.method != "POST":
        cart = Cart.objects.active().filter(pk=cart_id, user__isnull=False).select_related("user", "discount").first()
        initial = ManualOrderForm.initial_from_cart(cart) if cart else None
    form = ManualOrderForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        order = form.save()
        if order.is_paid:
            messages.success(request, _("Sipariş %(number)s ödendi olarak açıldı; kurs erişimleri açıldı.") % {"number": order.number})
        else:
            messages.success(request, _("Sipariş %(number)s açıldı; ödeme gelince bu sayfadan onayla.") % {"number": order.number})
        return redirect("studio:order_detail", order.pk)
    return render(request, "studio/order_form.html", dict(form=form))


def _order(order_id):
    items = OrderItem.objects.select_related("course", "bundle")
    return get_object_or_404(
        Order.objects.select_related("user", "discount", "cart").prefetch_related(
            Prefetch("items", queryset=items), Prefetch("enrollments", queryset=Enrollment.objects.select_related("course"))
        ),
        pk=order_id,
    )


@superuser_required
def order_detail(request, order_id):
    """Sipariş kalemleri, açtığı kurs kayıtları ve ödeme bilgisi; mali kayıt olduğu için tutarlar değiştirilmez."""
    return render(request, "studio/order_detail.html", dict(order=_order(order_id)))


@superuser_required
@require_POST
def order_mark_paid(request, order_id):
    """Bekleyen ya da başarısız siparişi elle ödendi yapar (havale vb.); kurs kayıtları açılır."""
    order = _order(order_id)
    if order.is_paid:
        messages.info(request, _("Sipariş zaten ödenmiş."))
    else:
        order.mark_paid(provider=order.payment_provider or "manual")
        messages.success(request, _("Sipariş ödendi olarak işaretlendi; kurs kayıtları açıldı."))
    url = reverse("studio:order_detail", args=[order.pk])
    return HttpResponseClientRedirect(url) if request.htmx else redirect(url)


# Sepetler
CART_FILTERS = {
    "active": (gettext_lazy("Açık"), Q(status=CartStatus.ACTIVE)),
    "emptied": (gettext_lazy("Boşaltılan"), Q(status=CartStatus.EMPTIED)),
    "converted": (gettext_lazy("Siparişe dönüşen"), Q(status=CartStatus.CONVERTED)),
    "all": (gettext_lazy("Tümü"), Q()),
}


@superuser_required
def carts(request):
    """İçinde ürün olan sepetler: açık, boşaltılan, siparişe dönüşen; e-posta araması."""
    key = request.GET.get("status", "active")
    if key not in CART_FILTERS:
        key = "active"
    query = request.GET.get("q", "").strip()
    base = Cart.objects.filter(items__isnull=False).distinct()
    if query:
        base = base.filter(user__email__icontains=query)
    counts = base.aggregate(**{f"n{index}": Count("pk", distinct=True, filter=condition) for index, (_label, condition) in enumerate(CART_FILTERS.values())})
    filters = [dict(key=name, label=label, count=counts[f"n{index}"]) for index, (name, (label, _condition)) in enumerate(CART_FILTERS.items())]
    items = CartItem.objects.select_related("course", "bundle")
    rows = base.filter(CART_FILTERS[key][1]).select_related("user", "discount").prefetch_related(Prefetch("items", queryset=items))
    page = _page(request, rows.order_by("-updated_at", "id"))
    return _list_response(request, "carts", dict(page=page, status=key, query=query, filters=filters))


# Öğrenciler (üyeler)
STUDENT_FILTERS = {
    "enrolled": (gettext_lazy("Kursu olan"), Q(enrollment_total__gt=0)),
    "not-enrolled": (gettext_lazy("Kursu olmayan"), Q(enrollment_total=0)),
    "all": (gettext_lazy("Tümü"), Q()),
}


@superuser_required
def students(request):
    """Üyeler: kurs sayısı ve ödenen sipariş sayısıyla; ad/e-posta araması, kurs filtresi."""
    key = request.GET.get("status", "enrolled")
    if key not in STUDENT_FILTERS:
        key = "enrolled"
    query = request.GET.get("q", "").strip()
    course_id = request.GET.get("course", "")
    base = User.objects.annotate(
        enrollment_total=Count("enrollments", distinct=True),
        paid_order_total=Count("orders", filter=Q(orders__status=OrderStatus.PAID), distinct=True),
    )
    if query:
        base = base.filter(Q(email__icontains=query) | Q(first_name__icontains=query) | Q(last_name__icontains=query))
    if course_id:
        base = base.filter(enrollments__course_id=course_id) if Course.objects.filter(pk=course_id).exists() else base.none()
    counts = base.aggregate(**{f"n{index}": Count("pk", filter=condition) for index, (_label, condition) in enumerate(STUDENT_FILTERS.values())})
    filters = [dict(key=name, label=label, count=counts[f"n{index}"]) for index, (name, (label, _condition)) in enumerate(STUDENT_FILTERS.items())]
    page = _page(request, base.filter(STUDENT_FILTERS[key][1]).order_by("-date_joined", "id"))
    context = dict(page=page, status=key, query=query, course_id=course_id, filters=filters, courses=Course.objects.order_by("title"))
    return _list_response(request, "students", context)


def _member(user_id):
    return get_object_or_404(User, pk=user_id)


@superuser_required
def student_detail(request, user_id):
    """Üyenin kursları (izleme oranıyla), siparişleri ve sepeti; elle kurs erişimi açma, kaldırma, hesabı kapatma."""
    member = _member(user_id)
    enrollments = Enrollment.objects.filter(user=member).with_progress().select_related("course", "last_lesson", "order")
    context = dict(
        member=member,
        enrollments=enrollments.order_by("-last_watched_at", "-created_at", "id"),
        orders=member.orders.prefetch_related("items").order_by("-created_at", "id"),
        cart_items=CartItem.objects.filter(cart__user=member, cart__status=CartStatus.ACTIVE).select_related("course", "bundle"),
        subscriber=Subscriber.objects.by_email(member.email),
        grant_form=EnrollmentGrantForm(user=member),
        access_form=MemberAccessForm(instance=member, editor=request.user),
    )
    return render(request, "studio/student_detail.html", context)


@superuser_required
@require_POST
def student_enroll(request, user_id):
    member = _member(user_id)
    form = EnrollmentGrantForm(request.POST, user=member)
    if form.is_valid():
        enrollment = form.save()
        messages.success(request, _("%(course)s erişimi açıldı.") % {"course": enrollment.course})
    else:
        messages.error(request, _("Erişim açılamadı; kursu ve kaynağı seç."))
    return redirect("studio:student_detail", member.pk)


@superuser_required
@require_POST
def enrollment_delete(request, enrollment_id):
    """Kurs erişimini kaldırır; ders ilerlemesi silinmez (erişim yeniden açılırsa kaldığı yerden devam eder)."""
    enrollment = get_object_or_404(Enrollment.objects.select_related("course"), pk=enrollment_id)
    user_id = enrollment.user_id
    enrollment.delete()
    messages.success(request, _("%(course)s erişimi kaldırıldı.") % {"course": enrollment.course})
    url = reverse("studio:student_detail", args=[user_id])
    return HttpResponseClientRedirect(url) if request.htmx else redirect(url)


@superuser_required
@require_POST
def student_access(request, user_id):
    member = _member(user_id)
    form = MemberAccessForm(request.POST, instance=member, editor=request.user)
    if form.is_valid() and form.has_changed():
        form.save()
        messages.success(request, _("Hesap açıldı.") if member.is_active else _("Hesap kapatıldı; giriş yapamaz."))
    return redirect("studio:student_detail", member.pk)


# Bülten aboneleri: onaylama ve abonelikten çıkarma (admin işlemleri)
SUBSCRIBER_ACTIONS = {
    "confirm": (Subscriber.confirm, gettext_lazy("Abone onaylandı.")),
    "unsubscribe": (Subscriber.unsubscribe, gettext_lazy("Abonelikten çıkarıldı.")),
}


@superuser_required
@require_POST
def subscriber_action(request, subscriber_id, action):
    if action not in SUBSCRIBER_ACTIONS:
        return HttpResponseBadRequest()
    subscriber = get_object_or_404(Subscriber.objects.with_unsubscribe_email(), pk=subscriber_id)
    method, message = SUBSCRIBER_ACTIONS[action]
    method(subscriber)
    subscriber = Subscriber.objects.with_unsubscribe_email().get(pk=subscriber.pk)
    response = render(request, "studio/partials/_subscriber_row.html", dict(subscriber=subscriber))
    return _toast(response, "success", str(message))
