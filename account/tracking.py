"""Kayıt ve giriş kaydı (AccountEvent.data): ziyaretçi bilgileri (core.visitor). Her başarılı giriş user_logged_in ile
kaydedilir; kayıt görünümü girişten önce request.account_event_kind = SIGNUP yazar, o giriş "signup" kaydı olur. Kayıt
hiçbir zaman girişi engellemez: bir hata loglanır ve geçilir."""

import logging

from account.models import AccountEvent, AccountEventKind
from core import visitor

logger = logging.getLogger(__name__)


def record_login(sender, request, user, **kwargs):
    """user_logged_in alıcısı."""
    if request is None:
        return
    kind = getattr(request, "account_event_kind", AccountEventKind.LOGIN)
    try:
        AccountEvent.objects.create(user=user, kind=kind, data=dict(visitor.collect(request, user), path=request.path[:300]))
    except Exception:  # noqa: BLE001
        logger.exception("Kayıt/giriş kaydı yazılamadı")
