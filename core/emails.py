"""Şablonlu e-postalar. Her e-posta `templates/emails/<anahtar>/` altında üç dosyadır: subject.txt, body.txt, body.html.

HTML gövde `emails/base.html` düzenini, düz metin `emails/base.txt` düzenini genişletir. Değişkenler Django şablon
sözdizimiyle yazılır ({{ first_name }}, {% for item in items %} ...). Hangi e-postanın hangi değişkenleri aldığı
EMAILS listesinde yazılıdır; stüdyodaki önizleme sayfası bu listeyi gösterir.
"""

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

# Her e-postada bulunan değişkenler
COMMON_VARIABLES = {
    "first_name": "Alıcının adı (boş olabilir)",
    "last_name": "Alıcının soyadı (boş olabilir)",
    "full_name": "Ad soyad; ikisi de boşsa boş",
    "greeting_name": "Selamlamada kullanılan ad: ad, yoksa boş (\"Merhaba,\")",
    "email": "Alıcının e-posta adresi",
    "site_url": "Sitenin adresi",
    "library_url": "Kurslarım sayfası",
    "login_url": "Giriş sayfası",
}
ITEM_VARIABLES = {
    "items": "Satın alınan ürünler listesi; her biri: title, url, price, paid_price, discount (biçimlendirilmiş tutarlar)",
    "product_title": "İlk ürünün adı (tek ürünlü e-postalar için kısayol)",
    "product_price": "İlk ürünün liste fiyatı (ör. 99,90 €)",
    "paid_price": "İlk ürün için ödenen tutar",
    "order_number": "Sipariş no (birden fazla siparişte ilki)",
    "order_total": "Sipariş(ler)de ödenen toplam",
    "currency": "Para birimi kodu (TRY, EUR)",
    "coupon": "Kullanılan indirim kodu (varsa)",
    "purchased_at": "Satın alma tarihi",
}

COURSE_VARIABLES = {
    "course_title": "Kursun adı",
    "course_url": "Kurs sayfası",
}


def _email(label, group, description, variables, recipient="user"):
    return {"label": label, "group": group, "description": description, "variables": variables, "recipient": recipient}


# Sitenin gönderebileceği e-postalar. "recipient": user (öğrenci), subscriber (bülten), admin (yönetici).
EMAILS = {
    # Hesap
    "welcome": _email(
        "Hoş geldin", "Hesap", "Kayıt olunca: hesabın hazır, kurslara göz at.", {**COMMON_VARIABLES, "courses_url": "Tüm kurslar"}
    ),
    "account_migrated": _email(
        "Hesabın taşındı (Podia)",
        "Hesap",
        "Podia'dan aktarılan müşteriye, kişi başına bir e-posta: hesabına tanımlanan eğitimler ve şifre belirleme bağlantısı.",
        {**COMMON_VARIABLES, **ITEM_VARIABLES, "set_password_url": "Şifre belirleme bağlantısı (tek kullanımlık, süreli)"},
    ),
    "password_reset": _email(
        "Şifremi unuttum",
        "Hesap",
        "\"Şifremi unuttum\" formundan istenen şifre sıfırlama bağlantısı.",
        {**COMMON_VARIABLES, "reset_url": "Şifre sıfırlama bağlantısı (tek kullanımlık, süreli)"},
    ),
    "password_changed": _email(
        "Şifren değiştirildi", "Hesap", "Şifre değişince güvenlik bildirimi.", {**COMMON_VARIABLES, "changed_at": "Değişiklik zamanı", "reset_page_url": "Şifremi unuttum sayfası"}
    ),
    "email_change": _email(
        "E-posta değişikliği onayı",
        "Hesap",
        "Yeni e-posta adresine gönderilen onay bağlantısı.",
        {**COMMON_VARIABLES, "new_email": "Yeni e-posta adresi", "confirm_url": "Onay bağlantısı"},
    ),
    # Satın alma
    "purchase_confirmation": _email(
        "Teşekkürler, satın alma onayı",
        "Satın alma",
        "Ödemesi onaylanan sipariş (iyzico): satın alınan eğitimler, tutarlar ve Kurslarım bağlantısı.",
        {**COMMON_VARIABLES, **ITEM_VARIABLES},
    ),
    "payment_failed": _email(
        "Ödeme başarısız",
        "Satın alma",
        "Ödeme tamamlanamayınca: sepetteki ürünler ve yeniden deneme bağlantısı.",
        {**COMMON_VARIABLES, **ITEM_VARIABLES, "retry_url": "Ödemeyi yeniden deneme (sepet)"},
    ),
    "refund_processed": _email(
        "İade yapıldı",
        "Satın alma",
        "Sipariş iade edilince: iade tutarı ve kapanan erişim.",
        {**COMMON_VARIABLES, **ITEM_VARIABLES, "refund_amount": "İade edilen tutar"},
    ),
    "course_granted": _email(
        "Kurs hesabına tanımlandı",
        "Satın alma",
        "Hediye ya da manuel olarak kurs erişimi açılınca.",
        {**COMMON_VARIABLES, **COURSE_VARIABLES, "grant_reason": "Neden (ör. Hediye)", "sender_name": "Hediye eden (varsa)"},
    ),
    # Eğitim
    "course_completed": _email(
        "Tebrikler, kursu bitirdin",
        "Eğitim",
        "Kurstaki tüm dersler tamamlanınca.",
        {
            **COMMON_VARIABLES,
            **COURSE_VARIABLES,
            "lesson_total": "Tamamlanan ders sayısı",
            "completed_at": "Bitirme tarihi",
            "review_url": "Kursu değerlendirme bağlantısı",
        },
    ),
    "review_approved": _email(
        "Yorumun yayınlandı",
        "Eğitim",
        "Kullanıcının değerlendirmesi onaylanınca.",
        {**COMMON_VARIABLES, **COURSE_VARIABLES, "rating": "Puan (1-5)", "review_text": "Yorum metni"},
    ),
    # Bülten
    "newsletter_confirm": _email(
        "Bülten aboneliği onayı",
        "Bülten",
        "Abone olunca onay bağlantısı (çift onay).",
        {"name": "Abonenin adı", "email": "Abonenin e-postası", "confirm_url": "Onay bağlantısı", "site_url": "Sitenin adresi"},
        recipient="subscriber",
    ),
    "newsletter": _email(
        "Bülten",
        "Bülten",
        "Bülten sayısı: başlık, giriş, Markdown'dan içerik ve çıkış bağlantısı.",
        {
            "name": "Abonenin adı",
            "email": "Abonenin e-postası",
            "headline": "Bülten başlığı",
            "intro": "Giriş paragrafı",
            "content_html": "İçerik (Markdown'dan temizlenmiş HTML)",
            "content_text": "İçeriğin düz metin hâli",
            "cta_label": "Düğme yazısı (isteğe bağlı)",
            "cta_url": "Düğme bağlantısı (isteğe bağlı)",
            "unsubscribe_url": "Abonelikten çıkış bağlantısı (zorunlu)",
            "site_url": "Sitenin adresi",
        },
        recipient="subscriber",
    ),
    # Yönetici
    "admin_new_order": _email(
        "Yeni satış (yönetici)",
        "Yönetici",
        "Ödeme onaylanınca yöneticiye özet.",
        {**COMMON_VARIABLES, **ITEM_VARIABLES, "admin_url": "Siparişin admin sayfası"},
        recipient="admin",
    ),
    "admin_review_pending": _email(
        "Onay bekleyen yorum (yönetici)",
        "Yönetici",
        "Yeni ya da değiştirilmiş yorum onaya düşünce.",
        {
            **COURSE_VARIABLES,
            "reviewer_name": "Yorumu yazanın görünen adı",
            "rating": "Puan",
            "review_text": "Yorum metni",
            "is_edit": "Onaylı yorum değiştirildiyse True",
            "studio_url": "Stüdyo → Yorumlar",
        },
        recipient="admin",
    ),
}


# Şablonların sabit içerikleri (bağlamda verilmezse kullanılır).
DEFAULTS = {
    "welcome": {
        "features": [
            {"title": "Projelerle öğren", "text": "Her bölüm, öğrendiklerini kullandığın bir projeyle biter."},
            {"title": "Kendi hızında", "text": "Dersleri istediğin zaman, istediğin cihazdan izle."},
            {"title": "Ücretsiz önizleme", "text": "Satın almadan önce önizleme derslerini izleyebilirsin."},
        ]
    }
}


def template_names(key):
    return {part: f"emails/{key}/{part}" for part in ("subject.txt", "body.txt", "body.html")}


def render_email(key, context):
    """(konu, düz metin, HTML) döner."""
    if key not in EMAILS:
        raise KeyError(f"Tanımsız e-posta: {key}")
    names = template_names(key)
    context = {"site_name": "Hakan Yalçınkaya", "email_key": key, **DEFAULTS.get(key, {}), **context}
    subject = " ".join(render_to_string(names["subject.txt"], context).split())
    return subject, render_to_string(names["body.txt"], context).strip() + "\n", render_to_string(names["body.html"], context)


def send_email(key, to, context):
    subject, text, html = render_email(key, context)
    message = EmailMultiAlternatives(subject, text, settings.DEFAULT_FROM_EMAIL, [to])
    message.attach_alternative(html, "text/html")
    message.send()
    return message


def sample_context(key):
    """Önizleme için örnek veri (gerçek kişi değil)."""
    from datetime import datetime, timezone

    site = settings.SITE_URL.rstrip("/")
    when = datetime(2026, 3, 14, 10, 30, tzinfo=timezone.utc)
    items = [
        {
            "title": "Sıfırdan Projelerle Front-End ve React 18.x Öğren",
            "url": f"{site}/react/",
            "price": "₺1.999",
            "paid_price": "₺899",
            "discount": "₺1.100",
            "purchased_at": when,
        },
        {
            "title": "Sıfırdan Uçtan Uca Projelerle Python ve Django Öğren",
            "url": f"{site}/django/",
            "price": "₺1.999",
            "paid_price": "₺999",
            "discount": "₺1.000",
            "purchased_at": when,
        },
    ]
    base = {
        "first_name": "Ayşe",
        "last_name": "Yılmaz",
        "full_name": "Ayşe Yılmaz",
        "greeting_name": "Ayşe",
        "email": "ayse@example.com",
        "site_url": site,
        "library_url": f"{site}/p/products/library/",
        "login_url": f"{site}/account/login/",
        "courses_url": f"{site}/courses/",
        "items": items,
        "product_title": items[0]["title"],
        "product_price": items[0]["price"],
        "paid_price": items[0]["paid_price"],
        "order_number": "HY-260314-A1B2C3",
        "order_total": "₺1.898",
        "currency": "TRY",
        "coupon": "BAHAR2026",
        "purchased_at": when,
        "course_title": items[0]["title"],
        "course_url": items[0]["url"],
        "name": "Ayşe",
    }
    extra = {
        "account_migrated": {
            "items": [dict(items[0], price="29,99 €", paid_price="14,99 €", discount="15,00 €")],
            "product_price": "29,99 €",
            "paid_price": "14,99 €",
            "order_total": "14,99 €",
            "currency": "EUR",
            "coupon": "KENDINIGELISTIRMEYEDEVAM",
            "set_password_url": f"{site}/account/password-reset/ornek/belirtec/",
        },
        "password_reset": {"reset_url": f"{site}/account/password-reset/ornek/belirtec/"},
        "password_changed": {"changed_at": when, "reset_page_url": f"{site}/account/password-reset/"},
        "email_change": {"new_email": "ayse.yeni@example.com", "confirm_url": f"{site}/account/email/ornek-onay/"},
        "payment_failed": {"retry_url": f"{site}/cart/"},
        "refund_processed": {"items": items[:1], "refund_amount": "₺899", "order_total": "₺899"},
        "course_granted": {"grant_reason": "Hediye", "sender_name": "Mehmet K."},
        "course_completed": {"lesson_total": 335, "completed_at": when, "review_url": f"{site}/react/#yorumlar"},
        "review_approved": {"rating": 5, "review_text": "Projelerle ilerlemek konuları kalıcı hâle getirdi."},
        "newsletter_confirm": {"confirm_url": f"{site}/newsletter/confirm/?ornek"},
        "newsletter": {
            "headline": "Mart bülteni: React 19 ve yeni dersler",
            "intro": "Bu ay kursa eklenen dersleri ve öne çıkan yazıları derledim.",
            "content_html": "<h3 style=\"margin:18px 0 8px;font-size:18px;color:#151515;\">Yeni dersler</h3><ul style=\"padding-left:20px;margin:0 0 14px;\"><li>RTK Query ile veri yönetimi</li><li>React 19 ile gelen yenilikler</li></ul>",
            "content_text": "Yeni dersler\n- RTK Query ile veri yönetimi\n- React 19 ile gelen yenilikler",
            "cta_label": "Kurslara göz at",
            "cta_url": f"{site}/courses/",
            "unsubscribe_url": f"{site}/newsletter/unsubscribe/?ornek",
        },
        "admin_new_order": {"admin_url": f"{site}/admin/order/order/"},
        "admin_review_pending": {
            "reviewer_name": "Ayşe Y.",
            "rating": 4,
            "review_text": "Anlatım çok net, bazı bölümler biraz hızlı.",
            "is_edit": False,
            "studio_url": f"{site}/studio/reviews/",
        },
    }
    return {**base, **extra.get(key, {})}
