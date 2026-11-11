"""Ziyaretçi bilgileri (sepete ekleme, kayıt ve giriş kayıtlarının data alanı): ağ, konum, cihaz, dil, tarayıcı, geliş
ve üyelik.

Site Cloudflare arkasında: IP CF-Connecting-IP'den, ülke CF-IPCountry'den okunur. Şehir, bölge, saat dilimi ve internet
sağlayıcısı MaxMind GeoLite2 dosyalarından gelir (GEOIP_PATH klasöründe GeoLite2-City.mmdb ve GeoLite2-ASN.mmdb); dosya
yoksa bu alanlar boş kalır. Enlem/boylam tutulmaz, konum şehir düzeyindedir. IP, IP_RETENTION_DAYS gün sonra maskelenir
(mask_visitor_ips); diğer bilgiler kalır.

Tarayıcı tarafı (ekran, saat dilimi, tema, siteye ilk giriş, UTM) site.js'in yazdığı CLIENT_COOKIE çerezinden okunur;
çerez yoksa (JS kapalı) yalnız sunucu bilgileri yazılır. Çerezdeki değerler bilinen anahtarlarla ve uzunlukla sınırlanır.
"""

import ipaddress
import json
import logging
from functools import cache
from pathlib import Path
from urllib.parse import unquote, urlparse

from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from ipware import get_client_ip
from user_agents import parse as parse_user_agent

logger = logging.getLogger(__name__)

# Kayıtlardaki IP bu kadar gün sonra maskelenir.
IP_RETENTION_DAYS = 180

CLIENT_COOKIE = "hy_client"
IP_HEADERS = ("HTTP_CF_CONNECTING_IP", "HTTP_X_FORWARDED_FOR", "HTTP_X_REAL_IP", "REMOTE_ADDR")
# CF-IPCountry'nin ülke olmayan değerleri: XX bilinmiyor, T1 Tor.
UNKNOWN_COUNTRIES = {"", "XX", "T1"}
CLIENT_HINTS = dict(
    brands="HTTP_SEC_CH_UA",
    mobile="HTTP_SEC_CH_UA_MOBILE",
    platform="HTTP_SEC_CH_UA_PLATFORM",
    platform_version="HTTP_SEC_CH_UA_PLATFORM_VERSION",
    model="HTTP_SEC_CH_UA_MODEL",
)
UTM_KEYS = ("source", "medium", "campaign", "term", "content")
# Çerezden kabul edilen alanlar: kısa anahtar → (kayıttaki ad, tür).
CLIENT_FIELDS = dict(
    sw=("screen_width", int),
    sh=("screen_height", int),
    vw=("viewport_width", int),
    vh=("viewport_height", int),
    dpr=("pixel_ratio", float),
    cd=("color_depth", int),
    tz=("timezone", str),
    tzo=("utc_offset_minutes", int),
    langs=("languages", list),
    cs=("color_scheme", str),
    rm=("reduced_motion", bool),
    tp=("touch_points", int),
    hc=("cpu_cores", int),
    dm=("memory_gb", float),
    net=("connection", str),
    save=("data_saver", bool),
    theme=("site_theme", str),
    accent=("site_accent", str),
    pv=("page_views", int),
)
FIRST_FIELDS = dict(land=("landing_path", str), ref=("referrer", str), at=("first_seen", str))
MAX_TEXT = 300


def _text(value, limit=MAX_TEXT):
    return str(value)[:limit] if value is not None else ""


def client_ip(request):
    return get_client_ip(request, request_header_order=IP_HEADERS)[0] or ""


def _network(ip):
    if not ip:
        return dict(ip="")
    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        return dict(ip=_text(ip, 64))
    return dict(ip=str(address), version=address.version, is_private=address.is_private)


@cache
def _reader(name):
    """GeoLite2 dosyası için okuyucu; GEOIP_PATH yoksa ya da dosya açılamazsa None."""
    folder = getattr(settings, "GEOIP_PATH", "")
    path = Path(folder) / name if folder else None
    if not path or not path.exists():
        return None
    try:
        import geoip2.database

        return geoip2.database.Reader(str(path))
    except Exception:  # noqa: BLE001 — dosya bozuksa konum boş kalır
        logger.exception("GeoLite2 dosyası açılamadı: %s", path)
        return None


def _geo(request, ip):
    header = _text(request.META.get("HTTP_CF_IPCOUNTRY"), 8).upper()
    result = dict(country_code="" if header in UNKNOWN_COUNTRIES else header, is_tor=header == "T1")
    city_reader, asn_reader = _reader("GeoLite2-City.mmdb"), _reader("GeoLite2-ASN.mmdb")
    if not ip:
        return result
    if city_reader is not None:
        try:
            city = city_reader.city(ip)
            result.update(
                country_code=result["country_code"] or (city.country.iso_code or ""),
                country=city.country.names.get("tr") or city.country.name or "",
                continent=city.continent.code or "",
                region=city.subdivisions.most_specific.name or "",
                city=city.city.names.get("tr") or city.city.name or "",
                timezone=city.location.time_zone or "",
                is_eu=bool(city.country.is_in_european_union),
            )
        except Exception:  # noqa: BLE001 — adres veritabanında yoksa
            pass
    if asn_reader is not None:
        try:
            asn = asn_reader.asn(ip)
            result.update(asn=asn.autonomous_system_number, isp=asn.autonomous_system_organization or "")
        except Exception:  # noqa: BLE001
            pass
    return result


def _device_type(agent):
    if agent.is_bot:
        return "bot"
    if agent.is_tablet:
        return "tablet"
    if agent.is_mobile:
        return "mobile"
    if agent.is_pc:
        return "desktop"
    return "other"


def _agent(request):
    raw = _text(request.META.get("HTTP_USER_AGENT"), 512)
    agent = parse_user_agent(raw)
    return dict(
        raw=raw,
        type=_device_type(agent),
        browser=dict(family=agent.browser.family, version=agent.browser.version_string),
        os=dict(family=agent.os.family, version=agent.os.version_string),
        device=dict(family=agent.device.family, brand=agent.device.brand or "", model=agent.device.model or ""),
        is_touch=agent.is_touch_capable,
        hints={key: _text(request.META[header], 200).strip('"') for key, header in CLIENT_HINTS.items() if request.META.get(header)},
    )


def _languages(header):
    """Accept-Language → [{code, q}] ağırlık sırasıyla."""
    rows = []
    for part in header.split(",")[:10]:
        code, _sep, params = part.strip().partition(";")
        if not code:
            continue
        weight = 1.0
        if params.strip().startswith("q="):
            try:
                weight = float(params.strip()[2:])
            except ValueError:
                weight = 0.0
        rows.append(dict(code=code.lower()[:20], q=weight))
    return sorted(rows, key=lambda row: -row["q"])


def _language(request):
    header = _text(request.META.get("HTTP_ACCEPT_LANGUAGE"))
    languages = _languages(header)
    primary = languages[0]["code"] if languages else ""
    return dict(raw=header, languages=languages, primary=primary, base=primary.split("-")[0])


def _coerce(value, kind):
    if kind is list:
        return [_text(item, 20) for item in value[:10]] if isinstance(value, list) else []
    if kind is bool:
        return bool(value)
    try:
        return kind(value) if kind is not str else _text(value)
    except (TypeError, ValueError):
        return None


def _pick(raw, fields):
    result = {}
    for key, (name, kind) in fields.items():
        if key in raw:
            value = _coerce(raw[key], kind)
            if value is not None:
                result[name] = value
    return result


def _client(request):
    """site.js çerezi: tarayıcı/ekran bilgileri ve siteye ilk giriş (UTM dahil)."""
    try:
        raw = json.loads(unquote(request.COOKIES.get(CLIENT_COOKIE, "")) or "{}")
    except ValueError:
        raw = {}
    if not isinstance(raw, dict):
        raw = {}
    first = raw.get("first") if isinstance(raw.get("first"), dict) else {}
    utm = first.get("utm") if isinstance(first.get("utm"), dict) else {}
    first_touch = _pick(first, FIRST_FIELDS)
    first_touch["utm"] = {key: _text(utm[key], 100) for key in UTM_KEYS if utm.get(key)}
    if first_touch.get("referrer"):
        first_touch["referrer_host"] = urlparse(first_touch["referrer"]).hostname or ""
    return _pick(raw, CLIENT_FIELDS), first_touch, bool(raw)


def _visit(request, first_touch):
    referer = _text(request.META.get("HTTP_REFERER"))
    host = urlparse(referer).hostname or ""
    return dict(
        path=_text(request.path),
        referer=referer,
        referer_host=host,
        is_internal=bool(host) and host == request.META.get("HTTP_HOST", "").split(":")[0],
        is_htmx=bool(getattr(request, "htmx", False)),
        first=first_touch,
    )


def _member(user, light=False):
    if not user.is_authenticated:
        return dict(is_member=False, is_staff=False)
    if light:
        return dict(is_member=True, is_staff=user.is_staff, joined_days=(timezone.now() - user.date_joined).days)
    from order.models import Order

    return dict(
        is_member=True,
        is_staff=user.is_staff,
        joined_days=(timezone.now() - user.date_joined).days,
        paid_orders=Order.objects.sold().filter(email__iexact=user.email).count(),
        enrollments=user.enrollments.count(),
    )


def collect(request, user=None, light=False):
    """İstekten ziyaretçi bilgileri; user verilmezse request.user. light=True sık yazılan kayıtlar (ders izleme, sayfa
    ziyareti) içindir: üyelik sayıları için sorgu atılmaz. Kayıt sürümü (version) yapı değişirse artar."""
    ip = client_ip(request)
    client, first_touch, has_cookie = _client(request)
    local = timezone.localtime()
    return dict(
        version=1,
        network=_network(ip),
        geo=_geo(request, ip),
        agent=_agent(request),
        language=_language(request),
        client=dict(client, has_cookie=has_cookie),
        visit=_visit(request, first_touch),
        member=_member(user or request.user, light),
        time=dict(local=local.isoformat(timespec="seconds"), hour=local.hour, weekday=local.isoweekday()),
    )


def mask_ip(ip):
    """IPv4'te son sekizli, IPv6'da /48 sonrası sıfırlanır (85.105.12.34 → 85.105.12.0); geçersizse boş."""
    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        return ""
    prefix = 24 if address.version == 4 else 48
    return str(ipaddress.ip_network(f"{address}/{prefix}", strict=False).network_address)


DEVICE_LABELS = dict(desktop=_("Masaüstü"), mobile=_("Mobil"), tablet=_("Tablet"), bot=_("Bot"), other=_("Diğer"))
DEVICE_ICONS = dict(desktop="laptop", mobile="phone", tablet="tablet", bot="robot", other="question-circle")


def flag(code):
    """"TR" → 🇹🇷; geçersizse boş."""
    code = (code or "").upper()
    if len(code) != 2 or not code.isalpha():
        return ""
    return "".join(chr(0x1F1E6 + ord(letter) - ord("A")) for letter in code)


def summary(data):
    """Stüdyo listeleri ve tabloları için kısa özet; veri yoksa None."""
    if not data:
        return None
    geo, agent = data.get("geo") or {}, data.get("agent") or {}
    browser, system = agent.get("browser") or {}, agent.get("os") or {}
    client, network = data.get("client") or {}, data.get("network") or {}
    code = geo.get("country_code", "")
    country = geo.get("country") or code
    city = geo.get("city", "")
    device = agent.get("type", "")
    screen = f"{client['screen_width']}×{client['screen_height']}" if client.get("screen_width") else ""
    return dict(
        flag=flag(code),
        country=country,
        city=city,
        region=geo.get("region", ""),
        place=", ".join(part for part in (city, country) if part),
        device=DEVICE_LABELS.get(device, device),
        device_icon=DEVICE_ICONS.get(device, "question-circle"),
        os=" ".join(part for part in (system.get("family", ""), system.get("version", "")) if part),
        browser=" ".join(part for part in (browser.get("family", ""), browser.get("version", "").split(".")[0]) if part),
        language=(data.get("language") or {}).get("primary", ""),
        screen=screen,
        timezone=client.get("timezone", ""),
        ip=network.get("ip", ""),
        ip_masked=bool(network.get("masked")),
    )
