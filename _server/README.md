# Sunucu kurulumu (hakanyalcinkaya.com)

Ubuntu 24.04 (Python 3.12 sistemle gelir) için adım adım kurulum. Bu klasördeki dosyalar şu yolları varsayar; farklı
bir yol seçilirse dosyalardaki yollar da değiştirilmelidir:

| Ne | Yol |
|---|---|
| Kod (bu repo) | `/var/www/hakanyalcinkaya/hakanyalcinkaya_dj` |
| Statik / medya | `/var/www/hakanyalcinkaya/static_cdn/static_files`, `.../media_files` (`settings_prod.py`) |
| uWSGI log | `/var/www/hakanyalcinkaya/log/uwsgi.log` |
| venv | `/var/Env/hakanyalcinkaya_312` |
| uWSGI soketi | `/run/uwsgi/hakanyalcinkaya.sock` |

Komutlar sudo yetkili bir kullanıcıyla çalıştırılır. Uygulama `www-data` kullanıcısıyla çalışır.

## 0. Ön koşullar

- DNS: `hakanyalcinkaya.com` ve `www.hakanyalcinkaya.com` için A (ve varsa AAAA) kaydı sunucuyu göstermeli.
- Disk: stüdyoda yüklenen video önce Nginx'in geçici klasörüne (`/var/lib/nginx/body`), sonra Django'nun geçici
  dosyasına, sonra `media_files/video_uploads/` altına yazılır. En büyük videonun en az 3 katı boş yer olmalı.
  Platforma gönderilip işlenince dosya silinir.

## 1. Paketler

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y git python3.12-venv postgresql redis-server nginx ufw
```

Kurulu olan paketler (ör. Nginx, PostgreSQL) atlanır. Celery sistem paketi değildir; venv'e pip ile kurulur (adım 5). Celery'nin istediği sistem servisi
Redis'tir.

## 2. Güvenlik duvarı

```bash
sudo ufw allow OpenSSH
sudo ufw allow "Nginx Full"
sudo ufw enable
```

## 3. Klasörler

```bash
sudo mkdir -p /var/www/hakanyalcinkaya/{log,static_cdn/static_files,static_cdn/media_files} /var/Env
sudo chown -R $USER:$USER /var/www/hakanyalcinkaya /var/Env
# Uygulamanın yazdığı yerler: yüklenen dosyalar ve log
sudo chown -R www-data:www-data /var/www/hakanyalcinkaya/static_cdn/media_files /var/www/hakanyalcinkaya/log
```

## 4. Kod

Repo özelse sunucuya salt okunur bir deploy anahtarı eklenir (GitHub → repo → Settings → Deploy keys):

```bash
ssh-keygen -t ed25519 -C "deploy@hakanyalcinkaya.com" -f ~/.ssh/hakanyalcinkaya_deploy -N ""
cat ~/.ssh/hakanyalcinkaya_deploy.pub   # GitHub'a eklenir
cat >> ~/.ssh/config <<'EOF'
Host github-hakanyalcinkaya
    HostName github.com
    IdentityFile ~/.ssh/hakanyalcinkaya_deploy
EOF
git clone git@github-hakanyalcinkaya:hakanyalcinkaya/hakanyalcinkaya_com.git /var/www/hakanyalcinkaya/hakanyalcinkaya_dj
```

## 5. Python ortamı

```bash
python3.12 -m venv /var/Env/hakanyalcinkaya_312
/var/Env/hakanyalcinkaya_312/bin/pip install --upgrade pip
/var/Env/hakanyalcinkaya_312/bin/pip install -r /var/www/hakanyalcinkaya/hakanyalcinkaya_dj/requirements.txt
```

## 6. PostgreSQL

Django 6.1 en az PostgreSQL 15 ister (Django 6.0: 14). Ubuntu 24.04 paketi 16'dır; sürüm: `psql --version`.

```bash
sudo -u postgres psql <<'EOF'
CREATE USER hakanyalcinkaya WITH PASSWORD 'GÜÇLÜ-BİR-ŞİFRE';
CREATE DATABASE hakanyalcinkaya OWNER hakanyalcinkaya ENCODING 'UTF8' TEMPLATE template0;
EOF
```

Şifre yalnız `.env`'ye yazılır (adım 8).

## 7. Redis

Ubuntu paketi kurulunca çalışır ve yalnız `127.0.0.1`'i dinler. Kontrol:

```bash
redis-cli ping   # PONG
```

Sunucuda Redis kullanan başka proje varsa bu proje ayrı bir veritabanı numarası kullanır (`.env.copy`'de `/2`).

## 8. `.env`

```bash
cd /var/www/hakanyalcinkaya/hakanyalcinkaya_dj
cp .env.copy .env
nano .env
sudo chown $USER:www-data .env && chmod 640 .env
```

Doldurulacaklar: `SECRET_KEY` (dosyadaki komutla üretilir), `DB_*`, Bunny/Vimeo anahtarları, `SENDGRID_API_KEY`.
`DEBUG=False` kalmalı. Yayına çıkarken `EMAIL_REDIRECT_TO` boş olmalı (yoksa bütün e-postalar o adrese gider).

## 9. Django

```bash
cd /var/www/hakanyalcinkaya/hakanyalcinkaya_dj
PY=/var/Env/hakanyalcinkaya_312/bin/python
$PY manage.py check --deploy
$PY manage.py migrate
$PY manage.py collectstatic --noinput
$PY manage.py createsuperuser
```

Yönetim paneli `/verona/` adresindedir (`/admin/` sahte giriş sayfası).

## 10. SSL sertifikası

Sertifika `hakanyalcinkaya.com` ve `www.hakanyalcinkaya.com`'u kapsamalıdır. Nginx dosyaları doğrudan bu klasörden
okur (kopya ya da link yok); `_server/ssl/` git'te takip edilmez (`.gitignore`):

| Dosya | İçerik |
|---|---|
| `_server/ssl/hakanyalcinkaya_2026.crt` | Alan adı sertifikası + ara sertifika(lar), bu sırayla; kök sertifika eklenmez |
| `_server/ssl/hakanyalcinkaya_2026.key` | Özel anahtar |
| `_server/ssl/hakanyalcinkaya_2026.csr` | Sertifika isteği (yalnız sağlayıcıya verilir) |

CSR ve anahtar sunucuda üretilir (`-subj` değerleri sağlayıcının istediği bilgilerle):

```bash
cd /var/www/hakanyalcinkaya/hakanyalcinkaya_dj/_server/ssl
openssl req -new -newkey rsa:2048 -nodes -keyout hakanyalcinkaya_2026.key -out hakanyalcinkaya_2026.csr -subj "/C=TR/ST=Istanbul/L=Istanbul/O=Hakan Yalcinkaya/CN=hakanyalcinkaya.com/emailAddress=admin@hakanyalcinkaya.com" -addext "subjectAltName=DNS:hakanyalcinkaya.com,DNS:www.hakanyalcinkaya.com"
chmod 600 hakanyalcinkaya_2026.key
```

Sertifika gelince kontrol:

```bash
openssl x509 -noout -subject -issuer -dates -ext subjectAltName -in hakanyalcinkaya_2026.crt
openssl crl2pkcs7 -nocrl -certfile hakanyalcinkaya_2026.crt | openssl pkcs7 -print_certs -noout   # zincir; son sertifikada subject = issuer ise kök, çıkarılır
# Anahtar ile sertifika eşleşiyor mu (iki satır aynı olmalı):
openssl x509 -noout -pubkey -in hakanyalcinkaya_2026.crt | openssl sha256
openssl pkey -pubout -in hakanyalcinkaya_2026.key | openssl sha256
```

Yenilemede (DV sertifika en fazla 200 gün; 2026 sertifikası 15 Mayıs 2027'de biter) yeni dosyalar yeni yıl adıyla
bu klasöre konur, `hakanyalcinkaya_nginx.conf`'taki dört `ssl_certificate*` satırı güncellenir ve
`sudo nginx -t && sudo systemctl reload nginx` çalıştırılır.

## 11. Nginx

```bash
sudo rm -f /etc/nginx/sites-enabled/default
sudo ln -sf /var/www/hakanyalcinkaya/hakanyalcinkaya_dj/_server/hakanyalcinkaya_nginx.conf /etc/nginx/sites-enabled/hakanyalcinkaya.conf
sudo nginx -t
sudo systemctl reload nginx
```

Config Nginx 1.24 (Ubuntu 24.04) için `listen 443 ssl http2;` yazımını kullanır. Nginx 1.25.1 ve üstünde bu yazım
uyarı verir (`the "listen ... http2" directive is deprecated`); yükseltilirse `http2` `listen` satırlarından çıkarılıp
her 443 bloğuna `http2 on;` eklenir.

## 12. uWSGI

Sunucudaki uWSGI Emperor (`uwsgi.service`) `/etc/uwsgi/sites` altındaki her .ini'yi ayrı bir site olarak çalıştırır
ve `/var/Env/python_312/bin/uwsgi` (Python 3.12) kullanır; bu proje de 3.12 olduğu için aynı Emperor'a eklenir.
`uwsgi.service` sunucunun ortak dosyasıdır, bu projeden değiştirilmez.

Stüdyonun uzun yükleme süresi (`route = ^/studio/ harakiri:900`) uwsgi'nin PCRE desteğiyle derlenmesini ister. Logda
`no internal routing support` yazıyorsa ortak uwsgi yeniden derlenir (Emperor'daki bütün siteler birkaç saniye
yeniden başlar):

```bash
sudo apt install -y libpcre2-dev build-essential python3-dev
sudo /var/Env/python_312/bin/pip install --no-cache-dir --force-reinstall --no-deps "uwsgi==$(/var/Env/python_312/bin/uwsgi --version)"
timeout 3 /var/Env/python_312/bin/uwsgi --route '^/x harakiri:900' --http-socket 127.0.0.1:39123 2>&1 | grep -i routing   # boş olmalı
sudo systemctl restart uwsgi
```

```bash
touch /var/www/hakanyalcinkaya/hakanyalcinkaya_dj/reload.txt
sudo ln -sf /var/www/hakanyalcinkaya/hakanyalcinkaya_dj/_server/hakanyalcinkaya_uwsgi.ini /etc/uwsgi/sites/hakanyalcinkaya.ini
systemctl status uwsgi --no-pager | head -6       # "governing N vassals" bir artmalı
sudo journalctl -u uwsgi -n 50 --no-pager          # site açılmazsa Emperor'un hatası
ls -l /run/uwsgi/hakanyalcinkaya.sock
```

## 13. Celery

[celery/README.md](celery/README.md):

```bash
sudo mkdir -p /var/log/celery && sudo chown www-data:www-data /var/log/celery
sudo ln -sf /var/www/hakanyalcinkaya/hakanyalcinkaya_dj/_server/celery/hakanyalcinkaya-celery.service /etc/systemd/system/hakanyalcinkaya-celery.service
sudo systemctl daemon-reload
sudo systemctl enable --now hakanyalcinkaya-celery
```

## 14. Kontrol

```bash
curl -sI http://hakanyalcinkaya.com | head -3          # 301 -> https://hakanyalcinkaya.com/
curl -sI https://www.hakanyalcinkaya.com | head -3     # 301 -> https://hakanyalcinkaya.com/
curl -sI https://hakanyalcinkaya.com | head -20        # 200; Strict-Transport-Security tek kez
curl -sI https://hakanyalcinkaya.com/media/video_uploads/x.mp4 | head -1   # 404
systemctl status uwsgi hakanyalcinkaya-celery nginx
tail -f /var/www/hakanyalcinkaya/log/uwsgi.log /var/log/nginx/hakanyalcinkaya_error.log
```

Tarayıcıda: giriş, `/studio/`'da işçinin çalışır göründüğü ve küçük bir videonun yüklenip platforma gittiği denenir.

## 15. Yedek

Günlük veritabanı yedeği (7 gün saklanır):

```bash
sudo mkdir -p /var/backups/hakanyalcinkaya && sudo chown postgres:postgres /var/backups/hakanyalcinkaya
echo '30 3 * * * postgres pg_dump -Fc hakanyalcinkaya > /var/backups/hakanyalcinkaya/db-$(date +\%F).dump && find /var/backups/hakanyalcinkaya -name "db-*.dump" -mtime +7 -delete' | sudo tee /etc/cron.d/hakanyalcinkaya-backup
```

`media_files` (kurs görselleri, eğitmen fotoğrafları, altyazılar) ve `.env` de sunucu dışına yedeklenmelidir.

## Güncelleme (deploy)

`main`'e push edilince GitHub Actions sunucuyu kendisi günceller: kurulum ve kullanım [DEPLOY.md](DEPLOY.md). Elle
çalıştırmak için `bash _server/deploy.sh` (yalnız gereken servisleri yeniden başlatır). Betik olmadan elle:

```bash
cd /var/www/hakanyalcinkaya/hakanyalcinkaya_dj
PY=/var/Env/hakanyalcinkaya_312/bin/python
git pull
/var/Env/hakanyalcinkaya_312/bin/pip install -r requirements.txt
$PY manage.py migrate
$PY manage.py collectstatic --noinput
touch reload.txt                                  # uWSGI kesintisiz yeniden yüklenir
sudo systemctl restart hakanyalcinkaya-celery     # süren video yüklemesi yarıda kalır; stüdyodan yeniden denenir
```

`_server/` altındaki bir servis dosyası değiştiyse `sudo systemctl daemon-reload`, Nginx config'i değiştiyse
`sudo nginx -t && sudo systemctl reload nginx`, uWSGI ini değiştiyse `touch /etc/uwsgi/sites/hakanyalcinkaya.ini` (Emperor siteyi yeniden açar).

## Yayından sonra

- Bunny panelinde izinli alan adı `hakanyalcinkaya.com`; Vimeo için `.env` `VIMEO_EMBED_DOMAINS`.
- SendGrid'de gönderici alan adı doğrulaması (SPF/DKIM) ve gerçek gönderim testi.
- Birkaç gün sorunsuz çalışınca `.env`'de `SECURE_HSTS_SECONDS=31536000`, ardından `touch reload.txt`.
- Diğer açık işler: kök klasördeki `TODO.md`.
