"""Ziyaretçi kayıtlarında (sepete ekleme, kayıt, giriş, ders izleme, sayfa ziyareti, özel indirim isteği) IP_RETENTION_DAYS günden eski IP'leri maskeler; ülke, şehir,
cihaz ve diğer bilgiler kalır. Sunucuda cron her gece çalıştırır (_server/README.md, "IP maskeleme"). Örnek:
    python manage.py mask_visitor_ips
    python manage.py mask_visitor_ips --dry-run     # yalnız kaç kayıt maskeleneceğini yaz
"""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from account.models import AccountEvent, PageView
from cart.models import CartAddEvent
from core.visitor import IP_RETENTION_DAYS
from discount.models import PersonalDiscountRequest
from learning.models import LessonView

MODELS = (CartAddEvent, AccountEvent, LessonView, PageView, PersonalDiscountRequest)


class Command(BaseCommand):
    help = f"{IP_RETENTION_DAYS} günden eski ziyaretçi kayıtlarındaki IP adreslerini maskeler."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Maskelemeden yalnız sayıyı yaz.")

    def handle(self, dry_run, **options):
        now = timezone.now()
        cutoff = now - timedelta(days=IP_RETENTION_DAYS)
        for model in MODELS:
            rows = model.objects.unmasked_before(cutoff)
            if dry_run:
                self.stdout.write(f"{model._meta.verbose_name_plural}: {rows.count()} kayıt maskelenecek.")
                continue
            total = 0
            for event in rows.only("pk", "data").iterator(chunk_size=500):
                event.mask_ip(now)
                total += 1
            self.stdout.write(self.style.SUCCESS(f"{model._meta.verbose_name_plural}: {total} kaydın IP'si maskelendi."))
