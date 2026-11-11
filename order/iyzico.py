"""iyzico Checkout Form istemcisi (kartla ödeme). Kart bilgisi siteye gelmez; müşteri iyzico'nun ödeme sayfasında öder.

1. Bekleyen sipariş için ödeme formu açılır (`initialize`): iyzico bir token ve ödeme sayfası adresi (paymentPageUrl) döner.
2. Müşteri ödedikten sonra iyzico tarayıcıyı callbackUrl'e token ile POST eder. Ayrıca panelde tanımlıysa (Ayarlar ›
   Bildirimler) webhook aynı token'ı sunucudan sunucuya gönderir; müşteri sayfayı dönüşten önce kapatsa da ödeme işlenir.
3. Her iki durumda da ödemenin sonucu token ile iyzico'dan sorulur (`retrieve`, kendi API anahtarımızla imzalı istek);
   callback ya da webhook gövdesindeki bilgiye güvenilmez. Aynı sonuç birden çok gelebilir.
"""

import base64
import hashlib
import hmac
import json
import logging
import secrets
import time
from dataclasses import dataclass
from decimal import Decimal

import requests
from django.conf import settings

INITIALIZE_PATH = "/payment/iyzipos/checkoutform/initialize/auth/ecom"
RETRIEVE_PATH = "/payment/iyzipos/checkoutform/auth/ecom/detail"
TIMEOUT = 20
CURRENCY = "TRY"
REQUIRED_SETTINGS = ("IYZICO_API_KEY", "IYZICO_SECRET_KEY", "IYZICO_BASE_URL")
NAME_LENGTH = 60
# Kurslar dijital teslim edildiği için fatura adresi ve kimlik bilgisi sabit gider (iyzico zorunlu tutar).
DIGITAL_ADDRESS = "Dijital ürün (online kurs)"
CITY = "Istanbul"
COUNTRY = "Turkey"
# TC kimlik no sorulmaz; iyzico bu durumda 11 haneli yer tutucu kabul eder.
IDENTITY_NUMBER = "11111111111"
# Ödeme sonucu: fraudStatus 1 onaylı, 0 incelemede (sonuç sonradan webhook ile gelir), -1 reddedildi.
FRAUD_APPROVED = 1
FRAUD_REVIEW = 0

logger = logging.getLogger(__name__)


class IyzicoError(Exception):
    pass


def is_configured():
    return all(getattr(settings, name, "") for name in REQUIRED_SETTINGS)


def _headers(path, body):
    """IYZWSv2 imzası: HMAC-SHA256(gizli anahtar, rastgele anahtar + yol + gövde)."""
    random_key = f"{int(time.time() * 1000)}{secrets.token_hex(4)}"
    signature = hmac.new(settings.IYZICO_SECRET_KEY.encode(), f"{random_key}{path}{body}".encode(), hashlib.sha256).hexdigest()
    auth = f"apiKey:{settings.IYZICO_API_KEY}&randomKey:{random_key}&signature:{signature}"
    return {
        "Authorization": f"IYZWSv2 {base64.b64encode(auth.encode()).decode()}",
        "x-iyzi-rnd": random_key,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _post(path, payload, label):
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    try:
        response = requests.post(
            settings.IYZICO_BASE_URL.rstrip("/") + path, data=body.encode(), headers=_headers(path, body), timeout=TIMEOUT
        )
        return response.json()
    except (requests.RequestException, ValueError) as error:
        logger.warning("iyzico %s isteği başarısız: %s", label, error)
        raise IyzicoError(str(error)) from error


def price(amount):
    """5499 → "5499.00" (iyzico tutarları ondalık metin ister)."""
    return f"{Decimal(amount):.2f}"


def split_name(full_name):
    """"Ad İkinci Soyad" → ("Ad İkinci", "Soyad"); tek kelimede ad ve soyad aynı gider (iyzico ikisini de zorunlu tutar)."""
    words = full_name.split()
    if len(words) < 2:
        return full_name, full_name
    return " ".join(words[:-1]), words[-1]


def gsm_number(phone):
    """05xx… / 5xx… / 905xx… → +905xx… (iyzico uluslararası biçim ister); + ile yazılan numara olduğu gibi gider."""
    if phone.startswith("+"):
        return phone
    digits = phone.lstrip("0")
    return f"+{digits}" if digits.startswith("90") and len(digits) == 12 else f"+90{digits}"


def basket_items(order):
    """Sepet satırları; iyzico 0 TL'lik satırı kabul etmez (%100 indirimli satır atlanır)."""
    return [
        {
            "id": str(item.course_id or item.bundle_id or item.pk),
            "name": item.title,
            "category1": "Online kurs",
            "itemType": "VIRTUAL",
            "price": price(item.paid_price),
        }
        for item in order.items.all()
        if item.paid_price > 0
    ]


def initialize(order, user_ip, user_name, user_phone, callback_url):
    """Bekleyen sipariş için ödeme formu; ödeme sayfasının adresini (paymentPageUrl) döner. iyzico reddederse ya da
    ulaşılamazsa IyzicoError."""
    items = basket_items(order)
    name, surname = split_name(user_name)
    max_installment = settings.IYZICO_MAX_INSTALLMENT
    address = dict(contactName=user_name, city=CITY, country=COUNTRY, address=DIGITAL_ADDRESS)
    payload = {
        "locale": "tr",
        "conversationId": order.number,
        "price": price(sum(Decimal(item["price"]) for item in items)),
        "paidPrice": price(order.total),
        "currency": CURRENCY,
        "basketId": order.number,
        "paymentGroup": "PRODUCT",
        "callbackUrl": callback_url,
        "enabledInstallments": [n for n in (1, 2, 3, 6, 9, 12) if n <= max(max_installment, 1)],
        "buyer": {
            "id": str(order.user_id or order.email),
            "name": name,
            "surname": surname,
            "gsmNumber": gsm_number(user_phone),
            "email": order.email,
            "identityNumber": IDENTITY_NUMBER,
            "registrationAddress": DIGITAL_ADDRESS,
            "ip": user_ip or "",
            "city": CITY,
            "country": COUNTRY,
        },
        "billingAddress": address,
        "basketItems": items,
    }
    result = _post(INITIALIZE_PATH, payload, "ödeme formu")
    if result.get("status") != "success" or not result.get("paymentPageUrl"):
        logger.warning("iyzico ödeme formu reddedildi (%s): %s %s", order.number, result.get("errorCode"), result.get("errorMessage"))
        raise IyzicoError(result.get("errorMessage", ""))
    return result["paymentPageUrl"]


@dataclass
class Payment:
    """Token ile iyzico'dan sorulan ödeme sonucu."""

    basket_id: str
    payment_id: str
    is_success: bool
    # Onaylı ödeme dolandırıcılık incelemesinde: sonuç sonradan webhook ile gelir, sipariş bekler.
    in_review: bool
    # Tahsil edilen tutar; taksitte vade farkıyla siparişin tutarından yüksek olabilir.
    paid_price: Decimal
    error: str

    @property
    def is_failed(self):
        return not self.is_success and not self.in_review


def retrieve(token):
    """Ödeme formunun sonucu; token tanınmazsa basket_id boş gelir. iyzico'ya ulaşılamazsa IyzicoError."""
    result = _post(RETRIEVE_PATH, {"locale": "tr", "token": token}, "ödeme sonucu")
    basket_id = result.get("basketId") or ""
    paid = result.get("status") == "success" and result.get("paymentStatus") == "SUCCESS"
    fraud = result.get("fraudStatus")
    return Payment(
        basket_id=basket_id,
        payment_id=str(result.get("paymentId") or ""),
        is_success=paid and fraud == FRAUD_APPROVED,
        in_review=paid and fraud == FRAUD_REVIEW,
        paid_price=Decimal(str(result.get("paidPrice") or 0)) if result.get("currency", CURRENCY) == CURRENCY else Decimal(0),
        error=" ".join(filter(None, (str(result.get("errorCode") or ""), result.get("errorMessage") or ""))),
    )
