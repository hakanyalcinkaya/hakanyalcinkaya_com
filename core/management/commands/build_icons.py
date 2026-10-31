"""Bootstrap Icons'tan yalnız kodda kullanılan ikonları içeren font ve CSS'i üretir (static_files/icons/, git'e girmez).

İkon listesi değişmediyse dosyalara dokunmaz. Geliştirmede runserver kendiliğinden çalıştırır; sunucuda deploy betiği.
Deploy betiği çıktıdaki "yeniden üretildi" ifadesine bakıp collectstatic çalıştırır.

Örnek:
    python manage.py build_icons
    python manage.py build_icons --force
"""

from django.core.management.base import BaseCommand

from core import icons


class Command(BaseCommand):
    help = "Kullanılan Bootstrap ikonlarıyla küçük ikon fontu ve CSS'i üretir."

    def add_arguments(self, parser):
        parser.add_argument("--force", action="store_true", help="İkon listesi değişmemiş olsa da yeniden üret.")

    def handle(self, force, **options):
        built, count = icons.build(force=force)
        if not built:
            self.stdout.write(f"İkonlar güncel ({count} ikon).")
            return
        size = (icons.OUTPUT_FONT.stat().st_size + icons.OUTPUT_CSS.stat().st_size) / 1024
        self.stdout.write(self.style.SUCCESS(f"İkonlar yeniden üretildi: {count} ikon, {size:.1f} KB."))
