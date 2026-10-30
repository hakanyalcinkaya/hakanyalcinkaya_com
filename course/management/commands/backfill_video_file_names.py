"""Dosya adı tutulmadan önce yüklenen videoların dosya adını derse yazar (ek bilgi / altyazı eşleştirmesi ve stüdyoda gösterim).

Kaynak sırası: kuyrukta duran son yükleme işi, yoksa platformdaki video başlığı (ders adına çevrilmediyse dosya adından gelir).

Örnek:
    python manage.py backfill_video_file_names --dry-run
"""

from collections import Counter

from django.core.management.base import BaseCommand

from course.models import Lesson


class Command(BaseCommand):
    help = "Videolu derslerde boş olan video dosya adını son yüklemeden ya da platformdaki video başlığından doldurur."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Hiçbir şey kaydetmeden raporla.")

    def handle(self, dry_run, **options):
        lessons = (
            Lesson.objects.exclude(video_id="")
            .filter(video_file_name="")
            .select_related("section__course")
            .prefetch_related("video_uploads")
        )
        counts = Counter()
        for lesson in lessons:
            upload = lesson.latest_upload
            if upload and upload.original_name:
                source, name = "yükleme", upload.original_name
            elif lesson.video_title and lesson.video_title != lesson.title:
                source, name = "video başlığı", lesson.video_title
            else:
                counts["bulunamadı"] += 1
                self.stdout.write(f"  bulunamadı: {lesson.section.course.short_title} · {lesson.title}")
                continue
            counts[source] += 1
            if not dry_run:
                Lesson.objects.filter(pk=lesson.pk).update(video_file_name=name[:255])
        self.stdout.write(
            ("[deneme, kaydedilmedi] " if dry_run else "")
            + f"{sum(counts.values())} ders: {counts['yükleme']} yüklemeden, {counts['video başlığı']} video başlığından, "
            f"{counts['bulunamadı']} bulunamadı."
        )
