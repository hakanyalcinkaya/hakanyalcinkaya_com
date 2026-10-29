import json
from functools import wraps
from urllib.parse import urlencode, urlparse

from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from cart.request_cart import current_cart
from course.models import Course, Lesson, Review, ReviewSource
from learning.models import Enrollment, Favorite, LessonProgress, PlayerPreference
from mailing.models import EmailLog
from newsletter.models import Subscriber
from page import content
from page.catalog import (
    NEWSLETTER_SESSION_KEY,
    ORDER_SESSION_KEY,
    RESET_SESSION_KEY,
    TOPIC_FILTERS,
    UNSUBSCRIBED_SESSION_KEY,
    catalog_stats,
    course_filters,
    course_page,
    courses_by_slugs,
    curriculum,
    filter_courses,
    find_lesson,
    legal_page,
    order_summary,
    owns_course,
    purchase_steps,
    reviews,
)
from page.forms import (
    CheckoutForm,
    CouponForm,
    EmailChangeForm,
    LoginForm,
    NewsletterForm,
    NewsletterManageForm,
    NewsletterUnsubscribeForm,
    PasswordChangeForm,
    PasswordResetForm,
    PlayerPreferenceAutoForm,
    ReviewForm,
    PlayerPreferenceForm,
    ProfileForm,
    SignupForm,
)


def _newsletter(request):
    if request.method == "POST":
        form = NewsletterForm(request.POST)
        if form.is_valid():
            # Form her sayfadan ana sayfaya gönderilir; kaynak olarak geldiği sayfa saklanır.
            source = urlparse(request.META.get("HTTP_REFERER", "")).path or request.path
            Subscriber.subscribe(form.cleaned_data["email"], name=form.cleaned_data["name"], source=source[:200])
            request.session[NEWSLETTER_SESSION_KEY] = form.cleaned_data["email"]
            return form, redirect("page:newsletter_confirm")
        return form, None
    # Giriş yapmış kullanıcıda ad ve e-posta hazır gelir; tek tıkla abone olur.
    user = request.user
    initial = {"name": user.get_full_name(), "email": user.email} if user.is_authenticated else None
    return NewsletterForm(initial=initial), None


def index(request):
    cards = content.catalog_cards(request.user)
    form, done = _newsletter(request)
    if done:
        return done
    return render(
        request,
        "index.html",
        {
            "form": form,
            **content.home_reviews(),
            "courses": content.with_ratings(cards),
            "stats": catalog_stats(cards),
        },
    )


def course_list(request):
    cards = content.catalog_cards(request.user)
    topic, courses = filter_courses(request.GET.get("konu", ""), cards)
    form, done = _newsletter(request)
    if done:
        return done
    count = len(courses)
    topic_label = dict(TOPIC_FILTERS).get(topic) if topic else ""
    context = {
        "form": form,
        "topic": topic,
        "page_title": f"{topic_label} kursları — Hakan Yalçınkaya" if topic_label else "Kurslar — Hakan Yalçınkaya",
        "course_list": content.with_ratings(courses),
        "filters": course_filters(topic, cards),
        "result_text": f"{count} kurs",
        "empty": count == 0,
        "stats": catalog_stats(cards),
    }
    # Konu filtresi HTMX ile yalnız listeyi yeniler.
    if request.htmx and not request.htmx.boosted:
        return render(request, "page/partials/course_list.html", context)
    context.update(content.home_reviews())
    return render(request, "page/courses.html", context)


def _enrolled(request, slug):
    """Kursa erişim: personel her kursu görür; veritabanındaki kurslarda kurs kaydı (Enrollment) gerekir.

    Yalnız örnek veride olan kurslar (henüz veritabanında yok) örnek kuralla çalışır.
    """
    if request.user.is_staff:
        return True
    course = Course.objects.filter(slug=slug).first()
    if course is not None:
        return Enrollment.objects.has_access(request.user, course)
    return owns_course(request.user, request.session, slug)


def course_detail(request, slug):
    # Veritabanındaki kurs (müfredat, tanıtım videosu) önce gelir; yoksa örnek veri gösterilir.
    course = content.visible_course(slug, request.user)
    if course is None and (moved := content.moved_course(slug, request.user)) is not None:
        # Eski platformdaki kurs adresi: kurs sitede başka slug'la açıldı.
        return redirect(moved.get_absolute_url(), permanent=True)
    review_context = dict(reviews=reviews(), review_total=len(reviews()))
    site_rating = None
    if course is not None:
        site_rating = Review.objects.filter(course=course, source=ReviewSource.USER).rating_summary()
        enrolled = _enrolled(request, slug)
        page = content.course_page(course, enrolled=enrolled, staff=request.user.is_staff)
        # Personel dersleri izleyebilir (enrolled) ama satın alma düğmeleri yalnız gerçek kurs kaydına göre gizlenir.
        enrollment = Enrollment.objects.for_user(request.user).filter(course=course).select_related("last_lesson").first()
        page["course"]["owned"] = enrollment is not None
        resume = enrollment.continue_lesson() if enrollment else None
        page["first_lesson_url"] = resume.get_absolute_url() if resume else (page["lessons"][0]["url"] if page["lessons"] else "")
        review_context = content.course_reviews(course)
        page["course"]["rating"] = review_context["rating"]
        # Kursu satın alan üye kendi puanını ve yorumunu burada verir ya da düzenler (personel erişimi yetmez).
        if page["course"]["owned"]:
            review_context.update(
                review_course=course, my_review=Review.objects.filter(course=course, user=request.user).first()
            )
    else:
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
            **review_context,
            "form": form,
            "course_schema": content.course_schema(
                page["course"], page["detail"], request.build_absolute_uri(page["course"]["url"]), site_rating
            ),
        },
    )


def all_reviews(request):
    """Tüm onaylı yorumlar (pencerede, en yeni önce); ana sayfa ve kurs listesinden açılır. ?kurs=<slug> o kursa daraltır."""
    courses = Review.objects.course_counts()
    selected = request.GET.get("kurs", "")
    course = Course.objects.filter(slug=selected).first() if selected else None
    items = Review.objects.all_for(course).order_by("-approved_written_at", "id")[:ALL_REVIEWS_LIMIT]
    context = dict(
        reviews=[item.card() for item in items],
        show_course=course is None,
        course_filter=courses,
        total=sum(item["count"] for item in courses),
        selected=course.slug if course else "",
        course=course,
        rating=Review.objects.filter(course=course).rating_summary() if course else None,
    )
    return render(request, "page/partials/reviews_dialog.html", context)


def course_reviews(request, slug):
    """Kursun tüm onaylı yorumları (pencerede)."""
    course = content.visible_course(slug, request.user)
    if course is None:
        raise Http404
    items = Review.objects.all_for(course).order_by("-approved_written_at", "id")[:ALL_REVIEWS_LIMIT]
    context = dict(
        reviews=[item.card() for item in items], course=course, rating=Review.objects.filter(course=course).rating_summary()
    )
    return render(request, "page/partials/reviews_dialog.html", context)


def lesson(request, course_slug, section_slug, lesson_slug):
    course = content.visible_course(course_slug, request.user)
    if course is not None:
        enrolled = _enrolled(request, course_slug)
        staff = request.user.is_staff
        completed = (
            LessonProgress.completed_lesson_ids(request.user, content.visible_lessons(course, staff)) if enrolled else set()
        )
        page = content.find_lesson(course, section_slug, lesson_slug, enrolled=enrolled, staff=staff, completed=completed)
    elif (moved_course := content.moved_course(course_slug, request.user)) is not None:
        # Eski kurs slug'ıyla açılan ders: aynı ders (eski ya da yeni slug'larıyla) varsa ona, yoksa kursun sayfasına.
        moved = content.moved_lesson(*content.legacy_lesson_slugs(section_slug, lesson_slug), request.user, course=moved_course)
        return redirect((moved or moved_course).get_absolute_url(), permanent=moved is not None)
    else:
        enrolled = owns_course(request.user, request.session, course_slug)
        page = find_lesson(course_slug, section_slug, lesson_slug, enrolled=enrolled)
    if page is None:
        raise Http404
    if page.get("locked") and page.get("previews"):
        # Kursu almamış ziyaretçi kilitli derse gelirse sıradaki (yoksa ilk) önizleme dersine yönlenir.
        target = next((item for item in page["previews"] if item["n"] > page["current"]["n"]), page["previews"][0])
        return redirect(target["url"])
    lesson = page["current"].get("object")
    # Favori ve tamamlama düğmeleri kursa erişimi olan üyeye; önizleme ziyaretçisine gösterilmez.
    favorite = None
    review_course = None
    if lesson is not None and not page["preview"] and request.user.is_authenticated:
        favorite = dict(lesson_id=lesson.pk, is_favorite=Favorite.is_favorite(request.user, lesson))
        # Kursu satın alıp değerlendirmemişse ders sayfasında sorulur; değerlendirdiyse burada bir daha sorulmaz.
        if Enrollment.objects.has_access(request.user, course) and not Review.objects.filter(course=course, user=request.user).exists():
            review_course = course
    return render(
        request,
        "page/lesson.html",
        {
            **page,
            "favorite": favorite,
            "review_course": review_course,
            # Oynatıcı tercihleri (hız, kalite, altyazı, tam ekran); ziyaretçiye varsayılanlar.
            "player_preferences_json": json.dumps(PlayerPreference.for_user(request.user).player_options()),
            # Önizleme ziyaretçisine kursun öne çıkan yorumları (örnek kursta örnek yorumlar).
            "reviews": (content.course_reviews(course)["reviews"] if course is not None else reviews())[:3],
        },
    )


def legacy_lesson(request, course_slug, section_slug, lesson_slug):
    """Eski platformun (Podia) ders adresi (/p/courses/kurs/bölüm/ders/): aynı derse kalıcı yönlenir. Ders yoksa ya da
    görünmüyorsa kursun sayfasına; kurs da yoksa 404."""
    course = content.visible_course(course_slug, request.user) or content.moved_course(course_slug, request.user)
    section, lesson = content.legacy_lesson_slugs(section_slug, lesson_slug)
    moved = content.moved_lesson(section, lesson, request.user, course=course) if course is not None else None
    if moved is not None:
        return redirect(moved.get_absolute_url(), permanent=True)
    if course is not None:
        return redirect(course.get_absolute_url())
    if find_lesson(course_slug, section_slug, lesson_slug) is not None:
        # Yalnız örnek veride olan kurs: örnek ders yeni adres yapısında açılır.
        return redirect(reverse("page:lesson", kwargs=dict(course_slug=course_slug, section_slug=section_slug, lesson_slug=lesson_slug)), permanent=True)
    raise Http404


def _member_lesson(request, lesson_id):
    """Kursa erişimi olan üyenin görebildiği ders; değilse 404."""
    lesson = get_object_or_404(Lesson.objects.select_related("section__course"), pk=lesson_id)
    course = content.visible_course(lesson.section.course.slug, request.user)
    if course is None or not content.lesson_visible(lesson, request.user.is_staff) or not _enrolled(request, course.slug):
        raise Http404
    return lesson


REVIEW_PLACES = ("lesson", "course", "library")
ALL_REVIEWS_LIMIT = 500


@login_required
def course_review(request, slug):
    """Kursu alan kullanıcının puan ve yorum kutusu (ders sayfası, kurs sayfası, Kurslarım).

    GET kutuyu, ?edit=1 formu döner; POST kaydeder ve yorum yeniden onaya gider. Ders sayfasından değerlendiren
    kullanıcıya orada bir daha sorulmaz; yorumunu Kurslarım'da görüp düzenler.
    """
    course = content.visible_course(slug, request.user)
    # Yalnız kursu satın alan (kurs kaydı olan) değerlendirir; personelin izleme erişimi yetmez.
    if course is None or not Enrollment.objects.has_access(request.user, course):
        raise Http404
    place = request.POST.get("place") or request.GET.get("place")
    place = place if place in REVIEW_PLACES else "course"
    review = Review.objects.filter(course=course, user=request.user).first()
    context = dict(course=course, review=review, place=place)
    if request.method == "POST":
        form = ReviewForm(request.POST, review=review)
        if form.is_valid():
            context.update(review=form.save(course, request.user, review), saved=True)
            return render(request, "page/partials/review_box.html", context)
        return render(request, "page/partials/review_form.html", dict(context, form=form))
    if request.GET.get("edit"):
        return render(request, "page/partials/review_form.html", dict(context, form=ReviewForm(review=review)))
    return render(request, "page/partials/review_box.html", context)


@login_required
@require_POST
def lesson_complete(request, lesson_id):
    """Dersi tamamlandı (done=1) ya da tamamlanmadı (done=0) olarak işaretler.

    Oynatıcı 5 sn kesintisiz oynayınca auto=1 ile çağırır: yalnız işaretler, kullanıcının kaldırdığı işareti geri koymaz
    (istemci o sayfada elle seçim yapıldıysa göndermez). Yanıt düğme ve (OOB) kenar listesi ile ilerleme çubuğudur.
    """
    lesson = _member_lesson(request, lesson_id)
    done = request.POST.get("done") == "1"
    LessonProgress.set_completed(request.user, lesson, done)
    if not request.htmx:
        return redirect(lesson.get_absolute_url())
    context = dict(
        lesson_id=lesson.pk,
        is_done=done,
        manual=request.POST.get("auto") != "1",
        progress=content.progress_summary(lesson.section.course, request.user, request.user.is_staff),
    )
    return render(request, "page/partials/complete_response.html", context)


@login_required
@require_POST
def lesson_favorite(request, lesson_id):
    """Dersi favorilere ekler ya da çıkarır; yalnız kursa erişimi olan üye için."""
    lesson = _member_lesson(request, lesson_id)
    is_favorite = Favorite.toggle(request.user, lesson)
    if not request.htmx:
        return redirect(lesson.get_absolute_url())
    return render(request, "page/partials/favorite_button.html", dict(lesson_id=lesson.pk, is_favorite=is_favorite))


@require_POST
def add_to_cart(request, slug):
    """Herkes sepete ekleyebilir; sahip olunan kurs eklenmez, kursa yönlendirilir."""
    card = content.card_by_slug(slug, request.user)
    if card is None:
        raise Http404
    if card["owned"]:
        messages.info(request, "Bu eğitime zaten sahipsin.")
        return redirect(card["url"])
    try:
        content.cart_add(request, slug)
    except ValidationError as error:
        messages.info(request, error.messages[0])
        return redirect("page:cart")
    return redirect(f"{reverse('page:cart')}?{urlencode({'eklendi': slug})}")


@require_POST
def remove_from_cart(request, slug):
    content.cart_remove(request, slug)
    return redirect(f"{reverse('page:cart')}?{urlencode({'cikarildi': slug})}")


def buy(request, slug):
    """"Hemen Kaydol": online ödeme açılana kadar kursu sepete ekler (sahip olunan kurs eklenmez)."""
    card = content.card_by_slug(slug, request.user)
    if card is None:
        raise Http404
    if card["owned"]:
        messages.info(request, "Bu eğitime zaten sahipsin.")
        return redirect(card["url"])
    try:
        content.cart_add(request, slug)
    except ValidationError as error:
        messages.info(request, error.messages[0])
        return redirect("page:cart")
    return redirect(f"{reverse('page:cart')}?{urlencode({'eklendi': slug})}")


def _coupon(request, cart, items, action, next_url):
    """Sepet ve ödeme sayfasındaki indirim kodu: uygula / kaldır (POST action); (form, yönlendirme ya da None).
    Sepetteki kurslarda hiçbir şey düşürmeyen kod sepette tutulmaz."""
    form = CouponForm(request.POST if action == "coupon" else None, user=request.user)
    if cart is None:
        return None, None
    if action == "coupon" and form.is_valid():
        discount = form.cleaned_data["code"]
        cart.apply_discount(discount, request.user)
        if content.order_summary(items, cart)["coupon_saving"]:
            messages.success(request, f"{discount.code} indirim kodu uygulandı.")
        else:
            cart.remove_discount()
            messages.info(request, "Bu indirim kodu sepetindeki kurslarda geçerli değil.")
        return form, redirect(next_url)
    if action == "coupon_remove":
        cart.remove_discount()
        return form, redirect(next_url)
    return form, None


def cart(request):
    cards = content.catalog_cards(request.user)
    items = content.cart_cards(request, cards)
    action = request.POST.get("action") if request.method == "POST" else None
    coupon_form, done = _coupon(request, current_cart(request), items, action, "page:cart")
    if done:
        return done
    added = content.card_by_slug(request.GET.get("eklendi", ""), cards=cards)
    removed = content.card_by_slug(request.GET.get("cikarildi", ""), cards=cards)
    in_cart = {item["slug"] for item in items}
    return render(
        request,
        "page/cart.html",
        {
            "summary": content.order_summary(items, current_cart(request)),
            "steps": purchase_steps(0),
            "added_course": added if added in items else None,
            "removed_course": removed if removed not in items else None,
            "suggestions": [card for card in cards if card["slug"] not in in_cart and not card["owned"]],
            "checkout_open": True,
            "coupon_form": coupon_form,
        },
    )


# Kartla ödeme (iyzico) bağlanınca açılır; kapalıyken sipariş oluşturulmaz, sepet bekler.
CARD_PAYMENT_OPEN = False


def checkout(request):
    """Ödeme adımı, girişsiz: misafir yalnız e-posta yazar (doğrulanmaz). Giriş yapan üyenin e-postası hesabından gelir.
    Satın alma, e-postayla kayıtlı hesaba bağlanır; hesap yoksa ad soyad ödemeden sonra sorulur.
    Son kullanıcı yalnız kartla öder."""
    items = content.cart_cards(request)
    if not items:
        return redirect("page:cart")
    member = request.user.is_authenticated
    cart = current_cart(request)
    action = request.POST.get("action", "pay") if request.method == "POST" else None
    coupon_form, done = _coupon(request, cart, items, action, "page:checkout")
    if done:
        return done
    form = None if member else CheckoutForm(request.POST if action == "pay" else None)
    if action == "pay" and (form is None or form.is_valid()):
        if not CARD_PAYMENT_OPEN:
            messages.info(request, "Kartla online ödeme çok yakında açılıyor; sepetindeki kurslar seni bekliyor.")
            return redirect("page:checkout")
        email = request.user.email if member else form.cleaned_data["email"]
        content.create_card_order(request, email)
        # iyzico bağlanınca: ödeme sayfasına yönlendirme burada.
        return redirect("page:cart")
    return render(
        request,
        "page/checkout.html",
        {
            "summary": content.order_summary(items, cart),
            "steps": purchase_steps(1),
            "card_payment_open": CARD_PAYMENT_OPEN,
            "checkout_form": form,
            # İndirim kodu yalnız veritabanındaki kursların sepetine uygulanır.
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


def _library_reviews(request):
    """Kurslarım → Değerlendirmelerim: satın alınan (kurs kaydı olan) her kurs ve kullanıcının değerlendirmesi (varsa)."""
    reviews = {review.course_id: review for review in Review.objects.filter(user=request.user)}
    courses = Course.objects.published().filter(enrollments__user=request.user).order_by("title")
    return [dict(course=course, review=reviews.get(course.pk)) for course in courses]


@login_required
def library(request):
    status = request.GET.get("durum", "")
    if status not in {"devam", "bitti"}:
        status = ""
    return render(
        request,
        "page/library.html",
        {
            **content.library_page(request.user, status),
            "favorites": Favorite.objects.for_user(request.user).for_library(),
            "review_items": _library_reviews(request),
        },
    )


def _next_url(request, fallback):
    target = request.POST.get("next") or request.GET.get("next")
    if target and url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}):
        return target
    return fallback


def anonymous_required(view):
    """Giriş yapmış kullanıcı giriş, kayıt ve şifremi unuttum sayfalarını açarsa ana sayfaya gider."""

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect("page:index")
        return view(request, *args, **kwargs)

    return wrapper


@anonymous_required
def login(request):
    form = LoginForm(request.POST if request.method == "POST" else None, request=request)
    if form.is_valid():
        auth_login(request, form.user)
        messages.success(request, f"Hoş geldin, {form.user.display_name}.")
        return redirect(_next_url(request, reverse("page:library")))
    return render(request, "page/account/login.html", {"form": form})


@anonymous_required
def signup(request):
    form = SignupForm(request.POST if request.method == "POST" else None)
    if form.is_valid():
        user = form.save()
        auth_login(request, user)
        messages.success(request, f"Hesabın oluşturuldu. Hoş geldin, {user.first_name}!")
        return redirect("page:index")
    return render(request, "page/account/signup.html", {"form": form})


@anonymous_required
def password_reset(request):
    form = PasswordResetForm(request.POST if request.method == "POST" else None)
    if form.is_valid():
        form.send_link(request)
        request.session[RESET_SESSION_KEY] = form.cleaned_data["email"]
        return redirect("page:password_reset_sent")
    return render(request, "page/account/password_reset.html", {"form": form})


@anonymous_required
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
    "player": (PlayerPreferenceForm, "Video oynatma tercihlerin kaydedildi."),
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
            "player_form": forms["player"],
        },
    )


@login_required
@require_POST
def player_preferences(request):
    """Oynatıcıda hız, kalite ya da altyazı değişince arka planda çağrılır; yalnız gönderilen tercihler kaydedilir."""
    form = PlayerPreferenceAutoForm(request.POST, user=request.user)
    if not form.is_valid():
        return JsonResponse(dict(ok=False, errors=form.errors.get_json_data()), status=400)
    form.save()
    return JsonResponse(dict(ok=True, preferences=form.instance.player_options()))


def newsletter_confirmed(request):
    return render(request, "page/newsletter_confirmed.html")


def newsletter_activate(request, token):
    """Onay e-postasındaki bağlantı: aboneliği başlatır. Bağlantı geçersizse açıklama gösterilir."""
    subscriber = Subscriber.objects.filter(confirm_token=token).first()
    if subscriber is None:
        return render(request, "page/newsletter_confirmed.html", {"invalid": True}, status=404)
    if not subscriber.is_confirmed:
        subscriber.confirm()
    return redirect("page:newsletter_confirmed")


def newsletter_unsubscribe(request):
    """E-posta adresiyle abonelikten çıkış. Adres listede olmasa da aynı sonuç gösterilir."""
    form = NewsletterUnsubscribeForm(request.POST if request.method == "POST" else None)
    if form.is_valid():
        subscriber = Subscriber.objects.by_email(form.cleaned_data["email"])
        if subscriber is not None:
            subscriber.unsubscribe()
        request.session[UNSUBSCRIBED_SESSION_KEY] = form.cleaned_data["email"]
        return redirect("page:newsletter_unsubscribe")
    return render(
        request,
        "page/newsletter_unsubscribe.html",
        {"form": form, "unsubscribed": request.session.pop(UNSUBSCRIBED_SESSION_KEY, "")},
    )


@login_required
@require_POST
def newsletter_resend(request):
    """Giriş yapmış ve onayı bekleyen kullanıcıya onay e-postasını yeniden gönderir (dakikada bir)."""
    _subscriber, sent = Subscriber.subscribe(request.user.email, name=request.user.get_full_name(), source="/tekrar-gonder/")
    if sent:
        messages.success(request, "Onay e-postasını yeniden gönderdik; gelen kutunu kontrol et.")
    else:
        messages.info(request, "Onay e-postasını az önce gönderdik; birkaç dakika sonra yeniden deneyebilirsin.")
    return redirect(f"{_next_url(request, reverse('page:index'))}#bulten")


@csrf_exempt
def newsletter_unsubscribe_link(request, token):
    """E-postalardaki "abonelikten çık" bağlantısı. Bağlantıyı önceden açan e-posta tarayıcıları yanlışlıkla çıkarmasın
    diye çıkış düğmeyle (POST) yapılır. E-posta istemcilerinin tek tıkla çıkışı (List-Unsubscribe-Post) da buraya POST
    eder; CSRF anahtarı taşıyamadığı için muaftır, yetkiyi bağlantıdaki tahmin edilemez anahtar verir.
    `?e=` hangi e-postadan çıkıldığını gösterir (mailing.EmailLog)."""
    subscriber = Subscriber.objects.filter(confirm_token=token).first()
    if subscriber is None:
        return redirect("page:newsletter_unsubscribe")
    if request.method == "POST":
        subscriber.unsubscribe()
        log = EmailLog.objects.for_token(request.GET.get("e", "")).filter(to_email__iexact=subscriber.email).first()
        if log is not None:
            log.record_unsubscribe()
        request.session[UNSUBSCRIBED_SESSION_KEY] = subscriber.email
        return redirect("page:newsletter_unsubscribe")
    return render(request, "page/newsletter_unsubscribe.html", {"link_subscriber": subscriber})


def newsletter_manage(request, token):
    """E-postalardaki "Aboneliği düzenle" bağlantısı: adı günceller, abonelikten çıkar ya da yeniden abone eder.
    Yetkiyi bağlantıdaki tahmin edilemez anahtar verir; adres değişikliği için yeni adresle abone olunur."""
    subscriber = Subscriber.objects.filter(confirm_token=token).first()
    if subscriber is None:
        return redirect("page:newsletter_unsubscribe")
    action = request.POST.get("action") if request.method == "POST" else None
    form = NewsletterManageForm(request.POST if action == "save" else None, initial={"name": subscriber.name})
    if action == "save" and form.is_valid():
        subscriber.update_name(form.cleaned_data["name"])
        messages.success(request, "Bilgilerin kaydedildi.")
        return redirect("page:newsletter_manage", token=token)
    if action == "unsubscribe":
        subscriber.unsubscribe()
        messages.success(request, "Abonelikten çıktın; artık bülten gönderilmeyecek.")
        return redirect("page:newsletter_manage", token=token)
    if action == "resubscribe":
        # Bağlantı adresin sahibine gittiği için ayrıca onay istenmez.
        subscriber.confirm()
        messages.success(request, "Yeniden abone oldun.")
        return redirect("page:newsletter_manage", token=token)
    return render(request, "page/newsletter_manage.html", {"subscriber": subscriber, "form": form})


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
