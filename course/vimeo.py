"""Vimeo API istemcisi (v3.4). Video yükleme tus protokolüyle parça parça yapılır; kesilirse kaldığı yerden sürer."""

import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests
from django.conf import settings

API_ROOT = "https://api.vimeo.com"
API_ACCEPT = "application/vnd.vimeo.*+json;version=3.4"
TIMEOUT = 30
TUS_CHUNK_SIZE = 32 * 1024 * 1024
TUS_TIMEOUT = 300
TUS_RETRIES = 3
# Gizli video: vimeo.com'da açılmaz, yalnız izinli alan adlarına gömülür, indirilemez.
UPLOAD_PRIVACY = {"view": "disable", "embed": "whitelist", "download": False}
SRT_TIMESTAMP = re.compile(r"(\d{2}:\d{2}:\d{2}),(\d{3})")


class VimeoError(Exception):
    pass


class VimeoNotConfigured(VimeoError):
    pass


@dataclass
class VimeoVideo:
    id: str
    upload_link: str = ""


@dataclass
class VimeoStatus:
    transcode: str
    duration: int
    hash: str
    # Videonun genel durumu: uploading → transcode_starting → transcoding → available
    state: str = ""

    @property
    def is_ready(self):
        return self.transcode == "complete"

    @property
    def is_failed(self):
        return self.transcode == "error"


def _token():
    if not settings.VIMEO_ACCESS_TOKEN:
        raise VimeoNotConfigured("VIMEO_ACCESS_TOKEN tanımlı değil.")
    return settings.VIMEO_ACCESS_TOKEN


def _error_message(response):
    try:
        data = response.json()
    except ValueError:
        return f"Vimeo {response.status_code}"
    detail = data.get("developer_message") or data.get("error") or ""
    return f"Vimeo {response.status_code}: {detail}".strip()


def api(method, path, **kwargs):
    headers = {"Authorization": f"bearer {_token()}", "Accept": API_ACCEPT}
    try:
        response = requests.request(method, f"{API_ROOT}{path}", headers=headers, timeout=TIMEOUT, **kwargs)
    except requests.RequestException as error:
        raise VimeoError(f"Vimeo'ya ulaşılamadı: {error}") from error
    if not response.ok:
        raise VimeoError(_error_message(response))
    return response.json() if response.content else {}


def _video_id(uri):
    return uri.rstrip("/").rsplit("/", 1)[-1]


def fetch_duration(vimeo_id):
    """Videonun süresini (saniye) Vimeo API'sinden okur."""
    if not vimeo_id:
        raise VimeoError("Vimeo video kimliği boş.")
    return int(api("GET", f"/videos/{vimeo_id}", params={"fields": "duration"})["duration"])


def create_video(name, size):
    """Vimeo'da boş video kaydı açar; dosya `upload_file` ile `upload_link` adresine gönderilir."""
    data = api(
        "POST",
        "/me/videos",
        json={"upload": {"approach": "tus", "size": str(size)}, "name": name, "privacy": UPLOAD_PRIVACY},
        params={"fields": "uri,upload.upload_link"},
    )
    return VimeoVideo(id=_video_id(data["uri"]), upload_link=data["upload"]["upload_link"])


def _tus_offset(upload_link):
    response = requests.head(upload_link, headers={"Tus-Resumable": "1.0.0", "Accept": API_ACCEPT}, timeout=TIMEOUT)
    if not response.ok:
        raise VimeoError(_error_message(response))
    return int(response.headers["Upload-Offset"])


def upload_file(upload_link, path, on_progress=None):
    """Dosyayı tus ile gönderir. Hata olursa sunucudaki konumu sorup oradan devam eder; üst üste 3 hatada vazgeçer."""
    size = Path(path).stat().st_size
    offset = _tus_offset(upload_link)
    failures = 0
    with open(path, "rb") as file:
        while offset < size:
            file.seek(offset)
            try:
                response = requests.patch(
                    upload_link,
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
                raise VimeoError(message)
            offset = _tus_offset(upload_link)


def video_status(vimeo_id):
    data = api("GET", f"/videos/{vimeo_id}", params={"fields": "status,transcode.status,duration,player_embed_url"})
    query = parse_qs(urlparse(data.get("player_embed_url") or "").query)
    return VimeoStatus(
        transcode=(data.get("transcode") or {}).get("status", ""),
        duration=int(data.get("duration") or 0),
        hash=query.get("h", [""])[0],
        state=data.get("status") or "",
    )


def delete_video(vimeo_id):
    try:
        api("DELETE", f"/videos/{vimeo_id}")
    except VimeoError as error:
        # Zaten silinmişse hedefe ulaşılmış sayılır.
        if "404" not in str(error):
            raise


def allow_domains(vimeo_id, domains=None):
    for domain in domains if domains is not None else settings.VIMEO_EMBED_DOMAINS:
        api("PUT", f"/videos/{vimeo_id}/privacy/domains/{domain}")


def rename_video(vimeo_id, name):
    api("PATCH", f"/videos/{vimeo_id}", json={"name": name}, params={"fields": "uri"})


def create_folder(name):
    """Vimeo klasörü açar, URI'sini döner (ör. /users/1/projects/2)."""
    return api("POST", "/me/projects", json={"name": name}, params={"fields": "uri"})["uri"]


def token_scopes():
    """Erişim anahtarının yetkileri (ör. {"upload", "edit", "interact"})."""
    return set((api("GET", "/oauth/verify", params={"fields": "scope"}).get("scope") or "").split())


def folder_video_total(folder_uri):
    data = api("GET", folder_uri, params={"fields": "metadata.connections.videos.total"})
    return int(data["metadata"]["connections"]["videos"]["total"])


def add_to_folder(folder_uri, vimeo_id):
    api("PUT", f"/me/projects/{_video_id(folder_uri)}/videos/{vimeo_id}")


def as_webvtt(text):
    """Vimeo'nun altyazı adresi SRT'yi ayrıştıramıyor; SRT zaman damgaları WebVTT'ye çevrilir, VTT olduğu gibi kalır."""
    text = text.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    if text.startswith("WEBVTT"):
        return text
    lines = [SRT_TIMESTAMP.sub(r"\1.\2", line) if "-->" in line else line for line in text.split("\n")]
    return "WEBVTT\n\n" + "\n".join(lines).lstrip("\n")


def upload_text_track(vimeo_id, language, name, path):
    """Altyazıyı WebVTT olarak ekler ve etkinleştirir; text track URI'sini döner."""
    track = api(
        "POST", f"/videos/{vimeo_id}/texttracks", json={"type": "subtitles", "language": language, "name": name}
    )
    try:
        body = as_webvtt(Path(path).read_text(encoding="utf-8-sig")).encode()
        response = requests.put(track["link"], data=body, timeout=TIMEOUT)
    except requests.RequestException as error:
        raise VimeoError(f"Altyazı gönderilemedi: {error}") from error
    if not response.ok:
        # Altyazı sunucusu düz metin hata döner (ör. "Unable to parse captions"); boş kayıt Vimeo'da bırakılmaz.
        delete_text_track(track["uri"])
        raise VimeoError(f"Vimeo {response.status_code}: {response.text[:200]}")
    api("PATCH", track["uri"], json={"active": True})
    return track["uri"]


def delete_text_track(uri):
    try:
        api("DELETE", uri)
    except VimeoError as error:
        # Video ya da altyazı Vimeo'da zaten silinmişse hedefe ulaşılmış sayılır.
        if "404" not in str(error):
            raise
