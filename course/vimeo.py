"""Vimeo API istemcisi (v3.4). Video yükleme tus protokolüyle parça parça yapılır; kesilirse kaldığı yerden sürer.

Oynatma Video.js `<vimeo-video>` ile Vimeo'nun kendi oynatıcısından yapılır; videolar gizlidir ve yalnız izinli alan
adlarında gömülür. Ortak platform arayüzünün Vimeo karşılığıdır (bkz. `course.video_service`).
"""

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests
from django.conf import settings
from django.utils.translation import gettext_lazy as _

from course.bunny import as_webvtt
from course.video_service import RemoteVideo, VideoServiceError, VideoServiceNotConfigured, missing_settings

LABEL = "Vimeo"
# Kursun Vimeo'daki klasörü (API adresi, ör. /users/1/projects/2)
FOLDER_FIELD = "vimeo_folder_uri"
REQUIRED_SETTINGS = ("VIMEO_ACCESS_TOKEN",)
# Anahtarda bulunması gereken yetkiler: yükleme, başlık/altyazı düzenleme, silme.
REQUIRED_SCOPES = {"upload", "edit", "delete"}
API_ROOT = "https://api.vimeo.com"
API_ACCEPT = "application/vnd.vimeo.*+json;version=3.4"
TIMEOUT = 30
TUS_CHUNK_SIZE = 32 * 1024 * 1024
TUS_TIMEOUT = 300
TUS_RETRIES = 3
# Gizli video: vimeo.com'da açılmaz, yalnız izinli alan adlarına gömülür, indirilemez.
UPLOAD_PRIVACY = {"view": "disable", "embed": "whitelist", "download": False}
# Dosya Vimeo'ya ulaştıktan sonraki aşamalar (videonun genel durumu); stüdyoda açıklanır.
STATE_LABELS = {
    "uploading": _("Vimeo dosyayı alıyor"),
    "transcode_starting": _("Vimeo işlemeye başladı"),
    "transcoding": _("Vimeo kaliteleri hazırlıyor"),
}


@dataclass
class VideoStatus:
    transcode: str
    duration: int
    # Gizli bağlantı anahtarı (vimeo.com/<id>?h=<anahtar>); oynatıcı bununla açar.
    key: str
    # Videonun genel durumu: uploading → transcode_starting → transcoding → available
    state: str = ""
    # Vimeo işleme yüzdesi vermiyor.
    progress: int = 0

    @property
    def is_ready(self):
        return self.transcode == "complete"

    @property
    def is_failed(self):
        return self.transcode == "error"


def is_configured():
    return not missing_settings(REQUIRED_SETTINGS)


def _token():
    if not settings.VIMEO_ACCESS_TOKEN:
        raise VideoServiceNotConfigured("VIMEO_ACCESS_TOKEN tanımlı değil.")
    return settings.VIMEO_ACCESS_TOKEN


def _error_message(response):
    try:
        data = response.json()
    except ValueError:
        return f"Vimeo {response.status_code}: {response.text[:200]}".strip()
    detail = data.get("developer_message") or data.get("error") or ""
    return f"Vimeo {response.status_code}: {detail}".strip()


def api(method, path, **kwargs):
    headers = {"Authorization": f"bearer {_token()}", "Accept": API_ACCEPT}
    try:
        response = requests.request(method, f"{API_ROOT}{path}", headers=headers, timeout=TIMEOUT, **kwargs)
    except requests.RequestException as error:
        raise VideoServiceError(f"Vimeo'ya ulaşılamadı: {error}") from error
    if not response.ok:
        raise VideoServiceError(_error_message(response))
    try:
        return response.json() if response.content else {}
    except ValueError:
        return {}


def _ignore_missing(call, *args):
    """Silme işlerinde hedef zaten yoksa amaca ulaşılmış sayılır."""
    try:
        call(*args)
    except VideoServiceError as error:
        if "404" not in str(error):
            raise


def _last_part(uri):
    return uri.rstrip("/").rsplit("/", 1)[-1]


def token_scopes():
    """Erişim anahtarının yetkileri (ör. {"upload", "edit", "interact"})."""
    return set((api("GET", "/oauth/verify", params={"fields": "scope"}).get("scope") or "").split())


def check():
    """Bağlantıyı ve anahtarın yetkilerini dener."""
    missing = REQUIRED_SCOPES - token_scopes()
    if missing:
        raise VideoServiceError(
            _("Anahtarda eksik yetki: %(scopes)s") % {"scopes": ", ".join(sorted(missing))}
        )
    return _("Bağlantı kuruldu · yükleme, düzenleme ve silme yetkisi var")


# Video ve klasör


def create_folder(name):
    """Vimeo klasörü açar, URI'sini döner."""
    return api("POST", "/me/projects", json={"name": name}, params={"fields": "uri"})["uri"]


def create_video(title, folder="", size=0):
    """Vimeo'da boş video kaydı açar; dosya `upload_file` ile verilen adrese gönderilir."""
    data = api(
        "POST",
        "/me/videos",
        json={"upload": {"approach": "tus", "size": str(size)}, "name": title, "privacy": UPLOAD_PRIVACY},
        params={"fields": "uri,upload.upload_link"},
    )
    return RemoteVideo(id=_last_part(data["uri"]), upload_url=data["upload"]["upload_link"])


def allow_domains(video_id, domains=None):
    for domain in domains if domains is not None else settings.VIMEO_EMBED_DOMAINS:
        api("PUT", f"/videos/{video_id}/privacy/domains/{domain}")


def add_to_folder(folder, video_id):
    api("PUT", f"/me/projects/{_last_part(folder)}/videos/{video_id}")


def finish_upload(video, folder):
    """Gönderimden sonra: video yalnız izinli alan adlarında oynar ve kursun klasörüne eklenir.

    Klasör düzeni yardımcıdır (anahtarda "interact" yetkisi ister); eklenemezse video yine kullanılır.
    """
    allow_domains(video.id)
    if folder:
        try:
            add_to_folder(folder, video.id)
        except VideoServiceError:
            pass


def video_status(video_id):
    data = api("GET", f"/videos/{video_id}", params={"fields": "status,transcode.status,duration,player_embed_url"})
    query = parse_qs(urlparse(data.get("player_embed_url") or "").query)
    return VideoStatus(
        transcode=(data.get("transcode") or {}).get("status", ""),
        duration=int(data.get("duration") or 0),
        key=query.get("h", [""])[0],
        state=data.get("status") or "",
    )


def fetch_duration(video_id):
    """Videonun süresi (saniye)."""
    if not video_id:
        raise VideoServiceError("Video kimliği boş.")
    return int(api("GET", f"/videos/{video_id}", params={"fields": "duration"})["duration"])


def rename_video(video_id, title):
    api("PATCH", f"/videos/{video_id}", json={"name": title}, params={"fields": "uri"})


def delete_video(video_id):
    _ignore_missing(api, "DELETE", f"/videos/{video_id}")


# Dosya gönderimi (tus)


def _tus_offset(upload_url):
    response = requests.head(upload_url, headers={"Tus-Resumable": "1.0.0", "Accept": API_ACCEPT}, timeout=TIMEOUT)
    if not response.ok:
        raise VideoServiceError(_error_message(response))
    return int(response.headers["Upload-Offset"])


def upload_file(video, path, title, on_progress=None):
    """Dosyayı tus ile gönderir. Hata olursa sunucudaki konumu sorup oradan devam eder; üst üste 3 hatada vazgeçer."""
    size = Path(path).stat().st_size
    try:
        offset = _tus_offset(video.upload_url)
    except requests.RequestException as error:
        raise VideoServiceError(f"Vimeo'ya ulaşılamadı: {error}") from error
    failures = 0
    with open(path, "rb") as file:
        while offset < size:
            file.seek(offset)
            try:
                response = requests.patch(
                    video.upload_url,
                    data=file.read(TUS_CHUNK_SIZE),
                    headers={
                        "Tus-Resumable": "1.0.0",
                        "Upload-Offset": str(offset),
                        "Content-Type": "application/offset+octet-stream",
                        "Accept": API_ACCEPT,
                    },
                    timeout=TUS_TIMEOUT,
                )
            except requests.RequestException as error:
                response, message = None, f"Yükleme kesildi: {error}"
            if response is not None and response.ok:
                offset = int(response.headers["Upload-Offset"])
                failures = 0
                if on_progress:
                    on_progress(offset, size)
                continue
            if response is not None:
                message = _error_message(response)
            failures += 1
            if failures >= TUS_RETRIES:
                raise VideoServiceError(message)
            offset = _tus_offset(video.upload_url)


# Altyazı


def _text_tracks(video_id, language):
    data = api("GET", f"/videos/{video_id}/texttracks", params={"fields": "uri,language"})
    return [track["uri"] for track in data.get("data", []) if track.get("language") == language]


def delete_caption(video_id, language):
    for uri in _text_tracks(video_id, language):
        _ignore_missing(api, "DELETE", uri)


def upload_caption(video_id, language, label, path):
    """Altyazıyı WebVTT olarak ekler ve etkinleştirir; aynı dildeki önceki altyazının yerine geçer. Dil kodunu döner."""
    body = as_webvtt(Path(path).read_text(encoding="utf-8-sig")).encode()
    delete_caption(video_id, language)
    track = api("POST", f"/videos/{video_id}/texttracks", json={"type": "subtitles", "language": language, "name": label})
    try:
        response = requests.put(track["link"], data=body, timeout=TIMEOUT)
    except requests.RequestException as error:
        _ignore_missing(api, "DELETE", track["uri"])
        raise VideoServiceError(f"Altyazı gönderilemedi: {error}") from error
    if not response.ok:
        # Altyazı sunucusu düz metin hata döner (ör. "Unable to parse captions"); boş kayıt Vimeo'da bırakılmaz.
        _ignore_missing(api, "DELETE", track["uri"])
        raise VideoServiceError(f"Vimeo {response.status_code}: {response.text[:200]}")
    api("PATCH", track["uri"], json={"active": True})
    return language


# Oynatma adresleri


def playback(video_id, key=""):
    """Oynatıcı verisi: Vimeo bağlantısı (gizli videolarda anahtarla). Kapak görselini Vimeo oynatıcısı kendisi gösterir."""
    src = f"https://vimeo.com/{video_id}?h={key}" if key else f"https://vimeo.com/{video_id}"
    return {"platform": "vimeo", "src": src, "poster": ""}


def caption_url(video_id, language):
    """Altyazıları Vimeo oynatıcısı kendisi yükler; ayrı adres yok."""
    return ""


def dashboard_url(video_id):
    """Videonun Vimeo'daki yönetim sayfası (stüdyodaki "önizle" bağlantısı)."""
    return f"https://vimeo.com/manage/videos/{video_id}"
