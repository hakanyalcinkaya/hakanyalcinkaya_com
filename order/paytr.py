"""PayTR iFrame API istemcisi (kartla ödeme). Kart bilgisi siteye gelmez; ödeme formu PayTR'nin iframe'inde açılır.

1. Bekleyen sipariş için sunucudan token alınır (`create_token`); ödeme sayfası `iframe_url(token)` adresini gösterir.
2. Sonucu PayTR, panelde tanımlı Bildirim URL'sine POST eder (Destek & Kurulum › Ayarlar › Bildirim URL Ayarları).
   `parse_notification` imzayı doğrular; uç yalnız düz `OK` döner. Aynı bildirim birden çok gelebilir.
   Müşterinin döndüğü merchant_ok_url ödemenin kanıtı değildir; sipariş yalnız bildirimle ödenir.
"""

import base64
import hashlib
import hmac
import json
import logging
from dataclasses import dataclass
from decimal import Decimal

import requests
from django.conf import settings

TOKEN_URL = "https://www.paytr.com/odeme/api/get-token"
IFRAME_URL = "https://www.paytr.com/odeme/guvenli/{token}"
TIMEOUT = 20
CURRENCY = "TL"
# Ödeme formunun açık kalabileceği süre (dakika); sonra token geçersizdir.
TIMEOUT_LIMIT = 30
REQUIRED_SETTINGS = ("PAYTR_MERCHANT_ID", "PAYTR_MERCHANT_KEY", "PAYTR_MERCHANT_SALT")
# PayTR'nin alan sınırları
NAME_LENGTH = 60
ADDRESS_LENGTH = 400
PHONE_LENGTH = 20
# Adres zorunlu; kurslar dijital teslim edildiği için sabit metin gider.
DIGITAL_ADDRESS = "Dijital ürün (online kurs)"

logger = logging.getLogger(__name__)


class PaytrError(Exception):
    pass


def is_configured():
    return all(getattr(settings, name, "") for name in REQUIRED_SETTINGS)


def _sign(text):
    digest = hmac.new(settings.PAYTR_MERCHANT_KEY.encode(), text.encode(), hashlib.sha256).digest()
    return base64.b64encode(digest).decode()


def merchant_oid(order):
    """PayTR sipariş numarası: yalnız harf ve rakam kabul edilir (HY-261102-ABC123 → HY261102ABC123)."""
    return order.number.replace("-", "")


def to_kurus(amount):
    """34.56 → "3456" (PayTR tutarları 100 ile çarpılmış tam sayı ister)."""
    return str(int((Decimal(amount) * 100).quantize(Decimal(1))))


def basket(order):
    """Sepet: base64 JSON, her satır [ürün adı, birim fiyat, adet]. Fiyatlar indirimli ödenen tutardır."""
    rows = [[item.title, f"{item.paid_price:.2f}", 1] for item in order.items.all()]
    return base64.b64encode(json.dumps(rows).encode()).decode()


def create_token(order, user_ip, user_name, user_phone, user_address, ok_url, fail_url):
    """Bekleyen sipariş için iframe token'ı. ok_url/fail_url müşterinin döneceği tam adreslerdir. PayTR reddederse ya
    da ulaşılamazsa PaytrError."""
    max_installment = settings.PAYTR_MAX_INSTALLMENT
    fields = {
        "merchant_id": settings.PAYTR_MERCHANT_ID,
        "user_ip": user_ip,
        "merchant_oid": merchant_oid(order),
        "email": order.email,
        "payment_amount": to_kurus(order.total),
        "user_basket": basket(order),
        "no_installment": "1" if max_installment <= 1 else "0",
        "max_installment": "0" if max_installment <= 1 else str(min(max_installment, 12)),
        "currency": CURRENCY,
        "test_mode": "1" if settings.PAYTR_TEST_MODE else "0",
    }
    hash_str = "".join(fields.values())
    fields.update(
        paytr_token=_sign(hash_str + settings.PAYTR_MERCHANT_SALT),
        user_name=user_name[:NAME_LENGTH],
        user_address=user_address[:ADDRESS_LENGTH],
        user_phone=user_phone[:PHONE_LENGTH],
        merchant_ok_url=ok_url,
        merchant_fail_url=fail_url,
        timeout_limit=str(TIMEOUT_LIMIT),
        debug_on="1",
        lang="tr",
    )
    try:
        response = requests.post(TOKEN_URL, data=fields, timeout=TIMEOUT)
        result = response.json()
    except (requests.RequestException, ValueError) as error:
        logger.warning("PayTR token alınamadı (%s): %s", order.number, error)
        raise PaytrError(str(error)) from error
    if result.get("status") != "success":
        logger.warning("PayTR token reddedildi (%s): %s", order.number, result.get("reason"))
        raise PaytrError(result.get("reason", ""))
    return result["token"]


def iframe_url(token):
    return IFRAME_URL.format(token=token)


@dataclass
class Notification:
    """Bildirim URL'sine gelen ödeme sonucu (imzası doğrulanmış)."""

    merchant_oid: str
    is_success: bool
    # Tahsil edilen tutar; taksitte vade farkıyla siparişin tutarından yüksek olabilir.
    total_amount: Decimal
    # Token alınırken gönderilen sipariş tutarı.
    payment_amount: Decimal
    is_test: bool
    failed_reason: str


def parse_notification(data):
    """PayTR'nin POST verisi (request.POST). İmza tutmazsa PaytrError: istek PayTR'den gelmemiştir."""
    oid, status, total = data.get("merchant_oid", ""), data.get("status", ""), data.get("total_amount", "")
    expected = _sign(oid + settings.PAYTR_MERCHANT_SALT + status + total)
    if not oid or not hmac.compare_digest(expected, data.get("hash", "")):
        raise PaytrError("PayTR bildiriminin imzası geçersiz")
    reason = " ".join(filter(None, (data.get("failed_reason_code", ""), data.get("failed_reason_msg", ""))))
    return Notification(
        merchant_oid=oid,
        is_success=status == "success",
        total_amount=Decimal(total or 0) / 100,
        payment_amount=Decimal(data.get("payment_amount") or 0) / 100,
        is_test=data.get("test_mode") == "1",
        failed_reason=reason,
    )
