"""Kurs ve ders sayfalarının veritabanından gelen kısmı: tanıtım videosu, müfredat (bölüm/ders) ve ders oynatıcısı.

Şablonlar örnek verideki (catalog.py) sözlük biçimini bekler; burada modelden aynı biçim üretilir. Kursun tanıtım
metinleri (neler öğreneceksin, kimler için ...) aynı slug'lı örnek kurs varsa oradan, yoksa kurs maddelerinden gelir.
Taslak kurs, bölüm ve dersler yalnız personele görünür (stüdyodan yükleneni yayına almadan denemek için).
"""

import json

from django.db.models import Prefetch
from django.urls import reverse

from core.duration import ceil_minutes, clock, hours_minutes
from core.money import format_try
from core.models import Status
from course.models import Course, HighlightKind, Lesson, LessonKind, LessonSubtitle, SubtitleStatus
from learning.models import LessonProgress
from page import catalog

FALLBACK_IMAGE = "img/courses/react.jpg"
LESSON_FORMAT_KEYS = {LessonKind.VIDEO: "video", LessonKind.FORM: "form", LessonKind.TEXT: "text"}


def visible_course(slug, user):
    courses = Course.objects.all() if user.is_staff else Course.objects.published()
    return courses.filter(slug=slug).first()


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
        card = {
            "slug": course.slug,
            "url": course.get_absolute_url(),
            "cart_url": reverse("page:add_to_cart", kwargs={"slug": course.slug}),
            "buy_url": reverse("page:buy", kwargs={"slug": course.slug}),
            "image": FALLBACK_IMAGE,
            "alt": f"{course.title} kursunun kapak görseli",
            "tags": [technology.name for technology in course.technologies.all()],
        }
    minutes = sum(ceil_minutes(item["seconds"]) for item in flat)
    preview = course.preview_player or {}
    card.update(
        title=course.title,
        short=course.short_title,
        price=format_try(course.price),
        lessons=len(flat),
        duration=hours_minutes(minutes),
        preview_video=preview.get("src", ""),
        preview_poster=preview.get("poster", ""),
        preview_platform=preview.get("platform", ""),
    )
    return card


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
        "others": [item for item in catalog.course_catalog() if item["slug"] != course.slug],
    }


def _player(lesson):
    """Ders oynatıcısının verisi: platform, adres, kapak görseli ve hazır altyazılar (Video.js <track>).

    Vimeo altyazıları kendi oynatıcısında yüklendiği için yalnız Bunny videolarında <track> verilir.
    """
    player = lesson.player
    if player is None:
        return None
    service = lesson.video_service
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
        section["open"] = section["current"]
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
