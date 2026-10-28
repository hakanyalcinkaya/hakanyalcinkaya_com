from .settings_base import *  # noqa: F403

STATIC_ROOT = BASE_DIR.parent / "static_cdn" / "static_files"
MEDIA_ROOT = BASE_DIR.parent / "static_cdn" / "media_files"
