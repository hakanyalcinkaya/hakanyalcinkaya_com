"""Sitenin sürümü: commit sayısı ("v178") ve kısa commit kimliği. Superuser'a menüde gösterilir; yereldeki ve sunucudaki
numara karşılaştırılarak sunucunun hangi commit'te olduğu anlaşılır (tam git geçmişi gerekir, sığ klonda sayı küçük çıkar).

Önce deploy'un yazdığı .version dosyası okunur ("v178 abc1234"; _server/deploy.sh): sunucuda uygulama www-data ile
çalışır ve .git'i okuyamayabilir. Dosya yoksa (yerelde) git'e bakılır. Git her istekte çalışmaz: sonuç .git/HEAD ve
dalın ref dosyasının değişme zamanına göre saklanır; yeni commit ya da deploy'da kendiliğinden yenilenir. İkisi de
okunamazsa boş döner.
"""

import subprocess
import threading
from pathlib import Path

from django.conf import settings

_lock = threading.Lock()
_cache = {"key": None, "value": None}


def _git_dir():
    return Path(settings.BASE_DIR) / ".git"


def _version_file():
    return Path(settings.BASE_DIR) / ".version"


def _from_file(path):
    parts = path.read_text().split()
    return {"label": parts[0], "commit": parts[1] if len(parts) > 1 else ""} if parts else None


def _state_key(git_dir):
    """HEAD, dalın ref'i ve packed-refs dosyalarının değişme zamanları; commit gelince değişir."""
    head = git_dir / "HEAD"
    paths = [head, git_dir / "packed-refs"]
    try:
        content = head.read_text().strip()
    except OSError:
        return None
    if content.startswith("ref: "):
        paths.append(git_dir / content[5:])
    return tuple(path.stat().st_mtime_ns if path.exists() else 0 for path in paths)


def _git(*args):
    # Sunucuda uygulama www-data ile, repo ise başka kullanıcıyla sahiplenilmiş: git'in sahiplik denetimi bu depo için açılır.
    command = ["git", "-c", f"safe.directory={settings.BASE_DIR}", "-C", str(settings.BASE_DIR), *args]
    return subprocess.run(command, capture_output=True, text=True, timeout=5, check=True).stdout.strip()


def app_version():
    """{"label": "v178", "commit": "abc1234"}; okunamazsa {"label": "", "commit": ""}."""
    version_file = _version_file()
    try:
        key = ("file", version_file.stat().st_mtime_ns)
    except OSError:
        key = _state_key(_git_dir())
    if key is None:
        return {"label": "", "commit": ""}
    with _lock:
        if _cache["key"] != key:
            try:
                if key[0] == "file":
                    value = _from_file(version_file) or {"label": "", "commit": ""}
                else:
                    value = {"label": f"v{_git('rev-list', '--count', 'HEAD')}", "commit": _git("rev-parse", "--short", "HEAD")}
            except (OSError, subprocess.SubprocessError):
                value = {"label": "", "commit": ""}
            _cache.update(key=key, value=value)
        return _cache["value"]
