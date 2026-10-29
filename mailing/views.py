import base64

from django.http import HttpResponse, HttpResponseNotFound, HttpResponseRedirect
from django.views.decorators.cache import never_cache

from mailing.models import EmailLog
from mailing.tracking import unsign_click

# 1x1 saydam GIF
PIXEL = base64.b64decode("R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7")


def _user_agent(request):
    return request.headers.get("User-Agent", "")


@never_cache
def email_open(request, token):
    """Açılma görseli: e-posta istemcisi görselleri yüklediğinde sayılır. Kayıt yoksa da görsel döner."""
    log = EmailLog.objects.filter(token=token).first()
    if log is not None:
        log.record_open(_user_agent(request))
    return HttpResponse(PIXEL, content_type="image/gif")


@never_cache
def email_click(request, token):
    """Tıklama yönlendirmesi: hedef adres imzalıdır, imzasız adrese yönlendirilmez."""
    url, secret = unsign_click(request.GET.get("u", ""))
    if not url:
        return HttpResponseNotFound()
    log = EmailLog.objects.filter(token=token).first()
    if log is not None:
        # Şifre/onay bağlantısı gibi gizli adresler kaydedilmez; yalnız tıklandığı bilinir.
        log.record_click("" if secret else url, _user_agent(request))
    return HttpResponseRedirect(url)
