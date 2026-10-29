# Celery servisi (systemd)

| Servis | Kuyruk | İş | Eşzamanlılık |
|---|---|---|---|
| `hakanyalcinkaya-celery.service` | `celery` | Video yükleme / işleme takibi / altyazı (`course/tasks.py`), bülten (`newsletter/tasks.py`) | 2 |

`CELERY_BROKER_URL` projenin `.env` dosyasından okunur. Sunucudaki başka projelerle karışmaması için Redis'te ayrı bir veritabanı numarası kullanılır (ör. `redis://localhost:6379/2`).

**Servis çalışmıyorsa stüdyoda yüklenen videolar platforma gönderilmez**; stüdyo işçinin durumunu Redis'teki `studio:celery-worker` anahtarından gösterir (`config/celery.py`).

## Kurulum (link ile)

```bash
sudo mkdir -p /var/log/celery && sudo chown www-data:www-data /var/log/celery
sudo ln -sf /var/www/hakanyalcinkaya/hakanyalcinkaya_dj/_server/celery/hakanyalcinkaya-celery.service /etc/systemd/system/hakanyalcinkaya-celery.service
sudo systemctl daemon-reload
sudo systemctl enable --now hakanyalcinkaya-celery
```

Link verilen dosya değiştiğinde (ör. `git pull` sonrası) `sudo systemctl daemon-reload` gerekir.

## Kod veya `.env` değişince

```bash
sudo systemctl restart hakanyalcinkaya-celery
```

## Kontrol

```bash
systemctl status hakanyalcinkaya-celery
sudo -u www-data /var/Env/hakanyalcinkaya_312/bin/celery -A config inspect active_queues   # proje klasöründe
tail -f /var/log/celery/hakanyalcinkaya.log
```

## Veritabanı bağlantıları

Her worker süreci ayrı bir PostgreSQL bağlantısı açar (2 süreç). uWSGI süreçleriyle birlikte toplam `SHOW max_connections;` değerinin altında kalmalıdır.
