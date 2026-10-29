"""Başka platformdan çekilmiş yorumları (Markdown) kursa onaylı eski yorum olarak aktarır.

Örnek:
    python manage.py import_reviews udemy-react-yorumlar.md --course react --dry-run
"""

from django.core.management.base import BaseCommand, CommandError

from course.models import Course
from course.review_import import ReviewFileError, import_reviews, parse_reviews


class Command(BaseCommand):
    help = "Yorum dosyasını kursa aktarır; tekrar çalıştırılabilir (aynı ad ve metin ikinci kez eklenmez, eski kayıt düzeltilir)."

    def add_arguments(self, parser):
        parser.add_argument("path", help="Yorum dosyası (.md)")
        parser.add_argument("--course", required=True, help="Hedef kursun slug'ı")
        parser.add_argument("--dry-run", action="store_true", help="Hiçbir şey kaydetmeden raporla.")

    def handle(self, path, course, dry_run, **options):
        target = Course.objects.filter(slug=course).first()
        if target is None:
            raise CommandError(f"Bu slug'la kurs yok: {course}")
        try:
            with open(path, encoding="utf-8") as handle:
                reviews = parse_reviews(handle.read())
        except OSError as error:
            raise CommandError(f"Dosya okunamadı: {error}") from error
        except ReviewFileError as error:
            raise CommandError(str(error)) from error
        added, fixed, skipped = import_reviews(target, reviews, dry_run=dry_run)
        ratings = sorted({item.rating for item in reviews})
        self.stdout.write(
            ("[deneme, kaydedilmedi] " if dry_run else "")
            + f"{target.title}: {len(reviews)} yorum okundu, {added} eklendi, {fixed} düzeltildi, {skipped} zaten vardı (puanlar: {ratings})."
        )
