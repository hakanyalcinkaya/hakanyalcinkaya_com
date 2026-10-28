from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.db.models.functions import Lower
from django.utils.translation import gettext_lazy as _


def lower_tr(text):
    """Türkçe küçük harf: İ → i, I → ı (str.lower() İ'yi "i̇" yapar)."""
    return text.replace("İ", "i").replace("I", "ı").lower()


class UserQuerySet(models.QuerySet):
    def with_email(self, email):
        return self.filter(email__iexact=email.strip())


class UserManager(BaseUserManager.from_queryset(UserQuerySet)):
    use_in_migrations = True

    def normalize_email(self, email):
        return super().normalize_email(email).strip().lower()

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError(_("E-posta adresi gerekli."))
        user = self.model(email=self.normalize_email(email), **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if not extra_fields["is_staff"] or not extra_fields["is_superuser"]:
            raise ValueError(_("Yönetici hesabında is_staff ve is_superuser açık olmalı."))
        return self._create_user(email, password, **extra_fields)


class User(AbstractUser):
    """Kullanıcı adı yerine e-posta ile giriş yapan hesap."""

    username = None
    email = models.EmailField(_("e-posta"), unique=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    class Meta:
        verbose_name = _("kullanıcı")
        verbose_name_plural = _("kullanıcılar")
        ordering = ("email",)
        constraints = [
            models.UniqueConstraint(Lower("email"), name="account_user_email_ci_unique"),
        ]

    def __str__(self):
        return self.email

    def clean(self):
        super().clean()
        self.email = type(self).objects.normalize_email(self.email)

    @property
    def display_name(self):
        return self.get_full_name() or self.email

    @property
    def initials(self):
        """Hesap rozeti, küçük harfle: ad ve soyadın baş harfleri; ikisi de yoksa e-postanın ilk iki harfi."""
        letters = "".join(name.strip()[:1] for name in (self.first_name, self.last_name) if name.strip())
        return lower_tr(letters or self.email[:2])
