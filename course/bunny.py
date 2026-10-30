"""Bunny Stream istemcisi. Video önce oluşturulur, dosya TUS ile parça parça gönderilir; kesilirse kaldığı yerden sürer.

Oynatma doğrudan CDN'deki HLS listesinden yapılır (Video.js `<hlsjs-video>`); iframe kullanılmaz.
Ortak platform arayüzünün Bunny karşılığıdır (bkz. `course.video_service`).
"""

import base64
import hashlib
import re
import time
import urllib.parse
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import requests
from django.conf import settings
from django.utils.translation import gettext_lazy as _

from course.video_service import RemoteVideo, VideoServiceError, VideoServiceNotConfigured, missing_settings

LABEL = "Bunny Stream"
# Kursun Bunny'deki koleksiyonu
FOLDER_FIELD = "video_collection_id"
REQUIRED_SETTINGS = ("BUNNY_LIBRARY_ID", "BUNNY_API_KEY", "BUNNY_CDN_HOST")

API_ROOT = "https://video.bunnycdn.com"
TUS_ENDPOINT = f"{API_ROOT}/tusupload"
TIMEOUT = 30
TUS_CHUNK_SIZE = 32 * 1024 * 1024
TUS_TIMEOUT = 300
TUS_RETRIES = 3
# Kütüphane listelenirken sayfa başına video/koleksiyon sayısı (Bunny en çok 1000 verir; her sayfa ayrı istek, ~1-2 sn)
LIST_PAGE_SIZE = 1000
# TUS imzası bu süre geçerli; büyük dosyaların gönderimi bitene kadar yetmeli.
UPLOAD_SIGNATURE_SECONDS = 6 * 60 * 60
# Oynatma linkleri bu süre geçerli (CDN token koruması açıksa).
PLAYBACK_URL_SECONDS = 6 * 60 * 60
SRT_TIMESTAMP = re.compile(r"(\d{2}:\d{2}:\d{2}),(\d{3})")

# Bunny'nin video durum kodları
STATE_NAMES = {
    0: "created",
    1: "uploaded",
    2: "processing",
    3: "transcoding",
    4: "finished",
    5: "error",
    6: "upload_failed",
    7: "jit_segmenting",
    8: "jit_playlists_created",
}
# Dosya Bunny'ye ulaştıktan sonraki aşamalar; stüdyoda açıklanır.
STATE_LABELS = {
    "created": _("Bunny sıraya aldı"),
    "uploaded": _("Bunny dosyayı aldı"),
    "processing": _("Bunny işlemeye başladı"),
    "transcoding": _("Bunny kaliteleri hazırlıyor"),
}


@dataclass
class VideoStatus:
    code: int
    progress: int
    duration: int

    @property
    def state(self):
        return STATE_NAMES.get(self.code, str(self.code))

    @property
    def is_ready(self):
        return self.code == 4

    @property
    def is_failed(self):
        return self.code in (5, 6)

    @property
    def key(self):
        # Bunny'de oynatma için ek anahtar gerekmez (Vimeo'daki gizli bağlantı anahtarının karşılığı).
        return ""


@dataclass
class LibraryVideo:
    """Kütüphanedeki bir video (fazla videoları bulmak için listelenir)."""

    id: str
    title: str
    collection_id: str
    duration: int
    size: int
    uploaded_at: datetime | None
    code: int

    @property
    def state(self):
        return STATE_NAMES.get(self.code, str(self.code))

    @property
    def is_ready(self):
        return self.code == 4


def is_configured():
    return not missing_settings(REQUIRED_SETTINGS)


def _credentials():
    if not settings.BUNNY_LIBRARY_ID or not settings.BUNNY_API_KEY:
        raise VideoServiceNotConfigured("BUNNY_LIBRARY_ID / BUNNY_API_KEY tanımlı değil.")
    return settings.BUNNY_LIBRARY_ID, settings.BUNNY_API_KEY


def _error_message(response):
    try:
        data = response.json()
    except ValueError:
        return f"Bunny {response.status_code}: {response.text[:200]}".strip()
    detail = data.get("Message") or data.get("message") or data.get("title") or ""
    return f"Bunny {response.status_code}: {detail}".strip()


def api(method, path, **kwargs):
    library_id, api_key = _credentials()
    headers = {"AccessKey": api_key, "Accept": "application/json"}
    try:
        response = requests.request(
            method, f"{API_ROOT}/library/{library_id}{path}", headers=headers, timeout=TIMEOUT, **kwargs
        )
    except requests.RequestException as error:
        raise VideoServiceError(f"Bunny'ye ulaşılamadı: {error}") from error
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


def check():
    """Bağlantıyı dener; kütüphanedeki video sayısını döner."""
    data = api("GET", "/videos", params={"page": 1, "itemsPerPage": 1})
    return _("Bağlantı kuruldu · kütüphanede %(count)s video") % {"count": data.get("totalItems", 0)}


# Video ve koleksiyon


def create_folder(name):
    """Kursun koleksiyonu (Vimeo'daki klasör karşılığı); kimliğini döner."""
    return api("POST", "/collections", json={"name": name})["guid"]


def create_video(title, folder="", size=0):
    body = {"title": title}
    if folder:
        body["collectionId"] = folder
    return RemoteVideo(id=api("POST", "/videos", json=body)["guid"])


def finish_upload(video, folder):
    """Video koleksiyonda açıldığı için gönderimden sonra yapılacak bir şey yok."""


def video_status(video_id):
    data = api("GET", f"/videos/{video_id}")
    return VideoStatus(
        code=int(data.get("status") or 0),
        progress=int(data.get("encodeProgress") or 0),
        duration=int(data.get("length") or 0),
    )


def fetch_duration(video_id):
    """Videonun süresi (saniye)."""
    if not video_id:
        raise VideoServiceError("Video kimliği boş.")
    return video_status(video_id).duration


def rename_video(video_id, title):
    api("POST", f"/videos/{video_id}", json={"title": title})


def delete_video(video_id):
    _ignore_missing(api, "DELETE", f"/videos/{video_id}")


def _all_pages(path):
    page = 1
    while True:
        data = api("GET", path, params={"page": page, "itemsPerPage": LIST_PAGE_SIZE})
        items = data.get("items") or []
        yield from items
        if not items or page * LIST_PAGE_SIZE >= int(data.get("totalItems") or 0):
            return
        page += 1


def _parse_date(value):
    """Bunny tarihleri saat dilimi olmadan, UTC olarak verir."""
    try:
        parsed = datetime.fromisoformat(value) if value else None
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC) if parsed and parsed.tzinfo is None else parsed


def list_videos():
    """Kütüphanedeki bütün videolar."""
    return [
        LibraryVideo(
            id=item["guid"],
            title=item.get("title") or "",
            collection_id=item.get("collectionId") or "",
            duration=int(item.get("length") or 0),
            size=int(item.get("storageSize") or 0),
            uploaded_at=_parse_date(item.get("dateUploaded")),
            code=int(item.get("status") or 0),
        )
        for item in _all_pages("/videos")
    ]


def list_collections():
    """Koleksiyon kimliği → adı."""
    return {item["guid"]: item.get("name") or "" for item in _all_pages("/collections")}


# Dosya gönderimi (TUS)


def _tus_headers(video_id):
    library_id, api_key = _credentials()
    expire = str(int(time.time()) + UPLOAD_SIGNATURE_SECONDS)
    signature = hashlib.sha256(f"{library_id}{api_key}{expire}{video_id}".encode()).hexdigest()
    return {
        "AuthorizationSignature": signature,
        "AuthorizationExpire": expire,
        "VideoId": video_id,
        "LibraryId": str(library_id),
        "Tus-Resumable": "1.0.0",
    }


def _b64(text):
    return base64.b64encode(text.encode()).decode()


def _tus_offset(upload_url, headers):
    response = requests.head(upload_url, headers=headers, timeout=TIMEOUT)
    if not response.ok:
        raise VideoServiceError(_error_message(response))
    return int(response.headers["Upload-Offset"])


def upload_file(video, path, title, on_progress=None):
    """Dosyayı TUS ile gönderir. Hata olursa sunucudaki konumu sorup oradan devam eder; üst üste 3 hatada vazgeçer."""
    size = Path(path).stat().st_size
    headers = _tus_headers(video.id)
    try:
        created = requests.post(
            TUS_ENDPOINT,
            headers={
                **headers,
                "Upload-Length": str(size),
                "Upload-Metadata": f"filetype {_b64('video/mp4')},title {_b64(title)}",
            },
            timeout=TIMEOUT,
        )
    except requests.RequestException as error:
        raise VideoServiceError(f"Bunny'ye ulaşılamadı: {error}") from error
    if not created.ok or "Location" not in created.headers:
        raise VideoServiceError(_error_message(created))
    upload_url = urllib.parse.urljoin(TUS_ENDPOINT, created.headers["Location"])

    offset, failures = 0, 0
    with open(path, "rb") as file:
        while offset < size:
            file.seek(offset)
            try:
                response = requests.patch(
                    upload_url,
                    data=file.read(TUS_CHUNK_SIZE),
                    headers={**headers, "Upload-Offset": str(offset), "Content-Type": "application/offset+octet-stream"},
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
            offset = _tus_offset(upload_url, headers)


# Altyazı


def as_webvtt(text):
    """SRT zaman damgaları WebVTT'ye çevrilir, VTT olduğu gibi kalır (oynatıcı WebVTT bekler)."""
    text = text.lstrip("﻿").replace("\r\n", "\n").replace("\r", "\n")
    if text.startswith("WEBVTT"):
        return text
    lines = [SRT_TIMESTAMP.sub(r"\1.\2", line) if "-->" in line else line for line in text.split("\n")]
    return "WEBVTT\n\n" + "\n".join(lines).lstrip("\n")


def upload_caption(video_id, language, label, path):
    """Altyazıyı WebVTT olarak ekler; aynı dildeki önceki altyazının yerine geçer. Altyazının dil kodunu döner."""
    body = as_webvtt(Path(path).read_text(encoding="utf-8-sig"))
    api(
        "POST",
        f"/videos/{video_id}/captions/{language}",
        json={"srclang": language, "label": label, "captionsFile": base64.b64encode(body.encode()).decode()},
    )
    return language


def delete_caption(video_id, language):
    _ignore_missing(api, "DELETE", f"/videos/{video_id}/captions/{language}")


# Oynatma adresleri


def _signed(path, video_id):
    """CDN token koruması açıksa adres kısa süreli imzalanır; imza video klasörünü kapsar ki HLS parçaları da açılsın."""
    host = settings.BUNNY_CDN_HOST
    if not settings.BUNNY_CDN_TOKEN_AUTH or not settings.BUNNY_TOKEN_KEY:
        return f"https://{host}{path}"
    directory = f"/{video_id}/"
    expires = str(int(time.time()) + PLAYBACK_URL_SECONDS)
    raw = hashlib.sha256(f"{settings.BUNNY_TOKEN_KEY}{directory}{expires}token_path={directory}".encode()).digest()
    token = base64.b64encode(raw).decode().replace("+", "-").replace("/", "_").replace("=", "")
    token_path = urllib.parse.quote(directory, safe="")
    return f"https://{host}/bcdn_token={token}&expires={expires}&token_path={token_path}{path}"


def playback(video_id, key=""):
    """Oynatıcı verisi: HLS listesi ve kapak görseli."""
    return {"platform": "bunny", "src": playlist_url(video_id), "poster": thumbnail_url(video_id)}


def playlist_url(video_id):
    return _signed(f"/{video_id}/playlist.m3u8", video_id) if video_id else ""


def thumbnail_url(video_id):
    return _signed(f"/{video_id}/thumbnail.jpg", video_id) if video_id else ""


def caption_url(video_id, language):
    return _signed(f"/{video_id}/captions/{language}.vtt", video_id)


def dashboard_url(video_id):
    """Videonun Bunny panelindeki oynatma sayfası (stüdyodaki "önizle" bağlantısı)."""
    return f"https://iframe.mediadelivery.net/play/{settings.BUNNY_LIBRARY_ID}/{video_id}"
