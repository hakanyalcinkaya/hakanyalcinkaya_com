from crispy_forms.layout import HTML, Column, Layout, Row
from django import forms
from django.conf import settings

from page.forms import StyledForm, email_field, name_field, submit
from support import turnstile
from support.models import MESSAGE_MAX_LENGTH, Ticket


def message_field(label="Mesaj"):
    return forms.CharField(
        label=label,
        max_length=MESSAGE_MAX_LENGTH,
        error_messages={
            "required": "Mesajını yaz.",
            "max_length": f"Mesaj en fazla {MESSAGE_MAX_LENGTH} karakter olabilir.",
        },
        # Kalan karakter sayacı site.js'te (data-char-count).
        widget=forms.Textarea(attrs={"rows": 6, "maxlength": MESSAGE_MAX_LENGTH, "data-char-count": ""}),
    )


class TicketForm(StyledForm):
    """Üyenin yeni talebi: konu ve mesaj (ad ve e-posta hesabından)."""

    subject = forms.CharField(
        label="Konu",
        max_length=150,
        error_messages={"required": "Konuyu yaz."},
        widget=forms.TextInput(attrs={"placeholder": "Kısaca konu"}),
    )
    body = message_field()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper.layout = Layout(*self.layout_fields(), submit("Gönder", icon="bi-send"))

    def layout_fields(self):
        return ["subject", "body"]

    def save(self, user=None):
        data = self.cleaned_data
        return Ticket.open(subject=data["subject"], body=data["body"], user=user)


class GuestTicketForm(TicketForm):
    """Giriş yapmamış kullanıcı: ad, e-posta, konu, mesaj ve Turnstile doğrulaması."""

    name = name_field()
    email = email_field()

    def __init__(self, *args, remote_ip="", **kwargs):
        self.remote_ip = remote_ip
        super().__init__(*args, **kwargs)
        self.order_fields(["name", "email", "subject", "body"])

    def layout_fields(self):
        fields = [Row(Column("name", css_class="col-sm-6"), Column("email", css_class="col-sm-6")), "subject", "body"]
        if turnstile.is_enabled():
            fields.append(
                HTML(f'<div class="cf-turnstile mb-3" data-sitekey="{settings.TURNSTILE_SITE_KEY}" data-theme="auto" data-language="tr"></div>')
            )
        return fields

    def clean(self):
        cleaned = super().clean()
        if not turnstile.verify(self.data.get(turnstile.TOKEN_FIELD, ""), self.remote_ip):
            raise forms.ValidationError("Robot olmadığını doğrulayamadık; kutucuğu işaretleyip tekrar dene.")
        return cleaned

    def save(self, user=None):
        data = self.cleaned_data
        return Ticket.open(subject=data["subject"], body=data["body"], name=data["name"], email=data["email"])


class ReplyForm(StyledForm):
    body = message_field("Yanıtın")

    def __init__(self, *args, label="Gönder", **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["body"].widget.attrs["rows"] = 4
        self.helper.layout = Layout("body", submit(label, icon="bi-send", css_class="btn-primary"))
