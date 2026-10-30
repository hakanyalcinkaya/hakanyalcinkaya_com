"""Dosya adı tutulmadan önce yüklenen videoların dosya adını derse yazar (ek bilgi / altyazı eşleştirmesi ve stüdyoda gösterim).

Kaynak sırası: kuyrukta duran son yükleme işi, yoksa platformdaki video başlığı (ders adına çevrilmediyse dosya adından gelir).

--forget-learned: toplu ek bilgi / altyazı yüklemesinde eşleşmeden öğrenilmiş adları siler (yükleme işinden ya da video
başlığından gelmeyenler); yanlış eşleşmeyle öğrenilmiş ad sonraki yüklemeleri de yanlış derse götürür.

Örnek:
    python manage.py backfill_video_file_names --dry-run
    python manage.py backfill_video_file_names --forget-learned --course react --dry-run
"""

from collections import Counter

from django.core.management.base import BaseCommand, CommandError

from course.models import Course, Lesson


class Command(BaseCommand):
    help = "Videolu derslerde boş olan video dosya adını son yüklemeden ya da platformdaki video başlığından doldurur."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Hiçbir şey kaydetmeden raporla.")
        parser.add_argument("--forget-learned", action="store_true", help="Eşleşmeden öğrenilmiş dosya adlarını sil.")
        parser.add_argument("--course", help="Yalnız bu kurs (slug).")

    def handle(self, dry_run, forget_learned, course, **options):
        lessons = Lesson.objects.exclude(video_id="").select_related("section__course").prefetch_related("video_uploads")
        if course:
            target = Course.objects.filter(slug=course).first()
            if target is None:
                raise CommandError(f"Bu slug'la kurs yok: {course}")
            lessons = lessons.filter(section__course=target)
        prefix = "[deneme, kaydedilmedi] " if dry_run else ""
        if forget_learned:
            self.forget(lessons, dry_run, prefix)
        else:
            self.backfill(lessons.filter(video_file_name=""), dry_run, prefix)

    def backfill(self, lessons, dry_run, prefix):
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
            prefix
            + f"{sum(counts.values())} ders: {counts['yükleme']} yüklemeden, {counts['video başlığı']} video başlığından, "
            f"{counts['bulunamadı']} bulunamadı."
        )

    def forget(self, lessons, dry_run, prefix):
        forgotten = 0
        for lesson in lessons.exclude(video_file_name=""):
            sources = {upload.original_name for upload in lesson.video_uploads.all()}
            if lesson.video_title != lesson.title:
                sources.add(lesson.video_title)
            if lesson.video_file_name in sources:
                continue
            forgotten += 1
            self.stdout.write(f"  silinecek: {lesson.section.course.short_title} · {lesson.title} · {lesson.video_file_name}")
            if not dry_run:
                Lesson.objects.filter(pk=lesson.pk).update(video_file_name="")
        self.stdout.write(prefix + f"{forgotten} dersin öğrenilmiş dosya adı silindi.")
