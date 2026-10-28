from django import forms


class NewsletterForm(forms.Form):
    name = forms.CharField(
        min_length=2,
        error_messages={
            "required": "Lütfen adını gir (en az 2 karakter).",
            "min_length": "Lütfen adını gir (en az 2 karakter).",
        },
    )
    email = forms.EmailField(
        error_messages={
            "required": "E-posta adresi gerekli.",
            "invalid": "Geçerli bir e-posta adresi gir.",
        },
    )
