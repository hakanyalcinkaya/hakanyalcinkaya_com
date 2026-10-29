"""Kurs taslağını (course/outlines/*.json) bir kursa aktarır: bilgiler, sayfa maddeleri, bölüm ve ders başlıkları.

Örnek:
    python manage.py import_course_outline course/outlines/sifirdan-projelerle-front-end-ve-react-18-x-ogren.json \\
        --course react --dry-run
"""

import json

from django.core.management.base import BaseCommand, CommandError

from course.models import Course
from course.outline_import import OutlineError, import_outline

REPORT_LABELS = (
    ("section_created", "yeni bölüm"),
    ("section_deleted", "silinen boş bölüm"),
    ("section_renamed", "adresi yenilenen bölüm"),
    ("lesson_renamed", "adresi yenilenen ders"),
    ("lesson_created", "yeni ders (taslak)"),
    ("lesson_kept", "var olan ders"),
    ("lesson_matched_by_number", "dosya numarasıyla eşleşen video"),
    ("leftovers", "eşleşmeyen ders"),
    ("highlights", "sayfa maddesi"),
)


class Command(BaseCommand):
    help = "Kurs taslağını kursa aktarır; tekrar çalıştırılabilir, videolar ve stüdyo düzenlemeleri korunur."

    def add_arguments(self, parser):
        parser.add_argument("path", help="Taslak dosyası (course/outlines/*.json)")
        parser.add_argument("--course", required=True, help="Hedef kursun slug'ı")
        parser.add_argument("--replace-info", action="store_true", help="Kurs bilgilerini ve sayfa maddelerini üzerine yaz.")
        parser.add_argument("--dry-run", action="store_true", help="Hiçbir şey kaydetmeden raporla.")

    def handle(self, path, course, replace_info, dry_run, **options):
        try:
            with open(path, encoding="utf-8") as handle:
                outline = json.load(handle)
        except (OSError, ValueError) as error:
            raise CommandError(f"Taslak okunamadı: {error}") from error
        target = Course.objects.filter(slug=course).first()
        if target is None:
            raise CommandError(f"Bu slug'la kurs yok: {course}. Kursu önce stüdyodan aç.")
        try:
            report = import_outline(target, outline, replace_info=replace_info, dry_run=dry_run)
        except OutlineError as error:
            raise CommandError(str(error)) from error
        self.stdout.write(("[deneme, kaydedilmedi] " if dry_run else "") + f"{target.title} ({target.slug})")
        if report["info"]:
            self.stdout.write("  güncellenen bilgiler: " + ", ".join(report["info"]))
        for key, label in REPORT_LABELS:
            if report.get(key):
                self.stdout.write(f"  {label}: {report[key]}")
        for warning in report["warnings"]:
            self.stdout.write(self.style.WARNING(f"  uyarı: {warning}"))
