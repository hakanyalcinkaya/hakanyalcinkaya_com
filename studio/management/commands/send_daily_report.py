"""Günlük rapor e-postası (studio.daily_report): biten günün özeti DAILY_REPORT_TO adresine. Sunucuda cron her gece
Türkiye saatiyle 00:00'da çalıştırır (_server/README.md, "Günlük rapor"). Örnek:
    python manage.py send_daily_report                      # dün (yerel saat)
    python manage.py send_daily_report --date 2026-11-02
    python manage.py send_daily_report --dry-run            # göndermeden düz metni yaz
    python manage.py send_daily_report --to ali@example.com
"""

import smtplib
from datetime import date

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from mailing.emails import render_email, send_email
from studio.daily_report import build, report_day


class Command(BaseCommand):
    help = "Biten günün raporunu yöneticiye e-postayla gönderir."

    def add_arguments(self, parser):
        parser.add_argument("--date", type=date.fromisoformat, help="Raporun günü (YYYY-AA-GG); verilmezse dün.")
        parser.add_argument("--to", help="Alıcı; verilmezse DAILY_REPORT_TO.")
        parser.add_argument("--dry-run", action="store_true", help="Göndermeden konuyu ve düz metni yaz.")

    def handle(self, date, to, dry_run, **options):
        context = build(date or report_day())
        to = to or settings.DAILY_REPORT_TO
        if dry_run:
            subject, text, _html = render_email("daily_report", context)
            self.stdout.write(f"Alıcı: {to}\nKonu: {subject}\n\n{text}")
            return
        try:
            send_email("daily_report", to, context)
        except (smtplib.SMTPException, OSError) as error:
            raise CommandError(f"Gönderilemedi: {error}") from error
        self.stdout.write(self.style.SUCCESS(f"{context['day_label']} raporu {to} adresine gönderildi."))
