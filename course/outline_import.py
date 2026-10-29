"""Kurs içeriğini (bilgiler, sayfa maddeleri, bölüm ve ders başlıkları) bir taslak dosyasından aktarır (course/outlines/*.json).

Tekrar çalıştırılabilir. Bölüm ve dersler slug'larıyla eşleşir; eski platformdaki slug'la (legacy_slug, ör.
"2383524-baslangic") açılmış olanlar yeni slug'a ("baslangic") çevrilir. Eski adresler legacy_slug'la yönlendirilir. Var olan derslerin videoları korunur. Videoları daha önce dosya
adıyla açılmış dersler ("001-002-...") sıra numarasıyla taslaktaki derse bağlanır (1. bölüm, 2. ders). Taslakta karşılığı
olmayan dersler silinmez, sona "Eşleşmeyen dersler" bölümüne taşınır.

Kurs bilgileri ve sayfa maddeleri yalnız boşsa doldurulur (replace_info ile üzerine yazılır); stüdyoda yapılan düzenlemeler
ikinci çalıştırmada bozulmaz. Yeni bölümler yayında, yeni dersler taslak açılır; ders yayını stüdyodan yapılır.
"""

import re
from collections import Counter
from pathlib import Path

from django.contrib.staticfiles import finders
from django.core.files import File
from django.db import transaction

from core.models import Status
from course.models import LEFTOVER_SECTION_SLUG, CourseHighlight, HighlightKind, Lesson, LessonKind, Section, Technology

FILE_NUMBER = re.compile(r"^(\d{3})-(\d{3})(?!\d)")
INFO_FIELDS = ("title", "short_title", "subtitle", "description", "access_note")


class OutlineError(Exception):
    pass


def _number_key(title):
    match = FILE_NUMBER.match(title)
    return (int(match.group(1)), int(match.group(2))) if match else None


def _fill_info(course, outline, replace, dry_run, report):
    changed = []
    for name in INFO_FIELDS:
        value = (outline.get(name) or "").strip()
        if value and (replace or not getattr(course, name)):
            setattr(course, name, value[: course._meta.get_field(name).max_length or None])
            changed.append(name)
    if outline.get("image") and (replace or not course.image):
        found = finders.find(outline["image"])
        if found and dry_run:
            changed.append("image")
        elif found:
            with open(found, "rb") as handle:
                course.image.save(Path(found).name, File(handle), save=False)
            changed.append("image")
        else:
            report["warnings"].append(f"Görsel bulunamadı: {outline['image']}")
    if changed:
        course.save()
    report["info"] = changed
    for name in outline.get("technologies", ()):
        technology = Technology.objects.filter(name__iexact=name).first() or Technology.objects.create(name=name)
        course.technologies.add(technology)


def _fill_highlights(course, highlights, replace, report):
    existing = course.highlights.exists()
    if existing and not replace:
        report["highlights"] = 0
        return
    course.highlights.all().delete()
    items = []
    for kind in HighlightKind.values:
        for entry in highlights.get(kind, ()):
            title, text = (entry.get("title", ""), entry.get("text", "")) if isinstance(entry, dict) else ("", entry)
            if text:
                items.append(CourseHighlight(course=course, kind=kind, title=title, text=text, sort_order=len(items)))
    CourseHighlight.objects.bulk_create(items)
    report["highlights"] = len(items)


def _sync_curriculum(course, sections, report):
    lessons = list(Lesson.objects.filter(section__course=course).select_related("section"))
    by_lesson_slug = {}
    for lesson in lessons:
        by_lesson_slug.setdefault(lesson.slug, []).append(lesson)
    by_number = {}
    for lesson in lessons:
        key = _number_key(lesson.title)
        if key:
            by_number.setdefault(key, []).append(lesson)
    used, counts = set(), Counter()
    for section_no, item in enumerate(sections, start=1):
        section = course.sections.filter(slug=item["slug"]).first()
        if section is None and item.get("legacy_slug"):
            section = course.sections.filter(slug=item["legacy_slug"]).first()
            if section is not None:
                section.slug = item["slug"]
                section.save(update_fields=["slug", "updated_at"])
                counts["section_renamed"] += 1
        if section is None:
            section = Section.objects.create(
                course=course, title=item["title"], slug=item["slug"], sort_order=section_no, status=Status.PUBLISHED
            )
            counts["section_created"] += 1
        elif section.sort_order != section_no:
            section.sort_order = section_no
            section.save(update_fields=["sort_order", "updated_at"])
        for lesson_no, entry in enumerate(item["lessons"], start=1):
            lesson = None
            for slug in filter(None, (entry["slug"], entry.get("legacy_slug"))):
                candidates = [found for found in by_lesson_slug.get(slug, []) if found.pk not in used]
                # Önce aynı bölümdeki, yoksa kursta bu slug'lı tek ders.
                lesson = next((found for found in candidates if found.section_id == section.pk), None) or (
                    candidates[0] if len(candidates) == 1 else None
                )
                if lesson is not None:
                    break
            if lesson is not None and lesson.slug != entry["slug"]:
                lesson.slug = entry["slug"]
                counts["lesson_renamed"] += 1
            numbered = by_number.get((section_no, lesson_no), [])
            if lesson is not None:
                counts["lesson_kept"] += 1
            elif len(numbered) == 1 and numbered[0].pk not in used:
                # Videosu dosya adıyla yüklenmiş ders: taslaktaki başlığı ve adresi alır, videosu kalır.
                lesson = numbered[0]
                lesson.title, lesson.slug, lesson.is_preview = entry["title"], entry["slug"], entry["preview"]
                counts["lesson_matched_by_number"] += 1
            else:
                lesson = Lesson(
                    title=entry["title"],
                    slug=entry["slug"],
                    kind=LessonKind.TEXT if entry["kind"] == "text" else LessonKind.VIDEO,
                    is_preview=entry["preview"],
                )
                counts["lesson_created"] += 1
            lesson.section, lesson.sort_order = section, lesson_no
            lesson.save()
            used.add(lesson.pk)
    leftovers = [lesson for lesson in lessons if lesson.pk not in used]
    if leftovers:
        section, _created = course.sections.get_or_create(
            slug=LEFTOVER_SECTION_SLUG,
            defaults=dict(title="Eşleşmeyen dersler", sort_order=len(sections) + 1, status=Status.DRAFT),
        )
        start = section.next_lesson_order()
        for offset, lesson in enumerate(leftovers):
            lesson.move_to(section.pk, start + offset)
        report["warnings"].append(f"{len(leftovers)} ders taslakta yok; “Eşleşmeyen dersler” bölümüne taşındı.")
    keep = {item["slug"] for item in sections} | {LEFTOVER_SECTION_SLUG}
    empty = course.sections.exclude(slug__in=keep).filter(lessons__isnull=True)
    counts["section_deleted"] = empty.count()
    empty.delete()
    report.update(counts)
    report["leftovers"] = len(leftovers)


def import_outline(course, outline, replace_info=False, dry_run=False):
    """Taslağı kursa uygular; rapor sözlüğü döner. dry_run'da hiçbir şey kaydedilmez."""
    sections = outline.get("sections")
    if not sections:
        raise OutlineError("Taslakta bölüm yok.")
    slugs = [item["slug"] for item in sections]
    if len(slugs) != len(set(slugs)):
        raise OutlineError("Taslakta aynı slug'lı iki bölüm var.")
    report = dict(warnings=[])
    with transaction.atomic():
        _fill_info(course, outline, replace_info, dry_run, report)
        _fill_highlights(course, outline.get("highlights", {}), replace_info, report)
        _sync_curriculum(course, sections, report)
        if dry_run:
            transaction.set_rollback(True)
    return report
