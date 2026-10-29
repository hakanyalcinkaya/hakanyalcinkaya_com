"""Video platformları için ortak arayüz. Her platform modülü (`course.bunny`, `course.vimeo`) aynı adlarla çalışır:

- `LABEL`, `FOLDER_FIELD` (kursun platformdaki klasör/koleksiyon alanı), `REQUIRED_SETTINGS`, `STATE_LABELS`
- `is_configured()`, `check()` (bağlantıyı dener, kısa açıklama döner)
- `create_folder(name)`, `create_video(title, folder, size)` → `RemoteVideo`, `upload_file(video, path, title, on_progress)`,
  `finish_upload(video, folder)` (yükleme sonrası ayarlar), `video_status(video_id)`, `rename_video`, `delete_video`,
  `fetch_duration`
- `upload_caption(video_id, language, label, path)`, `delete_caption(video_id, language)`
- `playback(video_id, key)` → oynatıcı verisi, `caption_url(video_id, language)`, `dashboard_url(video_id)`

Yeni yüklemeler sitedeki ayarda seçili platforma gider; her video hangi platformda olduğunu kendi kaydında tutar.
"""

from dataclasses import dataclass
from importlib import import_module

from django.conf import settings

from core.models import SiteSettings, VideoPlatform


class VideoServiceError(Exception):
    pass


class VideoServiceNotConfigured(VideoServiceError):
    pass


@dataclass
class RemoteVideo:
    """Platformda açılan video kaydı; Vimeo dosyanın gönderileceği adresi de verir."""

    id: str
    upload_url: str = ""


def missing_settings(names):
    return [name for name in names if not getattr(settings, name, "")]


def get(platform):
    """Platform modülü (ör. "bunny" → course.bunny)."""
    return import_module(f"course.{VideoPlatform(platform).value}")


def current_name():
    return SiteSettings.load().video_platform


def current():
    return get(current_name())


def choices():
    """Ayarlar sayfası için: her platform, etiketi ve eksik ayarlarıyla."""
    return [
        {"value": value, "label": label, "missing": missing_settings(get(value).REQUIRED_SETTINGS)}
        for value, label in VideoPlatform.choices
    ]
