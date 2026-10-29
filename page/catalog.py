import json
import zlib
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

from django.urls import reverse
from django.utils import timezone

NAV = (
    ("egitimler", "Kurslar"),
    ("yorumlar", "Öğrenci Yorumları"),
    ("hakkimda", "Hakkımda"),
)

SHOP_URL_NAMES = frozenset({"course_list", "course_detail", "cart", "checkout", "buy", "thanks"})

DEFAULT_CART_SLUG = "sifirdan-projelerle-front-end-ve-react-18-x-ogren"

# Model yokken sepet, kupon ve son sipariş oturumda tutulur.
CART_SESSION_KEY = "cart"
COUPON_SESSION_KEY = "coupon"
ORDER_SESSION_KEY = "last_order"
NEWSLETTER_SESSION_KEY = "newsletter_email"
# [ÖRNEK] Sipariş modeli yokken satın alınan kurslar oturumda tutulur.
PURCHASED_SESSION_KEY = "purchased"
RESET_SESSION_KEY = "reset_email"
UNSUBSCRIBED_SESSION_KEY = "newsletter_unsubscribed"

# [ÖRNEK] İndirim kodu durumlarını göstermek için. Gerçek kodlar ödeme sağlayıcısında doğrulanacak.
COUPONS = {"ORNEK10": 10}

TOPIC_FILTERS = (
    ("", "Tümü"),
    ("frontend", "Front-End"),
    ("python", "Python"),
)

LIBRARY_DONE = {
    "sifirdan-projelerle-front-end-ve-react-18-x-ogren": 48,
    "sifirdan-uctan-uca-projelerle-python-ve-django-ogren": 12,
}

# [ÖRNEK] İzleme kaydı yokken "Kaldığın yer" kartındaki son izleme zamanı (yerel saat).
LAST_WATCHED = {
    "sifirdan-projelerle-front-end-ve-react-18-x-ogren": (2026, 10, 27, 21, 40),
    "sifirdan-uctan-uca-projelerle-python-ve-django-ogren": (2026, 10, 19, 10, 15),
}

DATA_DIR = Path(__file__).resolve().parent / "data"

# [ÖRNEK] Veride ders süresi ve türü yok. Süre ders kimliğinden sabit olarak türetilir (3:00–15:40);
# başlığında "Bildirim Formu" geçen dersler form, diğerleri videodur.
LESSON_FORMATS = {
    "video": {"icon": "bi-play-circle", "label": "Video"},
    "form": {"icon": "bi-ui-checks", "label": "Form"},
}
SAMPLE_SECONDS = (180, 940)

_COURSES = (
    {
        "slug": "sifirdan-projelerle-front-end-ve-react-18-x-ogren",
        "title": "Sıfırdan Projelerle Front-End ve React 18.x Öğren",
        "short": "Front-End ve React 18.x",
        "description": "Front-End temellerinden React 18.x’e; sıfırdan, projelerle ilerleyen kapsamlı kurs.",
        "tags": ("Front-End", "React 18.x"),
        "topic": "frontend",
        "duration": "52+ saat",
        "lessons": 335,
        "price": "€99.90",
        "image": "img/courses/react.jpg",
    },
    {
        "slug": "sifirdan-uctan-uca-projelerle-python-ve-django-ogren",
        "title": "Sıfırdan Uçtan Uca Projelerle Python ve Django Öğren",
        "short": "Python ve Django",
        "description": "Python ve Django ile sıfırdan başlayıp uçtan uca projeler geliştirdiğin kurs.",
        "tags": ("Python", "Django"),
        "topic": "python",
        "duration": "51+ saat",
        "lessons": 327,
        "price": "€99.90",
        "image": "img/courses/django.jpg",
        "subtitle": "Python ve Django ile sıfırdan başlayıp uçtan uca projeler geliştirdiğin kurs.",
        "stack": ("Python", "Django", "HTML", "CSS", "Git"),
        "learn": (
            "Python temellerini projelerle pekiştireceksin.",
            "Django ile uçtan uca web uygulaması kuracaksın.",
            "Veritabanı, form ve şablon katmanını birlikte kullanacaksın.",
            "Yaptığın projeleri yayına almayı göreceksin.",
        ),
        "about": (
            "Kurs sıfırdan başlar. Her bölümde öğrendiğini bir proje adımıyla uygularsın.",
            "Amaç, Python ve Django ile kendi web uygulamanı baştan sona çıkarabilmen.",
        ),
        "features": (
            ("Sıfırdan ilerler", "Önceden Django bilmene gerek yok. Bölümler birbirinin üstüne biner."),
            ("Proje odaklı", "Her bölümün sonunda öğrendiklerini çalışan bir parçaya dönüştürürsün."),
        ),
        "topics": (
            ("Python", "Dil temelleri, veri yapıları ve fonksiyonlarla düşünmek."),
            ("Django", "Modeller, view’lar, şablonlar ve formlarla web uygulaması."),
            ("Veritabanı", "İlişkiler, sorgular ve yönetim paneli."),
        ),
        "outcomes": (
            ("Uçtan uca proje", "Kendi Django uygulamanı baştan sona kurabilme."),
            ("Python pratiği", "Günlük geliştirmede kullanabileceğin Python alışkanlığı."),
        ),
        "audience": (
            "Python ile web geliştirmek isteyenler",
            "Django’ya sıfırdan başlamak isteyenler",
            "Proje portföyü çıkarmak isteyenler",
        ),
    },
    {
        "slug": "iki-egitmen-ile-sifirdan-python-ogren",
        "title": "İki Eğitmen ile Sıfırdan Python Öğren",
        "short": "Sıfırdan Python",
        "description": "İki eğitmenin anlatımıyla Python’a sıfırdan başlangıç.",
        "tags": ("Python", "Başlangıç"),
        "topic": "python",
        "duration": "Süre: [eklenecek]",
        "lessons": 109,
        "price": "€99.90",
        "image": "img/courses/python.png",
        "subtitle": "İki eğitmenin anlatımıyla Python’a sıfırdan başlangıç.",
        "stack": ("Python",),
        "learn": (
            "Python sözdizimini sıfırdan öğreneceksin.",
            "Küçük programlar yazarak konuları pekiştireceksin.",
            "İki farklı anlatımla aynı konuyu başka açıdan göreceksin.",
        ),
        "about": (
            "Bu kurs Python’a hiç başlamamış ya da temeli tazelemek isteyenler için.",
            "İki eğitmen aynı konuları farklı örneklerle anlatır.",
        ),
        "features": (
            ("İki eğitmen", "Aynı konu iki anlatımla gelir; takıldığın yerde ikinci örneğe bakarsın."),
            ("Başlangıç temposu", "Ön bilgi gerekmez. Adımlar kısa ve uygulamalıdır."),
        ),
        "topics": (
            ("Python temelleri", "Değişkenler, koşullar, döngüler ve fonksiyonlar."),
            ("Pratik", "Küçük alıştırmalarla yazdığın kodu çalıştırma."),
        ),
        "outcomes": (
            ("Python ile ilk programların", "Kendi başına küçük Python programları yazabilme."),
            ("Sonraki kursa hazırlık", "Django kursuna geçecek temel."),
        ),
        "audience": (
            "Python’a sıfırdan başlayanlar",
            "Programlamaya yeni girenler",
            "Temeli başka bir dille görüp Python’a geçenler",
        ),
    },
)

_REVIEWS = (
    (
        "Gülnisa",
        "Hocamızın emeğine sağlık. Anlamadığım birçok şeyi çok iyi anladım. Kurs içeriği çok güzel hazırlanmış. Hocamız her şeyi detaylıca anlatıyor ve konunun daha iyi anlaşılması için çeşitli örnek projeler yapıyor. Başka dersleri sabırsızlıkla bekliyorum",
    ),
    (
        "Ferdi S.",
        "Hakan Hocam gerçekten muazzam bilgi ve tecrübeleri ile harika bir eğitim hazırlamış. Eğitimi aldığım için çok mutluyum ve herkese tavsiye ederim.\n\nEdit: Eğitimin yarısı bitti bile ve çok eğlenceli geçiyor :)",
    ),
    (
        "Mustafa B.",
        "Dersine girdiğim en iyi Öğretmensiniz ve her bir kelimenizde ki bilgi benim için çok önemli . Totalde 52 saat ama bunun arka planında ki emeği görebiliyorum.\n\nUmarım bu bilgileri doğru bir şekilde kullanır ve sizinle paylaşma fırsatı yakalarım. Teşekürler",
    ),
    (
        "Umut K.",
        "Hakan hoca alanında gerçekten bayağı iyidir. Her eğitimini zevk alarak izleyeceğinizi düşünüyorum. İyi çalışmalar herkese :)",
    ),
    (
        "Onur I.",
        "Hakan hocamın Patika.dev deki eğitimlerinden oldukça memnun kaldığım için ve konu anlatımını kendi anlama biçimime yakın bulduğum gördüm ve bu eğitimi de ondan almaya karar verdim",
    ),
    (
        "Ahmet Fatih R.",
        "Her eğitiminde bir şeyleri öğretirken öylesine değil gerçekten öğrensinler şeklinde yaklaşımıyla, bence mükemmel üslubuyla. Kesinlikle çok kaliteli ve çok iyi bir eğitmen. Sayın Hakan Yalçınkaya benim nazarımda Hakan Yalçınkaya ve diğerleri gibi iddialı bir cümlenin karşılığı. Umarım hayatta her şey gönlünce olsun sayın Hocam. Sevgiler :)",
    ),
)


@lru_cache(maxsize=None)
def _load_detail(slug):
    path = DATA_DIR / f"{slug}.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def _pairs(rows):
    return [{"title": title, "text": text} for title, text in rows]


def _lesson_slugs(live_url):
    parts = urlparse(live_url).path.strip("/").split("/")
    return parts[-2], parts[-1]


def _present_course(raw):
    slug = raw["slug"]
    return {
        **raw,
        "url": reverse("page:course_detail", kwargs={"slug": slug}),
        "cart_url": reverse("page:add_to_cart", kwargs={"slug": slug}),
        "remove_url": reverse("page:remove_from_cart", kwargs={"slug": slug}),
        "buy_url": reverse("page:buy", kwargs={"slug": slug}),
        "owned": slug in LIBRARY_DONE,
        "alt": f"{raw['title']} kursunun kapak görseli",
        "image_label": f"{raw['title']} — kursu incele",
        "cart_label": f"{raw['title']} — sepete ekle",
        "remove_label": f"{raw['title']} — sepetten kaldır",
        "meta_line": f"{raw['duration']} · {raw['lessons']} ders",
        "tags_attr": "|".join(raw["tags"]),
    }


def course_catalog():
    return [_present_course(course) for course in _COURSES]


def course_by_slug(slug):
    for course in course_catalog():
        if course["slug"] == slug:
            return course
    return None


def _rounded_down(total):
    """Ana sayfadaki rakamlar: 10 ve üstü onluğa aşağı yuvarlanır ("770+"), küçükse olduğu gibi."""
    return f"{(total // 10) * 10}+" if total >= 10 else str(total)


def _card_minutes(course):
    # Veritabanındaki kurslarda dakika hesaplanmış gelir; örnek kurslarda süre "52+ saat" metnindedir.
    if "minutes" in course:
        return course["minutes"]
    digits = "".join(char for char in course.get("duration", "").split("saat")[0] if char.isdigit())
    return int(digits) * 60 if digits else 0


def catalog_stats(courses):
    lessons = sum(course["lessons"] for course in courses)
    hours = -(-sum(_card_minutes(course) for course in courses) // 60)  # yukarı yuvarlanır: 50 dk → 1 saat
    return {"courses": len(courses), "lessons": _rounded_down(lessons), "hours": _rounded_down(hours)}


def reviews():
    return [{"name": name, "text": text, "initial": name[0]} for name, text in _REVIEWS]


def course_filters(selected, courses=None):
    courses = course_catalog() if courses is None else courses
    items = []
    for key, label in TOPIC_FILTERS:
        if key:
            count = sum(1 for course in courses if course["topic"] == key)
            url = f"{reverse('page:course_list')}?konu={key}"
        else:
            count = len(courses)
            url = reverse("page:course_list")
        items.append(
            {
                "key": key,
                "label": label,
                "count": count,
                "checked": key == selected,
                "url": url,
            }
        )
    return items


def filter_courses(topic, courses=None):
    courses = course_catalog() if courses is None else courses
    if topic not in {key for key, _label in TOPIC_FILTERS if key}:
        topic = ""
    if topic:
        shown = [course for course in courses if course["topic"] == topic]
    else:
        shown = courses
    return topic, shown


def clock(seconds):
    """Süre gösterimi: 09:05 (dakika:saniye), bir saati aşınca 1:05:30."""
    minutes, secs = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def _lesson_format(title):
    return "form" if "bildirim formu" in title.lower() else "video"


def _sample_seconds(lesson_slug):
    low, high = SAMPLE_SECONDS
    return low + zlib.crc32(lesson_slug.encode()) % (high - low)


def curriculum(slug):
    detail = _load_detail(slug)
    sections = []
    flat = []
    number = 0
    for index, section in enumerate(detail.get("curriculum", []), start=1):
        name, items = section
        lessons = []
        section_slug = ""
        for title, live_url, preview in items:
            section_slug, lesson_slug = _lesson_slugs(live_url)
            number += 1
            kind = _lesson_format(title)
            seconds = _sample_seconds(lesson_slug) if kind == "video" else 0
            lesson = {
                "n": number,
                "title": title,
                "preview": bool(preview),
                "format": kind,
                "format_icon": LESSON_FORMATS[kind]["icon"],
                "format_label": LESSON_FORMATS[kind]["label"],
                "seconds": seconds,
                "duration": clock(seconds) if seconds else "",
                "section": name,
                "section_index": index,
                "section_slug": section_slug,
                "lesson_slug": lesson_slug,
                "url": reverse(
                    "page:lesson",
                    kwargs={
                        "course_slug": slug,
                        "section_slug": section_slug,
                        "lesson_slug": lesson_slug,
                    },
                ),
            }
            lessons.append(lesson)
            flat.append(lesson)
        preview_count = sum(1 for lesson in lessons if lesson["preview"])
        seconds = sum(lesson["seconds"] for lesson in lessons)
        summary = f"{len(lessons)} ders · {clock(seconds)}"
        sections.append(
            {
                "index": index,
                "id": f"bolum-{index}",
                "name": name,
                "slug": section_slug,
                "lessons": lessons,
                "count": len(lessons),
                "preview_count": preview_count,
                "seconds": seconds,
                "duration": clock(seconds),
                # Kursa erişimi olmayan önizleme sayısını da görür.
                "meta": summary + (f" · {preview_count} önizleme" if preview_count else ""),
                "meta_enrolled": summary,
            }
        )
    return sections, flat


def _copy(course):
    detail = _load_detail(course["slug"])
    return {
        "subtitle": detail.get("subtitle") or course.get("subtitle") or course["description"],
        "stack": detail.get("stack") or list(course.get("stack", course["tags"])),
        "learn": detail.get("learn") or list(course.get("learn", (course["description"],))),
        "about": detail.get("about") or list(course.get("about", (course["description"],))),
        "features": _pairs(detail.get("features") or course.get("features", ())),
        "topics": _pairs(detail.get("topics") or course.get("topics", ())),
        "outcomes": _pairs(detail.get("outcomes") or course.get("outcomes", ())),
        "audience": detail.get("audience") or list(course.get("audience", ())),
        "access": detail.get("access")
        or "Kursa kaydolduktan sonra videoları hemen platformdan izlemeye başlayabilirsin.",
        "discount": detail.get("discount"),
    }


def course_page(slug, enrolled=False):
    course = course_by_slug(slug)
    if course is None:
        return None
    sections, flat = curriculum(slug)
    # Kursa erişimi olmayan yalnız önizleme derslerini açabilir.
    for lesson in flat:
        lesson["locked"] = not enrolled and not lesson["preview"]
        lesson["icon"] = "bi-lock" if lesson["locked"] else lesson["format_icon"]
    previews = [lesson for lesson in flat if lesson["preview"]]
    return {
        "course": course,
        "detail": _copy(course),
        "sections": sections,
        "lessons": flat,
        "preview_count": len(previews),
        "section_count": len(sections),
        "first_preview": previews[0] if previews else None,
        "enrolled": enrolled,
        "others": [item for item in course_catalog() if item["slug"] != slug],
    }


def owns_course(user, session, slug):
    # [ÖRNEK] Yalnız veritabanında olmayan örnek kurslar için; gerçek erişim kurs kaydıyla (page.views._enrolled).
    return slug in session.get(PURCHASED_SESSION_KEY, [])


def _lesson_icon(lesson, preview):
    """Önizlemede kilit ya da ders türü; kursa erişimi olanda ilerleme (boş / işaretli daire)."""
    if preview:
        return "bi-lock" if lesson["locked"] else lesson["format_icon"]
    return "bi-check-circle-fill" if lesson["done"] else "bi-circle"


def find_lesson(course_slug, section_slug, lesson_slug, enrolled=None):
    course = course_by_slug(course_slug)
    if course is None:
        return None
    sections, flat = curriculum(course_slug)
    current = None
    for lesson in flat:
        if lesson["section_slug"] == section_slug and lesson["lesson_slug"] == lesson_slug:
            current = lesson
            break
    if current is None:
        return None
    index = current["n"] - 1
    # Kayıtlı olmayan (giriş yapmamış ya da kursu almamış) kullanıcı önizleme sürümünü görür: yalnız ücretsiz dersler oynar.
    preview = not (course["owned"] if enrolled is None else enrolled)
    done = LIBRARY_DONE.get(course_slug, 0)
    total = len(flat)
    for section in sections:
        section["current"] = section["index"] == current["section_index"]
        section["open"] = section["current"]
        for lesson in section["lessons"]:
            lesson["current"] = lesson["n"] == current["n"]
            lesson["done"] = not preview and lesson["n"] <= done
            lesson["locked"] = preview and not lesson["preview"]
            lesson["icon"] = _lesson_icon(lesson, preview)
        section["completed"] = not preview and all(lesson["done"] for lesson in section["lessons"])
    previews = [lesson for lesson in flat if lesson["preview"]]
    if preview:
        prev = next((lesson for lesson in reversed(previews) if lesson["n"] < current["n"]), None)
        following = next((lesson for lesson in previews if lesson["n"] > current["n"]), None)
    else:
        prev = flat[index - 1] if index else None
        following = flat[index + 1] if index + 1 < total else None
    detail = _copy(course)
    return {
        "course": course,
        "detail": detail,
        "sections": sections,
        "current": current,
        "prev": prev,
        "next": following,
        "total": total,
        "done": done,
        "pct": round(done / total * 100) if total else 0,
        "section_count": len(sections),
        "note": None if preview else _lesson_note(course, current),
        "preview": preview,
        "locked": preview and not current["preview"],
        "previews": previews,
        "preview_count": len(previews),
        "locked_count": total - len(previews),
        "learn_top": detail["learn"][:3],
    }


def _lesson_note(course, lesson):
    if course["slug"] != DEFAULT_CART_SLUG or lesson["n"] != LIBRARY_DONE[DEFAULT_CART_SLUG] + 1:
        return None
    return {
        "text": "Bu dersteki örneği kendi projemde bir kez daha yazacağım.",
        "scope_label": "Bu ders",
        "date": "12 Eki 2026",
    }


def cart_slugs(session):
    """Sepetteki kurs slug'ları; geçerlilik ve sahiplik page.content.cart_cards'ta denetlenir."""
    return list(session.get(CART_SESSION_KEY, []))


def cart_add(session, slug):
    slugs = cart_slugs(session)
    if slug not in slugs:
        slugs.append(slug)
    session[CART_SESSION_KEY] = slugs


def cart_remove(session, slug):
    session[CART_SESSION_KEY] = [item for item in cart_slugs(session) if item != slug]


def cart_courses(session):
    return [course_by_slug(slug) for slug in cart_slugs(session)]


def cart_suggestions(items):
    in_cart = {item["slug"] for item in items}
    return [course for course in course_catalog() if course["slug"] not in in_cart and not course["owned"]]


def courses_by_slugs(slugs):
    return [course for course in (course_by_slug(slug) for slug in slugs) if course]


def place_order(session, items, email, from_cart):
    purchased = session.get(PURCHASED_SESSION_KEY, [])
    session[PURCHASED_SESSION_KEY] = purchased + [item["slug"] for item in items if item["slug"] not in purchased]
    session[ORDER_SESSION_KEY] = {
        "slugs": [item["slug"] for item in items],
        "coupon": session.pop(COUPON_SESSION_KEY, None),
        "email": email,
    }
    if from_cart:
        session[CART_SESSION_KEY] = []


def price_amount(price):
    return float(price.replace("€", "").replace(",", ""))


def money(amount):
    return f"€{amount:.2f}"


def order_summary(items, coupon=None):
    subtotal = sum(price_amount(item["price"]) for item in items)
    pct = COUPONS.get(coupon, 0)
    discount = round(subtotal * pct / 100, 2)
    return {
        "items": items,
        "count": len(items),
        "count_text": f"{len(items)} kurs",
        "subtotal": money(subtotal),
        "coupon": coupon if pct else None,
        "coupon_pct": pct,
        "discount": money(discount),
        "total": money(subtotal - discount),
    }


def purchase_steps(active):
    labels = ("Sepet", "Ödeme", "Tamamlandı")
    # Geri dönülebilen adım yalnız sepet; tamamlanmış ödemeye geri gidilmez.
    urls = (reverse("page:cart"), None, None)
    steps = []
    for index, label in enumerate(labels):
        done = index < active
        current = index == active
        if current:
            box_cls = "bg-primary text-white"
            text_cls = "text-body"
        elif done:
            box_cls = "bg-primary-subtle text-primary-emphasis"
            text_cls = "text-body-secondary"
        else:
            box_cls = "border text-body-tertiary"
            text_cls = "text-body-tertiary"
        steps.append(
            {
                "label": label,
                "num": str(index + 1),
                "done": done,
                "current": current,
                "url": urls[index] if done else None,
                "sep": index < len(labels) - 1,
                "box_cls": box_cls,
                "text_cls": text_cls,
            }
        )
    return steps


def _last_watched(slug):
    moment = LAST_WATCHED.get(slug)
    return timezone.make_aware(datetime(*moment)) if moment else None


def _owned_row(course, flat, done):
    total = len(flat)
    continue_at = flat[min(done, total - 1)]
    pct = round(done / total * 100) if total else 0
    if done >= total and total:
        state_label = "Tamamlandı"
        state_cls = "bg-success-subtle text-success-emphasis"
        cta = "Kursu tekrar izle"
    elif done:
        state_label = "Devam ediyor"
        state_cls = "bg-primary-subtle text-primary-emphasis"
        cta = "Devam et"
    else:
        state_label = "Başlanmadı"
        state_cls = "bg-body-tertiary text-body-secondary"
        cta = "Başla"
    return {
        **course,
        "done": done,
        "total": total,
        "pct": pct,
        "continue_url": continue_at["url"],
        "continue_title": continue_at["title"],
        "continue_section": continue_at["section"],
        "continue_label": f"{continue_at['n']}. ders",
        "state_label": state_label,
        "state_cls": state_cls,
        "cta": cta,
        "finished": bool(total and done >= total),
        "last_watched": _last_watched(course["slug"]),
    }


def library_page(status):
    owned = []
    others = []
    for course in course_catalog():
        _sections, flat = curriculum(course["slug"])
        done = LIBRARY_DONE.get(course["slug"])
        if done is None:
            others.append(course)
            continue
        owned.append(_owned_row(course, flat, done))
    if status == "devam":
        shown = [course for course in owned if not course["finished"]]
    elif status == "bitti":
        shown = [course for course in owned if course["finished"]]
    else:
        status = ""
        shown = owned
    filters = []
    for key, label, rows in (
        ("", "Tümü", owned),
        ("devam", "Devam", [course for course in owned if not course["finished"]]),
        ("bitti", "Tamamlanan", [course for course in owned if course["finished"]]),
    ):
        url = reverse("page:library")
        if key:
            url = f"{url}?durum={key}"
        filters.append(
            {
                "label": label,
                "count": len(rows),
                "checked": key == status,
                "url": url,
            }
        )
    continue_course = next((course for course in owned if not course["finished"]), None)
    return {
        "owned": shown,
        "owned_count": len(owned),
        "others": others,
        "filters": filters,
        "continue_course": continue_course,
        "empty": not shown,
        "notes": _library_notes(),
        "summary": f"{len(owned)} kurs · örnek ilerleme",
    }


def _library_notes():
    page = find_lesson(
        DEFAULT_CART_SLUG,
        *_continue_slugs(DEFAULT_CART_SLUG),
    )
    if page is None or page["note"] is None:
        return []
    lesson = page["current"]
    note = page["note"]
    return [
        {
            **note,
            "url": lesson["url"],
            "where": f"{lesson['section']} · {lesson['title']}",
            "scope_cls": "bg-primary-subtle text-primary-emphasis",
        }
    ]


def _continue_slugs(slug):
    _sections, flat = curriculum(slug)
    done = LIBRARY_DONE.get(slug, 0)
    lesson = flat[min(done, len(flat) - 1)]
    return lesson["section_slug"], lesson["lesson_slug"]


# [PLACEHOLDER: hukuki metin] Başlıklar yer tutucudur; yayından önce hukuki incelemeden geçmeli.
LEGAL_UPDATED = "28 Ekim 2026"

_PRIVACY = (
    (
        "Veri sorumlusu",
        "Bu politika, hakanyalcinkaya.dev üzerinden sunulan kurslar kapsamında işlenen kişisel verilerin nasıl toplandığını ve kullanıldığını açıklar. Veri sorumlusu Hakan Yalçınkaya’dır.",
    ),
    (
        "Topladığımız veriler",
        "Hesap oluştururken verdiğin ad ve e-posta adresi, satın aldığın kurslar, ders ilerlemen ve aldığın notlar. Ödeme bilgilerin ödeme sağlayıcısı tarafından işlenir; kart bilgilerin bize ulaşmaz.",
    ),
    (
        "Verileri hangi amaçla kullanıyoruz",
        "Kurslara erişimini sağlamak, ilerlemeni kaydetmek, siparişlerini yönetmek ve izin verdiysen yeni kurslardan haberdar etmek için.",
    ),
    (
        "Verilerin aktarılması",
        "Veriler yalnızca hizmetin çalışması için gereken sağlayıcılarla (barındırma, ödeme, e-posta gönderimi) paylaşılır. Satılmaz ve reklam amacıyla aktarılmaz.",
    ),
    (
        "Saklama süresi",
        "Hesabın açık olduğu sürece ve yasal yükümlülüklerin gerektirdiği süre boyunca saklanır. Hesabını kapattığında veriler makul süre içinde silinir ya da anonimleştirilir.",
    ),
    (
        "Çerezler",
        "Oturumunu açık tutmak, sepetini hatırlamak ve tema tercihini saklamak için zorunlu çerezler ve tarayıcı depolaması kullanılır.",
    ),
    (
        "Hakların",
        "KVKK’nın 11. maddesi kapsamında verilerine erişme, düzeltilmesini ya da silinmesini isteme ve işlemeye itiraz etme hakkın vardır.",
    ),
    (
        "İletişim",
        "Bu politika hakkındaki soruların için iletişim adresine yazabilirsin. [PLACEHOLDER: iletişim e-postası]",
    ),
)

_TERMS = (
    (
        "Kapsam",
        "Bu şartlar, hakanyalcinkaya.dev üzerindeki kurslara erişimini ve siteyi kullanımını düzenler. Siteyi kullanarak bu şartları kabul etmiş olursun.",
    ),
    (
        "Hesap",
        "Hesap bilgilerinin doğru olmasından ve şifrenin gizliliğinden sen sorumlusun. Hesabın kişiseldir, başkasıyla paylaşılamaz.",
    ),
    (
        "Satın alma ve erişim",
        "Satın aldığın kursa ödeme onaylandıktan sonra erişebilirsin. Fiyatlar ödeme adımında gösterilen tutardır; indirim kodları tek siparişte geçerlidir.",
    ),
    (
        "İade",
        "İade koşulları ve süresi burada açıklanacak. [PLACEHOLDER: iade politikası]",
    ),
    (
        "Fikri mülkiyet",
        "Kurs videoları, kaynak kodları ve materyaller kişisel öğrenim içindir. İzin olmadan kopyalanamaz, paylaşılamaz ya da yeniden satılamaz.",
    ),
    (
        "Sorumluluğun sınırı",
        "Kurs içeriği eğitim amaçlıdır. İçerikteki örneklerin kendi projelerinde kullanılmasından doğan sonuçlardan site sorumlu tutulamaz.",
    ),
    (
        "Değişiklikler",
        "Bu şartlar güncellenebilir. Önemli değişiklikler e-posta ile ya da site üzerinden duyurulur.",
    ),
)


_COOKIES = (
    (
        "Çerez nedir?",
        "Çerezler, bir siteyi ziyaret ettiğinde tarayıcına kaydedilen küçük metin dosyalarıdır. Tarayıcı depolaması da benzer şekilde bilgiyi yalnız senin cihazında saklar.",
    ),
    (
        "Kullandığımız çerezler",
        "Sitede yalnız hizmetin çalışması için zorunlu çerezler ve senin seçtiğin tercihleri hatırlayan tarayıcı kayıtları kullanılır.",
        (
            ("sessionid", "Zorunlu çerez", "Oturumunu açık tutar; sepetini ve siparişini hatırlar.", "2 hafta"),
            ("csrftoken", "Zorunlu çerez", "Formları sahte isteklere karşı korur.", "1 yıl"),
            ("messages", "Zorunlu çerez", "“Kaydedildi” gibi bildirimleri bir sonraki sayfaya taşır.", "Bir sonraki sayfaya kadar"),
            ("site-theme, site-accent", "Tarayıcı depolaması (tercih)", "Seçtiğin tema ve vurgu rengini hatırlar.", "Sen silene kadar"),
        ),
    ),
    (
        "Analitik ve reklam çerezleri",
        "Şu an ziyaretini ölçen ya da reklam amaçlı çerez kullanılmıyor. İleride eklenirse yüklenmeden önce iznin istenecek ve tercihini istediğin zaman değiştirebileceksin.",
    ),
    (
        "Çerezleri yönetmek",
        "Çerezleri tarayıcı ayarlarından silebilir ya da engelleyebilirsin. Zorunlu çerezleri engellersen giriş, sepet ve ödeme çalışmaz.",
    ),
    (
        "İletişim",
        "Çerezlerle ilgili soruların için iletişim adresine yazabilirsin. [PLACEHOLDER: iletişim e-postası]",
    ),
)

COOKIE_COLUMNS = ("Ad", "Tür", "Amaç", "Süre")

LEGAL_DOCUMENTS = (
    (
        "privacy",
        "page:privacy",
        "Gizlilik Politikası",
        "Kişisel verilerini nasıl topladığımızı, kullandığımızı ve koruduğumuzu açıklar.",
        _PRIVACY,
    ),
    ("terms", "page:terms", "Kullanım Şartları", "Siteyi ve kursları kullanırken geçerli olan kurallar.", _TERMS),
    (
        "cookies",
        "page:cookies",
        "Çerez Politikası",
        "Sitede hangi çerezlerin ve tarayıcı kayıtlarının neden kullanıldığını açıklar.",
        _COOKIES,
    ),
)


def _legal_sections(rows):
    sections = []
    for index, row in enumerate(rows, start=1):
        title, text, *table = row
        sections.append(
            {
                "id": f"madde-{index}",
                "title": title,
                "text": text,
                "columns": COOKIE_COLUMNS if table else (),
                "rows": table[0] if table else (),
            }
        )
    return sections


def legal_page(kind):
    for key, url_name, title, intro, rows in LEGAL_DOCUMENTS:
        if key == kind:
            break
    others = [
        {"url": reverse(other_url), "label": label}
        for other, other_url, label, _intro, _rows in LEGAL_DOCUMENTS
        if other != kind
    ]
    return {
        "title": title,
        "intro": intro,
        "updated": LEGAL_UPDATED,
        "sections": _legal_sections(rows),
        "others": others,
    }
