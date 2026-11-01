"""Django'nun şifre doğrulayıcıları, sitenin diliyle ("şifre", "sen"): hazır çeviriler "parola" ve "Parolanız" diyordu.
AUTH_PASSWORD_VALIDATORS bunları kullanır; kurallar Django'nunkilerle aynı."""

from django.contrib.auth import password_validation


class MinimumLengthValidator(password_validation.MinimumLengthValidator):
    def get_error_message(self):
        return f"Şifren en az {self.min_length} karakter olmalı."

    def get_help_text(self):
        return f"En az {self.min_length} karakter."


class UserAttributeSimilarityValidator(password_validation.UserAttributeSimilarityValidator):
    def get_error_message(self):
        return "Şifren %(verbose_name)s ile çok benzer; farklı bir şifre seç."

    def get_help_text(self):
        return "Şifren adına ya da e-posta adresine benzememeli."


class CommonPasswordValidator(password_validation.CommonPasswordValidator):
    def get_error_message(self):
        return "Bu şifre çok yaygın; tahmin edilmesi zor bir şifre seç."

    def get_help_text(self):
        return "Yaygın bir şifre olmamalı."


class NumericPasswordValidator(password_validation.NumericPasswordValidator):
    def get_error_message(self):
        return "Şifren yalnız rakamlardan oluşamaz."

    def get_help_text(self):
        return "Yalnız rakamlardan oluşmamalı."
