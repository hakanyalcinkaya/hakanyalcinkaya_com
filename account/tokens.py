"""Şifre belirleme bağlantılarının belirteçleri. Şifremi unuttum ve satın alma onayı Django'nun belirtecini kullanır
(PASSWORD_RESET_TIMEOUT, 1 saat); Podia daveti ayrı tuzlu, 3 gün geçerli belirteçle gider. Sıfırlama sayfası ikisini de kabul eder."""

from django.contrib.auth.tokens import PasswordResetTokenGenerator, default_token_generator
from django.utils.crypto import constant_time_compare
from django.utils.http import base36_to_int

INVITE_TIMEOUT = 3 * 24 * 60 * 60


class InviteTokenGenerator(PasswordResetTokenGenerator):
    """Podia daveti: 3 gün geçerli. Ayrı tuz sayesinde normal sıfırlama belirteci bununla uzatılamaz; şifre belirlenince
    (parola özeti değişince) Django'nunki gibi geçersiz olur."""

    key_salt = "account.tokens.InviteTokenGenerator"

    def check_token(self, user, token):
        # Django'nun check_token'ı ile aynı; tek fark süre (PASSWORD_RESET_TIMEOUT yerine INVITE_TIMEOUT).
        if not (user and token):
            return False
        try:
            ts_b36, _hash = token.split("-")
            ts = base36_to_int(ts_b36)
        except ValueError:
            return False
        if not any(
            constant_time_compare(self._make_token_with_timestamp(user, ts, secret), token)
            for secret in [self.secret, *self.secret_fallbacks]
        ):
            return False
        return self._num_seconds(self._now()) - ts <= INVITE_TIMEOUT


invite_token_generator = InviteTokenGenerator()


class ResetOrInviteTokenGenerator:
    """Şifre sıfırlama sayfası (page.views.PasswordResetConfirmView): Şifremi unuttum ya da davet belirteci."""

    def check_token(self, user, token):
        return default_token_generator.check_token(user, token) or invite_token_generator.check_token(user, token)

    def make_token(self, user):
        return default_token_generator.make_token(user)
