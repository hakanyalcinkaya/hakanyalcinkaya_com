"""Üye sayfa ziyaretleri (PageView): giriş yapmış, personel olmayan üyenin başarılı tam sayfa GET istekleri ziyaretçi
bilgileriyle (core.visitor, hafif) kaydedilir. HTMX parçaları (boost hariç), yönlendirmeler, hatalar, HTML olmayan
yanıtlar ve SKIP_PREFIXES altındaki adresler kaydedilmez. Bir hata yanıtı bozmasın diye loglanır ve geçilir."""

import logging

from account.models import PageView
from core import visitor

logger = logging.getLogger(__name__)

SKIP_PREFIXES = ("/studio/", "/admin", "/static/", "/media/", "/__debug__/", "/__reload__/", "/favicon")


def should_record(request, response):
    user = getattr(request, "user", None)
    htmx = getattr(request, "htmx", None)
    return (
        request.method == "GET"
        and user is not None
        and user.is_authenticated
        and not user.is_staff
        and response.status_code == 200
        and (not htmx or htmx.boosted)
        and response.get("Content-Type", "").startswith("text/html")
        and not request.path.startswith(SKIP_PREFIXES)
    )


class MemberPageViewMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if should_record(request, response):
            try:
                match = getattr(request, "resolver_match", None)
                data = visitor.collect(request, light=True)
                data["visit"]["query"] = request.META.get("QUERY_STRING", "")[:300]
                PageView.objects.create(
                    user=request.user, path=request.path[:300], view_name=(match.view_name if match else "")[:100], data=data
                )
            except Exception:  # noqa: BLE001
                logger.exception("Sayfa ziyareti kaydedilemedi")
        return response
