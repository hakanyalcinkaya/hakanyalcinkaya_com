"""Bağlantıyla gelen indirim kodu (?code=KOD, discount.pending): sitenin herhangi bir sayfasında GET ile gelen kod
oturuma alınır, kullanıcıya bildirilir ve kod parametresi adresten çıkarılarak aynı sayfaya yönlendirilir."""

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import redirect

from cart.request_cart import current_cart
from discount import pending

SKIPPED_PREFIXES = ("/studio/", "/admin/", "/static/", "/media/")


class PendingDiscountCodeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method == "GET" and pending.CODE_PARAM in request.GET and not request.htmx and not request.path.startswith(SKIPPED_PREFIXES):
            return self.capture(request)
        return self.get_response(request)

    def capture(self, request):
        try:
            discount = pending.capture(request, current_cart(request))
        except ValidationError as error:
            messages.error(request, error.messages[0])
        else:
            messages.success(request, f"{discount.code} indirim kodu uygulandı.")
        params = request.GET.copy()
        params.pop(pending.CODE_PARAM)
        query = params.urlencode()
        return redirect(f"{request.path}?{query}" if query else request.path)
