"""Bootstrap Icons'un yalnız kullanılan ikonları: tam paket (frontend/bootstrap-icons/, 2000+ ikon) kaynak olarak durur;
şablonlarda, JS'te ve Python'da geçen `bi-…` adları taranır, o ikonları içeren küçük font ve CSS static_files/icons/
altına üretilir (git'e girmez).

Üretim: `manage.py build_icons`. Geliştirmede runserver açılınca ve dosya değişince kendiliğinden (core/apps.py), sunucuda
deploy betiği her güncellemede çalıştırır. İkon listesi değişmediyse hiçbir şey yazılmaz.
"""

import hashlib
import json
import re
from pathlib import Path

from django.conf import settings

SOURCE_DIR = settings.BASE_DIR / "frontend" / "bootstrap-icons"
SOURCE_CSS = SOURCE_DIR / "bootstrap-icons.css"
SOURCE_FONT = SOURCE_DIR / "fonts" / "bootstrap-icons.woff2"
OUTPUT_DIR = settings.BASE_DIR / "static_files" / "icons"
OUTPUT_CSS = OUTPUT_DIR / "bootstrap-icons.css"
OUTPUT_FONT = OUTPUT_DIR / "bootstrap-icons.woff2"
MANIFEST = OUTPUT_DIR / "icons.json"

SCAN_SUFFIXES = (".html", ".js", ".py", ".css")
# Taranmayan klasörler: kaynak paket (bütün adları içerir), üretilen çıktı, derlenmiş/indirilmiş dosyalar ve tasarım taslakları.
SKIP_DIRS = {
    ".git",
    "__pycache__",
    "node_modules",
    "media_files",
    "video",
    "_design",
    "_project",
    "frontend",
    "icons",
    "videojs",
    "migrations",
}

ICON_NAME = re.compile(r"\bbi-([a-z0-9]+(?:-[a-z0-9]+)*)")
ICON_RULE = re.compile(r'\.bi-([a-z0-9-]+)::before\{content:"\\([0-9a-f]+)"\}')
BASE_RULE = re.compile(r"\.bi::before,[^{]*\{[^}]*\}")


def source_icons():
    """Tam paketteki ikonlar: {ad: kod noktası}."""
    return {name: int(code, 16) for name, code in ICON_RULE.findall(SOURCE_CSS.read_text())}


def _scanned_files():
    for path in settings.BASE_DIR.rglob("*"):
        if path.suffix in SCAN_SUFFIXES and path.is_file() and not SKIP_DIRS.intersection(path.relative_to(settings.BASE_DIR).parts):
            yield path


def used_icons(available):
    """Kodda geçen ve pakette bulunan ikon adları (sıralı)."""
    found = set()
    for path in _scanned_files():
        try:
            found.update(ICON_NAME.findall(path.read_text(errors="ignore")))
        except OSError:
            continue
    return sorted(found & available.keys())


def _source_hash():
    digest = hashlib.sha256(SOURCE_CSS.read_bytes())
    digest.update(SOURCE_FONT.read_bytes())
    return digest.hexdigest()[:16]


def is_current(names, source_hash):
    try:
        manifest = json.loads(MANIFEST.read_text())
    except (OSError, ValueError):
        return False
    return (
        manifest.get("icons") == names
        and manifest.get("source") == source_hash
        and OUTPUT_CSS.exists()
        and OUTPUT_FONT.exists()
    )


def _subset_font(codes):
    import logging

    from fontTools import subset

    # Kaynak fonttaki zararsız biçim uyarıları ("extra bytes in post.stringData") çıktıyı kirletmesin.
    logging.getLogger("fontTools").setLevel(logging.ERROR)
    options = subset.Options()
    options.flavor = "woff2"
    font = subset.load_font(str(SOURCE_FONT), options)
    subsetter = subset.Subsetter(options)
    subsetter.populate(unicodes=codes)
    subsetter.subset(font)
    subset.save_font(font, str(OUTPUT_FONT), options)


def build(force=False):
    """Gerekiyorsa küçük font ve CSS'i üretir; (üretildi mi, ikon sayısı) döner."""
    available = source_icons()
    names = used_icons(available)
    source_hash = _source_hash()
    if not force and is_current(names, source_hash):
        return False, len(names)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    _subset_font([available[name] for name in names])
    font_hash = hashlib.sha256(OUTPUT_FONT.read_bytes()).hexdigest()[:12]
    source = SOURCE_CSS.read_text()
    header = source[: source.index("*/") + 2] if source.startswith("/*") else ""
    rules = "".join(f'.bi-{name}::before{{content:"\\{available[name]:x}"}}' for name in names)
    OUTPUT_CSS.write_text(
        f"{header}\n/* Üretildi: manage.py build_icons ({len(names)} ikon). Elle düzenleme; kaynak frontend/bootstrap-icons/. */\n"
        f'@font-face{{font-display:block;font-family:bootstrap-icons;src:url("bootstrap-icons.woff2?{font_hash}") format("woff2")}}'
        f"{BASE_RULE.search(source).group(0)}{rules}\n"
    )
    MANIFEST.write_text(json.dumps({"source": source_hash, "icons": names}, indent=0))
    return True, len(names)
