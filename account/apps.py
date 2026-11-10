from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class AccountConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "account"
    verbose_name = _("Hesaplar")

    def ready(self):
        from django.contrib.auth.signals import user_logged_in

        from account.tracking import record_login

        user_logged_in.connect(record_login, dispatch_uid="account_record_login")
