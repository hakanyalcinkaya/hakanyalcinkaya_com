# Otomatik güncelleme (GitHub Actions → SSH → deploy.sh)

`main` dalına push edildiğinde GitHub Actions sunucuya SSH ile bağlanır ve `_server/deploy.sh` çalışır. Betik
yeni commit'leri çeker ve **yalnız gereken işi** yapar: hangi servisin yeniden başlayacağı değişen dosyalardan çıkar
(liste `deploy.sh`'nin başında). Push her zaman elle yapılır.

```
git push (elle) ──► GitHub Actions (.github/workflows/deploy.yml)
                        │  ssh (yalnız deploy betiğini çalıştırabilen anahtar)
                        ▼
                 sunucu: _server/deploy.sh ──► git fetch + merge --ff-only
                                             ├─ pip install      (requirements.txt değiştiyse)
                                             ├─ migrate          (migrations değiştiyse)
                                             ├─ collectstatic    (static_files değiştiyse)
                                             ├─ uWSGI reload     (her seferinde, kesintisiz)
                                             ├─ Celery restart   (.py değiştiyse)
                                             └─ Nginx reload     (nginx config değiştiyse)
```

> **Ortak uWSGI'ye dokunulmaz.** Sunucuda başka siteler de aynı uWSGI Emperor'u (`uwsgi.service`) kullanır.
> Deploy yalnız bu sitenin kendi dosyalarını `touch` eder (`reload.txt`, `/etc/uwsgi/sites/hakanyalcinkaya.ini`);
> `uwsgi.service` düzenlenmez, `systemctl restart uwsgi` çalıştırılmaz, sudoers'ta da buna izin verilmez.

Adımlardaki örnekler: sunucu `hakanyalcinkaya.com`, SSH portu `22`, repoyu çeken kullanıcı `hakan`. Kendi
değerlerinle değiştir. Kurulum `README.md`'deki adımlar bittikten sonra yapılır.

---

## 1. Sunucuda deploy kullanıcısını belirle

Deploy, sunucuda repoyu çeken (ve `/var/www/hakanyalcinkaya`'nın sahibi olan) kullanıcıyla yapılır; `www-data` değil.

```bash
# Sunucuda:
stat -c %U /var/www/hakanyalcinkaya/hakanyalcinkaya_dj   # örnek: hakan
whoami                                                   # aynı kullanıcıyla bağlı olmalısın
```

## 2. Sunucunun GitHub'dan çekebildiğini doğrula

README adım 4'te sunucuya salt okunur bir **deploy key** eklenmişti. Şifre sormadan çekebilmeli:

```bash
cd /var/www/hakanyalcinkaya/hakanyalcinkaya_dj
git remote -v                       # git@github-hakanyalcinkaya:hakanyalcinkaya/hakanyalcinkaya_com.git
git fetch origin main && echo tamam # şifre/onay sormadan bitmeli
git rev-parse --is-shallow-repository   # false olmalı (sürüm numarası v178 tam geçmişle sayılır)
```

Sığ klonsa (`true`): `git fetch --unshallow`.

## 3. Log dosyası

Log klasörü `www-data`'nındır; deploy kullanıcısı kendi dosyasına yazar:

```bash
sudo touch /var/www/hakanyalcinkaya/log/deploy.log
sudo chown hakan:hakan /var/www/hakanyalcinkaya/log/deploy.log
```

## 4. GitHub Actions için SSH anahtarı (kendi bilgisayarında)

Bu anahtar yalnız GitHub'a verilir; sunucuya **genel** (public) kısmı eklenir.

```bash
# Kendi bilgisayarında:
ssh-keygen -t ed25519 -C "github-actions-deploy@hakanyalcinkaya.com" -f ~/.ssh/hy_github_actions -N ""
cat ~/.ssh/hy_github_actions.pub     # adım 4b'de sunucuya
cat ~/.ssh/hy_github_actions         # adım 7'de GitHub Secret (DEPLOY_SSH_KEY)
```

### 4b. Anahtarı sunucuya kısıtlı olarak ekle

Satırın başındaki `restrict,command="..."` sayesinde bu anahtarla yalnız deploy betiği çalışır; terminal, port
yönlendirme ya da başka komut açılamaz.

```bash
# Sunucuda (deploy kullanıcısıyla), tek satır; ssh-ed25519 ... kısmı 4'teki .pub dosyasının içeriği:
echo 'restrict,command="/var/www/hakanyalcinkaya/hakanyalcinkaya_dj/_server/deploy.sh" ssh-ed25519 AAAA...BURAYA... github-actions-deploy@hakanyalcinkaya.com' >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
```

Kendi bilgisayarından dene (deploy betiği çalışır; yeni commit yoksa "Yeni commit yok" yazar):

```bash
ssh -i ~/.ssh/hy_github_actions hakan@hakanyalcinkaya.com
```

## 5. Şifresiz sudo (yalnız gereken komutlar)

Betik Celery'yi yeniden başlatmak, servis dosyası değişince `daemon-reload` ve Nginx'i yeniden yüklemek için sudo
kullanır. Yalnız bu komutlara şifresiz izin verilir (`_server/sudoers-deploy`):

```bash
# Sunucuda:
sed 's/DEPLOY_USER/hakan/' /var/www/hakanyalcinkaya/hakanyalcinkaya_dj/_server/sudoers-deploy | sudo tee /etc/sudoers.d/hakanyalcinkaya-deploy
sudo chmod 440 /etc/sudoers.d/hakanyalcinkaya-deploy
sudo visudo -cf /etc/sudoers.d/hakanyalcinkaya-deploy   # "parsed OK"
sudo -k; sudo -n /usr/bin/systemctl restart hakanyalcinkaya-celery && echo izin-tamam   # şifre sormamalı
```

Komut yolları farklıysa (`which systemctl nginx`) dosyada düzeltilir.

## 6. Sunucunun SSH parmak izi (known_hosts)

GitHub'ın bağlandığı sunucunun gerçekten seninki olduğunu doğrulaması için:

```bash
# Kendi bilgisayarında:
ssh-keyscan -p 22 -t ed25519 hakanyalcinkaya.com 2>/dev/null > hy_known_hosts
ssh-keygen -lf hy_known_hosts
# Sunucuda aynı parmak izi görünmeli:
ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub
```

İkisi aynıysa `hy_known_hosts` dosyasının içeriği adım 7'de `DEPLOY_KNOWN_HOSTS` olur.

## 7. GitHub'da ortam ve Secrets

1. GitHub → repo → **Settings → Environments → New environment** → ad: `production`.
   İstersen **Required reviewers** ile her deploy'dan önce onay iste; **Deployment branches** → yalnız `main`.
2. `production` ortamına **Environment secrets** ekle:

| Secret | Değer |
|---|---|
| `DEPLOY_HOST` | `hakanyalcinkaya.com` (ya da sunucunun IP'si) |
| `DEPLOY_USER` | `hakan` (adım 1) |
| `DEPLOY_PORT` | `22` (farklıysa; boş bırakılırsa 22) |
| `DEPLOY_SSH_KEY` | `~/.ssh/hy_github_actions` dosyasının **tamamı** (`-----BEGIN ... END-----` dahil) |
| `DEPLOY_KNOWN_HOSTS` | adım 6'daki `hy_known_hosts` dosyasının içeriği |

Sonra yerel kopyadaki özel anahtarı ve `hy_known_hosts`'u silebilirsin (anahtar yalnız GitHub'da kalsın).

## 8. İlk deneme

1. GitHub → **Actions → Deploy → Run workflow** (main). Push etmeden betiği bir kez çalıştırır.
2. Çıktıda `Yeni commit yok (v178 abc1234)` ya da değişen dosyalar ve yapılan işler görünür.
3. Sunucuda: `tail -n 50 /var/www/hakanyalcinkaya/log/deploy.log`
4. Siteye superuser olarak gir: kullanıcı menüsündeki ve Stüdyo'daki **v178** numarası yereldekiyle aynı olmalı.
   Numara deploy'un yazdığı `.version` dosyasından okunur (`cat .version` → `v178 abc1234`); uygulama `www-data` ile
   çalıştığı için `.git`'e bakmasına gerek kalmaz.

## Günlük kullanım

- Yerelde commit, sonra elle `git push origin main` → birkaç dakika içinde site güncellenir (Actions sekmesinde izlenir).
- **Sürüm kontrolü:** superuser menüde `vNNN` görür (commit sayısı; üstüne gelince kısa commit kimliği). Yerel ve
  sunucu numarası aynıysa ikisi aynı commit'te; sunucunun numarası küçükse henüz deploy olmamış commit var.
- **Deploy istemiyorsan:** commit mesajına `[skip ci]` yaz.
- **Her şeyi yeniden başlat:** commit mesajına `[restart all]` (pip, migrate, collectstatic, uWSGI, Celery, Nginx).
- **Geri almak:** sunucuda elle geri sarma yok (`--ff-only`); hatalı commit yerelde `git revert` ile geri alınıp push edilir.
- **Celery ve video yüklemesi:** `.py` değişen her deploy'da Celery yeniden başlar; süren yükleme en fazla 60 sn
  (servisteki `TimeoutStopSec`) bitirilmeye çalışılır, yarıda kalırsa stüdyodan "Yeniden dene". Uzun yükleme
  sürerken push etmemek en güvenlisi.

## Sorun giderme

| Belirti | Neden / çözüm |
|---|---|
| Actions'ta `Permission denied (publickey)` | `DEPLOY_SSH_KEY` eksik/yanlış ya da 4b'deki satır sunucuda yok |
| `Host key verification failed` | `DEPLOY_KNOWN_HOSTS` eksik ya da sunucunun anahtarı değişti (adım 6) |
| `Not possible to fast-forward` | Sunucuda elle değiştirilmiş dosya var: `git status`; değişiklik geri alınır ya da commit'e taşınır |
| `sudo: a password is required` | Adım 5; komut yolu sudoers'takiyle birebir aynı olmalı |
| `deploy.log: Permission denied` | Adım 3 |
| Menüde sürüm yok ya da eski | Sunucu elle `git pull` ile güncellendiyse `.version` yenilenmez: `bash _server/deploy.sh` çalıştır (yeni commit yoksa yalnız `.version`'ı yazar) |
| Site açılmıyor (502) | `sudo journalctl -u uwsgi -n 50`, `tail /var/www/hakanyalcinkaya/log/uwsgi.log` |
