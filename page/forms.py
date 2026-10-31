from crispy_forms.bootstrap import FieldWithButtons, StrictButton
from crispy_forms.helper import FormHelper
from crispy_forms.layout import HTML, Column, Hidden, Layout, Row
from django import forms
from django.contrib.auth import authenticate, password_validation
from django.contrib.auth import forms as auth_forms
from django.urls import reverse
from django.utils.html import format_html

from account.models import User
from discount.models import Discount
from learning.models import PlayerPreference

INPUT_CLASS = "form-control-lg fs-6"
LABEL_CLASS = "small fw-medium text-body-secondary"


def submit(label, icon="bi-arrow-right", css_class="btn-primary btn-lg fs-6 w-100"):
    return StrictButton(
        f'{label} <i class="bi {icon} ms-1" aria-hidden="true"></i>',
        type="submit",
        css_class=css_class,
    )


class StyledFormMixin:
    """Tasarımdaki form görünümü: büyük girdiler, küçük soluk etiketler, sunucu tarafı doğrulama."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if not isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault("class", INPUT_CLASS)
        self.helper = FormHelper(self)
        self.helper.label_class = LABEL_CLASS
        self.helper.attrs = {"novalidate": ""}


class StyledForm(StyledFormMixin, forms.Form):
    pass


def email_field(label="E-posta"):
    return forms.EmailField(
        label=label,
        error_messages={
            "required": "E-posta adresi gerekli.",
            "invalid": "Geçerli bir e-posta adresi gir.",
        },
        widget=forms.EmailInput(
            attrs={"autocomplete": "email", "inputmode": "email", "placeholder": "ornek@eposta.com"}
        ),
    )


def password_field(label, autocomplete, min_length=None):
    errors = {"required": "Şifre gerekli."}
    if min_length:
        errors["min_length"] = f"Şifre en az {min_length} karakter olmalı."
    return forms.CharField(
        label=label,
        min_length=min_length,
        strip=False,
        error_messages=errors,
        widget=forms.PasswordInput(attrs={"autocomplete": autocomplete}),
    )


def name_field(label="Ad soyad", placeholder="Adın", autocomplete="name", noun="adını"):
    message = f"Lütfen {noun} gir (en az 2 karakter)."
    return forms.CharField(
        label=label,
        min_length=2,
        error_messages={"required": message, "min_length": message},
        widget=forms.TextInput(attrs={"autocomplete": autocomplete, "placeholder": placeholder}),
    )


class NewsletterForm(StyledForm):
    name = name_field(label="İsim")
    email = email_field()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Row(Column("name", css_class="col-sm-6"), Column("email", css_class="col-sm-6")),
            submit("Abone Ol", icon="bi-send", css_class="btn-outline-secondary btn-lg fs-6 w-100"),
        )


class LoginForm(StyledForm):
    email = email_field()
    password = password_field("Şifre", "current-password")

    def __init__(self, *args, request=None, **kwargs):
        self.request = request
        self.user = None
        super().__init__(*args, **kwargs)
        self.helper.layout = Layout(
            "email",
            "password",
            HTML(
                format_html(
                    '<div class="d-flex justify-content-between gap-3 small mt-n2 mb-3">'
                    '<a href="{}">Kayıt ol</a><a href="{}">Şifremi unuttum</a></div>',
                    reverse("page:signup"),
                    reverse("page:password_reset"),
                )
            ),
            submit("Giriş Yap"),
        )

    def clean(self):
        cleaned = super().clean()
        email = cleaned.get("email")
        password = cleaned.get("password")
        if email and password:
            self.user = authenticate(self.request, email=email.strip().lower(), password=password)
            if self.user is None:
                raise forms.ValidationError("E-posta adresi ya da şifre hatalı.")
        return cleaned


class SignupForm(StyledFormMixin, forms.ModelForm):
    first_name = name_field(label="Ad", autocomplete="given-name")
    last_name = name_field(label="Soyad", placeholder="Soyadın", autocomplete="family-name", noun="soyadını")
    email = email_field()
    password = password_field("Şifre", "new-password", min_length=8)
    terms = forms.BooleanField(
        error_messages={"required": "Devam etmek için şartları kabul etmelisin."},
    )

    class Meta:
        model = User
        fields = ("first_name", "last_name", "email")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["password"].help_text = "En az 8 karakter."
        self.fields["terms"].label = format_html(
            '<a href="{}">Kullanım Şartları</a>’nı ve <a href="{}">Gizlilik Politikası</a>’nı okudum, kabul ediyorum.',
            reverse("page:terms"),
            reverse("page:privacy"),
        )
        self.helper.layout = Layout(
            Row(Column("first_name", css_class="col-sm-6"), Column("last_name", css_class="col-sm-6")),
            "email",
            "password",
            "terms",
            submit("Hesap oluştur"),
        )

    def clean_email(self):
        email = User.objects.normalize_email(self.cleaned_data["email"])
        if User.objects.with_email(email).exists():
            raise forms.ValidationError("Bu e-posta adresiyle bir hesap zaten var.")
        return email

    def _post_clean(self):
        super()._post_clean()
        # Şifre kuralları kullanıcının adı ve e-postasıyla birlikte değerlendirilir.
        password = self.cleaned_data.get("password")
        if password:
            try:
                password_validation.validate_password(password, self.instance)
            except forms.ValidationError as error:
                self.add_error("password", error)

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password"])
        if commit:
            user.save()
        return user


class PasswordResetForm(StyledFormMixin, auth_forms.PasswordResetForm):
    """Django'nun sıfırlama formu: kayıtlı adrese tek kullanımlık bağlantı gönderir, kayıtsız adreste sessiz kalır."""

    email = email_field()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper.layout = Layout("email", submit("Sıfırlama bağlantısı gönder", icon="bi-send"))

    def send_link(self, request):
        self.save(request=request, use_https=request.is_secure())

    def get_users(self, email):
        """Django şifresi olmayan hesaplara bağlantı göndermez; Podia'dan aktarılan hesapların şifresi yok,
        "Şifremi unuttum" onlar için de çalışmalı. Etkin ve e-postası eşleşen her hesap."""
        return User.objects.with_email(email).filter(is_active=True)

    def send_mail(self, subject_template_name, email_template_name, context, from_email, to_email, html_email_template_name=None):
        """Şablon: templates/emails/password_reset (HTML + düz metin, bkz. mailing.emails)."""
        from mailing.emails import send_email
        from order.emails import password_reset_context

        path = reverse("page:password_reset_confirm", kwargs={"uidb64": context["uid"], "token": context["token"]})
        reset_url = f"{context['protocol']}://{context['domain']}{path}"
        send_email("password_reset", to_email, password_reset_context(context["user"], reset_url))


class NewPasswordForm(StyledFormMixin, auth_forms.SetPasswordForm):
    """Sıfırlama bağlantısından açılan yeni şifre formu (PasswordResetConfirmView ile)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["new_password1"].label = "Yeni şifre"
        self.fields["new_password1"].help_text = "En az 8 karakter."
        self.fields["new_password2"].label = "Yeni şifre (tekrar)"
        self.helper.layout = Layout("new_password1", "new_password2", submit("Şifremi kaydet", icon="bi-check-lg"))


class NewsletterManageForm(StyledForm):
    """E-postadaki "Aboneliği düzenle" sayfası: bültenlerde kullanılan ad."""

    name = name_field(label="İsim")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper.form_tag = False
        self.helper.layout = Layout("name", submit("Kaydet", icon="bi-check2", css_class="btn-primary btn-lg fs-6 w-100"))


class NewsletterUnsubscribeForm(StyledForm):
    email = email_field()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper.layout = Layout(
            "email",
            submit("Abonelikten çık", icon="bi-envelope-x", css_class="btn-outline-secondary btn-lg fs-6 w-100"),
        )


class ProfileForm(StyledFormMixin, forms.ModelForm):
    first_name = name_field(label="Ad", autocomplete="given-name")
    last_name = name_field(label="Soyad", placeholder="Soyadın", autocomplete="family-name", noun="soyadını")

    class Meta:
        model = User
        fields = ("first_name", "last_name")

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, instance=user, prefix="profile", **kwargs)
        self.helper.layout = Layout(
            Hidden("action", "profile"),
            Row(Column("first_name", css_class="col-sm-6"), Column("last_name", css_class="col-sm-6")),
            submit("Kaydet", icon="bi-check-lg", css_class="btn-primary"),
        )


class AppearanceForm(StyledFormMixin, forms.ModelForm):
    """Hesap ayarları → Görünüm: imleç ışık efekti (spotlight) açık mı."""

    class Meta:
        model = User
        fields = ("cursor_spotlight",)
        labels = {"cursor_spotlight": "İmleç ışık efekti"}
        help_texts = {"cursor_spotlight": "Fare kartların ve sayfanın üzerinde gezerken imlecin çevresinde vurgu renginde hafif bir ışık belirir."}

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, instance=user, prefix="appearance", **kwargs)
        self.helper.layout = Layout(
            Hidden("action", "appearance"),
            "cursor_spotlight",
            submit("Kaydet", icon="bi-check-lg", css_class="btn-primary"),
        )


class ReviewForm(forms.Form):
    """Kursu alan kullanıcının değerlendirmesi: puan zorunlu, yorum isteğe bağlı. Her kayıt yeniden onaya gider."""

    rating = forms.TypedChoiceField(
        label="Puanın",
        choices=[(value, f"{value} yıldız") for value in range(5, 0, -1)],
        coerce=int,
        widget=forms.RadioSelect,
        error_messages={"required": "Lütfen 1 ile 5 arasında puan ver."},
    )
    text = forms.CharField(
        label="Yorumun (isteğe bağlı)",
        required=False,
        max_length=2000,
        widget=forms.Textarea(attrs={"rows": 4, "class": "form-control", "placeholder": "Kurs hakkında düşüncelerin"}),
        error_messages={"max_length": "Yorum en fazla 2000 karakter olabilir."},
    )

    def __init__(self, *args, review=None, **kwargs):
        if review is not None and "initial" not in kwargs:
            kwargs["initial"] = {"rating": review.rating, "text": review.text}
        super().__init__(*args, **kwargs)

    def save(self, course, user, review=None):
        from course.models import Review

        review = review or Review(course=course, user=user)
        review.submit(self.cleaned_data["rating"], self.cleaned_data["text"])
        return review


class PlayerPreferenceForm(StyledFormMixin, forms.ModelForm):
    """Hesap ayarları → Video oynatma: varsayılan hız, kalite, altyazı, oynatınca tam ekran ve bitince sonraki derse geçiş."""

    class Meta:
        model = PlayerPreference
        # Altyazı dili şimdilik seçilmez (varsayılan Türkçe, PlayerPreference.subtitle_language). Açmak için alanı geri ekle:
        # fields = ("playback_rate", "quality", "subtitles_enabled", "subtitle_language", "fullscreen_on_play", "autoplay_next")
        fields = ("playback_rate", "quality", "subtitles_enabled", "fullscreen_on_play", "autoplay_next")
        widgets = {
            "playback_rate": forms.Select(attrs={"class": "form-select form-select-lg fs-6"}),
            "quality": forms.Select(attrs={"class": "form-select form-select-lg fs-6"}),
            "subtitle_language": forms.Select(attrs={"class": "form-select form-select-lg fs-6"}),
        }
        labels = {"fullscreen_on_play": "Oynat'a basınca tam ekrana geç", "autoplay_next": "Video bitince sonraki derse otomatik geç"}
        help_texts = {
            "quality": "Videoda bu kalite yoksa bağlantına göre otomatik seçilir.",
            "subtitles_enabled": "Açıksa altyazısı olan videolarda Türkçe altyazı kendiliğinden açılır.",
            "autoplay_next": "Ders videosu bitince sıradaki ders hemen açılır ve kendiliğinden başlar.",
        }

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, instance=PlayerPreference.for_user(user), prefix="player", **kwargs)
        self.helper.layout = Layout(
            Hidden("action", "player"),
            Row(Column("playback_rate", css_class="col-sm-6"), Column("quality", css_class="col-sm-6")),
            # Altyazı dili seçimi açılınca: Row(Column("subtitles_enabled", css_class="col-sm-6"), Column("subtitle_language", css_class="col-sm-6")),
            "subtitles_enabled",
            "fullscreen_on_play",
            "autoplay_next",
            HTML('<p class="small text-body-secondary">Oynatıcıda hızı, kaliteyi ya da altyazıyı değiştirdiğinde bu ayarlar kendiliğinden güncellenir.</p>'),
            submit("Kaydet", icon="bi-check-lg", css_class="btn-primary"),
        )


class PlayerPreferenceAutoForm(forms.ModelForm):
    """Oynatıcıdan gelen otomatik kayıt: yalnız gönderilen alanlar değişir, diğerleri olduğu gibi kalır."""

    FIELDS = ("playback_rate", "quality", "subtitles_enabled", "subtitle_language")

    class Meta:
        model = PlayerPreference
        fields = ("playback_rate", "quality", "subtitles_enabled", "subtitle_language")

    def __init__(self, data, *, user, **kwargs):
        instance = PlayerPreference.for_user(user)
        merged = {name: getattr(instance, name) for name in self.FIELDS}
        merged.update({name: data[name] for name in self.FIELDS if name in data})
        super().__init__(merged, instance=instance, **kwargs)


class CurrentPasswordMixin:
    """Hesap değişikliklerinden önce mevcut şifreyi doğrular."""

    def check_current_password(self, password):
        if not self.user.check_password(password):
            raise forms.ValidationError("Mevcut şifren hatalı.")
        return password


class EmailChangeForm(CurrentPasswordMixin, StyledForm):
    email = email_field(label="Yeni e-posta")
    password = password_field("Mevcut şifre", "current-password")

    def __init__(self, *args, user, **kwargs):
        self.user = user
        super().__init__(*args, prefix="email", **kwargs)
        self.fields["email"].help_text = "Giriş yaparken bu adresi kullanacaksın."
        self.helper.layout = Layout(
            Hidden("action", "email"),
            "email",
            "password",
            submit("E-postayı güncelle", icon="bi-check-lg", css_class="btn-primary"),
        )

    def clean_email(self):
        email = User.objects.normalize_email(self.cleaned_data["email"])
        if email == self.user.email:
            raise forms.ValidationError("Bu zaten şu anki e-posta adresin.")
        if User.objects.with_email(email).exclude(pk=self.user.pk).exists():
            raise forms.ValidationError("Bu e-posta adresiyle bir hesap zaten var.")
        return email

    def clean_password(self):
        return self.check_current_password(self.cleaned_data["password"])

    def save(self):
        self.user.email = self.cleaned_data["email"]
        self.user.save(update_fields=["email"])
        return self.user


class PasswordChangeForm(CurrentPasswordMixin, StyledForm):
    current_password = password_field("Mevcut şifre", "current-password")
    new_password = password_field("Yeni şifre", "new-password", min_length=8)
    new_password2 = password_field("Yeni şifre (tekrar)", "new-password")

    def __init__(self, *args, user, **kwargs):
        self.user = user
        super().__init__(*args, prefix="password", **kwargs)
        self.fields["new_password"].help_text = "En az 8 karakter."
        self.helper.layout = Layout(
            Hidden("action", "password"),
            "current_password",
            "new_password",
            "new_password2",
            submit("Şifreyi değiştir", icon="bi-check-lg", css_class="btn-primary"),
        )

    def clean_current_password(self):
        return self.check_current_password(self.cleaned_data["current_password"])

    def clean_new_password(self):
        password = self.cleaned_data["new_password"]
        password_validation.validate_password(password, self.user)
        return password

    def clean(self):
        cleaned = super().clean()
        first = cleaned.get("new_password")
        second = cleaned.get("new_password2")
        if first and second and first != second:
            self.add_error("new_password2", "Şifreler eşleşmiyor.")
        return cleaned

    def save(self):
        self.user.set_password(self.cleaned_data["new_password"])
        self.user.save(update_fields=["password"])
        return self.user


class CheckoutForm(StyledForm):
    email = email_field()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Adres doğrulanmaz ve kayıtlı olup olmadığı söylenmez; kayıtlıysa satın alma o hesaba bağlanır.
        self.fields["email"].help_text = "Kurslar bu e-posta adresine tanımlanır; ödeme bilgilendirmesi de buraya gelir."
        # "Öde" düğmesi sipariş özetinde durur ve form="odeme-formu" ile bu forma bağlanır.
        self.helper.form_id = "odeme-formu"
        self.helper.layout = Layout(Hidden("action", "pay"), "email")


class CouponForm(StyledForm):
    """Ödeme adımında indirim kodu (discount.Discount); geçerlilik, tarih ve kullanım sınırları kodda denetlenir."""

    code = forms.CharField(
        label="İndirim kodu",
        error_messages={"required": "Bir indirim kodu gir."},
        widget=forms.TextInput(attrs={"autocomplete": "off", "placeholder": "Kodunu gir"}),
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, prefix="coupon", **kwargs)
        self.user = user
        self.fields["code"].widget.attrs["class"] = ""
        self.helper.layout = Layout(
            Hidden("action", "coupon"),
            FieldWithButtons("code", StrictButton("Uygula", type="submit", css_class="btn-outline-secondary")),
        )

    def clean_code(self):
        discount = Discount.objects.by_code(self.cleaned_data["code"])
        if discount is None:
            raise forms.ValidationError("Bu indirim kodu geçerli değil.")
        discount.validate_for(self.user)
        return discount
