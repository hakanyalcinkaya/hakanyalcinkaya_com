from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from page.catalog import (
    COUPON_SESSION_KEY,
    NEWSLETTER_SESSION_KEY,
    ORDER_SESSION_KEY,
    RESET_SESSION_KEY,
    UNSUBSCRIBED_SESSION_KEY,
    cart_add,
    cart_courses,
    cart_remove,
    cart_suggestions,
    catalog_stats,
    course_by_slug,
    course_catalog,
    course_filters,
    course_page,
    courses_by_slugs,
    curriculum,
    filter_courses,
    find_lesson,
    legal_page,
    library_page,
    order_summary,
    owns_course,
    place_order,
    purchase_steps,
    reviews,
)
from page.forms import (
    CheckoutForm,
    CouponForm,
    EmailChangeForm,
    LoginForm,
    NewsletterForm,
    NewsletterUnsubscribeForm,
    PasswordChangeForm,
    PasswordResetForm,
    ProfileForm,
    SignupForm,
)


def _newsletter(request):
    if request.method == "POST":
        form = NewsletterForm(request.POST)
        if form.is_valid():
            request.session[NEWSLETTER_SESSION_KEY] = form.cleaned_data["email"]
            return form, redirect("page:newsletter_confirm")
        return form, None
    return NewsletterForm(), None


def index(request):
    form, done = _newsletter(request)
    if done:
        return done
    return render(
        request,
        "index.html",
        {
            "form": form,
            "reviews": reviews(),
            "stats": catalog_stats(course_catalog()),
        },
    )


def course_list(request):
    topic, courses = filter_courses(request.GET.get("konu", ""))
    form, done = _newsletter(request)
    if done:
        return done
    count = len(courses)
    return render(
        request,
        "page/courses.html",
        {
            "form": form,
            "topic": topic,
            "course_list": courses,
            "filters": course_filters(topic),
            "result_text": f"{count} kurs",
            "empty": count == 0,
            "stats": catalog_stats(course_catalog()),
            "reviews": reviews(),
        },
    )


def course_detail(request, slug):
    page = course_page(slug, enrolled=owns_course(request.user, request.session, slug))
    if page is None:
        raise Http404
    form, done = _newsletter(request)
    if done:
        return done
    return render(
        request,
        "page/course.html",
        {
            **page,
            "form": form,
            "reviews": reviews(),
        },
    )


def lesson(request, course_slug, section_slug, lesson_slug):
    enrolled = owns_course(request.user, request.session, course_slug)
    page = find_lesson(course_slug, section_slug, lesson_slug, enrolled=enrolled)
    if page is None:
        raise Http404
    return render(
        request,
        "page/lesson.html",
        {
            **page,
            "reviews": reviews()[:3],
        },
    )


@require_POST
def add_to_cart(request, slug):
    if course_by_slug(slug) is None:
        raise Http404
    cart_add(request.session, slug)
    return redirect(f"{reverse('page:cart')}?{urlencode({'eklendi': slug})}")


@require_POST
def remove_from_cart(request, slug):
    if course_by_slug(slug) is None:
        raise Http404
    cart_remove(request.session, slug)
    return redirect(f"{reverse('page:cart')}?{urlencode({'cikarildi': slug})}")


def cart(request):
    items = cart_courses(request.session)
    added = course_by_slug(request.GET.get("eklendi", ""))
    removed = course_by_slug(request.GET.get("cikarildi", ""))
    return render(
        request,
        "page/cart.html",
        {
            "summary": order_summary(items),
            "steps": purchase_steps(0),
            "added_course": added if added in items else None,
            "removed_course": removed if removed not in items else None,
            "suggestions": cart_suggestions(items),
        },
    )


def checkout(request, slug=None):
    if slug:
        course = course_by_slug(slug)
        if course is None:
            raise Http404
        items = [course]
    else:
        items = cart_courses(request.session)
    user = request.user
    checkout_form = CheckoutForm(initial={"email": user.email} if user.is_authenticated else None)
    coupon_form = CouponForm()
    if request.method == "POST" and items:
        action = request.POST.get("action")
        if action == "coupon":
            coupon_form = CouponForm(request.POST)
            if coupon_form.is_valid():
                request.session[COUPON_SESSION_KEY] = coupon_form.cleaned_data["code"]
                return redirect(request.path)
        elif action == "coupon_remove":
            request.session.pop(COUPON_SESSION_KEY, None)
            return redirect(request.path)
        else:
            checkout_form = CheckoutForm(request.POST)
            if checkout_form.is_valid():
                place_order(request.session, items, checkout_form.cleaned_data["email"], from_cart=not slug)
                return redirect("page:thanks")
    return render(
        request,
        "page/checkout.html",
        {
            "summary": order_summary(items, request.session.get(COUPON_SESSION_KEY)),
            "steps": purchase_steps(1),
            "checkout_form": checkout_form,
            "coupon_form": coupon_form,
        },
    )


def thanks(request):
    order = request.session.get(ORDER_SESSION_KEY)
    items = courses_by_slugs(order["slugs"]) if order else []
    context = {"steps": purchase_steps(2), "order": None}
    if items:
        course = items[0]
        _sections, flat = curriculum(course["slug"])
        context.update(
            order=order,
            summary=order_summary(items, order["coupon"]),
            course=course,
            start_url=flat[0]["url"] if flat else course["url"],
            headline=f"{course['short']} kursuna erişimin açıldı."
            if len(items) == 1
            else f"{len(items)} kursa erişimin açıldı.",
        )
    return render(request, "page/thanks.html", context)


@login_required
def library(request):
    status = request.GET.get("durum", "")
    if status not in {"devam", "bitti"}:
        status = ""
    return render(
        request,
        "page/library.html",
        library_page(status),
    )


def _next_url(request, fallback):
    target = request.POST.get("next") or request.GET.get("next")
    if target and url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}):
        return target
    return fallback


def login(request):
    form = LoginForm(request.POST if request.method == "POST" else None, request=request)
    if form.is_valid():
        auth_login(request, form.user)
        messages.success(request, f"Hoş geldin, {form.user.display_name}.")
        return redirect(_next_url(request, reverse("page:library")))
    return render(request, "page/account/login.html", {"form": form})


def signup(request):
    form = SignupForm(request.POST if request.method == "POST" else None)
    if form.is_valid():
        user = form.save()
        auth_login(request, user)
        messages.success(request, f"Hesabın oluşturuldu. Hoş geldin, {user.first_name}!")
        return redirect("page:index")
    return render(request, "page/account/signup.html", {"form": form})


def password_reset(request):
    form = PasswordResetForm(request.POST if request.method == "POST" else None)
    if form.is_valid():
        form.send_link(request)
        request.session[RESET_SESSION_KEY] = form.cleaned_data["email"]
        return redirect("page:password_reset_sent")
    return render(request, "page/account/password_reset.html", {"form": form})


def password_reset_sent(request):
    return render(
        request,
        "page/account/password_reset_sent.html",
        {"email": request.session.get(RESET_SESSION_KEY, "")},
    )


def password_reset_complete(request):
    return render(request, "page/account/password_reset_complete.html")


@require_POST
def logout(request):
    auth_logout(request)
    messages.success(request, "Oturumun kapatıldı.")
    return redirect("page:index")


SETTINGS_FORMS = {
    "profile": (ProfileForm, "Profil bilgilerin kaydedildi."),
    "email": (EmailChangeForm, "E-posta adresin güncellendi."),
    "password": (PasswordChangeForm, "Şifren değiştirildi."),
}


@login_required
def account_settings(request):
    user = request.user
    forms = {key: form_class(user=user) for key, (form_class, _message) in SETTINGS_FORMS.items()}
    action = request.POST.get("action")
    if request.method == "POST" and action in SETTINGS_FORMS:
        form_class, message = SETTINGS_FORMS[action]
        form = form_class(request.POST, user=user)
        if form.is_valid():
            form.save()
            # Şifre değişince oturum kapanmasın.
            update_session_auth_hash(request, user)
            messages.success(request, message)
            return redirect(f"{reverse('page:account_settings')}#{action}")
        forms[action] = form
    return render(
        request,
        "page/account/settings.html",
        {
            "profile_form": forms["profile"],
            "email_form": forms["email"],
            "password_form": forms["password"],
        },
    )


def newsletter_confirmed(request):
    # [ÖRNEK] Abonelik servisi bağlanınca e-postadaki onay bağlantısı buraya gelecek.
    return render(request, "page/newsletter_confirmed.html")


def newsletter_unsubscribe(request):
    # [ÖRNEK] Servis bağlı değil; adres yalnız doğrulanır, bir listeden çıkarılmaz.
    form = NewsletterUnsubscribeForm(request.POST if request.method == "POST" else None)
    if form.is_valid():
        request.session[UNSUBSCRIBED_SESSION_KEY] = form.cleaned_data["email"]
        return redirect("page:newsletter_unsubscribe")
    return render(
        request,
        "page/newsletter_unsubscribe.html",
        {"form": form, "unsubscribed": request.session.pop(UNSUBSCRIBED_SESSION_KEY, "")},
    )


def newsletter_confirm(request):
    return render(
        request,
        "page/newsletter_confirm.html",
        {"email": request.session.get(NEWSLETTER_SESSION_KEY, "")},
    )


def privacy(request):
    return render(request, "page/legal.html", legal_page("privacy"))


def terms(request):
    return render(request, "page/legal.html", legal_page("terms"))


def cookies(request):
    return render(request, "page/legal.html", legal_page("cookies"))
