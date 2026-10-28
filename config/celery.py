"""Celery uygulaması. Çalıştırma: `celery -A config worker -l info -P threads` (Redis açık olmalı).

İşler ağ ağırlıklı (Vimeo yükleme); thread havuzu yeterli. macOS'ta varsayılan prefork havuzu görevleri çalıştıramıyor.
"""

import os
import threading
import time

import redis
from celery import Celery
from celery.signals import worker_ready, worker_shutdown
from kombu.exceptions import OperationalError

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("config")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

# İşçi ayaktayken Redis'te kısa ömürlü bir anahtar tutar; panel işçinin çalışıp çalışmadığını buradan anlar.
# Kontrol mesajıyla (ping) sorgu thread havuzunda zaman zaman yanıtsız kalıyor.
HEARTBEAT_KEY = "studio:celery-worker"
HEARTBEAT_SECONDS = 10


def _redis():
    return redis.Redis.from_url(app.conf.broker_url, socket_timeout=1, socket_connect_timeout=1)


@worker_ready.connect
def start_heartbeat(sender=None, **kwargs):
    client = _redis()
    hostname = getattr(sender, "hostname", "worker")

    def beat():
        while True:
            try:
                client.set(HEARTBEAT_KEY, hostname, ex=HEARTBEAT_SECONDS * 3)
            except redis.RedisError:
                pass
            time.sleep(HEARTBEAT_SECONDS)

    threading.Thread(target=beat, name="studio-heartbeat", daemon=True).start()


@worker_shutdown.connect
def stop_heartbeat(**kwargs):
    try:
        _redis().delete(HEARTBEAT_KEY)
    except redis.RedisError:
        pass


def worker_online():
    """Çalışan bir işçi var mı. Heartbeat yoksa (eski sürümle başlatılmış işçi) ping ile yoklanır."""
    try:
        if _redis().exists(HEARTBEAT_KEY):
            return True
    except redis.RedisError:
        return False
    try:
        return bool(app.control.ping(timeout=1))
    except (OperationalError, OSError):
        return False
