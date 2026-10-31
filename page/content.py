"""Kurs ve ders sayfalarının veritabanından gelen kısmı: tanıtım videosu, müfredat (bölüm/ders) ve ders oynatıcısı.

Şablonlar örnek verideki (catalog.py) sözlük biçimini bekler; burada modelden aynı biçim üretilir. Kursun tanıtım
metinleri (neler öğreneceksin, kimler için ...) aynı slug'lı örnek kurs varsa oradan, yoksa kurs maddelerinden gelir.
Taslak kurs, bölüm ve dersler yalnız personele görünür (stüdyodan yükleneni yayına almadan denemek için).
"""

import json
import re
from collections import defaultdict
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

from django.db import models
from django.db.models import Prefetch
from django.templatetags.static import static
from django.urls import reverse

from account.models import User
from cart.models import CartRemovalReason
from cart.pricing import price_cart
from cart.request_cart import current_cart
from core.duration import ceil_minutes, clock, hours_minutes
from core.money import format_try
from core.models import Status
from core.site_url import absolute_url
from core.templatetags.core_tags import share_image
from course.models import (
    Course,
    HighlightKind,
    Lesson,
    LessonKind,
    LessonSubtitle,
    Review,
    SubtitleStatus,
    rating_summary,
)
from learning.models import Enrollment, LessonProgress
from order.models import Order
from page import catalog

# Kurs taslakları (eski platformdaki adreslerle); eski kurs adreslerini yönlendirmek için okunur.
OUTLINE_DIR = Path(__file__).resolve().parent.parent / "course" / "outlines"

FALLBACK_IMAGE = "img/courses/react.webp"
# Örnek veride karşılığı olmayan kursun kapağı: slug'da geçen kelimeye göre (kapak yükleme henüz yok).
FALLBACK_IMAGES = (("django", "img/courses/django.webp"), ("python", "img/courses/python.webp"), ("react", "img/courses/react.webp"))
LESSON_FORMAT_KEYS = {LessonKind.VIDEO: "video", LessonKind.FORM: "form", LessonKind.TEXT: "text"}


def visible_course(slug, user):
    courses = Course.objects.all() if user.is_staff else Course.objects.published()
    return courses.filter(slug=slug).first()


@lru_cache(maxsize=1)
def _legacy_outlines():
    """course/outlines taslaklarından: eski (Podia) kurs slug'ı → bölüm slug'ları ve
    (eski bölüm slug'ı, eski ders slug'ı) → (bölüm slug'ı, ders slug'ı)."""
    sections, lessons = {}, {}
    for path in OUTLINE_DIR.glob("*.json"):
        outline = json.loads(path.read_text(encoding="utf-8"))
        if outline.get("podia_slug"):
            sections[outline["podia_slug"]] = [section["slug"] for section in outline.get("sections", ())]
        for section in outline.get("sections", ()):
            for lesson in section["lessons"]:
                if section.get("legacy_slug") and lesson.get("legacy_slug"):
                    lessons[(section["legacy_slug"], lesson["legacy_slug"])] = (section["slug"], lesson["slug"])
    return sections, lessons


def legacy_lesson_slugs(section_slug, lesson_slug):
    """Eski ders adresinin bölüm ve ders slug'ları sitede neye karşılık gelir; taslakta yoksa baştaki sayı atılır."""
    found = _legacy_outlines()[1].get((section_slug, lesson_slug))
    if found:
        return found
    return re.sub(r"^\d+-", "", section_slug), re.sub(r"^\d+-", "", lesson_slug)


def moved_course(slug, user):
    """Eski kurs adresi (Podia slug'ı): bölümleri taslaktakilerle eşleşen, görünen kurs; yoksa None.
    Kurs sitede başka slug'la açılmış olsa da eski bağlantılar doğru kursa yönlenir."""
    sections = _legacy_outlines()[0].get(slug)
    if not sections:
        return None
    courses = Course.objects.all() if user.is_staff else Course.objects.published()
    # Bölüm adları kurslar arasında ortak olabilir ("html", "css"): en çok bölümü eşleşen kurs seçilir.
    matched = courses.exclude(slug=slug).filter(sections__slug__in=sections).annotate(matched=models.Count("sections"))
    return matched.order_by("-matched", "sort_order").first()


def moved_lesson(section_slug, lesson_slug, user, course=None):
    """Eski ders adresi: bölüm ve ders slug'ı eşleşen tek görünen ders (verilirse o kursta); yoksa ya da birden çoksa None."""
    lessons = Lesson.objects.filter(section__slug=section_slug, slug=lesson_slug).select_related("section__course")
    if course is not None:
        lessons = lessons.filter(section__course=course)
    if not user.is_staff:
        lessons = lessons.filter(
            status=Status.PUBLISHED, section__status=Status.PUBLISHED, section__course__status=Status.PUBLISHED
        )
    matches = list(lessons[:2])
    return matches[0] if len(matches) == 1 else None


def lesson_visible(lesson, staff=False):
    """Ders sitede görünür mü: personel taslakları da görür, diğerleri yalnız yayındaki bölüm ve dersleri."""
    return staff or (lesson.is_published and lesson.section.is_published)


def visible_lessons(course, staff=False):
    lessons = Lesson.objects.filter(section__course=course)
    return lessons if staff else lessons.published().filter(section__status=Status.PUBLISHED)


def progress_summary(course, user, staff=False):
    """Kursta tamamlanan ders sayısı, toplam ve yüzde (ders sayfasındaki ilerleme çubuğu)."""
    lessons = visible_lessons(course, staff)
    total = lessons.count()
    done = len(LessonProgress.completed_lesson_ids(user, lessons))
    return dict(done=done, total=total, pct=round(done * 100 / total) if total else 0)


def _sections(course, staff):
    lessons = Lesson.objects.all() if staff else Lesson.objects.published()
    subtitles = LessonSubtitle.objects.filter(status=SubtitleStatus.READY)
    lessons = lessons.prefetch_related(Prefetch("subtitles", queryset=subtitles))
    sections = course.sections.all() if staff else course.sections.published()
    return sections.prefetch_related(Prefetch("lessons", queryset=lessons))


def curriculum(course, staff=False):
    """Bölümler ve dersler, örnek verideki `curriculum()` ile aynı biçimde."""
    sections, flat, number = [], [], 0
    for index, section in enumerate(_sections(course, staff), start=1):
        lessons = []
        for lesson in section.lessons.all():
            number += 1
            seconds = lesson.duration_seconds or 0
            item = {
                "n": number,
                "title": lesson.title,
                "preview": lesson.is_preview,
                "format": LESSON_FORMAT_KEYS[lesson.kind],
                "format_icon": lesson.icon,
                "format_label": lesson.get_kind_display(),
                "seconds": seconds,
                "duration": clock(seconds) if seconds else "",
                "section": section.title,
                "section_index": index,
                "section_slug": section.slug,
                "lesson_slug": lesson.slug,
                "url": lesson.get_absolute_url(),
                "object": lesson,
                # Taslağı yalnız personel görür; sayfada "Taslak" etiketiyle.
                "draft": not lesson.is_published,
            }
            lessons.append(item)
            flat.append(item)
        preview_count = sum(1 for item in lessons if item["preview"])
        seconds = sum(item["seconds"] for item in lessons)
        summary = f"{len(lessons)} ders · {clock(seconds)}"
        sections.append(
            {
                "index": index,
                "id": f"bolum-{index}",
                "name": section.title,
                "slug": section.slug,
                "draft": not section.is_published,
                "lessons": lessons,
                "count": len(lessons),
                "preview_count": preview_count,
                "seconds": seconds,
                "duration": clock(seconds),
                "meta": summary + (f" · {preview_count} önizleme" if preview_count else ""),
                "meta_enrolled": summary,
            }
        )
    return sections, flat


def _course_card(course, flat):
    """Şablonların kullandığı kurs sözlüğü: örnek kurs varsa onun üstüne modeldeki güncel bilgiler yazılır."""
    card = dict(catalog.course_by_slug(course.slug) or {})
    if not card:
        tags = [technology.name for technology in course.technologies.all()]
        card = {
            "slug": course.slug,
            "url": course.get_absolute_url(),
            "cart_url": reverse("page:add_to_cart", kwargs={"slug": course.slug}),
            "remove_url": reverse("page:remove_from_cart", kwargs={"slug": course.slug}),
            "buy_url": reverse("page:buy", kwargs={"slug": course.slug}),
            "image": _fallback_image(course.slug),
            "alt": f"{course.title} kursunun kapak görseli",
            "image_label": f"{course.title} — kursu incele",
            "cart_label": f"{course.title} — sepete ekle",
            "remove_label": f"{course.title} — sepetten kaldır",
            "description": course.description or course.subtitle,
            "tags": tags,
            "tags_attr": "|".join(tags),
            "topic": _topic(course, tags),
        }
    minutes = sum(ceil_minutes(item["seconds"]) for item in flat)
    preview = course.preview_player or {}
    card.update(
        title=course.title,
        short=course.short_title,
        price=format_try(course.price),
        list_price=format_try(course.list_price) if course.has_list_discount else "",
        list_amount=course.list_price if course.has_list_discount else None,
        amount=course.price,
        lessons=len(flat),
        minutes=minutes,
        level_text=course.level_card_text,
        draft=not course.is_published,
        duration=hours_minutes(minutes),
        preview_video=preview.get("src", ""),
        preview_poster=preview.get("poster", ""),
        preview_platform=preview.get("platform", ""),
        course_id=course.pk,
    )
    card["meta_line"] = f"{card['duration']} · {card['lessons']} ders"
    return card


def _fallback_image(slug):
    return next((image for word, image in FALLBACK_IMAGES if word in slug), FALLBACK_IMAGE)


def _topic(course, tags):
    """Kurs listesi filtresi (catalog.TOPIC_FILTERS): kategori ve teknolojilerde geçen anahtar kelimeye göre."""
    words = " ".join([course.category.name, course.category.slug, *tags]).lower().replace("-", "")
    return next((key for key, _label in catalog.TOPIC_FILTERS if key and key in words), "")


# Mağaza: yayındaki kurslar, sahip olunanlar, sepet ve "Eğitimlerim". Veritabanında yayında kurs yoksa (yayın öncesi)
# listeler örnek kurslarla dolar; örnek kurslara kimse sahip değildir.
def owned_course_ids(user):
    if not user or not user.is_authenticated:
        return set()
    return set(Enrollment.objects.filter(user=user).values_list("course_id", flat=True))


def catalog_cards(user=None):
    """Sitede listelenen kurs kartları; `owned` kullanıcının kurs kaydına (Enrollment) göre."""
    courses = list(Course.objects.published().select_related("category").prefetch_related("technologies"))
    if not courses:
        return [dict(card, owned=False, amount=Decimal(str(catalog.price_amount(card["price"])))) for card in catalog.course_catalog()]
    durations = defaultdict(list)
    lessons = Lesson.objects.published().filter(section__status=Status.PUBLISHED, section__course__in=courses)
    for course_id, seconds in lessons.values_list("section__course_id", "duration_seconds"):
        durations[course_id].append({"seconds": seconds or 0})
    owned = owned_course_ids(user)
    return [dict(_course_card(course, durations[course.pk]), owned=course.pk in owned) for course in courses]


def card_by_slug(slug, user=None, cards=None):
    return next((card for card in (cards if cards is not None else catalog_cards(user)) if card["slug"] == slug), None)


def cart_cards(request, cards=None):
    """Sepetteki kurslar (eklenme sırasıyla). Veritabanındaki kurslar sepet kaydında (cart.Cart), yalnız örnek veride
    olanlar oturumda tutulur. Listede olmayan ya da artık sahip olunan kurslar sepetten düşer."""
    cards = {card["slug"]: card for card in (cards if cards is not None else catalog_cards(request.user))}
    kept = []
    cart = current_cart(request)
    if cart is not None:
        for item in cart.items.filter(course__isnull=False).select_related("course"):
            card = cards.get(item.course.slug)
            if card is not None and card["owned"]:
                cart.remove_item(item, reason=CartRemovalReason.OWNED)
            elif card is not None:
                kept.append(card)
    slugs = catalog.cart_slugs(request.session)
    sample = [slug for slug in slugs if slug in cards and not cards[slug]["owned"]]
    if sample != slugs:
        request.session[catalog.CART_SESSION_KEY] = sample
    return kept + [cards[slug] for slug in sample if cards[slug] not in kept]


def checkout_buyer(request, email):
    """Siparişin bağlanacağı hesap: giriş yapan üye; misafirde bu e-postayla kayıtlı hesap (doğrulama yok), yoksa None.
    Hesabı olmayan alıcının adı soyadı ödemeden sonra sorulur ve hesabı o adımda açılır."""
    if request.user.is_authenticated:
        return request.user
    return User.objects.with_email(email).first()


def create_card_order(request, email):
    """Kartla ödeme için bekleyen sipariş (sepetin o anki fiyatları); ödeme sağlayıcısı onaylayınca Order.mark_paid."""
    cart = current_cart(request)
    return Order.create_from_cart(cart, email, checkout_buyer(request, email), provider="card")


def cart_add(request, slug):
    """Kursu sepete ekler; veritabanındaki kursta sepet kaydına (sahip olunan ya da paketteki kurs eklenmez)."""
    course = Course.objects.filter(slug=slug).first()
    if course is None:
        catalog.cart_add(request.session, slug)
        return
    current_cart(request, create=True).add_course(course)


def cart_remove(request, slug):
    cart = current_cart(request)
    if cart is not None:
        item = cart.items.filter(course__slug=slug).first()
        if item is not None:
            cart.remove_item(item)
    catalog.cart_remove(request.session, slug)


def order_summary(items, cart=None):
    """Sepet özeti; tutarlar kartlardaki `amount` (₺, KDV dahil) ile. Sepette indirim kodu varsa kodun düştüğü tutar
    sipariş fiyatlamasıyla (cart.pricing) aynı hesaplanır."""
    subtotal = sum((item["amount"] for item in items), Decimal("0"))
    # Liste fiyatı olan kursta indirim = liste fiyatı − satış fiyatı; sepette toplam indirim tutarı gösterilir.
    list_total = sum((item.get("list_amount") or item["amount"] for item in items), Decimal("0"))
    saving = list_total - subtotal
    code, code_saving = None, Decimal("0")
    if cart is not None and cart.discount_id:
        slugs = {item["slug"] for item in items}
        lines = [line for line in price_cart(cart).lines if line.item.course_id and line.item.course.slug in slugs]
        code, code_saving = cart.discount.code, sum((line.base_price - line.final_price for line in lines), Decimal("0"))
    total = subtotal - code_saving
    return {
        "items": items,
        "count": len(items),
        "count_text": f"{len(items)} kurs",
        "list_total": format_try(list_total),
        "saving": format_try(saving) if saving > 0 else "",
        "subtotal": format_try(subtotal),
        "coupon": code,
        "coupon_saving": format_try(code_saving) if code_saving > 0 else "",
        "total": format_try(total),
    }


LIBRARY_FILTERS = (("", "Tümü"), ("in-progress", "Devam"), ("done", "Tamamlanan"))


def _library_row(enrollment, card, flat, done):
    """Eğitimlerim satırı: ilerleme, durum ve kaldığı ders (catalog._owned_row ile aynı biçim)."""
    total = len(flat)
    finished = bool(total and done >= total)
    if finished:
        state_label, state_cls, cta = "Tamamlandı", "bg-success-subtle text-success-emphasis", "Kursu tekrar izle"
    elif done:
        state_label, state_cls, cta = "Devam ediyor", "bg-primary-subtle text-primary-emphasis", "Devam et"
    else:
        state_label, state_cls, cta = "Başlanmadı", "bg-body-tertiary text-body-secondary", "Başla"
    lesson = enrollment.continue_lesson() if total else None
    current = next((item for item in flat if lesson and item["object"].pk == lesson.pk), None)
    return {
        **card,
        "done": done,
        "total": total,
        "pct": round(done * 100 / total) if total else 0,
        "continue_url": current["url"] if current else card["url"],
        "continue_title": current["title"] if current else "",
        "continue_section": current["section"] if current else "",
        "continue_label": f"{current['n']}. ders" if current else "",
        "state_label": state_label if total else "Yakında",
        "state_cls": state_cls,
        "cta": cta if total else "Kursa git",
        "finished": finished,
        "last_watched": enrollment.last_watched_at,
    }


def library_page(user, status):
    """Eğitimlerim: kullanıcının kurs kayıtları (yayındaki kurslar), ilerlemesi ve filtreler (catalog.library_page biçimi)."""
    enrollments = (
        Enrollment.objects.filter(user=user, course__status=Status.PUBLISHED)
        .select_related("course__category", "last_lesson__section")
        .prefetch_related("course__technologies")
        .order_by("-last_watched_at", "-created_at", "id")
    )
    owned = []
    for enrollment in enrollments:
        _sections, flat = curriculum(enrollment.course)
        done = len(LessonProgress.completed_lesson_ids(user, [item["object"] for item in flat]))
        owned.append(_library_row(enrollment, _course_card(enrollment.course, flat), flat, done))
    groups = {
        "": owned,
        "in-progress": [row for row in owned if not row["finished"]],
        "done": [row for row in owned if row["finished"]],
    }
    status = status if status in groups else ""
    url = reverse("page:library")
    filters = [
        dict(label=label, count=len(groups[key]), checked=key == status, url=f"{url}?status={key}" if key else url)
        for key, label in LIBRARY_FILTERS
    ]
    shown = groups[status]
    owned_ids = {row["course_id"] for row in owned}
    return {
        "owned": shown,
        "owned_count": len(owned),
        "others": [card for card in catalog_cards(user) if card.get("course_id") not in owned_ids and not card["owned"]],
        "filters": filters,
        "continue_course": next((row for row in owned if not row["finished"] and row["total"]), None),
        "empty": not shown,
        "notes": [],
        "summary": f"{len(owned)} kurs",
    }


def _detail(course, card):
    """Tanıtım metinleri: örnek kurstan ya da kurs maddelerinden (CourseHighlight)."""
    if catalog.course_by_slug(course.slug):
        detail = catalog._copy(card)
    else:
        highlights = {kind: [] for kind in HighlightKind.values}
        for highlight in course.highlights.all():
            highlights[highlight.kind].append(highlight)

        def pairs(kind):
            return [{"title": item.title, "text": item.text} for item in highlights[kind]]

        detail = {
            "subtitle": course.subtitle or course.description,
            "stack": card["tags"],
            "learn": [item.text or item.title for item in highlights[HighlightKind.LEARN]] or [course.description],
            "about": [item.text for item in highlights[HighlightKind.ABOUT]] or [course.description],
            "features": pairs(HighlightKind.FEATURE),
            "topics": pairs(HighlightKind.TOPIC),
            "outcomes": pairs(HighlightKind.OUTCOME),
            "audience": [item.text or item.title for item in highlights[HighlightKind.AUDIENCE]],
            "access": course.access_note
            or "Kursa kaydolduktan sonra videoları hemen platformdan izlemeye başlayabilirsin.",
            "discount": None,
        }
    if course.subtitle:
        detail["subtitle"] = course.subtitle
    # "Kategori" satırı: kursun kategorisi ve alt kategorileri ("Teknolojiler" satırı teknolojilerden gelir).
    names = [course.category.name, *(category.name for category in course.subcategories.all())]
    detail["categories"] = list(dict.fromkeys(names))
    return detail


def course_page(course, enrolled=False, staff=False):
    sections, flat = curriculum(course, staff)
    for item in flat:
        item["locked"] = not enrolled and not item["preview"]
        item["icon"] = "bi-lock" if item["locked"] else item["format_icon"]
    previews = [item for item in flat if item["preview"]]
    card = _course_card(course, flat)
    return {
        "course": card,
        "detail": _detail(course, card),
        "sections": sections,
        "lessons": flat,
        "preview_count": len(previews),
        "section_count": len(sections),
        "first_preview": previews[0] if previews else None,
        "enrolled": enrolled,
        "others": [item for item in catalog_cards() if item["slug"] != course.slug],
    }


def _player(lesson):
    """Ders oynatıcısının verisi: platform, adres, kapak görseli ve hazır altyazılar (Video.js <track>)."""
    player = lesson.player
    if player is None:
        return None
    service = lesson.video_service
    # Bunny'de altyazılar yüklenen dosyalardan <track> olarak verilir; Vimeo'da HLS listesinin içinde gelir.
    tracks = []
    for subtitle in lesson.subtitles.all():
        src = service.caption_url(lesson.video_id, subtitle.language)
        if src:
            tracks.append({"src": src, "lang": subtitle.language, "label": subtitle.get_language_display()})
    return {**player, "tracks_json": json.dumps(tracks)}


def find_lesson(course, section_slug, lesson_slug, enrolled=False, staff=False, completed=frozenset()):
    """Ders sayfası; örnek verideki `find_lesson()` ile aynı biçimde. `completed`: kullanıcının tamamladığı ders kimlikleri."""
    sections, flat = curriculum(course, staff)
    current = next(
        (item for item in flat if item["section_slug"] == section_slug and item["lesson_slug"] == lesson_slug), None
    )
    if current is None:
        return None
    preview = not enrolled
    for section in sections:
        section["current"] = section["index"] == current["section_index"]
        # Kursu almayan tüm içerik ağacını açık görür; kayıtlı öğrenci yalnız bulunduğu bölümü.
        section["open"] = preview or section["current"]
        for item in section["lessons"]:
            item["current"] = item["n"] == current["n"]
            item["done"] = not preview and item["object"].pk in completed
            item["locked"] = preview and not item["preview"]
            if preview:
                item["icon"] = "bi-lock" if item["locked"] else item["format_icon"]
            else:
                item["icon"] = "bi-check-circle-fill" if item["done"] else "bi-circle"
        section["completed"] = bool(section["lessons"]) and all(item["done"] for item in section["lessons"])
    previews = [item for item in flat if item["preview"]]
    index = current["n"] - 1
    if preview:
        prev = next((item for item in reversed(previews) if item["n"] < current["n"]), None)
        following = next((item for item in previews if item["n"] > current["n"]), None)
    else:
        prev = flat[index - 1] if index else None
        following = flat[index + 1] if index + 1 < len(flat) else None
    locked = preview and not current["preview"]
    current["video"] = None if locked else _player(current["object"])
    # Ek bilgiler videoyla aynı kurala uyar: kilitli derste gösterilmez.
    current["extra_html"] = "" if locked else current["object"].extra_content_html
    # İçerik dersinde (videosuz) oynatıcının yerinde bu içerik gösterilir.
    current["content_lesson"] = not current["object"].is_video
    card = _course_card(course, flat)
    detail = _detail(course, card)
    done = sum(1 for item in flat if item["done"])
    return {
        "course": card,
        "detail": detail,
        "sections": sections,
        "current": current,
        "prev": prev,
        "next": following,
        "total": len(flat),
        "done": done,
        "pct": round(done * 100 / len(flat)) if flat else 0,
        "section_count": len(sections),
        "note": None,
        "preview": preview,
        "locked": locked,
        "previews": previews,
        "preview_count": len(previews),
        "locked_count": len(flat) - len(previews),
        "learn_top": detail["learn"][:3],
    }


# Yorumlar: sitede yalnız onaylı sürüm görünür. Öne çıkanlar sayfada, hepsi "Tüm yorumlar" penceresinde.
FEATURED_REVIEW_LIMIT = 12


def _featured_or_latest(featured, everything):
    """Öne çıkarılmış yorum yoksa en yeniler gösterilir."""
    items = list(featured.ordered()[:FEATURED_REVIEW_LIMIT])
    return items or list(everything.order_by("-approved_written_at", "id")[:FEATURED_REVIEW_LIMIT])


def course_reviews(course):
    """Kurs sayfası: öne çıkan yorumlar, toplam yorum sayısı ve puan özeti."""
    everything = Review.objects.all_for(course)
    return dict(
        reviews=[review.card() for review in _featured_or_latest(Review.objects.featured_for(course), everything)],
        review_total=everything.count(),
        rating=Review.objects.filter(course=course).rating_summary(),
        reviews_url=reverse("page:course_reviews", kwargs={"slug": course.slug}),
    )


def home_reviews():
    """Ana sayfa ve kurs listesi: "ana sayfada göster" seçilen yorumlar. Veritabanında hiç yorum yoksa örnek yorumlar."""
    everything = Review.objects.all_for()
    if not everything.exists():
        return dict(reviews=catalog.reviews(), review_total=len(catalog.reviews()), reviews_url="")
    return dict(
        reviews=[review.card() for review in _featured_or_latest(Review.objects.for_home(), everything)],
        review_total=everything.count(),
        reviews_url=reverse("page:all_reviews"),
    )


def rating_by_slug():
    """Kurs kartları için: slug → onaylı puan ortalaması ve sayısı."""
    rows = (
        Review.objects.visible()
        .filter(approved_rating__isnull=False)
        .values("course__slug")
        .annotate(average=models.Avg("approved_rating"), count=models.Count("pk"))
    )
    return {row["course__slug"]: rating_summary(row["average"], row["count"]) for row in rows}


def with_ratings(cards):
    ratings = rating_by_slug()
    return [dict(card, rating=ratings.get(card["slug"])) for card in cards]


def course_schema(course, detail, rating=None):
    """Kurs sayfasının schema.org Course verisi (JSON-LD); <script> içine güvenle yazılır.

    Puan yalnız sitede yazılan yorumlardan verilir: arama motorları başka platformdan aktarılan yorumları kabul etmez.
    Google'ın kurs sonucu için CourseInstance'ta courseMode ile courseWorkload (ISO 8601 süre) birlikte gerekir.
    """
    url = absolute_url(course["url"])
    teacher = {"@type": "Person", "name": "Hakan Yalçınkaya", "url": absolute_url("/")}
    instance = {"@type": "CourseInstance", "courseMode": "online", "instructor": teacher}
    if course.get("minutes"):
        hours, minutes = divmod(course["minutes"], 60)
        instance["courseWorkload"] = f"PT{hours}H{minutes}M" if minutes else f"PT{hours}H"
    data = {
        "@context": "https://schema.org",
        "@type": "Course",
        "name": course["title"],
        "description": detail["subtitle"],
        "url": url,
        "image": absolute_url(static(share_image(course["image"]))),
        "inLanguage": "tr",
        "provider": teacher,
        "hasCourseInstance": instance,
    }
    amount = course.get("amount")
    if amount is not None and course.get("price", "").startswith("₺"):
        data["offers"] = {"@type": "Offer", "category": "Paid", "price": f"{amount:.2f}", "priceCurrency": "TRY", "url": url}
    rating = rating or {}
    if rating.get("count"):
        data["aggregateRating"] = {"@type": "AggregateRating", "ratingValue": rating["average"], "ratingCount": rating["count"]}
    return json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")
