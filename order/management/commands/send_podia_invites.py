"""Podia'dan aktarılan müşterilere "Hesabın taşındı" e-postası (şifre belirleme bağlantısı ve aktarılan kursları).

Önce aktarım (import_podia), kontrol, sonra bu komut. Her e-posta mailing.EmailLog'a yazılır; e-postayı almış olan
kişiye ikinci kez gönderilmez (--resend hariç). Örnek:
    python manage.py send_podia_invites --dry-run
    python manage.py send_podia_invites --email ali@example.com
    python manage.py send_podia_invites --limit 20
    python manage.py send_podia_invites
"""

import smtplib

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from mailing.emails import send_email
from order.emails import account_migrated_context
from order.podia import invite_candidates, unpublished_imported_courses

# Deneme modunda listelenen en çok kişi (kalanı sayıyla).
DRY_RUN_SHOWN = 20


class Command(BaseCommand):
    help = "Podia'dan aktarılan müşterilere hesap taşındı (şifre belirleme) e-postası gönderir."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Göndermeden kimlere gideceğini listele.")
        parser.add_argument("--email", help="Yalnız bu adrese (aktarılan müşterilerden biri olmalı).")
        parser.add_argument("--limit", type=int, help="En çok bu kadar kişiye gönder (parça parça göndermek için).")
        parser.add_argument("--resend", action="store_true", help="Daha önce gönderilmiş olanlara da gönder.")
        parser.add_argument(
            "--allow-unpublished", action="store_true", help="Yayında olmayan aktarılmış kurs varken de gönder."
        )

    def handle(self, dry_run, email, limit, resend, allow_unpublished, **options):
        users = invite_candidates(resend=resend)
        if email:
            users = users.filter(email__iexact=email.strip())
            if not users.exists():
                raise CommandError(f"{email}: aktarılan müşterilerde yok ya da e-postası zaten gönderilmiş (--resend).")
        total = users.count()
        if limit:
            users = users[:limit]
        users = list(users)

        unpublished = list(unpublished_imported_courses())
        for course in unpublished:
            self.stdout.write(self.style.WARNING(f"Yayında değil: {course.title} ({course.slug}) — alıcılar derslere ulaşamaz."))
        if settings.EMAIL_REDIRECT_TO:
            self.stdout.write(self.style.WARNING(f"Test modu: e-postaların hepsi {settings.EMAIL_REDIRECT_TO} adresine gider."))

        if dry_run:
            self.stdout.write(self.style.WARNING("DENEME (hiçbir e-posta gönderilmedi)"))
            for user in users[:DRY_RUN_SHOWN]:
                self.stdout.write(f"  {user.email}{'' if user.has_usable_password() else '  (şifresi yok)'}")
            if len(users) > DRY_RUN_SHOWN:
                self.stdout.write(f"  ... ve {len(users) - DRY_RUN_SHOWN} kişi daha")
            self.stdout.write(f"Gönderilecek: {len(users)} / bekleyen {total}")
            return
        if unpublished and not allow_unpublished:
            raise CommandError("Yayında olmayan kurs var; önce yayınla ya da --allow-unpublished ile gönder.")

        sent = failed = 0
        for user in users:
            try:
                send_email("account_migrated", user.email, account_migrated_context(user), user=user)
            except (smtplib.SMTPException, OSError) as error:
                failed += 1
                self.stdout.write(self.style.ERROR(f"  {user.email}: {error}"))
                continue
            sent += 1
            self.stdout.write(f"  {user.email}")
        style = self.style.SUCCESS if not failed else self.style.WARNING
        self.stdout.write(style(f"Gönderildi: {sent}, hata: {failed}, kalan: {total - sent}"))
