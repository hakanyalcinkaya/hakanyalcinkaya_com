"""Bağlantıyla gelen indirim kodu (?coupon=KOD, discount.pending): sitenin herhangi bir sayfasında GET ile gelen kod
oturuma alınır ve ilk gelişte kullanıcıya bildirilir; adres değişmez, istek sayfaya devam eder."""

from django.contrib import messages
from django.core.exceptions import ValidationError

from cart.request_cart import current_cart
from discount import pending

SKIPPED_PREFIXES = ("/studio/", "/admin/", "/static/", "/media/")


class PendingDiscountCodeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method == "GET" and pending.CODE_PARAM in request.GET and not request.htmx and not request.path.startswith(SKIPPED_PREFIXES):
            self.capture(request)
        return self.get_response(request)

    def capture(self, request):
        try:
            discount, is_new = pending.capture(request, current_cart(request))
        except ValidationError as error:
            messages.error(request, error.messages[0])
        else:
            if is_new:
                messages.success(request, f"{discount.code} indirim kodu uygulandı.")
